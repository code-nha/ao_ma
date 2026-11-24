"""Dựng sheet riêng cho một nguồn trong output, kèm nhãn thời điểm/nhóm góc."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "output/obj_1")
NEEDLE = sys.argv[2] if len(sys.argv) > 2 else "Facebook"

rows = [json.loads(l) for l in (OUT / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
rows = [r for r in rows if NEEDLE in r["source"]]
print(f"{len(rows)} ảnh khớp '{NEEDLE}'")
cols, cell, pad = 6, 190, 30
n_rows = math.ceil(len(rows) / cols)
sheet = np.full((n_rows * (cell + pad), cols * cell, 3), 255, np.uint8)
for i, r in enumerate(rows):
    img = cv2.imdecode(np.fromfile(str(OUT / r["path"]), np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    s = min(cell / w, cell / h)
    thumb = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    row, col = divmod(i, cols)
    y0, x0 = row * (cell + pad), col * cell
    sheet[y0:y0 + thumb.shape[0], x0:x0 + thumb.shape[1]] = thumb
    cv2.putText(sheet, f"{r['t']:.1f}s {r['bucket']}", (x0 + 2, y0 + cell + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
    cv2.putText(sheet, f"face={r['face_sim']} h={r['person_h']}", (x0 + 2, y0 + cell + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.37, (110, 60, 20), 1, cv2.LINE_AA)
dest = OUT / f"sheet_{NEEDLE[:12]}.jpg"
cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tofile(str(dest))
print("sheet:", dest)
