"""Test nhanh các phần logic thuần (không cần model/GPU): chạy `pytest` trong luyen_co/."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from core.select import dedupe, diverse_gate, head_pose, pick_diverse, pose_vector
from core.tracker import IoUTracker
from core.types import Candidate
from core.utils import expand_box, letterbox, nms, others_area_fraction


def make_cand(t=0.0, track=1, clip=None, source="a.mp4", yaw=0.0, blur=100.0, h=200):
    return Candidate(
        source=source, kind="video", t=t, frame_idx=int(t * 10), track_id=track,
        box=np.array([10, 20, 110, 220], np.float32), person_score=0.9,
        face_sim=0.9, body_sim=0.85, yaw=yaw, pitch=0.0, blur=blur, person_h=h,
        jpeg=b"x", clip_vec=(np.array(clip, np.float32) if clip is not None else None),
        pose_vec=np.zeros(34, np.float32),
    )


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
