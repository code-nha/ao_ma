"""Kiểu dữ liệu dùng chung giữa các bước của pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Candidate:
    """Một person crop ứng viên (đã qua cổng chất lượng, chưa chắc đúng người)."""

    source: str
    kind: str                      # "video" | "image"
    t: float                       # giây trong video (ảnh: 0)
    frame_idx: int
    track_id: int
    box: np.ndarray                # xyxy trong frame gốc
    person_score: float
    face_sim: float                # cosine với mặt tham chiếu, -1 nếu không thấy mặt
    body_sim: float
    yaw: float
    pitch: float
    blur: float
    person_h: int                  # chiều cao bbox (px)
    jpeg: bytes                    # crop người đã encode JPEG
    full_jpeg: bytes | None = None # nguyên frame (giữ bối cảnh) nếu --save full/both
    src_w: int = 0                 # kích thước frame gốc
    src_h: int = 0
    scene: int = 0                 # chỉ số cảnh (cắt cảnh) trong video
    color_sim: float = -1.0        # tương quan histogram màu áo/quần với tham chiếu
    staged: "Path | None" = None   # file tạm trên đĩa (giải phóng RAM cho video dài)
    kpts: np.ndarray | None = None
    face_box: np.ndarray | None = None
    clip_vec: np.ndarray | None = None
    pose_vec: np.ndarray | None = field(default=None)

    @property
    def has_face(self) -> bool:
        return self.face_sim >= 0.0
