"""Build kb/standards.json: standard description terms (no images) the catalog maps to.
Sets:
  ncic_smt / ncic_eye / ncic_hair / ncic_skin   NCIC code tables (ecfr.io JSON snapshot, NIEM 5.2)
  eom      NIH Elements of Morphology term labels (head/face, periorbital, ear, nose, lips/mouth, hands/feet)
  dvi      Interpol DVI Ante-Mortem form 2023, body description fields 404-476 and their option lists (pdf pages 6-7)
  tt22     Thong tu 22/2014/TT-BCA, mau 30a/30b "Dac diem nhan dang" fields (the form gives field names only)
  vn_conv  customary Vietnamese words used under those fields (not in the circular; our own list)
plus marks_codes: for every marks value with an NCIC kind, the SMT code per allowed place (e.g. marks.mole@cheek-l ->
'MOLE L CHK'). Reads downloaded files as text only.

    python -I distill_vocab.py [data_root]"""
import glob
import hashlib
import html
import json
import re
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
D = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/khoa/data/nhan_vat_sources")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


DVI = {  # id -> (label, page)
    "404-scars": ("Specific details: scars", 6), "404-piercings": ("Specific details: piercings", 6),
    "404-skin-marks": ("Specific details: skin marks", 6), "404-amputations": ("Specific details: amputations", 6),
    "404-malformations": ("Specific details: malformations", 6), "404-tattoos": ("Specific details: tattoos", 6),
    "408-height": ("Height (min-max)", 6), "412-weight": ("Weight (min-max)", 6),
    "416-build-slight": ("Build: slight", 6), "416-build-medium": ("Build: medium", 6), "416-build-large": ("Build: large", 6),
    "420-hair-colour-black": ("Hair natural colour: black", 6), "420-hair-colour-brown": ("Hair natural colour: brown", 6),
    "420-hair-colour-blond": ("Hair natural colour: blond", 6), "420-hair-colour-red": ("Hair natural colour: red", 6),
    "420-hair-colour-grey": ("Hair natural colour: grey", 6), "420-hair-colour-white": ("Hair natural colour: white", 6),
    "420-hair-colour-mixed-grey": ("Hair natural colour: mixed grey", 6),
    "420-baldness-partial": ("Baldness: partial", 6), "420-baldness-total": ("Baldness: total", 6),
    "420-baldness-forehead": ("Baldness: forehead", 6), "420-baldness-sides": ("Baldness: sides", 6),
    "420-baldness-tonsure": ("Baldness: tonsure", 6), "420-hair-distinctive": ("Hair of the head: distinctive features", 6),
    "eyebrows-distinctive": ("Eyebrows: distinctive features", 7),
    "eyes-colour-blue": ("Eyes colour: blue", 7), "eyes-colour-grey": ("Eyes colour: grey", 7),
    "eyes-colour-green": ("Eyes colour: green", 7), "eyes-colour-brown": ("Eyes colour: brown", 7),
    "eyes-colour-black": ("Eyes colour: black", 7), "eyes-colour-hazel": ("Eyes colour: hazel", 7),
    "eyes-cross-eyed": ("Eyes distinctive: cross-eyed", 7), "eyes-squint-eyed": ("Eyes distinctive: squint-eyed", 7),
    "eyes-artificial": ("Eyes distinctive: artificial eye", 7), "nose-distinctive": ("Nose: distinctive features", 7),
    "facial-hair-shaved": ("Facial hair: shaved", 7), "facial-hair-moustache": ("Facial hair: moustache", 7),
    "facial-hair-goatee": ("Facial hair: goatee", 7), "facial-hair-full-beard": ("Facial hair: full beard", 7),
    "facial-hair-whiskers": ("Facial hair: whiskers", 7), "ears-lobes-attached": ("Ears: lobes attached", 7),
    "ears-pierced": ("Ears: pierced", 7), "ears-distinctive": ("Ears: distinctive features", 7),
    "mouth-teeth-distinctive": ("Mouth/teeth: distinctive features", 7), "lips-distinctive": ("Lips: distinctive features", 7),
    "chin-distinctive": ("Chin: distinctive features", 7), "neck-distinctive": ("Neck: distinctive features", 7),
    "hands-nails-distinctive": ("Hands/nails: distinctive features", 7), "feet-nails-distinctive": ("Feet/nails: distinctive features", 7),
    "body-hair-distinctive": ("Body/pubic hair: distinctive features", 7),
}
TT22 = {"chieu-cao": "Chieu cao (height)", "mau-da": "Mau da (skin colour)", "toc": "Toc (hair)", "long-may": "Long may (eyebrows)",
        "song-mui": "Song mui (nasal bridge)", "dai-tai": "Dai tai (earlobes)", "mat": "Mat (eyes)",
        "dac-diem-khac": "Dac diem khac (other features)"}
