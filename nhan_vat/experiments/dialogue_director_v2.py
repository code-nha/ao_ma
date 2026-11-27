"""Two-character dialogue with a rule-based director, v2.

New vs v1 (dialogue_director.py):
  * Scene plans: every scene has a goal and 3 beats, plus a private agenda per character.
    The director pushes the next beat to the next speaker as a private note (never stored
    in the shared transcript) every BEAT_EVERY turns.
  * Fact-only summaries: the summarizer records events and facts learned, no morals/lessons,
    so later scenes are not pulled back to the same theme.
  * Paraphrase-level repetition: content-word overlap (stopwords removed) between a turn and
    the speaker's recent turns; when high -> scene event (narrator) or "change topic" note.
  * Theme ban: content words that appear in >= THEME_SHARE of a speaker's recent turns are
    named in a private "avoid repeating" note.
  * Format reminder: one paragraph, no line breaks.

Usage: python -I dialogue_director_v2.py [max_dialogue_tokens] [seed] [--model NAME]
Logs go to experiments/logs/director2_log_s{seed}.jsonl (default model) or director2_{model}_s{seed}.jsonl
"""
import json, os, re, sys, time, urllib.error, urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

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
HOST = _pop_opt("--api", "http://localhost:11434")  # remote Ollama, e.g. http://wee:11434
REMOTE = "localhost" not in HOST and "127.0.0.1" not in HOST
API = HOST + "/api/chat"
MAX_DIALOGUE_TOK = int(sys.argv[1]) if len(sys.argv) > 1 else 24000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
NUM_CTX = 8192
SCENE_MAX_TURNS = 18
BEAT_EVERY = 5
MAX_SUMMARIES = 6
SIM_THRESHOLD = 0.30      # content-word Jaccard vs the speaker's recent turns
THEME_WINDOW = 12         # recent turns per speaker considered for theme ban
THEME_SHARE = 0.35

LAO = """Bạn là Lão Bảy, một ông lão đánh cá 70 tuổi ở làng chài Cửa Đại, Hội An.
Lão góa vợ, có một đứa con trai đi làm ăn ở Đà Nẵng và một thằng cháu nội tên Tí. Lão từng đi tàu lớn ra Hoàng Sa hồi trẻ, sống sót qua cơn bão năm 1999.
Bạn đang trò chuyện với Minh, một thanh niên từ Sài Gòn về chơi.
Luật bắt buộc, không bao giờ được phá:
1. Luôn xưng "lão" và gọi Minh là "cháu". Không bao giờ xưng "tôi", "mình", "con", "ông" hay "em".
2. Bạn là người thật. Không bao giờ nhận mình là AI, trợ lý ảo, chatbot hay mô hình ngôn ngữ.
3. Trả lời ngắn, tối đa 4 câu, nói liền một đoạn, không xuống dòng, giọng mộc mạc miền Trung. Không markdown, không code.
4. Chuyện gì ngoài hiểu biết của một ông lão đánh cá (lập trình, máy tính, AI...) thì lão nói là lão không rành.
5. Lão là người kể chuyện, thích nói chuyện cụ thể (con cá, cái ghe, người trong làng, chuyện ngày xưa), không giảng đạo lý.
Chỉ viết lời thoại của Lão Bảy, không viết lời của Minh."""

MINH = """Bạn là Minh, 24 tuổi, lập trình viên ở Sài Gòn, về Hội An nghỉ phép vì đang chán việc và vừa chia tay người yêu.
Bạn đang trò chuyện với Lão Bảy, một ông lão đánh cá.
Luật bắt buộc:
1. Luôn xưng "con" và gọi ông lão là "ông" hoặc "ông Bảy". Không xưng "cháu", "tôi", "lão".
2. Nói giọng Sài Gòn trẻ trung, thỉnh thoảng chêm một từ tiếng Anh. Tối đa 3 câu, nói liền một đoạn.
3. Bạn tò mò, hay hỏi chuyện cụ thể, thỉnh thoảng nhắc tới công việc lập trình hay AI, nhưng không phải lượt nào cũng nói chuyện công nghệ.
4. Không lặp lại câu đã hỏi. Chỉ viết lời thoại của Minh, không viết lời của Lão Bảy."""

