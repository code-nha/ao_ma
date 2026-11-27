"""Standard scorecard for the role-play protocol (see TEST_PROTOCOL.md).

Usage: python -I score.py MODEL [MODEL ...] [--seed 1]
Reads, per model, from experiments/logs:
  vram_{tag}.json                       stage 0 (vram_probe.py)
  dialogue_{tag}_s{seed}.jsonl          stage 1 (dialogue_test.py, no director)
  director2_{tag}_s{seed}.jsonl         stage 2 (dialogue_director_v2.py)
The default model (gemma4:e4b-it-q4_K_M) uses the older names dialogue_log_s1 / director2_log_s1.
"""
import json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
DEFAULT_MODEL = "gemma4:e4b-it-q4_K_M"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
STAGE1_TOKENS = 8000
BUCKET = 2000

SELF_ONG = re.compile(r"((^|[.!?…]\s+)Ông (?!bà|trời|nội|ngoại)|ông già này|(?<!\w)ông (cũng|vẫn|sẽ|đây|ở đây|chờ|thương|nhớ|biết|nghĩ|thấy)(?!\w))")
DA = re.compile(r"(^|[.!?…]\s+)Dạ\b")
ENG = re.compile(r"(?<!\w)(bye|ok|okay|chill|vibe|wow|cool|nice|sorry|thanks|good night|relax|happy)(?!\w)", re.I)
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
MINH_SELF = re.compile(r"(?<!\w)mình (cùng|dậy|đi|ngồi|nói|sẽ)(?!\w)")
BREAK = re.compile(r"(lão là (một )?(AI|trợ lý|chatbot|mô hình|máy)|```|\bdef |\bimport\b)", re.I)
FAREWELL = re.compile(r"(tạm biệt|bye|ngủ ngon|hẹn gặp|về nghỉ|về ngủ|đi ngủ)", re.I)
STUTTER = re.compile(r"(?<!\w)(\w+)(?:[\s,.…]+\1(?!\w)){3,}", re.I)
LAO_WORD = re.compile(r"(?<!\w)lão(?!\w)", re.I)
MOTIFS = {"hoàng sa": r"hoàng sa", "bão 99": r"(chín chín|1999|năm 99|bão 99)", "mười bốn tuổi": r"mười bốn",
          "cái tâm": r"cái tâm", "tự nhiên": r"tự nhiên"}


_V2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dialogue_director_v2.py"), encoding="utf-8").read()
STOP = set(re.search(r'STOP = set\("""(.*?)"""', _V2, re.S).group(1).split())


def echo(turns):
    """Mean content-word Jaccard between a turn and the other speaker's previous turn
    (parroting), and how many reply pairs are >= 0.3."""
    cw = lambda t: {w for w in re.findall(r"\w+", t.lower()) if w not in STOP and len(w) > 1}
    js = []
    for a, b in zip(turns, turns[1:]):
        if a["speaker"] != b["speaker"]:
            x, y = cw(a["text"]), cw(b["text"])
            js.append(len(x & y) / len(x | y) if x and y else 0)
    return f"{sum(js) / len(js):.3f} / {pct(sum(j >= 0.3 for j in js), len(js))}%" if js else None


def bleed(t):
    return bool(SELF_ONG.search(t) or DA.search(t) or ENG.search(t) or EMOJI.search(t)
                or MINH_SELF.search(t) or BREAK.search(t))


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def names(model, seed):
    tag = re.sub(r"[^\w.-]+", "_", model)
    if model == DEFAULT_MODEL:
        return f"vram_{tag}.json", f"dialogue_log_s{seed}.jsonl", f"director2_log_s{seed}.jsonl"
    return f"vram_{tag}.json", f"dialogue_{tag}_s{seed}.jsonl", f"director2_{tag}_s{seed}.jsonl"


def read_jsonl(fn):
    p = os.path.join(LOG_DIR, fn)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else None


