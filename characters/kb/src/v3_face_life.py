"""One-off v2 -> v3 step (kept as history, like migrate_v2.py). Run from anywhere:

    python -I src/v3_face_life.py

1. vocab.json: new slots (groups B face, C natural hair, H marks), prompt order A B C D E F G H, face regions,
   dims lines/scalp/grey/teeth, life facets + keyword tables (means, life, diet, alcohol, smoke, place, era, eth),
   cite rules, mark locations.
2. catalog/<slot>.jsonl for the 24 new slots from src/face_bch.txt (overwritten; ids are new in v3).
3. needs/fit on every body value, derived from its causes (+ a few overrides), written into catalog.
4. evidence/<source>_pf.jsonl: cards cited by the new values, copied from ebook_maker work/_skill_trial/kb/character-portrait/
   cards.jsonl (the card set behind the character-portrait skill's sources.jsonl; ids prefixed "pf." because the build1
   lane used for body cards reuses the same k-numbers for other cards).
5. vi.jsonl glosses, sources.jsonl entries.
After this, catalog/*.jsonl is the source of truth again; do not rerun once ids are locked (it would rewrite catalog).
"""
import json
import re
from pathlib import Path

KB = Path(__file__).resolve().parents[1]
EBM = Path(r"C:/Users/khoa/code_nha/ebook_maker")
SKILL = EBM / "skills/character-portrait/character-portrait-prompt"
LANE = EBM / "work/_skill_trial/kb/character-portrait/cards.jsonl"   # merged cards; matches skill sources.jsonl (cid, h)

AG = {"Y": (18, 29), "A": (30, 44), "M": (45, 64), "E": (65, 120)}
BN = {"Y": "young", "A": "adult", "M": "middle", "E": "elderly"}
FQ = {"c": "common", "u": "uncommon", "r": "rare"}
SL = {"p": "plain", "m": "mild", "k": "marked"}
SX = {"m": "male", "f": "female", "a": "any"}

# ------------------------------------------------------------------ 1. vocab
vocab = json.loads((KB / "vocab.json").read_text(encoding="utf-8"))
NEW_SLOTS = []          # filled while parsing
order_groups = ["A", "B", "C", "D", "E", "F", "G", "H"]

LOC_WORDS = {
    "forehead": "forehead", "temple-l": "left temple", "temple-r": "right temple", "brow-l": "left brow", "brow-r": "right brow",
    "cheek-l": "left cheek", "cheek-r": "right cheek", "nose": "nose", "lip": "upper lip", "chin": "chin",
    "jaw-l": "left jaw", "jaw-r": "right jaw", "ear-l": "left ear", "ear-r": "right ear",
    "neck": "neck", "throat": "throat", "scalp": "scalp",
    "shoulder-l": "left shoulder", "shoulder-r": "right shoulder", "upperarm-l": "left upper arm", "upperarm-r": "right upper arm",
    "forearm-l": "left forearm", "forearm-r": "right forearm", "hand-l": "left hand", "hand-r": "right hand",
    "chest": "chest", "belly": "belly", "back": "back",
    "thigh-l": "left thigh", "thigh-r": "right thigh", "knee-l": "left knee", "knee-r": "right knee",
    "shin-l": "left shin", "shin-r": "right shin", "foot-l": "left foot", "foot-r": "right foot",
    "leg-l": "left leg", "leg-r": "right leg", "arm-l": "left arm", "arm-r": "right arm", "eye-l": "left eye", "eye-r": "right eye",
}
LOC_GROUPS = {
    "face": ["forehead", "temple-l", "temple-r", "brow-l", "brow-r", "cheek-l", "cheek-r", "nose", "lip", "chin", "jaw-l", "jaw-r",
             "ear-l", "ear-r"],
    "neck": ["neck", "throat"],
    "arms": ["shoulder-l", "shoulder-r", "upperarm-l", "upperarm-r", "forearm-l", "forearm-r", "hand-l", "hand-r"],
    "torso": ["chest", "belly", "back"],
    "legs": ["thigh-l", "thigh-r", "knee-l", "knee-r", "shin-l", "shin-r", "foot-l", "foot-r"],
}