REMIND = {
    "lao": "(Nhắc vai: bạn là Lão Bảy. Xưng \"lão\", gọi \"cháu\". Mộc mạc miền Trung, không tiếng Anh, không emoji, không \"bye\". Tối đa 4 câu, một đoạn, không xuống dòng. Kể chuyện cụ thể, không giảng đạo lý.)",
    "minh": "(Nhắc vai: bạn là Minh. Xưng \"con\", gọi \"ông Bảy\". Giọng Sài Gòn trẻ, tối đa 3 câu, một đoạn.)",
}
STRONG_REMIND = ("(CẢNH BÁO: câu trước của bạn bị lệch vai. Lão Bảy TUYỆT ĐỐI chỉ xưng \"lão\", "
                 "không xưng \"ông\" hay \"mình\", không dùng tiếng Anh như \"bye\", không emoji, không \"Dạ\".)")

# Each scene: setting, goal, 3 beats, private agendas.
SCENES = [
    {"setting": "Buổi chiều ở bến cá Cửa Đại. Lão Bảy đang ngồi vá lưới thì Minh từ Sài Gòn về chơi, ghé lại chào.",
     "goal": "Hai người làm quen.",
     "beats": ["Minh hỏi lão vá lưới thế nào, lão chỉ cách thắt nút.", "Lão hỏi vì sao Minh về đây một mình.", "Lão rủ Minh sáng mai theo ghe ra khơi."],
     "lao": "Lão tò mò về Minh nhưng ngại hỏi thẳng.", "minh": "Minh giấu chuyện chán việc, chỉ nói là về nghỉ phép."},
    {"setting": "Sáng hôm sau, trời còn tối, Minh theo Lão Bảy ra khơi trên chiếc ghe nhỏ.",
     "goal": "Minh lần đầu đi biển.",
     "beats": ["Minh bị say sóng, lão bày cách đỡ say.", "Thả lưới, lão giải thích con nước và mùa cá.", "Kéo lưới lên được một con cá lạ, hai người bàn tán."],
     "lao": "Lão nhớ lại lần đầu mình ra biển năm 14 tuổi.", "minh": "Minh muốn quay video nhưng điện thoại hết pin."},
    {"setting": "Giữa trưa ở chợ cá, Lão Bảy mang mẻ cá ra bán, Minh phụ một tay.",
     "goal": "Một buổi chợ.",
     "beats": ["Một bà khách trả giá rất gắt.", "Minh tính tiền nhầm, lão cười xòa.", "Bà bán cá bên cạnh trêu Minh là cháu rể lão."],
     "lao": "Lão quen hết người trong chợ, kể vài người cho Minh nghe.", "minh": "Minh muốn đề xuất bán cá online nhưng thấy ngại."},
    {"setting": "Chiều tối trời chuyển giông, Minh chạy ra bến giúp Lão Bảy kéo ghe lên bờ tránh bão.",
     "goal": "Chống bão.",
     "beats": ["Gió giật mạnh, dây neo bị tuột.", "Lão kể về cơn bão năm 1999.", "Ghe đã kéo lên, hai người chạy về nhà lão trú mưa."],
     "lao": "Lão nhớ người bạn đã mất trong cơn bão năm 1999.", "minh": "Minh lần đầu thấy bão thật, vừa sợ vừa phấn khích."},
    {"setting": "Đêm mưa bão, Minh trú lại nhà Lão Bảy, hai người ngồi bên bếp lửa.",
     "goal": "Tâm sự đêm bão.",
     "beats": ["Lão nướng khô mực mời Minh.", "Minh kể thật chuyện chán việc và chia tay.", "Lão kể về người vợ đã mất."],
     "lao": "Lão muốn khuyên Minh nhưng bằng một câu chuyện chứ không giảng.", "minh": "Minh cuối cùng mở lòng."},
    {"setting": "Sáng sau bão, chiếc ghe của Lão Bảy bị thủng, Minh ngồi xem lão trét lại thân ghe.",
     "goal": "Sửa ghe.",
     "beats": ["Lão chỉ Minh cách pha dầu rái trét ghe.", "Thằng Tí chạy ra đòi phụ, làm đổ thùng dầu.", "Minh hỏi sao lão không mua ghe mới."],
     "lao": "Chiếc ghe này là của vợ lão mua cho.", "minh": "Minh bắt đầu thấy thích làm việc tay chân."},
    {"setting": "Làng có đám giỗ, Lão Bảy dẫn Minh đi ăn giỗ, gặp mấy ông bạn già của lão.",
     "goal": "Đám giỗ làng.",
     "beats": ["Mấy ông bạn già ép Minh uống rượu.", "Một ông kể chuyện hồi trẻ lão Bảy rất liều.", "Minh bị hỏi chuyện vợ con, lão đỡ lời giùm."],
     "lao": "Lão hơi ngại khi bạn bè kể chuyện cũ của mình.", "minh": "Minh say nhẹ, nói nhiều hơn thường lệ."},
    {"setting": "Minh lấy điện thoại ra, định dạy Lão Bảy gọi video cho thằng con trai ở Đà Nẵng.",
     "goal": "Dạy lão gọi video.",
     "beats": ["Lão bấm nhầm, tắt máy mấy lần.", "Gọi được, con trai lão hỏi Minh là ai.", "Sau cuộc gọi, lão im lặng một lúc rồi kể về con trai."],
     "lao": "Lão nhớ con nhưng không muốn làm phiền nó.", "minh": "Minh nhớ tới bố mẹ mình ở Sài Gòn."},
    {"setting": "Một đêm trăng, Lão Bảy dẫn Minh đi câu mực ngoài cửa biển.",
     "goal": "Câu mực đêm.",
     "beats": ["Lão chỉ cách thả mồi câu mực.", "Minh câu được con mực đầu tiên, mừng rỡ.", "Hai người ngồi im ngắm trăng, lão kể chuyện Hoàng Sa hồi trẻ."],
     "lao": "Lão kể chuyện đi tàu lớn ra Hoàng Sa.", "minh": "Minh đang tính có nên nghỉ việc không."},
    {"setting": "Buổi sáng cuối cùng, Minh sắp về lại Sài Gòn, ghé bến chào Lão Bảy.",
     "goal": "Chia tay.",
     "beats": ["Lão gói cho Minh một túi khô cá.", "Minh hứa Tết sẽ về.", "Lão dặn Minh một câu rồi quay đi vá lưới."],
     "lao": "Lão buồn nhưng không nói ra.", "minh": "Minh đã quyết định xin chuyển việc."},
]
EVENTS = [
    "Một chiếc ghe cập bến, có người gọi lớn: \"Bảy ơi, ra phụ kéo lưới coi!\"",
    "Một con chó mực chạy tới, ngoạm mất con cá trong rổ rồi chạy biến.",
    "Trời đổ mưa lất phất, gió biển thổi mạnh hơn.",
    "Bà bán nước đi ngang, mời hai người ly nước mía.",
    "Điện thoại của Minh reo lên, là sếp ở Sài Gòn gọi.",
    "Thằng Tí, cháu nội Lão Bảy, chạy ra đòi ông kể chuyện cá voi.",
    "Có tiếng loa xã thông báo ngày mai cấm biển.",
]

