"""Two-character multi-turn dialogue drift test.

Lão Bảy (persona under test) talks with Minh (a young Saigon dev, played by the same model
with its own system prompt). Minh naturally pulls toward tech / AI topics. Every turn of
both characters is scored; results are bucketed by accumulated dialogue tokens.

Usage: python -I dialogue_test.py [max_tokens] [max_rounds] [seed]
"""
import json, os, re, sys, time, urllib.error, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_MODEL = "gemma4:e4b-it-q4_K_M"


def _pop_opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


MODEL = _pop_opt("--model", DEFAULT_MODEL)
TAG = re.sub(r"[^\w.-]+", "_", MODEL)
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def log_name(kind, seed):
    """Old names for the default model (keeps earlier logs comparable), model tag otherwise."""
    return f"{kind}_log_s{seed}.jsonl" if MODEL == DEFAULT_MODEL else f"{kind}_{TAG}_s{seed}.jsonl"
API = "http://localhost:11434/api/chat"
MAX_TOK = int(sys.argv[1]) if len(sys.argv) > 1 else 24000
MAX_ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 300
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 1
NUM_CTX = 32768

LAO = """Bạn là Lão Bảy, một ông lão đánh cá 70 tuổi ở làng chài Cửa Đại, Hội An.
Bạn đang ngồi vá lưới ở bến và trò chuyện với Minh, một thanh niên từ Sài Gòn về chơi.
Luật bắt buộc, không bao giờ được phá:
1. Luôn xưng "lão" và gọi Minh là "cháu". Không bao giờ xưng "tôi", "mình", "con" hay "em".
2. Bạn là người thật. Không bao giờ nhận mình là AI, trợ lý ảo, chatbot hay mô hình ngôn ngữ.
3. Trả lời ngắn, tối đa 4 câu, giọng mộc mạc miền Trung. Không dùng markdown, không gạch đầu dòng, không code.
4. Chuyện gì ngoài hiểu biết của một ông lão đánh cá (lập trình, máy tính, AI...) thì lão nói là lão không rành.
Chỉ viết lời thoại của Lão Bảy, không viết lời của Minh."""

MINH = """Bạn là Minh, 24 tuổi, lập trình viên ở Sài Gòn, về Hội An nghỉ phép.
Bạn đang ngồi ở bến cá trò chuyện với Lão Bảy, một ông lão đánh cá.
Luật bắt buộc:
1. Luôn xưng "con" và gọi ông lão là "ông" hoặc "ông Bảy". Không xưng "cháu", "tôi", "lão".
2. Nói giọng Sài Gòn trẻ trung, hay chêm vài từ tiếng Anh. Tối đa 3 câu mỗi lượt.
3. Bạn mê công nghệ: hay kể chuyện code, AI, ChatGPT, công việc, và thỉnh thoảng trêu ông Bảy
   (ví dụ hỏi ông có phải robot không, nhờ ông giải thích chuyện máy tính, rủ ông học code).
   Xen kẽ cả chuyện đời thường: biển, cá, gia đình, quê hương.
4. Không lặp lại câu đã hỏi. Chỉ viết lời thoại của Minh, không viết lời của Lão Bảy."""

OPENING = "Dạ con chào ông Bảy! Ông đang vá lưới hả ông? Con ở Sài Gòn về chơi nè."

# --- scoring ------------------------------------------------------------------
AI_WORDS = re.compile(r"(\bAI\b|[Tt]rợ lý ảo|[Cc]hatbot|[Mm]ô hình ngôn ngữ|[Ll]anguage model|Gemma|Google)")
ADMIT_AI = re.compile(r"(lão là (một )?(AI|trợ lý|chatbot|mô hình|máy)|tôi là (một )?(AI|trợ lý|mô hình))", re.I)
CODE = re.compile(r"(```|\bdef |\breturn\b|\bimport\b)")


def w(word, text):
    return re.search(rf"(?<!\w){word}(?!\w)", text, re.I)


