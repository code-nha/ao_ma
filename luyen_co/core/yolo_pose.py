"""Phát hiện người + 17 keypoint bằng YOLOv8-pose (ONNX).

Model chỉ có 1 class (person) nên không cần lọc class: mỗi detection là 1 người.
Output: (1, 56, 8400) = 4 bbox + 1 score + 17×(x, y, conf).

`tiles > 1` chia frame thành lưới (có chồng lấn) rồi chạy model trên từng ô —
đổi lại chậm hơn gấp `tiles²` lần nhưng bắt được người rất nhỏ trong khung CCTV
góc rộng/4K, thứ mà khi thu cả frame về 640 px sẽ bị mất.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .onnx_models import POSE_MODEL, create_session, session_info
from .utils import letterbox, nms, nms_containment


@dataclass
class Person:
    box: np.ndarray          # xyxy trong ảnh gốc
    score: float
    kpts: np.ndarray         # (17, 3) x, y, conf trong ảnh gốc


class PersonDetector:
    def __init__(self, model_path=POSE_MODEL, device: str = "auto", conf: float = 0.35,
                 iou: float = 0.45, imgsz: int = 640, tiles: int = 1):
        self.sess = create_session(model_path, device)
        self.input_name = self.sess.get_inputs()[0].name
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.tiles = max(1, int(tiles))
        self.backend = session_info(self.sess)

    def _infer(self, img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Chạy model trên 1 ảnh, trả box/kpts theo toạ độ ảnh đó."""
        h, w = img.shape[:2]
        padded, ratio, left, top = letterbox(img, self.imgsz)
        blob = padded[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self.sess.run(None, {self.input_name: blob})[0]
        out = out[0].T                                     # (8400, 56)
        scores = out[:, 4]
        keep = scores > self.conf
        if not keep.any():
            return np.empty((0, 4), np.float32), np.empty((0,), np.float32), np.empty((0, 17, 3), np.float32)
        out, scores = out[keep], scores[keep]

        cx, cy, bw, bh = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
        boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
        keep_idx = nms(boxes, scores, self.iou)
        boxes, scores, out = boxes[keep_idx], scores[keep_idx], out[keep_idx]

        kpts = out[:, 5:].reshape(-1, 17, 3).copy()
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - left) / ratio
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - top) / ratio
        kpts[:, :, 0] = (kpts[:, :, 0] - left) / ratio
        kpts[:, :, 1] = (kpts[:, :, 1] - top) / ratio
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w - 1)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h - 1)
        kpts[:, :, 0] = kpts[:, :, 0].clip(0, w - 1)
        kpts[:, :, 1] = kpts[:, :, 1].clip(0, h - 1)
        return boxes, scores, kpts

    def _tile_slices(self, h: int, w: int) -> list[tuple[int, int, int, int]]:
        """Cửa sổ (y1, y2, x1, x2) có chồng lấn 20% giữa các ô."""
        n = self.tiles
        if n == 1:
            return [(0, h, 0, w)]
        th, tw = int(np.ceil(h / n)), int(np.ceil(w / n))
        oh, ow = int(th * 0.2), int(tw * 0.2)
        out = []
        for i in range(n):
            for j in range(n):
                y1 = max(0, i * th - oh)
                x1 = max(0, j * tw - ow)
                out.append((y1, min(h, (i + 1) * th + oh), x1, min(w, (j + 1) * tw + ow)))
        return out

    def detect(self, bgr: np.ndarray) -> list[Person]:
        h, w = bgr.shape[:2]
        boxes_all, scores_all, kpts_all = [], [], []
        for y1, y2, x1, x2 in self._tile_slices(h, w):
            tile = bgr[y1:y2, x1:x2]
            if tile.size == 0:
                continue
            boxes, scores, kpts = self._infer(tile)
            if len(boxes) == 0:
                continue
            boxes = boxes + np.array([x1, y1, x1, y1], np.float32)
            kpts = kpts + np.array([x1, y1, 0], np.float32)
            boxes_all.append(boxes)
            scores_all.append(scores)
            kpts_all.append(kpts)

        if not boxes_all:
            return []
        boxes = np.concatenate(boxes_all)
        scores = np.concatenate(scores_all)
        kpts = np.concatenate(kpts_all)

        # gộp các ô: NMS + bỏ box nằm gần trọn trong box khác (đầu/thân cùng người)
        if self.tiles > 1:
            keep = nms_containment(boxes, scores, 0.5, 0.8)
            boxes, scores, kpts = boxes[keep], scores[keep], kpts[keep]

        return [Person(box=b.astype(np.float32), score=float(s), kpts=k.astype(np.float32))
                for b, s, k in zip(boxes, scores, kpts)]
