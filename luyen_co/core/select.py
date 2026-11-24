"""Ước lượng góc đầu, vector pose, lọc trùng và chọn bộ frame đa dạng.

Góc đầu (yaw/pitch) tính từ 5 landmark của SCRFD — đủ để phân biệt "nhìn
thẳng / quay trái / quay phải / cúi / ngửa", không phải số đo chính xác.
Pose toàn thân dùng 17 keypoint COCO chuẩn hoá theo bbox.
"""

from __future__ import annotations

import math

import numpy as np

from .types import Candidate

# Template ArcFace 112×112: mắt trái, mắt phải, mũi, mép trái, mép phải
_EYE_DIST = 35.24
_NOSE_DY = 20.2


def head_pose(kps: np.ndarray | None) -> tuple[float, float]:
    """(yaw, pitch) độ, dương = quay sang phải / cúi xuống. Không có mặt → (0, 0)."""
    if kps is None or len(kps) < 5:
        return 0.0, 0.0
    eye_l, eye_r, nose, mouth_l, mouth_r = (np.asarray(p, dtype=np.float32) for p in kps[:5])
    eye_mid = (eye_l + eye_r) / 2.0
    mouth_mid = (mouth_l + mouth_r) / 2.0
    eye_d = float(np.linalg.norm(eye_r - eye_l))
    if eye_d < 1e-3:
        return 0.0, 0.0
    center_x = (eye_mid[0] + mouth_mid[0]) / 2.0
    # mũi lệch khỏi trục mặt theo phương ngang ~ 0.35 × khoảng cách 2 mắt
    ratio_x = (nose[0] - center_x) / (0.35 * eye_d)
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, ratio_x))))
    ratio_y = (nose[1] - eye_mid[1]) / eye_d
    pitch = (ratio_y - _NOSE_DY / _EYE_DIST) * 60.0
    return float(yaw), float(pitch)


def pose_vector(kpts: np.ndarray | None, box: np.ndarray) -> np.ndarray:
    """17 keypoint chuẩn hoá trong bbox → vector 34 chiều (0.5 nếu thiếu)."""
    out = np.full(34, 0.5, dtype=np.float32)
    if kpts is None:
        return out
    x1, y1, x2, y2 = box
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    kp = np.asarray(kpts, dtype=np.float32)
    xs = ((kp[:, 0] - x1) / w).clip(0, 1)
    ys = ((kp[:, 1] - y1) / h).clip(0, 1)
    conf = kp[:, 2]
    ok = conf > 0.2
    out[0::2] = np.where(ok, xs, 0.5)
    out[1::2] = np.where(ok, ys, 0.5)
    return out


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def diversity_features(cands: list[Candidate], pose_weight: float = 1.0,
                       clip_weight: float = 1.0) -> np.ndarray:
    """Ma trận đặc trưng để đo độ khác nhau: góc đầu + pose + ngoại hình."""
    feats = []
    for c in cands:
        head = _unit(np.array([c.yaw / 90.0, c.pitch / 60.0], dtype=np.float32))
        pose = _unit(c.pose_vec if c.pose_vec is not None else np.zeros(34, np.float32))
        clip = _unit(c.clip_vec) if c.clip_vec is not None else np.zeros(512, np.float32)
        feats.append(np.concatenate([head * 1.5, pose * pose_weight, clip * clip_weight]))
    return np.stack(feats) if feats else np.zeros((0, 0), np.float32)


def dedupe(cands: list[Candidate], dup_sim: float = 0.97, min_gap: float = 0.35) -> list[Candidate]:
    """Bỏ frame gần như trùng: sát thời gian trong cùng track, hoặc ngoại hình quá giống.

    So sánh ngoại hình bằng 1 phép nhân ma trận mỗi frame (BLAS) thay vì vòng
    lặp Python, để video CCTV vài chục nghìn frame vẫn chạy nhanh.
    """
    from collections import defaultdict

    by_source: dict[str, list[Candidate]] = defaultdict(list)
    for c in cands:
        by_source[c.source].append(c)

    kept: list[Candidate] = []
    for items in by_source.values():
        items.sort(key=lambda c: c.t)
        mat: np.ndarray | None = None
        last_t: dict[int, float] = {}
        for c in items:
            if c.track_id in last_t and abs(c.t - last_t[c.track_id]) < min_gap:
                continue
            similar = c.clip_vec is not None and mat is not None and \
                float((mat @ c.clip_vec).max()) >= dup_sim
            if similar:
                continue
            kept.append(c)
            last_t[c.track_id] = c.t
            if c.clip_vec is not None:
                mat = c.clip_vec[None].copy() if mat is None else np.vstack([mat, c.clip_vec[None]])

    kept.sort(key=lambda c: (c.source, c.t))
    return kept


