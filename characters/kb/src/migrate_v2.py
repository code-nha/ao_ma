"""One-time migration: kb/body.json (v1, 471 values) -> kb v2 layout (catalog/*.jsonl, vocab.json, vi.jsonl,
evidence/, sources.jsonl, rules.jsonl, tests/golden.jsonl).

    python -I src/migrate_v2.py <path to ebook_maker cards out.jsonl>

The cards path is read ONLY here, to copy the cited cards into kb/evidence/. Nothing at runtime points to ebook_maker.
After migration the JSONL files are the source of truth; edit them, not this script. Kept for the record.
"""
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

KB = Path(__file__).resolve().parents[1]
TODAY = "2026-11-24"
BANDS = {"young": [18, 29], "adult": [30, 44], "middle": [45, 64], "elderly": [65, 120]}
OLD_BAND = {"young": "young", "adult": "adult", "middle": "middle", "elderly": "elderly"}

# ---------------------------------------------------------------- closed cause vocabulary (bug 4)
CAUSES = OrderedDict([
    ("genetics", "inborn build or trait"),
    ("youth", "body not yet filled out, adolescence"),
    ("ageing", "normal ageing"),
    ("hormones", "hormonal changes incl. menopause"),
    ("childbearing", "pregnancy, childbirth, nursing, carrying children"),
    ("manual-labour", "heavy physical work, carrying, farming, standing work"),
    ("water-work", "long hours in water: fishing, washing"),
    ("barefoot", "going barefoot"),
    ("footwear", "tight or poor shoes"),
    ("sun", "long sun exposure"),
    ("climate", "hot humid or cold climate"),
    ("sedentary", "sitting, little movement"),
    ("sport", "sport, riding, running, dancing"),
    ("gym", "gym training for looks"),
    ("enhanced", "drugs or surgery to change the body"),
    ("poverty", "poor food, hard living"),
    ("wealth", "money, easy living, care"),
    ("diet", "eating a lot or rich food"),
    ("weight", "being heavy"),
    ("weight-loss", "dieting or large weight loss"),
    ("alcohol", "drinking"),
    ("substances", "smoking, drugs"),
    ("illness", "illness or medical condition"),
    ("injury", "injury, fights, abuse"),
    ("custom", "local custom or habit (betel, long pinky nail)"),
    ("grooming", "careful self-care"),
    ("neglect", "little self-care"),
    ("stress", "tension, stress"),
    ("low-mood", "sadness, exhaustion"),
    ("temperament", "personality shown in stance or walk"),
])
CAUSE_MAP = {
    "genetics": "genetics", "tall": "genetics", "lean": "genetics", "big-bust": "genetics",
    "youth": "youth", "growth": "youth",
    "ageing": "ageing", "osteoporosis": "ageing",
    "hormones": "hormones", "menopause": "hormones",
    "childbirth": "childbearing", "pregnancy": "childbearing", "carrying-child": "childbearing",
    "manual-labour": "manual-labour", "carrying-loads": "manual-labour", "farming": "manual-labour",
    "standing-work": "manual-labour", "walking": "manual-labour",
    "fishing": "water-work", "washing": "water-work",
    "barefoot": "barefoot", "tight-shoes": "footwear",
    "sun": "sun", "tropical": "climate", "heat": "climate", "cold": "climate",
    "sedentary": "sedentary", "sport": "sport", "riding": "sport",
    "gym-display": "gym", "enhanced": "enhanced",
    "poverty": "poverty", "rickets": "poverty", "wealth": "wealth",
    "diet": "diet", "weight": "weight", "weight-loss": "weight-loss", "dieting": "weight-loss",
    "alcohol": "alcohol", "smoking": "substances", "addiction": "substances",
    "illness": "illness", "anemia": "illness", "stroke": "illness", "scoliosis": "illness",
    "hip-problem": "illness", "fungal": "illness",
    "injury": "injury", "fighting": "injury", "abuse": "injury",
    "custom": "custom", "grooming": "grooming", "neglect": "neglect",
    "stress": "stress", "tension": "stress",
    "low-mood": "low-mood", "exhaustion": "low-mood",
    "confidence": "temperament", "dominance": "temperament", "timidity": "temperament", "relaxed": "temperament",
    "discipline": "temperament", "guarded": "temperament", "awkward": "temperament", "cheerful": "temperament",
    "authority": "temperament", "status": "temperament", "busy": "temperament",
}

