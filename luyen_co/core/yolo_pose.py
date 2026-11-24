"""Phát hiện người + 17 keypoint bằng YOLOv8-pose (ONNX).

Model chỉ có 1 class (person) nên không cần lọc class: mỗi detection là 1 người.
Output: (1, 56, 8400) = 4 bbox + 1 score + 17×(x, y, conf).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .onnx_models import POSE_MODEL, create_session, session_info
from .utils import letterbox, nms


@dataclass
class Person:
    box: np.ndarray          # xyxy trong ảnh gốc
    score: float
    kpts: np.ndarray         # (17, 3) x, y, conf trong ảnh gốc


class PersonDetector:
    def __init__(self, model_path=POSE_MODEL, device: str = "auto", conf: float = 0.35,
                 iou: float = 0.45, imgsz: int = 640):
        self.sess = create_session(model_path, device)
        self.input_name = self.sess.get_inputs()[0].name
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.backend = session_info(self.sess)

    def detect(self, bgr: np.ndarray) -> list[Person]:
        h, w = bgr.shape[:2]
        img, ratio, left, top = letterbox(bgr, self.imgsz)
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self.sess.run(None, {self.input_name: blob})[0]
        out = out[0].T                                     # (8400, 56)
        scores = out[:, 4]
        keep = scores > self.conf
        if not keep.any():
            return []
        out, scores = out[keep], scores[keep]

        cx, cy, bw, bh = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
        boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
        keep_idx = nms(boxes, scores, self.iou)
        boxes, scores, out = boxes[keep_idx], scores[keep_idx], out[keep_idx]

        kpts = out[:, 5:].reshape(-1, 17, 3).copy()
        # về toạ độ ảnh gốc
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - left) / ratio
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - top) / ratio
        kpts[:, :, 0] = (kpts[:, :, 0] - left) / ratio
        kpts[:, :, 1] = (kpts[:, :, 1] - top) / ratio
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w - 1)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h - 1)
        kpts[:, :, 0] = kpts[:, :, 0].clip(0, w - 1)
        kpts[:, :, 1] = kpts[:, :, 1].clip(0, h - 1)

        return [Person(box=b.astype(np.float32), score=float(s), kpts=k.astype(np.float32))
                for b, s, k in zip(boxes, scores, kpts)]
