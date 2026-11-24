"""Test nhanh các phần logic thuần (không cần model/GPU): chạy `pytest` trong luyen_co/."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from core.select import (coverage_pick, dedupe, distinct_pose_pick, diverse_gate, drop_bad_frames,
                         drop_blurry_faces,
                         drop_similar, face_vis,
                         head_pose, keep_best_body_tracks, pick_diverse, pose_angle_dist,
                         pose_angles, pose_vector,
                         shot_coverage_pick, shot_histogram, shot_scale,
                         yaw_bucket, yaw_histogram)
from core.tracker import IoUTracker
from core.types import Candidate
from core.utils import expand_box, letterbox, nms, others_area_fraction


def make_cand(t=0.0, track=1, clip=None, source="a.mp4", yaw=0.0, blur=100.0, h=200,
              body=0.85, pose=None, face=0.9, face_px=0, src_h=1280, face_blur=0.0):
    return Candidate(
        source=source, kind="video", t=t, frame_idx=int(t * 10), track_id=track,
        box=np.array([10, 20, 110, 220], np.float32), person_score=0.9,
        face_sim=face, body_sim=body, yaw=yaw, pitch=0.0, blur=blur, person_h=h,
        jpeg=b"x", clip_vec=(np.array(clip, np.float32) if clip is not None else None),
        pose_vec=(np.zeros(34, np.float32) if pose is None else np.array(pose, np.float32)),
        face_px=face_px, src_h=src_h, face_blur=face_blur,
    )


def make_kpts(nose=0.99, span=0.5, shoulder_conf=0.99, eye=None, ear=0.9, feet=0.9):
    """17 keypoint COCO giả trong bbox rộng 100px.

    `span`: bề rộng vai/hông theo tỉ lệ bbox — người nhìn thẳng/quay lưng ~0.5,
    nhìn ngang (vai chồng nhau) ~0.05.
    `eye`: conf 2 mắt — mặc định đi theo `nose`, vì khi người quay lưng YOLO mất
    cả mũi lẫn mắt; đặt riêng để test ca mũi còn cao nhưng mắt đã khuất.
    `feet`: conf cổ chân — dùng để test nhãn "toàn thân" (thấy bàn chân).
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
    kp[7] = [cx - half - 4, 110.0, 0.9]           # khuỷu trái
    kp[8] = [cx + half + 4, 110.0, 0.9]           # khuỷu phải
    kp[9] = [cx - half - 6, 150.0, 0.9]           # cổ tay trái
    kp[10] = [cx + half + 6, 150.0, 0.9]          # cổ tay phải
    kp[11] = [cx - half, 150.0, 0.9]              # hông trái
    kp[12] = [cx + half, 150.0, 0.9]              # hông phải
    kp[13] = [cx - half * 0.9, 200.0, 0.9]        # gối trái
    kp[14] = [cx + half * 0.9, 200.0, 0.9]        # gối phải
    kp[15] = [cx - 8, 240.0, feet]                # cổ chân trái
    kp[16] = [cx + 8, 240.0, feet]                # cổ chân phải
    return kp


def mirror_kpts(kp, cx=60.0):
    """Lật gương bộ keypoint: đổi trái↔phải và lật trục x."""
    out = kp.copy()
    for i, j in ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)):
        out[i], out[j] = kp[j], kp[i]
    out[:, 0] = 2 * cx - out[:, 0]
    return out


def make_kpts_arm_up():
    """Dáng không đối xứng: tay trái giơ thẳng lên (để test gương / một chi đổi)."""
    kp = make_kpts()
    kp[7] = [35.0, 10.0, 0.9]        # khuỷu trái
    kp[9] = [35.0, -40.0, 0.9]       # cổ tay trái
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


def _pose(base=0.5, delta=0.0):
    return np.full(34, base + delta, np.float32)


