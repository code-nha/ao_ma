"""So sánh các cách chọn ảnh: coverage hiện tại vs gom cụm trên toàn bộ frame nhận.

Chạy: .venv\\Scripts\\python.exe _diag_sel.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from core.pipeline import Config, Pipeline          # noqa: E402
from core.select import (coverage_pick, dedupe, distinct_pose_pick,  # noqa: E402
                         drop_similar, yaw_bucket)

BASE = Path("sample/obj_1")
cfg = Config(refs=[BASE / "main.jpg"], out=Path("out_diag3"), fps=2.0, save="crop")
pipe = Pipeline(cfg)
pipe.run(BASE)

accepted = pipe._filter_body_only(pipe.accepted)
deduped = dedupe(accepted, cfg.dup_sim, cfg.min_gap)
print(f"nhận {len(accepted)} → dedupe {len(deduped)}\n")


def per_source(items):
    d = defaultdict(list)
    for c in items:
        d[Path(c.source).name].append(c)
    return d


cur = distinct_pose_pick(drop_similar(coverage_pick(deduped, cfg.per_bucket), 0.93),
                         cfg.min_yaw, cfg.min_pose)
new = distinct_pose_pick(deduped, cfg.min_yaw, cfg.min_pose)
print(f"{'nguồn':<34} {'nhận':>5} {'dedupe':>7} {'hiện tại':>9} {'gom cụm':>8}")
for name, items in sorted(per_source(deduped).items(), key=lambda kv: -len(kv[1])):
    cur_n = sum(1 for c in cur if Path(c.source).name == name)
    new_n = sum(1 for c in new if Path(c.source).name == name)
    print(f"{name[:34]:<34} {len(items):>5} {len(items):>7} {cur_n:>9} {new_n:>8}")
print(f"{'TỔNG':<34} {len(accepted):>5} {len(deduped):>7} {len(cur):>9} {len(new):>8}")

print("\nnhóm góc của phương án gom cụm:")
print("  " + " · ".join(f"{k} {v}" for k, v in Counter(yaw_bucket(c) for c in new).most_common()))

for pb, my, mp in ((3, 25, 0.08), (5, 25, 0.08), (3, 25, 0.12)):
    alt = distinct_pose_pick(drop_similar(coverage_pick(deduped, pb), 0.93), my, mp)
    print(f"\n--per-bucket {pb} (min_yaw {my}, min_pose {mp}): {len(alt)} ảnh "
          f"· Facebook: {sum(1 for c in alt if 'Facebook' in c.source)}")
