"""Acceptance fix 1 (2026-11-25): burn becomes its own cause; sport keywords cover running, swimming, cycling, yoga...

- A burn scar now needs an event that shows a burn (kettle, boiling water, fire), and a burn event no longer
  explains other injury scars (jagged tear, stitched cut).
- LIFE "runs 5 km three mornings a week" now reads as sport.
Run once: python -I src/fix_accept1.py (idempotent).
"""
import json
from pathlib import Path

KB = Path(__file__).resolve().parent.parent

vp = KB / "vocab.json"
v = json.loads(vp.read_text(encoding="utf-8"))
v["causes"]["burn"] = "burns and scalds (fire, boiling water or oil, chemicals)"
ck = v["cause_keywords"]
# "scar" names the result, not the cause: a burn event "left a scar" must not also read as injury. Cuts are injuries.
ck["injury"] = ck["injury"].replace(r"|burn\w*", "").replace(r"|scar\w*", "")
if "|knife" not in ck["injury"]:
    ck["injury"] = ck["injury"].replace(r"|stab\w*", r"|stab\w*|knife|slash\w*|cut (his|her|my) |gashed?")
ck["burn"] = r"\b(burn(ed|t|s)?\b|scald\w*|boiling (water|oil)|kettle|caught fire|on fire|flames?\b|acid)"
ck["sport"] = (r"\b(sports?|boxing|football|soccer|martial|wrestl\w*|gym|athlet\w*|running|runs? \d|ran \d|\d+ ?km\b"
               r"|marathon|jog\w*|swim\w*|cycling|cycles\b|badminton|volleyball|tennis|yoga|dancer?s?\b|dancing)")
v["cite"]["implies"] = {"burn": ["injury"]}   # claim check: "from an injury" is fine when the item shows a burn
cc = v["cite"]["claim_causes"]
if "burn" not in cc:
    cc.append("burn")
vp.write_text(json.dumps(v, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

mp = KB / "catalog" / "marks.jsonl"
out = []
for line in mp.read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    if r["id"] == "marks.burn" and r["causes"] != ["burn"]:
        r["causes"] = ["burn"]
        r["rev"] = r.get("rev", 1) + 1
    out.append(json.dumps(r, ensure_ascii=False))
mp.write_text("\n".join(out) + "\n", encoding="utf-8")
print("ok")

# "lean" muscles mean less fat than average: the Luan hoi check kept flagging wiry/ropy + "average weight" (3 of 5 runs).
cp = KB / "catalog" / "muscle.jsonl"
out = []
for line in cp.read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    if r["id"] in ("muscle.wiry-m", "muscle.ropy-labour-m") and r["dims"].get("fat") != [1, 2]:
        r["dims"]["fat"] = [1, 2]
        r["rev"] = r.get("rev", 1) + 1
    out.append(json.dumps(r, ensure_ascii=False))
cp.write_text("\n".join(out) + "\n", encoding="utf-8")
print("muscle dims ok")
