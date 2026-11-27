"""Vòng ảnh LOOK: nhân vật nhìn ảnh của mình và tự quyết định ngoại hình (tối đa 5 vòng, nhân vật biết giới hạn này).

    python -I look_loop.py lao_bay [--rounds 5] [--story <story>] [--server http://senlab:8188] [--api http://wee:11435]

Cần LOOK.kb.json từ luan_hoi.py. Mỗi vòng k:
  1 code ghép prompt Qwen = câu mở (đứng, từ đầu tới gối, thấy rõ hai tay, áo trơn, nền trơn) + câu nhấn (<= 3 ô) + LOOK
  2 render 2 seed cố định trên ComfyUI senlab (tuần tự, lưu vào output/nhan_vat/)
  3 MẮT, tả mù rồi so (2026-11-25, xem eval_eye.py): lời gọi 1 (vision, không thấy LOOK) tả giới, tuổi, đẹp hóa không và từng
    bộ phận so với người cùng tuổi cùng giới; lời gọi 2 (text, không ảnh) so lời tả với cụm LOOK từng ô -> yes / partly / no /
    not visible. Đọc sẵn LOOK rồi hỏi "có thấy không" thì model dễ gật. Không hỏi dân tộc: model không phân được.
  4 code: cổng (giới đúng, tuổi lệch <= 10, không đẹp hóa) + điểm (ô nhận diện x2, ô khác x1), điểm chỉ để tham khảo
  5 NHÂN VẬT (Gemma vision, nhập vai, thấy ảnh + bảng "mình là / mắt thấy", biết còn bao nhiêu lượt): đây có phải mình không;
    sửa tối đa 3 ô: emphasize (đúng nét nhưng ảnh không ra: code nhấn trong prompt), repick (muốn giá trị khác: chọn lại từ kho
    nét qua luan_hoi.py --redo, đủ các bước kiểm), plain (về nét nền). Nhân vật được báo luật chọn bản cuối; vòng cuối chỉ
    trả lời "có phải mình không", không xin sửa (sửa ở vòng cuối không được vẽ; 2026-11-27). Cho nhân vật tự chọn giữa các bản
    đã thử offline và bỏ: 26b chọn theo vị trí hoặc chấm dồn về 7 (xem choose_test.py, choose_rate.py, BACKLOG).
  6 dừng khi nhân vật nói "yes" (và ảnh qua cổng); hoặc nhân vật không sửa gì; hoặc hết lượt.
LOOK cuối do nhân vật chọn: vòng cuối cùng nhân vật nói "yes" và qua cổng; không có thì vòng "yes" cuối cùng; không có "yes"
thì "almost" trước "no", rồi qua cổng, rồi điểm cao nhất (bằng nhau thì vòng sau). LOOK.kb.json + sổ nét story được ghi lại từ bản đó, kèm "render".
Ghi: experiments/look_loop/<id>/<ts>/ (ảnh, LOOK từng vòng), experiments/logs/look_loop.jsonl (một dòng mỗi vòng).
Máy dùng chung: wee tuần tự, không gửi num_ctx/keep_alive/options; senlab tuần tự, gặp lỗi CUDA thì dừng ngay.
"""
import base64
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARS = ROOT / "characters"
sys.path.insert(0, str(CHARS / "kb"))
import kbq  # noqa: E402

HARNESS = Path(r"C:\Users\khoa\xyz\hoa_si\qwen\research_v2\harness")     # render_t2i.py: flattens the Qwen workflow
WORKFLOW = HARNESS.parents[1] / "image_qwen_image_2_1_t2i.json"
sys.path.insert(0, str(HARNESS))
import render_t2i as R  # noqa: E402


def opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


ROUNDS = int(opt("--rounds", "5"))
STORY = opt("--story", None)
SERVER = opt("--server", "http://senlab:8188").rstrip("/")
API_BASE = opt("--api", "http://wee:11435")
API = API_BASE + "/api/chat"
MODEL = "gemma4:26b"
if any(a.startswith("-") for a in sys.argv[1:]):
    sys.exit("usage: look_loop.py [char_id] [--rounds N] [--story S] [--server URL] [--api URL]")
CID = sys.argv[1] if len(sys.argv) > 1 else "lao_bay"

