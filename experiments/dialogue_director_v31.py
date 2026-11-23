"""Two-character dialogue with a rule-based director, v3.1 = v3 + retell enforcement.

New vs v3:
  * Retell check at generation time: a Lao turn that shares >= 2 distinctive two-syllable phrases
    with a story already in the memory book, or >= 3 with one of his earlier turns in the same
    scene, is discarded and regenerated with a "don't retell" warning (like persona bleed).
  * Agenda done: once Lao has told the story his scene agenda asks for, the agenda is replaced
    so the prompt stops pushing the same story every turn.
  * Extraction: maxItems 4 per field, higher num_predict, repeat_penalty, one retry on bad JSON.
  * Story dedupe ignores generic phrases ("ngay xua", "hoi do"...).
Logs go to experiments/logs/director31_log_s{seed}.jsonl. Turn records add retell_raw /
retell_final / regens_retell; new record {"scene", "agenda_done", "turn"}.

--- v3 notes ---
v3 = v2 + structured memory.

New vs v2:
  * Per-character memory book: stories already told (da_ke, with count + scenes), facts known
    about the other character (biet), shared events (su_kien).
  * After each scene the model extracts those items as JSON (Ollama structured output) and the
    director merges them (dedupe by content-word overlap).
  * Every turn the speaker gets a private memory note: all told stories ("don't retell") plus
    the facts / events most relevant to the current scene.
  * Agenda/beat swap: if a scene asks Lão to tell a story he already told, the director swaps
    it for a story seed he has not told yet.
  * Theme ban skips phrases that belong to already-told stories (memory handles those).
Persona text, scenes, thresholds and seed handling are identical to v2 for a fair comparison.

Usage: python -I dialogue_director_v3.py [max_dialogue_tokens] [seed]
Logs go to experiments/logs/director3_log_s{seed}.jsonl

--- v2 notes ---
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

Usage: python -I dialogue_director_v2.py [max_dialogue_tokens] [seed]
Logs go to experiments/logs/director2_log_s{seed}.jsonl
"""
import json, os, re, sys, time, urllib.error, urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "gemma4:e4b-it-q4_K_M"
API = "http://localhost:11434/api/chat"
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
# Story seeds the director can hand Lão when a scene asks for a story he already told.
FRESH_STORIES = [
    "hồi mới cưới, lão chèo ghe sang làng bên rước dâu, giữa đường ghe mắc cạn",
    "lần lão câu được con cá mú to nhất làng, cả xóm kéo tới coi",
    "hồi nhỏ lão trốn học đi tắm biển, bị cha đánh một trận nhớ đời",
    "đêm thằng Tí chào đời, trời mưa to, lão chạy đi kêu bà mụ",
    "con chó mực tên Vện ngày xưa hay theo lão ra ghe",
    "lần ghe lão bị lạc trong sương mù suốt một đêm",
    "hồi lão dạy thằng con trai bơi ở cửa sông",
    "lần lão bán nhầm cá cho ông trưởng thôn, bị cả làng chọc mấy năm",
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


STUTTER = re.compile(r"(?<!\w)(\w+)(?:[\s,.…]+\1(?!\w)){3,}", re.I)


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
def call(msgs, num_predict=160, seed=0, fmt=None, temperature=0.8, extra=None):
    for attempt in range(4):
        body = {"model": MODEL, "messages": msgs, "stream": False, "think": False, "keep_alive": "10m",
                "options": {"num_ctx": NUM_CTX, "num_predict": num_predict, "temperature": temperature,
                            "seed": seed + attempt, **(extra or {})}}
        if attempt > 0:  # after a "token repeat limit" abort, push harder against loops
            body["options"].setdefault("repeat_penalty", 1.1 + 0.1 * attempt)
        if fmt:
            body["format"] = fmt
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
    private = memory_note(me, scene, scene_turns) + [f"(Điều chỉ bạn biết trong cảnh này: {scene[me]})"] + notes + [REMIND[me]]
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


# --- memory ------------------------------------------------------------------------
MAX_FACTS, MAX_EVENTS, MAX_TOLD_SHOWN = 15, 12, 10
memory = {me: {"da_ke": [], "biet": [], "su_kien": []} for me in ("lao", "minh")}
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "array", "items": {"type": "string"}, "maxItems": 4} for k in
                   ("lao_ke", "minh_ke", "lao_biet_ve_minh", "minh_biet_ve_lao", "su_kien")},
    "required": ["lao_ke", "minh_ke", "lao_biet_ve_minh", "minh_biet_ve_lao", "su_kien"],
}
EXTRACT_SYS = (
    "Bạn là người ghi chép truyện. Đọc một cảnh hội thoại giữa Lão Bảy và Minh rồi trả về JSON với các trường:\n"
    "- lao_ke: các CHUYỆN QUÁ KHỨ mà Lão Bảy đã kể trong cảnh (chuyện ngày xưa, kỷ niệm, người cũ). Mỗi chuyện 1 dòng ngắn dưới 15 chữ, nêu đủ ai, chuyện gì.\n"
    "- minh_ke: các chuyện về đời mình mà Minh đã kể (công việc, người yêu, gia đình...). Mỗi chuyện 1 dòng ngắn.\n"
    "- lao_biet_ve_minh: thông tin cụ thể Lão Bảy biết thêm về Minh trong cảnh này.\n"
    "- minh_biet_ve_lao: thông tin cụ thể Minh biết thêm về Lão Bảy trong cảnh này.\n"
    "- su_kien: việc hai người đã cùng làm trong cảnh (1-2 dòng).\n"
    "Chỉ ghi sự việc có trong lời thoại, không suy diễn, không ghi bài học hay cảm nghĩ. Trường nào không có thì để mảng rỗng.")


