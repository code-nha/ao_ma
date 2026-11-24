"""Luân hồi v3 (toàn bộ LOOK: thân + mặt + tóc + dấu vết), dùng kho nét v3 (characters/kb, module kbq):
code đọc FACTS từ IDENTITY/STYLE (mức sống, nghề, ăn uống, rượu, thuốc, dân tộc...) -> code lọc cứng (giới, tuổi, needs theo
FACTS, trần dùng lại) -> Luân hồi gạch giá trị không thể có -> nhân vật chọn 2 bước (1: ô nào là nét nhận diện / nét phụ,
trên tất cả các ô; 2: giá trị cho các ô đó, menu đã lọc theo lựa chọn trước) -> code kiểm mâu thuẫn + kiểm LÝ DO (giá trị hiếm
hoặc nổi bật phải dẫn một mục LIFE hoặc một trường IDENTITY có nguyên nhân khớp) -> Luân hồi kiểm mâu thuẫn làm lưới cuối
-> ô không chọn nhận giá trị nền theo giới x tuổi (x dân tộc) -> sổ nét của story.

    python -I luan_hoi.py lao_bay [--story demo] [--api http://wee:11435] [--model gemma4:26b] [--dry]

Nét nhận diện: 2-5 trên toàn bộ các ô, tối đa 3 trong một nhóm (A thân tổng thể, B mặt, C tóc, D-G thân, H dấu vết).
Nét phụ: tối đa 6. Mỗi lời gọi model <= ~3.5k token đầu vào (kbq.plan_calls). Ghi:
  characters/<id>/LOOK.kb.json               lựa chọn từng ô + cụm tiếng Anh + prompt (tổng thể -> mặt -> tóc -> thân -> dấu vết)
  characters/stories/<story>/registry.json   sổ nét của story (kb_version; counts tính lại từ chars)
  experiments/logs/luan_hoi.jsonl            toàn bộ lời gọi (prompt_tokens từng lời gọi)
  experiments/logs/rule_candidates.jsonl     mâu thuẫn LLM bắt được (code_found=false: code bỏ sót -> thêm dims/luật)
Máy wee dùng chung: tuần tự, không gửi num_ctx / keep_alive.
"""
import json
import re
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


API = opt("--api", "http://wee:11435") + "/api/chat"
MODEL = opt("--model", "gemma4:26b")
STORY = opt("--story", "demo")
DRY = "--dry" in sys.argv
if DRY:
    sys.argv.remove("--dry")
if any(a.startswith("-") for a in sys.argv[1:]):
    sys.exit("usage: luan_hoi.py [char_id] [--story S] [--api URL] [--model M] [--dry]")
CID =sys.argv[1] if len(sys.argv) > 1 else "lao_bay"

CAP_SHARE, CAP_MIN = 0.2, 2
MIN_SIG, MAX_SIG, MAX_SIG_GROUP, MAX_EXTRA = 2, 5, 3, 6
MAX_SHARED_SIG = 1      # signatures shared with any one other character of the same story
FIX_ROUNDS = 2          # số lần hỏi lại một lời gọi bước 2 khi code thấy lỗi
LLM_CHECKS = 2          # số lần Luân hồi kiểm mâu thuẫn (lần 2 sau khi sửa)
STYLE_KEYS = r"grooming|eating|drinking|gestures|posture|walk|body"

SYS_LUAN_HOI = """You are LUAN HOI, the keeper of appearances for one story. You do not play the character. For each slot you
receive a numbered menu of values. Using the character's IDENTITY, LIFE and the FACTS code read from them, list ONLY the numbers
of values that are truly IMPOSSIBLE or absurd for this person (wrong age, wrong sex, wrong means or work, contradicts LIFE).
Everything else stays, including unusual and unflattering values: the wider the choice, the more diverse the cast. When unsure,
do not remove. Value 1 of each slot is what is ordinary for this person; never remove it.
Answer JSON: {"remove": {"<slot>": ["<number>", ...]}} with every slot present (empty list if nothing is impossible)."""