# ---------------------------------------------------------------- visible-only rewrites (bug 5); ids unchanged
REPHRASE = {
    "height.shrunken-m": "shrunken old man, compressed short stature",
    "height.shrunken-f": "tiny shrunken old woman, compressed stature",
    "fat.gaunt-ill-m": "gaunt wasted body with a sickly hollow look",
    "fat.gaunt-ill-f": "gaunt wasted body with a sickly hollow look",
    "fat.loose-after-loss-f": "deflated body with loose empty folds of skin",
    "fat.loose-after-loss-m": "deflated body with loose empty folds of skin",
    "muscle.ropy-labour-m": "hard ropy muscles, lean and corded",
    "muscle.onesided-m": "one arm and shoulder visibly more muscled",
    "muscle.farm-strong-f": "sturdy strong body with solid arms and legs",
    "muscle.gone-soft-m": "thick build gone soft, faded muscle shape",
    "muscle.gone-soft-f": "soft body with faint traces of old muscle",
    "shoulders.pole-m": "one shoulder thickened with a callused pad",
    "shoulders.load-f": "strong rounded shoulders with thick muscle",
    "chest.labour-m": "solid thick muscular chest",
    "chest.sagging-f": "deflated breasts sagging low on the chest",
    "waist_belly.pooch-f": "loose soft pouch of lower belly",
    "waist_belly.diastasis-f": "belly bulging along the midline",
    "back.fieldbent": "back bent forward at the waist, held low",
    "back.broad-m": "broad thick muscular back",
    "back.lean-sideways": "spine leaning to one side, one side lower",
    "body_skin.loose-m": "loose empty folds of skin on the body",
    "body_skin.loose-f": "loose empty folds of skin on the body",
    "arms.forearms-m": "thick strong forearms with ropy tendons",
    "hands.stained": "hands stained dark in the skin creases",
    "hands.crooked": "one crooked finger bent at a knuckle",
    "nails.stained-betel-f": "reddish-brown stained fingertips",
    "legs.calves-m": "big hard knotted calves",
    "legs.cyclist-m": "lean sinewy legs with hard calves and thighs",
    "feet.calloused": "thick hard calloused soles",
    "feet.splayed": "toes spread wide apart",
    "feet.water-feet": "pale puckered wrinkled skin on the feet",
    "posture.desk-hunch": "hunched upper back, head and shoulders forward",
    "posture.labour-bent": "permanently stooped forward at the waist",
    "gait.rolling-sailor": "wide rolling side-to-side gait, feet planted apart",
    "gait.load-trot": "quick short jogging trot with bent knees",
    "hips.augmented-f": "unnaturally round high lifted buttocks",
}

# ---------------------------------------------------------------- new age baselines (bug 1)
# id: (sex, age, phrase, vi, spec)
NEW = {
    "muscle.normal-old-m": ("male", [65, 120], "ordinary older muscle tone, slightly slack", "cơ người già bình thường, hơi nhão", "m1-2"),
    "muscle.normal-old-f": ("female", [65, 120], "ordinary older muscle tone, slightly slack", "cơ người già bình thường, hơi nhão", "m1-2"),
    "shoulders.normal-old-m": ("male", [65, 120], "average older shoulders, slightly narrowed and sloping", "vai người già bình thường, hơi hẹp và xuôi", ""),
    "shoulders.normal-old-f": ("female", [65, 120], "narrow softly sloping older shoulders", "vai người già bình thường, hẹp, xuôi", ""),
    "chest.normal-old-m": ("male", [65, 120], "flat older chest with slightly loose skin", "ngực người già bình thường, da hơi chùng", "f1-5"),
    "chest.normal-old-f": ("female", [65, 120], "soft lowered breasts of an older woman", "ngực người già bình thường, mềm, thấp", ""),
    "waist_belly.normal-old-m": ("male", [65, 120], "older male waist, belly a little soft", "eo bụng người già bình thường, bụng hơi mềm", "f2-5"),
    "waist_belly.normal-old-f": ("female", [65, 120], "thickened older waist, softly rounded belly", "eo người già dày ra, bụng hơi tròn", "f2-6"),
    "hips.normal-old-m": ("male", [65, 120], "narrow male hips, flatter older buttocks", "hông nam hẹp, mông người già phẳng hơn", ""),
    "hips.normal-old-f": ("female", [65, 120], "medium hips, flatter softer older buttocks", "hông vừa, mông người già phẳng mềm hơn", ""),
    "back.normal-old": ("any", [65, 120], "back slightly rounded at the top", "lưng trên hơi tròn của người già", "s1-2"),
    "arms.normal-old-m": ("male", [65, 120], "thinner older arms, skin slightly loose", "tay người già gầy hơn, da hơi chùng", "f0-5"),
    "hands.normal-old": ("any", [65, 120], "older hands, thin skin and visible veins", "bàn tay người già, da mỏng, lộ gân", ""),
    "legs.normal-old-m": ("male", [65, 120], "ordinary older legs with thinner calves", "chân người già bình thường, bắp chân gầy hơn", ""),
    "legs.normal-old-f": ("female", [65, 120], "ordinary older legs, soft thighs, thinner calves", "chân người già bình thường, đùi mềm, bắp chân gầy", ""),
    "posture.normal-old": ("any", [65, 120], "ordinary older stance with a slight forward lean", "dáng đứng người già bình thường, hơi đổ về trước", "s1-2"),
    "gait.normal-old": ("any", [65, 120], "steady unhurried walk with shorter steps", "đi chậm rãi vững, bước ngắn hơn", ""),
}
# slot -> {sex: {band: baseline id}}
def _bl(m, f, m_old=None, f_old=None):
    out = {"male": {b: m for b in BANDS}, "female": {b: f for b in BANDS}}
    if m_old:
        out["male"]["elderly"] = m_old
    if f_old:
        out["female"]["elderly"] = f_old
    return out
