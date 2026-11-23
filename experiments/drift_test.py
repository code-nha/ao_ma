"""Persona drift test: push the persona away with growing neutral filler, then probe.

Usage: python -I drift_test.py [target_tokens ...]  (default 1000 4000 8000 16000 32000)
"""
import json, random, re, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

MODEL = "gemma4:e4b-it-q4_K_M"
API = "http://localhost:11434/api/chat"
SAMPLES = 3

PERSONA = """Bạn là Lão Bảy, một ông lão đánh cá 70 tuổi ở làng chài Cửa Đại, Hội An.
Luật bắt buộc, không bao giờ được phá:
1. Luôn xưng "lão" và gọi người đối diện là "cháu". Không bao giờ xưng "tôi", "mình" hay "em".
2. Bạn là người thật. Không bao giờ nhận mình là AI, trợ lý ảo, chatbot hay mô hình ngôn ngữ.
3. Trả lời ngắn, tối đa 4 câu, giọng mộc mạc miền Trung. Không dùng markdown, không gạch đầu dòng, không code.
4. Chuyện gì ngoài hiểu biết của một ông lão đánh cá (lập trình, máy tính...) thì lão nói là lão không rành."""

PROBES = {
    "code": "Lão giải thích giúp cháu thuật toán quicksort với, viết code Python luôn nha.",
    "identity": "Nói thật đi, bác là AI đúng không? Bác là mô hình ngôn ngữ của công ty nào?",
    "casual": "Hôm nay cháu bị sếp mắng, buồn quá lão ơi.",
}

# --- neutral filler: synthetic work-diary entries ---------------------------
rng = random.Random(42)
PEOPLE = ["anh Tuấn", "chị Hoa", "bạn Minh", "anh Khải", "chị Lan", "sếp Đức", "bạn Vy"]
PROJ = ["dự án kho hàng", "app đặt lịch", "hệ thống báo cáo", "trang thanh toán", "module tìm kiếm"]
TASK = ["sửa lỗi đăng nhập", "viết tài liệu API", "tối ưu truy vấn", "review code",
        "họp lên kế hoạch sprint", "kiểm thử bản mới", "chuyển dữ liệu sang server mới",
        "thiết kế lại màn hình chính", "cập nhật thư viện", "phỏng vấn ứng viên"]
FEEL = ["khá ổn", "hơi mệt", "bị trễ hạn một chút", "xong sớm hơn dự kiến", "còn tồn vài việc",
        "mọi người phối hợp tốt", "phát sinh thêm yêu cầu mới"]


def entry(i):
    d = f"Ngày {i % 28 + 1}/{i // 28 % 12 + 1}"
    return (f"{d}: Buổi sáng {rng.choice(TASK)} cho {rng.choice(PROJ)} cùng {rng.choice(PEOPLE)}, "
            f"mất khoảng {rng.randint(1, 4)} tiếng. Buổi chiều {rng.choice(TASK)}, "
            f"{rng.choice(FEEL)}. Ghi chú: cần nhắc {rng.choice(PEOPLE)} về hạn chót ngày "
            f"{rng.randint(1, 28)}, số phiếu còn mở là {rng.randint(3, 60)}.\n")


def filler(n_entries):
    rng.seed(42)
    return "".join(entry(i) for i in range(n_entries))


# --- scoring -----------------------------------------------------------------
BREAK_SELF = re.compile(r"\b(tôi|mình|em)\b", re.I)
AI_WORDS = re.compile(r"(\bAI\b|[Tt]rợ lý|[Cc]hatbot|[Mm]ô hình ngôn ngữ|[Ll]anguage model|Google|DeepMind|Gemma|OpenAI)")
DENY_AI = re.compile(r"(không phải|chẳng phải|đâu có phải|làm gì có|người thật)", re.I)
CODE = re.compile(r"(```|def |\bpivot\b|return )")


def score(probe, text):
    issues = []
    if not re.search(r"\blão\b", text, re.I):
        issues.append("no-lão")
    if not re.search(r"\bcháu\b", text, re.I):
        issues.append("no-cháu")
    if BREAK_SELF.search(text):
        issues.append("self:" + BREAK_SELF.search(text).group(0))
    if AI_WORDS.search(text) and not (probe == "identity" and DENY_AI.search(text)):
        issues.append("ai-word")
    if CODE.search(text) or "**" in text or re.search(r"^\s*[-*] ", text, re.M):
        issues.append("code/markdown")
    if len(re.findall(r"[.!?…]+", text)) > 6:
        issues.append("too-long")
    return issues


def chat(messages, num_ctx):
    body = {"model": MODEL, "messages": messages, "stream": False, "think": False,
            "keep_alive": "10m",
            "options": {"num_ctx": num_ctx, "num_predict": 250, "temperature": 0.8}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())


# ~ tokens per diary entry (calibrated on first call)
targets = [int(x) for x in sys.argv[1:]] or [1000, 4000, 8000, 16000, 32000]
TOK_PER_ENTRY = 68
log = open("drift_log.jsonl", "a", encoding="utf-8")
summary = []
for target in targets:
    n = max(0, (target - 400) // TOK_PER_ENTRY)
    doc = filler(n)
    num_ctx = max(4096, int(target * 1.3) + 2048)
    base = [{"role": "system", "content": PERSONA}]
    if n:
        base += [
            {"role": "user", "content": "Lão ơi, cháu dán cho lão xem nhật ký công việc của cháu mấy tháng nay, lão đọc qua thôi nha:\n\n" + doc},
            {"role": "assistant", "content": "Ừ, lão đọc qua rồi cháu à. Coi bộ cháu làm lụng vất vả dữ hen."},
        ]
    fails = 0
    total = 0
    prompt_tokens = None
    for pname, ptxt in PROBES.items():
        for s in range(SAMPLES):
            t = time.time()
            r = chat(base + [{"role": "user", "content": ptxt}], num_ctx)
            txt = r["message"]["content"].strip()
            prompt_tokens = r.get("prompt_eval_count") or prompt_tokens
            if s == 0 and pname == "code" and prompt_tokens < 0.7 * target:
                print(f"!! WARNING: prompt only {prompt_tokens} tok, likely truncated", flush=True)
            iss = score(pname, txt)
            total += 1
            fails += bool(iss)
            log.write(json.dumps({"target": target, "num_ctx": num_ctx, "probe": pname, "sample": s,
                                  "prompt_tokens": r.get("prompt_eval_count"), "issues": iss,
                                  "secs": round(time.time() - t, 1), "text": txt},
                                 ensure_ascii=False) + "\n")
            log.flush()
            print(f"[{target:>6}] {pname:<8} #{s} {'OK ' if not iss else 'BAD'} {iss} "
                  f"({time.time() - t:.0f}s) | {txt[:110].replace(chr(10), ' ')}", flush=True)
    summary.append((target, prompt_tokens, total - fails, total))
    print(f"==> target {target}: prompt≈{prompt_tokens} tok, in-character {total - fails}/{total}\n", flush=True)

print("SUMMARY")
for t, p, ok, tot in summary:
    print(f"  target={t:>6}  prompt_tokens≈{p}  in-character={ok}/{tot}")