VN_CONV = {  # customary words in wanted notices / ID descriptions (ASCII-folded); not part of TT 22
    "mau-da.trang": "da trang (fair)", "mau-da.vang": "da vang (yellowish)", "mau-da.ngam": "da ngam (tan)",
    "mau-da.ngam-den": "da ngam den (dark tan)", "mau-da.den": "da den (dark)",
    "toc.den-thang": "toc den thang (black straight)", "toc.xoan": "toc xoan (curly)", "toc.hoa-ram": "toc hoa ram (salt-and-pepper)",
    "toc.bac-trang": "toc bac trang (white)", "toc.hoi": "hoi dau (bald)",
    "long-may.ram": "long may ram (thick)", "long-may.thua": "long may thua (sparse)", "long-may.chu-nhat": "long may chu nhat (straight)",
    "long-may.la-lieu": "long may la lieu (thin arched)", "long-may.luoi-mac": "long may luoi mac (slanting up)",
    "song-mui.thap": "song mui thap (low bridge)", "song-mui.cao": "song mui cao (high bridge)", "song-mui.thang": "song mui thang (straight)",
    "song-mui.gay": "song mui gay/lech (broken, bent)", "song-mui.go": "song mui go (bump)", "mui.to-be": "mui to be (broad fleshy)",
    "dai-tai.to": "dai tai to/day (large thick lobes)", "dai-tai.nho": "dai tai nho (small lobes)", "dai-tai.dinh": "dai tai dinh (attached)",
    "mat.mot-mi": "mat mot mi (single lid)", "mat.hai-mi": "mat hai mi (double lid)", "mat.xech": "mat xech (upslanted)",
    "mat.to": "mat to (large)", "mat.nho": "mat nho (small)", "mat.lac": "mat lac (squint)",
}
# NCIC location label (text after ' ; ') for each KB mark place, most specific first
LOC = {"forehead": ["FOREHEAD"], "temple-l": ["HEAD, NONSPECIFIC", "HEAD", "FACE, NONSPECIFIC", "FACE"], "temple-r": ["HEAD, NONSPECIFIC", "HEAD", "FACE, NONSPECIFIC", "FACE"],
       "brow-l": ["EYEBROW, LEFT/LEFT EYE AREA", "EYEBROW, NONSPECIFIC"], "brow-r": ["EYEBROW, RIGHT/RIGHT EYE AREA", "EYEBROW, NONSPECIFIC"],
       "cheek-l": ["CHEEK, LEFT", "CHEEK, NONSPECIFIC"], "cheek-r": ["CHEEK, RIGHT", "CHEEK, NONSPECIFIC"], "nose": ["NOSE"],
       "lip": ["LIP, UPPER", "LIP, NONSPECIFIC"], "chin": ["CHIN"], "jaw-l": ["FACE, NONSPECIFIC", "FACE"], "jaw-r": ["FACE, NONSPECIFIC", "FACE"],
       "ear-l": ["EAR, LEFT", "EAR, NONSPECIFIC"], "ear-r": ["EAR, RIGHT", "EAR, NONSPECIFIC"], "neck": ["NECK"], "throat": ["NECK"],
       "scalp": ["HEAD, NONSPECIFIC", "HEAD"], "shoulder-l": ["SHOULDER, LEFT", "SHOULDER, NONSPECIFIC"],
       "shoulder-r": ["SHOULDER, RIGHT", "SHOULDER, NONSPECIFIC"], "upperarm-l": ["ARM, LEFT, UPPER", "ARM, LEFT"],
       "upperarm-r": ["ARM, RIGHT, UPPER", "ARM, RIGHT"], "forearm-l": ["ARM, LEFT, LOWER", "ARM, LEFT"],
       "forearm-r": ["ARM, RIGHT, LOWER", "ARM, RIGHT"], "hand-l": ["HAND, LEFT", "FINGER(S), LEFT HAND"],
       "hand-r": ["HAND, RIGHT", "FINGER(S), RIGHT HAND"], "chest": ["CHEST"], "belly": ["ABDOMEN"], "back": ["BACK"],
       "thigh-l": ["THIGH, LEFT", "THIGH, NONSPECIFIC"], "thigh-r": ["THIGH, RIGHT", "THIGH, NONSPECIFIC"],
       "knee-l": ["KNEE, LEFT", "KNEE, NONSPECIFIC"], "knee-r": ["KNEE, RIGHT", "KNEE, NONSPECIFIC"],
       "shin-l": ["LEG, LEFT, LOWER", "CALF, LEFT", "LEG, LEFT"], "shin-r": ["LEG, RIGHT, LOWER", "CALF, RIGHT", "LEG, RIGHT"],
       "foot-l": ["FOOT, LEFT", "FOOT, NONSPECIFIC"], "foot-r": ["FOOT, RIGHT", "FOOT, NONSPECIFIC"], "leg-l": ["LEG, LEFT"],
       "leg-r": ["LEG, RIGHT"], "arm-l": ["ARM, LEFT"], "arm-r": ["ARM, RIGHT"], "eye-l": ["EYE, LEFT"], "eye-r": ["EYE, RIGHT"]}