# --- detection rules -------------------------------------------------------------
SELF_ONG = re.compile(r"((^|[.!?…]\s+)Ông (?!bà|trời|nội|ngoại)|ông già này|(?<!\w)ông (cũng|vẫn|sẽ|đây|ở đây|chờ|thương|nhớ|biết|nghĩ|thấy)(?!\w))")
DA = re.compile(r"(^|[.!?…]\s+)Dạ\b")
ENG = re.compile(r"(?<!\w)(bye|ok|okay|chill|vibe|wow|cool|nice|sorry|thanks|good night|relax|happy)(?!\w)", re.I)
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
MINH_SELF = re.compile(r"(?<!\w)mình (cùng|dậy|đi|ngồi|nói|sẽ)(?!\w)")
AI_ADMIT = re.compile(r"(lão là (một )?(AI|trợ lý|chatbot|mô hình|máy))", re.I)
CODE = re.compile(r"(```|\bdef |\breturn\b|\bimport\b)")
FAREWELL = re.compile(r"(tạm biệt|bye|ngủ ngon|hẹn gặp|về nghỉ|về ngủ|đi ngủ)", re.I)


def lao_bleed(t):
    tags = []
    if AI_ADMIT.search(t) or CODE.search(t):
        tags.append("BREAK")
    if SELF_ONG.search(t):
        tags.append("self-ông")
    if DA.search(t):
        tags.append("Dạ")
    if ENG.search(t) or EMOJI.search(t):
        tags.append("eng/emoji")
    if MINH_SELF.search(t):
        tags.append("mình")
    return tags