SYS_STEP1 = f"""You play the character below and decide your own visible LOOK (face, hair, body, marks) at the age in your IDENTITY.
Every slot is already set to what is ordinary for your sex and age. You only say where you are NOT ordinary:
- "signature": the slots people remember when they meet you (they will get notable values). In total over all parts
  {MIN_SIG}-{MAX_SIG}, at most {MAX_SIG_GROUP} from one group.
- "extras": other slots that differ a little from ordinary (near-plain values); at most {MAX_EXTRA} in total.
For each slot give an "idea": a few words of what you picture there. The examples only show what kind of values exist.
Head, face shape, eyes, nose, ears, height and frame come from birth and family, not personality. resting_face, posture and
gait may follow your SOUL. Fat, muscle, skin, teeth, hands, wrinkles and marks show how you live (work, food, habits, LIFE events,
age). A rare or notable feature will need a reason: a LIFE item number or an IDENTITY field. Be honest, not flattering: look
like yourself, not good.
Answer JSON: {{"signature": [{{"slot": "<slot>", "idea": "<few words>"}}], "extras": [{{"slot": "<slot>", "idea": "<few words>"}}]}}"""

SYS_STEP2 = f"""You play the character below and pick the exact value for each listed slot of your LOOK, following your plan.
Pick by number from each slot's list. "notable" values are what people remember; "near-plain" values are small differences.
At most {MAX_SIG} notable values in total. All values together describe ONE person: they must not contradict each other or your
other picks, and the same feature must not be described in two slots. At most one rare value, unless a LIFE item explains it.
"cite": for every value marked rare or notable, the reason in your files: "LIFE <number>", "IDENTITY <field>", or "FACTS" for habits
code read (drinking, smoking, diet, work); resting_face, posture and gait may cite "SOUL"); the cited item must really show that cause. Otherwise "-".
For "marks" give 1-3 items, each with a "loc" from the listed places. Be honest, not flattering.
Answer JSON: {{"<slot>": {{"pick": "<number>", "cite": "<reason or ->", "why": "<few words>"}}, ...,
 "marks": {{"items": [{{"pick": "<number>", "loc": "<place>", "cite": "<reason or ->"}}], "why": "<few words>"}}}}"""

SYS_CHECK = """You are LUAN HOI checking one character's appearance, slot by slot. Find slots whose values CONTRADICT each other so that
no single real person could have them all (e.g. "stocky square frame" with "thin flat chest, ribs showing"; "hollow sunken cheeks"
with "soft double chin"; "completely bald" with "very thick hair"), or that describe the same feature twice in incompatible ways.
Ignore anything merely unusual.
Answer JSON: {"conflicts": [{"slots": ["<slot>", "<slot>"], "why": "<short>"}]} (empty list if none)."""


