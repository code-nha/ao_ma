# LOOK knowledge base: guide for agents (schema 3)

Use `kbq.py`; do not read `catalog/` or `kb.json` directly at runtime. All model-facing text is English. Vietnamese glosses
live only in `vi.jsonl` (`kb.vi(id)`), never send them to the model.

```python
import sys; sys.path.insert(0, "<repo>/characters/kb"); import kbq
kb = kbq.load()                                        # kb.json; run `python -I kb.py build` if missing
facts = kb.facts(identity, life, style)                # what code can read from the character files
ctx = facts.ctx                                        # kbq.Ctx(sex, age, tags); ctx.group == "male-elderly", ctx.eth == "kinh"
```

42 slots in prompt order: A overall (height frame fat muscle fat_where), B face (head face_shape forehead brows eyes under_eye nose
cheeks mouth teeth jaw_chin ears neck skin_tone skin_texture wrinkles facial_hair asymmetry resting_face), C natural hair
(hair_color hair_texture hair_density hairline), D-G body, H marks. Required in every prompt: height, frame, fat, face_shape,
skin_tone, hair_color. `resting_face`, `posture`, `gait` are `soul` slots (may follow SOUL); everything else follows birth (B
structure, height, frame) or how the person lives (fat, muscle, skin, teeth, hands, wrinkles, marks).

| call | returns |
|---|---|
| `kb.facts(identity, life, style)` | `Facts`: `tags` (facet tags), `src` (tag -> "IDENTITY Occupation" / "STYLE eating and drinking"), `fields`, `life` {n: text}, `field_tags` / `life_tags` (cause tags per IDENTITY field / LIFE item), `line()` for prompts |
| `kb.baseline(slot, ctx)` | the value ordinary for this person; lookup order `kb.baseline_keys(ctx)`: `<eth>/<group>`, then `<life or place tag>/<group>` (`vocab.baseline_facets`, e.g. `sea/male-elderly` -> sun-darkened skin), then `<group>` |
| `kb.fits(v, ctx)` | sex, age and `needs` (life facts) all allow the value |
| `kb.menu(slot, ctx, counts, cap, locked, k, seed)` | baseline first, then values that fit, under the reuse cap, not conflicting with `locked`; values whose `fit` tags match the person come first; at most `k` (14) |
| `kb.render(slot, values, ctx, mode)` | `(text, {key: id})`; `"luan_hoi"` shows causes + fit tags, `"character"` shows notable / near-plain + causes; marks show `where:`; with `facts=` rare/notable lines end in `cite: LIFE 1 / IDENTITY Occupation` (valid targets) or `cite: none in your files` |
| `kb.cls(v, ctx)`, `kb.sal(v, ctx, loc)` | frequency (common/uncommon/rare) and salience (plain/mild/marked; hidden mark places count as mild) |
| `kb.notable(v, ctx, loc)` / `kb.near_plain(...)` | marked and not baseline (signature material) / plain or mild and not baseline |
| `kb.needs_cite(v, ctx, loc)` | rare or notable: the character must cite a reason |
| `kb.cite_problem(slot, pick, cite, facts, ctx, why="")` | `None` if fine, else a FIX message. Cite = `"LIFE <n>"`, `"IDENTITY <field>"` or (soul slots) `"SOUL"`; the item must exist and carry one of the value's causes (no generic free pass: IDENTITY Age carries ageing/hormones at 45+ or youth under 30, Nationality/Hometown genetics/climate, SOUL temperament/stress/low-mood). Pass the model's reason text as `why`: a cause it claims (`vocab.cite.claim_causes`: injury, illness, alcohol...) must be shown by the cited item or the facts (`vocab.cite.facet_causes`) |
| `kb.cite_options(slot, v, facts)` | up to 2 cites that `cite_problem` accepts for this value (`[]` = nothing in the files explains it) |
| `kb.life_explained(slot, pick, cite, facts)` | a cited LIFE item shows a specific cause: such a rare value does not count toward the one-rare cap |
| `kb.check(picks, ctx)` | conflicts among `{slot: id or [id@loc]}`: hidden axes (`dims`: fat, muscle, frame, spine, lines, scalp, grey, teeth), the same feature in two slots (`regions`), `rules.jsonl`; each has `msg` |
| `kb.fill(picks, ctx)` | `(full, covered)`: baselines for unpicked slots; a baseline that conflicts with a pick is dropped (`covered[slot] = pick`) |
| `kb.prompt(full, ctx, groups)` | image-prompt text: non-baseline values + required slots in slot order; `groups="B"` for one section |
| `kb.plan_calls(slots, cost, budget, fixed)` | slots grouped into calls under `budget` tokens (`vocab.budget.call_tokens`, 3500) |
| `kb.counts(registry, group, exclude)` | reuse counts from `registry["chars"]`, old ids resolved, marks counted by kind, baselines not counted |
| `kb.resolve(id)`, `kb.phrase(pick)`, `kbq.split_pick(pick)` | tombstones; phrase with the mark place filled in; `"marks.mole@cheek-l" -> ("marks.mole", "cheek-l")` |
| `kbq.est_tokens(text)` | rough input-token estimate (chars / 3.5; Gemma counts ~10% less) |
| `kb.height_cm(ctx, born)` / `kb.cm_range(v, ctx, born)` | NCD-RisC mean and SD (cm) for this sex x birth year x population (kinh, sea-asian, east-asian; mixed uses kinh) / the cm range of a height value's `z` band; `render(..., facts=)` appends `(~lo-hi cm)` |
| `kb.hints(picks, ctx)` | soft hints (`rules.jsonl` `kind: hint`, basis proxy, e.g. very short man with very broad shoulders); advice only, never a conflict |
| `kb.std(pick)` | standard terms for a value (DVI AM 2023, NCIC SMT/EYE/HAIR/SKIN, TT 22/2014, NIH EoM labels); `kb.std_marks` has NCIC SMT codes per marks value x place |