SEEDS = [1101, 2202]
W, H, STEPS = 896, 1152, 30
UNET, CLIP = "qwen_image_2.1_int8_convrot.safetensors", "qwen3vl_8b_int8_convrot.safetensors"
AGE_TOL, MAX_CHANGES = 10, 3
MAX_EMPH = 3          # emphasized slots per round: more dilutes them
# a front head-to-knees frame cannot show these; the eye is not asked about them
HIDDEN = {"height", "legs", "feet", "gait", "back"}
HIDDEN_LOCS = re.compile(r"shin|calf|foot|feet|ankle|back|buttock", re.I)
SEEN = ["yes", "partly", "no", "not visible"]
SECTIONS = {"overall": "A", "face": "B", "hair": "C", "body": "DEFG", "marks": "H"}     # as in luan_hoi.py

# what the describer is asked to look at, per slot (it never sees the intended LOOK)
PART = {"frame": "overall body build and frame (width, stockiness, bone)", "fat": "body fat (how much)",
        "muscle": "muscles (how much, how defined)", "fat_where": "where fat sits on the body", "head": "head size and shape",
        "face_shape": "face shape", "forehead": "forehead", "brows": "eyebrows", "eyes": "eyes", "under_eye": "under the eyes",
        "nose": "nose", "cheeks": "cheeks and cheekbones", "mouth": "lips and mouth", "teeth": "teeth", "jaw_chin": "jaw and chin",
        "ears": "ears (size relative to head)", "neck": "neck", "skin_tone": "skin colour", "skin_texture": "face skin texture",
        "wrinkles": "wrinkles and creases", "facial_hair": "beard, moustache, stubble", "asymmetry": "face asymmetry",
        "resting_face": "resting facial expression", "hair_color": "head hair colour", "hair_texture": "head hair texture",
        "hair_density": "head hair amount", "hairline": "hairline and baldness", "shoulders": "shoulders", "chest": "chest",
        "waist_belly": "waist and belly", "hips": "hips", "body_skin": "skin on arms and neck", "arms": "forearms and arms",
        "hands": "hands and fingers", "nails": "fingernails", "posture": "posture",
        "marks": "scars, moles, tattoos, birthmarks (where)"}

SYS_DESC = """You look at one photograph of a person. You know nothing else about this person.
Give apparent sex and age (judge from face and body). "too_polished": "yes" if the photo looks retouched or idealised (waxy smooth
skin, perfect white even teeth, model-like features, gym muscles) for a real person of this kind; else "no".
For each body part listed, describe in plain words what the photo shows (size, shape, condition), as a careful, unflattering
observer. Compare with an average person of the same apparent age and sex ("thinner than average", "unusually large"...).
If the part is visible but absent (no beard, no visible veins), say so plainly ("none: clean-shaven"). Say "not visible" ONLY
when it is cropped, covered or too small to judge. Answer JSON only."""

SYS_CMP = """You compare an observer's description of a photo with what a character's appearance should be. For each slot, does the
description show the intended feature? "yes", "partly", "no", or "not visible" (the observer could not see it).
- "yes": the description matches, in other words is fine ("yellowed stained teeth" for "tobacco-stained teeth").
- "partly": same direction but weaker or only some aspects mentioned, and nothing contradicts ("thin bony forearms" for "wiry
  veiny forearms"; "slightly yellow" for "brown stained").
- "no": the description contradicts the intended feature: a thin, slight body is "no" for "stocky" or "muscular"; a full beard
  is "no" for "hairless face".
- An intended ABSENCE ("hairless face", "no scars") matches a description saying none / not present / clean.
Answer JSON only."""