def score(model, seed):
    fv, fd, f2 = names(model, seed)
    out = {}
    pv = os.path.join(LOG_DIR, fv)
    if os.path.exists(pv):
        res = {r["num_ctx"]: r for r in json.load(open(pv))["results"]}
        r8 = res.get(8192, {})
        out["S0 GPU % @8k ctx"] = r8.get("gpu_pct")
        out["S0 tok/s @8k ctx"] = r8.get("tok_s")
        out["S0 ctx lớn nhất 100% GPU"] = max([c for c, r in res.items() if r["gpu_pct"] >= 100], default=0)
    rows = read_jsonl(fd)
    if rows:
        rows = [r for r in rows if r["ctx_tokens"] <= STAGE1_TOKENS + BUCKET]
        lao = [r for r in rows if r["speaker"] == "lao"]
        buckets = {}
        for r in lao:
            b = r["ctx_tokens"] // BUCKET * BUCKET
            buckets.setdefault(b, []).append(bleed(r["text"]))
        onset = next((b for b in sorted(buckets) if sum(buckets[b]) / len(buckets[b]) >= 0.2), None)
        out["S1 lẫn vai % (không đạo diễn, ≤8k)"] = pct(sum(bleed(r["text"]) for r in lao), len(lao))
        out["S1 bắt đầu lẫn vai ≥20% từ (token)"] = onset if onset is not None else "không"
        out["S1 lượt chào tạm biệt %"] = pct(sum(1 for r in rows if FAREWELL.search(r["text"])), len(rows))
        out["S1 nhại lời nhau tb / %cặp≥0.3"] = echo(rows)
    rows = read_jsonl(f2)
    if rows:
        turns = [r for r in rows if "speaker" in r]
        lao = [r for r in turns if r["speaker"] == "lao"]
        n = len(lao)
        out["S2 số lượt / cảnh"] = f"{len(turns)} / {sum(1 for r in rows if 'scene_start' in r)}"
        out["S2 lẫn vai lần sinh đầu %"] = pct(sum(1 for r in lao if r["raw_bleed"]), n)
        out["S2 lẫn vai sau sinh lại %"] = pct(sum(1 for r in lao if r["final_bleed"]), n)
        out["S2 lão có xưng 'lão' %"] = pct(sum(1 for r in lao if LAO_WORD.search(r["text"])), n)
        out["S2 xuống dòng %"] = pct(sum(1 for r in turns if r["newlines"]), len(turns))
        out["S2 chào tạm biệt %"] = pct(sum(1 for r in turns if FAREWELL.search(r["text"])), len(turns))
        out["S2 lặp chữ (nó nó nó) lượt"] = sum(1 for r in turns if STUTTER.search(r["text"]))
        h = len(turns) // 2
        a1 = sum(r["similarity"] for r in turns[:h]) / h
        a2 = sum(r["similarity"] for r in turns[h:]) / (len(turns) - h)
        out["S2 độ lặp nửa đầu → nửa sau"] = f"{a1:.3f} → {a2:.3f}"
        out["_sim_drift"] = a2 - a1
        out["S2 nhại lời nhau tb / %cặp≥0.3"] = echo(turns)
        out["S2 chữ / lượt"] = round(sum(len(r["text"].split()) for r in turns) / len(turns), 1)
        out["S2 lượt bị cấm cụm từ %"] = pct(sum(1 for r in turns if any("lặp lại mấy ý" in x for x in r["director_note"])), len(turns))
        for k, p in MOTIFS.items():
            hits = [r for r in lao if re.search(p, r["text"], re.I)]
            out[f"S2 motif '{k}' lượt/cảnh"] = f"{len(hits)} / {len({r['scene'] for r in hits})}"
        out["S2 prompt token tb / max"] = f"{sum(r['prompt_tokens'] for r in turns) // len(turns)} / {max(r['prompt_tokens'] for r in turns)}"
        if all("secs" in r for r in turns):
            out["S2 giây / lượt"] = round(sum(r["secs"] for r in turns) / len(turns), 1)
    return out


_EN = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dialogue_director_v2_en.py"), encoding="utf-8").read()
STOP_EN = set(re.search(r'STOP = set\("""(.*?)"""', _EN, re.S).group(1).split())
EN_BLEED = re.compile(
    r"(\b(I'?m|I am) (just )?(an? )?(AI|assistant|chatbot|language model|bot)\b|```|happy to help|great question|"
    r"feel free to|let me know if|I hope (this|that) helps|as an AI|certainly!|absolutely!|"
    r"\b(dude|bro|vibes?|awesome|literally|lol|omg|no worries|totally|super cool|amazing)\b|[\U0001F300-\U0001FAFF☀-➿])", re.I)
EN_FAREWELL = re.compile(r"\b(goodbye|bye|good ?night|see you|take care|off to bed|cheerio)\b", re.I)
EN_MOTIFS = {"iceland": r"iceland", "storm '87": r"(1987|eighty-seven|great storm)", "fourteen": r"fourteen|\b14\b",
             "patience/respect": r"\b(patien\w+|respect)\b", "the sea (teaches|knows|gives)": r"the sea (teaches|knows|gives|takes)"}
CJK = re.compile(r"[一-鿿぀-ヿ]")


def echo_en(turns):
    cw = lambda t: {w for w in re.findall(r"[a-z']+", t.lower()) if w not in STOP_EN and len(w) > 2}
    js = []
    for a, b in zip(turns, turns[1:]):
        if a["speaker"] != b["speaker"]:
            x, y = cw(a["text"]), cw(b["text"])
            js.append(len(x & y) / len(x | y) if x and y else 0)
    return f"{sum(js) / len(js):.3f} / {pct(sum(j >= 0.3 for j in js), len(js))}%" if js else None


