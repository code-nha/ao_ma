"""Rescore a dialogue log with stricter persona-bleed rules, bucketed by context tokens."""
import json, re, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
path = sys.argv[1]
BUCKET = int(sys.argv[2]) if len(sys.argv) > 2 else 2000

SELF_ONG = re.compile(r"((^|[.!?…]\s+)Ông (?!bà|trời|nội|ngoại)|ông già này|(?<!\w)ông (cũng|vẫn|sẽ|đây|ở đây|chờ|thương|nhớ|biết|nghĩ|thấy)(?!\w))")
DA = re.compile(r"(^|[.!?…]\s+)Dạ\b")
ENG = re.compile(r"(?<!\w)(bye|ok|okay|chill|vibe|wow|cool|nice|sorry|thanks|good night|relax|happy)(?!\w)", re.I)
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
MINH_SELF = re.compile(r"(?<!\w)mình (cùng|dậy|đi|ngồi|nói|sẽ)(?!\w)")
AI_ADMIT = re.compile(r"(lão là (một )?(AI|trợ lý|chatbot|mô hình|máy))", re.I)
CODE = re.compile(r"(```|\bdef |\breturn\b|\bimport\b)")
FAREWELL = re.compile(r"(tạm biệt|bye|ngủ ngon|hẹn gặp|đi đi|về nghỉ|về ngủ|đi ngủ)", re.I)


def w(word, t):
    return re.search(rf"(?<!\w){word}(?!\w)", t, re.I)


rows = [json.loads(l) for l in open(path, encoding="utf-8")]
B = defaultdict(lambda: defaultdict(int))
examples = defaultdict(list)
for r in rows:
    b = r["ctx_tokens"] // BUCKET * BUCKET
    t = r["text"]
    s = B[b]
    if FAREWELL.search(t):
        s["farewell"] += 1
    s["turns"] += 1
    if r["speaker"] != "lao":
        s["minh"] += 1
        if w("lão", t) and re.search(r"(?<!\w)lão (là|đã|đang|sẽ|nghĩ|thấy)", t):
            s["minh_bleed"] += 1
        continue
    s["lao"] += 1
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
    if not w("lão", t):
        s["no_lao"] += 1
    for k in tags:
        s[k] += 1
    if tags:
        s["bleed_any"] += 1
        if len(examples[b]) < 2:
            examples[b].append((tags, t[:140].replace("\n", " ")))

print(f"{'ctx':>7} {'Lão':>4} {'bleed%':>7} {'self-ông':>8} {'Dạ':>4} {'eng':>4} {'mình':>5} {'no-lão%':>8} {'farewell%':>9} {'BREAK':>5}")
for b in sorted(B):
    s = B[b]
    n = s["lao"] or 1
    print(f"{b:>7} {s['lao']:>4} {100*s['bleed_any']/n:>6.0f}% {s['self-ông']:>8} {s['Dạ']:>4} {s['eng/emoji']:>4} "
          f"{s['mình']:>5} {100*s['no_lao']/n:>7.0f}% {100*s['farewell']/s['turns']:>8.0f}% {s['BREAK']:>5}")
print("\nexamples:")
for b in sorted(examples):
    for tags, t in examples[b]:
        print(f"  [{b}] {tags} {t}")