def read(name):
    p = CHARS / CID / f"{name}.en.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def call(system, user, schema):
    body = {"model": MODEL, "stream": False, "think": False, "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.8, "num_predict": 3000}}
    t = time.time()
    bad = []
    for attempt in range(3):            # Gemma sometimes stops inside a JSON string or loops on one phrase: ask again (sequential)
        req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            out = json.loads(r.read())
        try:
            res = json.loads(out["message"]["content"])
            break
        except json.JSONDecodeError:
            bad.append(out["message"]["content"][-200:])
            print("   (malformed JSON from model, retrying)", flush=True)
    else:
        # give up on this call, not on the run: callers treat {} as "no answer" (menu kept whole, slots stay ordinary)
        print(f"   (malformed JSON {len(bad)} times; call skipped)", flush=True)
        res = {}
    return res, {"secs": round(time.time() - t, 1), "prompt_tokens": out.get("prompt_eval_count"),
                 "eval_tokens": out.get("eval_count"), "est_tokens": kbq.est_tokens(system + user),
                 **({"malformed_retries": len(bad)} if bad else {})}


def as_list(p):
    return p if isinstance(p, list) else [p]


def main():
    kb = kbq.load()
    budget = kb.vocab["budget"]["call_tokens"]
    ident, soul, life, style = read("IDENTITY"), read("SOUL"), read("LIFE"), read("STYLE")
    facts = kb.facts(ident, life, style)
    ctx = facts.ctx
    gkey = ctx.group
    seed = f"{STORY}/{CID}"
    grp = {s: kb.vocab["slots"][s]["group"] for s in kb.slots}
    max_marks = kb.marks.get("max", 3)

    reg_path = CHARS / "stories" / STORY / "registry.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {"chars": {}}
    counts = kb.counts(reg, gkey, exclude=CID)        # tính lại từ chars, bỏ chính nhân vật này
    n_group = sum(1 for k, c in reg["chars"].items() if c["group"] == gkey and k != CID)
    cap = max(CAP_MIN, round(CAP_SHARE * (n_group + 1)))
    # signatures of the other characters in this story (any group): this one may share at most MAX_SHARED_SIG with each
    other_sig = {k: {kbq.split_pick(p)[0] for p in c.get("signature", [])} for k, c in reg["chars"].items() if k != CID}

    menus = {s: kb.menu(s, ctx, counts=counts, cap=cap, seed=seed, facts=facts) for s in kb.slots}
    print(gkey, "kb", kb.version, "cap", cap, "facts:", facts.line(), flush=True)

    facts_txt = f"FACTS (read by code from IDENTITY/STYLE): {facts.line()}"
    style_look = "\n".join(l for l in style.splitlines() if re.search(rf"^\s*-\s*({STYLE_KEYS})", l, re.I))
    profile = "\n\n".join(x for x in (ident, soul, life, style_look, facts_txt) if x)
    log = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "char": CID, "story": STORY, "model": MODEL, "group": gkey,
           "kb_version": kb.version, "facts": sorted(facts.tags), "calls": []}

    # ---------------------------------------------------------------- Luân hồi: gạch giá trị không thể có
    lh_profile = "\n\n".join(x for x in (ident, life, facts_txt) if x)
    rendered = {s: kb.render(s, menus[s], ctx, "luan_hoi", counts) for s in kb.slots}
    fixed = kbq.est_tokens(SYS_LUAN_HOI + f"CHARACTER\n{lh_profile}\n\nMENUS\n") + 60
    plan = kb.plan_calls(kb.slots, {s: kbq.est_tokens(rendered[s][0]) for s in kb.slots}, budget, fixed)
    short = {}
    for slots in plan:
        user = f"CHARACTER\n{lh_profile}\n\nMENUS\n" + "\n".join(rendered[s][0] for s in slots)
        if DRY:
            print("luan_hoi", len(slots), "slots ~", kbq.est_tokens(SYS_LUAN_HOI + user), "tokens")
            for s in slots:
                short[s] = [v["id"] for v in menus[s]]
            continue
        schema = {"type": "object", "properties": {"remove": {"type": "object", "properties": {
            s: {"type": "array", "items": {"type": "string", "enum": list(rendered[s][1])[1:] or ["1"]}} for s in slots},
            "required": slots}}, "required": ["remove"]}
        res, stat = call(SYS_LUAN_HOI, user, schema)
        for s in slots:
            keys = rendered[s][1]
            rm = {keys[k] for k in res.get("remove", {}).get(s, []) if k in keys and k != "1"}
            keep = [v["id"] for v in menus[s] if v["id"] not in rm]
            short[s] = keep if len(keep) >= 5 or len(menus[s]) < 5 else [v["id"] for v in menus[s]]
        log["calls"].append({"role": "luan_hoi", "slots": slots, "out": res, **stat})
        print("luan_hoi", len(slots), "slots", stat, flush=True)

    # ---------------------------------------------------------------- nhân vật bước 1: chọn ô (một hoặc vài phần)
    vals = {s: [kb.get(i) for i in short[s]] for s in kb.slots}
    notable = {s: sorted([v for v in vals[s] if kb.notable(v, ctx)], key=lambda v: -kb.fit_score(v, ctx)) for s in kb.slots}
    nearpl = {s: sorted([v for v in vals[s] if kb.near_plain(v, ctx)], key=lambda v: -kb.fit_score(v, ctx)) for s in kb.slots}

    def ex(v):
        return v["phrase"].replace("{loc}", "[place]")

    def ov_line(s, n_not, n_near):
        out = [f"## {s} ({grp[s]}): ordinary = {ex(kb.baseline(s, ctx))}"]
        if notable[s][:n_not]:
            out.append("  notable e.g.: " + "; ".join(ex(v) for v in notable[s][:n_not]))
        if nearpl[s][:n_near]:
            out.append("  near-plain e.g.: " + "; ".join(ex(v) for v in nearpl[s][:n_near]))
        return "\n".join(out)

    head1 = f"YOU\n{profile}\n\nGROUPS: A overall, B face, C hair, D torso, E arms/hands, F legs/feet, G posture/gait, H marks\n\n"
    for n_not, n_near in ((2, 1), (1, 1), (1, 0)):
        lines = {s: ov_line(s, n_not, n_near) for s in kb.slots}
        fixed1 = kbq.est_tokens(SYS_STEP1 + head1 + "ALREADY CHOSEN\n" + "x" * 300 + "\n\nSLOTS\n") + 40
        parts = kb.plan_calls(kb.slots, {s: kbq.est_tokens(lines[s]) for s in kb.slots}, budget, fixed1)
        if len(parts) <= 2:
            break
    role, idea = {}, {}

    def n_role(kind, g=None):
        return sum(1 for s, r in role.items() if r == kind and (g is None or grp[s] == g))

    for pi, part in enumerate(parts):
        last = pi == len(parts) - 1
        sig_ok = [s for s in part if notable[s] and n_role("signature", grp[s]) < MAX_SIG_GROUP]
        ext_ok = [s for s in part if nearpl[s] or notable[s]]
        lo, hi = (max(0, MIN_SIG - n_role("signature")) if last else 0), max(0, MAX_SIG - n_role("signature"))
        room_ext = max(0, MAX_EXTRA - n_role("extra"))
        chosen_txt = "\n".join(f"- {s} ({role[s]}): {idea[s]}" for s in role) or "- (nothing yet)"
        quota = (f"\n\nTHIS PART: choose {lo}-{hi} signature slots and at most {room_ext} extras among the slots above"
                 f"{' (this is the last part)' if last else f' (part {pi + 1} of {len(parts)})'}.")
        user1 = head1 + f"ALREADY CHOSEN\n{chosen_txt}\n\nSLOTS\n" + "\n".join(lines[s] for s in part) + quota
        if DRY:
            print("character step1 part", pi + 1, len(part), "slots ~", kbq.est_tokens(SYS_STEP1 + user1), "tokens", (n_not, n_near))
            res1 = {"signature": [{"slot": s, "idea": "x"} for s in sig_ok[:max(lo, min(hi, 2))]],
                    "extras": [{"slot": s, "idea": "x"} for s in ext_ok[-2:]]}
        else:
            def it(en):
                return {"type": "object", "properties": {"slot": {"type": "string", "enum": en or ["none"]},
                                                         "idea": {"type": "string", "maxLength": 160}}, "required": ["slot", "idea"]}
            schema1 = {"type": "object", "properties": {
                "signature": {"type": "array", "items": it(sig_ok), "minItems": min(lo, len(sig_ok)), "maxItems": min(hi, len(sig_ok))},
                "extras": {"type": "array", "items": it(ext_ok), "maxItems": room_ext}},
                "required": ["signature", "extras"]}
            res1, stat = call(SYS_STEP1, user1, schema1)
            log["calls"].append({"role": "character_step1", "part": pi + 1, "slots": part, "out": res1, **stat})
            print("character step1 part", pi + 1, stat, flush=True)
        for kind, items in (("signature", res1.get("signature", [])), ("extra", res1.get("extras", []))):
            for x in items:
                s = x.get("slot")
                if s not in part or s in role:
                    continue
                if kind == "signature" and (s not in sig_ok or n_role("signature") >= MAX_SIG
                                            or n_role("signature", grp[s]) >= MAX_SIG_GROUP):
                    continue
                if kind == "extra" and (s not in ext_ok or n_role("extra") >= MAX_EXTRA):
                    continue
                role[s], idea[s] = kind, x.get("idea", "")
    chosen = [s for s in kb.slots if s in role]
    print("plan:", {s: f"{role[s]}: {idea[s]}" for s in chosen}, flush=True)

    # ---------------------------------------------------------------- nhân vật bước 2: chọn giá trị (menu lọc theo lựa chọn trước)
    plan_txt = "\n".join(f"- {s} ({role[s]}): {idea[s]}" for s in chosen)
    head2 = f"YOU\n{profile}\n\nYOUR PLAN\n{plan_txt}\n\n"
    fixed2 = kbq.est_tokens(SYS_STEP2 + head2 + "ALREADY PICKED\n" + "x" * 600 + "\n\nSLOTS\n") + 80

    def role_menu(s, locked, exclude=()):
        # every non-baseline value of the shortlist; the planned kind first. Whether a pick counts as a signature is
        # decided by the value (notable), not by the plan.
        pool = notable[s] + nearpl[s] if role[s] == "signature" else nearpl[s] + notable[s]
        lv = [kb.get(p) for _, p in kb.items(locked)]
        return [v for v in pool if v["id"] not in exclude and not any(kb.pair_conflicts(v, p, ctx) for p in lv)]

    worst = {s: kbq.est_tokens(kb.render(s, role_menu(s, {}), ctx, "character", facts=facts)[0]) + 30 for s in chosen}
    plan2 = kb.plan_calls(chosen, worst, budget, fixed2)
    picks, why, cites, code_caught = {}, {}, {}, []
    rounds = [0]
    cur_why = {}    # slot -> step1 idea + step2 why: a reason may not claim a cause (injury, illness...) the files do not show

    def why_of(s):
        return f"{idea.get(s, '')}. {cur_why.get(s, '')}"

    def unexplained_rares(p):
        return [(s, x) for s, x in kb.items(p) if kb.cls(kb.get(x), ctx) == "rare"
                and not kb.life_explained(s, x, cites.get(x, ""), facts)]

    def shared_overflow(trial, new):
        """New picks that make this character share more than MAX_SHARED_SIG signatures with another character of the
        story: [(pick, other char id)]. Picks already locked count first, so the newest pick is the one to change."""
        sig_base = lambda p: kbq.split_pick(p)[0]
        notable_ids = [(s, x) for s, x in kb.items(trial) if kb.notable(kb.get(x), ctx, kbq.split_pick(x)[1])]
        newp = {x for _, x in kb.items(new)}
        out = []
        for o, osig in other_sig.items():
            shared = [x for _, x in notable_ids if sig_base(x) in osig]
            shared.sort(key=lambda x: x in newp)          # locked first
            out += [(x, o) for x in shared[MAX_SHARED_SIG:] if x in newp]
        return out

    def problems(trial, new):
        """Code checks on a trial pick set; returns messages for a FIX prompt."""
        newp = {x for _, x in kb.items(new)}
        errs_sh = [f'"{kb.phrase(x)}" is already a signature feature of another character in this story ({o}); you may share at '
                   f'most {MAX_SHARED_SIG} with them. Pick a different value so the two of you are told apart.'
                   for x, o in shared_overflow(trial, new)]
        errs = [c["msg"] for c in kb.check(trial, ctx) if set(c["ids"]) & newp]
        errs += [m for s, x in kb.items(new) for m in [kb.cite_problem(s, x, cites.get(x, ""), facts, ctx, why=why_of(s))] if m]
        rares = unexplained_rares(trial)
        if len(rares) > 1:
            errs.append(f"More than one rare value without a LIFE reason ({'; '.join(kb.phrase(x) for _, x in rares)}); keep at most one.")
        nn = [x for _, x in kb.items(trial) if kb.notable(kb.get(x), ctx, kbq.split_pick(x)[1])]
        if len(nn) > MAX_SIG:
            errs.append(f"{len(nn)} notable values; at most {MAX_SIG}. Use near-plain values for the others.")
        return errs + errs_sh

    def step2(slots, extra_msg="", exclude=()):
        locked = {s: picks[s] for s in picks if s not in slots}
        lists = {}
        for s in slots:
            m = role_menu(s, locked, exclude)
            if m:
                lists[s] = m
            else:
                print("   slot", s, "has no value left that fits earlier picks; stays ordinary", flush=True)
                picks.pop(s, None)
        if not lists:
            return
        texts = {s: kb.render(s, lists[s], ctx, "character", facts=facts) for s in lists}
        already = "\n".join(f"- {s}: {kb.phrase(p)}" for s, p in kb.items(locked)) or "- (nothing yet)"
        body = head2 + f"ALREADY PICKED\n{already}\n\nSLOTS\n" + "\n".join(
            f"{t[0].splitlines()[0]} ({role[s]})\n" + "\n".join(t[0].splitlines()[1:]) for s, t in texts.items())
        props = {}
        for s in texts:
            keys = list(texts[s][1])
            if kb.multi(s):
                locs = sorted({l for v in lists[s] for l in v.get("locs", [])})
                body += f"\n(marks places: {', '.join(locs)})"
                props[s] = {"type": "object", "properties": {
                    "items": {"type": "array", "minItems": 1, "maxItems": max_marks, "items": {"type": "object", "properties": {
                        "pick": {"type": "string", "enum": keys}, "loc": {"type": "string", "enum": locs}, "cite": {"type": "string", "maxLength": 40}},
                        "required": ["pick", "loc", "cite"]}}, "why": {"type": "string", "maxLength": 300}}, "required": ["items", "why"]}
            else:
                props[s] = {"type": "object", "properties": {"pick": {"type": "string", "enum": keys}, "cite": {"type": "string", "maxLength": 40},
                                                             "why": {"type": "string", "maxLength": 300}}, "required": ["pick", "cite", "why"]}
        schema = {"type": "object", "properties": props, "required": list(texts)}
        user, errs, new, res = body + extra_msg, [], {}, {}
        for rnd in range(FIX_ROUNDS + 1):
            rounds[0] += 1
            if DRY:
                print("character step2", list(texts), "~", kbq.est_tokens(SYS_STEP2 + user), "tokens")
                res = {s: ({"items": [{"pick": "1", "loc": lists[s][0]["locs"][0], "cite": "-"}], "why": "x"} if kb.multi(s)
                           else {"pick": "1", "cite": "-", "why": "x"}) for s in texts}
            else:
                res, stat = call(SYS_STEP2, user, schema)
            new, loc_errs = {}, []
            for s in texts:
                r = res.get(s) or {}
                if kb.multi(s):
                    items = []
                    for x in (r.get("items") or [])[:max_marks]:
                        vid = texts[s][1].get(x.get("pick"))
                        if not vid:
                            continue
                        if x.get("loc") not in kb.get(vid).get("locs", []):
                            loc_errs.append(f'"{kb.get(vid)["phrase"]}" cannot be on {x.get("loc")}; places: {kb.where(kb.get(vid))}.')
                            continue
                        p = f"{vid}@{x['loc']}"
                        if p not in items:
                            items.append(p)
                            cites[p] = x.get("cite", "")
                    if items:
                        new[s] = items
                elif r.get("pick") in texts[s][1]:
                    new[s] = texts[s][1][r["pick"]]
                    cites[new[s]] = r.get("cite", "")
            cur_why.update({s: (res.get(s) or {}).get("why", "") for s in texts})
            errs = loc_errs + problems({**locked, **new}, new)
            if not DRY:
                log["calls"].append({"role": "character_step2", "slots": list(texts), "round": rnd + 1, "out": res,
                                     "errors": errs, **stat})
                print("character step2", list(texts), stat, "errors", len(errs), flush=True)
            for e in errs:
                print("   -", e, flush=True)
            code_caught.extend(errs)
            if not errs or rnd == FIX_ROUNDS or DRY:
                break
            user = (body + extra_msg + "\n\nYOUR PREVIOUS ANSWER\n" + json.dumps(res, ensure_ascii=False)
                    + "\n\nFIX THESE PROBLEMS AND PICK AGAIN:\n- " + "\n- ".join(errs))
        if errs:            # vẫn còn lỗi sau các lần sửa: bỏ các lựa chọn gây lỗi, ô đó về giá trị nền
            bad = {i for c in kb.check({**locked, **new}, ctx) for i in c["ids"]}
            bad |= {x for s, x in kb.items(new) if kb.cite_problem(s, x, cites.get(x, ""), facts, ctx, why=why_of(s))}
            extra_rares = [x for s, x in unexplained_rares({**locked, **new}) if s in new]
            n_locked_rare = len(unexplained_rares(locked))
            bad |= set(extra_rares[max(0, 1 - n_locked_rare):])
            bad |= {x for x, _ in shared_overflow({**locked, **new}, new)}
            for s in list(new):
                keep = [x for x in as_list(new[s]) if x not in bad]
                if not keep:
                    del new[s]
                else:
                    new[s] = keep if kb.multi(s) else keep[0]
            print("   dropped after fixes:", sorted(set(lists) - set(new)), flush=True)
        picks.update(new)
        why.update({s: (res.get(s) or {}).get("why", "") for s in new})

    for slots in plan2:
        step2(slots)

    # ---------------------------------------------------------------- lưới cuối: Luân hồi kiểm mâu thuẫn
    chk_schema = {"type": "object", "properties": {"conflicts": {"type": "array", "items": {"type": "object", "properties": {
        "slots": {"type": "array", "items": {"type": "string", "enum": kb.slots}}, "why": {"type": "string"}},
        "required": ["slots", "why"]}}}, "required": ["conflicts"]}
    llm_caught, unresolved = [], []
    for n in range(LLM_CHECKS):
        full, covered = kb.fill(picks, ctx)
        desc = "\n".join(f"{s}: {kb.phrase(p)}" for s, p in kb.items(full)
                         if s in picks or kb.vocab["slots"][s].get("required_in_prompt"))
        if DRY:
            print("check ~", kbq.est_tokens(SYS_CHECK + desc), "tokens")
            break
        chk, cstat = call(SYS_CHECK, desc, chk_schema)
        log["calls"].append({"role": "check", "n": n + 1, "out": chk, **cstat})
        conf = [c for c in chk.get("conflicts", []) if any(s in picks for s in c.get("slots", []))
                and len(c.get("why", "")) <= 300]
        print("check", n + 1, cstat, "conflicts", len(chk.get("conflicts", [])), flush=True)
        if not chk.get("conflicts"):
            break
        with (ROOT / "experiments" / "logs" / "rule_candidates.jsonl").open("a", encoding="utf-8") as fh:
            for c in chk["conflicts"]:
                ids = {s: full.get(s) for s in c.get("slots", [])}
                rec = {"ts": log["ts"], "char": CID, "group": gkey, "kb_version": kb.version, "slots": c.get("slots"),
                       "ids": ids, "phrases": {s: [kb.phrase(p) for p in as_list(i)] for s, i in ids.items() if i},
                       "why": c.get("why"),
                       "code_found": bool(kb.check({s: i for s, i in ids.items() if i}, ctx)),
                       "acted": c in conf and n + 1 < LLM_CHECKS}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                llm_caught.append(rec)
                print("   - LLM:", c.get("slots"), c.get("why"), flush=True)
        if not conf:
            break
        if n + 1 == LLM_CHECKS:
            # no rounds left: a contradiction must not reach LOOK. Per conflict, the slot to let go back to ordinary:
            # an extra before a signature, then the slot picked last (the latest re-pick is the least settled).
            order = {s: i for i, s in enumerate(picks)}
            for c in conf:
                cand = [s for s in c["slots"] if s in picks]
                if not cand:
                    continue
                s = max(cand, key=lambda x: (role.get(x) != "signature", order.get(x, 0)))
                picks.pop(s, None)
                unresolved.append({"slots": c["slots"], "why": c.get("why"), "dropped": s})
                print("   unresolved after checks; slot back to ordinary:", s, flush=True)
            break
        redo = sorted({s for c in conf for s in c["slots"] if s in picks}, key=kb.slots.index)
        old_ids = {kbq.split_pick(p)[0] for s in redo for p in as_list(picks[s])}
        msg = "\n\nLUAN HOI FOUND THESE CONTRADICTIONS; PICK THESE SLOTS AGAIN:\n- " + "\n- ".join(
            f"{', '.join(c['slots'])}: {c['why']}" for c in conf)
        for s in redo:
            picks.pop(s, None)
        step2(redo, msg, exclude=old_ids)
    if DRY:
        return

    full, covered = kb.fill(picks, ctx)
    sections = {"overall": "A", "face": "B", "hair": "C", "body": "DEFG", "marks": "H"}
    prompt_parts = {k: kb.prompt(full, ctx, groups=g) for k, g in sections.items()}
    prompt = " | ".join(f"{k}: {t}" for k, t in prompt_parts.items() if t)
    sig = [p for s, p in kb.items(picks) if kb.notable(kb.get(p), ctx, kbq.split_pick(p)[1])]
    ext = [p for s, p in kb.items(picks) if p not in sig]
    look = {"char": CID, "story": STORY, "group": gkey, "kb_version": kb.version,
            "facts": {t: facts.src.get(t) for t in sorted(facts.tags)},
            "picks": full, "covered": covered, "signature": sig, "extras": ext, "planned": role, "ideas": idea, "why": why,
            "cites": {p: cites.get(p, "") for _, p in kb.items(picks)}, "rounds_step2": rounds[0],
            "remaining_errors": len(kb.check(picks, ctx)),
            "phrases": {s: ([kb.phrase(x) for x in p] if isinstance(p, list) else kb.phrase(p)) for s, p in full.items()},
            "vi": {s: ([kb.vi(x) for x in p] if isinstance(p, list) else kb.vi(p)) for s, p in full.items()},
            "prompt_sections": prompt_parts, "prompt": prompt,
            "shortlist_sizes": {s: f"{len(short[s])}/{len(menus[s])}" for s in short}}
    (CHARS / CID / "LOOK.kb.json").write_text(json.dumps(look, ensure_ascii=False, indent=1), encoding="utf-8")

    # sổ nét của story: counts luôn tính lại từ chars
    reg["chars"][CID] = {"id": CID, "group": gkey, "kb_version": kb.version, "picks": full, "signature": sig}
    reg["kb_version"] = kb.version
    reg["counts"] = {g: kb.counts(reg, g) for g in sorted({c["group"] for c in reg["chars"].values()})}
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")

    log.update({"code_caught": code_caught, "llm_caught": llm_caught, "unresolved": unresolved, "prompt": prompt, "prompt_sections": prompt_parts,
                "picks": picks, "cites": look["cites"], "covered": covered})
    (ROOT / "experiments" / "logs").mkdir(exist_ok=True)
    with (ROOT / "experiments" / "logs" / "luan_hoi.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log, ensure_ascii=False) + "\n")
    print("tokens per call:", [(c["role"], c.get("prompt_tokens")) for c in log["calls"]])
    print("PROMPT:", prompt)


if __name__ == "__main__":
    main()