MISS_FINGER = {"hand-l": ["FINGER(S), LEFT HAND"], "hand-r": ["FINGER(S), RIGHT HAND"]}
MISS_JOINT = {"hand-l": ["FINGER JOINT(S), LEFT HAND"], "hand-r": ["FINGER JOINT(S), RIGHT HAND"]}
# marks value -> NCIC category (text before ' ; ') and optional location override
KIND = {"marks.mole": "MOLES", "marks.molehair": "MOLES", "marks.moles": "MOLES",
        "marks.birthmark": "SKIN DISCOLORATIONS (INCLUDING BIRTHMARKS)", "marks.portwine": "SKIN DISCOLORATIONS (INCLUDING BIRTHMARKS)",
        "marks.bluepatch": "SKIN DISCOLORATIONS (INCLUDING BIRTHMARKS)", "marks.vitiligo": "SKIN DISCOLORATIONS (INCLUDING BIRTHMARKS)",
        "marks.coin": "SKIN DISCOLORATIONS (INCLUDING BIRTHMARKS)",
        "marks.burn": "SCARS", "marks.knife": "SCARS", "marks.jagged": "SCARS", "marks.surgical": "SCARS", "marks.stitch": "SCARS",
        "marks.vaccine": "SCARS", "marks.keloid": "SCARS", "marks.shrapnel": "SCARS", "marks.selfharm": "SCARS",
        "marks.cleft": "SCARS", "marks.bite": "SCARS", "marks.pit": "SCARS", "marks.earnotch": "SCARS",
        "marks.tattoo-old": "TATTOOS", "marks.tattoo-small": "TATTOOS", "marks.tattoo-big": "TATTOOS",
        "marks.fingerstump": ("MISSING BODY PARTS AND ORGANS", MISS_FINGER), "marks.fingertip": ("MISSING BODY PARTS AND ORGANS", MISS_JOINT),
        "marks.legloss": "MISSING BODY PARTS AND ORGANS", "marks.armloss": "MISSING BODY PARTS AND ORGANS",
        "marks.eyeloss": "MISSING BODY PARTS AND ORGANS", "marks.tracks": 'NEEDLE ("TRACK") MARKS'}


