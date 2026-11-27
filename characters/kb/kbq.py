"""kbq: query module for the character LOOK knowledge base (kb.json, built by kb.py). Schema 3.

    import sys; sys.path.insert(0, "<repo>/characters/kb"); import kbq
    kb = kbq.load()
    facts = kb.facts(identity_text, life_text, style_text)   # tags code can read (means, life, diet, ...) + LIFE items
    ctx = facts.ctx                                           # kbq.Ctx(sex, age, tags)
    kb.menu("waist_belly", ctx, counts=..., cap=2, locked={...}, k=14, seed="demo/lao_bay")
    kb.check({"frame": "frame.stocky-m", "chest": "chest.thin-m"}, ctx)   # -> conflicts
    kb.cite_problem("gait", "gait.dragfoot", "LIFE 5", facts)              # -> None or a message for a FIX prompt
    kb.fill(picks, ctx); kb.prompt(full, ctx)
A marks pick is a list of "<id>@<loc>" strings. See AGENTS.md.
"""
import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB_JSON = HERE / "kb.json"
SAL_RANK = {"plain": 0, "mild": 1, "marked": 2}


class _State:
    bands = {"young": [18, 29], "adult": [30, 44], "middle": [45, 64], "elderly": [65, 120]}
    facet_of = {}            # tag -> facet
    eth_default = "kinh"

    def band(self, age):
        for k, (lo, hi) in self.bands.items():
            if lo <= age <= hi:
                return k
        return "young" if age < 18 else "elderly"


_S = _State()


@dataclass(frozen=True)
class Ctx:
    sex: str
    age: int
    tags: frozenset = frozenset()

    @property
    def band(self):
        return _S.band(self.age)

    @property
    def group(self):
        return f"{self.sex}-{self.band}"

    @property
    def eth(self):
        e = [t for t in self.tags if _S.facet_of.get(t) == "eth"]
        return sorted(e)[0] if e else _S.eth_default

    def facet(self, name):
        return {t for t in self.tags if _S.facet_of.get(t) == name}


@dataclass
class Facts:
    """What code read from the character files. tags: facet tags; src: tag -> where it was read;
    fields: IDENTITY field -> text; life: {n: text}; field_tags / life_tags: cause tags per field / LIFE item."""
    sex: str = "male"
    age: int = 30
    tags: set = field(default_factory=set)
    src: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)
    life: dict = field(default_factory=dict)
    field_tags: dict = field(default_factory=dict)
    life_tags: dict = field(default_factory=dict)
    born: int = None

    @property
    def ctx(self):
        return Ctx(self.sex, self.age, frozenset(self.tags))

    def facet_tags(self, name):
        return {t for t in self.tags if _S.facet_of.get(t) == name}

    def line(self):
        """One line for model prompts: facet=value list, what code knows."""
        by = {}
        for t in sorted(self.tags):
            by.setdefault(_S.facet_of.get(t, "?"), []).append(t)
        return "; ".join(f"{f}={','.join(v)}" for f, v in by.items())


def split_pick(p):
    """'marks.mole@cheek-l' -> ('marks.mole', 'cheek-l'); plain ids -> (id, None)."""
    if "@" in p:
        a, b = p.split("@", 1)
        return a, b
    return p, None


def ctx_from_identity(text):
    sex = "female" if re.search(r"Sex:\s*female", text, re.I) else "male"
    m = re.search(r"Age:\s*(\d+)", text)
    return Ctx(sex, int(m.group(1)) if m else 30)


def est_tokens(text, cpt=3.5):
    return int(len(text) / cpt) + 8


def _resolve_rows(rows, ctx, key):
    """rows: [{"when": {...}, key: ...}]; most specific matching row wins."""
    best, score = None, -1
    for r in rows:
        w = r.get("when", {})
        if all((ctx.sex if k == "sex" else ctx.band if k == "band" else None) == v for k, v in w.items()):
            if len(w) > score:
                best, score = r, len(w)
    return best[key] if best else None