def diverse_gate(cands: list[Candidate], min_yaw: float = 12.0,
                 min_pose: float = 0.08) -> list[Candidate]:
    """Chỉ giữ frame khác biệt đủ rõ so với các frame đã giữ (cùng nguồn).

    Một frame bị bỏ khi VỪA gần góc đầu VÀ gần dáng so với một frame đã giữ —
    tức là hai ảnh gần như cùng một tư thế. Thực tế chỉ cần vài ảnh khác nhau
    làm bằng chứng nhận dạng, không cần 20 ảnh cùng một pose.
    """
    if min_yaw <= 0 and min_pose <= 0:
        return list(cands)
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda x: (x.source, x.t)):
        drop = False
        for k in kept:
            if k.source != c.source:
                continue
            yaw_d = math.hypot(c.yaw - k.yaw, c.pitch - k.pitch)
            pose_d = 1.0
            if c.pose_vec is not None and k.pose_vec is not None:
                pose_d = float(np.mean(np.abs(c.pose_vec - k.pose_vec)))
            if yaw_d < min_yaw and pose_d < min_pose:
                drop = True
                break
        if not drop:
            kept.append(c)
    return kept


YAW_BUCKETS = [
    ("trái nhiều", -180, -25),
    ("trái", -25, -10),
    ("thẳng", -10, 10),
    ("phải", 10, 25),
    ("phải nhiều", 25, 180),
]


def yaw_bucket(c: Candidate) -> str:
    """Nhóm góc: mặt không đủ tin cậy = 'sau lưng/nghiêng'; còn lại theo yaw."""
    if not c.has_face or c.face_sim < 0.35:
        return "sau lưng"
    for label, lo, hi in YAW_BUCKETS:
        if lo <= c.yaw < hi:
            return label
    return "thẳng"


def coverage_pick(cands: list[Candidate], per_bucket: int = 2,
                  bucket_dup: float = 0.93) -> list[Candidate]:
    """Chọn ảnh theo độ phủ góc: mỗi nhóm giữ tối đa `per_bucket` ảnh tốt nhất.

    Khác với `diverse_gate` (bỏ dần theo ngưỡng), cách này đảm bảo **có đủ** mặt
    trái/phải/thẳng và cả ảnh sau lưng (frame không thấy mặt nhưng khớp ngoại
    hình qua neo của video) — đúng nhu cầu đối chiếu danh tính.

    Trong cùng một nhóm còn loại tiếp ảnh gần như trùng nhau (`bucket_dup`) để
    không ra 5 tấm cùng một tư thế.
    """
    buckets: dict[tuple[str, int, str], list[Candidate]] = {}
    for c in cands:
        buckets.setdefault((c.source, c.scene, yaw_bucket(c)), []).append(c)

    picked: list[Candidate] = []
    for items in buckets.values():
        items.sort(key=lambda c: (c.face_sim if c.has_face else c.body_sim,
                                  c.person_h, c.blur), reverse=True)
        chosen: list[Candidate] = []
        for c in items:
            if len(chosen) >= per_bucket:
                break
            if any(c.clip_vec is not None and k.clip_vec is not None
                   and float(np.dot(c.clip_vec, k.clip_vec)) >= bucket_dup
                   for k in chosen):
                continue
            chosen.append(c)
        picked.extend(chosen)
    picked.sort(key=lambda c: (c.source, c.t))
    return picked


def pick_diverse(cands: list[Candidate], n: int, pose_weight: float = 1.0,
                 clip_weight: float = 1.0) -> list[Candidate]:
    """Chọn n frame phủ đa dạng nhất bằng greedy farthest-point sampling."""
    if n <= 0 or len(cands) <= n:
        return list(cands)
    feats = diversity_features(cands, pose_weight, clip_weight)
    # bắt đầu từ frame có chất lượng tốt nhất (blur cao, người to)
    first = int(np.argmax([c.blur * math.log1p(c.person_h) for c in cands]))
    chosen = [first]
    dist = np.linalg.norm(feats - feats[first], axis=1)
    while len(chosen) < n:
        idx = int(np.argmax(dist))
        if dist[idx] <= 1e-6:
            break
        chosen.append(idx)
        dist = np.minimum(dist, np.linalg.norm(feats - feats[idx], axis=1))
    return [cands[i] for i in chosen]


def yaw_histogram(cands: list[Candidate]) -> list[tuple[str, int]]:
    """Đếm số frame theo 6 khoảng góc đầu, để báo cáo độ phủ góc."""
    bins = [(-91, -60, "trái nhiều"), (-60, -30, "trái"), (-30, -12, "hơi trái"),
            (-12, 12, "thẳng"), (12, 30, "hơi phải"), (30, 60, "phải"), (60, 91, "phải nhiều")]
    counts = []
    for lo, hi, label in bins:
        counts.append((label, sum(1 for c in cands if lo <= c.yaw < hi)))
    return counts
