"""Soi riêng clip 'bảo vệ quay bằng điện thoại': phân bố pose/yaw và số cụm theo ngưỡng."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from core.pipeline import Config, Pipeline          # noqa: E402
from core.select import dedupe, distinct_pose_pick, yaw_bucket  # noqa: E402

BASE = Path("sample/obj_1")
VIDEO = next(BASE.glob("*Facebook Video*"))
cfg = Config(refs=[BASE / "main.jpg"], out=Path("out_diag3"), fps=2.0, save="crop")
pipe = Pipeline(cfg)
pipe.process_video(VIDEO)
cands = dedupe(pipe._filter_body_only(pipe.accepted), cfg.dup_sim, cfg.min_gap)
cands.sort(key=lambda c: c.t)
print(f"\n{VIDEO.name}\nnạp {len(cands)} frame sau dedupe")
print("nhóm góc:", dict(Counter(yaw_bucket(c) for c in cands)))
print(f"yaw: {min(c.yaw for c in cands):.0f}…{max(c.yaw for c in cands):.0f}°  "
      f"pitch: {min(c.pitch for c in cands):.0f}…{max(c.pitch for c in cands):.0f}°")

mat = np.stack([c.pose_vec for c in cands])
sub = mat[:: max(1, len(mat) // 40)]
pd = np.abs(sub[:, None, :] - sub[None, :, :]).mean(axis=2)
iu = pd[np.triu_indices(len(sub), k=1)]
print(f"pose_d giữa các frame: min {iu.min():.3f} · p10 {np.percentile(iu,10):.3f} · "
      f"trung vị {np.median(iu):.3f} · p90 {np.percentile(iu,90):.3f}")

def greedy(items, my, mp):
    kept = []
    for c in sorted(items, key=lambda x: (-x.face_sim if x.has_face else 1.0, -x.person_h, -x.blur)):
        if any(abs(c.pose_vec - k.pose_vec).mean() < mp and
               (yaw_bucket(c) == yaw_bucket(k) or abs(c.yaw - k.yaw) < my)
               for k in kept):
            continue
        kept.append(c)
    return kept


print("\ntham lam (không nối chuỗi):")
for mp in (0.05, 0.08, 0.10, 0.12):
    print(f"  min_yaw 25 · min_pose {mp:.2f} → {len(greedy(cands, 25.0, mp)):>2} ảnh")

for mp in (0.03, 0.04, 0.05, 0.06, 0.08):
    for my in (15.0, 25.0):
        kept = distinct_pose_pick(cands, my, mp)
        print(f"  min_yaw {my:>4.0f} · min_pose {mp:.2f} → {len(kept):>2} ảnh")
