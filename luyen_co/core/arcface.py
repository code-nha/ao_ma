"""Embedding khuôn mặt bằng ArcFace (w600k_r50.onnx của insightface buffalo_l).

Ảnh mặt được align về template 112×112 chuẩn của ArcFace bằng 5 landmark,
sau đó đưa qua ResNet50 → vector 512 chiều đã L2-normalize.
"""

from __future__ import annotations

import cv2
import numpy as np

from .onnx_models import ARCFACE_MODEL, create_session, session_info
from .utils import l2norm

# Template 5 điểm chuẩn (mắt trái, mắt phải, mũi, mép trái, mép phải)
TEMPLATE = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


class FaceEmbedder:
    def __init__(self, model_path=ARCFACE_MODEL, device: str = "auto"):
        self.sess = create_session(model_path, device)
        self.input_name = self.sess.get_inputs()[0].name
        self.backend = session_info(self.sess)

    @staticmethod
    def align(bgr: np.ndarray, kps: np.ndarray) -> np.ndarray | None:
        m, _ = cv2.estimateAffinePartial2D(kps.astype(np.float32), TEMPLATE, method=cv2.LMEDS)
        if m is None:
            return None
        return cv2.warpAffine(bgr, m, (112, 112), borderValue=0)

    def embed(self, aligned_bgr: np.ndarray) -> np.ndarray:
        blob = cv2.dnn.blobFromImage(aligned_bgr, 1.0 / 127.5, (112, 112),
                                     (127.5, 127.5, 127.5), swapRB=True)
        out = self.sess.run(None, {self.input_name: blob})[0]
        return l2norm(out)

    def embed_face(self, bgr: np.ndarray, kps: np.ndarray) -> np.ndarray | None:
        aligned = self.align(bgr, kps)
        if aligned is None:
            return None
        return self.embed(aligned)


def cosine(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return -1.0
    a, b = l2norm(a), l2norm(b)
    return float(np.dot(a, b))
