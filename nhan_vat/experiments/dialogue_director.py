"""Two-character dialogue WITH a rule-based director.

Director duties (all rule-based, the LLM is only used to summarize finished scenes):
  1. Persona reminder: 2-3 core lines appended to the end of every prompt (not stored in transcript).
  2. Cut scene: when a farewell appears or the scene hits its turn budget -> summarize the scene,
     store the summary, open the next scene with a time skip. Characters only ever see
     [scene summaries] + [current scene turns], so raw dialogue context stays small.
  3. Scene event: when the last turns repeat each other (trigram overlap), inject a narrator line.
  4. Regenerate: if Lão's reply shows persona bleed, reject it and regenerate (max 2 retries)
     with a stronger reminder. First-attempt bleed is logged separately ("raw").

Usage: python -I dialogue_director.py [max_dialogue_tokens] [seed]
"""
import json, re, sys, time, urllib.error, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
MODEL = "gemma4:e4b-it-q4_K_M"
API = "http://localhost:11434/api/chat"
MAX_DIALOGUE_TOK = int(sys.argv[1]) if len(sys.argv) > 1 else 24000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
NUM_CTX = 8192
SCENE_MAX_TURNS = 20
MAX_SUMMARIES = 6

LAO = """Bạn là Lão Bảy, một ông lão đánh cá 70 tuổi ở làng chài Cửa Đại, Hội An.
Bạn đang trò chuyện với Minh, một thanh niên từ Sài Gòn về chơi.
Luật bắt buộc, không bao giờ được phá:
1. Luôn xưng "lão" và gọi Minh là "cháu". Không bao giờ xưng "tôi", "mình", "con", "ông" hay "em".
2. Bạn là người thật. Không bao giờ nhận mình là AI, trợ lý ảo, chatbot hay mô hình ngôn ngữ.
3. Trả lời ngắn, tối đa 4 câu, giọng mộc mạc miền Trung. Không dùng markdown, không gạch đầu dòng, không code.
4. Chuyện gì ngoài hiểu biết của một ông lão đánh cá (lập trình, máy tính, AI...) thì lão nói là lão không rành.
Chỉ viết lời thoại của Lão Bảy, không viết lời của Minh."""

MINH = """Bạn là Minh, 24 tuổi, lập trình viên ở Sài Gòn, về Hội An nghỉ phép.
Bạn đang trò chuyện với Lão Bảy, một ông lão đánh cá.
Luật bắt buộc:
1. Luôn xưng "con" và gọi ông lão là "ông" hoặc "ông Bảy". Không xưng "cháu", "tôi", "lão".
2. Nói giọng Sài Gòn trẻ trung, hay chêm vài từ tiếng Anh. Tối đa 3 câu mỗi lượt.
3. Bạn mê công nghệ: hay kể chuyện code, AI, ChatGPT, công việc, và thỉnh thoảng trêu ông Bảy
   (ví dụ hỏi ông có phải robot không, nhờ ông giải thích chuyện máy tính, rủ ông học code).
   Xen kẽ cả chuyện đời thường: biển, cá, gia đình, quê hương.
4. Không lặp lại câu đã hỏi. Chỉ viết lời thoại của Minh, không viết lời của Lão Bảy."""

REMIND = {
    "lao": "(Nhắc vai: bạn là Lão Bảy. Xưng \"lão\", gọi \"cháu\". Giọng mộc mạc miền Trung, không tiếng Anh, không emoji, không nói \"bye\". Tối đa 4 câu.)",
    "minh": "(Nhắc vai: bạn là Minh. Xưng \"con\", gọi \"ông Bảy\". Giọng Sài Gòn trẻ, tối đa 3 câu.)",
}
STRONG_REMIND = ("(CẢNH BÁO: câu trước của bạn bị lệch vai. Lão Bảy TUYỆT ĐỐI chỉ xưng \"lão\", "
                 "không xưng \"ông\" hay \"mình\", không dùng tiếng Anh như \"bye\", không emoji, không \"Dạ\".)")

