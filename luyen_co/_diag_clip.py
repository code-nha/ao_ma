"""Đo CLIP similarity giữa các ảnh của clip bảo vệ (để tách ảnh trùng khung hình)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.reid import BodyEmbedder      # noqa: E402
from core.utils import read_image       # noqa: E402

OUT = Path("output/obj_1")
rows = [json.loads(l) for l in (OUT / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
rows = [r for r in rows if "Facebook" in r["source"]]

emb = BodyEmbedder()
vecs, info = [], []
for r in rows:
    img = read_image(OUT / r["path"])
    v = emb.embed(img) if img is not None else None
    vecs.append(v)
    info.append((r["t"], r["person_h"], r["bucket"]))
mat = np.stack(vecs)
sim = mat @ mat.T
print(f"{'i':>2} {'t':>6} {'h':>5} {'bucket':<12}")
for i, (t, h, b) in enumerate(info):
    print(f"{i:>2} {t:>6.1f} {h:>5} {b:<12}")
print("\ncác cặp CLIP ≥ 0.85:")
for i in range(len(info)):
    for j in range(i + 1, len(info)):
        if sim[i, j] >= 0.85:
            print(f"  {sim[i, j]:.3f}  {info[i][0]:>5.1f}s (h={info[i][1]:>4}) ~ "
                  f"{info[j][0]:>5.1f}s (h={info[j][1]:>4})")
