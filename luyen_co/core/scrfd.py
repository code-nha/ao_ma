"""Phát hiện khuôn mặt bằng SCRFD (det_10g.onnx của insightface buffalo_l).

SCRFD trả 3 mức stride (8, 16, 32), mỗi mức 2 anchor/ô: score, khoảng cách
bbox (4 số) và 5 điểm landmark. Ở đây input cố định 640×640 (model khai báo
shape động nhưng luôn chạy 640 cho ổn định với DirectML).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .onnx_models import SCRFD_MODEL, create_session, session_info
from .utils import nms


@dataclass
class Face:
    box: np.ndarray          # xyxy
    kps: np.ndarray          # (5, 2) mắt trái, mắt phải, mũi, mép trái, mép phải
    score: float


def _distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    out = []
    for i in range(0, distance.shape[1], 2):
        out.append(points[:, 0] + distance[:, i])
        out.append(points[:, 1] + distance[:, i + 1])
    return np.stack(out, axis=-1).reshape(-1, 5, 2)


class FaceDetector:
    def __init__(self, model_path=SCRFD_MODEL, device: str = "auto", det_size: int = 640,
                 conf: float = 0.5, iou: float = 0.4):
        self.sess = create_session(model_path, device)
        self.input_name = self.sess.get_inputs()[0].name
        self.det_size = det_size
        self.conf = conf
        self.iou = iou
        self.backend = session_info(self.sess)

    def detect(self, bgr: np.ndarray) -> list[Face]:
        h, w = bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(bgr, 1.0 / 128, (self.det_size, self.det_size),
                                     (127.5, 127.5, 127.5), swapRB=True)
        outs = self.sess.run(None, {self.input_name: blob})

        # Gom output theo số anchor, rồi suy stride: n = 2 × (size/stride)²
        groups: dict[int, dict[int, np.ndarray]] = {}
        for arr in outs:
            arr = np.asarray(arr)
            groups.setdefault(arr.shape[0], {})[arr.shape[1]] = arr.reshape(-1, arr.shape[1])

        boxes_all, scores_all, kps_all = [], [], []
        for n, parts in groups.items():
            if not {1, 4, 10}.issubset(parts):
                continue
            stride = self.det_size / (n / 2) ** 0.5
            if abs(stride - round(stride)) > 1e-3:
                continue
            stride = int(round(stride))
            fh = fw = self.det_size // stride
            ys, xs = np.mgrid[:fh, :fw]
            centers = np.stack([xs.ravel() * stride, ys.ravel() * stride], axis=1).astype(np.float32)
            centers = np.repeat(centers, 2, axis=0)          # 2 anchor mỗi ô
            scores = parts[1].reshape(-1)
            mask = scores >= self.conf
            if not mask.any():
                continue
            centers_m = centers[mask]
            boxes_all.append(_distance2bbox(centers_m, parts[4][mask] * stride))
            kps_all.append(_distance2kps(centers_m, parts[10][mask] * stride))
            scores_all.append(scores[mask])

        if not boxes_all:
            return []
        boxes = np.concatenate(boxes_all)
        scores = np.concatenate(scores_all)
        kps = np.concatenate(kps_all)

        keep = nms(boxes, scores, self.iou)
        boxes, scores, kps = boxes[keep], scores[keep], kps[keep]

        sx, sy = w / self.det_size, h / self.det_size
        boxes[:, [0, 2]] *= sx
        boxes[:, [1, 3]] *= sy
        kps[:, :, 0] *= sx
        kps[:, :, 1] *= sy
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w - 1)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h - 1)

        return [Face(box=b.astype(np.float32), kps=k.astype(np.float32), score=float(s))
                for b, k, s in zip(boxes, kps, scores)]
