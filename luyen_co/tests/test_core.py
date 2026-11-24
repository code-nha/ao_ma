"""Test nhanh các phần logic thuần (không cần model/GPU): chạy `pytest` trong luyen_co/."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from core.select import (coverage_pick, dedupe, diverse_gate, drop_similar, face_vis,
                         head_pose, keep_best_body_tracks, pick_diverse, pose_vector,
                         yaw_bucket, yaw_histogram)
from core.tracker import IoUTracker
from core.types import Candidate
from core.utils import expand_box, letterbox, nms, others_area_fraction


def make_cand(t=0.0, track=1, clip=None, source="a.mp4", yaw=0.0, blur=100.0, h=200,
              body=0.85):
    return Candidate(
        source=source, kind="video", t=t, frame_idx=int(t * 10), track_id=track,
        box=np.array([10, 20, 110, 220], np.float32), person_score=0.9,
        face_sim=0.9, body_sim=body, yaw=yaw, pitch=0.0, blur=blur, person_h=h,
        jpeg=b"x", clip_vec=(np.array(clip, np.float32) if clip is not None else None),
        pose_vec=np.zeros(34, np.float32),
    )


def make_kpts(nose=0.99, span=0.5, shoulder_conf=0.99, eye=None, ear=0.9):
    """17 keypoint COCO giả trong bbox rộng 100px.

    `span`: bề rộng vai/hông theo tỉ lệ bbox — người nhìn thẳng/quay lưng ~0.5,
    nhìn ngang (vai chồng nhau) ~0.05.
    `eye`: conf 2 mắt — mặc định đi theo `nose`, vì khi người quay lưng YOLO mất
    cả mũi lẫn mắt; đặt riêng để test ca mũi còn cao nhưng mắt đã khuất.
    """
    kp = np.zeros((17, 3), np.float32)
    kp[:, 2] = 0.9
    eye_c = nose if eye is None else eye
    half = 100.0 * span / 2.0
    cx = 60.0
    kp[0] = [cx, 40.0, nose]                      # mũi: conf thấp = quay lưng
    kp[1] = [cx - 8, 30.0, eye_c]                 # mắt trái
    kp[2] = [cx + 8, 30.0, eye_c]                 # mắt phải
    kp[3] = [cx - 15, 32.0, ear]                  # tai trái
    kp[4] = [cx + 15, 32.0, ear]                  # tai phải
    kp[5] = [cx - half, 60.0, shoulder_conf]      # vai trái
    kp[6] = [cx + half, 60.0, shoulder_conf]      # vai phải
    kp[11] = [cx - half, 150.0, 0.9]              # hông trái
    kp[12] = [cx + half, 150.0, 0.9]              # hông phải
    return kp


def test_letterbox_keeps_aspect_and_pads():
    img = np.zeros((200, 400, 3), np.uint8)
    out, ratio, left, top = letterbox(img, 640)
    assert out.shape == (640, 640, 3)
    assert abs(ratio - 640 / 400) < 1e-6
    assert left == 0 and top > 0


def test_nms_suppresses_overlap():
    boxes = np.array([[0, 0, 100, 100], [5, 5, 100, 100], [300, 300, 400, 400]], np.float32)
    scores = np.array([0.9, 0.8, 0.7], np.float32)
    keep = nms(boxes, scores, 0.5)
    assert list(keep) == [0, 2]


def test_expand_box_clipped():
    box = expand_box(np.array([10, 10, 50, 50], np.float32), 0.5, 100, 100)
    assert box[0] >= 0 and box[1] >= 0
    assert box[2] <= 99 and box[3] <= 99
    assert box[0] < 10 and box[2] > 50


def test_others_area_fraction():
    crop = np.array([0, 0, 100, 100], np.float32)
    assert others_area_fraction(crop, []) == 0.0
    assert abs(others_area_fraction(crop, [np.array([0, 0, 50, 100], np.float32)]) - 0.5) < 1e-6
    assert others_area_fraction(crop, [np.array([200, 200, 300, 300], np.float32)]) == 0.0
    # nhiều người chồng nhau không vượt quá 1
    two = [np.array([0, 0, 100, 100], np.float32)] * 2
    assert others_area_fraction(crop, two) == 1.0


FRONTAL = np.array([[38.29, 51.70], [73.53, 51.50], [56.03, 71.74],
                    [41.55, 92.37], [70.73, 92.20]], np.float32)


def test_head_pose_frontal_and_turned():
    yaw, pitch = head_pose(FRONTAL)
    assert abs(yaw) < 3
    assert abs(pitch) < 3
    turned = FRONTAL.copy()
    turned[2, 0] += 8
    yaw_t, _ = head_pose(turned)
    assert yaw_t > 20


def test_pose_vector_missing_keypoints():
    vec = pose_vector(None, np.array([0, 0, 100, 200], np.float32))
    assert vec.shape == (34,) and np.allclose(vec, 0.5)


def test_dedupe_min_gap_and_similarity():
    same = [1.0] + [0.0] * 7
    a = make_cand(t=0.0, clip=same)
    b = make_cand(t=0.1, clip=same)          # quá sát thời gian
    c = make_cand(t=5.0, clip=same)          # ngoại hình y hệt
    d = make_cand(t=5.1, clip=[0.0, 1.0] + [0.0] * 6)  # khác hẳn
    kept = dedupe([a, b, c, d], dup_sim=0.97, min_gap=0.35)
    assert [k.t for k in kept] == [0.0, 5.1]


def test_dedupe_only_within_source():
    same = [1.0] + [0.0] * 7
    a = make_cand(t=0.0, source="a.mp4", clip=same)
    b = make_cand(t=0.0, source="b.mp4", clip=same)
    assert len(dedupe([a, b])) == 2


def test_tracker_keeps_id_and_expires():
    tr = IoUTracker(max_age=1)
    box = np.array([[0, 0, 50, 100]], np.float32)
    assert tr.update(box) == [1]
    assert tr.update(box) == [1]
    tr.update(np.empty((0, 4), np.float32))
    tr.update(np.empty((0, 4), np.float32))
    assert 1 in tr.stale()
    tr.drop(1)
    assert tr.update(box) == [2]


def test_tile_slices_cover_frame():
    from core.yolo_pose import PersonDetector

    det = PersonDetector.__new__(PersonDetector)     # không load model
    det.tiles = 3
    slices = det._tile_slices(1080, 1920)
    assert len(slices) == 9
    for y1, y2, x1, x2 in slices:
        assert 0 <= y1 < y2 <= 1080
        assert 0 <= x1 < x2 <= 1920
    # phủ hết 4 góc
    corners = {(0, 0), (0, 1920), (1080, 0), (1080, 1920)}
    covered = set()
    for y1, y2, x1, x2 in slices:
        for cy in (y1, y2):
            for cx in (x1, x2):
                if (cy, cx) in corners:
                    covered.add((cy, cx))
    assert covered == corners


def test_diverse_gate_drops_same_pose_keeps_other_angle():
    a = make_cand(t=0.0, yaw=0.0)
    b = make_cand(t=1.0, yaw=5.0)          # cùng dáng, góc lệch < 20° → bỏ
    c = make_cand(t=2.0, yaw=35.0)         # góc lệch đủ → giữ
    kept = diverse_gate([a, b, c], min_yaw=20.0, min_pose=0.15)
    assert [k.t for k in kept] == [0.0, 2.0]


def test_diverse_gate_keeps_different_body_pose():
    a = make_cand(t=0.0, yaw=0.0)
    b = make_cand(t=1.0, yaw=0.0)
    b.pose_vec = np.ones(34, np.float32)   # dáng khác hẳn
    kept = diverse_gate([a, b], min_yaw=20.0, min_pose=0.15)
    assert len(kept) == 2


def test_yaw_bucket_and_coverage():
    front = make_cand(t=0.0, yaw=0.0)
    left = make_cand(t=1.0, yaw=-40.0)
    right = make_cand(t=2.0, yaw=50.0)
    back = make_cand(t=3.0, yaw=0.0)
    back.face_sim = -1.0                      # không thấy mặt
    back.kpts = make_kpts(nose=0.3)           # mũi khuất → quay lưng
    assert yaw_bucket(front) == "thẳng"
    assert yaw_bucket(left) == "trái nhiều"
    assert yaw_bucket(right) == "phải nhiều"
    assert yaw_bucket(back) == "sau lưng"

    picked = coverage_pick([front, left, right, back], per_bucket=1)
    # mỗi nhóm góc còn 1 ảnh, gồm cả ảnh sau lưng
    assert len(picked) == 4
    assert back in picked


def test_yaw_bucket_tach_sau_lung_nghieng_va_khong_ro_mat():
    back = make_cand(t=0.0)
    back.face_sim = -1.0
    back.kpts = make_kpts(nose=0.3)                 # mũi khuất, vai mở rộng
    side = make_cand(t=1.0)
    side.face_sim = -1.0
    side.kpts = make_kpts(nose=0.95, span=0.05)     # vai chồng nhau → nhìn ngang
    far = make_cand(t=2.0)
    far.face_sim = -1.0
    far.kpts = make_kpts(nose=0.95, span=0.5)       # nhìn thẳng nhưng xa/không thấy mặt
    assert yaw_bucket(back) == "sau lưng"
    assert yaw_bucket(side) == "nghiêng"
    assert yaw_bucket(far) == "không rõ mặt"


def test_yaw_qua_90_do_la_nhom_nghieng():
    c = make_cand(t=0.0, yaw=-90.0)
    c.kpts = make_kpts(nose=0.95, span=0.05)
    assert yaw_bucket(c) == "nghiêng"


def test_sau_lung_khi_mui_con_cao_nhung_mat_khuat():
    # Đo thật trên v1.mp4: frame 25.5 s (đang đi, quay lưng) có mũi 0.58 nhưng
    # mắt chỉ 0.36 → cách cũ (chỉ so mũi < 0.5) xếp nhầm sang "không rõ mặt".
    c = make_cand(t=0.0)
    c.face_sim = -1.0
    c.kpts = make_kpts(nose=0.58, eye=0.36)
    assert face_vis(c) < 0.6
    assert yaw_bucket(c) == "sau lưng"


def test_nhin_thang_o_xa_khong_bi_goi_sau_lung():
    c = make_cand(t=0.0, h=650)
    c.face_sim = -1.0
    c.kpts = make_kpts(nose=0.97, eye=0.89)      # SCRFD không thấy mặt nhưng mũi+mắt rõ
    assert yaw_bucket(c) == "không rõ mặt"


def test_khong_ket_luan_sau_lung_khi_thieu_tai_hoac_vai():
    thieu_tai = make_cand(t=0.0)
    thieu_tai.face_sim = -1.0
    thieu_tai.kpts = make_kpts(nose=0.3, ear=0.05)       # keypoint đầu không đáng tin
    assert yaw_bucket(thieu_tai) == "không rõ mặt"
    thieu_vai = make_cand(t=1.0)
    thieu_vai.face_sim = -1.0
    thieu_vai.kpts = make_kpts(nose=0.3, shoulder_conf=0.2)
    assert yaw_bucket(thieu_vai) == "không rõ mặt"


def test_keep_best_body_tracks_giu_track_tot_nhat():
    # Ca clip chỉ quay lưng: không track nào khớp mặt, body_sim của người mục
    # tiêu 0.60–0.62 còn người đi đường 0.37–0.45 → phải giữ track 1, bỏ track 2.
    good = [make_cand(t=float(i), track=1, body=b) for i, b in enumerate((0.60, 0.62, 0.59))]
    other = [make_cand(t=float(i), track=2, body=b) for i, b in enumerate((0.37, 0.45, 0.40))]
    kept, th = keep_best_body_tracks(good + other, low=0.45, rel=0.85)
    assert {c.track_id for c in kept} == {1}
    assert abs(th - 0.85 * 0.60) < 1e-6


def test_keep_best_body_tracks_ton_trong_san():
    cands = [make_cand(t=0.0, track=1, body=0.50), make_cand(t=1.0, track=2, body=0.30)]
    kept, th = keep_best_body_tracks(cands, low=0.48, rel=0.85)
    assert th == 0.48                              # 0.85 × 0.50 = 0.425 < sàn
    assert [c.track_id for c in kept] == [1]


def test_coverage_giu_ca_anh_sau_lung_lan_nguoi_o_xa():
    # Lỗi cũ: frame nhìn thẳng ở xa (mặt không detect được) và frame quay lưng
    # cùng bị gom vào "sau lưng", ảnh xa thắng nên mất hẳn ảnh quay lưng.
    far_front = make_cand(t=11.5, h=280)
    far_front.face_sim = -1.0
    far_front.kpts = make_kpts(nose=0.97, span=0.5)
    back = make_cand(t=18.0, h=620)
    back.face_sim = -1.0
    back.kpts = make_kpts(nose=0.3)
    picked = coverage_pick([far_front, back], per_bucket=1)
    assert back in picked and far_front in picked


def test_nhom_sau_lung_chon_nguoi_to_hon():
    far_back = make_cand(t=18.0, h=300, blur=900.0)
    far_back.face_sim = -1.0
    far_back.kpts = make_kpts(nose=0.3)
    far_back.body_sim = 0.80                    # CLIP khớp cao hơn
    near_back = make_cand(t=21.0, h=650, blur=300.0)
    near_back.face_sim = -1.0
    near_back.kpts = make_kpts(nose=0.3)
    near_back.body_sim = 0.60
    assert coverage_pick([far_back, near_back], per_bucket=1) == [near_back]


def test_yaw_histogram_dem_theo_nhom_goc():
    front = make_cand(t=0.0, yaw=0.0)
    back = make_cand(t=1.0)
    back.face_sim = -1.0
    back.kpts = make_kpts(nose=0.3)
    hist = dict(yaw_histogram([front, back]))
    assert hist["thẳng"] == 1
    assert hist["sau lưng"] == 1


def test_drop_similar_chi_trong_cung_nguon_va_cung_nhom():
    same = [1.0] + [0.0] * 7
    front_a = make_cand(t=0.0, source="a.mp4", clip=same, yaw=0.0)
    front_b = make_cand(t=1.0, source="a.mp4", clip=same, yaw=0.0)
    other_src = make_cand(t=0.0, source="b.mp4", clip=same, yaw=0.0)
    back = make_cand(t=2.0, source="a.mp4", clip=same)
    back.face_sim = -1.0
    back.kpts = make_kpts(nose=0.3)
    kept = drop_similar([front_a, front_b, other_src, back], th=0.93)
    assert front_b not in kept            # cùng nguồn + cùng nhóm "thẳng" → bỏ
    assert front_a in kept
    assert other_src in kept              # khác nguồn → không so
    assert back in kept                   # khác nhóm "sau lưng" → không bị ảnh mặt xoá


def test_pick_diverse_returns_distinct():
    import math

    cands = []
    for i in range(10):
        ang = i * 0.3
        clip = [math.cos(ang), math.sin(ang)] + [0.0] * 6
        cands.append(make_cand(t=float(i), clip=clip, yaw=float(i * 10)))
    picked = pick_diverse(cands, 4)
    assert len(picked) == 4
    assert len({c.t for c in picked}) == 4
