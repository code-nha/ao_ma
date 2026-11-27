"""Thử cách viết thân người trong prompt Qwen (2026-11-26): Lão Bảy 70 tuổi cứ bị vẽ gầy yếu dù LOOK là "thấp đậm, cơ rắn".

    python -I body_prompt_test.py [--render] [--server http://senlab:8188] [--api http://wee:11435]

Mỗi biến thể đổi phần thân (và có biến thể bỏ cụm mặt kéo về già yếu), 2 seed như look_loop. Không có --render thì chỉ in
prompt. Ảnh vào experiments/look_loop/lao_bay/body_test_<ts>/; mắt tả mù (look_loop.SYS_DESC / SYS_CMP) chấm frame, muscle, arms.
Ghi experiments/logs/body_prompt_test.jsonl.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # python -I drops the script dir
RENDER = "--render" in sys.argv
if RENDER:
    sys.argv.remove("--render")
sys.argv = [sys.argv[0], "lao_bay"] + sys.argv[1:]
import look_loop as L  # noqa: E402  (parses --server/--api)

OPEN = ("The image is a vertical documentary photograph of one 70-year-old Vietnamese man, standing, front view, framed from the "
        "top of the head to the knees, arms relaxed at the sides, both hands fully in frame, plain grey short-sleeved t-shirt and "
        "plain dark trousers, plain light background, soft daylight, realistic unretouched skin. ")
FACE_OLD = ("face: older face, sunken temples, loose jawline; eyes held narrowed, peering; dry cracked lips; brown tobacco-stained "
            "teeth; large ears for the head size; deep brown sun-darkened skin; thick leathery face skin, deep creases; deep "
            "vertical frown lines between the brows; almost hairless face, no beard growth | hair: mostly grey hair")
FACE_BROAD = FACE_OLD.replace("older face, sunken temples, loose jawline", "older face, broad weathered face")
BODY_CONCRETE = ("overall: short man, below average height; broad thick-set body, wide shoulders, deep barrel chest, thick neck, "
                 "solid heavy torso; hard lean muscle on the shoulders and upper arms")
ARMS_CONCRETE = "body: thick forearms with raised veins and tendons"
VITAL = "He looks strong and vigorous for his age, a man who still does heavy physical work every day. "

VARIANTS = {
    "v0_current": ("overall: short man, below average height; short stocky square-built frame; hard ropy muscles, lean and corded | "
                   + FACE_OLD + " | body: wiry veiny forearms"),
    "v1_concrete": BODY_CONCRETE + " | " + FACE_OLD + " | " + ARMS_CONCRETE,
    "v2_concrete_broadface": BODY_CONCRETE + " | " + FACE_BROAD + " | " + ARMS_CONCRETE,
    "v3_concrete_vital": VITAL + BODY_CONCRETE + " | " + FACE_OLD + " | " + ARMS_CONCRETE,
}
CHECK = {"frame": "short stocky square-built frame", "muscle": "hard ropy muscles, lean and corded",
         "arms": "wiry veiny forearms", "fat": "average weight, neither thin nor fat"}


def eye(png):
    parts = "BODY PARTS\n" + "\n".join(f"{s}: {L.PART[s]}" for s in CHECK)
    sch = {"type": "object", "properties": {"sex": {"type": "string"}, "age": {"type": "integer"}, "parts": {
        "type": "object", "properties": {s: {"type": "string", "maxLength": 160} for s in CHECK}, "required": list(CHECK)}},
           "required": ["sex", "age", "parts"]}
    d, _ = L.call(L.SYS_DESC, parts, sch, [png])
    got = d.get("parts", {})
    c, _ = L.call(L.SYS_CMP, "\n".join(f"{s}: intended \"{CHECK[s]}\" | observer: \"{got.get(s, '')}\"" for s in CHECK),
                  {"type": "object", "properties": {s: {"type": "string", "enum": L.SEEN} for s in CHECK},
                   "required": list(CHECK)})
    return d, c


def main():
    names = [n for n in VARIANTS if n != "v0_current"]       # v0 = what look_loop already rendered; kept for reference
    for n in VARIANTS:
        print(f"== {n}\n{OPEN + VARIANTS[n]}\n")
    if not RENDER:
        return
    run = L.ROOT / "experiments" / "look_loop" / "lao_bay" / time.strftime("body_test_%Y%m%d_%H%M%S")
    run.mkdir(parents=True)
    painter = L.Painter()
    log = (L.ROOT / "experiments" / "logs" / "body_prompt_test.jsonl").open("a", encoding="utf-8")
    for n in names:
        prompt = OPEN + VARIANTS[n]
        for i, seed in enumerate(L.SEEDS, 1):
            png = run / f"{n}_s{i}.png"
            secs = painter.render(prompt, seed, png, f"lao_bay_{run.name}_{n}_s{i}")
            d, c = eye(png)
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "variant": n, "seed": seed, "png": str(png.relative_to(L.ROOT)),
                   "prompt": prompt, "render_secs": secs, "age": d.get("age"), "describe": d.get("parts"), "compare": c}
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log.flush()
            print(n, i, "age", d.get("age"), c, "|", (d.get("parts") or {}).get("frame", "")[:90], flush=True)


if __name__ == "__main__":
    main()
