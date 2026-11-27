"""Thử offline cách "chấm từng bản" (2026-11-27): mỗi lời gọi chỉ một bản (2 ảnh, 2 seed), nhân vật chấm 1-10 "giống mình tới đâu".
Không có A/B nên không có thiên vị vị trí (choose_test.py: 2 bản cạnh nhau thì 26b chọn bản đứng trước 86%).

    python -I choose_rate.py [--dry] [--reps 2] [--api http://wee:11435]

Chấm 25 vòng của 5 lần chạy 2026-11-26 + bản "yes" hôm 25, mỗi bản --reps lần (cùng input, để đo độ ổn định).
Nhân vật chỉ thấy ảnh và hồ sơ: không thấy lời tả của mắt, điểm, số vòng.
Ghi: experiments/logs/choose_rate.jsonl; chạy lại thì bỏ qua lời gọi đã có. Đếm: --report.
"""
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # -I drops the script dir
from choose_test import RUNS, YES_RUN, ROOT, call, load_rounds, read, opt

REPS = int(opt("--reps", "2"))
DRY = "--dry" in sys.argv
LOG = ROOT / "experiments" / "logs" / "choose_rate.jsonl"

SYS_RATE = """You play the character below. A painter made a picture of you from the appearance you chose; you see it painted twice
(different seeds, same description). Judge as yourself, by your IDENTITY, SOUL and LIFE: would people who know you say "that is
him/her"? Not by beauty. Be honest and strict. Clothes, background, light and pose are fixed by the painter; ignore them.
First say what in the pictures is like you and what is not, then rate.
"rating" 1-10: 10 = people would know you at once; 7 = clearly you but some things are off; 5 = could be you or many other men or
women your age; 3 = mostly not you; 1 = not you at all.
Answer JSON: {"like_me": "<short>", "not_like_me": "<short>", "rating": 1}"""

SCHEMA = {"type": "object", "properties": {
    "like_me": {"type": "string", "maxLength": 300}, "not_like_me": {"type": "string", "maxLength": 300},
    "rating": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["like_me", "not_like_me", "rating"]}


def targets(recs):
    return sorted(k for k in recs if k[0] in RUNS) + [YES_RUN]


def run():
    recs = load_rounds()
    profile = "\n\n".join(x for x in (read("IDENTITY"), read("SOUL"), read("LIFE")) if x)
    have = defaultdict(int)
    if LOG.exists():
        for line in LOG.open(encoding="utf-8"):
            r = json.loads(line)
            have[tuple(r["v"])] += 1
    todo = [(k, rep) for rep in range(REPS) for k in targets(recs) if have[k] <= rep]
    print(len(todo), "calls to do", flush=True)
    user = f"YOU\n{profile}\n\nPICTURES: 2 (same description, different painter seeds)"
    for n, (k, rep) in enumerate(todo, 1):
        imgs = [x["png"].replace("\\", "/") for x in recs[k]["renders"]]
        if DRY:
            print(k, rep, imgs)
            continue
        ans, st = call(SYS_RATE, user, SCHEMA, imgs)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "v": list(k), "rep": rep, "answer": ans, **st},
                                ensure_ascii=False) + "\n")
        print(f"[{n}/{len(todo)}] {k[0][-6:]}r{k[1]} rep{rep} -> {ans.get('rating')} ({st['secs']}s) "
              f"| not: {ans.get('not_like_me', '')[:90]}", flush=True)


def report():
    recs = load_rounds()
    by = defaultdict(list)
    for line in LOG.open(encoding="utf-8"):
        r = json.loads(line)
        if "rating" in r["answer"]:
            by[tuple(r["v"])].append(r["answer"]["rating"])
    allr = [x for v in by.values() for x in v]
    print(f"calls {len(allr)}; ratings {dict(sorted((x, allr.count(x)) for x in set(allr)))}")
    diffs = [abs(v[0] - v[1]) for v in by.values() if len(v) >= 2]
    print(f"repeat |diff|: mean {statistics.mean(diffs):.2f}, same {sum(d == 0 for d in diffs)}/{len(diffs)}, "
          f">=2: {sum(d >= 2 for d in diffs)}")
    for run in RUNS:
        ks = sorted(k for k in by if k[0] == run)
        m = {k: statistics.mean(by[k]) for k in ks}
        best = max(ks, key=lambda k: (m[k], k[1]))
        sc = max(ks, key=lambda k: recs[k]["score"])
        print(f"{run}: " + ", ".join(f"r{k[1]} {m[k]:.1f}({recs[k]['me'].get('is_me', '?')[0]},{recs[k]['score']:.2f})" for k in ks)
              + f" | top rating r{best[1]} | top score r{sc[1]}")
    if YES_RUN in by:
        nos = [k for k in by if k in recs and k[0] in RUNS and recs[k]["me"].get("is_me") == "no"]
        print(f"yes-round {YES_RUN}: {statistics.mean(by[YES_RUN]):.1f} {by[YES_RUN]} | 'no' rounds: "
              + ", ".join(f"{k[0][-6:]}r{k[1]} {statistics.mean(by[k]):.1f}" for k in nos))
    xs = [(statistics.mean(by[k]), recs[k]["score"]) for k in by if k[0] in RUNS]
    if len(xs) > 2:
        print(f"corr(rating, eye score) over {len(xs)} rounds: {statistics.correlation(*zip(*xs)):.2f}")
    print("is_me vs mean rating:", {s: round(statistics.mean([statistics.mean(by[k]) for k in by if k[0] in RUNS
                                                              and recs[k]['me'].get('is_me') == s]), 2)
                                    for s in ("almost", "no")})


if __name__ == "__main__":
    report() if "--report" in sys.argv else run()
