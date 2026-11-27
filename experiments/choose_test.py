"""Thử offline bước "chọn bản cuối" của look_loop trên ảnh đã có (không render, chỉ gọi wee).

    python -I choose_test.py [--dry] [--only main|nonotes|same|known] [--api http://wee:11435]

Nhân vật xem 2 bản (mỗi bản 2 ảnh = 4 ảnh một lời gọi), chọn A / B / neither. Không thấy điểm, số vòng, bản nào mới hơn.
Các phần (Fable đề xuất 2026-11-26):
  main     mọi cặp vòng trong từng lần chạy 2026-11-26, cả 2 thứ tự; có lời tả của mắt cho các ô hai bản khác nhau
  nonotes  như main nhưng không có lời tả của mắt (xem nhân vật chọn theo ảnh hay theo chữ)
  same     cùng một vòng làm cả A và B (thiên vị vị trí)
  known    bản "yes" hôm 25 (20261125_213116 vòng 5) so với các vòng nhân vật đã chê "no"
Ghi: experiments/logs/choose_test.jsonl (một dòng mỗi lời gọi; chạy lại thì bỏ qua lời gọi đã có).
Máy dùng chung: wee tuần tự, không gửi options/num_ctx/keep_alive.
"""
import base64
import itertools
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARS = ROOT / "characters"
sys.path.insert(0, str(CHARS / "kb"))
import kbq  # noqa: E402


def opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


API = opt("--api", "http://wee:11435").rstrip("/") + "/api/chat"
ONLY = opt("--only", None)
DRY = "--dry" in sys.argv
MODEL = "gemma4:26b"
CID = "lao_bay"
RUNS = ["20261126_204828", "20261126_205635", "20261126_211737", "20261126_212733", "20261126_214750"]
YES_RUN = ("20261125_213116", 5)
LOG = ROOT / "experiments" / "logs" / "choose_test.jsonl"

SYS_CHOOSE = """You play the character below. A painter made pictures of you from the appearance you chose, in several tries.
There will be no more painting. Now you see two versions, A and B: pictures 1 and 2 are version A, pictures 3 and 4 are version
B (each version painted twice with different seeds). The version you choose becomes your appearance for the whole story.
Judge as yourself, by your IDENTITY, SOUL and LIFE: would people who know you say "that is him/her"? Not by beauty. Be honest.
Clothes, background, light and pose are fixed by the painter; ignore them.
"choice": "A" or "B" for the version closer to you; "neither" only if both are clearly not you.
"best_picture": the single picture (1-4) most like you. "still_missing": up to 3 slots that are still wrong in your choice
(noted for later, not painted now).
Answer JSON: {"choice": "A|B|neither", "why": "<one sentence, as yourself>", "best_picture": 1, "still_missing": ["<slot>"]}"""


def read(name):
    p = CHARS / CID / f"{name}.en.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def call(system, user, schema, images):
    msg = {"role": "user", "content": user,
           "images": [base64.b64encode((ROOT / i).read_bytes()).decode() for i in images]}
    body = {"model": MODEL, "stream": False, "think": False, "format": schema,
            "messages": [{"role": "system", "content": system}, msg]}
    t = time.time()
    for _ in range(3):
        req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            out = json.loads(r.read())
        try:
            return json.loads(out["message"]["content"]), {"secs": round(time.time() - t, 1),
                                                           "prompt_tokens": out.get("prompt_eval_count")}
        except json.JSONDecodeError:
            print("   (malformed JSON, retrying)", flush=True)
    return {}, {"secs": round(time.time() - t, 1), "failed": True}


