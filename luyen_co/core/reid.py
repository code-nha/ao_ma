"""Embedding toàn thân bằng CLIP ViT-B/32 (vision encoder, ONNX).

Dùng để (a) so khớp danh tính khi mặt bị che/mờ và (b) đo độ đa dạng ngoại
hình giữa các frame. Người được crop từ bbox YOLO rồi letterbox về 224×224
(giữ nguyên tỉ lệ cơ thể, không kéo méo).
"""

from __future__ import annotations

import numpy as np

from .onnx_models import CLIP_MODEL, create_session, session_info
from .utils import l2norm, letterbox

CLIP_SIZE = 224
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


class BodyEmbedder:
    def __init__(self, model_path=CLIP_MODEL, device: str = "auto"):
        self.sess = create_session(model_path, device)
        self.input_name = self.sess.get_inputs()[0].name
        self.backend = session_info(self.sess)

    def embed(self, person_bgr: np.ndarray) -> np.ndarray | None:
        if person_bgr.size == 0:
            return None
        img, _, _, _ = letterbox(person_bgr, CLIP_SIZE, pad_color=(127, 127, 127))
        x = img[:, :, ::-1].astype(np.float32) / 255.0
        x = (x - CLIP_MEAN) / CLIP_STD
        blob = x.transpose(2, 0, 1)[None]
        out = self.sess.run(None, {self.input_name: blob})[0]
        return l2norm(out)