def test_distinct_pose_pick_khong_noi_chuoi_frame():
    # Chuỗi A≈B (15°), B≈C (13°), A cách C 28°. Nối chuỗi (union-find) sẽ gộp cả
    # 3 → 1 ảnh; duyệt tham lam giữ A và C vì A khác C đủ rõ. Đây là lý do clip
    # quay bằng điện thoại (dáng đổi dần) trước chỉ ra 6 ảnh, giờ ra 17.
    a = make_cand(t=0.0, yaw=0.0, pose=_pose())
    b = make_cand(t=1.0, yaw=15.0, pose=_pose(delta=0.01))
    c = make_cand(t=2.0, yaw=28.0, pose=_pose(delta=0.02))
    kept = distinct_pose_pick([a, b, c], min_yaw=25.0, min_pose=0.08)
    assert len(kept) == 2
    assert {k.t for k in kept} == {0.0, 2.0}


def test_distinct_pose_pick_giu_anh_chat_luong_nhat():
    # Cùng cụm: ảnh mặt nét hơn (face_sim cao) phải được giữ, không phải ảnh đầu.
    low = make_cand(t=0.0, yaw=0.0, pose=_pose(), face=0.42)
    high = make_cand(t=1.0, yaw=5.0, pose=_pose(delta=0.01), face=0.71)
    kept = distinct_pose_pick([low, high], min_yaw=25.0, min_pose=0.08)
    assert kept == [high]


def test_distinct_pose_pick_giu_khi_khac_goc_hoac_khac_dang():
    same_pose_other_angle = make_cand(t=1.0, yaw=60.0, pose=_pose())
    same_angle_other_pose = make_cand(t=2.0, yaw=0.0, pose=_pose(delta=0.3))
    base = make_cand(t=0.0, yaw=0.0, pose=_pose())
    kept = distinct_pose_pick([base, same_pose_other_angle, same_angle_other_pose],
                              min_yaw=25.0, min_pose=0.08)
    assert len(kept) == 3


def test_distinct_pose_pick_khong_gop_khac_nguon():
    a = make_cand(t=0.0, source="a.mp4", pose=_pose())
    b = make_cand(t=0.0, source="b.mp4", pose=_pose())
    kept = distinct_pose_pick([a, b], min_yaw=25.0, min_pose=0.08)
    assert len(kept) == 2


def test_yaw_dist_bo_pitch_khi_goc_cuc_tri():
    # |yaw| ≥ 70: pitch là nhiễu (bị kẹp ±89) nên không được làm 2 frame cùng
    # dáng dựa tường thành "khác góc".
    a = make_cand(t=0.0, yaw=-90.0, pose=_pose())
    b = make_cand(t=1.0, yaw=-90.0, pose=_pose(delta=0.01))
    a.pitch, b.pitch = 89.0, 48.0
    a.kpts = make_kpts(nose=0.95, span=0.05)
    b.kpts = make_kpts(nose=0.95, span=0.05)
    assert yaw_bucket(a) == yaw_bucket(b) == "nghiêng"
    kept = distinct_pose_pick([a, b], min_yaw=25.0, min_pose=0.08)
    assert len(kept) == 1


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


# ------------------------------------------------------------------- cỡ cảnh
def test_yaw_bucket_tach_sau_lung_3_4():
    # Mặt khuất một nửa (mũi 0.55, mắt 0.50 → face_vis ≈ 0.52) là 3/4 sau,
    # khác hẳn chính sau (mũi 0.3 → face_vis 0.40) mà nhóm cũ gộp làm một.
    c = make_cand(t=0.0)
    c.face_sim = -1.0
    c.kpts = make_kpts(nose=0.55, eye=0.50)
    assert 0.50 <= face_vis(c) < 0.60
    assert yaw_bucket(c) == "sau lưng 3/4"


def test_shot_scale_dem_so_dau_trong_khung():
    # Ngưỡng hiệu chỉnh trên obj_1: số "đầu" = person_h / face_px
    assert shot_scale(make_cand(h=1080, face_px=432)) == "cận cảnh"      # 2.5 đầu
    assert shot_scale(make_cand(h=1135, face_px=366)) == "trung cận"     # 3.1 đầu
    assert shot_scale(make_cand(h=898, face_px=187)) == "trung cảnh"     # 4.8 đầu
    assert shot_scale(make_cand(h=762, face_px=99)) == "toàn thân"       # 7.7 đầu
    assert shot_scale(make_cand(h=294, face_px=28)) == "viễn cảnh"       # 10.5 đầu
    # dưới 1.6 đầu = đặc tả (mặt chiếm gần nửa khung)
    assert shot_scale(make_cand(h=1000, face_px=800)) == "đặc tả"