BASELINE = {
    "height": _bl("height.normal-m", "height.normal-f"),
    "frame": _bl("frame.normal-m", "frame.normal-f"),
    "fat": _bl("fat.normal-m", "fat.normal-f"),
    "muscle": _bl("muscle.normal-m", "muscle.normal-f", "muscle.normal-old-m", "muscle.normal-old-f"),
    "fat_where": _bl("fat_where.normal-m", "fat_where.normal-f"),
    "shoulders": _bl("shoulders.normal-m", "shoulders.normal-f", "shoulders.normal-old-m", "shoulders.normal-old-f"),
    "chest": _bl("chest.normal-m", "chest.normal-f", "chest.normal-old-m", "chest.normal-old-f"),
    "waist_belly": _bl("waist_belly.normal-m", "waist_belly.normal-f", "waist_belly.normal-old-m", "waist_belly.normal-old-f"),
    "hips": _bl("hips.normal-m", "hips.normal-f", "hips.normal-old-m", "hips.normal-old-f"),
    "back": _bl("back.normal", "back.normal", "back.normal-old", "back.normal-old"),
    "body_skin": _bl("body_skin.normal-m", "body_skin.normal-f", "body_skin.crepey-m", "body_skin.crepey-f"),
    "arms": _bl("arms.normal-m", "arms.normal-f", "arms.normal-old-m", "arms.crepey-f"),
    "hands": _bl("hands.normal-m", "hands.normal-f", "hands.normal-old", "hands.normal-old"),
    "nails": _bl("nails.normal", "nails.normal"),
    "legs": _bl("legs.normal-m", "legs.normal-f", "legs.normal-old-m", "legs.normal-old-f"),
    "feet": _bl("feet.normal", "feet.normal-f"),
    "posture": _bl("posture.normal", "posture.normal", "posture.normal-old", "posture.normal-old"),
    "gait": _bl("gait.normal", "gait.normal", "gait.normal-old", "gait.normal-old"),
}

