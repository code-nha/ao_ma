"""Lọc dataset LoRA từ thư mục crop đã có: kích thước, độ nét, ánh sáng, khung hình,
đa dạng, và trùng lặp. Chép ảnh đạt sang thư mục đích (không sửa ảnh gốc).

Chạy trong repo luyen_co (dùng lại core.scrfd / core.yolo_pose):

    .venv\\Scripts\\python.exe -X utf8 filter_dataset.py ^
        --src output\\obj_1\\crops ^
        --dst output\\obj_1\\flter

Ngưỡng lấy từ chính dữ liệu này: chạy `--analyze-only` trước để xem phân bố
các số đo (CSV), rồi soi `sheet_*.jpg` mới chốt.

Tiêu chí (theo yêu cầu lọc ảnh):
  1. Cạnh ngắn >= --min-side (mặc định 768, mục tiêu 1024); không phóng to.
  2. Nét: Laplacian vùng mặt 112x112 (đo đã dùng trong pipeline) + Laplacian cả ảnh.
  3. Đủ sáng: độ sáng trung bình vùng mặt trong khoảng cho phép, không bệt.
  4. Mặt phải thấy rõ: SCRFD phải bắt được mặt, mặt không bị cắt ở mép khung.
  5. Không có người khác: mặt thứ hai đủ lớn hoặc người thứ hai đủ lớn -> loại.
  6. Khung hình: phân loại theo tỉ lệ chiều cao mặt / chiều cao ảnh, chọn theo tỉ lệ
     mục tiêu 40% cận mặt / 35% ngang vai-ngực / 25% ngang eo-toàn thân.
  7. Đa dạng: trần theo nguồn (buổi chụp), trần theo nhóm góc, trần theo cửa sổ thời gian.
  8. Trùng / gần trùng: MD5 + dHash (kể cả bản lật gương) + cùng nguồn & gần thời điểm.

Script không tự quyết "ảnh có watermark / filter mạnh / khẩu trang" — mấy thứ đó
không đo được đáng tin; script xuất contact sheet để soi mắt, và đọc `--skip-list`
để loại tay những file đã soi thấy lỗi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# --------------------------------------------------------------------- import core


def _import_core():
    """Nạp core.* của repo luyen_co (script có thể nằm ngoài repo khi thử nghiệm)."""
    root = Path(__file__).resolve().parent
    candidates = [root, Path(os.environ.get("LUYEN_CO_ROOT", "")) if os.environ.get("LUYEN_CO_ROOT") else None]
    for cand in candidates:
        if cand and (cand / "core" / "scrfd.py").exists():
            sys.path.insert(0, str(cand))
            break
    from core.arcface import FaceEmbedder, cosine  # noqa: E402
    from core.reid import BodyEmbedder            # noqa: E402
    from core.scrfd import FaceDetector          # noqa: E402
    from core.utils import (                     # noqa: E402
        crop_xyxy, laplacian_var, read_image, write_image,
    )
    from core.yolo_pose import PersonDetector     # noqa: E402

    return (FaceDetector, PersonDetector, crop_xyxy, laplacian_var, read_image,
            FaceEmbedder, cosine, BodyEmbedder, write_image)


(FaceDetector, PersonDetector, crop_xyxy, laplacian_var, read_image,
 FaceEmbedder, cosine, BodyEmbedder, write_image) = _import_core()

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Bảng lượng tử chuẩn (IJG, kênh sáng) để ước lượng chất lượng JPEG từ header.
# libjpeg nhân bảng này với hệ số s (s = 5000/q nếu q<50, ngược lại s = 200-2q);
# so bảng lưu trong file với 100 bảng ứng viên, lấy bảng khớp nhất.
STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
], dtype=np.float64)


def _quant_tables() -> dict[int, np.ndarray]:
    out = {}
    for q in range(1, 101):
        s = 5000 // q if q < 50 else 200 - 2 * q
        out[q] = np.clip((STD_LUMA * s + 50) // 100, 1, 255)
    return out


QTABLES = _quant_tables()


def jpeg_quality(path: Path) -> tuple[float | None, int | None, float | None]:
    """Ước lượng chất lượng JPEG từ **bảng nén trong header** (không giải mã pixel).

    Trả (quality, quality_khop_bang_chuan, sai_so_khop). Ảnh không phải JPEG
    hoặc không có bảng lượng tử -> (None, None, None).

    `quality` lấy theo **tỉ lệ trung vị** giữa bảng thật và bảng chuẩn, nên vẫn
    ước lượng được khi file dùng bảng hơi khác chuẩn (Instagram/Facebook hay
    re-encode bằng bảng riêng). Khi bảng khớp chuẩn, hai cách cho cùng kết quả.
    """
    try:
        with Image.open(path) as im:          # Pillow chỉ đọc header + bảng lượng tử
            if (im.format or "").upper() not in ("JPEG", "MPO"):
                return None, None, None
            qt = getattr(im, "quantization", None)
    except Exception:
        return None, None, None
    if not qt:
        return None, None, None
    raw = np.asarray(list(qt.get(0) or next(iter(qt.values()))), dtype=np.float64)
    if raw.size != 64:
        return None, None, None
    errors = {q: float(np.abs(raw - t).sum()) for q, t in QTABLES.items()}
    best_q = min(errors, key=errors.get)
    s = 100.0 * float(np.median(raw / STD_LUMA))
    q = 5000.0 / s if s > 100 else (200.0 - s) / 2.0
    return round(max(1.0, min(100.0, q)), 1), best_q, round(errors[best_q], 1)

# Cỡ cảnh: tỉ lệ chiều cao mặt / chiều cao ảnh. Ngưỡng chọn theo phân bố thật của
# obj_1 (cận mặt hiếm vì nguồn 720p), xem `--analyze-only`.
CLASS_CLOSE, CLASS_CHEST, CLASS_WAIST, CLASS_FULL = "close", "chest", "waist", "full"
CLASS_ORDER = [CLASS_CLOSE, CLASS_CHEST, CLASS_WAIST, CLASS_FULL]
CLASS_LABEL = {
    CLASS_CLOSE: "can mat",
    CLASS_CHEST: "ngang vai/nguc",
    CLASS_WAIST: "ngang eo",
    CLASS_FULL: "toan than",
}
# Trung điểm các dải trong spec: cận 20–35%, vai/ngực 30–45%, eo 15–30%,
# toàn thân 10–20%. Tổng 102.5% nên chia lại cho khớp 100%.
_QUOTA = {CLASS_CLOSE: 0.275, CLASS_CHEST: 0.375, CLASS_WAIST: 0.225, CLASS_FULL: 0.150}
_qsum = sum(_QUOTA.values())
CLASS_QUOTA = {c: v / _qsum for c, v in _QUOTA.items()}


# ----------------------------------------------------------------------- dữ liệu


@dataclass
class Row:
    path: Path
    name: str
    w: int = 0
    h: int = 0
    short: int = 0
    md5: str = ""
    dhash: int = 0
    dhash_flip: int = 0
    n_faces: int = 0
    n_persons: int = 0
    face_px: int = 0
    face_frac: float = 0.0        # face_h / H
    face_border: float = 1.0      # khoảng cách mặt tới mép gần nhất, tỉ lệ cạnh ngắn
    yaw: float = 0.0
    pitch: float = 0.0
    bucket: str = "khong ro mat"
    sharp_face: float = 0.0
    sharp_img: float = 0.0
    blockiness: float = 1.0      # mức "vỡ khối" 8px của JPEG (1.0 = không thấy)
    jpeg_q: float | None = None  # chất lượng JPEG ước lượng từ bảng nén
    jpeg_q_match: int | None = None
    jpeg_err: float | None = None
    lum_face: float = 0.0
    lum_img: float = 0.0
    std_face: float = 0.0
    other_face: float = 0.0       # diện tích mặt người khác / mặt chính
    other_person: float = 0.0     # diện tích người khác / người chính
    face_sim: float = -1.0        # cosine ArcFace với ảnh tham chiếu (nếu có)
    clip: np.ndarray | None = None  # embedding ngoại hình (đo "cùng look"), không ghi CSV
    look: int = -1                # chỉ số cụm look sau khi chọn
    face_box: tuple | None = None  # xyxy mặt chính trong ảnh (để tự cắt cận mặt)
    extent: float = 0.0            # số "đầu" từ cằm xuống đáy ảnh (đo shot toàn thân)
    crop_box: tuple | None = None  # (x, y, side) khung cận mặt sẽ cắt
    parent: "Row | None" = None    # ảnh gốc của ảnh cận mặt tự cắt
    source: str = ""
    t: float | None = None
    cls: str = ""
    score: float = 0.0
    accepted: bool = False
    reason: str = ""
    rank: int = 0

    def as_dict(self) -> dict:
        return {
            "file": self.name, "w": self.w, "h": self.h, "short_side": self.short,
            "faces": self.n_faces, "persons": self.n_persons,
            "face_px": self.face_px, "face_frac": round(self.face_frac, 4),
            "extent": round(self.extent, 2),
            "face_border": round(self.face_border, 4),
            "yaw": round(self.yaw, 1), "pitch": round(self.pitch, 1), "bucket": self.bucket,
            "sharp_face": round(self.sharp_face, 1), "sharp_img": round(self.sharp_img, 1),
            "blockiness": round(self.blockiness, 3),
            "jpeg_q": self.jpeg_q, "jpeg_q_match": self.jpeg_q_match, "jpeg_err": self.jpeg_err,
            "lum_face": round(self.lum_face, 1), "lum_img": round(self.lum_img, 1),
            "std_face": round(self.std_face, 1),
            "other_face": round(self.other_face, 3), "other_person": round(self.other_person, 3),
            "face_sim": round(self.face_sim, 3),
            "source": self.source, "t": self.t, "class": self.cls,
            "score": round(self.score, 4), "accepted": int(self.accepted), "reason": self.reason,
        }


# --------------------------------------------------------------------- số đo ảnh


def dhash64(gray: np.ndarray, size: int = 8) -> int:
    """dHash 64 bit: so sánh cường độ 2 pixel cạnh nhau sau khi thu về (size+1)×size."""
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    out = 0
    for bit in diff.reshape(-1):
        out = (out << 1) | int(bit)
    return out


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def blockiness(gray: np.ndarray) -> float:
    """Mức "vỡ khối" JPEG: gradient ở biên khối 8×8 so với gradient trung bình.

    1.0 = không thấy khối; >1.15 là bắt đầu thấy vỡ khối do nén.
    """
    if gray.size == 0:
        return 1.0
    g = gray.astype(np.float32)
    gx = np.abs(np.diff(g, axis=1))
    gy = np.abs(np.diff(g, axis=0))
    ax = float(gx.mean()) + 1e-6
    ay = float(gy.mean()) + 1e-6
    ex = float(gx[:, 7::8].mean()) if gx.shape[1] > 7 else ax
    ey = float(gy[7::8, :].mean()) if gy.shape[0] > 7 else ay
    return float(0.5 * (ex / ax + ey / ay))


def head_pose_lm(kps: np.ndarray) -> tuple[float, float]:
    """(yaw, pitch) độ từ 5 landmark. Cùng công thức core.select.head_pose."""
    eye_l, eye_r, nose, mouth_l, mouth_r = (np.asarray(p, dtype=np.float32) for p in kps[:5])
    eye_mid = (eye_l + eye_r) / 2.0
    mouth_mid = (mouth_l + mouth_r) / 2.0
    eye_d = float(np.linalg.norm(eye_r - eye_l))
    if eye_d < 1e-3:
        return 0.0, 0.0
    center_x = (eye_mid[0] + mouth_mid[0]) / 2.0
    ratio_x = (nose[0] - center_x) / (0.35 * eye_d)
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, ratio_x))))
    ratio_y = (nose[1] - eye_mid[1]) / eye_d
    pitch = (ratio_y - 20.2 / 35.24) * 60.0
    return float(yaw), float(max(-89.0, min(89.0, pitch)))


def yaw_bucket(yaw: float, pitch: float) -> str:
    """Nhóm góc thô để đa dạng hoá: 3/4 / nghiêng hẳn / thẳng / ngẩng / cúi."""
    if pitch >= 18:
        return "hoi ngang"
    if pitch <= -18:
        return "hoi cui"
    a = abs(yaw)
    if a < 12:
        return "thang"
    side = "trai" if yaw > 0 else "phai"
    if a < 32:
        return side
    if a < 55:
        return f"{side} 3/4"
    return f"{side} nghieng"


def classify_shot(face_frac: float, extent: float, close_th: float = 0.34,
                  chest_th: float = 0.20, waist_ext: float = 4.5) -> str:
    """Xếp 4 lớp khung hình: 2 lớp đầu theo hộp mặt, 2 lớp sau theo phần thân còn thấy.

    - `face_frac` = chiều cao hộp mặt SCRFD / chiều cao ảnh. Hộp mặt chỉ tính từ
      lông mày tới cằm, nên 0.34 ≈ "cả đầu chiếm ~50% khung"; 0.50 thì gần như chỉ
      còn mắt-mũi-miệng.
    - `extent` = số "đầu" từ cằm xuống đáy ảnh. Chân dung nửa người ~1–2.5, ngang
      eo ~2.5–4.5, còn ≥ 4.5 là thấy tới đùi/gối/bàn chân — tức toàn thân.
    """
    if face_frac >= close_th:
        return CLASS_CLOSE
    if face_frac >= chest_th:
        return CLASS_CHEST
    if extent < waist_ext:
        return CLASS_WAIST
    return CLASS_FULL


class FaceBank:
    """SCRFD ở 640×640 — DirectML chỉ chạy được đúng kích thước này (xem core/scrfd.py),
    nên không đổi det_size theo ảnh; ảnh lớn vẫn ổn vì mặt trong crop luôn chiếm tỉ lệ."""

    def __init__(self, device: str = "auto"):
        self.lo = FaceDetector(device=device, det_size=640)
        self.backend = self.lo.backend

    def detect(self, img: np.ndarray):
        return self.lo.detect(img)


CACHE_FIELDS = ("w", "h", "short", "md5", "dhash", "dhash_flip", "n_faces", "n_persons",
                "face_px", "face_frac", "face_border", "yaw", "pitch", "bucket",
                "sharp_face", "sharp_img", "blockiness", "jpeg_q", "jpeg_q_match",
                "jpeg_err", "lum_face", "lum_img", "std_face",
                "other_face", "other_person", "face_sim", "face_box", "extent", "source", "t", "cls")


def load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def cache_key(path: Path) -> str:
    st = path.stat()
    return f"{path.name}:{st.st_size}:{int(st.st_mtime)}"


def row_from_cache(path: Path, d: dict) -> Row:
    r = Row(path=path, name=path.name)
    for k in CACHE_FIELDS:
        if k in d and d[k] is not None:
            setattr(r, k, d[k])
    r.reason = d.get("reason", "")
    return r


def row_to_cache(r: Row) -> dict:
    d = {}
    for k in CACHE_FIELDS:
        v = getattr(r, k)
        if isinstance(v, np.floating):
            v = float(v)
        elif isinstance(v, np.integer):
            v = int(v)
        d[k] = v
    d["reason"] = r.reason
    return d


def analyze(path: Path, faces: "FaceBank", persons: "PersonDetector | None",
            meta: dict, args, embedder: "FaceEmbedder | None" = None,
            ref_emb: np.ndarray | None = None) -> Row:
    row = Row(path=path, name=path.name)
    img = read_image(path)
    if img is None or img.size == 0:
        row.reason = "unreadable"
        return row
    row.h, row.w = img.shape[:2]
    row.short = min(row.w, row.h)
    row.md5 = hashlib.md5(path.read_bytes()).hexdigest()
    m = meta.get(path.name)
    row.source = (m.get("source") if m else "") or path.stem
    row.t = m.get("t") if m else None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    row.dhash = dhash64(gray)
    row.dhash_flip = dhash64(cv2.flip(gray, 1))
    row.sharp_img = laplacian_var(gray)
    row.lum_img = float(gray.mean())
    row.blockiness = blockiness(gray)
    row.jpeg_q, row.jpeg_q_match, row.jpeg_err = jpeg_quality(path)

    found = faces.detect(img)
    row.n_faces = len(found)
    if not found:
        row.reason = "no_face"
        return row

    # đúng người: so ArcFace với ảnh tham chiếu, lấy mặt GIỐNG NHẤT trong khung
    if embedder is not None and ref_emb is not None:
        by_area = sorted(found, key=lambda f: -(f.box[2] - f.box[0]) * (f.box[3] - f.box[1]))
        sims = []
        for f in by_area[:4]:
            emb = embedder.embed_face(img, f.kps)
            sims.append(cosine(ref_emb, emb))
        row.face_sim = max(sims) if sims else -1.0

    # mặt chính: ưu tiên diện tích × score, thưởng nhẹ nếu ở nửa trên và gần trục giữa
    def w(f):
        area = (f.box[2] - f.box[0]) * (f.box[3] - f.box[1])
        cx = (f.box[0] + f.box[2]) / 2 / max(1, row.w)
        cy = (f.box[1] + f.box[3]) / 2 / max(1, row.h)
        bonus = 1.25 if cy < 0.55 else 0.9
        return area * f.score * bonus * (1.0 - 0.3 * abs(cx - 0.5))

    main = max(found, key=w)
    x1, y1, x2, y2 = [float(v) for v in main.box]
    fw, fh = max(1.0, x2 - x1), max(1.0, y2 - y1)
    row.face_px = int(round(max(fw, fh)))
    row.face_frac = fh / max(1, row.h)
    row.face_border = min(x1, y1, row.w - x2, row.h - y2) / max(1, row.short)
    row.face_box = (x1, y1, x2, y2)
    row.extent = (row.h - y2) / max(1.0, fh)

    area_main = fw * fh
    for f in found:
        if f is main:
            continue
        area = (f.box[2] - f.box[0]) * (f.box[3] - f.box[1])
        row.other_face = max(row.other_face, area / max(1.0, area_main))

    # độ nét / sáng vùng mặt: chuẩn hoá về 112×112 (đúng ngưỡng đã hiệu chỉnh ở pipeline)
    fb = crop_xyxy(img, main.box)
    if fb.size:
        interp = cv2.INTER_AREA if max(fb.shape[:2]) > 112 else cv2.INTER_LINEAR
        face112 = cv2.resize(fb, (112, 112), interpolation=interp)
        g112 = cv2.cvtColor(face112, cv2.COLOR_BGR2GRAY)
        row.sharp_face = laplacian_var(g112)
        row.lum_face = float(g112.mean())
        row.std_face = float(g112.std())

    row.yaw, row.pitch = head_pose_lm(main.kps)
    row.bucket = yaw_bucket(row.yaw, row.pitch)
    row.cls = classify_shot(row.face_frac, row.extent, args.close_frac, args.chest_frac, args.waist_extent)

    if persons is not None:
        ppl = persons.detect(img)
        ppl = [p for p in ppl if p.score >= 0.4]
        row.n_persons = len(ppl)
        if ppl:
            def area_of(b):
                return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])

            main_p = max(ppl, key=lambda p: area_of(p.box))
            a_main = max(1.0, area_of(main_p.box))
            row.other_person = max([area_of(p.box) / a_main for p in ppl if p is not main_p] or [0.0])
    return row


# ------------------------------------------------------------------------- cổng lọc


def gates(row: Row, args) -> str:
    """Trả lý do loại, hoặc '' nếu đạt."""
    if row.reason:
        return row.reason
    if row.short < args.min_side:
        return "small"
    if row.jpeg_q is not None and row.jpeg_q < args.min_jpeg_quality:
        return "jpeg_quality"
    if row.jpeg_q is None and args.reject_nonjpeg:
        return "not_jpeg"
    if row.n_faces == 0:
        return "no_face"
    if row.face_sim >= 0 and row.face_sim < args.min_face_sim:
        return "wrong_person"
    if row.face_frac > args.max_face_frac:
        return "too_tight"
    if row.face_px < args.min_face_px:
        return "face_too_small"
    if row.face_border < args.face_border:
        return "face_at_border"
    if row.other_face >= args.max_other_face:
        return "other_face"
    if row.n_persons >= 2 and row.other_person >= args.max_other_person:
        return "other_person"
    if row.sharp_face < args.min_face_sharp:
        return "blurry_face"
    if row.sharp_img < args.min_img_sharp:
        return "blurry"
    if not (args.min_lum <= row.lum_face <= args.max_lum):
        return "bad_light"
    if row.std_face < args.min_face_std:
        return "flat"
    return ""


def score(row: Row, args) -> float:
    def n01(v, lo, hi):
        return float(np.clip((v - lo) / max(1e-6, hi - lo), 0.0, 1.0))

    s_sharp = n01(row.sharp_face, args.min_face_sharp, args.good_face_sharp)
    s_size = n01(row.short, args.min_side, args.ideal_side)
    s_face = n01(row.face_frac, 0.05, 0.45)
    s_lum = 1.0 - min(1.0, abs(row.lum_face - 135.0) / 75.0)
    s_det = n01(row.sharp_img, args.min_img_sharp, args.good_img_sharp)
    return 0.40 * s_sharp + 0.20 * s_size + 0.20 * s_face + 0.10 * s_lum + 0.10 * s_det


# ------------------------------------------------------------------------- chọn bộ


def dedupe(rows: list[Row], args) -> list[Row]:
    """Gộp cụm gần trùng: MD5 trùng, hoặc dHash (kể cả bản lật) trong ngưỡng,
    hoặc cùng nguồn + gần thời điểm + dHash tương đối gần. Giữ ảnh điểm cao nhất."""
    rows = sorted(rows, key=lambda r: -r.score)
    kept: list[Row] = []
    for r in rows:
        dup = False
        for k in kept:
            if r.md5 == k.md5:
                dup = True
                break
            d = min(hamming(r.dhash, k.dhash),
                    hamming(r.dhash_flip, k.dhash),
                    hamming(r.dhash, k.dhash_flip))
            th = args.dup_hamming
            if r.source == k.source and r.t is not None and k.t is not None \
                    and abs(r.t - k.t) <= args.near_t:
                th = max(th, args.dup_hamming_near)
            if d <= th:
                dup = True
                break
        if not dup:
            kept.append(r)
        else:
            r.reason = "duplicate"
    return kept


def select(rows: list[Row], args) -> list[Row]:
    """Chọn theo tỉ lệ cỡ cảnh + trần nguồn/góc/cửa sổ thời gian/cụm look, điểm cao trước."""
    rows = sorted(rows, key=lambda r: -r.score)
    max_n = args.max_images
    quota = {c: int(round(max_n * q)) for c, q in CLASS_QUOTA.items()}
    bucket_cap = max(2, int(round(max_n * args.bucket_share)))
    src_cap = max(1, int(round(max_n * args.source_share)))
    src_cap = min(src_cap, args.max_per_source) if args.max_per_source else src_cap
    win = max(1, args.per_window)
    per_look = max(1, args.per_look)

    chosen: list[Row] = []
    cnt = Counter()
    src_n = Counter()
    bkt_n = Counter()
    win_n = Counter()
    look_reps: list[Row] = []          # đại diện từng cụm look đã có ảnh
    look_n = Counter()
    look_cap = per_look

    def window_key(r):
        if r.t is None:
            return None
        return (r.source, int(r.t // args.window_sec))

    def look_of(r) -> int:
        """Chỉ số cụm look (ảnh giống nhất với 1 ảnh đã chọn), -1 nếu look mới."""
        if r.clip is None or not look_reps:
            return -1
        best, bi = -1.0, -1
        for i, c in enumerate(look_reps):
            if c.clip is None:
                continue
            s = float(np.dot(r.clip, c.clip))
            if s > best:
                best, bi = s, i
        return bi if best >= args.look_sim else -1

    def try_take(r, check_quota, check_bucket, check_window, check_src, check_look):
        if len(chosen) >= max_n:
            return False
        if check_src and src_n[r.source] >= src_cap:
            return False
        if check_quota and cnt[r.cls] >= quota[r.cls]:
            return False
        if check_bucket and bkt_n[r.bucket] >= bucket_cap:
            return False
        wk = window_key(r)
        if check_window and wk is not None and win_n[wk] >= win:
            return False
        lk = look_of(r) if check_look else -1
        if check_look and lk >= 0 and look_n[lk] >= look_cap:
            return False
        if check_look and lk >= 0:
            r.look = lk
        elif check_look:
            r.look = len(look_reps)
            look_reps.append(r)
        chosen.append(r)
        r.accepted = True
        cnt[r.cls] += 1
        src_n[r.source] += 1
        bkt_n[r.bucket] += 1
        if r.look >= 0:
            look_n[r.look] += 1
        if wk is not None:
            win_n[wk] += 1
        return True

    for r in rows:                          # pass 1: đủ mọi ràng buộc
        try_take(r, True, True, True, True, True)
    look_cap = per_look * 2
    for r in rows:                          # pass 2: nới trần góc/cửa sổ, trần look ×2
        if not r.accepted:
            try_take(r, True, False, False, True, True)
    for r in rows:                          # pass 3: nới tỉ lệ cỡ cảnh, bỏ trần look
        if not r.accepted:
            try_take(r, False, False, False, True, False)

    chosen.sort(key=lambda r: (CLASS_ORDER.index(r.cls), -r.score))
    for i, r in enumerate(chosen, 1):
        r.rank = i
    for r in rows:
        if not r.accepted and not r.reason:
            r.reason = "over_quota"
    return chosen


# ------------------------------------------------------------------------ báo cáo


def write_csv(path: Path, rows: list[Row]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].as_dict().keys()) if rows else []
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        for r in rows:
            wr.writerow(r.as_dict())


def make_sheets(items: list[Row], out_dir: Path, prefix: str, cols: int = 6,
                tile_w: int = 260, per_sheet: int = 36) -> list[Path]:
    """Contact sheet có số thứ tự + nhãn ASCII để soi mắt."""
    paths = []
    if not items:
        return paths
    for si in range(0, len(items), per_sheet):
        chunk = items[si:si + per_sheet]
        tiles = []
        for r in chunk:
            img = read_image(r.path)
            if img is None:
                continue
            h, w = img.shape[:2]
            th = max(1, int(round(h * tile_w / w)))
            tile = cv2.resize(img, (tile_w, th), interpolation=cv2.INTER_AREA)
            th = min(th, 420)
            tile = tile[:th]
            canvas = np.full((th + 26, tile_w, 3), 24, np.uint8)
            canvas[:th] = tile
            cap = f"#{r.rank:03d} {r.cls[:4]} f{r.face_px} sh{int(r.sharp_face)}"
            cv2.putText(canvas, cap, (3, th + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        (235, 235, 235), 1, cv2.LINE_AA)
            tiles.append(canvas)
        if not tiles:
            continue
        ch = max(t.shape[0] for t in tiles)
        rows_n = (len(tiles) + cols - 1) // cols
        sheet = np.full((rows_n * ch, cols * tile_w, 3), 12, np.uint8)
        for i, t in enumerate(tiles):
            y, x = (i // cols) * ch, (i % cols) * tile_w
            sheet[y:y + t.shape[0], x:x + t.shape[1]] = t
        out = out_dir / f"{prefix}_{si // per_sheet + 1}.jpg"
        ok, buf = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if ok:
            buf.tofile(str(out))
            paths.append(out)
    return paths


def print_distribution(rows: list[Row]) -> None:
    """In phân bố số đo để chọn ngưỡng (dùng với --analyze-only)."""
    def q(vals, ps=(0, 10, 25, 50, 75, 90, 100)):
        if not vals:
            return "  (trong)"
        a = np.asarray(vals, dtype=float)
        parts = [f"p{p}={np.percentile(a, p):.1f}" for p in ps]
        return "  ".join(parts)

    have = [r for r in rows if r.n_faces > 0]
    print("\n=== PHAN BO SO DO (chi anh co mat) ===")
    for key, label in (("short", "canh ngan"), ("face_px", "face_px"), ("face_frac", "face_frac"),
                       ("sharp_face", "sharp_face"), ("sharp_img", "sharp_img"),
                       ("blockiness", "blockiness"), ("jpeg_q", "jpeg_q"),
                       ("lum_face", "lum_face"), ("std_face", "std_face"),
                       ("other_face", "other_face")):
        vals = [getattr(r, key) for r in have]
        vals = [v for v in vals if v is not None]
        print(f"{label:12s} n={len(vals):3d}  {q(vals)}")
    print(f"khong thay mat: {sum(1 for r in rows if r.n_faces == 0)}/{len(rows)}")
    print("\nti le qua tung cong (tinh doc lap, tren anh co mat):")
    checks = {
        "size>=min_side": lambda r: r.short >= 768,
        "face_px>=80": lambda r: r.face_px >= 80,
        "sharp_face>=55": lambda r: r.sharp_face >= 55,
        "sharp_face>=100": lambda r: r.sharp_face >= 100,
        "sharp_img>=40": lambda r: r.sharp_img >= 40,
        "lum 62..212": lambda r: 62 <= r.lum_face <= 212,
        "std>=14": lambda r: r.std_face >= 14,
        "other_face<0.22": lambda r: r.other_face < 0.22,
        "face_border>=0.012": lambda r: r.face_border >= 0.012,
    }
    for name, fn in checks.items():
        print(f"  {name:20s} {sum(1 for r in have if fn(r)):3d}/{len(have)}")
    print("\nco canh (face_frac):")
    for c, v in Counter(r.cls for r in have).most_common():
        print(f"  {CLASS_LABEL[c]:18s} {v:3d}")
    print("\nnhom goc:")
    for c, v in Counter(r.bucket for r in have).most_common():
        print(f"  {c:14s} {v:3d}")


def face_crop_box(r: Row, args) -> tuple[int, int, int] | None:
    """(x, y, side) khung cận mặt hợp lệ, hoặc None.

    Vuông quanh mặt, cạnh = --face-crop-scale × chiều cao mặt (mặt chiếm ~1/scale
    khung). Dịch cho vừa ảnh, **không** phóng to: cạnh phải >= --face-crop-min-side
    và khung phải nằm trọn trong ảnh gốc.
    """
    if r.face_box is None or r.face_px < args.face_crop_min:
        return None
    x1, y1, x2, y2 = r.face_box
    fh = y2 - y1
    # vuông nếu vừa; ảnh hẹp (4:5) thì lấy cạnh ngắn nhất -> mặt càng chiếm lớn,
    # vẫn là cắt pixel gốc chứ không phóng to
    side = min(int(round(fh * args.face_crop_scale)), r.w, r.h)
    min_side = max(args.face_crop_min_side, 1)
    if side < min_side:
        return None
    cx = (x1 + x2) / 2.0
    eye_y = y1 + 0.35 * fh
    bx = int(round(cx - side / 2.0))
    by = int(round(eye_y - 0.40 * side))
    bx = min(max(0, bx), r.w - side)
    by = min(max(0, by), r.h - side)
    return bx, by, side


def _face_area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def mine_variants(rows: list[Row], faces: "FaceBank", embedder, ref_emb, args) -> list[Row]:
    """Tự tìm và cắt thêm ảnh CẬN MẶT từ **mọi** ảnh có mặt đủ lớn.

    Cố ý quét cả ảnh bị loại ở bước chọn: một ảnh có watermark / người khác /
    khung xấu vẫn có thể cho một khung cận mặt sạch — cắt sát mặt là cách loại
    luôn chữ ở nền và người đứng cạnh. Ảnh sai người (`wrong_person`) và ảnh có
    trong `--skip-list` thì không quét.

    Mỗi khung cắt ra được **kiểm tra lại như một ảnh độc lập**: phải thấy đúng 1
    mặt, mặt chiếm đủ lớn, đúng người, và đủ nét; không đạt thì bỏ.
    """
    out: list[Row] = []
    seen: set[str] = set()
    for r in rows:
        if r.n_faces == 0 or r.reason in ("no_face", "wrong_person", "skip_list"):
            continue
        if r.face_sim >= 0 and r.face_sim < args.min_face_sim:
            continue
        if r.sharp_face < args.min_face_sharp or r.std_face < args.min_face_std:
            continue
        if not (args.min_lum <= r.lum_face <= args.max_lum):
            continue
        if r.jpeg_q is not None and r.jpeg_q < args.min_jpeg_quality:
            continue                              # nén mạnh thì cắt ra cũng vỡ khối
        box = face_crop_box(r, args)
        if box is None:
            continue
        name = f"{r.path.stem}_face{r.path.suffix}"
        if name in seen:
            continue
        v = Row(path=r.path, name=name, w=box[2], h=box[2], short=box[2],
                n_faces=1, n_persons=r.n_persons, face_px=r.face_px,
                face_frac=1.0 / args.face_crop_scale, face_border=1.0,
                yaw=r.yaw, pitch=r.pitch, bucket=r.bucket,
                sharp_face=r.sharp_face, sharp_img=r.sharp_img, lum_face=r.lum_face,
                lum_img=r.lum_img, std_face=r.std_face, other_face=r.other_face,
                other_person=r.other_person, face_sim=r.face_sim,
                blockiness=r.blockiness, jpeg_q=r.jpeg_q, jpeg_q_match=r.jpeg_q_match,
                jpeg_err=r.jpeg_err,
                source=r.source, t=r.t, cls=CLASS_CLOSE, score=r.score,
                crop_box=box, parent=r)
        if verify_variant(v, faces, embedder, ref_emb, args):
            seen.add(name)
            out.append(v)
    return out


def verify_variant(v: Row, faces: "FaceBank", embedder, ref_emb, args) -> bool:
    """Đo lại chính khung cận mặt vừa cắt: 1 mặt, to, đúng người, đủ nét."""
    if v.crop_box is None or v.parent is None:
        return False
    img = read_image(v.parent.path)
    if img is None:
        return False
    bx, by, side = v.crop_box
    crop = img[by:by + side, bx:bx + side]
    if crop.size == 0 or min(crop.shape[:2]) < max(args.face_crop_min_side, 1):
        return False

    found = faces.detect(crop)
    if not found:
        return False
    main = max(found, key=lambda f: _face_area(f.box) * f.score)
    if _face_area(main.box) / float(side * side) < args.face_crop_face_area:
        return False
    for f in found:
        if f is not main and _face_area(f.box) >= args.max_other_face * _face_area(main.box):
            return False                       # dính mặt người khác trong khung

    if embedder is not None and ref_emb is not None:
        sims = []
        for f in sorted(found, key=lambda f: -_face_area(f.box))[:2]:
            sims.append(cosine(ref_emb, embedder.embed_face(crop, f.kps)))
        v.face_sim = max(sims) if sims else -1.0
        if v.face_sim < args.min_face_sim:
            return False

    fb = crop_xyxy(crop, main.box)
    if not fb.size:
        return False
    interp = cv2.INTER_AREA if max(fb.shape[:2]) > 112 else cv2.INTER_LINEAR
    face112 = cv2.resize(fb, (112, 112), interpolation=interp)
    g112 = cv2.cvtColor(face112, cv2.COLOR_BGR2GRAY)
    v.sharp_face = laplacian_var(g112)
    v.lum_face = float(g112.mean())
    v.face_px = int(round(max(main.box[2] - main.box[0], main.box[3] - main.box[1])))
    v.face_frac = (main.box[3] - main.box[1]) / max(1, side)

    # dấu vân tay của chính khung cắt để lọc các khung gần trùng nhau
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    v.dhash = dhash64(gray)
    v.dhash_flip = dhash64(cv2.flip(gray, 1))
    v.md5 = hashlib.md5(crop.tobytes()).hexdigest()
    return v.sharp_face >= args.min_face_sharp and args.min_lum <= v.lum_face <= args.max_lum


def _greedy_fill(pool: list[Row], chosen: list[Row], n: int, args) -> list[Row]:
    """Chọn n ảnh từ pool, greedy trừ điểm trùng look (CLIP) và dồn nhóm góc."""
    picked: list[Row] = []
    if n <= 0:
        return picked
    look_vecs = [r.clip for r in chosen if r.clip is not None]
    bucket_cnt = Counter(r.bucket for r in chosen)
    rest = list(pool)
    while rest and len(picked) < n:
        best, best_u = None, -1e9
        for r in rest:
            sim = 0.0
            if r.clip is not None and look_vecs:
                sim = max(float(np.dot(r.clip, v)) for v in look_vecs)
            share = bucket_cnt[r.bucket] / max(1, len(chosen) + len(picked))
            utility = r.score - args.look_penalty * max(0.0, sim) - args.bucket_penalty * share
            if utility > best_u:
                best, best_u = r, utility
        rest.remove(best)
        picked.append(best)
        bucket_cnt[best.bucket] += 1
        if best.clip is not None:
            look_vecs.append(best.clip)
    return picked


def max_fill_select(rows: list[Row], args) -> list[Row]:
    """WF "lấy tối đa rồi bù": lấy **hết** ảnh cận mặt + ngang vai/ngực đạt cổng,
    rồi tính số ảnh ngang eo + toàn thân cần thêm cho đủ tỉ lệ (4 lớp).

    Khối cận+vai chiếm `quota_cận + quota_vai` của bộ (theo trung điểm các dải
    trong spec), nên tổng = khối / (quota_cận + quota_vai). Hai lớp còn lại được
    chọn **greedy trừ điểm**: ảnh trùng look (CLIP cao với ảnh đã có) hoặc dồn vào
    một nhóm góc đã nhiều bị trừ điểm, nên ảnh lấy sau càng đa dạng.
    """
    base = sorted((r for r in rows if r.cls in (CLASS_CLOSE, CLASS_CHEST)),
                  key=lambda r: -r.score)
    if not base:
        return []
    pool = {c: sorted((r for r in rows if r.cls == c), key=lambda r: -r.score)
            for c in (CLASS_WAIST, CLASS_FULL)}

    share_base = CLASS_QUOTA[CLASS_CLOSE] + CLASS_QUOTA[CLASS_CHEST]
    total = int(round(len(base) / max(1e-6, share_base)))
    if args.max_images:
        total = min(total, args.max_images)
    n_fill = {c: max(0, int(round(total * CLASS_QUOTA[c]))) for c in (CLASS_WAIST, CLASS_FULL)}
    if len(base) > total:
        print(f"  canh bao: {len(base)} anh can+vai da vuot tran {total} -> giu het, khong bu")
        n_fill = {c: 0 for c in n_fill}

    chosen = list(base)
    added = {}
    for c in (CLASS_WAIST, CLASS_FULL):
        got = _greedy_fill(pool[c], chosen, n_fill[c], args)
        chosen.extend(got)
        added[c] = len(got)

    keep_ids = {id(r) for r in chosen}
    for r in rows:
        if id(r) in keep_ids:
            r.accepted = True
        elif not r.reason:
            r.reason = "over_quota"
    chosen.sort(key=lambda r: (CLASS_ORDER.index(r.cls), -r.score))
    for i, r in enumerate(chosen, 1):
        r.rank = i
    print(f"  can+vai {len(base)} -> tong {len(chosen)}"
          f" (+{added[CLASS_WAIST]} eo, +{added[CLASS_FULL]} toan than)")
    return chosen


def assemble(chosen: list[Row], variants: list[Row], args) -> tuple[list[Row], list[Row]]:
    """Gộp ảnh gốc + ảnh cận tự cắt thành bộ cuối: đúng **tổng số** và tỉ lệ 4 lớp.

    `--target-close` chỉ dùng để chặn tổng (muốn 40% cận thì tổng tối đa là
    `số_ảnh_cận / 0.40`); các lớp còn lại chia theo CLASS_QUOTA, lớp nào thiếu thì
    bù bằng lớp khác để vẫn đủ tổng.
    """
    pools = {c: sorted([r for r in chosen if r.cls == c] + (variants if c == CLASS_CLOSE else []),
                       key=lambda r: -r.score)
             for c in CLASS_ORDER}

    total = args.max_images
    if args.target_close > 0 and pools[CLASS_CLOSE]:
        reachable = int(round(len(pools[CLASS_CLOSE]) / args.target_close))
        total = min(total, max(args.min_images, reachable))

    want = {}
    if args.target_close > 0:
        want[CLASS_CLOSE] = min(len(pools[CLASS_CLOSE]),
                                int(round(total * args.target_close)))
    else:
        want[CLASS_CLOSE] = len(pools[CLASS_CLOSE])
    slots = max(0, total - want[CLASS_CLOSE])
    rest = [c for c in CLASS_ORDER if c != CLASS_CLOSE]
    share = {c: CLASS_QUOTA[c] / sum(CLASS_QUOTA[x] for x in rest) for c in rest}
    for c in rest:
        want[c] = min(len(pools[c]), int(round(slots * share[c])))
    left = slots - sum(want[c] for c in rest)          # lớp nào thiếu thì bù
    for c in rest:
        if left <= 0:
            break
        add = min(len(pools[c]) - want[c], left)
        want[c] += add
        left -= add

    keep = set()
    for c in CLASS_ORDER:
        keep |= {id(r) for r in pools[c][:want[c]]}

    out_chosen, out_variants = [], []
    for r in chosen + variants:
        if id(r) in keep:
            if r in variants:
                out_variants.append(r)
            else:
                out_chosen.append(r)
        elif r in variants:
            r.reason = "budget"
        else:
            r.accepted = False
            r.reason = "budget"
    return out_chosen, out_variants


def write_variant(v: Row, dst: Path, args) -> bool:
    """Ghi ảnh cận mặt ra file (cắt từ ảnh gốc, không phóng to)."""
    if v.crop_box is None or v.parent is None:
        return False
    img = read_image(v.parent.path)
    if img is None:
        return False
    bx, by, side = v.crop_box
    crop = img[by:by + side, bx:bx + side]
    if crop.size == 0 or min(crop.shape[:2]) < args.min_side:
        return False
    return bool(write_image(dst / v.name, crop, quality=95))


def write_summary(path: Path, rows: list[Row], chosen: list[Row], args, src_n: int,
                  elapsed: float, sheets: list[Path], n_face_crop: int = 0) -> None:
    total = len(rows)
    reasons = Counter(r.reason for r in rows if not r.accepted)
    line = []
    add = line.append
    add("LOC ANH CHO DATASET LoRA")
    add(f"thoi diem: {time.strftime('%Y-%m-%d %H:%M:%S')}  ({elapsed:.1f}s)")
    add(f"nguon: " + " | ".join(str(s) for s in args.src))
    add(f"workflow: {args.workflow}"
        + ("  (lay toi da can+vai, roi bu ngang eo + toan than cho du dai ti le)" if args.workflow == "max-fill"
           else f"  (ti le can mat muc tieu {args.target_close:.0%})"))
    add(f"dich:  {args.dst}")
    add("")
    add(f"anh doc duoc: {src_n}  ·  dat: {len(chosen)}  ·  loai: {total - len(chosen)}")
    add("")
    add("LY DO LOAI")
    for k, v in reasons.most_common():
        add(f"  {k:16s} {v:4d}")
    add("")
    total_n = len(chosen) + n_face_crop
    add(f"CO CANH  (tong {total_n} anh)")
    for c in CLASS_ORDER:
        n = (n_face_crop if c == CLASS_CLOSE else 0) + sum(1 for r in chosen if r.cls == c)
        share = n / max(1, total_n)
        add(f"  {CLASS_LABEL[c]:18s} {n:3d}  {share:5.1%}   (muc tieu {CLASS_QUOTA[c]:.0%})")
    if n_face_crop:
        add(f"  ({n_face_crop} anh can mat tu cat them tu chinh anh goc, khong phong to)")
    add("")
    add("GOC MAT")
    for k, v in Counter(r.bucket for r in chosen).most_common():
        add(f"  {k:14s} {v:3d}")
    add("")
    looks = Counter(r.look for r in chosen if r.look >= 0)
    if looks:
        add(f"LOOK (CLIP >= {args.look_sim:.2f}, tran {args.per_look}): {len(looks)} cum,"
            f" nhieu nhat {max(looks.values())} anh/cum")
    add("")
    add(f"NGUON: {len({r.source for r in chosen})} nguon / tran {args.source_share:.0%}")
    for k, v in Counter(r.source for r in chosen).most_common(10):
        add(f"  {v:2d}x {Path(k).name if k else k}")
    add("")
    sh = [r.short for r in chosen]
    if sh:
        add(f"canh ngan: min {min(sh)} · trung vi {int(np.median(sh))} · max {max(sh)}"
            f"  (nguong {args.min_side}, muc tieu {args.ideal_side})")
        add(f"face_px:  min {min(r.face_px for r in chosen)} · trung vi"
            f" {int(np.median([r.face_px for r in chosen]))} · max {max(r.face_px for r in chosen)}")
    add("")
    add("CHAT LUONG JPEG (doc tu bang nen trong header)")
    all_q = [r.jpeg_q for r in rows if r.jpeg_q is not None]
    keep_q = [r.jpeg_q for r in chosen if r.jpeg_q is not None]
    if all_q:
        add(f"  toan bo:  n={len(all_q)}  trung vi {np.median(all_q):.0f}"
            f"  · duoi {args.min_jpeg_quality:.0f}: {sum(1 for q_ in all_q if q_ < args.min_jpeg_quality)}")
    if keep_q:
        add(f"  anh dat:  n={len(keep_q)}  trung vi {np.median(keep_q):.0f}"
            f"  · thap nhat {min(keep_q):.0f}")
    n_nj = sum(1 for r in rows if r.jpeg_q is None)
    if n_nj:
        add(f"  {n_nj} anh khong phai JPEG (khong co bang nen) -> "
            f"{'loai' if args.reject_nonjpeg else 'bo qua cong nay'}")
    bl = [r.blockiness for r in chosen]
    if bl:
        add(f"  vo khoi (blockiness) trung vi {np.median(bl):.2f} (1.00 = khong thay khoi)")
    add("")
    add("CANH BAO")
    n_small = sum(1 for r in rows if r.reason == "small")
    add(f"  - {n_small} anh bi loai vi canh ngan < {args.min_side}px (ha --min-side de giu them).")
    n_meta = sum(1 for r in rows if r.t is not None)
    add(f"  - {n_meta}/{total} anh co thong tin nguon+thoi diem (metadata/mapping);"
        f" phan con lai moi file tinh la mot nguon rieng.")
    if any(r.face_sim >= 0 for r in rows):
        sims = [r.face_sim for r in rows if r.face_sim >= 0]
        add(f"  - face_sim voi anh tham chieu: min {min(sims):.2f} · trung vi"
            f" {float(np.median(sims)):.2f}; nguong --min-face-sim {args.min_face_sim:.2f}")
    n_probe = sum(1 for r in rows if r.h == 2048 or r.w == 2048)
    if n_probe:
        add(f"  - {n_probe} anh co chieu 2048px: nhieu kha nang da bi phong to tu anh nho hon"
            f" (nguon goc <=1920px) - neu khong muon thi loc them o buoc chon.")
    add("  - Script khong tu phat hien watermark / filter man / khau trang / kinh ram:")
    add("    soi sheet_*.jpg roi liet ke file vao --skip-list roi chay lai.")
    for s in sheets:
        add(f"  - sheet: {s}")
    path.write_text("\n".join(line) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Loc dataset LoRA tu thu muc crop.")
    ap.add_argument("--src", required=True, nargs="+",
                    help="thu muc anh dau vao (co the nhieu thu muc, loc chung mot bo)")
    ap.add_argument("--dst", required=True, help="thu muc chep anh dat")
    ap.add_argument("--metadata", default=None,
                    help="metadata.jsonl cua pipeline (lay source/t); mac dinh tu do tim")
    ap.add_argument("--report-dir", default=None, help="noi ghi csv/summary/sheet (mac dinh: thu muc cha cua --dst)")
    ap.add_argument("--min-side", type=int, default=768, help="canh ngan toi thieu (px)")
    ap.add_argument("--ideal-side", type=int, default=1024, help="canh ngan muc tieu (diem cong)")
    ap.add_argument("--min-jpeg-quality", type=float, default=90.0,
                    help="chat luong JPEG toi thieu, doc tu bang nen trong header")
    ap.add_argument("--reject-nonjpeg", action="store_true",
                    help="loai ca anh khong phai JPEG (mac dinh: bo qua cong chat luong)")
    ap.add_argument("--no-convert", action="store_false", dest="convert_nonjpeg",
                    help="giu nguyen webp/... thay vi chuyen thanh JPEG khi chep")
    ap.add_argument("--min-face-px", type=int, default=80, help="canh dai nho nhat cua mat (px)")
    ap.add_argument("--face-border", type=float, default=0.012,
                    help="mat phai cach mep it nhat ti le nay cua canh ngan")
    ap.add_argument("--close-frac", type=float, default=0.34,
                    help="mat/chieu cao khung >= muc nay thi tinh la CAN MAT (0.45 = chi con mat)")
    ap.add_argument("--chest-frac", type=float, default=0.20,
                    help="mat/khung >= muc nay thi tinh la NGANG VAI/NGUC")
    ap.add_argument("--waist-extent", type=float, default=4.5,
                    help="so dau tu cam xuong day anh: duoi muc nay la NGANG EO, tren la TOAN THAN")
    ap.add_argument("--max-face-frac", type=float, default=0.75,
                    help="mat khong duoc chiem qua ti le nay chieu cao khung (cat sat qua)")
    ap.add_argument("--min-face-sharp", type=float, default=55.0,
                    help="Laplacian 112x112 vung mat toi thieu")
    ap.add_argument("--good-face-sharp", type=float, default=160.0, help="muc coi la rat net")
    ap.add_argument("--min-img-sharp", type=float, default=40.0, help="Laplacian ca anh toi thieu")
    ap.add_argument("--good-img-sharp", type=float, default=200.0, help="muc anh net")
    ap.add_argument("--min-lum", type=float, default=62.0, help="do sang TB vung mat toi thieu")
    ap.add_argument("--max-lum", type=float, default=212.0, help="do sang TB vung mat toi da")
    ap.add_argument("--min-face-std", type=float, default=14.0, help="do lech chuan vung mat toi thieu")
    ap.add_argument("--max-other-face", type=float, default=0.22,
                    help="mat nguoi khac / mat chinh >= muc nay thi loai")
    ap.add_argument("--max-other-person", type=float, default=0.30,
                    help="dien tich nguoi khac / nguoi chinh >= muc nay thi loai")
    ap.add_argument("--dup-hamming", type=int, default=6, help="nguong dHash coi la trung")
    ap.add_argument("--dup-hamming-near", type=int, default=10,
                    help="nguong dHash khi cung nguon va gan thoi diem")
    ap.add_argument("--near-t", type=float, default=2.5, help="gan thoi diem (giay)")
    ap.add_argument("--window-sec", type=float, default=10.0, help="cua so thoi gian (giay)")
    ap.add_argument("--per-window", type=int, default=2, help="so anh toi da moi cua so")
    ap.add_argument("--max-images", type=int, default=200,
                    help="so anh toi da (tran cung; da dang van do cac tran khac giu)")
    ap.add_argument("--source-share", type=float, default=0.12, help="tran ti le moi nguon")
    ap.add_argument("--max-per-source", type=int, default=0, help="tran tuyet doi moi nguon (0 = theo ti le)")
    ap.add_argument("--bucket-share", type=float, default=0.35, help="tran ti le moi nhom goc")
    ap.add_argument("--look-sim", type=float, default=0.88,
                    help="cosine CLIP coi la cung mot look (cung bo do / cung boi canh)")
    ap.add_argument("--per-look", type=int, default=3, help="so anh toi da moi cum look")
    ap.add_argument("--no-look", action="store_true", help="khong do CLIP (nhanh hon, kem da dang)")
    ap.add_argument("--face-crops", action="store_true",
                    help="cat them anh CAN MAT tu anh ngang vai/toan than (khong phong to)")
    ap.add_argument("--face-crop-min", type=int, default=420,
                    help="mat phai >= so px nay moi tu cat duoc can mat")
    ap.add_argument("--face-crop-scale", type=float, default=2.2,
                    help="canh khung can mat = so lan chieu cao mat")
    ap.add_argument("--face-crop-min-side", type=int, default=0,
                    help="canh nho nhat cua anh can mat (0 = bang --min-side)")
    ap.add_argument("--face-crop-face-area", type=float, default=0.10,
                    help="mat phai chiem it nhat ti le nay dien tich khung can mat")
    ap.add_argument("--workflow", choices=("ratio", "max-fill"), default="ratio",
                    help="ratio: chon theo ti le 40/35/25 | max-fill: lay toi da can+vai roi bu toan than")
    ap.add_argument("--look-penalty", type=float, default=0.25,
                    help="[max-fill] diem tru khi anh trung look voi anh da chon (CLIP cao)")
    ap.add_argument("--target-close", type=float, default=0.0,
                    help="[workflow ratio] ti le can mat muc tieu (vd 0.40): cat bot anh vai/toan than")
    ap.add_argument("--bucket-penalty", type=float, default=0.15,
                    help="[max-fill] diem tru khi nhom goc nay da chiem ti le cao")
    ap.add_argument("--min-images", type=int, default=30,
                    help="khong cat bot duoi so anh nay khi can ti le")
    ap.add_argument("--skip-list", default=None, help="file liet ke ten anh can loai tay")
    ap.add_argument("--mapping", default=None,
                    help="CSV (file,source,t) khi metadata khong khop ten file")
    ap.add_argument("--no-persons", action="store_true", help="khong chay YOLO (nhanh hon)")
    ap.add_argument("--clean", action="store_true", help="xoa anh cu trong --dst truoc khi chep")
    ap.add_argument("--analyze-only", action="store_true", help="chi do va ghi CSV, khong chep")
    ap.add_argument("--no-cache", action="store_true", help="khong dung cache so do")
    ap.add_argument("--ref", default=None,
                    help="anh tham chieu cua nguoi can lay (bat cong dung nguoi)")
    ap.add_argument("--min-face-sim", type=float, default=0.40,
                    help="cosine ArcFace toi thieu voi anh tham chieu")
    ap.add_argument("--device", default="auto", help="auto|gpu|cpu")
    args = ap.parse_args(argv)

    srcs = [Path(s).expanduser().resolve() for s in args.src]
    for s in srcs:
        if not s.is_dir():
            print(f"khong thay thu muc nguon: {s}", file=sys.stderr)
            return 2
    dst = Path(args.dst).expanduser().resolve()
    report_dir = Path(args.report_dir).expanduser().resolve() if args.report_dir else dst.parent
    report_dir.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    for s in srcs:
        files += [p for p in s.iterdir() if p.suffix.lower() in IMAGE_EXT and p.is_file()]
    # báo cáo của lần chạy trước có thể nằm ngay trong thư mục nguồn
    files = [p for p in sorted(set(files))
             if not p.name.startswith(("sheet_flter_", "sheet_facecrop_"))]
    if not files:
        print(f"khong co anh trong: {', '.join(str(s) for s in srcs)}", file=sys.stderr)
        return 2

    meta_path = Path(args.metadata) if args.metadata else (
        srcs[0].parent / "metadata.jsonl" if len(srcs) == 1 else None)
    meta: dict = {}
    if meta_path is not None and meta_path.exists():
        for ln in meta_path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if "path" in d:
                meta[Path(d["path"]).name] = d

    skip = set()
    if args.skip_list and Path(args.skip_list).exists():
        for ln in Path(args.skip_list).read_text(encoding="utf-8").splitlines():
            ln = ln.split("#")[0].strip()       # bỏ chú thích cuối dòng
            if ln:
                skip.add(Path(ln).name)

    if args.mapping:
        import csv as _csv

        map_path = Path(args.mapping)
        with open(map_path, encoding="utf-8-sig", newline="") as fh:
            for row_m in _csv.DictReader(fh):
                name = Path(str(row_m.get("file", ""))).name
                if not name:
                    continue
                t_val = row_m.get("t")
                try:
                    t_val = float(t_val) if t_val not in (None, "") else None
                except ValueError:
                    t_val = None
                meta[name] = {"source": row_m.get("source", "") or "", "t": t_val}
        print(f"mapping: doc {map_path.name}")

    print(f"nguon {len(srcs)} thu muc · {len(files)} anh · metadata {len(meta)} dong")
    t0 = time.time()
    faces = FaceBank(device=args.device)
    persons = None if args.no_persons else PersonDetector(device=args.device)
    embedder, ref_emb = None, None
    if args.ref:
        ref_img = read_image(Path(args.ref).expanduser().resolve())
        if ref_img is None:
            print(f"khong doc duoc anh tham chieu: {args.ref}", file=sys.stderr)
            return 2
        embedder = FaceEmbedder(device=args.device)
        ref_faces = faces.detect(ref_img)
        if not ref_faces:
            print("khong thay mat trong anh tham chieu", file=sys.stderr)
            return 2
        ref_main = max(ref_faces, key=lambda f: f.score * (f.box[2] - f.box[0]) * (f.box[3] - f.box[1]))
        ref_emb = embedder.embed_face(ref_img, ref_main.kps)
    print(f"backend: mat={faces.backend} nguoi={'-' if persons is None else persons.backend}"
          f" arcface={'-' if embedder is None else embedder.backend}")

    rows: list[Row] = []
    cache_path = report_dir / "filter_cache.json"
    cache = {} if args.no_cache else load_cache(cache_path)
    fresh: dict = {}
    n_hit = 0
    for i, p in enumerate(files, 1):
        ck = cache_key(p)
        cached = cache.get(ck)
        # cache cũ chụp trước khi có --ref thì thiếu face_sim -> đo lại
        if cached is not None and args.ref and cached.get("n_faces", 0) and cached.get("face_sim", -1) < 0:
            cached = None
        if cached is not None and "face_box" not in cached:
            cached = None
        if cached is not None and "jpeg_q" not in cached:
            cached = None
        if cached is not None and "extent" not in cached:
            cached = None
        if cached is not None:
            r = row_from_cache(p, cached)
            m = meta.get(p.name)
            if m:                       # nguon/thoi diem luon lay moi tu mapping
                r.source = m.get("source") or r.source
                r.t = m.get("t")
            # nguong phan loai co the doi giua 2 lan chay -> tinh lai tu face_frac
            r.cls = classify_shot(r.face_frac, r.extent, args.close_frac, args.chest_frac, args.waist_extent)
            n_hit += 1
        else:
            r = analyze(p, faces, persons, meta, args, embedder, ref_emb)
            fresh[ck] = row_to_cache(r)
        if r.name in skip and not r.reason:
            r.reason = "skip_list"
        if not r.reason:
            r.reason = gates(r, args)
        if not r.reason:
            r.score = score(r, args)
        rows.append(r)
        if i % 25 == 0 or i == len(files):
            print(f"  {i}/{len(files)}  dat {sum(1 for x in rows if not x.reason)}", flush=True)
    if fresh and not args.no_cache:
        cache.update(fresh)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if n_hit:
        print(f"  (dung lai so do cua {n_hit} anh tu cache)")

    ok = [r for r in rows if not r.reason]
    kept = dedupe(ok, args)
    print(f"qua cong chat luong: {len(ok)} · sau loc trung: {len(kept)}")

    if not args.no_look and kept:
        body = BodyEmbedder(device=args.device)
        n_clip = 0
        for r in kept:
            img = read_image(r.path)
            if img is not None:
                r.clip = body.embed(img)
                n_clip += 1
        print(f"clip: {n_clip}/{len(kept)} anh")

    chosen = [] if args.analyze_only else (
        max_fill_select(kept, args) if args.workflow == "max-fill" else select(kept, args))
    variants: list[Row] = []
    if not args.analyze_only and args.workflow == "max-fill":
        print("workflow max-fill: chi dung anh goc, khong tu cat them")
    elif not args.analyze_only and args.face_crops:
        variants = mine_variants(rows, faces, embedder, ref_emb, args)
        variants = dedupe(variants, args)      # nhiều ảnh gốc cùng một tư thế -> 1 khung
        for i, v in enumerate(variants, 1):
            v.rank = i
        chosen, variants = assemble(chosen, variants, args)
        print(f"tu cat duoc {len(variants)} anh can mat (sau loc trung + han muc)")
    rows_sorted = sorted(rows, key=lambda r: (not r.accepted, -r.score, r.name))
    write_csv(report_dir / "filter_report.csv", rows_sorted)

    if args.analyze_only:
        print_distribution(rows)
        print(f"analyze-only: da ghi {report_dir / 'filter_report.csv'}")
        return 0

    dst.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for p in dst.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXT:
                p.unlink()
    for r in chosen:
        if args.convert_nonjpeg and r.path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            img = read_image(r.path)               # spec: chỉ JPEG hoặc PNG
            out = dst / (r.path.stem + ".jpg")
            if img is not None and write_image(out, img, quality=95):
                continue
        shutil.copy2(r.path, dst / r.name)

    extra_faces: list[Row] = []
    for v in variants:
        if write_variant(v, dst, args):
            v.path = dst / v.name      # sheet doc tu file da ghi
            extra_faces.append(v)
    if extra_faces:
        print(f"tu cat them {len(extra_faces)} anh can mat")

    sheets = make_sheets(chosen, report_dir, "sheet_flter")
    if extra_faces:
        sheets += make_sheets(extra_faces, report_dir, "sheet_facecrop")
    write_summary(report_dir / "filter_summary.txt", rows, chosen, args, len(files),
                  time.time() - t0, sheets, len(extra_faces))
    print(f"da chep {len(chosen)} anh -> {dst}")
    print(f"bao cao: {report_dir / 'filter_summary.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