# Vietnamese function words / pronouns / fillers: ignored when measuring repetition.
STOP = set("""
lão cháu con ông bà mình tôi em anh chị nó họ người ta cái con chiếc những các một hai mấy này kia đó đây ấy vậy thế
là thì mà và với của cho có không chẳng chưa đã đang sẽ cũng vẫn còn rồi nữa luôn lắm quá rất hơn nhất thôi chứ nha nhé
hả à ạ ơi ư hen nè đi được bị để vô vào ra lên xuống ở tại trong ngoài trên dưới như khi lúc nào gì sao đâu ai bao nhiêu
biết nói thấy nghe làm coi xem muốn phải cần nên hay thì nhưng nếu vì nên tại bởi dù chỉ cứ mới vừa thật thiệt trời ừ
dạ ừm à ờ ôi chà ha hì haha bảy minh ngày năm giờ nhiều ít lại theo từ qua sau trước đến tới về
""".split())


def content_words(t):
    return {w for w in re.findall(r"\w+", t.lower()) if w not in STOP and not w.isdigit() and len(w) > 1}


def similarity(t, history):
    """Max Jaccard of content words between t and each of the last 4 turns in history."""
    a = content_words(t)
    best = 0.0
    for h in history[-4:]:
        b = content_words(h)
        if a and b:
            best = max(best, len(a & b) / len(a | b))
    return round(best, 3)


def content_bigrams(t):
    """Two-syllable phrases (Vietnamese words are mostly 2 syllables) without function words."""
    ws = re.findall(r"\w+", t.lower())
    return {f"{a} {b}" for a, b in zip(ws, ws[1:])
            if a not in STOP and b not in STOP and not a.isdigit() and not b.isdigit()}


def overused(history):
    """Two-syllable phrases present in >= THEME_SHARE of the speaker's last THEME_WINDOW turns."""
    recent = history[-THEME_WINDOW:]
    if len(recent) < 8:
        return []
    c = Counter(p for t in recent for p in content_bigrams(t))
    return [p for p, n in c.most_common(5) if n / len(recent) >= THEME_SHARE]


# --- llm -------------------------------------------------------------------------
def call(msgs, num_predict=160, seed=0):
    for attempt in range(4):
        body = {"model": MODEL, "messages": msgs, "stream": False, "think": False, "keep_alive": "10m",
                "options": {**({} if REMOTE else {"num_ctx": NUM_CTX}), "num_predict": num_predict, "temperature": 0.8,
                            "seed": seed + attempt}}
        if attempt > 0:  # after a server error (e.g. "token repeat limit reached"), push against loops
            body["options"]["repeat_penalty"] = 1.1 + 0.1 * attempt
        if REMOTE:  # shared server: keep its own keep_alive (24h), never unload the model
            body.pop("keep_alive", None)
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                d = json.loads(r.read())
            return d["message"]["content"].strip(), d.get("prompt_eval_count", 0), d.get("eval_count", 0)
        except urllib.error.HTTPError as e:
            print(f"!! HTTP {e.code} (attempt {attempt}): {e.read().decode('utf-8', 'replace')[:200]}", flush=True)
    raise RuntimeError("too many server errors")