# ---------------------------------------------------------------- hidden axes + regions (bug 2)
# f=fat 0-7, m=muscle 0-4, F=frame 0-4, s=spine 0-3; r:region,region
SPEC = """
height.gangly-m f1-3 m1-2
frame.normal-m F2-2
frame.small-m F0-1
frame.narrow-m F1-1 f0-3
frame.broad-m F3-4
frame.stocky-m F3-4 f2-7 m2-4
frame.barrel-m F3-4 f3-7
frame.pyramid-m F1-3
frame.wedge-m F2-4 m2-4
frame.angular-m f0-2
frame.normal-f F2-2
frame.small-f F0-1
frame.narrow-f F1-1 f0-3
frame.broad-f F3-4
frame.sturdy-f F3-4 f2-7 m2-4
frame.pear-f F1-3
frame.wideshoulder-f F2-4
frame.angular-f f0-2
fat.normal-m f3-3
fat.emaciated-m f0-0 m0-2
fat.very-thin-m f1-1
fat.thin-m f2-2 F0-2
fat.lean-m f2-2
fat.softish-m f4-4
fat.chubby-m f4-5
fat.skinnyfat-m f3-4 r:belly
fat.overweight-m f5-5 r:belly
fat.stout-m f5-5 F2-4
fat.obese-m f6-6
fat.very-obese-m f7-7
fat.gaunt-ill-m f0-1 m0-1
fat.bloated-m f4-6
fat.normal-f f3-3
fat.emaciated-f f0-0 m0-2
fat.very-thin-f f1-1
fat.thin-f f2-2 F0-2
fat.lean-f f2-2 m2-3
fat.plump-f f4-5
fat.skinnyfat-f f3-4 r:belly
fat.overweight-f f5-5 r:belly,hips
fat.stout-f f5-5 F2-4
fat.obese-f f6-6
fat.very-obese-f f7-7
fat.gaunt-ill-f f0-1 m0-1
fat.loose-after-loss-f f2-4 r:loose_skin
fat.loose-after-loss-m f2-4 r:loose_skin
muscle.normal-m m2-2
muscle.slack-m m0-1
muscle.soft-m m1-1
muscle.wiry-m m3-3 f1-3
muscle.ropy-labour-m m3-3 f1-3
muscle.thick-labour-m m3-4 f2-5
muscle.toned-m m3-3 f2-3
muscle.athletic-m m3-4 f2-4
muscle.gym-bulky-m m4-4 f2-5
muscle.bodybuilder-m m4-4 f2-4
muscle.overbuilt-m m4-4 f2-3
muscle.padded-strong-m m3-3 f4-5
muscle.powerlifter-m m4-4 f4-6 r:belly
muscle.runner-m m3-3 f1-2
muscle.swimmer-m m3-4 f2-4
muscle.gone-soft-m m2-2 f4-5
muscle.onesided-m m3-4
muscle.old-strong-m m3-3 f1-3
muscle.normal-f m2-2
muscle.slack-f m0-1
muscle.soft-f m1-1
muscle.slight-f m1-2 f1-3
muscle.toned-f m3-3 f2-3
muscle.athletic-f m3-4 f2-4
muscle.gym-muscular-f m4-4 f2-3
muscle.bodybuilder-f m4-4 f1-3
muscle.dancer-f m3-3 f1-2
muscle.farm-strong-f m3-3 f2-5
muscle.wiry-f m3-3 f1-2
muscle.strong-legs-f m2-3
muscle.gone-soft-f m1-2 f3-5
muscle.old-strong-f m3-3 f1-3
fat_where.normal-m f3-7
fat_where.none-m f0-2
fat_where.belly-m f4-7 r:belly
fat_where.visceral-m f3-5 r:belly
fat_where.flanks-m f4-7 r:flanks
fat_where.chest-m f4-7 r:chest
fat_where.neck-face-m f4-7 r:neck
fat_where.nape-m f4-7 r:upper_back
fat_where.lowback-m f4-7 r:lower_back
fat_where.saghip-m f4-7 r:hips
fat_where.seat-m f4-7 r:buttocks,thighs
fat_where.knees-m f4-7 r:knees
fat_where.normal-f f3-7
fat_where.none-f f0-2
fat_where.pear-f f4-7 r:hips,thighs
fat_where.apple-f f4-7 r:belly
fat_where.pooch-f f3-6 r:belly
fat_where.flanks-f f4-7 r:flanks
fat_where.bust-f f4-7 r:chest
fat_where.upperarm-f f4-7 r:upper_arms
fat_where.backroll-f f4-7 r:upper_back
fat_where.saddle-f f4-7 r:thighs
fat_where.innerthigh-f f4-7 r:thighs
fat_where.buttocks-f f4-7 r:buttocks
fat_where.neck-f f4-7 r:neck
fat_where.knees-f f4-7 r:knees
fat_where.lipedema-f f3-7 r:thighs,calves
shoulders.broad-m F2-4
shoulders.very-broad-m F3-4 m3-4
shoulders.narrow-m F0-2
shoulders.rounded-m s1-2
shoulders.bony-m f0-2
shoulders.traps-m m3-4
shoulders.pole-m m2-4
shoulders.fleshy-m f4-7
shoulders.delts-m m3-4 f1-4
shoulders.drooping-m m0-2
shoulders.winged-m f0-3 r:shoulder_blades
shoulders.narrow-f F0-2
shoulders.broad-f F2-4
shoulders.bony-f f0-2
shoulders.rounded-f s1-2
shoulders.fleshy-f f4-7
shoulders.load-f m3-4
shoulders.swimmer-f m3-4 f1-3
shoulders.blades-f f0-3 r:shoulder_blades
shoulders.drooping-f m0-2
chest.normal-m f1-5
chest.sunken-m r:chest
chest.pigeon-m r:chest
chest.thin-m f0-1 r:chest
chest.narrow-m F0-2 r:chest
chest.barrel-m F2-4 r:chest
chest.muscular-m m3-4 f1-4 r:chest
chest.gym-pecs-m m4-4 f1-3 r:chest
chest.overbuilt-m m4-4 f1-3 r:chest
chest.labour-m m3-4 f2-5 r:chest
chest.soft-m f4-7 m0-2 r:chest
chest.moobs-m f5-7 r:chest
chest.gyno-m f1-3 r:chest
chest.sagging-m f2-5 m0-2 r:chest
chest.bony-old-m f0-2 r:chest
chest.uneven-m r:chest
chest.flat-f f0-4 r:chest
chest.small-f r:chest
chest.small-high-f r:chest
chest.full-f f3-7 r:chest
chest.very-large-f f4-7 r:chest
chest.wide-set-f r:chest
chest.low-set-f r:chest
chest.slight-droop-f r:chest
chest.sagging-f r:chest
chest.deflated-f f1-4 r:chest
chest.pendulous-f r:chest
chest.uneven-f r:chest
chest.tuberous-f r:chest
chest.implants-f r:chest
chest.old-implant-f r:chest
chest.bony-f f0-1 r:chest
chest.athletic-f m3-4 f1-3 r:chest
waist_belly.normal-m f1-4
waist_belly.sixpack-m f1-2 m3-4 r:belly
waist_belly.lean-flat-m f1-2 r:belly
waist_belly.vtaper-m m3-4 f1-3
waist_belly.thick-m F2-4 f3-6
waist_belly.soft-m f4-6 r:belly
waist_belly.beer-m f4-6 r:belly
waist_belly.gut-m f5-7 r:belly
waist_belly.loves-m f4-6 r:flanks
waist_belly.pot-thin-m f2-4 r:belly
waist_belly.hollow-m f0-1 r:belly
waist_belly.rolls-m f5-7 r:belly
waist_belly.loose-m f2-5 r:belly
waist_belly.twopack-m f1-3 m3-3 r:belly
waist_belly.normal-f f2-5
waist_belly.narrow-f f1-3
waist_belly.thick-meno-f f3-6
waist_belly.soft-f f3-6 r:belly
waist_belly.pooch-f f3-6 r:belly
waist_belly.diastasis-f r:belly
waist_belly.apron-f f5-7 r:belly
waist_belly.toned-f f1-3 m3-3 r:belly
waist_belly.abs-f f1-2 m3-4 r:belly
waist_belly.apple-f f4-7 r:belly
waist_belly.muffin-f f4-6 r:flanks
waist_belly.rolls-f f5-7 r:belly
waist_belly.hollow-f f0-1 r:belly
waist_belly.lownavel-f f5-7 r:belly
waist_belly.loose-f f2-5 r:belly
hips.muscular-m m3-4
hips.wide-m F2-4
hips.heavy-m f5-7 r:buttocks
hips.bony-m f0-2
hips.dimples-m f1-3
hips.overhang-m f4-7 r:flanks
hips.tight-m f1-3
hips.pear-m f4-6 r:hips
hips.bony-old-m f0-2
hips.thighheavy-m f3-6 r:thighs
hips.narrow-f F0-2
hips.very-wide-f r:thighs
hips.large-f f4-7 r:buttocks
hips.saddle-f f4-7 r:thighs
hips.dimples-f f1-3
hips.bony-old-f f0-2
hips.diamond-f f4-6 r:lower_back
back.normal s0-1
back.hunch s1-2
back.kyphosis s3-3
back.hump-f s2-3
back.fieldbent s2-3
back.sway s0-1
back.flat s0-0
back.vback-m m3-4 f1-3 s0-1
back.broad-m m3-4 F2-4
back.columns m3-4 f1-3
back.bony f0-1
back.blades f0-2 r:shoulder_blades
back.rolls f5-7 r:upper_back,lower_back
back.slim-f f1-3
back.stiff s0-2
posture.normal s0-1
posture.upright s0-0
posture.rigid s0-0
posture.slouched s1-2
posture.desk-hunch s1-2
posture.headforward s1-2
posture.stooped-old s2-3
posture.labour-bent s2-3
posture.chestout-m s0-0
posture.bellyfwd f4-7
posture.shouldersfwd s1-2
posture.weary s1-2
posture.neck-lifted-f s0-0
arms.skinny-m f0-3
arms.wiry-m f0-3 m2-4
arms.forearms-m m3-4
arms.muscular-m m3-4 f1-4
arms.biceps-m m4-4 f1-4
arms.huge-m m4-4 f1-3
arms.soft-m f4-7 m0-2 r:upper_arms
arms.fat-m f5-7 r:upper_arms
arms.loose-m f1-5 r:upper_arms
arms.stick-m f0-2 m0-2
arms.thin-f f0-2
arms.soft-f f3-6 r:upper_arms
arms.heavy-f f5-7 r:upper_arms
arms.batwing-f r:upper_arms
arms.toned-f m3-3 f1-3
arms.muscular-f m4-4 f1-3
arms.forearms-f m3-4
arms.wiry-f m3-3 f0-2
arms.plump-f f4-6
arms.long-f f0-3
arms.stick-f f0-2
hands.plump f4-7
hands.sausage f5-7
hands.old-thin f0-4
hands.veiny f0-4
legs.skinny-m f0-3
legs.chicken-m f3-7
legs.thighs-m m3-4 r:thighs
legs.calves-m m3-4 r:calves
legs.cyclist-m m3-3 f1-3 r:calves
legs.heavy-m f5-7 r:thighs
legs.knobbly-m f0-3 r:knees
legs.long-f f0-4
legs.short-f f3-6 r:thighs
legs.thighs-touch-f f4-7 r:thighs
legs.thin-f f0-2 r:thighs
legs.calves-f r:calves
legs.cankles-f f4-7
legs.athletic-f m3-4 r:thighs,calves
legs.fatknees-f f5-7 r:knees
legs.knobbly-f f0-3 r:knees
legs.heavy-f f5-7 r:thighs,calves
body_skin.loose-m r:loose_skin
body_skin.loose-f r:loose_skin
"""