def test_shot_scale_thay_ban_chan_thi_la_toan_than():
    # Người chiếm 60% khung và thấy cổ chân → cả người trong khung: toàn thân,
    # dù đếm đầu (2.5) sẽ xếp nhầm thành cận cảnh.
    c = make_cand(h=768, face_px=300)
    c.kpts = make_kpts(feet=0.8)
    assert shot_scale(c) == "toàn thân"
    # cùng tỉ lệ nhưng người rất bé trong khung → viễn cảnh
    far = make_cand(h=200, face_px=80)
    far.kpts = make_kpts()
    assert shot_scale(far) == "viễn cảnh"


def test_shot_scale_khong_thay_mat_thi_doan_theo_than():
    near = make_cand(h=1200, face_px=0)          # kín khung → trung cận
    near.kpts = make_kpts(feet=0.1)
    assert shot_scale(near) == "trung cận"
    mid = make_cand(h=700, face_px=0)            # 55% khung → trung cảnh
    mid.kpts = make_kpts(feet=0.1)
    assert shot_scale(mid) == "trung cảnh"
    low = make_cand(h=400, face_px=0)            # 31% khung → toàn thân
    low.kpts = make_kpts(feet=0.1)
    assert shot_scale(low) == "toàn thân"
    tiny = make_cand(h=200, face_px=0)           # 16% khung → viễn cảnh
    tiny.kpts = make_kpts(feet=0.1)
    assert shot_scale(tiny) == "viễn cảnh"


def test_shot_histogram_du_6_muc_theo_thu_tu():
    hist = shot_histogram([make_cand(h=1000, face_px=800)])
    assert [label for label, _ in hist] == ["đặc tả", "cận cảnh", "trung cận",
                                            "trung cảnh", "toàn thân", "viễn cảnh"]
    assert dict(hist)["đặc tả"] == 1


def test_shot_coverage_pick_chan_moi_o_goc_x_co():
    # 3 ảnh cùng nhóm góc "thẳng" và cùng cỡ cảnh trung cảnh + 1 ảnh viễn cảnh:
    # không giới hạn thì giữ cả 4, giới hạn 1/ô thì mỗi ô còn 1.
    ms = [make_cand(t=float(i), h=800, blur=100.0 + i) for i in range(3)]
    far = make_cand(t=9.0, h=200, blur=50.0)
    far.kpts = make_kpts()
    cands = ms + [far]
    assert len(shot_coverage_pick(cands, per_cell=0)) == 4      # 0 = tắt
    kept = shot_coverage_pick(cands, per_cell=1)
    assert far in kept
    assert len(kept) == 2
    # trong ô trung cảnh giữ ảnh nét nhất (blur 102), không phải ảnh đầu danh sách
    assert [c for c in kept if shot_scale(c) == "trung cảnh"] == [ms[2]]


# --------------------------------------------------------------- góc khớp pose
def test_pose_angles_11_goc_va_khop_khuat_bi_nan():
    c = make_cand(h=400)
    c.kpts = make_kpts()
    ang = pose_angles(c)
    assert ang is not None and len(ang) == 11
    assert not np.isnan(ang).any()          # đủ keypoint → đo được hết
    # che cổ tay trái (conf thấp) → chỉ góc khuỷu trái mất, các góc khác vẫn còn
    kp = make_kpts()
    kp[9, 2] = 0.1
    c.kpts = kp
    ang = pose_angles(c)
    assert ang is not None
    assert np.isnan(ang[0]) and not np.isnan(ang[1])