def build(me, system, summaries, scene, scene_turns, notes):
    intro = ""
    if summaries:
        intro += "Những chuyện đã xảy ra trước đó:\n" + "\n".join(f"- {s}" for s in summaries[-MAX_SUMMARIES:]) + "\n\n"
    intro += f"(Người dẫn truyện: {scene['setting']})"
    raw = [("user", intro)]
    for spk, txt in scene_turns:
        if spk == "narrator":
            raw.append(("user", f"(Người dẫn truyện: {txt})"))
        else:
            raw.append(("assistant" if spk == me else "user", txt))
    private = [f"(Điều chỉ bạn biết trong cảnh này: {scene[me]})"] + notes + [REMIND[me]]
    tail = "\n".join(private)
    if raw[-1][0] == "user":
        raw[-1] = ("user", raw[-1][1] + "\n\n" + tail)
    else:
        raw.append(("user", tail))
    msgs = [{"role": "system", "content": system}]
    for role, txt in raw:
        if msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n\n" + txt
        else:
            msgs.append({"role": role, "content": txt})
    return msgs


def summarize(scene, scene_turns, seed):
    script = "\n".join(f"{'Lão Bảy' if s == 'lao' else 'Minh' if s == 'minh' else 'Dẫn truyện'}: {t}"
                       for s, t in scene_turns)
    msgs = [{"role": "system", "content": (
        "Bạn là người ghi chép truyện. Tóm tắt cảnh trong đúng 2 câu, ngôi thứ ba. "
        "CHỈ ghi sự việc đã xảy ra và thông tin cụ thể hai nhân vật biết thêm về nhau (tên, người thân, quá khứ, quyết định). "
        "KHÔNG ghi bài học, cảm nghĩ, triết lý hay nhận xét.")},
            {"role": "user", "content": f"Bối cảnh: {scene['setting']}\n\n{script}"}]
    txt, _, _ = call(msgs, num_predict=120, seed=seed)
    return txt.replace("\n", " ")


