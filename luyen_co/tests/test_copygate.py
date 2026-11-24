"""Test cổng chặn ảnh trùng thật (SIFT + RANSAC) — chạy `pytest` trong luyen_co/.

Không cần model/GPU: ảnh kiểm thử được vẽ bằng OpenCV nên chạy được offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from core.copygate import _features, copy_score, copy_veto
from core.select import pose_angle_deltas
from core.types import Candidate


def _scene(seed: int, size: tuple[int, int] = (300, 400)) -> np.ndarray:
    """Ảnh tổng hợp có texture ổn định (khối màu + chấm tròn) để SIFT bám được."""
    rng = np.random.default_rng(seed)
    h, w = size
    img = np.full((h, w, 3), 240, np.uint8)
    for _ in range(45):
        x, y = int(rng.integers(5, w - 30)), int(rng.integers(5, h - 30))
        rw, rh = int(rng.integers(10, 60)), int(rng.integers(10, 60))
        col = tuple(int(v) for v in rng.integers(0, 220, 3))
        if rng.random() < 0.55:
            cv2.rectangle(img, (x, y), (x + rw, y + rh), col, -1)
        else:
            cv2.circle(img, (x, y), int(rng.integers(5, 22)), col, -1)
    return cv2.GaussianBlur(img, (3, 3), 0)


def _warp(img: np.ndarray, scale: float = 0.9, dx: int = 12, dy: int = 8) -> np.ndarray:
    """Bản "chụp lại" cùng cảnh: phóng nhẹ + dịch — mô phỏng hai frame gần nhau."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 0.0, scale)
    m[:, 2] += (dx, dy)
    return cv2.warpAffine(img, m, (w, h), borderValue=(240, 240, 240))


def _cand(img: np.ndarray, t: float = 0.0, source: str = "a.mp4",
          clip=None, h: int = 200) -> Candidate:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return Candidate(
        source=source, kind="video", t=t, frame_idx=int(t * 10), track_id=1,
        box=np.array([0, 0, img.shape[1], img.shape[0]], np.float32),
        person_score=0.9, face_sim=0.9, body_sim=0.9, yaw=0.0, pitch=0.0,
        blur=100.0, person_h=h, jpeg=buf.tobytes(),
        src_h=img.shape[0], src_w=img.shape[1],
        clip_vec=(np.array(clip, np.float32) if clip is not None else None),
    )


def test_copy_score_bat_hai_anh_cung_canh():
    a = _scene(1)
    b = _warp(a)
    inl, ratio = copy_score(_features(_cand(a)), _features(_cand(b, t=0.5)))
    assert inl >= 40, f"cùng cảnh phải khớp nhiều điểm, đo được {inl}"
    assert ratio >= 0.22, f"tỉ lệ inlier phải vượt ngưỡng, đo được {ratio:.3f}"


def test_copy_score_khong_bat_hai_canh_khac_nhau():
    a, c = _scene(1), _scene(999)
    inl, ratio = copy_score(_features(_cand(a)), _features(_cand(c, t=1.0)))
    assert inl < 25, f"hai cảnh khác nhau không được khớp, đo được {inl}"
    assert ratio < 0.15


def test_copy_veto_bo_anh_trung_giu_anh_khac():
    img_a = _scene(1)
    img_b = _warp(img_a, scale=0.88, dx=20, dy=14)
    img_c = _scene(999)
    cands = [_cand(img_a, t=0.0), _cand(img_b, t=0.5), _cand(img_c, t=1.0)]
    kept, removed = copy_veto(cands)
    assert len(removed) == 1, f"phải bỏ đúng 1 ảnh, bỏ {len(removed)}"
    assert len(kept) == 2
    assert 1.0 in {k.t for k in kept}, "ảnh cảnh khác phải được giữ"


def test_copy_veto_xuyen_nguon():
    a = _scene(7)
    b = _warp(a, scale=0.95, dx=6, dy=10)
    clip = [1.0, 0.0, 0.0]
    cands = [_cand(a, t=0.0, source="kenh_a.mp4", clip=clip),
             _cand(b, t=3.0, source="kenh_b.mp4", clip=clip)]
    kept, removed = copy_veto(cands)
    assert len(removed) == 1, "cùng một tấm ảnh ở hai nguồn phải bị bắt"
    assert len(kept) == 1


def test_copy_veto_khong_phu_thuoc_thu_tu():
    a = _scene(1)
    b = _warp(a, scale=0.9, dx=8, dy=6)
    c = _scene(999)
    d = _scene(1234)
    base = [_cand(a, t=0.0), _cand(b, t=0.5), _cand(c, t=1.0), _cand(d, t=1.5)]
    kept1, _ = copy_veto(base)
    kept2, _ = copy_veto(list(reversed(base)))
    assert sorted(k.t for k in kept1) == sorted(k.t for k in kept2)