def overlap(a, b):
    """Content-word Jaccard between two short strings."""
    x, y = content_words(a), content_words(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def merge_list(items, new, cap, scene_idx):
    """Append new strings unless they near-duplicate an existing one. Returns added strings."""
    added = []
    for s in new:
        s = s.strip()
        if not s or any(overlap(s, old) >= 0.5 for old in items):
            continue
        items.append(s)
        added.append(s)
    del items[:-cap]
    return added


GENERIC = {"ngày xưa", "hồi xưa", "hồi đó", "ngày trước", "hồi trẻ", "hồi nhỏ", "năm đó", "lần đó", "ra khơi",
           "đi biển", "ra biển", "đánh cá", "cả làng", "cả xóm", "người làng", "trong làng", "biển này", "cửa biển",
           "cửa đại", "tay chân", "mắt lão", "nhớ hoài", "cả đời", "đi tàu", "con nước"}


def story_keys(t):
    """Distinctive two-syllable phrases of a text (generic time/sea phrases removed)."""
    return content_bigrams(t) - GENERIC


def same_story(a, b):
    """Same story if content words overlap enough or they share a distinctive phrase
    (e.g. "mười bốn", "hoàng sa")."""
    return overlap(a, b) >= 0.3 or bool(story_keys(a) & story_keys(b))


def retell(txt, scene_lao_turns):
    """Name of the story this Lao turn retells, or None."""
    keys = story_keys(txt)
    for st in memory["lao"]["da_ke"]:
        if len(keys & story_keys(st["tom_tat"])) >= 2:
            return st["tom_tat"]
    for prev in scene_lao_turns:
        shared = keys & story_keys(prev)
        if len(shared) >= 3:
            return "vừa kể trong cảnh này: " + ", ".join(sorted(shared)[:4])
    return None


RETELL_NOTE = ("(CẢNH BÁO: câu vừa rồi lão kể lại chuyện cũ ({story}) mà cháu đã nghe rồi. Lượt này KHÔNG nhắc lại "
               "chuyện đó: hỏi cháu một câu, hoặc nói về việc đang diễn ra trước mắt.)")
AGENDA_DONE = "Lão đã kể xong chuyện của mình trong cảnh này, giờ lão để ý tới cháu và việc đang diễn ra trước mắt."


def agenda_told(agenda, txt):
    if not re.search(r"(kể|nhớ)", agenda):
        return False
    return len(story_keys(agenda) & story_keys(txt)) >= 2 or len(content_words(agenda) & content_words(txt)) >= 4


def merge_stories(stories, new, scene_idx):
    for s in new:
        s = s.strip()
        if not s:
            continue
        hit = next((st for st in stories if same_story(s, st["tom_tat"])), None)
        if hit:
            if scene_idx not in hit["canh"]:
                hit["canh"].append(scene_idx)
                hit["so_lan"] += 1
        else:
            stories.append({"tom_tat": s, "canh": [scene_idx], "so_lan": 1})


def extract_memory(scene, scene_turns, scene_idx, seed):
    script = "\n".join(f"{'Lão Bảy' if s == 'lao' else 'Minh' if s == 'minh' else 'Dẫn truyện'}: {t}"
                       for s, t in scene_turns)
    msgs = [{"role": "system", "content": EXTRACT_SYS},
            {"role": "user", "content": f"Bối cảnh: {scene['setting']}\n\n{script}"}]
    d = None
    for k in range(2):
        txt, _, _ = call(msgs, num_predict=900, seed=seed + 50 * k, fmt=EXTRACT_SCHEMA, temperature=0.2,
                         extra={"repeat_penalty": 1.3})
        try:
            d = json.loads(txt)
            break
        except json.JSONDecodeError:
            stats["extract_retry"] += 1
    if d is None:
        stats["extract_fail"] += 1
        return {"error": txt[:300]}
    merge_stories(memory["lao"]["da_ke"], d.get("lao_ke", []), scene_idx)
    merge_stories(memory["minh"]["da_ke"], d.get("minh_ke", []), scene_idx)
    merge_list(memory["lao"]["biet"], d.get("lao_biet_ve_minh", []), MAX_FACTS, scene_idx)
    merge_list(memory["minh"]["biet"], d.get("minh_biet_ve_lao", []), MAX_FACTS, scene_idx)
    for me in ("lao", "minh"):
        merge_list(memory[me]["su_kien"], [f"(cảnh {scene_idx + 1}) {e}" for e in d.get("su_kien", [])],
                   MAX_EVENTS, scene_idx)
    return d


def relevant(items, context, k):
    """Up to k items: the ones sharing content words with context first, then the most recent."""
    ctx = content_words(context)
    scored = sorted(((len(content_words(s) & ctx), i) for i, s in enumerate(items)), reverse=True)
    pick = [i for sc, i in scored if sc > 0][:k]
    for i in range(len(items) - 1, -1, -1):
        if len(pick) >= k:
            break
        if i not in pick:
            pick.append(i)
    return [items[i] for i in sorted(pick)]


def memory_note(me, scene, scene_turns):
    m = memory[me]
    you, other = ("lão", "cháu") if me == "lao" else ("con", "ông Bảy")
    parts = []
    if m["da_ke"]:
        told = sorted(m["da_ke"], key=lambda st: st["canh"][-1])[-MAX_TOLD_SHOWN:]
        lst = "; ".join(st["tom_tat"] + (f" ({st['so_lan']} lần)" if st["so_lan"] > 1 else "") for st in told)
        parts.append(f"(Sổ nhớ - chuyện {you} đã kể cho {other} rồi, KHÔNG kể lại, nếu cần chỉ nhắc thoáng qua: {lst}.)")
    ctx = " ".join([scene["setting"], scene["goal"], scene[me]] + [t for _, t in scene_turns[-3:]])
    if m["biet"]:
        parts.append(f"(Sổ nhớ - {you} đã biết về {other}, đừng hỏi lại: {'; '.join(relevant(m['biet'], ctx, 5))}.)")
    if m["su_kien"]:
        parts.append(f"(Sổ nhớ - hai người đã cùng: {'; '.join(relevant(m['su_kien'], ctx, 3))}.)")
    return parts


def told_match(text):
    """The already-told Lão story that a scene instruction asks for, if any."""
    for st in memory["lao"]["da_ke"]:
        a, b = content_words(text), content_words(st["tom_tat"])
        if len(a & b) >= 2:
            return st
    return None


def fresh_story():
    for s in FRESH_STORIES:
        if not any(overlap(s, st["tom_tat"]) >= 0.25 for st in memory["lao"]["da_ke"]) and s not in used_fresh:
            used_fresh.add(s)
            return s
    return None


used_fresh = set()


def swap_told(scene):
    """Replace Lão's agenda / story beats that ask for an already-told story. Returns swap log."""
    swaps = []
    st = told_match(scene["lao"])
    if st and (fs := fresh_story()):
        swaps.append({"field": "lao", "old": scene["lao"], "told": st["tom_tat"], "new_story": fs})
        scene["lao"] = f"Lão kể một chuyện CHƯA từng kể cho cháu: {fs}."
    beats = list(scene["beats"])
    for i, b in enumerate(beats):
        if "kể" in b and (st := told_match(b)) and (fs := fresh_story()):
            swaps.append({"field": f"beat{i}", "old": b, "told": st["tom_tat"], "new_story": fs})
            beats[i] = f"Lão kể một chuyện chưa từng kể: {fs}."
    scene["beats"] = beats
    return swaps


def told_phrases():
    return set().union(*(content_bigrams(st["tom_tat"]) | content_words(st["tom_tat"])
                         for st in memory["lao"]["da_ke"])) if memory["lao"]["da_ke"] else set()


# --- main loop -------------------------------------------------------------------
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
log = open(os.path.join(HERE, "logs", f"director31_log_s{SEED}.jsonl"), "w", encoding="utf-8")
summaries, dialogue_tok = [], 0
history = {"lao": [], "minh": []}
stats = Counter()
t0 = time.time()
scene_idx, event_idx, call_seed = 0, 0, SEED * 100000
while dialogue_tok < MAX_DIALOGUE_TOK:
    scene = dict(SCENES[scene_idx % len(SCENES)])
    if scene_idx >= len(SCENES):
        scene["setting"] = f"(Lần về quê thứ {scene_idx // len(SCENES) + 1} của Minh, vài tháng sau) " + scene["setting"]
    swaps = swap_told(scene)
    stats["swaps"] += len(swaps)
    print(f"\n=== SCENE {scene_idx}: {scene['setting']}", flush=True)
    for s in swaps:
        print(f"   >> SWAP {s['field']}: '{s['old']}' (đã kể: {s['told']}) -> {s['new_story']}", flush=True)
    log.write(json.dumps({"scene": scene_idx, "scene_start": scene["setting"], "goal": scene["goal"],
                          "beats": scene["beats"], "agenda": {"lao": scene["lao"], "minh": scene["minh"]},
                          "swaps": swaps}, ensure_ascii=False) + "\n")
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
        told = told_phrases() if me == "lao" else set()
        bans = [p for p in overused(history[me]) if p not in told and not set(p.split()) <= told]
        if bans:
            notes.append(f"(Đạo diễn: bạn đã lặp lại mấy ý này quá nhiều: {', '.join(bans)}. Lượt này nói chuyện khác, cụ thể hơn.)")
            stats["theme_bans"] += 1
        base_notes, raw_tags, raw_retell, attempts, n_retell = list(notes), None, None, 0, 0
        lao_prev = [t for s_, t in scene_turns if s_ == "lao"]
        while True:
            call_seed += 1
            txt, ptok, etok = call(build(me, system, summaries, scene, scene_turns, notes), seed=call_seed)
            tags = lao_bleed(txt) if me == "lao" else []
            if STUTTER.search(txt):  # degenerate "nó nó nó nó": would poison every later prompt
                tags = tags + ["stutter"]
            rt = retell(txt, lao_prev) if me == "lao" else None
            if raw_tags is None:
                raw_tags, raw_retell = tags, rt
            if (not tags and not rt) or attempts >= 2:
                if tags:
                    stats["regen_failed"] += 1
                if rt:
                    stats["retell_failed"] += 1
                break
            attempts += 1
            notes = list(base_notes)
            if "stutter" in tags:
                stats["regens_stutter"] += 1
                notes.append("(Lưu ý: viết câu bình thường, không lặp đi lặp lại một chữ.)")
            if any(t != "stutter" for t in tags):
                stats["regens"] += 1
                notes.append(STRONG_REMIND)
            if rt:
                stats["regens_retell"] += 1
                n_retell += 1
                notes.append(RETELL_NOTE.format(story=rt))
        sim = similarity(txt, history[me])
        history[me].append(txt)
        scene_turns.append((me, txt))
        dialogue_tok += etok
        rec = {"scene": scene_idx, "turn": turn, "speaker": me, "beat": beat, "prompt_tokens": ptok,
               "dialogue_tokens": dialogue_tok, "raw_bleed": raw_tags, "final_bleed": tags, "regens": attempts,
               "retell_raw": raw_retell, "retell_final": rt, "regens_retell": n_retell,
               "similarity": sim, "newlines": txt.count("\n"), "director_note": base_notes,
               "memory_note": memory_note(me, scene, scene_turns[:-1]), "text": txt}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        if me == "lao" and not scene.get("_agenda_done") and agenda_told(scene["lao"], txt):
            scene["_agenda_done"] = True
            log.write(json.dumps({"scene": scene_idx, "agenda_done": scene["lao"], "turn": turn},
                                 ensure_ascii=False) + "\n")
            print(f"   >> AGENDA DONE: {scene['lao']}", flush=True)
            scene["lao"] = AGENDA_DONE
            stats["agenda_done"] += 1
        flag = "BAD" if tags else ("fix" if raw_tags else "OK ")
        if raw_retell:
            flag += f" RETELL({'ok' if not rt else 'FAIL'})"
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
    call_seed += 1
    extracted = extract_memory(scene, scene_turns, scene_idx, call_seed)
    log.write(json.dumps({"scene": scene_idx, "memory_update": extracted, "memory": memory},
                         ensure_ascii=False) + "\n")
    log.flush()
    print(f"   >> MEMORY +{extracted}", flush=True)
    print(f"      Lão đã kể: {[(st['tom_tat'], st['so_lan']) for st in memory['lao']['da_ke']]}", flush=True)
    scene_idx += 1

print(f"\ndone: {scene_idx} scenes, {dialogue_tok} dialogue tokens, {time.time() - t0:.0f}s, stats={dict(stats)}")