# salience: default plain (baseline) / mild (old freq common) / marked (else). Overrides:
SAL_MARKED = {"back.kyphosis", "fat_where.visceral-m", "waist_belly.gut-m", "fat.very-thin-m", "fat.very-thin-f"}
# frequency/salience changes for the elderly band (features that become ordinary, or stop being ordinary, with age)
ELDER_COMMON_MILD = {"legs.varicose-m", "nails.ridged", "feet.bunion", "feet.hammer", "feet.toenails", "muscle.slack-m",
                     "muscle.slack-f", "body_skin.spots-m", "body_skin.spots-f", "hands.spots", "hands.veiny",
                     "legs.varicose-f", "gait.heavy"}
ELDER_COMMON = {"hands.arthritic"}                    # common when old but still noticeable
ELDER_UNCOMMON_MARKED = {"muscle.ropy-labour-m", "muscle.thick-labour-m", "muscle.wiry-m"}

RULES = [
    ("R0001", "frame.pyramid-m", ["shoulders.broad-m", "shoulders.very-broad-m", "shoulders.square-m"], "narrow-shouldered frame vs broad shoulders"),
    ("R0002", "frame.wedge-m", ["shoulders.narrow-m", "hips.wide-m"], "wide-shouldered narrow-hipped frame vs narrow shoulders or wide hips"),
    ("R0003", "frame.pear-f", ["shoulders.broad-f"], "narrow-shouldered frame vs broad shoulders"),
    ("R0004", "frame.wideshoulder-f", ["shoulders.narrow-f", "hips.wide-f", "hips.very-wide-f"], "broad-shouldered narrow-hipped frame vs narrow shoulders or wide hips"),
    ("R0005", "height.dwarf-m", ["legs.long-m"], "dwarfism means short limbs"),
    ("R0006", "height.dwarf-f", ["legs.long-f"], "dwarfism means short limbs"),
    ("R0007", "legs.wasted-m", ["gait.bouncy", "gait.loping", "gait.brisk", "gait.swagger-m"], "a wasted leg does not give a springy or long stride"),
    ("R0008", "muscle.onesided-m", ["arms.onesided-m"], "the same uneven arm described twice"),
    ("R0009", "posture.stooped-old", ["posture.upright", "gait.bouncy"], "stooped vs upright or bouncy"),
    ("R0010", "back.scoliosis", ["back.lean-sideways"], "the same sideways spine described twice"),
]

