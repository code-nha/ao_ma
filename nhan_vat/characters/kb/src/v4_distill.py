"""One-off (history): v3 -> v3 + real numbers. Applies distilled numbers and standard terms to the catalog.
Run after distill_ncdrisc.py, distill_tables.py, distill_maad.py, distill_ansur.py, distill_vocab.py (they write
stats.json, standards.json, evidence/num/*.csv). Idempotent: re-running sets the same fields.

    python -I v4_distill.py
Edits: vocab.json (baseline_facets, stricter cause keywords, cite claims, slot std), catalog (freq basis=stat rows with p,
z bands for height, facet baselines for skin, std term lists, new values), evidence/*.jsonl cards, sources.jsonl,
vi.jsonl, rules.jsonl (1 exclude + soft hints), tests/golden.jsonl (new cases appended once)."""
import json
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
ST = json.loads((KB / "stats.json").read_text(encoding="utf-8"))
STD = json.loads((KB / "standards.json").read_text(encoding="utf-8"))
BANDS = {"young": [18, 29], "adult": [30, 44], "middle": [45, 64], "elderly": [65, 120]}


def cls_of(p):
    return "common" if p >= 0.10 else "uncommon" if p >= 0.02 else "rare"


# ------------------------------------------------------------------ catalog io
def load_cat():
    cat = {}
    for p in sorted((KB / "catalog").glob("*.jsonl")):
        cat[p.stem] = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return cat