def test_pose_angle_khong_phu_thuoc_co_canh():
    # Cùng một dáng, người to gấp đôi trong khung → góc khớp phải y hệt.
    small = make_cand(h=400)
    small.kpts = make_kpts()
    big = make_cand(h=800)
    big.kpts = (make_kpts() * np.array([2.0, 2.0, 1.0], np.float32))
    d = pose_angle_dist(small, big)
    assert d is not None and d[0] < 1e-3 and d[1] < 1e-3


def test_pose_angle_giong_nhau_giua_hai_anh():
    a = make_cand(t=0.0, h=400)
    a.kpts = make_kpts()
    b = make_cand(t=1.0, h=400)
    b.kpts = make_kpts()
    d = pose_angle_dist(a, b)
    assert d is not None and d[0] < 1e-3


def test_pose_angle_giong_nhau_khi_lat_guong():
    # Dáng tay trái giơ lên và bản gương (tay phải giơ lên) = cùng dáng → lệch ~0.
    a = make_cand(t=0.0, h=400)
    a.kpts = make_kpts_arm_up()
    b = make_cand(t=1.0, h=400)
    b.kpts = mirror_kpts(make_kpts_arm_up())
    d = pose_angle_dist(a, b)
    assert d is not None and d[0] < 1.0 and d[1] < 1.0
    # nếu không xét gương thì hai ảnh này khác nhau rõ rệt (cùng khớp, khác bên)
    va, vb = pose_angles(a), pose_angles(b)
    assert np.nanmax(np.abs(va - vb)) > 20


def test_pose_angle_bat_mot_tay_gio_len():
    a = make_cand(t=0.0, h=400, face_px=64)
    a.kpts = make_kpts()
    b = make_cand(t=1.0, h=400, face_px=64)
    b.kpts = make_kpts_arm_up()
    mean, mx = pose_angle_dist(a, b)
    assert mean < 20 and mx >= 45
    assert len(distinct_pose_pick([a, b], min_yaw=25.0, min_pose=0.08)) == 2


def test_bbox_nhieu_khong_pha_vo_ket_luan_cung_dang():
    # Cùng keypoint (cùng dáng) nhưng pose_vec lệch hẳn — mô phỏng đúng lỗi bbox
    # đổi khi giơ tay làm toạ độ chuẩn hoá bị nén. Tầng góc khớp là chính nên vẫn
    # phải gộp, không được giữ cả hai.
    a = make_cand(t=0.0, h=400)
    a.kpts = make_kpts()
    b = make_cand(t=1.0, h=400)
    b.kpts = make_kpts()
    b.pose_vec = np.full(34, 0.5, np.float32)
    assert len(distinct_pose_pick([a, b], min_yaw=25.0, min_pose=0.08)) == 1


def test_khac_co_canh_thi_khong_bi_coi_la_trung():
    # Cùng dáng, cùng góc, nhưng một ảnh toàn thân một ảnh viễn cảnh → 2 ảnh khác
    # nhau về cỡ cảnh nên phải giữ cả hai (3 trục đo độc lập).
    near = make_cand(t=0.0, h=1200)
    near.kpts = make_kpts(feet=0.9)
    far = make_cand(t=6.0, h=300)
    far.kpts = make_kpts(feet=0.9)
    assert shot_scale(near) == "toàn thân" and shot_scale(far) == "viễn cảnh"
    assert len(distinct_pose_pick([near, far], min_yaw=25.0, min_pose=0.08)) == 2
    # còn cùng cỡ cảnh + cùng dáng + cùng góc thì chỉ giữ 1
    twin = make_cand(t=6.0, h=1200)
    twin.kpts = make_kpts(feet=0.9)
    assert len(distinct_pose_pick([near, twin], min_yaw=25.0, min_pose=0.08)) == 1


def test_drop_blurry_faces_bo_frame_chong_mo():
    # Đo thật trên clip 1750183430: frame chuyển cảnh chồng mờ có Laplacian vùng
    # mặt 23, các frame sạch cùng cảnh 90–161 → phải bị bỏ, frame sạch giữ lại.
    blur = [100.3, 131.2, 120.4, 23.3, 90.3, 161.4, 157.9]
    cands = [make_cand(t=float(i), face_px=90, face_blur=v) for i, v in enumerate(blur)]
    kept = drop_blurry_faces(cands, ratio=0.35)
    assert len(kept) == len(cands) - 1
    assert 23.3 not in [c.face_blur for c in kept]