Life facets (closed, `vocab.facets`; every tag unique): `means` destitute..rich, `life` outdoor-manual sea farm street office display
domestic military idle, `diet` underfed plain-diet well-fed overfed, `alcohol` sober drinks heavy-drinker, `smoke`, `place`, `era`
(birth cohort), `eth` kinh (default) sea-asian east-asian south-asian european african mixed. Code reads them with
`vocab.fact_keywords` from IDENTITY fields (`fact_fields` says which) and STYLE lines; LIFE items only give cause tags
(`cause_keywords`; injury/illness in an item about someone else's death are ignored). A value's `needs` is a list of
conditions (any one must hold; inside one, every facet the person has must match; unknown facets pass; `mixed` passes eth).

Rules of use:
- Keep each model call <= ~3.5k input tokens: render menus, cost them with `est_tokens`, split with `plan_calls`.
- Pick in slot order and pass earlier picks as `locked`; run `check` and `cite_problem` after every pick; at most one rare
  value not explained by LIFE; use an LLM check only as a last net and log what it finds to `experiments/logs/rule_candidates.jsonl`.
- Marks: up to `vocab.marks.max` (3) picks `"<id>@<loc>"`, loc from the value's `locs`.
- Store picks by id plus a phrase snapshot and `kb.version`; never store phrases alone.

Editing (distiller agents): one value per line in `catalog/<slot>.jsonl`; ids are never renamed, deleted or reused (tombstone with
`into`); causes, dims, regions, bands, facets come only from `vocab.json`; phrases describe only what is visible (no "from", "after",
"years of", no beauty words); add `needs` when a life fact makes the value impossible (e.g. beer belly needs well-fed/overfed or a
heavy drinker), `fit` when it makes it likely; values typical of another population get `needs: [{"eth": [...]}]`.
Default frequencies are for Vietnamese Kinh / Southeast Asians. `basis: stat` rows (height, fat, waist, head, face, nose,
mouth, jaw) come from `stats.json` via `src/distill_*.py` + `src/v4_distill.py` and cite a table; `basis: proxy` data
(MAAD-Face, ANSUR II) may only add exclude rules or hints, never Vietnamese frequencies. Height values carry `z` bands
(relative to the same sex, birth cohort and population), not cm. Then `python -I kb.py build` (must print `check: OK`; golden
tests in `tests/golden.jsonl` cover conflicts, menus under life facts, cites and fact parsing).
