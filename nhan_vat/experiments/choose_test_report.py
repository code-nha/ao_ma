"""Đếm kết quả choose_test.jsonl: ổn định khi đảo thứ tự, tỉ lệ chọn vị trí A, khớp điểm mắt / is_me, ảnh hưởng của lời tả.

    python -I choose_test_report.py
"""
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
recs = {}
for line in (ROOT / "experiments" / "logs" / "look_loop.jsonl").open(encoding="utf-8"):
    r = json.loads(line)
    recs[(os.path.basename(r["run"].replace("\\", "/")), r["round"])] = r
rows = [json.loads(x) for x in (ROOT / "experiments" / "logs" / "choose_test.jsonl").open(encoding="utf-8")]


def winner(r):
    c = r["answer"].get("choice")
    return tuple(r["A"]) if c == "A" else tuple(r["B"]) if c == "B" else None


for part in ("main", "nonotes"):
    rs = [r for r in rows if r["part"] == part]
    if not rs:
        continue
    pos = Counter(r["answer"].get("choice") for r in rs)
    pair = defaultdict(list)
    for r in rs:
        pair[frozenset([tuple(r["A"]), tuple(r["B"])])].append(r)
    stable = flip = neither = 0
    agree_score = agree_n = 0
    agree_me = agree_me_n = 0
    picks = {}
    for k, two in pair.items():
        if len(two) < 2:
            continue
        w = [winner(r) for r in two]
        if None in w:
            neither += 1
            continue
        if w[0] == w[1]:
            stable += 1
            win = w[0]
            lose = next(x for x in k if x != win)
            picks[k] = win
            if recs[win]["score"] != recs[lose]["score"]:
                agree_n += 1
                agree_score += recs[win]["score"] > recs[lose]["score"]
            nm = {"yes": 2, "almost": 1, "no": 0}
            mw, ml = nm.get(recs[win]["me"].get("is_me"), 0), nm.get(recs[lose]["me"].get("is_me"), 0)
            if mw != ml:
                agree_me_n += 1
                agree_me += mw > ml
        else:
            flip += 1
    n = stable + flip + neither
    if not n:
        continue
    print(f"== {part}: {len(rs)} calls, {n} pairs")
    print(f"   position: A {pos['A']}, B {pos['B']}, neither {pos['neither']}  (A share {pos['A'] / len(rs):.0%})")
    print(f"   order-stable {stable}/{n} ({stable / n:.0%}), flips {flip}, has neither {neither}")
    print(f"   stable picks agree with higher eye score: {agree_score}/{agree_n}; with is_me (almost>no): {agree_me}/{agree_me_n}")
    # per run: wins among stable picks (a ranking), and which round would be chosen
    for run in sorted({k[0] for k in recs if k[0].startswith("20261126")} - {""}):
        wins = Counter()
        for k, win in picks.items():
            if next(iter(k))[0] == run:
                wins[win[1]] += 1
        rounds = sorted(k[1] for k in recs if k[0] == run)
        if not rounds:
            continue
        sc = {r: recs[(run, r)]["score"] for r in rounds}
        print(f"   {run}: wins " + ", ".join(f"r{r}:{wins[r]}" for r in rounds)
              + f" | best score r{max(sc, key=sc.get)} | last r{rounds[-1]}")
    if part == "main":
        main_picks = picks
    else:
        same = sum(1 for k, v in picks.items() if main_picks.get(k) == v)
        both = sum(1 for k in picks if k in main_picks)
        print(f"   same pick as with notes: {same}/{both}")

for part in ("same", "known"):
    rs = [r for r in rows if r["part"] == part]
    if rs:
        print(f"== {part}")
        for r in rs:
            print(f"   A={r['A'][0][-6:]}r{r['A'][1]} B={r['B'][0][-6:]}r{r['B'][1]} -> {r['answer'].get('choice')} | "
                  f"{r['answer'].get('why', '')[:110]}")

ms = Counter(s for r in rows if r["part"] == "main" for s in r["answer"].get("still_missing", []))
print("== still_missing (main):", dict(ms.most_common(8)))
secs = [r["secs"] for r in rows]
print(f"== secs: mean {sum(secs) / len(secs):.1f}, max {max(secs)}")