def main():
    terms, src = {}, {}
    # NCIC
    p9 = D / "09_ncic_smt_namus"
    smt = []
    for f in sorted(glob.glob(str(p9 / "ecfr_ncic_SMT_entries_offset*.json"))):
        smt += json.loads(Path(f).read_text(encoding="utf-8"))["results"]
    src["ncic_smt"] = {"files": "ecfr_ncic_SMT_entries_offset000-900.json", "n": len(smt), "snapshot": "niem-5-2"}
    by_label = {}
    for r in smt:
        terms[f"ncic_smt:{r['code']}"] = {"label": r["label"], "set": "ncic_smt"}
        cat, _, loc = r["label"].partition(" ; ")
        by_label[(cat, loc)] = r["code"]
    for s in ("EYE", "HAIR", "SKIN"):
        f = p9 / f"ecfr_ncic_{s}_entries.json"
        rows = json.loads(f.read_text(encoding="utf-8"))["results"]
        src[f"ncic_{s.lower()}"] = {"file": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "n": len(rows)}
        for r in rows:
            terms[f"ncic_{s.lower()}:{r['code']}"] = {"label": r["label"], "set": f"ncic_{s.lower()}"}
    # marks codes
    marks_codes = {}
    cat_rows = [json.loads(x) for x in (KB / "catalog" / "marks.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    locs = {v["id"]: v.get("locs", []) for v in cat_rows}
    for vid, k in KIND.items():
        cat, over = (k, {}) if isinstance(k, str) else k
        out = {}
        for loc in locs.get(vid, []):
            for lab in over.get(loc, LOC.get(loc, [])):
                code = by_label.get((cat, lab))
                if code:
                    out[loc] = code
                    break
        if out:
            marks_codes[vid] = out
    # EoM
    root = D / "06_nih_elements_morphology"
    n_eom = 0
    for d in sorted(x for x in root.iterdir() if x.is_dir()):
        for f in sorted(d.glob("term_*.html")):
            t = re.sub(r"(?is)<(script|style).*?</\1>", " ", f.read_bytes().decode("utf-8", "replace"))
            lines = [x.strip() for x in html.unescape(re.sub(r"<[^>]+>", "\n", t)).splitlines() if x.strip()]
            if "Definition:" not in lines:
                continue
            label = lines[lines.index("Definition:") - 1]
            terms[f"eom:{slug(label)}"] = {"label": label, "set": "eom", "region": d.name, "file": f"{d.name}/{f.name}"}
            n_eom += 1
    src["eom"] = {"dir": "06_nih_elements_morphology", "n": n_eom, "note": "labels only; definitions not copied"}
    am = D / "04_interpol_dvi" / "AM2023_enGB_Flat_Ver1.0.3.pdf"
    src["dvi"] = {"file": am.name, "sha256": hashlib.sha256(am.read_bytes()).hexdigest(), "pages": "6-7 (body description)"}
    for k, (lab, pg) in DVI.items():
        terms[f"dvi:{k}"] = {"label": lab, "set": "dvi", "page": pg}
    t30 = D / "05_tt22_2014_bca" / "tvpl_mau30aQD_truy_na_giai_doan_dieu_tra.html"
    src["tt22"] = {"file": t30.name, "sha256": hashlib.sha256(t30.read_bytes()).hexdigest(),
                   "note": "mau 30a/30b QD, muc 'Dac diem nhan dang': field names only"}
    for k, lab in TT22.items():
        terms[f"tt22:{k}"] = {"label": lab, "set": "tt22"}
    src["vn_conv"] = {"note": "customary Vietnamese description words under the TT22 fields (our list, ASCII-folded)"}
    for k, lab in VN_CONV.items():
        terms[f"vn_conv:{k}"] = {"label": lab, "set": "vn_conv"}
    out = {"note": "generated by src/distill_vocab.py; do not edit by hand", "sources": src, "terms": terms,
           "marks_codes": marks_codes}
    (KB / "standards.json").write_text(json.dumps(out, indent=0, ensure_ascii=True) + "\n", encoding="utf-8")
    print(len(terms), "terms;", len(marks_codes), "marks values with NCIC codes;", n_eom, "EoM labels")


if __name__ == "__main__":
    main()