GOLDEN = [
    {"sex": "male", "age": 40, "picks": {"frame": "frame.stocky-m", "chest": "chest.thin-m"}, "expect": "conflict", "note": "observed bug: stocky frame + ribs showing"},
    {"sex": "male", "age": 55, "picks": {"fat_where": "fat_where.visceral-m", "waist_belly": "waist_belly.beer-m"}, "expect": "conflict", "note": "belly twice"},
    {"sex": "male", "age": 55, "picks": {"fat": "fat.skinnyfat-m", "fat_where": "fat_where.belly-m", "waist_belly": "waist_belly.pot-thin-m"}, "expect": "conflict", "note": "observed bug: three bellies"},
    {"sex": "male", "age": 70, "picks": {"back": "back.normal", "posture": "posture.stooped-old"}, "expect": "conflict", "note": "observed bug: straight back + stooped"},
    {"sex": "male", "age": 30, "picks": {"muscle": "muscle.bodybuilder-m", "fat": "fat.emaciated-m"}, "expect": "conflict"},
    {"sex": "male", "age": 50, "picks": {"chest": "chest.moobs-m", "fat": "fat.very-thin-m"}, "expect": "conflict"},
    {"sex": "male", "age": 30, "picks": {"posture": "posture.upright", "back": "back.hunch"}, "expect": "conflict"},
    {"sex": "male", "age": 70, "picks": {"legs": "legs.knobbly-m", "fat_where": "fat_where.knees-m"}, "expect": "conflict"},
    {"sex": "female", "age": 40, "picks": {"frame": "frame.wideshoulder-f", "hips": "hips.wide-f"}, "expect": "conflict"},
    {"sex": "male", "age": 70, "picks": {"height": "height.shrunken-m", "muscle": "muscle.ropy-labour-m", "body_skin": "body_skin.leathery-m",
     "hands": "hands.calloused", "legs": "legs.knobbly-m", "posture": "posture.stooped-old", "gait": "gait.shuffle"}, "expect": "ok", "note": "Lao Bay v1 picks"},
    {"sex": "male", "age": 40, "picks": {"frame": "frame.stocky-m", "fat": "fat.lean-m", "muscle": "muscle.thick-labour-m"}, "expect": "ok"},
    {"sex": "male", "age": 50, "picks": {"fat": "fat.overweight-m", "chest": "chest.soft-m", "arms": "arms.soft-m"}, "expect": "ok"},
    {"sex": "female", "age": 35, "picks": {"fat": "fat.plump-f", "hips": "hips.wide-f", "chest": "chest.full-f"}, "expect": "ok"},
    {"sex": "male", "age": 70, "picks": {"fat": "fat.thin-m"}, "expect": "covers", "covers": ["fat_where"], "note": "thin body: 'fat spread evenly' baseline must drop"},
    {"sex": "male", "age": 70, "picks": {"posture": "posture.rigid"}, "expect": "covers", "covers": ["back"], "note": "upright old man: rounded-back baseline must drop"},
]

SOURCES = {
    "the-art-of-aesthetic-surgery-principles-and-techniques": "aesthetic_surgery",
    "anatomy-for-sculptors-understanding-the-human-figure": "anatomy_sculptors",
    "force-character-design-from-life-drawing": "force_drawing",
    "picture-perfect-posing-practicing-the-art-of-posing-for-phot": "picture_perfect_posing",
    "the-photographers-guide-to-posing-techniques-to-flatter-ever": "photographers_posing",
    "reading-faces-window-to-the-soul": "reading_faces",
    "the-magic-garment-principles-of-costume-design": "magic_garment",
    "figure-drawing-for-all-its-worth": "loomis_figure",
}