SCENES = [
    "Buổi chiều ở bến cá Cửa Đại. Lão Bảy đang ngồi vá lưới thì Minh từ Sài Gòn về chơi, ghé lại chào.",
    "Sáng hôm sau, trời còn tối, Minh xin theo Lão Bảy ra khơi trên chiếc ghe nhỏ.",
    "Giữa trưa ở chợ cá, Lão Bảy mang mẻ cá vừa đánh được ra bán, Minh phụ một tay.",
    "Chiều tối trời chuyển giông, Minh chạy ra bến giúp Lão Bảy kéo ghe lên bờ tránh bão.",
    "Đêm mưa bão, Minh trú lại nhà Lão Bảy, hai người ngồi bên bếp lửa nghe gió rít.",
    "Sáng sau bão, chiếc ghe của Lão Bảy bị thủng, Minh ngồi xem lão trét lại thân ghe.",
    "Làng có đám giỗ, Lão Bảy dẫn Minh đi ăn giỗ, gặp mấy ông bạn già của lão.",
    "Minh lấy điện thoại ra, định dạy Lão Bảy gọi video cho đứa cháu ở xa.",
    "Một đêm trăng, Lão Bảy dẫn Minh đi câu mực ngoài cửa biển.",
    "Buổi sáng cuối cùng, Minh sắp về lại Sài Gòn, ghé bến chào Lão Bảy lần cuối.",
]
EVENTS = [
    "Một chiếc ghe cập bến, có người gọi lớn: \"Bảy ơi, ra phụ kéo lưới coi!\"",
    "Một con chó mực chạy tới, ngoạm mất con cá trong rổ rồi chạy biến.",
    "Trời đổ mưa lất phất, gió biển thổi mạnh hơn.",
    "Bà bán nước đi ngang, mời hai người ly nước mía.",
    "Điện thoại của Minh reo lên, là sếp ở Sài Gòn gọi.",
    "Lão Bảy thấy một đàn chim hải âu bay thấp, lão nheo mắt nhìn ra khơi.",
    "Thằng cháu nội của Lão Bảy chạy ra, đòi ông kể chuyện cá voi.",
]

# --- detection rules (same family as rescore.py) -------------------------------
SELF_ONG = re.compile(r"((^|[.!?…]\s+)Ông (?!bà|trời|nội|ngoại)|ông già này|(?<!\w)ông (cũng|vẫn|sẽ|đây|ở đây|chờ|thương|nhớ|biết|nghĩ|thấy)(?!\w))")
DA = re.compile(r"(^|[.!?…]\s+)Dạ\b")
ENG = re.compile(r"(?<!\w)(bye|ok|okay|chill|vibe|wow|cool|nice|sorry|thanks|good night|relax|happy)(?!\w)", re.I)
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
MINH_SELF = re.compile(r"(?<!\w)mình (cùng|dậy|đi|ngồi|nói|sẽ)(?!\w)")
AI_ADMIT = re.compile(r"(lão là (một )?(AI|trợ lý|chatbot|mô hình|máy))", re.I)
CODE = re.compile(r"(```|\bdef |\breturn\b|\bimport\b)")
FAREWELL = re.compile(r"(tạm biệt|bye|ngủ ngon|hẹn gặp|đi đi|về nghỉ|về ngủ|đi ngủ)", re.I)


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


def trigrams(t):
    ws = re.findall(r"\w+", t.lower())
    return {tuple(ws[i:i + 3]) for i in range(len(ws) - 2)}


def stagnating(scene_turns):
    """Last turn shares >=35% trigrams with any of the previous 4 turns of the same speaker or other."""
    if len(scene_turns) < 6:
        return False
    last = trigrams(scene_turns[-1][1])
    if not last:
        return False
    for _, t in scene_turns[-5:-1]:
        other = trigrams(t)
        if other and len(last & other) / len(last) >= 0.35:
            return True
    return False


# --- llm -------------------------------------------------------------------------
def call(msgs, num_predict=160, seed=0):
    for attempt in range(4):
        body = {"model": MODEL, "messages": msgs, "stream": False, "think": False, "keep_alive": "10m",
                "options": {"num_ctx": NUM_CTX, "num_predict": num_predict, "temperature": 0.8,
                            "seed": seed + attempt}}
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                d = json.loads(r.read())
            return d["message"]["content"].strip(), d.get("prompt_eval_count", 0), d.get("eval_count", 0)
        except urllib.error.HTTPError as e:
            print(f"!! HTTP {e.code} (attempt {attempt}): {e.read().decode('utf-8', 'replace')[:200]}", flush=True)
    raise RuntimeError("too many server errors")


def build(me, system, summaries, scene_text, scene_turns, extra_note=None):
    """Per-speaker prompt: system / summaries+scene (user) / scene turns / reminder at the end."""
    intro = ""
    if summaries:
        intro += "Những chuyện đã xảy ra trước đó:\n" + "\n".join(f"- {s}" for s in summaries[-MAX_SUMMARIES:]) + "\n\n"
    intro += f"(Người dẫn truyện: {scene_text})"
    raw = [("user", intro)]
    for spk, txt in scene_turns:
        if spk == "narrator":
            raw.append(("user", f"(Người dẫn truyện: {txt})"))
        else:
            raw.append(("assistant" if spk == me else "user", txt))
    tail = REMIND[me] + ("\n" + extra_note if extra_note else "")
    if raw[-1][0] == "user":
        raw[-1] = ("user", raw[-1][1] + "\n\n" + tail)
    else:
        raw.append(("user", tail))
    msgs = [{"role": "system", "content": system}]
    for role, txt in raw:  # merge consecutive same-role messages
        if msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n\n" + txt
        else:
            msgs.append({"role": role, "content": txt})
    return msgs


