"""kb.py: check and build the LOOK knowledge base.

    python -I kb.py check            validate everything (exit 1 on error)
    python -I kb.py build            check, then write kb.json, ids.lock, report.md
    python -I kb.py find "<phrase>"  near-duplicate search before adding a value
    python -I kb.py menu male 70 [--tags poor,sea,plain-diet] [slot ...]   menus + token estimate for a sample person
    python -I kb.py facts <character dir>   what code reads from IDENTITY / LIFE / STYLE (tags, LIFE item causes)
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kbq  # noqa: E402

ID_RE = re.compile(r"^[a-z_]+\.[a-z0-9]+(?:-[a-z0-9]+)*$")
BEAUTY = re.compile(r"\b(beautiful|handsome|attractive|perfect|flawless|pretty|gorgeous|sexy|lovely|stunning)\b", re.I)
CAUSE_WORDS = re.compile(r"\b(after|due to|because|caused|used to|someone|years of|decades of|lifetime|with age|"
                         r"from (?!the (back|side|front)\b)\w+)\b", re.I)
CLOTHING = re.compile(r"\b(shirt|trousers|pants|dress|skirt|shoe|shoes|hat|jacket|coat|sandals|bra|ring(?! finger)|tattooed|"
                      r"hairstyle|ponytail|bun|makeup|lipstick|glasses|watch)\b", re.I)


def _S_facet(facets, tag):
    return next((f for f, ts in facets.items() if tag in ts), None)


def read_jsonl(p):
    out = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append((n, json.loads(line)))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{p.name}:{n}: bad JSON: {e}")
    return out


def load_sources():
    vocab = json.loads((HERE / "vocab.json").read_text(encoding="utf-8"))
    values, where = {}, {}
    errs = []
    for slot in vocab["slots"]:
        p = HERE / "catalog" / f"{slot}.jsonl"
        if not p.exists():
            errs.append(f"catalog/{slot}.jsonl missing")
            continue
        for n, v in read_jsonl(p):
            loc = f"catalog/{slot}.jsonl:{n}"
            if v.get("id") in values:
                errs.append(f"{loc}: duplicate id {v.get('id')} (also {where[v['id']]})")
            values[v.get("id")] = v
            where[v.get("id")] = loc
    extra = {p.stem for p in (HERE / "catalog").glob("*.jsonl")} - set(vocab["slots"])
    errs += [f"catalog/{s}.jsonl: slot not in vocab.json" for s in sorted(extra)]
    cards = {}
    for p in sorted((HERE / "evidence").glob("*.jsonl")):
        for n, c in read_jsonl(p):
            if c["id"] in cards:
                errs.append(f"evidence/{p.name}:{n}: duplicate card {c['id']}")
            cards[c["id"]] = c
            where[c["id"]] = f"evidence/{p.name}:{n}"
    sources = {s["id"]: s for _, s in read_jsonl(HERE / "sources.jsonl")}
    rules = [r for _, r in read_jsonl(HERE / "rules.jsonl")]
    vi = {r["id"]: r["vi"] for _, r in read_jsonl(HERE / "vi.jsonl")}
    golden = [g for _, g in read_jsonl(HERE / "tests" / "golden.jsonl")]
    return vocab, values, where, cards, sources, rules, vi, golden, errs


def resolve_map(values):
    out = {}
    for vid in values:
        seen, stack, res = set(), [vid], []
        while stack:
            x = stack.pop()
            if x in seen or x not in values:
                return None, f"tombstone chain from {vid} broken or cyclic at {x}"
            seen.add(x)
            v = values[x]
            if v["status"] == "active":
                res.append(x)
            elif v["status"] in ("merged", "split"):
                into = v.get("into") or []
                stack.extend(into if isinstance(into, list) else [into])
            # deprecated: resolves to nothing
        out[vid] = sorted(set(res))
    return out, None


def kb_version(vocab_txt, files):
    h = hashlib.sha256(vocab_txt.encode())
    for p in files:
        h.update(p.name.encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return "3." + h.hexdigest()[:10]


def load_extras(values):
    """stats.json (numbers made by src/distill_*.py; kb.json keeps the 'height' table) and standards.json (standard terms;
    kb.json keeps the terms values point to + NCIC SMT codes per marks value and place)."""
    stats, std = {}, {"terms": {}, "marks_codes": {}}
    sp, tp = HERE / "stats.json", HERE / "standards.json"
    full = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else {"terms": {}, "marks_codes": {}}
    if sp.exists():
        st = json.loads(sp.read_text(encoding="utf-8"))
        stats = {k: st[k] for k in ("height",) if k in st}
    used = {t for v in values.values() for t in v.get("std", [])}
    std["terms"] = {t: full["terms"][t]["label"] for t in sorted(used) if t in full["terms"]}
    std["marks_codes"] = full.get("marks_codes", {})
    for codes in std["marks_codes"].values():
        for c in codes.values():
            t = f"ncic_smt:{c}"
            if t in full["terms"]:
                std["terms"][t] = full["terms"][t]["label"]
    return stats, std, full


def assemble():
    vocab, values, where, cards, sources, rules, vi, golden, errs = load_sources()
    resolve, e = resolve_map(values)
    if e:
        errs.append(e)
        resolve = {}
    files = sorted((HERE / "catalog").glob("*.jsonl")) + [HERE / "rules.jsonl"] + \
        [p for p in (HERE / "stats.json", HERE / "standards.json") if p.exists()]
    ver = kb_version((HERE / "vocab.json").read_text(encoding="utf-8"), files)
    stats, std, std_full = load_extras(values)
    data = {"kb_version": ver, "schema": 3, "vocab": vocab, "values": values, "resolve": resolve, "rules": rules,
            "stats": stats, "std": std}
    unknown = sorted({t for v in values.values() for t in v.get("std", [])} - set(std_full["terms"]))
    errs += [f"std term {t} not in standards.json" for t in unknown]
    return data, where, cards, sources, vi, golden, errs


def check(verbose=True):
    data, where, cards, sources, vi, golden, errs = assemble()
    warns = []
    vocab, values = data["vocab"], data["values"]
    groups = [f"{s}-{b}" for s in ("male", "female") for b in vocab["age_bands"]]
    facets = vocab.get("facets", {})
    all_tags = {t for ts in facets.values() for t in ts}
    dup = [t for t in all_tags if sum(t in ts for ts in facets.values()) > 1]
    errs += [f"vocab.facets: tag {t} is in two facets (tags must be unique)" for t in dup]
    locw = vocab.get("marks", {}).get("loc_words", {})
    dims = vocab["dims"]
    lo_age, hi_age = vocab["age_limits"]
    for vid, v in values.items():
        loc = where.get(vid, vid)
        for f in ("id", "slot", "status", "sex", "age", "phrase", "causes", "freq", "sal", "baseline_for", "dims", "regions", "ev",
                  "needs", "fit"):
            if f not in v:
                errs.append(f"{loc}: missing field {f}")
        if any(f not in v for f in ("id", "slot", "status", "sex", "age", "phrase")):
            continue
        if not ID_RE.match(vid) or not vid.startswith(v["slot"] + "."):
            errs.append(f"{loc}: bad id {vid}")
        if v["status"] not in vocab["statuses"]:
            errs.append(f"{loc}: bad status {v['status']}")
        if v["status"] in ("merged", "split"):
            into = v.get("into")
            into = into if isinstance(into, list) else [into]
            for t in into:
                if t not in values:
                    errs.append(f"{loc}: into {t} does not exist")
        if v["sex"] not in vocab["sexes"]:
            errs.append(f"{loc}: bad sex")
        a = v["age"]
        if not (isinstance(a, list) and len(a) == 2 and lo_age <= a[0] <= a[1] <= hi_age):
            errs.append(f"{loc}: bad age {a}")
        ph = v["phrase"]
        multi = vocab["slots"].get(v["slot"], {}).get("multi")
        if "{loc}" in ph:
            if not multi:
                errs.append(f"{loc}: {{loc}} placeholder only allowed in multi slots")
            ph = ph.replace("{loc}", "left cheek")
        if multi and not v.get("baseline_for"):
            if not v.get("locs") or any(x not in locw for x in v["locs"]):
                errs.append(f"{loc}: multi-slot value needs 'locs' from vocab.marks.loc_words")
            elif "{loc}" not in v["phrase"]:
                errs.append(f"{loc}: multi-slot value phrase needs a {{loc}} placeholder")
        wc = len(ph.replace(",", " ").split())
        if not 3 <= wc <= 10:
            errs.append(f"{loc}: phrase has {wc} words")
        # optional "paint": image-prompt wording when the phrase does not render (concrete shapes, not abstract words)
        pt = v.get("paint")
        if pt is not None:
            if not isinstance(pt, str) or not pt.isascii() or not 3 <= len(pt.replace(",", " ").split()) <= 20:
                errs.append(f"{loc}: paint must be ASCII, 3-20 words")
            elif ("{loc}" in pt) != ("{loc}" in v["phrase"]):
                errs.append(f"{loc}: paint and phrase must both have or both lack {{loc}}")
        if not ph.isascii():
            errs.append(f"{loc}: phrase not ASCII")
        for rx, what in ((BEAUTY, "beauty word"), (CAUSE_WORDS, "cause word"), (CLOTHING, "clothing/object word")):
            m = rx.search(ph)
            if m:
                errs.append(f"{loc}: {what} '{m.group(0)}' in phrase: {ph}")
        for c in v.get("causes", []):
            if c not in vocab["causes"]:
                errs.append(f"{loc}: cause '{c}' not in vocab.causes")
        for key, rows, allowed in (("cls", v.get("freq", []), vocab["freq_classes"]), ("s", v.get("sal", []), vocab["salience"])):
            if not rows or any(r.get("when") for r in rows[:1]):
                errs.append(f"{loc}: {key} rows need a default row (no 'when') first")
            for r in rows:
                if r.get(key) not in allowed:
                    errs.append(f"{loc}: bad {key} {r.get(key)}")
                for wk, wv in r.get("when", {}).items():
                    if wk not in vocab["when_keys"] or (wk == "band" and wv not in vocab["age_bands"]) or (wk == "sex" and wv not in ("male", "female")):
                        errs.append(f"{loc}: bad when {wk}={wv}")
                if key == "cls" and r.get("basis") not in vocab["freq_basis"]:
                    errs.append(f"{loc}: bad freq basis {r.get('basis')}")
                if key == "cls" and r.get("basis") == "stat" and "p" not in r:
                    errs.append(f"{loc}: basis stat needs p")
        for d, rg in v.get("dims", {}).items():
            if d not in dims:
                errs.append(f"{loc}: dim {d} not in vocab")
            elif not (dims[d]["range"][0] <= rg[0] <= rg[1] <= dims[d]["range"][1]):
                errs.append(f"{loc}: dim {d} range {rg} out of scale")
        for r in v.get("regions", []):
            if r not in vocab["regions"]:
                errs.append(f"{loc}: region {r} not in vocab")
        for cond in v.get("needs", []):
            if not isinstance(cond, dict) or not cond:
                errs.append(f"{loc}: needs must be a list of non-empty {{facet: [values]}}")
                continue
            for f, allowed in cond.items():
                if f not in facets or any(a not in facets[f] for a in allowed):
                    errs.append(f"{loc}: needs {f}={allowed} not in vocab.facets")
        for t in v.get("fit", []):
            if t not in all_tags:
                errs.append(f"{loc}: fit tag {t} not in vocab.facets")
        for e in v.get("ev", []):
            if e.get("c") not in cards:
                errs.append(f"{loc}: card {e.get('c')} missing in evidence/")
            if e.get("rel") not in vocab["ev_rel"]:
                errs.append(f"{loc}: bad ev rel {e.get('rel')}")
        if "z" in v and not (v["slot"] == "height" and isinstance(v["z"], list) and len(v["z"]) == 2 and v["z"][0] < v["z"][1]):
            errs.append(f"{loc}: z band only for height values, as [lo, hi]")
        for g in v.get("baseline_for", []):
            eth = None
            if "/" in g:
                eth, g = g.split("/", 1)
                if eth not in all_tags:
                    errs.append(f"{loc}: bad baseline prefix {eth} (must be a facet tag)")
                elif eth not in facets.get("eth", []) and _S_facet(facets, eth) not in vocab.get("baseline_facets", []):
                    errs.append(f"{loc}: baseline prefix {eth}: its facet is not in vocab.baseline_facets")
            if g not in groups:
                errs.append(f"{loc}: bad baseline group {g}")
                continue
            sex, band = g.split("-")
            blo, bhi = vocab["age_bands"][band]
            if v["sex"] not in (sex, "any") or not (v["age"][0] <= blo and bhi <= v["age"][1]):
                errs.append(f"{loc}: baseline for {g} but sex/age do not cover it")
            if v["status"] != "active":
                errs.append(f"{loc}: inactive value is a baseline")
        if vid not in vi:
            warns.append(f"{loc}: no Vietnamese gloss in vi.jsonl")
    for cid, c in cards.items():
        if c.get("source") not in sources:
            errs.append(f"{where[cid]}: source {c.get('source')} not in sources.jsonl")
    for sid, s in sources.items():
        if s.get("license_needed") is not False or not s.get("terms"):
            errs.append(f"sources.jsonl {sid}: needs terms and license_needed=false (free sources only)")
    # ids.lock: ids never disappear
    lock = HERE / "ids.lock"
    if lock.exists():
        known = set(values) | {r["id"] for r in data["rules"]}
        for x in lock.read_text(encoding="utf-8").split():
            if x not in known:
                errs.append(f"ids.lock: id {x} was removed or renamed (never delete; use a tombstone with 'into')")
    # rules
    rids = set()
    for r in data["rules"]:
        if r.get("kind", "exclude") not in ("exclude", "hint"):
            errs.append(f"rules.jsonl {r['id']}: kind must be exclude or hint")
        if r.get("kind") == "hint" and r.get("basis") not in vocab["freq_basis"]:
            errs.append(f"rules.jsonl {r['id']}: a hint needs basis stat/proxy/est")
        if r["id"] in rids:
            errs.append(f"rules.jsonl: duplicate {r['id']}")
        rids.add(r["id"])
        for x in [r["a"]] + r["b"]:
            if x not in values:
                errs.append(f"rules.jsonl {r['id']}: unknown id {x}")
    if errs:
        return data, errs, warns
    kb = kbq.KB(data)
    # coverage: exactly one baseline per slot x group; enough choices
    for slot in kb.slots:
        ethb = Counter(b for v in kb.by_slot[slot] for b in v["baseline_for"] if "/" in b)
        errs += [f"coverage: {slot} {b} has {n} baselines" for b, n in ethb.items() if n > 1]
        for v in kb.by_slot[slot]:
            for b in v["baseline_for"]:
                if "/" in b:
                    t, g = b.split("/", 1)
                    sx, bd = g.split("-")
                    c = kbq.Ctx(sx, vocab["age_bands"][bd][0], frozenset([t]))
                    if not kb.needs_ok(v, c) or kb.baseline(slot, c)["id"] != v["id"]:
                        errs.append(f"coverage: {v['id']} is baseline for {b} but is not chosen for such a person")
        for g in groups:
            sex, band = g.split("-")
            bl = [v["id"] for v in kb.by_slot[slot] if g in v["baseline_for"]]
            if len(bl) != 1:
                errs.append(f"coverage: {slot} {g} has {len(bl)} baselines {bl}")
            elif not kb.needs_ok(kb.values[bl[0]], kbq.Ctx(sex, vocab["age_bands"][band][0])):
                errs.append(f"coverage: baseline {bl[0]} of {g} fails its own needs for the default population")
            lo, hi = vocab["age_bands"][band]
            for age in sorted({lo, hi, (lo + hi) // 2}):
                ctx = kbq.Ctx(sex, age)
                vals = [v for v in kb.by_slot[slot] if kb.fits(v, ctx) and not kb.is_baseline(v, ctx)]
                if len(vals) < 6:
                    warns.append(f"coverage: {slot} {sex} {age}: only {len(vals)} non-baseline values")
                if not any(kb.notable(v, ctx) for v in vals):
                    warns.append(f"coverage: {slot} {sex} {age}: no notable value")
    # baselines of each group must not conflict
    for g in groups:
        sex, band = g.split("-")
        ctx = kbq.Ctx(sex, vocab["age_bands"][band][0])
        bl = {s: kb.baseline(s, ctx)["id"] for s in kb.slots}
        for c in kb.check(bl, ctx):
            errs.append(f"baselines {g} conflict: {c['msg']}")
    # golden tests
    for n, gt in enumerate(golden, 1):
        kind = gt.get("kind", "pairs")
        if kind != "pairs":
            errs += [f"golden {n}: {e}" for e in golden_other(kb, gt)]
            continue
        ctx = kbq.Ctx(gt["sex"], gt["age"], frozenset(gt.get("tags", [])))
        got = kb.check(gt["picks"], ctx)
        if gt["expect"] == "conflict" and not got:
            errs.append(f"golden {n}: expected a conflict, none found ({gt.get('note', '')})")
        if gt["expect"] in ("ok", "covers") and got:
            errs.append(f"golden {n}: expected ok, got {[c['msg'] for c in got]}")
        if gt["expect"] == "covers":
            _, cov = kb.fill(gt["picks"], ctx)
            miss = [s for s in gt["covers"] if s not in cov]
            if miss:
                errs.append(f"golden {n}: baseline of {miss} should be covered ({gt.get('note', '')})")
    # budget: one slot menu must fit well inside a call
    cpt = vocab["budget"]["chars_per_token"]
    worst = 0
    for g in groups:
        sex, band = g.split("-")
        ctx = kbq.Ctx(sex, vocab["age_bands"][band][0])
        for slot in kb.slots:
            txt, _ = kb.render(slot, kb.menu(slot, ctx), ctx)
            worst = max(worst, kbq.est_tokens(txt, cpt))
    if worst > vocab["budget"]["call_tokens"] // 6:
        errs.append(f"budget: a single slot menu is ~{worst} tokens; lower budget.menu_k")
    if verbose:
        print(f"kb {data['kb_version']}: {sum(v['status'] == 'active' for v in values.values())} active values, "
              f"{len(cards)} cards, {len(sources)} sources, {len(data['rules'])} rules, {len(golden)} golden tests; "
              f"largest slot menu ~{worst} tokens")
    return data, errs, warns


def golden_other(kb, gt):
    """Golden kinds besides pairs: menu (life filters), cite (reasons for rare/notable picks), facts (parsing)."""
    note = f" ({gt['note']})" if gt.get("note") else ""
    if gt["kind"] == "menu":
        ctx = kbq.Ctx(gt["sex"], gt["age"], frozenset(gt.get("tags", [])))
        ids = {v["id"] for v in kb.by_slot[gt["slot"]] if kb.fits(v, ctx)}
        return ([f"menu {gt['slot']} should exclude {x}{note}" for x in gt.get("excludes", []) if x in ids] +
                [f"menu {gt['slot']} should include {x}{note}" for x in gt.get("includes", []) if x not in ids])
    if gt["kind"] == "baseline":
        ctx = kbq.Ctx(gt["sex"], gt["age"], frozenset(gt.get("tags", [])))
        got = kb.baseline(gt["slot"], ctx)["id"]
        return [] if got == gt["expect"] else [f"baseline {gt['slot']} for {ctx.group} {sorted(ctx.tags)}: {got}, expected {gt['expect']}{note}"]
    if gt["kind"] == "height":
        ctx = kbq.Ctx(gt["sex"], gt["age"], frozenset(gt.get("tags", [])))
        hc = kb.height_cm(ctx, gt.get("born"))
        lo, hi = gt["mean_between"]
        return [] if hc and lo <= hc["mean"] <= hi else [f"height mean {hc and hc['mean']} not in {gt['mean_between']}{note}"]
    if gt["kind"] == "freq":
        ctx = kbq.Ctx(gt["sex"], gt["age"], frozenset(gt.get("tags", [])))
        got = kb.cls(kb.get(gt["id"]), ctx)
        return [] if got == gt["expect"] else [f"freq {gt['id']} {ctx.group}: {got}, expected {gt['expect']}{note}"]
    if gt["kind"] == "hint":
        ctx = kbq.Ctx(gt["sex"], gt["age"], frozenset(gt.get("tags", [])))
        h, c = kb.hints(gt["picks"], ctx), kb.check(gt["picks"], ctx)
        return ([] if h else [f"hint expected for {gt['picks']}{note}"]) + ([f"a hint must not be a conflict: {c}"] if c else [])
    if gt["kind"] == "cite":
        f = kb.facts(gt.get("identity", ""), gt.get("life", ""), gt.get("style", ""))
        prob = kb.cite_problem(gt["slot"], gt["pick"], gt.get("cite", ""), f, why=gt.get("why", ""))
        if gt["expect"] == "reject" and not prob:
            return [f"cite {gt['pick']} '{gt.get('cite')}' should be rejected{note}"]
        if gt["expect"] == "ok" and prob:
            return [f"cite {gt['pick']} '{gt.get('cite')}' should pass: {prob}{note}"]
        return []
    if gt["kind"] == "facts":
        f = kb.facts(gt.get("identity", ""), gt.get("life", ""), gt.get("style", ""))
        out = [f"facts should have tag {t}{note}" for t in gt.get("tags", []) if t not in f.tags]
        out += [f"facts should not have tag {t}{note}" for t in gt.get("not_tags", []) if t in f.tags]
        for n, cs in gt.get("life_tags", {}).items():
            out += [f"LIFE {n} should carry {c}{note}" for c in cs if c not in f.life_tags.get(int(n), set())]
        for n, cs in gt.get("life_not", {}).items():
            out += [f"LIFE {n} should not carry {c}{note}" for c in cs if c in f.life_tags.get(int(n), set())]
        return out
    return [f"unknown golden kind {gt['kind']}"]


def build():
    data, errs, warns = check()
    golden = [g for _, g in read_jsonl(HERE / "tests" / "golden.jsonl")]
    report(errs, warns)
    if errs:
        sys.exit(1)
    (HERE / "kb.json").write_text(json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8")
    lock = HERE / "ids.lock"
    old = set(lock.read_text(encoding="utf-8").split()) if lock.exists() else set()
    ids = old | set(data["values"]) | {r["id"] for r in data["rules"]}
    lock.write_text("\n".join(sorted(ids)) + "\n", encoding="utf-8")
    kb = kbq.KB(data)
    lines = [f"# KB build report (generated by kb.py build; do not edit)", "", f"kb_version: `{data['kb_version']}`", "",
             "| grp | slot | active | male | female | baselines | with evidence | dims | regions | needs | fit |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    for s in kb.slots:
        vs = kb.by_slot[s]
        g = data["vocab"]["slots"][s]["group"]
        row = [len(vs), sum(v['sex'] in ('male', 'any') for v in vs), sum(v['sex'] in ('female', 'any') for v in vs),
               sum(bool(v['baseline_for']) for v in vs), sum(bool(v['ev']) for v in vs), sum(bool(v['dims']) for v in vs),
               sum(bool(v['regions']) for v in vs), sum(bool(v['needs']) for v in vs), sum(bool(v['fit']) for v in vs)]
        tot[g] += row[0]
        lines.append(f"| {g} | {s} | " + " | ".join(map(str, row)) + " |")
    lines += ["", "active values per group: " + ", ".join(f"{g} {n}" for g, n in sorted(tot.items()))]
    gk = Counter(g.get("kind", "pairs") for g in golden)
    lines += ["", f"golden tests: {len(golden)} ({', '.join(f'{k} {n}' for k, n in sorted(gk.items()))}), all passing",
              "life facets: " + "; ".join(f"{f}: {', '.join(ts)}" for f, ts in data['vocab'].get('facets', {}).items()),
              f"values with needs: {sum(bool(v.get('needs')) for v in data['values'].values() if v['status'] == 'active')}, "
              f"with fit: {sum(bool(v.get('fit')) for v in data['values'].values() if v['status'] == 'active')}, "
              f"eth-specific baselines: {sum(1 for v in data['values'].values() for b in v['baseline_for'] if '/' in b)}"]
    basis = Counter(r["basis"] for v in data["values"].values() for r in v["freq"])
    nstd = sum(bool(v.get("std")) for v in data["values"].values() if v["status"] == "active")
    fb = sorted({b.split("/")[0] for v in data["values"].values() for b in v["baseline_for"] if "/" in b})
    lines += ["", f"freq basis (rows): {dict(basis)}; values with a stat row: "
              f"{sum(any(r['basis'] == 'stat' for r in v['freq']) for v in data['values'].values())}",
              f"values mapped to standard terms (std): {nstd}; std terms in kb.json: {len(data['std']['terms'])}; "
              f"marks values with NCIC codes: {len(data['std']['marks_codes'])}",
              f"baseline prefixes (eth / life facts): {', '.join(fb)}",
              f"rules: {sum(r.get('kind', 'exclude') == 'exclude' for r in data['rules'])} exclude, "
              f"{sum(r.get('kind') == 'hint' for r in data['rules'])} hint",
              ""] + provenance_vi() + ["", f"warnings: {len(warns)}"] + [f"- {w}" for w in warns[:40]]
    (HERE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"built kb.json ({(HERE / 'kb.json').stat().st_size // 1024} KB), ids.lock ({len(ids)} ids), report.md")


def provenance_vi():
    """Vietnamese section of report.md: which numbers came from where (read from stats.json, so it stays in sync)."""
    sp = HERE / "stats.json"
    if not sp.exists():
        return []
    st = json.loads(sp.read_text(encoding="utf-8"))
    out = ["## Số liệu từ đâu (tiếng Việt, sinh từ stats.json)", ""]
    h = st.get("height", {})
    if h:
        m = lambda k: h["by"].get(k, {}).get("mean", "?")  # noqa: E731
        out.append(f"- **Chiều cao** (`height.*`, `basis: stat`): trung bình người trưởng thành VN theo năm sinh từ NCD-RisC "
                   f"(eLife 2016; lớp sinh 1997-2000 lấy từ Lancet 2020 tuổi 19, dời theo độ lệch chồng lấn). Nam sinh 1950s "
                   f"{m('kinh/male/1950')} cm, 1970s {m('kinh/male/1970')}, 2000 {m('kinh/male/2000')}; nữ {m('kinh/female/1950')}, "
                   f"{m('kinh/female/1970')}, {m('kinh/female/2000')}. Dải z (rất thấp < -2 ... rất cao > 2) so với cùng giới, cùng "
                   f"lớp sinh, cùng dân tộc; SD là PROXY (nam {h['sd']['male']}, nữ {h['sd']['female']} cm, từ ANSUR II và CI của "
                   f"STEPS). Bảng: `evidence/num/ncdrisc_height_*.csv`, `height_bands.csv`; `kb.height_cm(ctx, born)`.")
    if "bmi" in st:
        out.append("- **Béo/gầy** (`fat.*`): tỉ lệ theo lớp BMI của NCD-RisC 2024 cho VN, theo giới x dải tuổi (`evidence/num/"
                   "ncdrisc_bmi_vn.csv`); rất gầy < 18.5, gầy 18.5-20, thường 20-25, thừa cân 25-30, béo 30-35, rất béo >= 35. "
                   "WHO STEPS VN 2021/2015 (đo thật) đối chiếu: thiếu cân nam 11.6/6.9/10.3%, nữ 20.8/5.3/6.3% (18-29/30-49/50-69, "
                   "Bảng 32 tr.46); thành thị béo hơn nông thôn (BMI >= 25: 24.2 vs 16.7%, Bảng 55) -> `fit` urban/rural.")
    if "steps" in st:
        out.append("- **Vòng eo** (`waist_belly.soft-m`, `thick-meno-f`): STEPS 2021 Bảng A27 tr.86, vượt ngưỡng 90/85 cm: nam "
                   "8.6/16.6/18.6%, nữ 11.4/15.1/33.3%.")
    if "kinh_face" in st:
        out.append("- **Mặt, đầu, mũi** (`head.*`, `face_shape.*`, `nose.*`, `mouth.protruding`, `jaw_chin.delicate`): TCNCYH 2023 "
                   "(Kinh 18-25, 3068 nam / 4308 nữ), Bảng 2-6: chỉ số đầu, mặt toàn bộ, mũi, vẩu, hàm; VMJ 2021 (n 2462): mặt "
                   "oval 66.3%, vuông 26.6%, tam giác 7.1%. Bảng: `evidence/num/kinh_face.csv`.")
    if "maad" in st or "ansur" in st:
        out.append("- **PROXY, không đặt tần suất VN**: MAAD-Face (nhãn máy trên ảnh người nổi tiếng, lệch giới) chỉ cho luật "
                   "R0013 (mặt oval thon không đi với cằm đôi); ANSUR II (lính Mỹ) chỉ cho các gợi ý mềm H0001-H0006 (người rất "
                   "thấp hiếm vai rộng...), `kb.hints()`, không bao giờ là mâu thuẫn.")
    out.append("- **Từ vựng chuẩn** (`std` trên giá trị, `standards.json`): Interpol DVI AM 2023, mã NCIC SMT/EYE/HAIR/SKIN, mẫu "
               "truy nã TT 22/2014 (mẫu 30a/30b), NIH Elements of Morphology (chỉ nhãn). Các giá trị còn lại vẫn là `est` "
               "(ước lượng từ sách). AIST 1991-92 bỏ qua: bảng là ảnh GIF, cấm sao chép.")
    return out


def report(errs, warns):
    for w in warns:
        print("WARN", w)
    for e in errs:
        print("ERROR", e)
    print("check:", "FAIL" if errs else "OK", f"({len(errs)} errors, {len(warns)} warnings)")


def find(q):
    data, *_ = assemble()
    qs = set(re.findall(r"[a-z]+", q.lower()))
    scored = []
    for v in data["values"].values():
        ws = set(re.findall(r"[a-z]+", v["phrase"].lower()))
        j = len(qs & ws) / max(1, len(qs | ws))
        scored.append((j, v["id"], v["phrase"]))
    for j, i, p in sorted(scored, reverse=True)[:10]:
        print(f"{j:.2f}  {i}  | {p}")


def facts_cmd(cdir):
    kb = kbq.load()
    d = Path(cdir)

    def rd(n):
        p = d / f"{n}.en.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""
    f = kb.facts(rd("IDENTITY"), rd("LIFE"), rd("STYLE"))
    print(f"{f.sex} {f.age} group {f.ctx.group} eth {f.ctx.eth}")
    for t in sorted(f.tags):
        print(f"  {t:16} <- {f.src.get(t)}")
    for k, t in f.field_tags.items():
        print(f"  IDENTITY {k}: {sorted(t)}")
    for n, t in f.life_tags.items():
        print(f"  LIFE {n}: {sorted(t)}")


def menu(sex, age, slots):
    kb = kbq.load()
    tags = []
    if "--tags" in slots:
        i = slots.index("--tags")
        tags = slots[i + 1].split(",")
        slots = slots[:i] + slots[i + 2:]
    ctx = kbq.Ctx(sex, int(age), frozenset(tags))
    tot = 0
    for s in slots or kb.slots:
        txt, _ = kb.render(s, kb.menu(s, ctx), ctx)
        t = kbq.est_tokens(txt)
        tot += t
        print(txt, f"\n  (~{t} tokens)")
    print(f"group {ctx.group}: all menus ~{tot} tokens")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        _, e, w = check()
        report(e, w)
        sys.exit(1 if e else 0)
    elif cmd == "build":
        build()
    elif cmd == "find":
        find(" ".join(sys.argv[2:]))
    elif cmd == "menu":
        menu(sys.argv[2], sys.argv[3], sys.argv[4:])
    elif cmd == "facts":
        facts_cmd(sys.argv[2])
    else:
        print(__doc__)