def test_drop_blurry_faces_khong_bo_khi_ca_canh_deu_mo():
    # Cả cảnh đều mờ (clip nhòe sẵn) → không có "ảnh rõ hơn" để đổi, nên giữ nguyên
    cands = [make_cand(t=float(i), face_px=90, face_blur=20.0 + i) for i in range(4)]
    assert len(drop_blurry_faces(cands, ratio=0.35)) == 4


def test_drop_blurry_faces_bo_qua_frame_khong_co_mat():
    cands = [make_cand(t=0.0, face_px=0, face_blur=0.0),
             make_cand(t=1.0, face_px=90, face_blur=120.0),
             make_cand(t=2.0, face_px=90, face_blur=140.0)]
    assert len(drop_blurry_faces(cands, ratio=0.35)) == 3


def test_drop_bad_frames_ba_loai():
    # Dựng đúng số đo trên obj_1: 1 frame hiệu ứng lấp lánh, 1 frame mờ hẳn,
    # 1 frame cận cảnh mà mặt không khớp, còn lại là frame tốt.
    good = [make_cand(t=float(i), h=800, face_px=60, face_blur=150.0) for i in range(3)]
    for c in good:
        c.blur, c.spark, c.face_sim = 600.0, 0.005, 0.55
    spark = make_cand(t=9.0, h=800, face_px=60, face_blur=150.0)
    spark.blur, spark.spark, spark.face_sim = 600.0, 0.09, 0.55
    blurry = make_cand(t=10.0, h=800, face_px=60, face_blur=150.0)
    blurry.blur, blurry.spark, blurry.face_sim = 42.0, 0.005, 0.55
    closeup = make_cand(t=11.0, h=1200, face_px=500, face_blur=150.0)   # cận cảnh
    closeup.blur, closeup.spark, closeup.face_sim = 600.0, 0.005, 0.10
    assert shot_scale(closeup) == "cận cảnh"

    kept, why = drop_bad_frames(good + [spark, blurry, closeup], face_th=0.40)
    assert kept == good
    assert why == {"hiệu ứng lấp lánh": 1, "mờ hẳn so với cảnh": 1, "cận cảnh mặt hỏng": 1}


def test_drop_bad_frames_khong_bo_frame_tot():
    cands = [make_cand(t=float(i), h=800, face_px=60, face_blur=150.0) for i in range(4)]
    for c in cands:
        c.blur, c.spark, c.face_sim = 500.0 + c.t, 0.02 + c.t / 1000, 0.5
    kept, why = drop_bad_frames(cands, face_th=0.40)
    assert len(kept) == 4 and not any(why.values())


def test_cung_ben_va_giong_ngoai_hinh_thi_gop():
    # 4 ảnh MC đang nói (cùng váy, cùng bối cảnh, cùng cỡ cảnh) chỉ khác góc đầu
    # vài chục độ và dáng tay → CLIP 0.84+ nên phải gộp còn 1 (lỗi user báo).
    same = [1.0, 0.0, 0.0] + [0.0] * 5
    base = dict(h=900, face_px=200, blur=600.0, face_blur=150.0)
    a = make_cand(t=45.0, yaw=-90.0, clip=same, **base)
    b = make_cand(t=52.5, yaw=-90.0, clip=same, **base)
    c = make_cand(t=56.5, yaw=-25.3, clip=same, **base)
    assert len(distinct_pose_pick([a, b, c], min_yaw=25.0, min_pose=0.08)) == 1
    # cùng bên nhưng ngoại hình khác hẳn (CLIP thấp) → vẫn giữ cả hai
    other = [0.0, 1.0, 0.0] + [0.0] * 5
    d = make_cand(t=70.0, yaw=-40.0, clip=other, **base)
    assert len(distinct_pose_pick([a, d], min_yaw=25.0, min_pose=0.08)) == 2
    # khác bên quay (một trái một phải) thì không gộp theo luật này
    e = make_cand(t=80.0, yaw=+40.0, clip=same, **base)
    assert len(distinct_pose_pick([a, e], min_yaw=25.0, min_pose=0.08)) == 2