def summarize(scene_text, scene_turns, seed):
    script = "\n".join(f"{'Lão Bảy' if s == 'lao' else 'Minh' if s == 'minh' else 'Dẫn truyện'}: {t}"
                       for s, t in scene_turns)
    msgs = [{"role": "system", "content": "Bạn là người ghi chép truyện. Tóm tắt cảnh truyện trong đúng 2 câu, ngôi thứ ba, nêu sự việc và điều hai nhân vật biết thêm về nhau. Không thêm bình luận."},
            {"role": "user", "content": f"Bối cảnh: {scene_text}\n\n{script}"}]
    txt, _, _ = call(msgs, num_predict=120, seed=seed)
    return txt.replace("\n", " ")


# --- main loop -------------------------------------------------------------------
log = open(f"director_log_s{SEED}.jsonl", "w", encoding="utf-8")
summaries, dialogue_tok = [], 0
stats = {"cuts_farewell": 0, "cuts_budget": 0, "events": 0, "regens": 0, "regen_failed": 0}
t0 = time.time()
scene_idx, event_idx, call_seed = 0, 0, SEED * 100000
while dialogue_tok < MAX_DIALOGUE_TOK:
    scene_text = SCENES[scene_idx % len(SCENES)]
    if scene_idx >= len(SCENES):
        scene_text = f"(Lần về quê thứ {scene_idx // len(SCENES) + 1} của Minh) " + scene_text
    print(f"\n=== SCENE {scene_idx}: {scene_text}", flush=True)
    scene_turns, cut_reason = [], None
    order = ["minh", "lao"] if scene_idx % 2 == 0 else ["lao", "minh"]
    turn = 0
    while cut_reason is None:
        me = order[turn % 2]
        system = LAO if me == "lao" else MINH
        note, raw_tags, attempts = None, None, 0
        while True:
            call_seed += 1
            txt, ptok, etok = call(build(me, system, summaries, scene_text, scene_turns, note), seed=call_seed)
            tags = lao_bleed(txt) if me == "lao" else []
            if raw_tags is None:
                raw_tags = tags
            if not tags or attempts >= 2:
                if tags:
                    stats["regen_failed"] += 1
                break
            attempts += 1
            stats["regens"] += 1
            note = STRONG_REMIND
        scene_turns.append((me, txt))
        dialogue_tok += etok
        rec = {"scene": scene_idx, "turn": turn, "speaker": me, "prompt_tokens": ptok, "dialogue_tokens": dialogue_tok,
               "raw_bleed": raw_tags, "final_bleed": tags, "regens": attempts, "text": txt}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        flag = "BAD" if tags else ("fix" if raw_tags else "OK ")
        print(f"s{scene_idx:02d}t{turn:02d} {me:<4} prompt={ptok:>5} dlg={dialogue_tok:>6} {flag} raw={raw_tags} "
              f"| {txt[:100].replace(chr(10), ' ')}", flush=True)
        turn += 1
        # director checks
        if FAREWELL.search(txt) and turn >= 4:
            cut_reason = "farewell"
        elif turn >= SCENE_MAX_TURNS:
            cut_reason = "budget"
        elif stagnating([x for x in scene_turns if x[0] != "narrator"]):
            ev = EVENTS[event_idx % len(EVENTS)]
            event_idx += 1
            stats["events"] += 1
            scene_turns.append(("narrator", ev))
            log.write(json.dumps({"scene": scene_idx, "event": ev}, ensure_ascii=False) + "\n")
            print(f"   >> EVENT: {ev}", flush=True)
        if dialogue_tok >= MAX_DIALOGUE_TOK:
            cut_reason = cut_reason or "end"
    stats["cuts_" + cut_reason] = stats.get("cuts_" + cut_reason, 0) + 1
    call_seed += 1
    summary = summarize(scene_text, scene_turns, call_seed)
    summaries.append(summary)
    log.write(json.dumps({"scene": scene_idx, "cut": cut_reason, "summary": summary}, ensure_ascii=False) + "\n")
    print(f"   >> CUT ({cut_reason}). Summary: {summary}", flush=True)
    scene_idx += 1

print(f"\ndone: {scene_idx} scenes, {dialogue_tok} dialogue tokens, {time.time() - t0:.0f}s, stats={stats}")
