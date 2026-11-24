"""So sánh: bỏ cap per-bucket vs nâng per-bucket, sau đó lọc tư thế tham lam."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from core.pipeline import Config, Pipeline                      # noqa: E402
from core.select import (coverage_pick, dedupe, distinct_pose_pick,  # noqa: E402
                         drop_similar)

BASE = Path("sample/obj_1")
cfg = Config(refs=[BASE / "main.jpg"], out=Path("out_diag3"), fps=2.0, save="crop")
pipe = Pipeline(cfg)
pipe.run(BASE)
deduped = dedupe(pipe._filter_body_only(pipe.accepted), cfg.dup_sim, cfg.min_gap)
print(f"\ndedupe: {len(deduped)} frame")


def plan(per_bucket: int | None, my=25.0, mp=0.08):
    base = drop_similar(coverage_pick(deduped, per_bucket), 0.93) if per_bucket else deduped
    return distinct_pose_pick(base, my, mp)


plans = {
    "per_bucket 1 (hiện tại)": plan(1),
    "per_bucket 3": plan(3),
    "per_bucket 5": plan(5),
    "bỏ cap (chỉ lọc tư thế)": plan(None),
    "bỏ cap, pose 0.10": plan(None, mp=0.10),
}
fb_src = next(c.source for c in deduped if "Facebook" in c.source)

print(f"{'phương án':<26}{'tổng':>6}{'clip bảo vệ':>13}")
for name, kept in plans.items():
    print(f"{name:<26}{len(kept):>6}{sum(1 for c in kept if c.source == fb_src):>13}")

print(f"\n{'nguồn':<30}" + "".join(f"{k.split()[0][:10]:>12}" for k in plans))
per_source = defaultdict(int)
for c in deduped:
    per_source[Path(c.source).name[:28]] += 1
for src in sorted(per_source, key=lambda s: -per_source[s]):
    row = "".join(f"{sum(1 for c in kept if Path(c.source).name[:28] == src):>12}"
                  for kept in plans.values())
    print(f"{src:<30}{row}")