FACETS = {
    "means": ["destitute", "poor", "modest", "comfortable", "rich"],
    "life": ["outdoor-manual", "sea", "farm", "street", "office", "display", "domestic", "military", "idle"],
    "diet": ["underfed", "plain-diet", "well-fed", "overfed"],
    "alcohol": ["sober", "drinks", "heavy-drinker"],
    "smoke": ["smoker", "non-smoker"],
    "place": ["rural", "urban", "coastal", "highland"],
    "era": ["born-pre1960", "born-1960-1989", "born-1990plus"],
    "eth": ["kinh", "sea", "east-asian", "south-asian", "european", "african", "mixed"],
}
# facet tag <- regex (first match in priority order wins per facet). Scanned in IDENTITY fields (not Name/Relationships)
# and in STYLE lines. LIFE items only give cause tags (below), never facets.
FACT_KEYWORDS = {
    "means": [["destitute", r"\b(destitute|homeless|beggar|penniless)"], ["poor", r"\b(poor|poverty|hard[- ]up|scrap(es)? by)"],
              ["rich", r"\b(rich|wealthy|millionaire|tycoon|owns? (a )?(company|factory|chain))"],
              ["comfortable", r"\b(well[- ]off|comfortable|middle[- ]class|affluent)"],
              ["modest", r"\b(modest|working[- ]class|ordinary income|small shop)"]],
    "life": [["sea", r"\b(fish|fisher\w*|boat|nets?\b|squid|sailor|seaman)"], ["farm", r"\b(farm\w*|rice field|paddy|buffalo|peasant)"],
             ["outdoor-manual", r"\b(fish\w*|farm\w*|porter|builder|construction|labou?rer|mason|carpenter|cyclo|motorbike taxi|"
                                r"xe ôm|vendor|carr(y|ies) (goods|loads)|mend\w* nets|haul)"],
             ["street", r"\b(street vendor|hawker|scavenger|beggar|shoeshine)"],
             ["office", r"\b(office|clerk|accountant|teacher|programmer|engineer|student|official|banker|manager|lawyer|doctor)"],
             ["display", r"\b(model|actor|actress|singer|idol|influencer|fitness|bodybuilder|dancer)"],
             ["domestic", r"\b(housewife|homemaker|maid|nanny|cook\b)"], ["military", r"\b(soldier|army|police|officer|militia)"],
             ["idle", r"\b(retired|unemployed|idle|heir)"]],
    "diet": [["underfed", r"\b(eats? little|skips? meals|hungry|starv\w*|goes hungry|not enough to eat)"],
             ["overfed", r"\b(eats? a lot|overeat\w*|gluttor\w*|feasts? (often|every)|heavy eater)"],
             ["plain-diet", r"\b(simple meals?|plain food|avoids heavy|rice and (salted|dried) fish|frugal)"],
             ["well-fed", r"\b(eats well|rich food|good food|restaurants?)"]],
    "alcohol": [["heavy-drinker", r"\b(drunk\w*|alcoholic|drinks? heavily|heavy drink\w*|every (night|day)[^.;]*(wine|beer|liquor))"],
                ["sober", r"\b(never drinks?|does not drink|doesn't drink|teetotal\w*|no alcohol)"],
                ["drinks", r"\b(rice wine|beer|liquor|rượu|bia|glass of wine|drinks? (with|a glass|occasionally))"]],
    "smoke": [["non-smoker", r"\b(never smok\w*|does not smoke|non-?smoker)"], ["smoker", r"\b(smok\w*|tobacco|cigarette|thuốc lào|pipe)"]],
    "place": [["coastal", r"\b(fishing village|coast\w*|seaside|by the sea|port)"], ["highland", r"\b(highland|mountain|central highlands)"],
              ["urban", r"\b(city|hanoi|hà nội|saigon|sài gòn|ho chi minh|hồ chí minh|đà nẵng|district|downtown|urban)"],
              ["rural", r"\b(village|countryside|commune|hamlet|rural)"]],
    "eth": [["mixed", r"\b(mixed|half-)"], ["sea", r"\b(cham|khmer|thai|lao|hmong|tày|tay|mường|muong|ê đê|ede|jarai|bahnar)"],
            ["east-asian", r"\b(hoa\b|chinese|korean|japanese)"], ["south-asian", r"\b(indian|pakistani|bangladeshi|sri lankan)"],
            ["african", r"\b(african|nigerian|kenyan|black american)"],
            ["european", r"\b(french|american|european|russian|german|british|english|australian|white)"],
            ["kinh", r"\b(kinh|vietnamese|việt)"]],
}
# cause tags of one LIFE item / IDENTITY field (for checking a cited reason). Closed causes from vocab.causes.
CAUSE_KEYWORDS = {
    "injury": r"\b(injur\w*|wound\w*|accident|broke|broken|fractur\w*|fight\w*|beaten|bitten|bite|burn\w*|scar\w*|stab\w*|shot|"
              r"shrapnel|bomb\w*|mine\b|landmine|fell|crash\w*|lost (a|his|her) (finger|leg|arm|eye|hand)|limp\w*)",
    "illness": r"\b(ill\b|illness|sick\w*|disease|stroke|fever|cancer|polio|leprosy|tubercul\w*|malaria|hospital\w*|surgery|operation)",
    "water-work": r"\b(sea|boat|fish\w*|nets?\b|squid|river|washing)",
    "sun": r"\b(sea|boat|fish\w*|farm\w*|field|paddy|sun\w*|outdoors?|market|street)",
    "manual-labour": r"\b(haul\w*|carr(y|ied|ies)|labou?r\w*|farm\w*|build\w*|construct\w*|porter|fish\w*|nets?\b|boat|heavy work)",
    "poverty": r"\b(poor|poverty|hunger|hungry|starv\w*|cassava|sweet potato|debt)",
    "wealth": r"\b(rich|wealth\w*|inherit\w*|fortune)",
    "childbearing": r"\b(gave birth|pregnan\w*|children|son|daughter|mother of)",
    "alcohol": r"\b(drink\w*|alcohol\w*|wine|beer|drunk\w*)",
    "substances": r"\b(smok\w*|tobacco|opium|drugs?|heroin|cigarettes?)",
    "low-mood": r"\b(died|death|grief|mourn\w*|lost his|lost her|alone|lonely)",
    "stress": r"\b(war|wartime|storm|fear\w*|debt|prison|nearly did not come back|survived)",
    "sport": r"\b(sport|boxing|football|martial|wrestl\w*|gym|athlet\w*)",
    "custom": r"\b(betel|lacquer\w*|tradition\w*|temple)",
    "sedentary": r"\b(office|desk|computer|sits all day)",
    "weight": r"\b(overweight|fat\b|obese)",
    "weight-loss": r"\b(lost weight|weight loss|dieting)",
}
# injury/illness words in an item that is about someone else's death do not count for the character
OTHER_DEATH = r"\b(wife|husband|son|daughter|father|mother|friend|brother|sister|grandson|granddaughter)\b[^.]*\b(died|killed|death|deceased)"