def save_cat(cat):
    for slot, rows in cat.items():
        (KB / "catalog" / f"{slot}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                      encoding="utf-8")


CAT = load_cat()
IDX = {v["id"]: v for rows in CAT.values() for v in rows}


def V(vid):
    if vid not in IDX:
        raise SystemExit(f"unknown id {vid}")
    return IDX[vid]


def add_ev(v, card, rel):
    if not any(e["c"] == card for e in v["ev"]):
        v["ev"].append({"c": card, "rel": rel})


def set_std(vid, terms):
    for t in terms:
        if t not in STD["terms"]:
            raise SystemExit(f"{vid}: std term {t} not in standards.json")
    v = V(vid)
    v["std"] = sorted(set(v.get("std", [])) | set(terms))


def new_value(slot, row):
    base = {"slot": slot, "status": "active", "baseline_for": [], "dims": {}, "regions": [], "needs": [], "fit": [], "ev": [],
            "since": 4, "rev": 1}
    base.update(row)
    if base["id"] in IDX:
        old = IDX[base["id"]]
        old.update({k: v for k, v in base.items() if k not in ("since",)})
        return old
    CAT[slot].append(base)
    IDX[base["id"]] = base
    return base


def stat_rows(by_band, src, age):
    """by_band {band: p} -> freq rows: default = first band inside age, then a 'when' row per band inside age."""
    bands = [b for b, (lo, hi) in BANDS.items() if hi >= age[0] and lo <= age[1] and b in by_band]
    rows = [{"cls": cls_of(by_band[bands[0]]), "basis": "stat", "p": round(by_band[bands[0]], 4), "src": f"{src} {bands[0]}"}]
    for b in bands:
        rows.append({"when": {"band": b}, "cls": cls_of(by_band[b]), "basis": "stat", "p": round(by_band[b], 4), "src": f"{src} {b}"})
    return rows


def sex_rows(pm, pf, src):
    return [{"cls": cls_of(pm), "basis": "stat", "p": pm, "src": f"{src} men"},
            {"when": {"sex": "male"}, "cls": cls_of(pm), "basis": "stat", "p": pm, "src": f"{src} men"},
            {"when": {"sex": "female"}, "cls": cls_of(pf), "basis": "stat", "p": pf, "src": f"{src} women"}]


# ------------------------------------------------------------------ 1. height: z bands vs same sex x birth cohort x population
ZP = {"very-short": 0.0228, "short": 0.1359, "normal": 0.6827, "tall": 0.1359, "very-tall": 0.0228}
ZB = ST["height"]["z_bands"]
for sx in ("m", "f"):
    for band in ZP:
        v = V(f"height.{band}-{sx}")
        v["z"] = ZB[band]
        v["freq"] = [{"cls": cls_of(ZP[band]), "basis": "stat", "p": ZP[band],
                      "src": f"normal model z {ZB[band]} around NCD-RisC cohort mean (stats.json height)"}]
        add_ev(v, "ncd.h.vn", "freq")
        add_ev(v, "ncd.h.sd", "freq")
V("height.gangly-m")["z"] = [1.0, 9]
tm = V("height.tall-m")
if tm["phrase"] != "tall man, taller than most men":
    tm["phrase"], tm["rev"] = "tall man, taller than most men", tm.get("rev", 1) + 1
vt = V("height.very-tall-m")
if vt["phrase"] != "very tall lanky man, towering over most men":
    vt["phrase"], vt["rev"] = "very tall lanky man, towering over most men", vt.get("rev", 1) + 1
for vid in ("height.very-short-m", "height.very-short-f", "height.short-m", "height.short-f", "height.normal-m",
            "height.normal-f", "height.tall-m", "height.tall-f", "height.very-tall-m", "height.very-tall-f"):
    set_std(vid, ["dvi:408-height", "tt22:chieu-cao"])

# ------------------------------------------------------------------ 2. fat from NCD-RisC BMI 2024 (Viet Nam)
BMI = ST["bmi"]["by"]
FATMAP = {"very-thin": ["lt18.5"], "thin": ["18.5-20"], "normal": ["20-25"], "overweight": ["25-30"], "obese": ["30-35"],
          "very-obese": ["35-40", "ge40"]}
for sx, sex in (("m", "male"), ("f", "female")):
    for key, cats in FATMAP.items():
        v = V(f"fat.{key}-{sx}")
        by = {b: sum(BMI[f"kinh/{sex}/2024/{b}"][c] for c in cats) for b in BANDS}
        v["freq"] = stat_rows(by, f"NCD-RisC 2024 VNM {sex} BMI {'+'.join(cats)}", v["age"])
        add_ev(v, "ncd.bmi.vn", "freq")
        add_ev(v, "steps.bmi", "supports")
        v["std"] = sorted(set(v.get("std", [])))
    for key in ("overweight", "obese"):
        v = V(f"fat.{key}-{sx}")
        v["fit"] = sorted(set(v["fit"]) | {"urban"})
        add_ev(v, "steps.ur", "supports")
    for key in ("thin", "very-thin"):
        v = V(f"fat.{key}-{sx}")
        v["fit"] = sorted(set(v["fit"]) | {"rural"})
        add_ev(v, "steps.ur", "supports")
for vid, b in (("fat.thin-m", "416-build-slight"), ("fat.thin-f", "416-build-slight"), ("fat.very-thin-m", "416-build-slight"),
               ("fat.very-thin-f", "416-build-slight"), ("fat.obese-m", "416-build-large"), ("fat.obese-f", "416-build-large")):
    set_std(vid, [f"dvi:{b}"])
# waist over cut-off (90 cm men / 85 cm women), STEPS 2021 Table A27
WM = {"young": 0.086, "adult": 0.166, "middle": 0.186, "elderly": 0.186}
WF = {"young": 0.114, "adult": 0.151, "middle": 0.333, "elderly": 0.333}
v = V("waist_belly.soft-m")
v["freq"] = stat_rows(WM, "STEPS VN 2021 Table A27 waist >= 90 cm (50-69 used for elderly)", v["age"])
add_ev(v, "steps.waist", "freq")
v = V("waist_belly.thick-meno-f")
v["freq"] = stat_rows(WF, "STEPS VN 2021 Table A27 waist >= 85 cm (50-69 used for elderly)", v["age"])
add_ev(v, "steps.waist", "freq")

# ------------------------------------------------------------------ 3. skin tone / body skin depend on sun exposure (life, place)
OUT = ["outdoor-manual", "sea", "farm", "street", "military"]
PLACE = ["rural", "coastal", "highland"]


def facet_baseline(vid, tags, sex):
    v = V(vid)
    keys = [f"{t}/{sex}-{b}" for t in tags for b in BANDS]
    v["baseline_for"] = sorted(set(v["baseline_for"]) | set(keys))


for _vid in ("skin_tone.deeptan", "skin_tone.golden", "skin_tone.olive", "body_skin.farmertan-m", "body_skin.farmertan-f"):
    V(_vid)["baseline_for"] = []   # these had no baselines in v3; rebuilt here
facet_baseline("skin_tone.deeptan", OUT, "male")
facet_baseline("skin_tone.golden", OUT, "female")
facet_baseline("skin_tone.golden", PLACE, "male")
facet_baseline("skin_tone.olive", PLACE, "female")
facet_baseline("body_skin.farmertan-m", OUT, "male")
facet_baseline("body_skin.farmertan-f", OUT, "female")
for vid in ("skin_tone.deeptan", "skin_tone.golden", "skin_tone.olive", "body_skin.farmertan-m", "body_skin.farmertan-f"):
    add_ev(V(vid), "std.skin", "describes")

# ------------------------------------------------------------------ 4. face from the Kinh papers
KF = ST["kinh_face"]


def kf(idx, classes, sex):
    return round(sum(KF[f"{idx}|{c}|{sex}"] for c in classes) / 100, 4)


SRC_K = "TCNCYH 2023 Kinh 18-25 (n 3068 m / 4308 f)"
head = new_value("head", {"id": "head.oval", "sex": "any", "age": [18, 120], "phrase": "oval head, moderately long front to back",
                          "causes": ["genetics"], "freq": [], "sal": [{"s": "plain"}]})
for vid, classes in (("head.normal", ["short81-86"]), ("head.flatback", ["very_short>86"]), ("head.oval", ["medium76-81"]),
                     ("head.long", ["very_long<71", "long71-76"])):
    v = V(vid)
    v["freq"] = sex_rows(kf("cephalic", classes, "male"), kf("cephalic", classes, "female"), f"{SRC_K} Bang 2 cephalic {'+'.join(classes)}")
    add_ev(v, "kf.head", "freq")
add_ev(V("head.broad"), "kf.head", "supports")
for vid, classes in (("face_shape.wideshort", ["very_wide<80"]), ("face_shape.long", ["long90-95", "very_long>95"])):
    v = V(vid)
    v["freq"] = sex_rows(kf("facial_total", classes, "male"), kf("facial_total", classes, "female"),
                         f"{SRC_K} Bang 3 total facial index {'+'.join(classes)}")
    add_ev(v, "kf.face", "freq")
SRC_V = "VMJ 2021 Binh Duong Kinh 18-25 (n 2462, both sexes) Celebie-Jerolimov"
for vid, cls_, p in (("face_shape.normal-m", "oval", 0.663), ("face_shape.normal-f", "oval", 0.663),
                     ("face_shape.square-m", "square", 0.266), ("face_shape.square-f", "square", 0.266),
                     ("face_shape.heart", "triangle (both kinds, upper bound)", 0.071),
                     ("face_shape.pear", "triangle (both kinds, upper bound)", 0.071)):
    v = V(vid)
    v["freq"] = [{"cls": cls_of(p), "basis": "stat", "p": p, "src": f"{SRC_V} {cls_}"}]
    add_ev(v, "kf.celebie", "freq")
nose_slim = new_value("nose", {"id": "nose.slim", "sex": "any", "age": [18, 120], "phrase": "narrow nose with slim nostrils",
                               "causes": ["genetics"], "freq": [], "sal": [{"s": "mild"}]})
for vid, classes in (("nose.normal", ["medium70-85"]), ("nose.flaring", ["wide85-100"]),
                     ("nose.flat", ["very_wide100-115", "hyper_wide>115"]), ("nose.slim", ["narrow55-70"]),
                     ("nose.pinched", ["hyper_narrow<40", "very_narrow40-55"])):
    v = V(vid)
    v["freq"] = sex_rows(kf("nasal", classes, "male"), kf("nasal", classes, "female"), f"{SRC_K} Bang 4 nasal index {'+'.join(classes)}")
    add_ev(v, "kf.nose", "freq")
v = V("mouth.protruding")
v["freq"] = sex_rows(kf("prognathism", ["prognathic109-113", "very>113"], "male"),
                     kf("prognathism", ["prognathic109-113", "very>113"], "female"), f"{SRC_K} Bang 5 prognathism index >= 109")
add_ev(v, "kf.prog", "freq")
v = V("jaw_chin.delicate")
v["freq"] = sex_rows(kf("mandibular", ["narrow<76"], "male"), kf("mandibular", ["narrow<76"], "female"),
                     f"{SRC_K} Bang 6 mandibular index < 76")
add_ev(v, "kf.mand", "freq")
jf = V("jaw_chin.normal-f")
if jf["phrase"] != "soft rounded jaw, small rounded chin":
    jf["phrase"], jf["rev"] = "soft rounded jaw, small rounded chin", jf.get("rev", 1) + 1   # 98% of Kinh women: wide mandibular index
add_ev(jf, "kf.mand", "supports")
for vid in ("ears.normal", "ears.large", "eyes.normal", "nose.normal", "mouth.normal", "forehead.normal-m", "forehead.normal-f"):
    add_ev(V(vid), "kf.meas", "describes")

# ------------------------------------------------------------------ 5. new values from the standard vocabularies
NEW = [
    ("eyes", {"id": "eyes.glasseye", "sex": "any", "age": [18, 120], "phrase": "one glass eye, fixed and lifeless",
              "causes": ["injury", "illness"], "freq": [{"cls": "rare", "basis": "est"}], "sal": [{"s": "marked"}],
              "regions": ["eye_unequal"], "std": ["dvi:eyes-artificial", "ncic_smt:ART EYE"]}),
    ("ears", {"id": "ears.lobecrease", "sex": "any", "age": [45, 120], "phrase": "diagonal crease across the earlobe",
              "causes": ["ageing"], "freq": [{"cls": "uncommon", "basis": "est"}, {"when": {"band": "elderly"}, "cls": "common", "basis": "est"}],
              "sal": [{"s": "plain"}], "std": ["eom:lobe-anterior-crease-s"]}),
    ("ears", {"id": "ears.darwin", "sex": "any", "age": [18, 120], "phrase": "small bump on the upper rim of the ear",
              "causes": ["genetics"], "freq": [{"cls": "uncommon", "basis": "est"}], "sal": [{"s": "plain"}],
              "std": ["eom:helix-darwin-tubercle"]}),
    ("ears", {"id": "ears.pit", "sex": "any", "age": [18, 120], "phrase": "tiny pit just in front of the ear",
              "causes": ["genetics"], "freq": [{"cls": "uncommon", "basis": "est"}], "sal": [{"s": "plain"}],
              "std": ["eom:pit-preauricular"]}),
    ("ears", {"id": "ears.tag", "sex": "any", "age": [18, 120], "phrase": "small skin tag in front of the ear",
              "causes": ["genetics"], "freq": [{"cls": "rare", "basis": "est"}], "sal": [{"s": "mild"}],
              "std": ["eom:tag-preauricular"]}),
    ("hands", {"id": "hands.extrafinger", "sex": "any", "age": [18, 120], "phrase": "small extra finger beside the thumb",
               "causes": ["genetics"], "freq": [{"cls": "rare", "basis": "est"}], "sal": [{"s": "marked"}],
               "std": ["eom:hand-preaxial-polydactyly-of", "ncic_smt:EXTR FGR"]}),
    ("hands", {"id": "hands.webbed", "sex": "any", "age": [18, 120], "phrase": "two fingers joined by skin",
               "causes": ["genetics"], "freq": [{"cls": "rare", "basis": "est"}], "sal": [{"s": "mild"}],
               "std": ["eom:fingers-cutaneous-syndactyly-of"]}),
    ("hands", {"id": "hands.claw", "sex": "any", "age": [18, 120], "phrase": "one hand stiff and curled, fingers bent",
               "causes": ["injury", "illness"], "freq": [{"cls": "rare", "basis": "est"}], "sal": [{"s": "marked"}],
               "std": ["ncic_smt:CRIP HAND"]}),
    ("legs", {"id": "legs.oneshort", "sex": "any", "age": [18, 120], "phrase": "one leg shorter, hip dipping on that side",
              "causes": ["injury", "illness", "genetics"], "freq": [{"cls": "rare", "basis": "est"}], "sal": [{"s": "marked"}],
              "std": ["ncic_smt:SHRT LEG"]}),
    ("feet", {"id": "feet.sandalgap", "sex": "any", "age": [18, 120], "phrase": "wide gap between the big and second toes",
              "causes": ["barefoot", "genetics"], "freq": [{"cls": "uncommon", "basis": "est"}], "sal": [{"s": "plain"}],
              "fit": ["farm", "outdoor-manual", "poor", "sea"], "std": ["eom:sandal-gap"]}),
]
for slot, row in NEW:
    v = new_value(slot, row)
    add_ev(v, "std.vocab", "describes")

# ------------------------------------------------------------------ 6. standard terms on existing values
E = lambda *labels: [f"eom:{x}" for x in labels]  # noqa: E731
MAP = {
    "head.broad": E("brachycephaly"), "head.flatback": E("occiput-flat", "brachycephaly"), "head.long": E("dolichocephaly"),
    "head.occiput": E("occiput-prominent"), "head.sideflat": E("plagiocephaly"), "head.large": E("macrocephaly"),
    "face_shape.round": E("face-round"), "face_shape.long": E("face-long"), "face_shape.square-m": E("face-square"),
    "face_shape.square-f": E("face-square"), "face_shape.heart": E("face-triangular"), "face_shape.flatbroad": E("face-flat", "face-broad"),
    "face_shape.wideshort": E("face-broad", "face-short"), "face_shape.concave": E("midface-retrusion"),
    "face_shape.heavy": E("face-coarse"), "face_shape.oval-narrow-f": E("face-narrow"),
    "forehead.high": E("hairline-high-anterior"), "forehead.low": E("hairline-low-anterior"), "forehead.bulging": E("forehead-prominent"),
    "forehead.sloping-m": E("forehead-sloping"), "forehead.bossing": E("frontal-bossing"), "forehead.wide": E("forehead-broad"),
    "forehead.narrow": E("forehead-narrow"), "forehead.browridge-m": E("supraorbital-ridges-prominent"),
    "forehead.browridge-f": E("supraorbital-ridges-prominent"), "forehead.dent": E("metopic-depression"),
    "brows.bushy": E("eyebrow-thick") + ["vn_conv:long-may.ram", "tt22:long-may"], "brows.thick-f": E("eyebrow-thick") + ["vn_conv:long-may.ram"],
    "brows.sparse": E("eyebrow-sparse") + ["vn_conv:long-may.thua", "tt22:long-may"], "brows.unibrow": E("synophrys"),
    "brows.flat": E("eyebrow-horizontal") + ["vn_conv:long-may.chu-nhat"], "brows.arched": E("eyebrow-highly-arched"),
    "brows.normal-f": ["vn_conv:long-may.la-lieu", "tt22:long-may"], "brows.upslant": ["vn_conv:long-may.luoi-mac"],
    "brows.long": E("eyebrow-laterally-extended"), "brows.normal-m": ["tt22:long-may", "dvi:eyebrows-distinctive"],
    "eyes.normal": E("palpebral-fissure-almond-shaped") + ["ncic_eye:BRO", "dvi:eyes-colour-brown", "tt22:mat"],
    "eyes.normal-old": ["ncic_eye:BRO", "dvi:eyes-colour-brown", "tt22:mat"],
    "eyes.monolid": ["vn_conv:mat.mot-mi", "tt22:mat"], "eyes.double": ["vn_conv:mat.hai-mi", "tt22:mat"],
    "eyes.innerfold": E("epicanthus"), "eyes.wideset": E("eyes-widely-spaced"), "eyes.closeset": E("eyes-closely-spaced"),
    "eyes.deepset": E("eye-deeply-set"), "eyes.bulging": E("proptosis"), "eyes.upturned": E("palpebral-fissure-upslanted") + ["vn_conv:mat.xech"],
    "eyes.downturned": E("palpebral-fissure-downslanted"), "eyes.ptosis": E("ptosis"), "eyes.puffylid": E("upper-eyelid-fullness-of"),
    "eyes.hooded": E("upper-eyelid-fullness-of"), "eyes.lashes-long": E("eyelashes-long"), "eyes.lashes-sparse": E("eyelashes-sparse"),
    "eyes.small": E("palpebral-fissure-short") + ["vn_conv:mat.nho"], "eyes.large": ["vn_conv:mat.to"],
    "eyes.cross": ["dvi:eyes-cross-eyed", "ncic_smt:CROSSEYED", "vn_conv:mat.lac"], "eyes.wall": ["dvi:eyes-squint-eyed", "vn_conv:mat.lac"],
    "eyes.cataract": ["ncic_smt:CATARACT"], "eyes.blackeyes": ["ncic_eye:BLK", "dvi:eyes-colour-black"],
    "eyes.lightbrown": ["ncic_eye:BRO", "dvi:eyes-colour-brown"], "eyes.blue": ["ncic_eye:BLU", "dvi:eyes-colour-blue"],
    "eyes.greygreen": ["ncic_eye:GRY", "ncic_eye:GRN", "dvi:eyes-colour-grey", "dvi:eyes-colour-green"],
    "eyes.hazel": ["ncic_eye:HAZ", "dvi:eyes-colour-hazel"], "eyes.eu-normal": ["ncic_eye:BRO"], "eyes.af-normal": ["ncic_eye:BRO"],
    "ears.large": E("macrotia"), "ears.protruding": E("ear-protruding"), "ears.cupped": E("ear-cupped"), "ears.lowset": E("ear-low-set"),
    "ears.attached": E("lobe-attached") + ["dvi:ears-lobes-attached", "vn_conv:dai-tai.dinh", "tt22:dai-tai"],
    "ears.longlobes": E("lobe-large") + ["vn_conv:dai-tai.to", "tt22:dai-tai"],
    "ears.thinlobes": E("lobe-small") + ["vn_conv:dai-tai.nho", "tt22:dai-tai"], "ears.narrowlong": E("ear-long"),
    "ears.wideshort": E("ear-short"), "ears.pointed": E("satyr-ear"), "ears.flathelix": E("helix-underfolded"),
    "ears.torn": E("lobe-cleft"), "ears.cauliflower": ["ncic_smt:CAUL EAR"], "ears.pierced-f": ["dvi:ears-pierced", "ncic_smt:PRCD EARS"],
    "ears.normal": ["tt22:dai-tai"],
    "nose.normal": ["vn_conv:song-mui.thap", "tt22:song-mui"], "nose.flat": E("nasal-bridge-depressed", "nose-wide") + ["vn_conv:mui.to-be"],
    "nose.highbridge": E("nasal-bridge-prominent") + ["vn_conv:song-mui.cao", "tt22:song-mui"],
    "nose.hooked": E("nasal-ridge-convex"), "nose.bump": E("nasal-ridge-convex") + ["vn_conv:song-mui.go"],
    "nose.bulbous": E("nose-bulbous", "nasal-tip-broad"), "nose.upturned": E("nares-anteverted"), "nose.droop": E("nasal-tip-overhanging"),
    "nose.pinched": E("nose-narrow", "naris-narrow"), "nose.slim": E("nose-narrow"), "nose.flaring": E("naris-enlarged", "nasal-base-wide"),
    "nose.large": E("nose-prominent"), "nose.small": E("nose-short"), "nose.long": E("nose-long") + ["vn_conv:song-mui.thang"],
    "nose.saddle": E("nasal-ridge-depressed"), "nose.crooked": E("nasal-tip-deviated") + ["vn_conv:song-mui.gay", "ncic_smt:HFR NOSE"],
    "nose.button": E("nose-short"),
    "mouth.wide": E("mouth-wide"), "mouth.small": E("mouth-narrow"),
    "mouth.full": E("vermilion-upper-lip-thick", "vermilion-lower-lip-thick"),
    "mouth.thin": E("vermilion-upper-lip-thin", "vermilion-lower-lip-thin"), "mouth.thinupper": E("vermilion-upper-lip-thin"),
    "mouth.downturned": E("mouth-downturned-corners-of"), "mouth.upturned": E("mouth-upturned-corners-of"),
    "mouth.bow": E("cupid-s-bow-exaggerated"), "mouth.flatlip": E("cupid-s-bow-absent"), "mouth.droopylower": E("vermilion-lower-lip-everted"),
    "mouth.longupper": E("philtrum-long"), "mouth.protruding": E("premaxillary-prominence"),
    "teeth.gap": E("diastema"), "teeth.crowded": E("dental-crowding"), "teeth.large": E("macrodontia"), "teeth.small": E("microdontia"),
    "teeth.toothless": ["ncic_smt:NO TEETH"], "teeth.fewleft": ["ncic_smt:MISS TEETH"], "teeth.normal-e": ["ncic_smt:MISS TEETH"],
    "teeth.missingfront": ["ncic_smt:MISS TEETH"], "teeth.dentures": ["ncic_smt:DENT UP"],
    "jaw_chin.square": E("jaw-broad"), "jaw_chin.flared": E("jaw-broad"), "jaw_chin.pointed": E("chin-pointed"),
    "jaw_chin.receding": E("retrognathia"), "jaw_chin.underjaw": E("prognathism") + ["ncic_smt:PROT JAW"],
    "jaw_chin.cleft": E("chin-vertical-crease") + ["ncic_smt:CLEFT CHIN"], "jaw_chin.chindimple": E("chin-dimple") + ["ncic_smt:DIMP CHIN"],
    "jaw_chin.wideshort": E("chin-broad", "chin-short"), "jaw_chin.long": E("chin-tall"), "jaw_chin.delicate": E("jaw-narrow"),
    "cheeks.highbones": E("cheekbone-prominence"), "cheeks.widebones": E("malar-prominence"), "cheeks.flat": E("malar-flattening"),
    "cheeks.hollow": E("cheeks-sunken"), "cheeks.chubby": E("cheeks-full"), "cheeks.dimples": ["ncic_smt:DIMP CHEEK"],
    "cheeks.onedimple": ["ncic_smt:DIMP CHEEK"], "cheeks.lowbones": E("cheekbone-underdevelopment"),
    "neck.short": E("neck-short"), "neck.long": E("neck-long"), "neck.swan-f": E("neck-long"), "neck.bull-m": E("neck-broad"),
    "neck.wide-m": E("neck-broad"), "neck.goiter": ["ncic_smt:MC THYROID"],
    "hair_texture.cowlick": E("hair-frontal-upsweep"), "hair_texture.doublecrown": E("hair-whorl-abnormal-position"),
    "hair_texture.normal": ["vn_conv:toc.den-thang", "tt22:toc"], "hair_texture.curly": ["vn_conv:toc.xoan"],
    "hair_texture.wavy": ["vn_conv:toc.xoan"],
    "hairline.peak": E("widow-s-peak"), "hairline.low": E("hairline-low-anterior"), "hairline.high": E("hairline-high-anterior"),
    "hairline.top-m": E("frontal-balding") + ["dvi:420-baldness-partial", "ncic_smt:BALD", "vn_conv:toc.hoi"],
    "hairline.fullbald-m": ["dvi:420-baldness-total", "ncic_smt:BALD", "ncic_hair:XXX", "vn_conv:toc.hoi"],
    "hairline.crown-m": ["dvi:420-baldness-tonsure", "ncic_smt:BALD"], "hairline.forelock-m": ["dvi:420-baldness-partial", "ncic_smt:BALD"],
    "hairline.mshape-m": ["dvi:420-baldness-forehead"], "hairline.earlyrecede-m": ["dvi:420-baldness-forehead"],
    "hairline.normal-old-m": ["dvi:420-baldness-forehead"], "hairline.bald-f": ["dvi:420-baldness-partial", "ncic_smt:BALD"],
    "hair_color.normal-y": ["ncic_hair:BLK", "dvi:420-hair-colour-black", "tt22:toc"], "hair_color.jet": ["ncic_hair:BLK", "dvi:420-hair-colour-black"],
    "hair_color.normal-m": ["ncic_hair:GRY", "dvi:420-hair-colour-mixed-grey", "tt22:toc"],
    "hair_color.normal-e": ["ncic_hair:GRY", "dvi:420-hair-colour-grey", "vn_conv:toc.hoa-ram"],
    "hair_color.saltpepper": ["ncic_hair:GRY", "dvi:420-hair-colour-mixed-grey", "vn_conv:toc.hoa-ram"],
    "hair_color.irongrey": ["ncic_hair:GRY", "dvi:420-hair-colour-grey"], "hair_color.white": ["ncic_hair:WHI", "dvi:420-hair-colour-white", "vn_conv:toc.bac-trang"],
    "hair_color.yellowwhite": ["ncic_hair:WHI", "dvi:420-hair-colour-white"], "hair_color.brownblack": ["ncic_hair:BRO", "dvi:420-hair-colour-brown"],
    "hair_color.lightbrown": ["ncic_hair:BRO", "dvi:420-hair-colour-brown"], "hair_color.dullbrown": ["ncic_hair:BRO", "dvi:420-hair-colour-brown"],
    "hair_color.eu-normal": ["ncic_hair:BRO", "dvi:420-hair-colour-brown"], "hair_color.blond": ["ncic_hair:BLN", "dvi:420-hair-colour-blond"],
    "hair_color.red": ["ncic_hair:RED", "dvi:420-hair-colour-red"], "hair_color.reddish": ["ncic_hair:RED"],
    "hair_color.premature": ["ncic_hair:GRY"], "hair_color.temples": ["ncic_hair:GRY"],
    "skin_tone.normal-m": ["ncic_skin:LBR", "tt22:mau-da", "vn_conv:mau-da.vang"], "skin_tone.normal-f": ["ncic_skin:FAR", "ncic_skin:YEL", "tt22:mau-da", "vn_conv:mau-da.trang"],
    "skin_tone.pale": ["ncic_skin:LGT", "vn_conv:mau-da.trang"], "skin_tone.fair": ["ncic_skin:FAR", "ncic_skin:YEL", "vn_conv:mau-da.trang"],
    "skin_tone.olive": ["ncic_skin:OLV", "vn_conv:mau-da.ngam"], "skin_tone.golden": ["ncic_skin:MBR", "vn_conv:mau-da.ngam"],
    "skin_tone.deeptan": ["ncic_skin:DBR", "vn_conv:mau-da.ngam-den"], "skin_tone.darkbrown": ["ncic_skin:DBR", "ncic_skin:DRK", "vn_conv:mau-da.den"],
    "skin_tone.sallow": ["ncic_skin:SAL"], "skin_tone.ruddy": ["ncic_skin:RUD"], "skin_tone.verydark": ["ncic_skin:BLK", "ncic_skin:DRK"],
    "skin_tone.eu-normal": ["ncic_skin:LGT", "ncic_skin:FAR"], "skin_tone.af-normal": ["ncic_skin:DBR", "ncic_skin:BLK"],
    "skin_tone.reddens": ["ncic_skin:FAR", "ncic_skin:RUD"], "skin_tone.farmertan": ["ncic_skin:MBR"],
    "skin_texture.pox": ["ncic_smt:POCKMARKS"], "skin_texture.freckles": ["ncic_smt:FRECKLES"], "skin_texture.acne": ["ncic_smt:MC ACNE"],
    "skin_texture.eczema": ["ncic_smt:MC SKIN"], "body_skin.psoriasis-m": ["ncic_smt:MC SKIN"],
    "facial_hair.normal-m": ["dvi:facial-hair-shaved"], "facial_hair.hairless-m": ["dvi:facial-hair-shaved"],
    "facial_hair.wispy-m": ["dvi:facial-hair-moustache"], "facial_hair.goatee-m": ["dvi:facial-hair-goatee"],
    "facial_hair.full-m": ["dvi:facial-hair-full-beard"], "facial_hair.whitebeard-m": ["dvi:facial-hair-full-beard"],
    "facial_hair.sideburns-m": ["dvi:facial-hair-whiskers"], "facial_hair.stubble-m": ["dvi:facial-hair-whiskers"],
    "frame.small-m": ["dvi:416-build-slight"], "frame.small-f": ["dvi:416-build-slight"], "frame.narrow-m": ["dvi:416-build-slight"],
    "frame.narrow-f": ["dvi:416-build-slight"], "frame.normal-m": ["dvi:416-build-medium"], "frame.normal-f": ["dvi:416-build-medium"],
    "frame.broad-m": ["dvi:416-build-large"], "frame.broad-f": ["dvi:416-build-large"], "frame.stocky-m": ["dvi:416-build-large"],
    "frame.sturdy-f": ["dvi:416-build-large"], "frame.barrel-m": ["dvi:416-build-large"],
    "hands.long-fingers": E("fingers-long"), "hands.stubby": E("finger-short"), "hands.clubbed": E("clubbing"), "hands.small": E("hand-small"),
    "hands.square-m": E("palm-broad"), "hands.crooked": E("clinodactyly"), "hands.dupuytren": E("camptodactyly"),
    "hands.arthritic": ["ncic_smt:MC ARTHRTS"],
    "feet.flat": E("pes-planus"), "feet.wide-flat": E("pes-planus", "foot-broad"), "feet.high-arch": E("pes-cavus"),
    "feet.hammer": E("hammertoe"), "feet.splayed": E("toes-splayed"), "feet.broad-m": E("foot-broad"), "feet.large": E("foot-long"),
    "feet.small": E("foot-short"), "feet.long-toe": E("toe-long"),
    "nails.spoon": E("nail-concave"), "nails.ridged": E("nail-ridged"), "nails.thick-yellow": E("nail-thick"),
    "legs.wasted-m": ["ncic_smt:CRIP LEG"], "legs.bow-m": ["dvi:404-malformations"], "legs.bow-f": ["dvi:404-malformations"],
    "back.scoliosis": ["dvi:404-malformations"], "mouth.lopsided": ["dvi:lips-distinctive"],
    "marks.none": ["dvi:404-skin-marks"], "marks.tracks": ["ncic_smt:NM ARM"],
}
for vid, terms in MAP.items():
    set_std(vid, terms)
for vid in STD["marks_codes"]:
    k = V(vid)
    kind = ("dvi:404-tattoos" if "tattoo" in vid else "dvi:404-amputations" if vid in ("marks.legloss", "marks.armloss", "marks.fingerstump",
            "marks.fingertip", "marks.eyeloss") else "dvi:404-scars" if any(w in k["phrase"] for w in ("scar", "notch", "pitted"))
            else "dvi:404-skin-marks")
    set_std(vid, [kind])

save_cat(CAT)

# ------------------------------------------------------------------ 7. vocab.json
vp = KB / "vocab.json"
vocab = json.loads(vp.read_text(encoding="utf-8"))
vocab["baseline_facets"] = ["life", "place"]
ck = vocab["cause_keywords"]
BOAT = r"(on|in|aboard) (the |a |his |her |their |big |small |fishing )*boats?\b"
ck["water-work"] = (r"\b(at sea|to sea|out to sea|on the sea|fish(ing|ed|es|erman|ermen)?\b|nets?\b|squid|" + BOAT +
                    r"|rivers?\b|paddy|paddies|rice fields?|transplant\w*|washing|laundry|div(ing|er)\b)")
ck["sun"] = (r"\b(at sea|to sea|out to sea|fish(ing|ed|erman|ermen)?\b|" + BOAT + r"|farm\w*|fields?\b|paddy|paddies|"
             r"sun\w*|outdoors?|in the open|market stall|street vend\w*|construction|building site|herd\w*)")
ck["manual-labour"] = (r"\b(haul\w*|carr(y|ied|ies|ying)|labou?r\w*|farm\w*|build(ing|er|ers)\b|construct\w*|porter|"
                       r"fish(ing|ed|erman|ermen)?\b|at sea|to sea|nets?\b|" + BOAT + r"|heavy work|plough\w*|dig(s|ging)?\b|"
                       r"factory|mine\b|mines\b|quarry|load(s|ing)?\b)")
ck["childbearing"] = (r"\b(gave birth|giving birth|give birth|pregnan\w*|childbirth|miscarr\w*|breast-?fe\w*|"
                      r"bore (a|her|him|two|three|four|five|six|seven)\b|had (a|her|their) (first |second |third )?(baby|son|daughter|child)|"
                      r"raised (two|three|four|five|six|seven|\d+) children|mother of)")
vocab["cause_only_sex"] = {"childbearing": "female"}
vocab["cite"]["claim_causes"] = ["injury", "illness", "alcohol", "substances", "childbearing", "weight-loss"]
vocab["cite"]["facet_causes"] = {"smoker": ["substances"], "drinks": ["alcohol"], "heavy-drinker": ["alcohol"],
                                 "poor": ["poverty"], "destitute": ["poverty"], "underfed": ["poverty"], "overfed": ["diet"],
                                 "well-fed": ["diet"], "sea": ["water-work", "sun", "manual-labour"],
                                 "farm": ["sun", "manual-labour", "water-work"], "outdoor-manual": ["sun", "manual-labour"],
                                 "street": ["sun"], "military": ["sun", "manual-labour"], "office": ["sedentary"]}
vocab["cite"]["note"] = ("rare or notable picks need a cite 'LIFE <n>', 'IDENTITY <field>' or (soul slots) 'SOUL'. The cited item "
                         "must carry one of the value's causes: LIFE items carry causes read from their event text (not the "
                         "Interpretation); IDENTITY Age carries ageing/hormones (45+) or youth (<30); Nationality/Hometown carry "
                         "genetics/climate; SOUL carries temperament/stress/low-mood. A reason text may not claim a specific "
                         "cause (claim_causes) that the cited item and the facets (facet_causes) do not show.")
SLOT_STD = {"height": ["dvi:408-height", "tt22:chieu-cao"], "frame": ["dvi:416-build-medium"], "fat": ["dvi:412-weight"],
            "skin_tone": ["tt22:mau-da"], "hair_color": ["tt22:toc"], "hair_texture": ["tt22:toc"], "hairline": ["dvi:420-hair-distinctive"],
            "brows": ["tt22:long-may", "dvi:eyebrows-distinctive"], "nose": ["tt22:song-mui", "dvi:nose-distinctive"],
            "ears": ["tt22:dai-tai", "dvi:ears-distinctive"], "eyes": ["tt22:mat"], "mouth": ["dvi:lips-distinctive"],
            "teeth": ["dvi:mouth-teeth-distinctive"], "jaw_chin": ["dvi:chin-distinctive"], "neck": ["dvi:neck-distinctive"],
            "hands": ["dvi:hands-nails-distinctive"], "nails": ["dvi:hands-nails-distinctive"], "feet": ["dvi:feet-nails-distinctive"],
            "body_skin": ["dvi:body-hair-distinctive"], "marks": ["dvi:404-scars", "dvi:404-skin-marks", "dvi:404-tattoos",
                                                                 "dvi:404-amputations", "tt22:dac-diem-khac"],
            "facial_hair": ["dvi:facial-hair-shaved"]}
for s, t in SLOT_STD.items():
    vocab["slots"][s]["std"] = t
vp.write_text(json.dumps(vocab, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

# ------------------------------------------------------------------ 8. evidence cards
H = ST["height"]["by"]


def hb(k):
    return H[k]["mean"]


def bm(sex, band, cats):
    return round(100 * sum(BMI[f"kinh/{sex}/2024/{band}"][c] for c in cats), 1)


A = ST["ansur"]["by"]
M = ST["maad"]["share"]
CARDS = {
    "ncdrisc.jsonl": [
        {"id": "ncd.h.vn", "source": "ncdrisc_height", "kind": "stat", "num": "num/ncdrisc_height_adult.csv; num/ncdrisc_height_age19.csv; num/height_bands.csv",
         "text": (f"Viet Nam mean adult height by birth decade: men {hb('kinh/male/1930')} (1930s), {hb('kinh/male/1950')} (1950s), "
                  f"{hb('kinh/male/1970')} (1970s), {hb('kinh/male/1990')} (1990s), {hb('kinh/male/2000')} cm (2000); women "
                  f"{hb('kinh/female/1930')}, {hb('kinh/female/1950')}, {hb('kinh/female/1970')}, {hb('kinh/female/1990')}, "
                  f"{hb('kinh/female/2000')} cm. SEA neighbours (unweighted) men 1950s {hb('sea-asian/male/1950')}, 2000 "
                  f"{hb('sea-asian/male/2000')}. Cohort 2000 = age-19 height 2019 (Lancet 2020) shifted by the 1987-1996 overlap "
                  f"offset to the eLife 2016 series (VN men {ST['height']['src']['offset_1997_2000']['VNM/male']} cm)."),
         "loc": "eLife 2016 adult height by year of birth (rows VNM 1896-1996); Lancet 2020 age 19 (rows Viet Nam 1985-2019)"},
        {"id": "ncd.h.sd", "source": "ansur2", "kind": "proxy", "num": "num/ansur_corr.csv",
         "text": f"Within-population height SD used for z bands: men {ST['height']['sd']['male']} cm, women {ST['height']['sd']['female']} cm. {ST['height']['sd_note']}.",
         "loc": "ANSUR II public CSV stature columns; STEPS VN 2015 Table 83 / 2021 Table A25 CIs"},
        {"id": "ncd.bmi.vn", "source": "ncdrisc_bmi", "kind": "stat", "num": "num/ncdrisc_bmi_vn.csv",
         "text": (f"Viet Nam 2024 BMI classes (share, mean of 5-year age groups): men 18-29 <18.5 {bm('male','young',['lt18.5'])}%, "
                  f"25-30 {bm('male','young',['25-30'])}%, >=30 {bm('male','young',['30-35','35-40','ge40'])}%; men 65+ <18.5 "
                  f"{bm('male','elderly',['lt18.5'])}%, 25-30 {bm('male','elderly',['25-30'])}%; women 45-64 <18.5 "
                  f"{bm('female','middle',['lt18.5'])}%, 25-30 {bm('female','middle',['25-30'])}%, >=30 "
                  f"{bm('female','middle',['30-35','35-40','ge40'])}%."),
         "loc": "NCD-RisC Nature 2026 age-specific country CSVs, rows VNM 2024"},
    ],
    "who_steps_vn.jsonl": [
        {"id": "steps.bmi", "source": "who_steps_vn_2021", "kind": "stat", "num": "num/steps_vn.csv",
         "text": ("Measured adults 18-69, 2021: underweight men 11.6/6.9/10.3% (18-29/30-49/50-69), women 20.8/5.3/6.3%; "
                  "overweight 25-29.9 men 11.6/19.2/19.8%, women 14.3/16.2/22.7%; obese >=30 about 2%. Mean BMI 22.4 men, 22.5 women."),
         "loc": "STEPS VN 2021 Table 32 (pdf p46), Table A26 (p85)"},
        {"id": "steps.height", "source": "who_steps_vn_2021", "kind": "stat", "num": "num/steps_vn.csv",
         "text": ("Measured height 2021: men 165.8/164.1/161.9 cm (18-29/30-49/50-69), women 155.0/153.2/152.0 cm; 2015: men "
                  "163.7/162.0/161.4, women 154.2/152.5/150.9. Agrees with NCD-RisC cohort means within ~1 cm."),
         "loc": "STEPS VN 2021 Table A25 (p85); STEPS VN 2015 annex Table 83 (p105)"},
        {"id": "steps.waist", "source": "who_steps_vn_2021", "kind": "stat", "num": "num/steps_vn.csv",
         "text": ("Waist 2021: men 77.8/81.2/81.7 cm, women 72.8/76.2/81.0 cm (18-29/30-49/50-69); over cut-off (90 men / 85 women) "
                  "men 8.6/16.6/18.6%, women 11.4/15.1/33.3%."),
         "loc": "STEPS VN 2021 Table A27 (p86)"},
        {"id": "steps.ur", "source": "who_steps_vn_2015", "kind": "stat", "num": "num/steps_vn.csv",
         "text": ("Urban vs rural: BMI >= 25 2015 men 22.1 vs 11.2%, women 20.6 vs 14.0%; 2021 both sexes 24.2 vs 16.7%. "
                  "Underweight 2015 men 9.3 vs 11.4%, women 9.6 vs 14.2%. Waist 2015 men 80.4 vs 76.5 cm."),
         "loc": "STEPS VN 2015 Tables 41, 89, 91 (p60, p107, p109); STEPS VN 2021 Table 55 (p61)"},
    ],
    "kinh_face_papers.jsonl": [
        {"id": "kf.head", "source": "kinh_face_tcncyh_2023", "kind": "stat", "num": "num/kinh_face.csv",
         "text": "Cephalic index, Kinh 18-25: very short (>86) men 40.3% women 44.7%; short 33.9/36.8%; medium 21.6/14.9%; long+very long 4.2/3.6%.",
         "loc": "TCNCYH 162(1) 2023, Bang 2 (pdf p5)"},
        {"id": "kf.face", "source": "kinh_face_tcncyh_2023", "kind": "stat", "num": "num/kinh_face.csv",
         "text": "Total facial index: very wide (<80) men 44.9% women 26.5%; wide 36.1/30.0%; medium 13.1/32.7%; long 3.9/8.1%; very long 2.1/2.7%.",
         "loc": "TCNCYH 2023, Bang 3 (pdf p5)"},
        {"id": "kf.nose", "source": "kinh_face_tcncyh_2023", "kind": "stat", "num": "num/kinh_face.csv",
         "text": "Nasal index: narrow (55-70) men 9% women 26%; medium 43/46%; wide (85-100) 35.6/21%; very wide 9.5/4.6%; hyper wide 2.9/1.3%; very narrow 0.03/0.95%.",
         "loc": "TCNCYH 2023, Bang 4 (pdf p5)"},
        {"id": "kf.prog", "source": "kinh_face_tcncyh_2023", "kind": "stat", "num": "num/kinh_face.csv",
         "text": "Prognathism index: none men 91.1% women 87.2%; prognathic 6.2/6.4%; very prognathic 2.7/6.4%.",
         "loc": "TCNCYH 2023, Bang 5 (pdf p6)"},
        {"id": "kf.mand", "source": "kinh_face_tcncyh_2023", "kind": "stat", "num": "num/kinh_face.csv",
         "text": "Mandibular index (gonial / face width): wide men 92.9% women 98.4%; narrow 4.4/0.5%. Narrow jaws are rare in Kinh women.",
         "loc": "TCNCYH 2023, Bang 6 (pdf p6)"},
        {"id": "kf.meas", "source": "kinh_face_tcncyh_2023", "kind": "stat", "num": "num/kinh_face.csv",
         "text": ("Mean sizes men/women (mm): face width 138.6/131.2, nose width 40.8/37.5, mouth width 50.4/48.3, eye width 31.6/30.8, "
                  "intercanthal 35.2/34.2, ear length 59.2/55.7, forehead height 72.2/68.1."),
         "loc": "TCNCYH 2023, Bang 1 (pdf p3-4)"},
        {"id": "kf.celebie", "source": "kinh_face_vmj_2021", "kind": "stat", "num": "num/kinh_face.csv",
         "text": "Face outline (Celebie-Jerolimov, photos), Kinh 18-25 Binh Duong, n 2462: oval 66.3%, square 26.6%, triangular 7.1%.",
         "loc": "Tap chi Y hoc VN 502(1) 2021, Bieu do 3.2 and Bang 3.1 (pdf p2)"},
    ],
    "maad_face.jsonl": [
        {"id": "maad.marg", "source": "maad_face", "kind": "proxy", "num": "num/maad_marginals.csv",
         "text": (f"PROXY, celebrity photos with classifier labels ({ST['maad']['identities']} identities, {ST['maad']['asian_identities']} "
                  f"labelled Asian). Asian men: bushy brows {M['male/all/Asian']['Bushy_Eyebrows']}, big nose {M['male/all/Asian']['Big_Nose']}, "
                  f"double chin {M['male/all/Asian']['Double_Chin']}, high cheekbones {M['male/all/Asian']['High_Cheekbones']}; Asian women: "
                  f"high cheekbones {M['female/all/Asian']['High_Cheekbones']}, round face {M['female/all/Asian']['Round_Face']}. Labels are "
                  f"sex-stereotyped (square face {M['male/all/all']['Square_Face']} of men, oval {M['female/all/all']['Oval_Face']} of women): "
                  f"never a Vietnamese frequency."),
         "loc": "MAAD_Face.csv streamed, identity-level majority labels"},
        {"id": "maad.cooc", "source": "maad_face", "kind": "proxy", "num": "num/maad_cooc.csv",
         "text": ("PROXY co-occurrence: oval face with double chin lift 0.01, oval face with chubby 0.0 (narrow oval faces are not "
                  "fat faces) -> rule R0013; most other low-lift pairs are label artefacts (blond vs big nose)."),
         "loc": "maad_cooc.csv subset all, lift < 0.25"},
    ],
    "ansur2.jsonl": [
        {"id": "ansur.frame", "source": "ansur2", "kind": "proxy", "num": "num/ansur_corr.csv",
         "text": (f"PROXY, US Army 2012 (n {A['male']['n']} men, {A['female']['n']} women): stature vs shoulder (biacromial) breadth r "
                  f"{A['male']['r']['stature~biacromialbreadth']}/{A['female']['r']['stature~biacromialbreadth']}, vs wrist "
                  f"{A['male']['r']['stature~wristcircumference']}/{A['female']['r']['stature~wristcircumference']}; top-tenth shoulders "
                  f"among the shortest tenth {A['male']['conditional']['P(shoulders z>=1.28 | stature z<-1.28)']} vs 0.10 overall."),
         "loc": "ANSUR II public CSVs"},
        {"id": "ansur.bmi", "source": "ansur2", "kind": "proxy", "num": "num/ansur_corr.csv",
         "text": (f"PROXY: BMI vs waist r {A['male']['r']['bmi~waistcircumference']} men / {A['female']['r']['bmi~waistcircumference']} women; "
                  f"stature vs BMI r {A['male']['r']['stature~bmi']} (height says nothing about fatness); taller people have relatively "
                  f"longer legs (stature vs sitting/stature r {A['male']['r']['stature~sitting_ratio']})."),
         "loc": "ANSUR II public CSVs"},
    ],
    "vocab_standards.jsonl": [
        {"id": "std.vocab", "source": "nih_eom", "kind": "vocab", "text": "Standard morphology terms (labels) used to name new face, ear, nose and hand values; see standards.json.",
         "loc": "06_nih_elements_morphology term pages"},
        {"id": "std.skin", "source": "ncic_codes", "kind": "vocab",
         "text": "NCIC skin tone codes (LGT, FAR, YEL, LBR, MBR, OLV, DBR, DRK, RUD, SAL, BLK) give the closed skin-colour scale the tones map to; sun exposure moves Vietnamese outdoor workers from LBR/FAR to MBR/DBR.",
         "loc": "ecfr_ncic_SKIN_entries.json"},
        {"id": "std.dvi", "source": "interpol_dvi_am_2023", "kind": "vocab", "text": "Interpol DVI AM body description fields 404-476 (build slight/medium/large, hair colour and baldness types, eye colours and distinctive features, facial hair types, attached/pierced lobes, specific details by body region).",
         "loc": "AM2023 form pdf p6-7"},
        {"id": "std.tt22", "source": "tt22_2014", "kind": "vocab", "text": "Wanted-notice template (mau 30a/30b QD) 'Dac diem nhan dang': chieu cao, mau da, toc, long may, song mui, dai tai, mat, dac diem khac.",
         "loc": "tvpl_mau30aQD html"},
    ],
}
for fn, cards in CARDS.items():
    (KB / "evidence" / fn).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards), encoding="utf-8")

# ------------------------------------------------------------------ 9. sources.jsonl
RAW = "C:/Users/khoa/data/nhan_vat_sources/"
NEWSRC = [
    ("ncdrisc_height", "dataset", "NCD-RisC adult height by birth year (eLife 2016) + child/adolescent height (Lancet 2020)", "01_ncdrisc",
     "free download, no registration; site states (c) NCD-RisC all rights reserved, papers open access; numbers used as facts for private research"),
    ("ncdrisc_bmi", "dataset", "NCD-RisC BMI by age and sex, country (Nature 2026)", "01_ncdrisc", "free download, as above"),
    ("who_steps_vn_2021", "report", "National survey on NCD risk factors Viet Nam 2021 (WHO STEPS)", "02_who_steps_vn", "CC BY-NC-SA 3.0 IGO"),
    ("who_steps_vn_2015", "report", "WHO STEPS Viet Nam 2015 report", "02_who_steps_vn", "free WHO report (no licence line found); numbers cited with table/page"),
    ("kinh_face_tcncyh_2023", "paper", "Chu Van Tue Binh, Nguyen Duc Nghia: head-face sizes and indices of Kinh 18-25, TCNCYH 162(1) 2023",
     "03_kinh_face_papers", "free journal PDF; numbers cited with table/page"),
    ("kinh_face_vmj_2021", "paper", "Vo Truong Nhu Ngoc, Nguyen Huu Huynh: face sizes by face shape, Kinh 18-25 Binh Duong, Tap chi Y hoc VN 502(1) 2021",
     "03_kinh_face_papers", "free journal PDF (vnras.com repost); numbers cited with table/page"),
    ("interpol_dvi_am_2023", "form", "Interpol DVI Ante-Mortem form 2023", "04_interpol_dvi", "public form, free download; field names only"),
    ("tt22_2014", "law", "Thong tu 22/2014/TT-BCA, mau 30a/30b QD (truy na)", "05_tt22_2014_bca", "public legal text; field names only"),
    ("nih_eom", "glossary", "NIH/NHGRI Elements of Morphology: Human Malformation Terminology", "06_nih_elements_morphology",
     "free web pages (Wiley 2009 papers); labels only, definitions not copied"),
    ("ncic_codes", "codes", "NCIC code manual tables SMT, EYE, HAIR, SKIN (ecfr.io NIEM 5.2 snapshot)", "09_ncic_smt_namus", "US government code tables, public"),
    ("maad_face", "dataset", "MAAD-Face attribute labels for VGGFace2 (CSV)", "10_maad_face", "CC BY-SA 4.0; labels only, no images; PROXY"),
    ("ansur2", "dataset", "ANSUR II public anthropometric data (US Army 2012)", "08_ansur2", "cleared for unlimited public release; PROXY"),
    ("aist_1991", "dataset", "AIST Japanese body dimensions 1991-92", "07_aist_1991-92",
     "tables are GIF images only and no reproduction without permission: skipped"),
]
srcs = [json.loads(x) for x in (KB / "sources.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
have = {s["id"] for s in srcs}
ncards = {}
for cards in CARDS.values():
    for c in cards:
        ncards[c["source"]] = ncards.get(c["source"], 0) + 1
for sid, kind, title, d, terms in NEWSRC:
    row = {"id": sid, "kind": kind, "title": title, "license_needed": False, "terms": terms, "retrieved": "2026-11-24",
           "raw": RAW + d, "manifest": RAW + "manifest.jsonl", "n_cards": ncards.get(sid, 0),
           "status": "skipped" if sid == "aist_1991" else "active"}
    if sid in have:
        srcs = [row if s["id"] == sid else s for s in srcs]
    else:
        srcs.append(row)
(KB / "sources.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in srcs), encoding="utf-8")

# ------------------------------------------------------------------ 10. vi glosses
VI = {"head.oval": "đầu hình bầu dục, dài vừa trước sau", "nose.slim": "mũi hẹp, cánh mũi thon",
      "eyes.glasseye": "một mắt giả, đứng yên vô hồn", "ears.lobecrease": "nếp gấp chéo trên dái tai",
      "ears.darwin": "u nhỏ trên vành tai", "ears.pit": "lỗ rò nhỏ trước tai", "ears.tag": "mẩu thịt thừa trước tai",
      "hands.extrafinger": "ngón thừa nhỏ cạnh ngón cái", "hands.webbed": "hai ngón dính nhau bằng da",
      "hands.claw": "một bàn tay co cứng, ngón quặp", "legs.oneshort": "một chân ngắn hơn, hông lệch bên đó",
      "feet.sandalgap": "kẽ rộng giữa ngón cái và ngón hai",
      "height.tall-m": "đàn ông cao, cao hơn phần lớn đàn ông", "height.very-tall-m": "đàn ông rất cao, lêu nghêu, vượt hẳn mọi người",
      "jaw_chin.normal-f": "hàm tròn mềm, cằm nhỏ tròn"}
vip = KB / "vi.jsonl"
vrows = [json.loads(x) for x in vip.read_text(encoding="utf-8").splitlines() if x.strip()]
vids = {r["id"] for r in vrows}
for r in vrows:
    if r["id"] in VI:
        r["vi"] = VI[r["id"]]
for k, t in VI.items():
    if k not in vids:
        vrows.append({"id": k, "vi": t})
vip.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in vrows), encoding="utf-8")

# ------------------------------------------------------------------ 11. rules
rp = KB / "rules.jsonl"
rules = [json.loads(x) for x in rp.read_text(encoding="utf-8").splitlines() if x.strip()]
cm = A["male"]["conditional"]
cf = A["female"]["conditional"]
NEWR = [
    {"id": "R0013", "kind": "exclude", "a": "face_shape.oval-narrow-f", "b": ["jaw_chin.double", "jaw_chin.lost", "jaw_chin.heavy"],
     "why": "a narrow oval face with a pointed chin has no soft double chin", "status": "active", "since": 4, "basis": "proxy",
     "ev": "maad.cooc"},
    {"id": "H0001", "kind": "hint", "a": "height.very-short-m", "b": ["shoulders.very-broad-m", "shoulders.broad-m"],
     "why": "very short men rarely have broad shoulders", "p": cm["P(shoulders z>=1.28 | stature z<-1.28)"], "basis": "proxy",
     "status": "active", "since": 4, "ev": "ansur.frame"},
    {"id": "H0002", "kind": "hint", "a": "height.very-short-m", "b": ["frame.broad-m"], "why": "very short men rarely have heavy bones and thick wrists",
     "p": cm["P(wrist z>=1.28 | stature z<-1.28)"], "basis": "proxy", "status": "active", "since": 4, "ev": "ansur.frame"},
    {"id": "H0003", "kind": "hint", "a": "height.very-tall-m", "b": ["shoulders.narrow-m"], "why": "very tall men rarely have narrow shoulders",
     "p": cm["P(shoulders z<-1.28 | stature z>=1.28)"], "basis": "proxy", "status": "active", "since": 4, "ev": "ansur.frame"},
    {"id": "H0004", "kind": "hint", "a": "height.very-short-f", "b": ["shoulders.broad-f", "frame.broad-f"],
     "why": "very short women rarely have broad shoulders or heavy bones", "p": cf["P(shoulders z>=1.28 | stature z<-1.28)"],
     "basis": "proxy", "status": "active", "since": 4, "ev": "ansur.frame"},
    {"id": "H0005", "kind": "hint", "a": "height.very-short-m", "b": ["legs.long-m"], "why": "short people have relatively short legs",
     "basis": "proxy", "status": "active", "since": 4, "ev": "ansur.bmi"},
    {"id": "H0006", "kind": "hint", "a": "height.very-tall-m", "b": ["legs.short-m"], "why": "tall people have relatively long legs",
     "basis": "proxy", "status": "active", "since": 4, "ev": "ansur.bmi"},
]
rid = {r["id"]: i for i, r in enumerate(rules)}
for r in NEWR:
    if r["id"] in rid:
        rules[rid[r["id"]]] = r
    else:
        rules.append(r)
rp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rules), encoding="utf-8")
print("catalog, vocab, evidence, sources, vi, rules updated")