def test_chinh_dien_cung_ngoai_hinh_thi_gop():
    # 3 ảnh 67.0 / 68.0 / 68.5 s: yaw −12.4 / 2.7 / 0 → đều gần chính diện,
    # CLIP 0.953–0.966 → phải gộp còn 1.
    same = [1.0, 0.0, 0.0] + [0.0] * 5
    base = dict(h=900, face_px=200, blur=600.0, face_blur=150.0)
    a = make_cand(t=67.0, yaw=-12.4, clip=same, **base)
    b = make_cand(t=68.0, yaw=2.7, clip=same, **base)
    c = make_cand(t=68.5, yaw=0.0, clip=same, face=-1.0, **base)
    assert len(distinct_pose_pick([a, b, c], min_yaw=25.0, min_pose=0.08)) == 1
    # nhưng ảnh chính diện khác cỡ cảnh thì vẫn giữ (trục cỡ cảnh độc lập)
    twin = make_cand(t=90.0, yaw=3.0, clip=same, h=400, face_px=40, blur=600.0,
                     face_blur=150.0)
    assert shot_scale(twin) != shot_scale(a)
    assert len(distinct_pose_pick([a, twin], min_yaw=25.0, min_pose=0.08)) == 2


def test_cung_co_canh_khi_sat_bien_hai_muc():
    # 70.0 / 70.5 s: người chiếm 91% khung ở CẢ HAI, nhưng face_px 282 vs 330
    # → số đầu 4.11 vs 3.53 → nhãn trung cảnh vs trung cận. Framing thật như nhau
    # nên phải gộp (CLIP 0.934), không được tách vì nhãn khác.
    same = [1.0, 0.0, 0.0] + [0.0] * 5
    a = make_cand(t=70.0, yaw=-55.8, clip=same, h=1159, face_px=282, blur=100.0,
                  face_blur=240.0)
    b = make_cand(t=70.5, yaw=-68.9, clip=same, h=1166, face_px=330, blur=51.0,
                  face_blur=196.0)
    assert shot_scale(a) != shot_scale(b)          # nhãn khác nhau...
    assert len(distinct_pose_pick([a, b], min_yaw=25.0, min_pose=0.08)) == 1


def test_toan_than_khac_can_canh_du_cung_ty_le_khung():
    # Cùng chiếm 91% khung nhưng một ảnh thấy cổ chân (toàn thân), một ảnh không
    # (trung cảnh) → vẫn là hai cỡ cảnh khác nhau, phải giữ cả hai.
    same = [1.0, 0.0, 0.0] + [0.0] * 5
    full = make_cand(t=1.0, clip=same, h=1160, face_px=60, blur=600.0, face_blur=150.0)
    full.kpts = make_kpts(feet=0.9)
    waist = make_cand(t=2.0, clip=same, h=1160, face_px=330, blur=600.0, face_blur=150.0)
    waist.kpts = make_kpts(feet=0.1)
    assert len(distinct_pose_pick([full, waist], min_yaw=25.0, min_pose=0.08)) == 2


def test_goc_quay_khac_nhau_van_giu_du_cung_dang():
    # Cùng dáng nhưng đầu quay khác hẳn: góc khớp (không dùng mắt/mũi) coi là cùng
    # dáng, còn trục góc quay tách ra → giữ cả hai ảnh.
    a = make_cand(t=0.0, h=400, yaw=0.0)
    a.kpts = make_kpts()
    b = make_cand(t=1.0, h=400, yaw=-60.0)
    b.kpts = make_kpts()
    d = pose_angle_dist(a, b)
    assert d is not None and d[0] < 1.0          # dáng giống nhau
    assert len(distinct_pose_pick([a, b], min_yaw=25.0, min_pose=0.08)) == 2