def load_rounds():
    recs = {}
    for line in (ROOT / "experiments" / "logs" / "look_loop.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        recs[(os.path.basename(r["run"].replace("\\", "/")), r["round"])] = r
    return recs


def phrases(kb, v):
    return "; ".join(kb.phrase(p) for p in (v if isinstance(v, list) else [v])) if v else "ordinary"


def diff_text(kb, a, b, notes):
    """Slots where A and B differ in picks, emphasis or the eye's verdict; observer descriptions only with notes."""
    pa, pb = a["picks"], b["picks"]
    lines = []
    for s in sorted(set(pa) | set(pb)):
        if pa.get(s) != pb.get(s):
            lines.append(f"- {s}: in A you chose \"{phrases(kb, pa.get(s))}\"; in B you chose \"{phrases(kb, pb.get(s))}\"")
    ea, eb = set(a.get("emphasize", [])), set(b.get("emphasize", []))
    if ea != eb:
        lines.append(f"- the painter was told to show strongly: in A {', '.join(sorted(ea)) or 'nothing'}; "
                     f"in B {', '.join(sorted(eb)) or 'nothing'}")
    out = "WHAT DIFFERS BETWEEN A AND B IN WHAT YOU ASKED FOR\n" + ("\n".join(lines) or "- nothing")
    if notes:
        obs = []
        slots = set(a["eyes"][0].get("items", {})) | set(b["eyes"][0].get("items", {}))
        for s in sorted(slots):
            def get(r):
                return [(e.get("items", {}).get(s) or {}) for e in r["eyes"]]
            ga, gb = get(a), get(b)
            if pa.get(s) != pb.get(s) or [x.get("seen") for x in ga] != [x.get("seen") for x in gb]:
                obs.append(f"- {s}: A: " + " / ".join(f"\"{x.get('what', '')}\"" for x in ga)
                           + " | B: " + " / ".join(f"\"{x.get('what', '')}\"" for x in gb))
        if obs:
            out += ("\n\nA NEUTRAL OBSERVER (who does not know you) DESCRIBED THESE SLOTS IN EACH PICTURE "
                    "(picture 1 / picture 2 for A, picture 3 / picture 4 for B)\n" + "\n".join(obs))
    return out


def jobs(recs):
    out = []
    for run in RUNS:
        rs = sorted(k for k in recs if k[0] == run)
        for i, j in itertools.combinations([k[1] for k in rs], 2):
            for part, notes in (("main", True), ("nonotes", False)):
                out.append((part, (run, i), (run, j), notes))
                out.append((part, (run, j), (run, i), notes))
        sc = max(rs, key=lambda k: recs[k]["score"])
        out.append(("same", sc, sc, True))
    nos = [k for k in recs if k[0] in RUNS and recs[k]["me"].get("is_me") == "no"]
    for k in nos:
        out.append(("known", YES_RUN, k, True))
        out.append(("known", k, YES_RUN, True))
    order = {"main": 0, "same": 1, "known": 2, "nonotes": 3}
    return sorted((j for j in out if not ONLY or j[0] == ONLY), key=lambda j: order[j[0]])


def main():
    kb = kbq.load()
    profile = "\n\n".join(x for x in (read("IDENTITY"), read("SOUL"), read("LIFE")) if x)
    recs = load_rounds()
    done = set()
    if LOG.exists():
        for line in LOG.open(encoding="utf-8"):
            r = json.loads(line)
            done.add((r["part"], tuple(r["A"]), tuple(r["B"])))
    schema = {"type": "object", "properties": {
        "choice": {"type": "string", "enum": ["A", "B", "neither"]}, "why": {"type": "string", "maxLength": 300},
        "best_picture": {"type": "integer", "minimum": 1, "maximum": 4},
        "still_missing": {"type": "array", "maxItems": 3, "items": {"type": "string", "enum": list(kb.slots)}}},
        "required": ["choice", "why", "best_picture", "still_missing"]}
    todo = [j for j in jobs(recs) if (j[0], j[1], j[2]) not in done]
    print(len(todo), "calls to do", flush=True)
    for n, (part, ka, kb_, notes) in enumerate(todo, 1):
        a, b = recs[ka], recs[kb_]
        imgs = [x["png"].replace("\\", "/") for x in a["renders"]] + [x["png"].replace("\\", "/") for x in b["renders"]]
        user = f"YOU\n{profile}\n\nPICTURES: 4 (1-2 = version A, 3-4 = version B)\n\n" + diff_text(kb, a, b, notes)
        if DRY:
            print(f"--- {part} A={ka} B={kb_}\n{user[len(profile):]}\n", flush=True)
            continue
        ans, st = call(SYS_CHOOSE, user, schema, imgs)
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "part": part, "A": list(ka), "B": list(kb_), "notes": notes,
               "answer": ans, **st}
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{n}/{len(todo)}] {part} A={ka[0][-6:]}r{ka[1]} B={kb_[0][-6:]}r{kb_[1]} -> {ans.get('choice')} "
              f"({st['secs']}s) {ans.get('why', '')[:120]}", flush=True)


if __name__ == "__main__":
    main()