SYS_ME = """You play the character below. You asked a painter for a picture of yourself, from the appearance you chose. Now you
see the pictures, and a neutral observer's notes on what each slot of your appearance looks like in them.
Judge as yourself, by your IDENTITY, SOUL and LIFE: would people who know you say "that is him/her"? Not by beauty. Be honest.
You may change at most {maxc} slots this round:
- "emphasize": the value is right, but the pictures did not show it clearly (the painter will be told to show it);
- "repick": you want a different value for this slot; say what you want ("want"). It is picked again from the catalog with the
  same checks as before (a rare or notable value needs a reason in your files);
- "plain": the slot should be ordinary for your sex and age.
Do not change what already looks like you. Clothes, background, light and pose are fixed by the painter; ignore them.
"is_me": "yes" means this picture becomes your appearance for the whole story and you stop here (changes are then ignored);
say "yes" only if you would accept it. "almost" or "no" means you want another round.
{rounds}
Answer JSON: {{"is_me": "yes|almost|no", "feel": "<one sentence, as yourself>", "changes": [{{"slot": "<slot>",
 "action": "emphasize|repick|plain", "want": "<few words>"}}]}}"""


def read(name):
    p = CHARS / CID / f"{name}.en.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def call(system, user, schema, images=()):
    """Gemma on wee, sequential; no options (shared server: options or num_ctx could make it reload)."""
    msg = {"role": "user", "content": user}
    if images:
        msg["images"] = [base64.b64encode(Path(i).read_bytes()).decode() for i in images]
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
            print("   (malformed JSON from model, retrying)", flush=True)
    return {}, {"secs": round(time.time() - t, 1), "failed": True}


class Painter:
    def __init__(self):
        wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        info = json.loads(R.http(SERVER, "/object_info"))
        self.base = R.build_graph(wf, info)
        self.client = str(uuid.uuid4())

    def render(self, prompt, seed, out_png, prefix):
        g = json.loads(json.dumps(self.base))
        R.find(g, "UNETLoader")["inputs"]["unet_name"] = UNET
        R.find(g, "CLIPLoader")["inputs"]["clip_name"] = CLIP
        R.find(g, "TextEncodeQwenImage21")["inputs"]["prompt"] = prompt
        ge, gk = R.find(g, "EmptyLatentImage")["inputs"], R.find(g, "KSampler")["inputs"]
        ge["width"], ge["height"] = W, H
        gk["steps"], gk["seed"] = STEPS, seed
        g["save"]["inputs"]["filename_prefix"] = f"nhan_vat/{prefix}"
        pid, t0 = str(uuid.uuid4()), time.time()
        R.http(SERVER, "/prompt", json.dumps({"prompt": g, "client_id": self.client, "prompt_id": pid}).encode(),
               {"Content-Type": "application/json"})
        while time.time() - t0 < 1800:
            time.sleep(2)
            h = json.loads(R.http(SERVER, f"/history/{pid}") or b"{}").get(pid)
            if not h:
                continue
            st = h.get("status", {})
            if st.get("status_str") == "error":
                err = json.dumps([m for m in st.get("messages", []) if m[0] == "execution_error"])[:1500]
                if re.search(r"cuda|xid|device-side", err, re.I):
                    sys.exit(f"CUDA error on senlab, stopping now (tell senlab_admin): {err}")
                raise RuntimeError(err)
            if st.get("completed"):
                for node in h.get("outputs", {}).values():
                    for im in node.get("images", []):
                        q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"], "type": im["type"]})
                        out_png.write_bytes(R.http(SERVER, f"/view?{q}"))
                        return round(time.time() - t0, 1)
                raise RuntimeError("no image in outputs")
        raise RuntimeError("render timeout")