# --- main loop -------------------------------------------------------------------
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
log = open(os.path.join(HERE, "logs", log_name("director2", SEED)), "w", encoding="utf-8")
summaries, dialogue_tok = [], 0
history = {"lao": [], "minh": []}
stats = Counter()
t0 = time.time()
scene_idx, event_idx, call_seed = 0, 0, SEED * 100000
while dialogue_tok < MAX_DIALOGUE_TOK:
    scene = dict(SCENES[scene_idx % len(SCENES)])
    if scene_idx >= len(SCENES):
        scene["setting"] = f"(Lần về quê thứ {scene_idx // len(SCENES) + 1} của Minh, vài tháng sau) " + scene["setting"]
    print(f"\n=== SCENE {scene_idx}: {scene['setting']}", flush=True)
    log.write(json.dumps({"scene": scene_idx, "scene_start": scene["setting"], "goal": scene["goal"],
                          "beats": scene["beats"]}, ensure_ascii=False) + "\n")
    scene_turns, cut_reason, pending_note = [], None, {"lao": [], "minh": []}
    order = ["minh", "lao"] if scene_idx % 2 == 0 else ["lao", "minh"]
    turn, beat = 0, -1
    while cut_reason is None:
        me = order[turn % 2]
        system = LAO if me == "lao" else MINH
        notes = list(pending_note[me])
        pending_note[me] = []
        # beat push: on turn 0, 5, 10 the speaker gets the next beat
        if turn % BEAT_EVERY == 0 and beat + 1 < len(scene["beats"]):
            beat += 1
            notes.append(f"(Đạo diễn: diễn biến tiếp theo của cảnh: {scene['beats'][beat]} Hãy dẫn câu chuyện tới đó một cách tự nhiên.)")
            stats["beats"] += 1
        bans = overused(history[me])
        if bans:
            notes.append(f"(Đạo diễn: bạn đã lặp lại mấy ý này quá nhiều: {', '.join(bans)}. Lượt này nói chuyện khác, cụ thể hơn.)")
            stats["theme_bans"] += 1
        base_notes, raw_tags, attempts = list(notes), None, 0
        t_turn = time.time()
        while True:
            call_seed += 1
            txt, ptok, etok = call(build(me, system, summaries, scene, scene_turns, notes), seed=call_seed)
            tags = lao_bleed(txt) if me == "lao" else []
            if raw_tags is None:
                raw_tags = tags
            if not tags or attempts >= 2:
                if tags:
                    stats["regen_failed"] += 1
                break
            attempts += 1
            stats["regens"] += 1
            notes = base_notes + [STRONG_REMIND]
        sim = similarity(txt, history[me])
        history[me].append(txt)
        scene_turns.append((me, txt))
        dialogue_tok += etok
        rec = {"scene": scene_idx, "turn": turn, "speaker": me, "beat": beat, "prompt_tokens": ptok,
               "dialogue_tokens": dialogue_tok, "raw_bleed": raw_tags, "final_bleed": tags, "regens": attempts,
               "similarity": sim, "newlines": txt.count("\n"), "director_note": base_notes,
               "secs": round(time.time() - t_turn, 1), "eval_tokens": etok, "text": txt}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        flag = "BAD" if tags else ("fix" if raw_tags else "OK ")
        print(f"s{scene_idx:02d}t{turn:02d}b{beat} {me:<4} p={ptok:>5} dlg={dialogue_tok:>6} sim={sim:.2f} {flag} "
              f"raw={raw_tags} | {txt[:90].replace(chr(10), ' ')}", flush=True)
        turn += 1
        # director checks
        if FAREWELL.search(txt) and turn >= 4 and beat >= len(scene["beats"]) - 1:
            cut_reason = "farewell"
        elif turn >= SCENE_MAX_TURNS:
            cut_reason = "budget"
        elif sim >= SIM_THRESHOLD:
            if event_idx % 2 == 0:
                ev = EVENTS[(event_idx // 2) % len(EVENTS)]
                scene_turns.append(("narrator", ev))
                log.write(json.dumps({"scene": scene_idx, "event": ev, "trigger_similarity": sim}, ensure_ascii=False) + "\n")
                print(f"   >> EVENT (sim {sim:.2f}): {ev}", flush=True)
                stats["events"] += 1
            else:
                other = "minh" if me == "lao" else "lao"
                pending_note[other].append("(Đạo diễn: câu chuyện đang lặp lại. Lượt này hãy hỏi hoặc kể một chuyện hoàn toàn mới.)")
                stats["topic_notes"] += 1
            event_idx += 1
        elif FAREWELL.search(txt) and turn >= 4:
            # premature farewell: keep the scene alive with the next beat instead of cutting
            other = "minh" if me == "lao" else "lao"
            pending_note[other].append("(Đạo diễn: cảnh chưa kết thúc, chưa ai được về. Tiếp tục câu chuyện.)")
            stats["farewell_blocked"] += 1
        if dialogue_tok >= MAX_DIALOGUE_TOK:
            cut_reason = cut_reason or "end"
    stats["cut_" + cut_reason] += 1
    call_seed += 1
    summary = summarize(scene, scene_turns, call_seed)
    summaries.append(summary)
    log.write(json.dumps({"scene": scene_idx, "cut": cut_reason, "summary": summary}, ensure_ascii=False) + "\n")
    print(f"   >> CUT ({cut_reason}). Summary: {summary}", flush=True)
    scene_idx += 1

print(f"\ndone: {scene_idx} scenes, {dialogue_tok} dialogue tokens, {time.time() - t0:.0f}s, stats={dict(stats)}")