def parse_identity(text):
    out = {}
    for m in re.finditer(r"^\s*-\s*([A-Z][A-Za-z ]{1,30}):\s*(.*)$", text, re.M):
        out.setdefault(m.group(1).strip(), m.group(2).strip())
    return out


def parse_life(text):
    """Numbered items '1. ...' (continuation lines belong to the item above)."""
    items, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(.*)", line)
        if m:
            cur = int(m.group(1))
            items[cur] = m.group(2)
        elif cur is not None and line.strip() and not line.startswith("#"):
            items[cur] += " " + line.strip()
    return items


def life_event(text):
    """The event part of a LIFE item: what happened, without the character's 'Interpretation:' (a belief is not a cause)."""
    return re.split(r"\b(?:Interpretation|He thinks|She thinks|Meaning)\s*:", text, maxsplit=1)[0]


class KB:
    def __init__(self, data):
        self.d = data
        self.version = data["kb_version"]
        self.vocab = data["vocab"]
        self.values = data["values"]
        self.slots = sorted(self.vocab["slots"], key=lambda s: self.vocab["slots"][s]["order"])
        self.by_slot = {s: [] for s in self.slots}
        for v in self.values.values():
            if v["status"] == "active":
                self.by_slot[v["slot"]].append(v)
        for s in self.by_slot:
            self.by_slot[s].sort(key=lambda v: v["id"])
        self.base_idx = {}
        for s, vs in self.by_slot.items():
            for v in vs:
                for g in v["baseline_for"]:
                    self.base_idx[(s, g)] = v["id"]
        self.rules = [r for r in data["rules"] if r["status"] == "active"]
        self.excl, self.soft = {}, {}
        for r in self.rules:
            tab = self.soft if r.get("kind") == "hint" else self.excl
            for b in r["b"]:
                tab.setdefault(r["a"], {})[b] = r
                tab.setdefault(b, {})[r["a"]] = r
        self.stats = data.get("stats", {})
        self.std_terms = data.get("std", {}).get("terms", {})
        self.std_marks = data.get("std", {}).get("marks_codes", {})
        _S.bands = self.vocab["age_bands"]
        _S.facet_of = {t: f for f, ts in self.vocab.get("facets", {}).items() for t in ts}
        _S.eth_default = self.vocab.get("eth_default", "kinh")
        self.marks = self.vocab.get("marks", {})
        self._vi = None

    # ------------------------------------------------------------ lookups
    def get(self, vid):
        return self.values[split_pick(vid)[0]]

    def resolve(self, vid):
        """id -> list of current active ids (follows merged/split tombstones)."""
        return self.d["resolve"].get(split_pick(vid)[0], [])

    def loc_word(self, loc):
        return self.marks.get("loc_words", {}).get(loc, loc.replace("-", " "))

    def phrase(self, pick):
        vid, loc = split_pick(pick)
        ph = self.values[vid]["phrase"]
        return ph.replace("{loc}", self.loc_word(loc)) if "{loc}" in ph else ph

    def paint(self, pick):
        """Image-prompt wording: the value's "paint" if it has one (concrete shapes the painter renders), else its phrase."""
        vid, loc = split_pick(pick)
        ph = self.values[vid].get("paint") or self.values[vid]["phrase"]
        return ph.replace("{loc}", self.loc_word(loc)) if "{loc}" in ph else ph

    def vi(self, pick):
        vid, loc = split_pick(pick)
        if self._vi is None:
            self._vi = {}
            p = HERE / "vi.jsonl"
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    r = json.loads(line)
                    self._vi[r["id"]] = r["vi"]
        return self._vi.get(vid, "").replace("{loc}", loc or "")

    def multi(self, slot):
        return bool(self.vocab["slots"][slot].get("multi"))

    def items(self, picks):
        """{slot: id | [id@loc, ...]} -> [(slot, pick)] flattened."""
        out = []
        for s, p in picks.items():
            if not p:
                continue
            for x in (p if isinstance(p, list) else [p]):
                out.append((s, x))
        return out

    # ------------------------------------------------------------ filters
    def needs_ok(self, v, ctx):
        """Value allowed by what code knows about the person: any one condition holds; inside a condition every facet
        the person has a tag for must match (unknown facets pass). 'mixed' passes every eth condition."""
        if not v.get("needs"):
            return True
        for cond in v["needs"]:
            ok = True
            for f, allowed in cond.items():
                have = ctx.facet(f) if f != "eth" else {ctx.eth}
                if f == "eth" and "mixed" in have:
                    continue
                if have and not (have & set(allowed)):
                    ok = False
                    break
            if ok:
                return True
        return False

    def fits(self, v, ctx):
        return v["sex"] in (ctx.sex, "any") and v["age"][0] <= ctx.age <= v["age"][1] and self.needs_ok(v, ctx)

    def fit_score(self, v, ctx):
        return len(set(v.get("fit", [])) & set(ctx.tags))

    def cls(self, v, ctx):
        return _resolve_rows(v["freq"], ctx, "cls")

    def sal(self, v, ctx, loc=None):
        s = _resolve_rows(v["sal"], ctx, "s")
        if loc and loc in self.marks.get("hidden", []) and SAL_RANK[s] > 1:
            s = "mild"
        return s

    def baseline_keys(self, ctx):
        """Baseline lookup order for a person: '<eth>/<group>', then '<tag>/<group>' for life facts in vocab.baseline_facets
        order (e.g. sun exposure: 'sea/male-elderly'), then '<group>'."""
        keys = [f"{ctx.eth}/{ctx.group}"]
        for fct in self.vocab.get("baseline_facets", []):
            for t in self.vocab["facets"].get(fct, []):
                if t in ctx.tags:
                    keys.append(f"{t}/{ctx.group}")
        return keys + [ctx.group]

    def _bkey(self, slot, ctx_or_group):
        if isinstance(ctx_or_group, str):
            return ctx_or_group
        for k in self.baseline_keys(ctx_or_group):
            vid = self.base_idx.get((slot, k))
            if vid and (k == ctx_or_group.group or self.needs_ok(self.values[vid], ctx_or_group)):
                return k
        return ctx_or_group.group

    def is_baseline(self, v, ctx_or_group):
        if isinstance(v, str):
            v = self.get(v)
        return self.base_idx.get((v["slot"], self._bkey(v["slot"], ctx_or_group))) == v["id"]

    def near_plain(self, v, ctx, loc=None):
        return not self.is_baseline(v, ctx) and self.sal(v, ctx, loc) in ("plain", "mild")

    def notable(self, v, ctx, loc=None):
        return not self.is_baseline(v, ctx) and self.sal(v, ctx, loc) == "marked"

    def baseline(self, slot, ctx):
        vid = self.base_idx.get((slot, self._bkey(slot, ctx)))
        if not vid:
            raise KeyError(f"no baseline for {slot} {ctx.group}")
        return self.values[vid]

    # ------------------------------------------------------------ facts from character files
    def facts(self, identity, life="", style="", soul=""):
        fields = parse_identity(identity)
        ctx0 = ctx_from_identity(identity)
        f = Facts(sex=ctx0.sex, age=ctx0.age, fields=fields, life=parse_life(life))
        fk = self.vocab.get("fact_keywords", {})
        ff = self.vocab.get("fact_fields", {})
        skip = set(self.vocab.get("cite", {}).get("identity_skip", []))
        style_lines = {}
        for m in re.finditer(r"^\s*-\s*([a-z][a-z ]{1,30}):\s*(.*)$", style, re.M):
            style_lines[m.group(1).strip()] = m.group(2)
        for facet, table in fk.items():
            srcs = [(f"IDENTITY {k}", t) for k, t in fields.items() if k not in skip and re.search(ff.get(facet, "."), k, re.I)]
            srcs += [(f"STYLE {k}", t) for k, t in style_lines.items() if re.search(ff.get(facet, "."), k, re.I)]
            for tag, rx in table:
                hit = next((name for name, txt in srcs if re.search(rx, txt, re.I)), None)
                if hit:
                    f.tags.add(tag)
                    f.src.setdefault(tag, hit)
                    if facet in ("means", "diet", "alcohol", "smoke", "eth"):
                        break           # one value per facet (priority order)
        if not f.facet_tags("eth"):
            f.tags.add(_S.eth_default)
            f.src[_S.eth_default] = "default"
        if not f.facet_tags("diet") and f.facet_tags("means") & {"poor", "destitute"}:
            f.tags.add("plain-diet")
            f.src["plain-diet"] = f.src.get("poor", f.src.get("destitute")) + " (derived)"
        year = next((int(y) for k, t in fields.items() if re.search("era|year|place", k, re.I)
                     for y in re.findall(r"\b(1[89]\d\d|20\d\d)\b", t)), None)
        if year:
            born = year - f.age
            f.born = born
            tag = "born-pre1960" if born < 1960 else "born-1960-1989" if born < 1990 else "born-1990plus"
            f.tags.add(tag)
            f.src[tag] = f"IDENTITY Age + year {year}"
        ck = self.vocab.get("cause_keywords", {})
        od = self.vocab.get("other_death", "")
        only_sex = self.vocab.get("cause_only_sex", {})

        def ctags(text):
            t = {c for c, rx in ck.items() if re.search(rx, text, re.I)}
            if od and re.search(od, text, re.I):
                t -= {"injury", "illness"}
            return {c for c in t if only_sex.get(c, f.sex) == f.sex}
        for k, t in fields.items():
            if k in skip:
                continue
            tg = ctags(t)
            if re.match("age", k, re.I):
                tg |= {"ageing", "hormones"} if f.age >= 45 else {"youth"} if f.age <= 29 else set()
            if re.match("nation|ethnic|hometown|origin|race|people", k, re.I):
                tg |= {"genetics", "climate"}
            f.field_tags[k] = tg
        f.life_tags = {n: ctags(life_event(t)) for n, t in f.life.items()}
        return f

    # ------------------------------------------------------------ reasons for rare / notable picks
    def needs_cite(self, v, ctx, loc=None):
        return not self.is_baseline(v, ctx) and (self.cls(v, ctx) == "rare" or self.sal(v, ctx, loc) == "marked")

    def parse_cite(self, cite, facts, slot):
        """-> ('LIFE', n) | ('IDENTITY', field) | ('SOUL', None) | (None, message)."""
        cite = cite or ""
        m = re.search(r"\bLIFE\s*(?:item\s*)?#?\s*(\d+)", cite, re.I)
        if m:
            n = int(m.group(1))
            return ("LIFE", n) if n in facts.life else (None, f"LIFE {n} does not exist (LIFE has items {sorted(facts.life)})")
        m = re.search(r"\bIDENTITY\W*([A-Za-z][A-Za-z ]*)", cite, re.I)
        if m:
            want = m.group(1).strip().lower()
            for k in facts.fields:
                if want.startswith(k.lower()) or k.lower().startswith(want[:6]):
                    return "IDENTITY", k
            return None, f"IDENTITY has no field '{m.group(1).strip()}' (fields: {', '.join(facts.fields)})"
        if re.search(r"\b(FACTS|STYLE)\b", cite):
            if self.facet_causes(facts):
                return "FACTS", None
            return None, "FACTS shows nothing for this person (no drinking, smoking, diet or work facts were read)"
        if re.search(r"\bSOUL\b", cite):
            if self.vocab["slots"][slot].get("soul"):
                return "SOUL", None
            return None, f"SOUL may justify only {', '.join(s for s, m in self.vocab['slots'].items() if m.get('soul'))}"
        return None, "no reason cited: give a LIFE item number, an IDENTITY field, or FACTS (habits code read)"

    def claimed_causes(self, text):
        """Specific causes a free-text reason asserts ('from an old injury' -> {'injury'}); vocab.cite.claim_causes."""
        if not text:
            return set()
        ck = self.vocab.get("cause_keywords", {})
        return {c for c in self.vocab.get("cite", {}).get("claim_causes", []) if c in ck and re.search(ck[c], text, re.I)}

    def facet_causes(self, facts):
        """Causes implied by facet tags code read (smoker -> substances, sea -> water-work ...): vocab.cite.facet_causes."""
        fc = self.vocab.get("cite", {}).get("facet_causes", {})
        return {c for t in facts.tags for c in fc.get(t, [])}

    def cite_problem(self, slot, pick, cite, facts, ctx=None, why=""):
        """None if the pick needs no reason or the cited reason is valid; else a message for a FIX prompt.
        The cited item must carry one of the value's causes. Generic causes are not a free pass: they are carried only by
        the fitting place (IDENTITY Age -> ageing/youth/hormones, Nationality/Hometown -> genetics/climate, SOUL ->
        temperament). `why` (the character's own words, e.g. the plan idea) may not claim a specific cause (injury,
        illness, ...) that the cited item does not show."""
        ctx = ctx or facts.ctx
        v = self.get(pick)
        loc = split_pick(pick)[1]
        if not self.needs_cite(v, ctx, loc):
            return None
        kind, ref = self.parse_cite(cite, facts, slot)
        what = f'"{self.phrase(pick)}" ({slot}, {self.cls(v, ctx)}, {self.sal(v, ctx, loc)})'
        if kind is None:
            return f"{what} needs a reason: {ref}."
        causes = set(v["causes"])
        cr = self.vocab.get("cite", {})
        tags = (facts.life_tags.get(ref, set()) if kind == "LIFE" else facts.field_tags.get(ref, set()) if kind == "IDENTITY"
                else self.facet_causes(facts) if kind == "FACTS" else set(cr.get("soul_causes", [])))
        src = f"LIFE {ref}" if kind == "LIFE" else f"IDENTITY {ref}" if kind == "IDENTITY" else kind
        if not causes & tags:
            opts = self.cite_options(slot, v, facts)
            hint = f" Valid: {' / '.join(opts)}." if opts else " Nothing in your files shows it."
            return (f"{what} needs a cause among [{', '.join(sorted(causes))}], but {src} does not show one; pick another value "
                    f"or cite an item that does.{hint}")
        implied = {i for t in tags for i in cr.get("implies", {}).get(t, [])}      # a burn is an injury too
        claimed = self.claimed_causes(why) - tags - implied - self.facet_causes(facts)
        if claimed:
            return (f"{what}: your reason claims {', '.join(sorted(claimed))}, but {src} does not show it and nothing else in "
                    f"your files does; drop that claim or pick another value.")
        return None

    def cite_options(self, slot, v, facts, n=2):
        """Valid cites for a value (for menus): LIFE items / IDENTITY fields whose cause tags match, SOUL for soul slots.
        [] means nothing in the files explains it (a rare or notable pick would be rejected)."""
        if isinstance(v, str):
            v = self.get(v)
        causes = set(v["causes"])
        cr = self.vocab.get("cite", {})
        out = [f"LIFE {k}" for k, t in sorted(facts.life_tags.items()) if causes & t]
        out += [f"IDENTITY {k}" for k, t in facts.field_tags.items() if causes & t]
        if self.vocab["slots"][slot].get("soul") and causes & set(cr.get("soul_causes", [])):
            out.insert(0, "SOUL")
        if causes & self.facet_causes(facts):
            out.append("FACTS")
        return out[:n]

    def life_explained(self, slot, pick, cite, facts):
        """True if a LIFE item with a matching specific (non-generic) cause is cited: such a rare value is free of the rare cap."""
        kind, ref = self.parse_cite(cite, facts, slot)
        if kind != "LIFE":
            return False
        causes = set(self.get(pick)["causes"]) - set(self.vocab.get("cite", {}).get("generic", []))
        return bool(causes & facts.life_tags.get(ref, set()))

    # ------------------------------------------------------------ conflicts
    def pair_conflicts(self, a, b, ctx, pa=None, pb=None):
        """Conflicts between two values (dicts). Baselines never claim regions."""
        out = []
        pa, pb = pa or a["id"], pb or b["id"]
        for dim, (lo, hi) in a["dims"].items():
            if dim in b["dims"]:
                lo2, hi2 = b["dims"][dim]
                if max(lo, lo2) > min(hi, hi2):
                    out.append({"kind": "dims", "dim": dim, "ids": [pa, pb],
                                "msg": f'"{self.phrase(pa)}" ({a["slot"]}) and "{self.phrase(pb)}" ({b["slot"]}) cannot be the same '
                                       f'person ({dim}: {lo}-{hi} vs {lo2}-{hi2}).'})
        if a["slot"] != b["slot"] and not self.is_baseline(a, ctx) and not self.is_baseline(b, ctx):
            shared = sorted(set(a["regions"]) & set(b["regions"]))
            if shared:
                out.append({"kind": "region", "region": shared[0], "ids": [pa, pb],
                            "msg": f'Two slots describe the same feature ({shared[0].replace("_", " ")}): "{self.phrase(pa)}" '
                                   f'({a["slot"]}) and "{self.phrase(pb)}" ({b["slot"]}); keep one.'})
        r = self.excl.get(a["id"], {}).get(b["id"])
        if r:
            out.append({"kind": "rule", "rule": r["id"], "ids": [pa, pb],
                        "msg": f'"{self.phrase(pa)}" ({a["slot"]}) and "{self.phrase(pb)}" ({b["slot"]}) do not go together: {r["why"]}.'})
        return out

    def check(self, picks, ctx):
        """picks: {slot: id | [id@loc]}. Returns conflicts (dims, regions, rules) among the given values."""
        its = self.items(picks)
        out = []
        for i in range(len(its)):
            for j in range(i + 1, len(its)):
                a, b = self.get(its[i][1]), self.get(its[j][1])
                if a["id"] == b["id"]:
                    continue
                out.extend(self.pair_conflicts(a, b, ctx, its[i][1], its[j][1]))
        return out

    def hints(self, picks, ctx):
        """Soft compatibility notes (rules.jsonl kind 'hint', e.g. ANSUR II proxy: very short + very broad shoulders is
        unusual). Not conflicts: never block a pick; show them to the model or log them."""
        its = self.items(picks)
        out = []
        for i in range(len(its)):
            for j in range(i + 1, len(its)):
                a, b = split_pick(its[i][1])[0], split_pick(its[j][1])[0]
                r = self.soft.get(a, {}).get(b)
                if r:
                    out.append({"kind": "hint", "rule": r["id"], "ids": [its[i][1], its[j][1]], "p": r.get("p"),
                                "msg": f'"{self.phrase(its[i][1])}" with "{self.phrase(its[j][1])}" is unusual: {r["why"]}.'})
        return out

    # ------------------------------------------------------------ numbers and standard terms
    def born_year(self, ctx, born=None):
        if born:
            return born
        era = {"born-pre1960": 1950, "born-1960-1989": 1975, "born-1990plus": 2000}
        e = next((era[t] for t in ctx.tags if t in era), None)
        return e or (self.stats.get("height", {}).get("ref_year", 2026) - ctx.age)

    def height_cm(self, ctx, born=None):
        """Mean adult height and z-band cut-offs (cm) for the person's sex x birth decade x population (NCD-RisC; SD proxy).
        None when no table covers the population (european, african, south-asian)."""
        h = self.stats.get("height", {})
        eth = ctx.eth if ctx.eth in ("kinh", "sea-asian", "east-asian") else ("kinh" if ctx.eth == "mixed" else None)
        if not h or not eth:
            return None
        dec = max(1900, min(2000, self.born_year(ctx, born) // 10 * 10))
        return h["by"].get(f"{eth}/{ctx.sex}/{dec}")

    def cm_range(self, v, ctx, born=None):
        """'~157-163 cm' for a height value with a z band, else ''."""
        z = v.get("z")
        hc = self.height_cm(ctx, born) if z else None
        if not hc:
            return ""
        lo, hi = hc["mean"] + z[0] * hc["sd"], hc["mean"] + z[1] * hc["sd"]
        if z[0] <= -9:
            return f"under {hi:.0f} cm"
        if z[1] >= 9:
            return f"over {lo:.0f} cm"
        return f"~{lo:.0f}-{hi:.0f} cm"

    def std(self, pick):
        """Standard terms for a value: [(term id, label)] from Interpol DVI, NCIC (EYE/HAIR/SKIN/SMT), TT 22/2014 fields,
        NIH Elements of Morphology. A marks pick with a place also gets its NCIC SMT code (e.g. 'SC L CHK')."""
        vid, loc = split_pick(pick)
        out = [(t, self.std_terms.get(t, "")) for t in self.values[vid].get("std", [])]
        code = self.std_marks.get(vid, {}).get(loc) if loc else None
        if code:
            out.append((f"ncic_smt:{code}", self.std_terms.get(f"ncic_smt:{code}", "")))
        return out

    def fill(self, picks, ctx):
        """Add the baseline for every slot not picked. A baseline that conflicts with a pick is dropped:
        that slot is 'covered' by the pick. Returns (full {slot: id|[...]} in slot order, {slot: covering id})."""
        full, covered = {}, {}
        pv = [(p, self.get(p)) for _, p in self.items(picks)]
        for s in self.slots:
            if picks.get(s):
                full[s] = picks[s]
                continue
            b = self.baseline(s, ctx)
            hit = next((p for p, v in pv if self.pair_conflicts(b, v, ctx)), None)
            if hit:
                covered[s] = hit
            else:
                full[s] = [b["id"]] if self.multi(s) else b["id"]
        return full, covered

    # ------------------------------------------------------------ menus
    def menu(self, slot, ctx, counts=None, cap=None, locked=None, k=None, seed="", facts=None):
        """Values of one slot for this person: sex/age and life facts (needs), reuse cap, no conflict with locked picks,
        capped to k lines (baseline first; unused first; values that fit the person's life first; keep a mix of
        uncommon/rare; rest rotated by seed). With `facts`, values whose specific cause a LIFE item shows (a kettle burn ->
        burn scar, running -> toned body) are always kept: the menu must offer what the character's own life explains."""
        counts = counts or {}
        generic = set(self.vocab.get("cite", {}).get("generic", []))
        life_causes = set().union(*facts.life_tags.values()) - generic if facts and facts.life_tags else set()
        explained = lambda v: bool(set(v["causes"]) & life_causes)
        locked = locked or {}
        k = k or self.vocab["budget"]["menu_k"]
        lv = [self.get(p) for s, p in self.items(locked) if s != slot]
        base = self.baseline(slot, ctx)
        pool = []
        for v in self.by_slot[slot]:
            if v is base or not self.fits(v, ctx):
                continue
            if cap is not None and counts.get(v["id"], 0) >= cap:
                continue
            if any(self.pair_conflicts(v, p, ctx) for p in lv):
                continue
            pool.append(v)
        rnd = random.Random(hashlib.sha256(f"{seed}|{slot}".encode()).hexdigest())
        rnd.shuffle(pool)
        pool.sort(key=lambda v: (counts.get(v["id"], 0), not explained(v), -min(1, self.fit_score(v, ctx))))
        if len(pool) > k - 1:
            keep = [v for v in pool if explained(v)][:max(1, (k - 1) // 2)]
            rest = [v for v in pool if v not in keep]
            for want, n in (("rare", 1), ("uncommon", 2)):
                got = [v for v in rest if self.cls(v, ctx) == want][:n]
                keep += got
                rest = [v for v in rest if v not in got]
            pool = keep + rest[:k - 1 - len(keep)]
            pool.sort(key=lambda v: v["id"])
        return [base] + pool

    def tag(self, v, ctx):
        if self.is_baseline(v, ctx):
            return "ordinary for you"
        return "near-plain" if self.sal(v, ctx) in ("plain", "mild") else "notable"

    def where(self, v):
        """Compact location list of a marks value: group names when a whole group is allowed."""
        locs = list(v.get("locs", []))
        out = []
        for g, members in self.marks.get("loc_groups", {}).items():
            if all(m in locs for m in members):
                out.append(g)
                locs = [x for x in locs if x not in members]
        return ", ".join(out + locs)

    def render(self, slot, vals, ctx, mode="luan_hoi", counts=None, facts=None):
        """Menu text with short per-slot keys (1, 2, ...). Returns (text, {key: id}).
        With facts (character mode), rare/notable values show where a valid reason is ("cite: LIFE 1 / IDENTITY Occupation")
        or "cite: none in your files"."""
        counts = counts or {}
        lines, keys = [f"## {slot}"], {}
        born = facts.born if facts is not None else None
        for n, v in enumerate(vals, 1):
            keys[str(n)] = v["id"]
            parts = [str(n), v["phrase"], self.cls(v, ctx)]
            cm = self.cm_range(v, ctx, born)
            if cm:
                parts[1] += f" ({cm})"
            if mode == "luan_hoi":
                if self.is_baseline(v, ctx):
                    parts.append("ordinary for this person")
                else:
                    parts.append(", ".join(v["causes"][:3]) or "-")
                    if v.get("fit"):
                        fit = sorted(v["fit"], key=lambda t: t not in ctx.tags)
                        parts.append("fits " + ",".join(fit[:3]))
                if counts.get(v["id"]):
                    parts.append(f"used by {counts[v['id']]} earlier")
            else:
                parts.append(self.tag(v, ctx))
                if not self.is_baseline(v, ctx) and v["causes"]:
                    parts.append(", ".join(v["causes"][:2]))
                if facts is not None and self.needs_cite(v, ctx):
                    parts.append("cite: " + (" / ".join(self.cite_options(slot, v, facts)) or "none in your files"))
            if v.get("locs") and not self.is_baseline(v, ctx):
                parts.append("where: " + self.where(v))
            lines.append("- " + " | ".join(parts))
        return "\n".join(lines), keys

    def plan_calls(self, slots, cost, budget, fixed):
        """Pack slots (in order) into as few calls as possible with fixed + sum(cost[slot]) <= budget,
        then balance them (smallest per-call limit that keeps the same number of calls)."""
        def pack(limit):
            calls, cur, used = [], [], 0
            for s in slots:
                c = cost[s]
                if cur and used + c > limit:
                    calls.append(cur)
                    cur, used = [], 0
                cur.append(s)
                used += c
            if cur:
                calls.append(cur)
            return calls
        room = budget - fixed
        best = pack(room)
        lo, hi = max([cost[s] for s in slots] or [0]), room
        while lo < hi:
            mid = (lo + hi) // 2
            if len(pack(mid)) <= len(best):
                hi = mid
            else:
                lo = mid + 1
        return pack(lo) if slots else []

    # ------------------------------------------------------------ registry and prompt
    def counts(self, registry, group, exclude=None):
        """Recompute reuse counts for a group from registry['chars'] (resolving old ids; marks counted by kind).
        Baselines do not count."""
        out = {}
        for cid, c in registry.get("chars", {}).items():
            if cid == exclude or c.get("group") != group:
                continue
            for _, p in self.items(c.get("picks") or {}):
                for j in self.resolve(p):
                    if not self.is_baseline(j, group):
                        out[j] = out.get(j, 0) + 1
        return out

    def prompt(self, full, ctx, groups=None):
        """Image-prompt text: non-baseline values + required slots, in slot order (A overall, B face, C hair,
        D-G body, H marks). groups: optional subset of group letters."""
        req = {s for s, m in self.vocab["slots"].items() if m.get("required_in_prompt")}
        out = []
        for s in self.slots:
            if s not in full or (groups and self.vocab["slots"][s]["group"] not in groups):
                continue
            for p in (full[s] if isinstance(full[s], list) else [full[s]]):
                if p and (s in req or not self.is_baseline(p, ctx)):
                    out.append(self.paint(p))
        return "; ".join(out)


def load(path=KB_JSON):
    if not Path(path).exists():
        raise SystemExit(f"{path} missing: run  python -I {HERE / 'kb.py'} build")
    return KB(json.loads(Path(path).read_text(encoding="utf-8")))