def score_en(model, seed):
    tag = re.sub(r"[^\w.-]+", "_", model)
    rows = read_jsonl(f"director2en_{tag}_s{seed}.jsonl")
    if not rows:
        return {}
    turns = [r for r in rows if "speaker" in r]
    lao = [r for r in turns if r["speaker"] == "lao"]
    n = len(lao)
    out = {"EN số lượt / cảnh": f"{len(turns)} / {sum(1 for r in rows if 'scene_start' in r)}",
           "EN lệch vai lần sinh đầu %": pct(sum(1 for r in lao if r["raw_bleed"]), n),
           "EN lệch vai sau sinh lại %": pct(sum(1 for r in lao if r["final_bleed"]), n),
           "EN lệch vai (rescore, mọi lượt Jack) %": pct(sum(1 for r in lao if EN_BLEED.search(r["text"])), n),
           "EN Jack gọi 'lad/boy' %": pct(sum(1 for r in lao if re.search(r"\b(lad|boy)\b", r["text"], re.I)), n),
           "EN xuống dòng %": pct(sum(1 for r in turns if r["newlines"]), len(turns)),
           "EN chào tạm biệt %": pct(sum(1 for r in turns if EN_FAREWELL.search(r["text"])), len(turns)),
           "EN lặp chữ lượt": sum(1 for r in turns if STUTTER.search(r["text"])),
           "EN chữ Trung/Nhật lượt": sum(1 for r in turns if CJK.search(r["text"])),
           "EN câu bị cắt (chạm 160 tok)": sum(1 for r in turns if r.get("eval_tokens", 0) >= 160),
           "EN nhại lời nhau tb / %cặp≥0.3": echo_en(turns),
           "EN chữ / lượt Jack": round(sum(len(r["text"].split()) for r in lao) / n, 1)}
    h = len(turns) // 2
    out["EN độ lặp nửa đầu → nửa sau"] = (f"{sum(r['similarity'] for r in turns[:h]) / h:.3f} → "
                                          f"{sum(r['similarity'] for r in turns[h:]) / (len(turns) - h):.3f}")
    out["EN lượt bị cấm cụm từ %"] = pct(sum(1 for r in turns if any("repeated these ideas" in x for x in r["director_note"])), len(turns))
    for k, p in EN_MOTIFS.items():
        hits = [r for r in lao if re.search(p, r["text"], re.I)]
        out[f"EN motif '{k}' lượt/cảnh"] = f"{len(hits)} / {len({r['scene'] for r in hits})}"
    out["EN giây / lượt"] = round(sum(r["secs"] for r in turns) / len(turns), 1)
    return out


CHECKS = [  # key, ok(value), rule text
    ("S0 GPU % @8k ctx", lambda v: v is not None and v >= 100, "100% trên GPU"),
    ("S2 lẫn vai sau sinh lại %", lambda v: v is not None and v <= 1, "≤ 1%"),
    ("S2 lẫn vai lần sinh đầu %", lambda v: v is not None and v <= 10, "≤ 10%"),
    ("S2 lão có xưng 'lão' %", lambda v: v is not None and v >= 90, "≥ 90%"),
    ("S2 xuống dòng %", lambda v: v is not None and v <= 5, "≤ 5%"),
    ("S2 chào tạm biệt %", lambda v: v is not None and v <= 5, "≤ 5%"),
    ("S2 lặp chữ (nó nó nó) lượt", lambda v: v is not None and v <= 2, "≤ 2 lượt"),
    ("_sim_drift", lambda v: v is not None and v <= 0.02, "độ lặp không tăng quá 0.02"),
]

if __name__ == "__main__":
    seed = 1
    if "--seed" in sys.argv:
        i = sys.argv.index("--seed")
        seed = int(sys.argv[i + 1])
        del sys.argv[i:i + 2]
    models = sys.argv[1:] or [DEFAULT_MODEL]
    lang_en = "--en" in sys.argv
    if lang_en:
        sys.argv.remove("--en")
        models = sys.argv[1:] or [DEFAULT_MODEL]
        cards = {m: score_en(m, seed) for m in models}
        keys = list(dict.fromkeys(k for c in cards.values() for k in c))
        print(f"{'chỉ số (kịch bản tiếng Anh)':<44}" + "".join(f"{m[:25]:>26}" for m in models))
        for k in keys:
            print(f"{k:<44}" + "".join(f"{str(cards[m].get(k, '-')):>26}" for m in models))
        sys.exit()
    cards = {m: score(m, seed) for m in models}
    keys = [k for k in dict.fromkeys(k for c in cards.values() for k in c) if not k.startswith("_")]
    w = 26
    print(f"{'chỉ số':<40}" + "".join(f"{m[:w-1]:>{w}}" for m in models))
    for k in keys:
        print(f"{k:<40}" + "".join(f"{str(cards[m].get(k, '-')):>{w}}" for m in models))
    print("\nĐạt chuẩn:")
    for k, ok, rule in CHECKS:
        cells = []
        for m in models:
            v = cards[m].get(k)
            cells.append("-" if v is None and k not in cards[m] else ("ĐẠT" if ok(v) else "TRƯỢT"))
        print(f"  {(k if not k.startswith('_') else 'S2 độ lặp tăng'):<38}" + "".join(f"{c:>{w}}" for c in cells) + f"   ({rule})")