def main():
    kb = kbq.load()
    ident, soul, life, style = read("IDENTITY"), read("SOUL"), read("LIFE"), read("STYLE")
    facts = kb.facts(ident, life, style)
    ctx = facts.ctx
    look_path = CHARS / CID / "LOOK.kb.json"
    story = STORY or json.loads(look_path.read_text(encoding="utf-8")).get("story", "demo")
    age = int(re.search(r"Age:\s*(\d+)", ident).group(1))
    sex = "man" if re.search(r"Sex:\s*male", ident, re.I) else "woman"
    nat = "Vietnamese" if re.search(r"Vietnam", ident) else ""
    profile = "\n\n".join(x for x in (ident, soul, life) if x)
    run = ROOT / "experiments" / "look_loop" / CID / time.strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    painter = Painter()
    emph, rounds, best = [], [], None
    print(CID, age, sex, "story", story, "->", run, flush=True)

    for k in range(1, ROUNDS + 1):
        last = k == ROUNDS
        look = json.loads(look_path.read_text(encoding="utf-8"))
        shutil.copy(look_path, run / f"r{k}_LOOK.kb.json")
        full = look["picks"]
        planned = {s: r for s, r in look.get("planned", {}).items() if s in full}
        req = {s for s, m in kb.vocab["slots"].items() if m.get("required_in_prompt")}
        # checklist = every slot that reaches the prompt and a waist-up frame can show
        check = {}
        for s, p in kb.items(full):
            if (s in planned or s in req) and s not in HIDDEN and not (kbq.split_pick(p)[1] and HIDDEN_LOCS.search(kbq.split_pick(p)[1])):
                check.setdefault(s, []).append(kb.phrase(p))
        emph = [s for s in emph if s in full][-MAX_EMPH:]
        # rebuilt from the picks with the current KB (same sections as luan_hoi), so "paint" wording reaches older LOOKs too
        look_prompt = " | ".join(f"{k}: {t}" for k, g in SECTIONS.items() if (t := kb.prompt(full, ctx, groups=g)))
        lead = ", ".join(kb.paint(p) for s in emph for p in (full[s] if isinstance(full[s], list) else [full[s]]))
        pron = "His" if sex == "man" else "Her"
        prompt = (f"The image is a vertical documentary photograph of one {age}-year-old {nat} {sex}, standing, front view, framed "
                  f"from the top of the head to the knees, arms relaxed at the sides, both hands fully in frame, plain grey "
                  f"short-sleeved t-shirt and plain dark trousers, plain light background, soft daylight, realistic unretouched skin. "
                  + (f"{pron} most striking features, strongly visible: {lead}. " if lead else "") + look_prompt)
        (run / f"r{k}_prompt.txt").write_text(prompt, encoding="utf-8")
        print(f"\n== round {k}/{ROUNDS}  emphasize={emph}\n{prompt}", flush=True)

        imgs, eyes, rec = [], [], {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "char": CID, "story": story, "round": k,
                                    "run": str(run.relative_to(ROOT)), "prompt": prompt, "emphasize": list(emph),
                                    "picks": full, "planned": planned, "renders": [], "eyes": []}
        for i, seed in enumerate(SEEDS, 1):
            png = run / f"r{k}_s{i}.png"
            secs = painter.render(prompt, seed, png, f"{CID}_{run.name}_r{k}_s{i}")
            imgs.append(png)
            rec["renders"].append({"seed": seed, "png": str(png.relative_to(ROOT)), "secs": secs})
            print("render", png.name, secs, "s", flush=True)

        # ---- MẮT: describe blind (vision, no LOOK), then compare (text, no image); one image at a time
        desc_schema = {"type": "object", "properties": {
            "sex": {"type": "string", "enum": ["male", "female", "unclear"]},
            "age": {"type": "integer"},
            "too_polished": {"type": "string", "enum": ["yes", "no"]},
            "parts": {"type": "object", "properties": {s: {"type": "string", "maxLength": 160} for s in check},
                      "required": list(check)}},
            "required": ["sex", "age", "too_polished", "parts"]}
        cmp_schema = {"type": "object", "properties": {s: {"type": "string", "enum": SEEN} for s in check}, "required": list(check)}
        parts = "BODY PARTS\n" + "\n".join(f"{s}: {PART.get(s, s.replace('_', ' '))}" for s in check)
        for png in imgs:
            d, sd = call(SYS_DESC, parts, desc_schema, [png])
            got = d.get("parts", {})
            c, sc = call(SYS_CMP, "\n".join(f"{s}: intended \"{'; '.join(check[s])}\" | observer: \"{got.get(s, '')}\""
                                            for s in check), cmp_schema)
            e = {x: d.get(x) for x in ("sex", "age", "too_polished")}
            e["items"] = {s: {"seen": c.get(s), "what": got.get(s, "")} for s in check}
            st = {"secs": round(sd["secs"] + sc["secs"], 1), "describe": sd, "compare": sc}
            eyes.append(e)
            rec["eyes"].append({**e, **st})
            print("eye", png.name, st, {x: e.get(x) for x in ("sex", "age", "too_polished")}, flush=True)

        # ---- code: gates + score (average over seeds)
        val = {"yes": 1, "partly": 0.5, "no": 0}
        scores, gates = [], []
        for e in eyes:
            g = {"sex": e.get("sex") == ("male" if sex == "man" else "female"),
                 "age": isinstance(e.get("age"), int) and abs(e["age"] - age) <= AGE_TOL,
                 "not_polished": e.get("too_polished") == "no"}
            gates.append(g)
            num = den = 0
            for s in check:
                seen = (e.get("items", {}).get(s) or {}).get("seen")
                if seen in val:
                    w = 2 if planned.get(s) == "signature" else 1
                    num, den = num + w * val[seen], den + w
            scores.append(num / den if den else 0)
        score = round(sum(scores) / len(scores), 3)
        gate_ok = all(all(g.values()) for g in gates)
        rec.update({"score": score, "scores": scores, "gates": gates, "gate_ok": gate_ok})
        print("score", score, "gates", gates, flush=True)

        # ---- NHÂN VẬT: sees itself and decides
        table = []
        for s in check:
            seen = " / ".join(f'{(e.get("items", {}).get(s) or {}).get("seen", "?")}: {(e.get("items", {}).get(s) or {}).get("what", "")}'
                              for e in eyes)
            table.append(f"- {s} ({planned.get(s, 'ordinary')}): you chose \"{'; '.join(check[s])}\" | observer: {seen}")
        obs = "; ".join(f"picture {i}: {e.get('sex')}, about {e.get('age')}, retouched {e.get('too_polished')}"
                        for i, e in enumerate(eyes, 1))
        others = ", ".join(s for s in kb.slots if s not in check and s not in HIDDEN)
        user = (f"YOU\n{profile}\n\nPICTURES: {len(imgs)} (same description, different painter seeds)\nOBSERVER: {obs}\n\n"
                f"YOUR APPEARANCE, SLOT BY SLOT\n" + "\n".join(table)
                + f"\n\nOther slots (now ordinary for your sex and age; you may repick one): {others}"
                + (f"\n\nALREADY EMPHASIZED in these pictures (the painter was told to show them strongly): {', '.join(emph)}. "
                   "Emphasizing them again changes nothing; if one still looks wrong, repick it, make it plain, or accept it."
                   if emph and not last else ""))
        me_schema = {"type": "object", "properties": {
            "is_me": {"type": "string", "enum": ["yes", "almost", "no"]}, "feel": {"type": "string", "maxLength": 300},
            "changes": {"type": "array", "maxItems": 0 if last else MAX_CHANGES, "items": {"type": "object", "properties": {
                "slot": {"type": "string", "enum": [s for s in kb.slots if s not in HIDDEN]},
                "action": {"type": "string", "enum": ["emphasize", "repick", "plain"]},
                "want": {"type": "string", "maxLength": 160}}, "required": ["slot", "action", "want"]}}},
            "required": ["is_me", "feel", "changes"]}
        # the end rule is told up front; the last round only judges (a change asked there would never be painted;
        # 2026-11-26 every run asked for changes in round 5)
        sysme = SYS_ME.format(maxc=0 if last else MAX_CHANGES, rounds=(
            f"This is round {k} of {ROUNDS}, the LAST round: nothing more will be painted. Only say whether this is you "
            "(\"changes\" must be empty). If no round got your \"yes\", the round you judged closest becomes your appearance."
            if last else
            f"This is round {k} of {ROUNDS}; {ROUNDS - k} left after this one. If you never say \"yes\", the round you judged "
            "closest (\"almost\" before \"no\") becomes your appearance; changes asked in the last round are not painted."))
        me, st = call(sysme, user, me_schema, imgs)

        def effective(m):          # emphasizing a slot that is already emphasized would render the same picture again
            return [c for c in m.get("changes", []) if not (c["action"] == "emphasize" and c["slot"] in emph)]
        if last and me.get("changes"):          # in case the server ignores maxItems 0: logged, never applied
            me["changes_ignored"], me["changes"] = me["changes"], []
        if me.get("is_me") != "yes" and me.get("changes") and not effective(me):
            rec["me_first"] = {**me, **st}
            print("   only repeats emphasis; asking again", flush=True)
            me, st = call(sysme, user + "\n\nYOUR LAST ANSWER ONLY EMPHASIZED AGAIN WHAT IS ALREADY EMPHASIZED: the picture would be "
                          "the same. Repick or make plain a slot, or accept (\"yes\", or no changes).", me_schema, imgs)
        me["changes"] = effective(me)
        rec["me"] = {**me, **st}
        print("character:", me.get("is_me"), "|", me.get("feel"), flush=True)
        for c in me.get("changes", []):
            print("   change:", c, flush=True)

        # the character decides: its latest "yes" wins (one that also passes the gates first); score only breaks the rest
        yes = me.get("is_me") == "yes"
        # without a "yes", an "almost" beats a "no" (a 0.76 "no" once won over 0.72 "almost" rounds, 2026-11-26)
        near = {"yes": 2, "almost": 1}.get(me.get("is_me"), 0)
        key = (yes and gate_ok, near, gate_ok, k if yes else score)
        if best is None or key >= best["key"]:
            best = {"key": key, "round": k, "look": json.loads(look_path.read_text(encoding="utf-8")), "emph": list(emph),
                    "prompt": prompt, "imgs": [str(p.relative_to(ROOT)) for p in imgs], "score": score, "gate_ok": gate_ok,
                    "is_me": me.get("is_me")}
        done = (yes and gate_ok) or not me.get("changes")
        rec["stop"] = ("accepted" if yes and gate_ok else "last round" if last
                       else "nothing new to change" if done else "")
        with (ROOT / "experiments" / "logs" / "look_loop.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        rounds.append(rec)
        if done or k == ROUNDS:
            break

        # ---- apply changes
        repick = {c["slot"]: c["want"] for c in me["changes"] if c["action"] == "repick"}
        plain = [c["slot"] for c in me["changes"] if c["action"] == "plain" and c["slot"] in planned]
        for c in me["changes"]:
            if c["action"] == "emphasize" and c["slot"] in full:      # newest last: the oldest falls off past MAX_EMPH
                emph = [s for s in emph if s != c["slot"]] + [c["slot"]]
        emph = [s for s in emph if s not in repick and s not in plain]
        if repick or plain:
            rf = run / f"r{k}_redo.json"
            rf.write_text(json.dumps({"repick": repick, "plain": plain, "note": me.get("feel", "")}, ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable, "-I", str(ROOT / "experiments" / "luan_hoi.py"), CID, "--story", story,
                                "--api", API_BASE, "--redo", str(rf)], capture_output=True, text=True, encoding="utf-8")
            (run / f"r{k}_redo.log").write_text(r.stdout + r.stderr, encoding="utf-8")
            print("   redo exit", r.returncode, "|", (r.stdout.strip().splitlines() or [""])[-1][:300], flush=True)
            if r.returncode:
                sys.exit(f"luan_hoi --redo failed, see {run / f'r{k}_redo.log'}")
            # re-picked the value it already had: the value is right, the picture did not show it -> emphasize
            new = json.loads(look_path.read_text(encoding="utf-8"))["picks"]
            same = [s for s in repick if s in new and new[s] == full.get(s)]
            emph = [s for s in emph if s not in same] + same
            if same:
                print("   same value re-picked -> emphasize", same, flush=True)

    # ---- keep the best round as the LOOK of record
    look = best["look"]
    look["render"] = {"round": best["round"], "of": len(rounds), "is_me": best["is_me"], "score": best["score"],
                      "gate_ok": best["gate_ok"],
                      "emphasize": best["emph"], "prompt": best["prompt"], "images": best["imgs"], "seeds": SEEDS,
                      "model": UNET, "w": W, "h": H, "steps": STEPS}
    look_path.write_text(json.dumps(look, ensure_ascii=False, indent=1), encoding="utf-8")
    reg_path = CHARS / "stories" / story / "registry.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["chars"][CID] = {"id": CID, "group": look["group"], "kb_version": look["kb_version"], "picks": look["picks"],
                             "signature": look["signature"]}
        reg["counts"] = {g: kb.counts(reg, g) for g in sorted({c["group"] for c in reg["chars"].values()})}
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nCHOSEN round {best['round']} is_me {best['is_me']} score {best['score']} gate_ok {best['gate_ok']}; "
          f"renders: {len(rounds) * len(SEEDS)}")


if __name__ == "__main__":
    main()
