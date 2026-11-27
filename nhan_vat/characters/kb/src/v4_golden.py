"""One-off (history): append v4 golden cases (facts with full Lao Bay files, stricter cite, facet baselines, height, freq, hint).
Idempotent: a case is skipped when its note is already in tests/golden.jsonl.   python -I v4_golden.py"""
import json
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
LB = KB.parent / "lao_bay"
idt, life, style = ((LB / f).read_text(encoding="utf-8") for f in ("IDENTITY.en.md", "LIFE.en.md", "STYLE.en.md"))
F = {"identity": idt, "life": life, "style": style}
C = [
    dict(kind="facts", **F, tags=["poor", "sea", "outdoor-manual", "kinh", "coastal", "born-pre1960"], not_tags=["office"],
         life_tags={"1": ["water-work"], "2": ["poverty"]}, life_not={"7": ["childbearing"], "4": ["water-work"], "5": ["injury"]},
         note="v4: full Lao Bay LIFE with interpretation lines; son leaving is not childbearing, buying a boat is not water work"),
    dict(kind="cite", **F, slot="eyes", pick="eyes.cataract", cite="LIFE 5", expect="reject",
         note="v4: observed 2026-11-24 cataract cited to the storm item; the item must show ageing or illness"),
    dict(kind="cite", **F, slot="eyes", pick="eyes.cataract", cite="IDENTITY Age", expect="ok", note="v4: cataract at 70 cited to age is fine"),
    dict(kind="cite", **F, slot="eyes", pick="eyes.cataract", cite="IDENTITY Age", why="one eye clouded milky white from an old injury",
         expect="reject", note="v4: reason claims an injury that nothing in LIFE shows"),
    dict(kind="baseline", sex="male", age=70, tags=["sea", "coastal", "rural", "kinh"], slot="skin_tone", expect="skin_tone.deeptan",
         note="v4: an old fisherman is sun-darkened by default"),
    dict(kind="baseline", sex="male", age=30, tags=["office", "urban", "kinh"], slot="skin_tone", expect="skin_tone.normal-m",
         note="v4: urban office man keeps the light default"),
    dict(kind="baseline", sex="female", age=40, tags=["farm", "rural", "kinh"], slot="skin_tone", expect="skin_tone.golden",
         note="v4: farm woman is tanned by default"),
    dict(kind="baseline", sex="male", age=50, tags=["sea", "kinh"], slot="body_skin", expect="body_skin.farmertan-m",
         note="v4: outdoor worker gets the work tan"),
    dict(kind="height", sex="male", age=70, tags=["kinh"], born=1956, mean_between=[161.5, 164.0],
         note="v4: NCD-RisC VN men born 1956"),
    dict(kind="height", sex="male", age=26, tags=["kinh"], born=2000, mean_between=[166.0, 168.0],
         note="v4: NCD-RisC VN men born 2000"),
    dict(kind="height", sex="female", age=50, tags=["kinh"], born=1976, mean_between=[153.0, 155.5],
         note="v4: NCD-RisC VN women born 1976"),
    dict(kind="freq", id="fat.very-thin-m", sex="male", age=70, tags=["kinh"], expect="common",
         note="v4: NCD-RisC 2024 VN men 65+ BMI < 18.5 is about 23%"),
    dict(kind="freq", id="fat.obese-f", sex="female", age=55, tags=["kinh"], expect="uncommon",
         note="v4: NCD-RisC 2024 VN women 45-64 BMI 30-35 is 3.4%"),
    dict(kind="freq", id="face_shape.normal-m", sex="male", age=22, tags=["kinh"], expect="common", note="v4: oval 66% (VMJ 2021)"),
    dict(kind="hint", sex="male", age=40, tags=["kinh"], picks={"height": "height.very-short-m", "shoulders": "shoulders.very-broad-m"},
         note="v4: ANSUR proxy hint, never a conflict"),
]
gp = KB / "tests" / "golden.jsonl"
rows = [json.loads(x) for x in gp.read_text(encoding="utf-8").splitlines() if x.strip()]
notes = {r.get("note") for r in rows}
add = [c for c in C if c["note"] not in notes]
gp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows + add), encoding="utf-8")
print(f"added {len(add)}; total {len(rows) + len(add)}")