def parse_spec():
    out = {}
    for line in SPEC.strip().splitlines():
        parts = line.split()
        vid, dims, regions = parts[0], {}, []
        for p in parts[1:]:
            if p.startswith("r:"):
                regions = p[2:].split(",")
            else:
                key = {"f": "fat", "m": "muscle", "F": "frame", "s": "spine"}[p[0]]
                lo, hi = p[1:].split("-")
                dims[key] = [int(lo), int(hi)]
        if vid in out:
            raise SystemExit("dup spec " + vid)
        out[vid] = (dims, regions)
    return out


def age_range(bands):
    order = ["young", "adult", "middle", "elderly"]
    idx = sorted(order.index(b) for b in bands)
    return [BANDS[order[idx[0]]][0], BANDS[order[idx[-1]]][1]]


def main():
    cards_path = Path(sys.argv[1])
    old = json.loads((KB / "body.json").read_text(encoding="utf-8"))
    spec = parse_spec()
    base_of = {}  # id -> [group keys]
    for slot, sx in BASELINE.items():
        for sex, bands in sx.items():
            for band, vid in bands.items():
                base_of.setdefault(vid, []).append(f"{sex}-{band}")
    used_spec = set()
    catalog, vi, cited = {}, [], set()
    slots_meta = []
    for slot, sd in old["slots"].items():
        slots_meta.append((slot, sd["group"], sd["vi"]))
        rows = []
        for v in sd["values"]:
            vid = v["id"]
            causes = sorted({CAUSE_MAP[c] for c in v["causes"]})
            fq = {"common": "common", "uncommon": "uncommon", "rare": "rare"}[v["freq"]]
            freq = [{"cls": fq, "basis": "est"}]
            if vid in base_of:
                sal = [{"s": "plain"}]
            elif vid in SAL_MARKED:
                sal = [{"s": "marked"}]
            else:
                sal = [{"s": "mild" if fq == "common" else "marked"}]
            # ex-baseline values that are no longer ordinary for the elderly
            if vid in base_of and not any(g.endswith("elderly") for g in base_of[vid]) and "elderly" in v["ages"]:
                freq.append({"when": {"band": "elderly"}, "cls": "uncommon", "basis": "est"})
                sal.append({"when": {"band": "elderly"}, "s": "mild"})
            if vid in ELDER_COMMON_MILD:
                freq.append({"when": {"band": "elderly"}, "cls": "common", "basis": "est"})
                sal.append({"when": {"band": "elderly"}, "s": "mild"})
            if vid in ELDER_COMMON:
                freq.append({"when": {"band": "elderly"}, "cls": "common", "basis": "est"})
            if vid in ELDER_UNCOMMON_MARKED:
                freq.append({"when": {"band": "elderly"}, "cls": "uncommon", "basis": "est"})
                sal.append({"when": {"band": "elderly"}, "s": "marked"})
            dims, regions = spec.get(vid, ({}, []))
            if vid in spec:
                used_spec.add(vid)
            ev = [{"c": c, "rel": "supports"} for c in v["src"] if c != "general"]
            cited.update(e["c"] for e in ev)
            phrase = REPHRASE.get(vid, v["phrase"])
            row = OrderedDict([("id", vid), ("slot", slot), ("status", "active"), ("sex", v["sex"]),
                               ("age", age_range(v["ages"])), ("phrase", phrase), ("causes", causes),
                               ("freq", freq), ("sal", sal), ("baseline_for", sorted(base_of.get(vid, []))),
                               ("dims", dims), ("regions", regions), ("ev", ev), ("since", 1),
                               ("rev", 2 if vid in REPHRASE else 1)])
            rows.append(row)
            vi.append({"id": vid, "vi": v["vi"]})
        for vid, (sex, age, phrase, vtext, sp) in NEW.items():
            if not vid.startswith(slot + "."):
                continue
            dims = {}
            for p in sp.split():
                key = {"f": "fat", "m": "muscle", "F": "frame", "s": "spine"}[p[0]]
                lo, hi = p[1:].split("-")
                dims[key] = [int(lo), int(hi)]
            rows.append(OrderedDict([("id", vid), ("slot", slot), ("status", "active"), ("sex", sex), ("age", age),
                                     ("phrase", phrase), ("causes", ["ageing"]),
                                     ("freq", [{"cls": "common", "basis": "est"}]), ("sal", [{"s": "plain"}]),
                                     ("baseline_for", sorted(base_of.get(vid, []))), ("dims", dims), ("regions", []),
                                     ("ev", []), ("since", 2), ("rev", 1)]))
            vi.append({"id": vid, "vi": vtext})
        catalog[slot] = sorted(rows, key=lambda r: r["id"])
    missing = set(spec) - used_spec - set(NEW)
    if missing:
        raise SystemExit(f"spec ids not in catalog: {sorted(missing)}")
    missing_bl = set(base_of) - {r["id"] for rs in catalog.values() for r in rs}
    if missing_bl:
        raise SystemExit(f"baseline ids missing: {sorted(missing_bl)}")

    (KB / "catalog").mkdir(exist_ok=True)
    for slot, rows in catalog.items():
        with (KB / "catalog" / f"{slot}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=True) + "\n")

    # vocab
    order = [s for s, _, _ in slots_meta]
    vocab = OrderedDict([
        ("schema", 2),
        ("slots", OrderedDict((s, {"group": g, "order": i, "required_in_prompt": s in ("height", "frame", "fat"),
                                   "multi": False}) for i, (s, g, _) in enumerate(slots_meta))),
        ("groups", {"A": "overall build", "D": "torso", "E": "arms and hands", "F": "legs and feet", "G": "posture and gait"}),
        ("sexes", ["male", "female", "any"]),
        ("age_bands", BANDS),
        ("age_limits", [18, 120]),
        ("causes", CAUSES),
        ("cause_map_v1", CAUSE_MAP),
        ("freq_classes", ["common", "uncommon", "rare"]),
        ("freq_thresholds", {"common": 0.10, "uncommon": 0.02, "note": "share of people in the same sex x age band x population; rare below uncommon"}),
        ("freq_basis", ["stat", "proxy", "est"]),
        ("salience", {"plain": "nobody would notice", "mild": "noticeable on a close look, not memorable",
                      "marked": "people remember it"}),
        ("when_keys", ["sex", "band"]),
        ("dims", OrderedDict([
            ("fat", {"range": [0, 7], "scale": "0 emaciated, 1 very thin, 2 thin/lean, 3 average, 4 soft, 5 overweight, 6 obese, 7 severely obese"}),
            ("muscle", {"range": [0, 4], "scale": "0 wasted, 1 soft, 2 ordinary, 3 firm/hard, 4 bulky"}),
            ("frame", {"range": [0, 4], "scale": "0 small, 1 narrow, 2 medium, 3 broad/stocky, 4 heavy"}),
            ("spine", {"range": [0, 3], "scale": "0 upright, 1 slightly rounded, 2 stooped, 3 strongly bent"}),
        ])),
        ("regions", ["belly", "flanks", "chest", "upper_back", "lower_back", "hips", "buttocks", "thighs", "knees", "calves",
                     "upper_arms", "neck", "shoulder_blades", "loose_skin"]),
        ("statuses", ["active", "merged", "split", "deprecated"]),
        ("ev_rel", ["describes", "supports", "freq"]),
        ("budget", {"call_tokens": 3500, "menu_k": 14, "chars_per_token": 3.5}),
    ])
    (KB / "vocab.json").write_text(json.dumps(vocab, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")

    with (KB / "vi.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for s, _, v in slots_meta:
            fh.write(json.dumps({"id": s, "vi": v}, ensure_ascii=False) + "\n")
        for r in sorted(vi, key=lambda r: r["id"]):
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # evidence: copy cited cards, one file per source
    cards = {}
    for line in cards_path.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d["cid"] in cited:
            cards[d["cid"]] = d
    if set(cited) - set(cards):
        raise SystemExit(f"cards not found: {sorted(set(cited) - set(cards))}")
    (KB / "evidence").mkdir(exist_ok=True)
    by_src = {}
    for cid in sorted(cards):
        d = cards[cid]
        src = SOURCES[d["slug"]]
        by_src.setdefault(src, []).append(OrderedDict([
            ("id", cid), ("source", src), ("kind", d.get("kind")), ("text", d.get("statement")),
            ("condition", d.get("condition") or ""), ("quote", d.get("quote") or ""), ("about", d.get("about") or []),
            ("loc", ",".join(s["id"] for s in d.get("src", []))), ("status", "active")]))
    for src, rows in by_src.items():
        with (KB / "evidence" / f"{src}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    with (KB / "sources.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for slug, sid in SOURCES.items():
            fh.write(json.dumps(OrderedDict([
                ("id", sid), ("kind", "book"), ("title_slug", slug), ("license_needed", False),
                ("terms", "owned copy, private non-commercial research; cards are short paraphrases with brief quotes"),
                ("retrieved", "2026-11 (via ebook_maker card lane build1, copied)"), ("raw", None),
                ("n_cards", len(by_src.get(sid, []))), ("status", "active")])) + "\n")

    with (KB / "rules.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for rid, a, bs, why in RULES:
            fh.write(json.dumps(OrderedDict([("id", rid), ("kind", "exclude"), ("a", a), ("b", bs), ("why", why),
                                             ("status", "active"), ("since", 2)])) + "\n")

    (KB / "tests").mkdir(exist_ok=True)
    with (KB / "tests" / "golden.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for g in GOLDEN:
            fh.write(json.dumps(g) + "\n")
    print("catalog", sum(len(r) for r in catalog.values()), "values;", len(cards), "cards in", len(by_src), "sources")


if __name__ == "__main__":
    main()