vocab["schema"] = 3
vocab["groups"] = {"A": "overall build", "B": "head and face", "C": "natural hair", "D": "torso", "E": "arms and hands",
                   "F": "legs and feet", "G": "posture and gait", "H": "marks"}
vocab["regions"] = sorted(set(vocab["regions"]) | {
    "eyelid_droop", "eye_unequal", "eye_turn", "eye_narrow", "brow_level", "nose_bend", "mouth_corners", "mouth_slant", "jaw_side",
    "jowls", "chin_fat", "ear_set", "face_droop", "cheek_hollow", "cheek_side", "cheek_red", "temples", "bite", "parting"},
    key=lambda r: (r not in vocab["regions"], r))
vocab["dims"].update({
    "lines": {"range": [0, 4], "scale": "face lines: 0 smooth, 1 fine, 2 moderate, 3 deep, 4 very deep"},
    "scalp": {"range": [0, 4], "scale": "scalp hair: 0 bald, 1 very sparse, 2 thin, 3 medium, 4 thick"},
    "grey": {"range": [0, 4], "scale": "grey hair: 0 none, 1 a few, 2 salt-and-pepper, 3 mostly grey, 4 white"},
    "teeth": {"range": [0, 4], "scale": "teeth: 0 none, 1 few left, 2 several missing, 3 full but worn, 4 full"},
})
vocab["facets"] = FACETS
vocab["fact_keywords"] = FACT_KEYWORDS
vocab["cause_keywords"] = CAUSE_KEYWORDS
vocab["other_death"] = OTHER_DEATH
vocab["eth_default"] = "kinh"
vocab["fact_fields"] = {"means": "social|position|occupation|wealth|means|status",
                        "life": "occupation|job|work|social|position|lifestyle",
                        "diet": "eat|food|diet|habit|lifestyle", "alcohol": "drink|habit|lifestyle|eat",
                        "smoke": "smok|habit|groom|lifestyle", "place": "hometown|place|home|live|born",
                        "era": "era|year|place", "eth": "nationality|ethnic|origin|race|people"}