def test_candidate_anh_hong_khong_lam_sap():
    bad = _cand(_scene(3))
    bad.jpeg = b"not a jpeg"
    inl, ratio = copy_score(_features(bad), _features(_cand(_scene(3))))
    assert (inl, ratio) == (0, 0.0)


def test_doc_duoc_anh_tu_file_tam(tmp_path):
    """Pipeline stage crop ra đĩa rồi xoá `jpeg` — cổng phải đọc lại được."""
    img = _scene(5)
    path = tmp_path / "crop.jpg"
    path.write_bytes(cv2.imencode(".jpg", img)[1].tobytes())
    staged = _cand(img, t=2.0)
    staged.jpeg = b""
    staged.staged = path
    inl, ratio = copy_score(_features(staged), _features(_cand(img)))
    assert inl >= 40, f"đọc từ file tạm phải khớp được, đo được {inl}"
    assert ratio >= 0.22


def _kpts(arm_raised: bool) -> np.ndarray:
    """17 keypoint COCO giả: tay buông thẳng vs tay nâng ngang vai."""
    k = np.zeros((17, 3), np.float32)
    k[:, 2] = 0.9
    base = {0: (100, 50), 1: (90, 45), 2: (110, 45), 3: (80, 50), 4: (120, 50),
            5: (80, 120), 6: (120, 120), 11: (85, 300), 12: (115, 300),
            13: (85, 400), 14: (115, 400), 15: (85, 500), 16: (115, 500)}
    for i, p in base.items():
        k[i, :2] = p
    if arm_raised:                       # tay phải nâng ngang → khuỷu/vai gần 90°
        k[7, :2], k[8, :2] = (55, 160), (30, 175)
        k[9, :2], k[10, :2] = (25, 150), (60, 120)
    else:                                # tay buông thẳng
        k[7, :2], k[8, :2] = (78, 210), (122, 210)
        k[9, :2], k[10, :2] = (76, 290), (124, 290)
    return k


def test_khac_dang_thi_khong_gop():
    """SIFT khớp được cả phông nền: cùng nền mà người đổi dáng thì không được gộp."""
    from core.copygate import _pose_disagrees

    img = _scene(2)
    a = _cand(img, t=0.0)
    b = _cand(img, t=4.0)
    a.kpts, b.kpts = _kpts(False), _kpts(True)
    assert _pose_disagrees(a, b, 12.0, 30.0), "tay buông vs tay nâng phải bị coi là khác dáng"
    c = _cand(img, t=5.0)
    c.kpts = _kpts(False)
    assert not _pose_disagrees(a, c, 12.0, 30.0), "cùng dáng thì phải cho gộp"


def test_thieu_keypoint_thi_de_sift_quyet():
    from core.copygate import _pose_disagrees

    img = _scene(4)
    a, b = _cand(img), _cand(img, t=1.0)
    assert not _pose_disagrees(a, b, 12.0, 30.0), "không đo được dáng thì không chặn"


def test_mot_khop_lech_khong_du_ket_luan_khac_dang():
    """Cặp 87/88 (cùng khung, cách 14 s): chỉ **một** khớp (khuỷu trái) lệch 114°,
    5 khớp còn lại lệch 3–17° (median 9.3). Đó là keypoint nhiễu của một cánh tay,
    không phải dáng khác — không được chặn việc gộp."""
    from core.copygate import _pose_disagrees

    img = _scene(6)
    a, b = _cand(img, t=46.5), _cand(img, t=60.5)
    a.kpts = _kpts(False)
    k = _kpts(False).copy()
    # Xoay CẲNG TAY TRÁI quanh khuỷu: chỉ góc khuỷu trái đổi, hướng cánh tay giữ nguyên
    k[9, :2] = (148.0, 230.0)
    b.kpts = k
    d = pose_angle_deltas(a, b)
    assert d is not None and d.max() > 60.0 and int((d > 30).sum()) == 1
    assert not _pose_disagrees(a, b, 12.0, 30.0)


def test_hai_khop_lech_tro_len_van_la_khac_dang():
    """Hai tay đổi (2 khớp lệch > 30°) là dáng khác thật -> vẫn phải chặn."""
    from core.copygate import _pose_disagrees

    img = _scene(7)
    a, b = _cand(img), _cand(img, t=1.0)
    a.kpts, b.kpts = _kpts(False), _kpts(True)
    assert _pose_disagrees(a, b, 12.0, 30.0)
