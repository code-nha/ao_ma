"""So "mắt" chấm ảnh: model x cách hỏi, trên ảnh look_loop đã có, đáp án do Claude gắn (2026-11-25).

    python -I eval_eye.py gemma4:26b [--api http://wee:11435]

Cách hỏi:
  checklist  một lời gọi vision: đọc sẵn cụm LOOK từng ô, trả yes/partly/no/not visible (cách look_loop đang dùng)
  blind      lời gọi 1 (vision) tả từng bộ phận bằng lời của mình, không thấy LOOK; lời gọi 2 (text, không ảnh) so lời tả
             với cụm LOOK, trả yes/partly/no/not visible
Đúng: yes/partly khớp đáp án "yes", no khớp "no". Ghi experiments/logs/eval_eye.jsonl.
Máy dùng chung: tuần tự, không gửi options/num_ctx/keep_alive.
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = (sys.argv[sys.argv.index("--api") + 1] if "--api" in sys.argv else "http://wee:11435") + "/api/chat"
MODEL = sys.argv[1]
LL = ROOT / "experiments" / "look_loop" / "lao_bay"

# đáp án (Claude xem ảnh): cả 10 ảnh vẽ một ông già GẦY, không thấp đậm, không cơ bắp
TRUTH = {"frame": "no", "muscle": "no", "arms": "yes", "teeth": "yes", "ears": "yes", "hair_color": "yes",
         "facial_hair": "yes", "skin_texture": "yes"}
IMAGES = ["20261125_211606/r1_s1", "20261125_211606/r2_s1", "20261125_211606/r4_s1", "20261125_211606/r4_s2",
          "20261125_211606/r5_s1", "20261125_212525/r1_s1", "20261125_212525/r1_s2", "20261125_213116/r3_s1",
          "20261125_213116/r4_s2", "20261125_213116/r5_s1"]
SEEN = ["yes", "partly", "no", "not visible"]
PART = {"frame": "overall body build and frame (width, stockiness, bone)", "muscle": "muscles (how much, how defined)",
        "arms": "forearms and arms", "teeth": "teeth", "ears": "ears (size relative to head)", "hair_color": "head hair colour",
        "facial_hair": "beard, moustache, stubble", "skin_texture": "face skin texture and creases"}

SYS_CHECK = """You look at one photograph of a person and describe ONLY what is visible. You know nothing else about this person.
For each checklist line, say whether the photo shows it: "yes", "partly", "no", or "not visible" (cropped, covered, too small).
In "what", say in a few words what the photo actually shows there.
Answer JSON only."""
SYS_DESC = """You look at one photograph of a person. For each body part listed, describe in plain words what the photo shows
(size, shape, condition), as a careful, unflattering observer. Compare with an average person of the same apparent age and sex
("thinner than average", "unusually large"...). If the part is visible but absent (no beard, no visible veins), say so
plainly ("none: clean-shaven"). Say "not visible" ONLY when it is cropped, covered or too small to judge. Answer JSON only."""
SYS_CMP = """You compare an observer's description of a photo with what a character's appearance should be. For each slot, does the
description show the intended feature? "yes", "partly", "no", or "not visible" (the observer could not see it).
- "yes": the description matches, in other words is fine ("yellowed stained teeth" for "tobacco-stained teeth").
- "partly": same direction but weaker or only some aspects mentioned, and nothing contradicts ("thin bony forearms" for "wiry
  veiny forearms"; "slightly yellow" for "brown stained").
- "no": the description contradicts the intended feature: a thin, slight body is "no" for "stocky" or "muscular"; a full beard
  is "no" for "hairless face".
- An intended ABSENCE ("hairless face", "no scars") matches a description saying none / not present / clean.
Answer JSON only."""


def call(system, user, schema, image=None):
    msg = {"role": "user", "content": user}
    if image:
        msg["images"] = [base64.b64encode(image.read_bytes()).decode()]
    body = {"model": MODEL, "stream": False, "think": False, "format": schema,
            "messages": [{"role": "system", "content": system}, msg]}
    t = time.time()
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(r.read())
    try:
        res = json.loads(out["message"]["content"])
    except json.JSONDecodeError:
        res = {}
    return res, round(time.time() - t, 1)


def main():
    sys.path.insert(0, str(ROOT / "characters" / "kb"))
    import kbq
    kb = kbq.load()
    tally = {"checklist": [], "blind": []}
    log = (ROOT / "experiments" / "logs" / "eval_eye.jsonl").open("a", encoding="utf-8")
    for name in IMAGES:
        run, img = name.split("/")
        png = LL / run / f"{img}.png"
        look = json.loads((LL / run / f"{img.split('_')[0]}_LOOK.kb.json").read_text(encoding="utf-8"))
        phr = {s: "; ".join(kb.phrase(p) for p in (look["picks"][s] if isinstance(look["picks"][s], list) else [look["picks"][s]]))
               for s in TRUTH}
        item = {"type": "object", "properties": {"seen": {"type": "string", "enum": SEEN}, "what": {"type": "string", "maxLength": 120}},
                "required": ["seen", "what"]}
        # checklist
        sch = {"type": "object", "properties": {"items": {"type": "object", "properties": {s: item for s in TRUTH},
                                                          "required": list(TRUTH)}}, "required": ["items"]}
        a, ta = call(SYS_CHECK, "CHECKLIST (slot: what to look for)\n" + "\n".join(f"{s}: {phr[s]}" for s in TRUTH), sch, png)
        got_a = {s: (a.get("items", {}).get(s) or {}).get("seen") for s in TRUTH}
        # blind: describe, then compare (text only)
        schd = {"type": "object", "properties": {s: {"type": "string", "maxLength": 160} for s in TRUTH}, "required": list(TRUTH)}
        d, td = call(SYS_DESC, "BODY PARTS\n" + "\n".join(f"{s}: {PART[s]}" for s in TRUTH), schd, png)
        schc = {"type": "object", "properties": {s: {"type": "string", "enum": SEEN} for s in TRUTH}, "required": list(TRUTH)}
        c, tc = call(SYS_CMP, "\n".join(f"{s}: intended \"{phr[s]}\" | observer: \"{d.get(s, '')}\"" for s in TRUTH), schc)
        got_b = {s: c.get(s) for s in TRUTH}
        for meth, got in (("checklist", got_a), ("blind", got_b)):
            for s in TRUTH:
                ok = (got[s] in ("yes", "partly")) if TRUTH[s] == "yes" else got[s] == "no"
                tally[meth].append((s, ok))
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": MODEL, "image": name, "truth": TRUTH, "phrases": phr,
               "checklist": got_a, "checklist_raw": a, "describe": d, "blind": got_b, "secs": [ta, td, tc]}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        print(name, "checklist", {s: got_a[s] for s in ("frame", "muscle")}, "blind", {s: got_b[s] for s in ("frame", "muscle")},
              "secs", [ta, td, tc], flush=True)
    for meth, xs in tally.items():
        acc = sum(ok for _, ok in xs) / len(xs)
        neg = [ok for s, ok in xs if TRUTH[s] == "no"]
        pos = [ok for s, ok in xs if TRUTH[s] == "yes"]
        print(f"{MODEL} {meth:9}: all {acc:.0%} | catches 'no' (frame, muscle) {sum(neg)}/{len(neg)} | 'yes' items {sum(pos)}/{len(pos)}")


if __name__ == "__main__":
    main()