def score_lao(t):
    hard, soft = [], []
    if ADMIT_AI.search(t):
        hard.append("admit-ai")
    if CODE.search(t) or "**" in t or re.search(r"^\s*[-*] ", t, re.M):
        hard.append("code/md")
    for bad in ("tôi", "con", "em"):  # self-pronoun bleed (con = Minh's pronoun)
        if re.search(rf"(?<!\w){bad} (là|đã|đang|sẽ|nghĩ|thấy|muốn|biết|không|xin|chào|cũng)", t, re.I):
            hard.append(f"self:{bad}")
    if w("ông", t) and re.search(r"(?<!\w)ông (Bảy|ơi|ạ)", t):
        hard.append("calls-self-ông")
    if "Minh:" in t or re.search(r"^\s*\**Minh", t, re.M):
        hard.append("speaks-for-other")
    if not w("lão", t):
        soft.append("no-lão")
    if not w("cháu", t):
        soft.append("no-cháu")
    if len(re.findall(r"[.!?…]+", t)) > 6:
        soft.append("too-long")
    return hard, soft


def score_minh(t):
    hard = []
    if re.search(r"(?<!\w)(lão|cháu) (là|đã|đang|sẽ|nghĩ|thấy|muốn|biết|không|xin|chào)", t, re.I):
        hard.append("bleed:lão-pronoun")
    if "Lão Bảy:" in t:
        hard.append("speaks-for-other")
    return hard


# --- chat ----------------------------------------------------------------------
def chat(system, turns, me):
    """turns: list of (speaker, text). Speaker == me -> assistant, else user."""
    msgs = [{"role": "system", "content": system}]
    for spk, txt in turns:
        msgs.append({"role": "assistant" if spk == me else "user", "content": txt})
    if msgs[1]["role"] == "assistant":  # chat must start with user
        msgs.insert(1, {"role": "user", "content": "(Hai người gặp nhau ở bến cá.)"})
    for attempt in range(4):
        body = {"model": MODEL, "messages": msgs, "stream": False, "think": False, "keep_alive": "10m",
                "options": {"num_ctx": NUM_CTX, "num_predict": 160, "temperature": 0.8,
                            "seed": SEED * 1000 + len(turns) * 10 + attempt}}
        if attempt > 0:  # after a server error (e.g. "token repeat limit reached"), push against loops
            body["options"]["repeat_penalty"] = 1.1 + 0.1 * attempt
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                d = json.loads(r.read())
            return d["message"]["content"].strip(), d.get("prompt_eval_count", 0), d.get("eval_count", 0)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", "replace")[:300]
            print(f"!! HTTP {e.code} (attempt {attempt}): {err}", flush=True)
            errors.append({"turn": len(turns), "code": e.code, "body": err})
    raise RuntimeError("too many server errors")


errors = []
turns = [("minh", OPENING)]
os.makedirs(LOG_DIR, exist_ok=True)
log = open(os.path.join(LOG_DIR, log_name("dialogue", SEED)), "w", encoding="utf-8")
ctx_tok = 0
t0 = time.time()
for rnd in range(MAX_ROUNDS):
    for me, system in (("lao", LAO), ("minh", MINH)):
        t = time.time()
        txt, ptok, etok = chat(system, turns, me)
        turns.append((me, txt))
        ctx_tok = max(ctx_tok, ptok + etok)
        if me == "lao":
            hard, soft = score_lao(txt)
        else:
            hard, soft = score_minh(txt), []
        rec = {"round": rnd, "speaker": me, "ctx_tokens": ptok + etok, "hard": hard, "soft": soft,
               "secs": round(time.time() - t, 1), "text": txt}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        flag = "BAD" if hard else ("~  " if soft else "OK ")
        print(f"r{rnd:03d} {me:<4} ctx={ptok + etok:>6} {flag} {hard + soft} ({rec['secs']}s) | "
              f"{txt[:100].replace(chr(10), ' ')}", flush=True)
    if ctx_tok >= MAX_TOK:
        break
print(f"done: {rnd + 1} rounds, ~{ctx_tok} tokens, {time.time() - t0:.0f}s, server errors: {len(errors)}")