vocab["cite"] = {
    "generic": ["genetics", "ageing", "youth", "temperament", "hormones", "climate"],
    "soul_causes": ["temperament", "stress", "low-mood"],
    "identity_skip": ["Name", "Relationships"],
    "note": "rare or notable picks need a cite 'LIFE <n>', 'IDENTITY <field>' or (soul slots) 'SOUL'. If the value has a generic "
            "cause any existing source passes; otherwise the cited item must carry one of the value's causes (cause_keywords)."}
vocab["marks"] = {"max": 3, "loc_words": LOC_WORDS, "loc_groups": LOC_GROUPS,
                  "hidden": ["chest", "belly", "back", "thigh-l", "thigh-r"],
                  "note": "a marks pick is '<id>@<loc>'; hidden locations count as mild (not a signature)"}

# ------------------------------------------------------------------ 2. parse face_bch.txt
rid2cids = {}
for line in (SKILL / "sources.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    rid2cids.setdefault(r["rid"], []).append(r["cid"])
lane = {}
for line in LANE.read_text(encoding="utf-8").splitlines():
    c = json.loads(line)
    lane[c["cid"]] = c
SLUG2SRC = {"the-artists-complete-guide-to-facial-expression": "facial_expression",
            "the-art-of-aesthetic-surgery-principles-and-techniques": "aesthetic_surgery",
            "anthropometry-of-the-head-and-face": "anthropometry_face",
            "force-character-design-from-life-drawing": "force_drawing",
            "anatomy-of-facial-expression": "anatomy_facial_expression"}


def parse_rows(spec, letters):
    parts = spec.split(";")
    rows = [{"cls" if letters is FQ else "s": letters[parts[0]]}]
    for p in parts[1:]:
        k, v = p.split("=")
        w = {}
        for ch in k:
            if ch in "mf":
                w["sex"] = SX[ch]
            else:
                w["band"] = BN[ch]
        rows.append({"when": w, ("cls" if letters is FQ else "s"): letters[v]})
    if letters is FQ:
        for r in rows:
            r["basis"] = "est"
    return rows


def ages(spec):
    if "-" in spec:
        lo, hi = spec.split("-")
        return [int(lo), int(hi)]
    return [AG[spec[0]][0], AG[spec[-1]][1]]


def groups(spec):
    out = []
    for g in spec.split(","):
        eth = None
        if "/" in g:
            eth, g = g.split("/")
        sx = SX[g[0]]
        for ch in g[1:]:
            k = f"{sx}-{BN[ch]}"
            out.append(f"{eth}/{k}" if eth else k)
    return out


def needs_parse(spec):
    conds = []
    for alt in spec.split("/"):
        c = {}
        for part in alt.split("&"):
            f, vals = part.split(":")
            c[f] = vals.split("+")
        conds.append(c)
    return conds


catalog, vi_rows, used_cids = {}, [], {}
cur = None
for n, line in enumerate((KB / "src" / "face_bch.txt").read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip() or line.startswith("# "):
        continue
    if line.startswith("## "):
        slot, grp, vi, flags = line[3:].split("|")
        cur = slot
        fl = [f for f in flags.split(",") if f]
        NEW_SLOTS.append((slot, grp, fl))
        catalog[slot] = []
        vi_rows.append({"id": slot, "vi": vi})
        continue
    p = line.split("|")
    assert len(p) in (8, 9), f"line {n}: {len(p)} fields: {line}"
    slug, sx, ph, vi, fq, bands, causes, sal = p[:8]
    opts = dict(o.split("=", 1) for o in (p[8].split() if len(p) == 9 else []))
    vid = f"{cur}.{slug}"
    v = {"id": vid, "slot": cur, "status": "active", "sex": SX[sx], "age": ages(bands), "phrase": ph,
         "causes": [c for c in causes.split(",") if c], "freq": parse_rows(fq, FQ), "sal": parse_rows(sal, SL),
         "baseline_for": groups(opts["B"]) if "B" in opts else [], "dims": {}, "regions": [], "needs": [], "fit": [], "ev": []}
    if "d" in opts:
        for d in opts["d"].split(","):
            k, rg = d.split(":")
            lo, hi = rg.split("-")
            v["dims"][k] = [int(lo), int(hi)]
    if "r" in opts:
        v["regions"] = opts["r"].split(",")
    if "n" in opts:
        v["needs"] = needs_parse(opts["n"])
    if "eth" in opts:
        e = opts["eth"].split(",")
        v["needs"] = [{**c, "eth": e} for c in v["needs"]] or [{"eth": e}]
    if "fit" in opts:
        v["fit"] = opts["fit"].split(",")
    if "loc" in opts:
        locs = []
        for x in opts["loc"].split(","):
            locs += LOC_GROUPS.get(x, [x])
        assert all(l in LOC_WORDS for l in locs), (vid, locs)
        v["locs"] = locs
    if "ev" in opts:
        for ref in opts["ev"].split(","):
            cids = rid2cids.get(ref, [ref]) if ref.startswith("r") else [ref]
            for cid in cids[:2]:
                assert cid in lane, (vid, ref, cid)
                used_cids[cid] = True
                v["ev"].append({"c": "pf." + cid, "rel": "supports"})
    v["since"], v["rev"] = 3, 1
    catalog[cur].append(v)
    vi_rows.append({"id": vid, "vi": vi})

# slots in prompt order: A, then B, C, then D..G (existing), then H
old = vocab["slots"]
new = {s: (g, fl) for s, g, fl in NEW_SLOTS}
REQ_NEW = {s for s, g, fl in NEW_SLOTS if "req" in fl}
ordered = [s for s in old if old[s]["group"] == "A"] + [s for s, g, fl in NEW_SLOTS if g in "BC"] + \
          [s for s in old if old[s]["group"] in "DEFG"] + [s for s, g, fl in NEW_SLOTS if g == "H"]
slots = {}
for i, s in enumerate(ordered):
    if s in old:
        m = dict(old[s])
    else:
        g, fl = new[s]
        m = {"group": g, "required_in_prompt": "req" in fl, "multi": "multi" in fl}
        if "soul" in fl:
            m["soul"] = True
    m["order"] = i
    if s in ("posture", "gait"):
        m["soul"] = True
    slots[s] = m
vocab["slots"] = slots
(KB / "vocab.json").write_text(json.dumps(vocab, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

for slot, vals in catalog.items():
    (KB / "catalog" / f"{slot}.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in vals), encoding="utf-8")

# ------------------------------------------------------------------ 3. needs/fit for body values
NEEDS = {"gym": {"means": ["modest", "comfortable", "rich"]}, "enhanced": {"means": ["comfortable", "rich"]},
         "wealth": {"means": ["comfortable", "rich"]}, "poverty": {"means": ["destitute", "poor", "modest"]},
         "diet": {"diet": ["well-fed", "overfed"]}, "alcohol": {"alcohol": ["drinks", "heavy-drinker"]},
         "weight": {"diet": ["plain-diet", "well-fed", "overfed"]},
         "sedentary": {"life": ["office", "domestic", "idle", "display"]},
         "manual-labour": {"life": ["outdoor-manual", "sea", "farm", "street", "military", "domestic"]},
         "water-work": {"life": ["sea", "farm", "domestic", "street"]},
         "grooming": {"means": ["modest", "comfortable", "rich"]}, "barefoot": {"means": ["destitute", "poor", "modest"]}}
FIT = {"gym": ["display"], "enhanced": ["display"], "sedentary": ["office"], "manual-labour": ["outdoor-manual", "farm", "sea", "street"],
       "water-work": ["sea", "farm"], "sun": ["outdoor-manual", "farm", "sea", "street", "military"], "sport": ["display", "military"],
       "substances": ["smoker"], "barefoot": ["farm", "sea", "street"], "footwear": ["office", "display"],
       "grooming": ["office", "display"], "wealth": ["rich", "comfortable"], "poverty": ["poor", "destitute"],
       "alcohol": ["drinks", "heavy-drinker"], "diet": ["well-fed", "overfed"]}
FREE = {"genetics", "illness", "injury", "custom", "climate", "childbearing", "temperament"}
FAT_SLOTS = {"fat", "fat_where", "waist_belly", "chest", "hips", "legs", "arms", "back"}
HEAVY = [{"diet": ["well-fed", "overfed"]}, {"alcohol": ["heavy-drinker"]}]
OVERRIDE = {"waist_belly.beer-m": (["diet", "alcohol", "ageing"], HEAVY), "waist_belly.gut-m": (["diet", "alcohol"], HEAVY),
            "fat_where.visceral-m": (["diet", "alcohol", "ageing"], HEAVY)}


def derive(v):
    causes = v["causes"]
    fit = sorted({t for c in causes for t in FIT.get(c, [])})
    if v["id"] in OVERRIDE:
        return OVERRIDE[v["id"]][1], fit
    if set(causes) & FREE:
        return [], fit
    conds = []
    for c in causes:
        if c in NEEDS:
            cond = dict(NEEDS[c])
            if c == "alcohol" and v["slot"] in FAT_SLOTS:
                cond = {"alcohol": ["heavy-drinker"]}
            if cond not in conds:
                conds.append(cond)
    return conds, fit


tagged = 0
for p in sorted((KB / "catalog").glob("*.jsonl")):
    if p.stem in catalog:
        continue
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        v = json.loads(line)
        if v["id"] in OVERRIDE:
            v["causes"] = OVERRIDE[v["id"]][0]
            v["rev"] = v.get("rev", 1) + 1
        v["needs"], v["fit"] = derive(v)
        tagged += bool(v["needs"])
        out.append(json.dumps(v, ensure_ascii=False))
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("body values with needs:", tagged)
# face values: add fit from causes when not set explicitly
for slot, vals in catalog.items():
    for v in vals:
        if not v["fit"]:
            v["fit"] = sorted({t for c in v["causes"] for t in FIT.get(c, [])})
    (KB / "catalog" / f"{slot}.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in vals), encoding="utf-8")

# ------------------------------------------------------------------ 4. evidence
by_src = {}
for cid in used_cids:
    c = lane[cid]
    src = SLUG2SRC[c["slug"]]
    by_src.setdefault(src, []).append({"id": "pf." + cid, "source": src, "kind": c.get("kind", "cue"), "text": c["statement"],
                                       "condition": c.get("condition", ""), "quote": c.get("quote", ""), "about": c.get("about", []),
                                       "loc": ",".join(s["id"] for s in c.get("src", [])), "from": "ebook_maker kb/character-portrait", "status": "active"})
for src, cards in by_src.items():
    cards.sort(key=lambda c: c["id"])
    (KB / "evidence" / f"{src}_pf.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards), encoding="utf-8")
print("evidence cards:", {s: len(c) for s, c in by_src.items()})

# ------------------------------------------------------------------ 5. vi + sources
vi_path = KB / "vi.jsonl"
old_vi = [json.loads(l) for l in vi_path.read_text(encoding="utf-8").splitlines() if l.strip()]
newids = {r["id"] for r in vi_rows}
rows = [r for r in old_vi if r["id"] not in newids] + vi_rows
vi_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

src_path = KB / "sources.jsonl"
srcs = [json.loads(l) for l in src_path.read_text(encoding="utf-8").splitlines() if l.strip()]
have = {s["id"] for s in srcs}
TITLES = {"facial_expression": "the-artists-complete-guide-to-facial-expression",
          "anthropometry_face": "anthropometry-of-the-head-and-face",
          "anatomy_facial_expression": "anatomy-of-facial-expression"}
for sid, slug in TITLES.items():
    if sid not in have and sid in by_src:
        srcs.append({"id": sid, "kind": "book", "title_slug": slug, "license_needed": False,
                     "terms": "owned copy, private non-commercial research; cards are short paraphrases with brief quotes",
                     "retrieved": "2026-11 (via ebook_maker kb/character-portrait cards, copied)", "raw": None, "n_cards": len(by_src[sid]),
                     "status": "active"})
src_path.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in srcs), encoding="utf-8")
print("slots:", len(slots), "new values:", sum(len(v) for v in catalog.values()))
