"""Ước lượng góc đầu, vector pose, lọc trùng và chọn bộ frame đa dạng.

Góc đầu (yaw/pitch) tính từ 5 landmark của SCRFD — đủ để phân biệt "nhìn
thẳng / quay trái / quay phải / cúi / ngửa", không phải số đo chính xác.
Pose toàn thân dùng 17 keypoint COCO chuẩn hoá theo bbox.
"""

from __future__ import annotations

import math
from collections import Counter

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
    pitch = max(-89.0, min(89.0, pitch))    # 5 điểm dễ sai khi đầu nghiêng mạnh
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


def keep_best_body_tracks(cands: list[Candidate], low: float = 0.45,
                          rel: float = 0.85) -> tuple[list[Candidate], float]:
    """Chế độ chỉ-toàn-thân: giữ những track khớp ngoại hình tốt nhất.

    Dùng khi **không có track nào khớp mặt** (clip chỉ quay từ sau, CCTV xa…).
    Lúc đó không có mốc tuyệt đối nào để so, nên so tương đối: track có trung vị
    `body_sim` cao nhất là người mục tiêu, các track gần mức đó được giữ.

    Vì sao cần: ảnh quay lưng so với ảnh tham chiếu nhìn thẳng chỉ đạt cosine
    CLIP ~0.55–0.65 (đo trên v1.mp4), nên một ngưỡng tuyệt đối 0.72 đá sạch
    ảnh lưng — đúng lỗi "không ra ảnh sau lưng nào".

    Trả (danh sách giữ lại, ngưỡng thực dùng).
    """
    if not cands:
        return [], 0.0
    from collections import defaultdict

    by_track: dict[tuple[str, int], list[float]] = defaultdict(list)
    for c in cands:
        by_track[(c.source, c.track_id)].append(c.body_sim)
    med = {k: float(np.median(v)) for k, v in by_track.items()}
    th = max(float(low), float(rel) * max(med.values()))
    kept = [c for c in cands if med[(c.source, c.track_id)] >= th]
    kept.sort(key=lambda c: (c.source, c.t))
    return kept, th


YAW_BUCKETS = [
    ("trái nhiều", -180, -25),
    ("trái", -25, -10),
    ("thẳng", -10, 10),
    ("phải", 10, 25),
    ("phải nhiều", 25, 180),
]


FACE_VIS_BACK = 0.60   # TB conf (mũi + 2 mắt) dưới mức này = phần mặt bị khuất
EAR_VIS_MIN = 0.25     # tai vẫn thấy → keypoint đầu là thật, không phải đoán bừa
SHOULDER_VIS = 0.45    # vai phải đủ rõ mới dám kết luận về hướng thân
SIDE_SPAN = 0.22       # vai/hông hẹp hơn mức này (theo bề rộng bbox) = thân nhìn ngang


def face_vis(c: Candidate) -> float:
    """Độ "nhìn thấy mặt" theo keypoint: TB conf của mũi + 2 mắt (−1 nếu thiếu).

    Dùng cả 3 điểm thay vì riêng mũi: khi người quay lưng YOLO vẫn đoán ra mũi
    với conf lên tới 0.6 (đo trên v1.mp4: 0.58 ở frame đang xoay), nhưng **mắt**
    thì sụp theo — nên lấy trung bình 3 điểm ổn định hơn hẳn.
    """
    kp = c.kpts
    if kp is None or len(kp) < 7:
        return -1.0
    return float((kp[0, 2] + kp[1, 2] + kp[2, 2]) / 3.0)


def _facing_away(c: Candidate) -> bool:
    """Đoán người đang quay lưng: phần mặt khuất nhưng vai + tai vẫn rõ.

    Đo trên v1.mp4 (catwalk), phân bố rất tách:
      - quay lưng:  mũi 0.19–0.58, mắt 0.08–0.36 → face_vis 0.18–0.43
      - nhìn thẳng: mũi 0.92–0.99, mắt 0.73–0.95 → face_vis 0.73–0.97
    Ngưỡng 0.60 nằm giữa khoảng trống đó, nên cùng một đoạn đi bộ quay lưng
    không còn bị lật nhãn khi conf mũi nhảy (lỗi cũ: chỉ so mũi < 0.5).
    """
    if c.kpts is None or len(c.kpts) < 7:
        return False
    kp = c.kpts
    shoulders = max(float(kp[5, 2]), float(kp[6, 2]))
    ears = float((kp[3, 2] + kp[4, 2]) / 2.0)
    vis = face_vis(c)
    if vis < 0:
        return False
    return vis < FACE_VIS_BACK and shoulders > SHOULDER_VIS and ears >= EAR_VIS_MIN


def _side_body(c: Candidate) -> bool:
    """Thân nhìn ngang: vai và hông chồng nhau theo phương ngang.

    Dùng khi không có mặt (người ở xa): người nhìn thẳng/quay lưng có vai mở
    rộng, còn nhìn ngang thì vai/hông trái-phải gần như trùng toạ độ x.
    """
    if c.kpts is None or len(c.kpts) < 13:
        return False
    kp = c.kpts
    if max(float(kp[5, 2]), float(kp[6, 2])) < 0.45:
        return False
    x1, _, x2, _ = (float(v) for v in c.box)
    w = max(1.0, x2 - x1)
    span = abs(float(kp[5, 0]) - float(kp[6, 0])) / w
    hip = abs(float(kp[11, 0]) - float(kp[12, 0])) / w
    return max(span, hip) < SIDE_SPAN


def yaw_bucket(c: Candidate) -> str:
    """Nhóm góc: sau lưng / nghiêng / không rõ mặt, còn lại theo yaw/pitch.

    Trước đây mọi frame không thấy mặt (kể cả người ở xa, mặt quá nhỏ) đều bị
    gom vào "sau lưng", nên ảnh quay lưng thật bị ảnh nhìn thẳng ở xa "đè" mất.
    Giờ tách 3 nhóm riêng: mũi khuất → sau lưng, thân hẹp → nghiêng, còn lại
    → không rõ mặt.
    """
    if _facing_away(c):
        return "sau lưng"
    if c.has_face:
        if abs(c.yaw) >= 70:  # nghiêng gần hẳn: 5 điểm không còn đo được yaw
            return "nghiêng"
        if c.pitch > 15:      # camera/đầu ngửa lên
            return "ngửa"
        if c.pitch < -15:     # cúi xuống
            return "cúi"
        for label, lo, hi in YAW_BUCKETS:
            if lo <= c.yaw < hi:
                return label
        return "thẳng"
    if _side_body(c):
        return "nghiêng"
    return "không rõ mặt"


def _rank_key(c: Candidate) -> tuple[float, int, float]:
    """Điểm xếp hạng trong cùng một nhóm góc: (điểm mặt, người cao, độ nét).

    Nhóm "sau lưng" / "nghiêng" / "không rõ mặt" không có điểm mặt để so, nên
    xếp theo kích thước người rồi độ nét. Nhờ vậy frame quay lưng ở gần (người
    to, rõ) thắng frame nhìn thẳng ở xa — lỗi cũ khiến ảnh sau lưng bị loại.
    """
    if c.has_face and yaw_bucket(c) not in ("sau lưng", "nghiêng", "không rõ mặt"):
        return (c.face_sim, c.person_h, c.blur)
    return (-1.0, c.person_h, c.blur)


def coverage_pick(cands: list[Candidate], per_bucket: int = 2,
                  bucket_dup: float = 0.93) -> list[Candidate]:
    """Chọn ảnh theo độ phủ góc: mỗi nhóm giữ tối đa `per_bucket` ảnh tốt nhất.

    Nhóm góc gồm: thẳng / trái / phải / trái nhiều / phải nhiều / ngửa / cúi /
    nghiêng / sau lưng / không rõ mặt. Nhờ tách "sau lưng" và "nghiêng" khỏi
    "không rõ mặt", mỗi nhóm luôn có suất riêng — ảnh quay lưng thật không còn
    bị ảnh người ở xa (mặt không detect được) chiếm mất.

    Trong cùng một nhóm còn loại tiếp ảnh gần như trùng nhau (`bucket_dup`) để
    không ra 5 tấm cùng một tư thế.
    """
    buckets: dict[tuple[str, int, str], list[Candidate]] = {}
    for c in cands:
        buckets.setdefault((c.source, c.scene, yaw_bucket(c)), []).append(c)

    picked: list[Candidate] = []
    for items in buckets.values():
        # 1) giữ ảnh chất lượng nhất, 2) các ảnh sau chọn theo mức KHÁC BIỆT với
        # ảnh đã giữ (không phải theo chất lượng) → bắt được cả frame quay lưng
        # xa/nhỏ nếu nó là tư thế khác với ảnh đầu
        items = sorted(items, key=_rank_key, reverse=True)
        chosen: list[Candidate] = []
        while items and len(chosen) < per_bucket:
            if not chosen:
                chosen.append(items.pop(0))
                continue
            best_i, best_sim = None, 2.0
            for i, c in enumerate(items):
                if c.clip_vec is None:
                    continue
                sim = max(float(np.dot(c.clip_vec, k.clip_vec))
                          for k in chosen if k.clip_vec is not None)
                if sim < best_sim:
                    best_sim, best_i = sim, i
            if best_i is None or best_sim >= bucket_dup:
                break
            chosen.append(items.pop(best_i))
        picked.extend(chosen)
    picked.sort(key=lambda c: (c.source, c.t))
    return picked


def drop_similar(cands: list[Candidate], th: float = 0.93) -> list[Candidate]:
    """Loại lần cuối: ảnh quá giống một ảnh đã giữ trong CÙNG nguồn & cùng nhóm góc.

    Chỉ so trong cùng nhóm để không xoá mất ảnh quay lưng/nghiêng chỉ vì nó
    giống ảnh nhìn thẳng (cùng bộ đồ, cùng dáng đứng) — nếu không, bước lọc cuối
    này sẽ phá đúng cái "đủ góc" mà coverage_pick vừa chọn.
    """
    mats: dict[tuple[str, str], np.ndarray] = {}
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda x: (x.source, x.t)):
        if c.clip_vec is None:
            kept.append(c)
            continue
        key = (c.source, yaw_bucket(c))
        mat = mats.get(key)
        if mat is not None and float((mat @ c.clip_vec).max()) >= th:
            continue
        kept.append(c)
        mats[key] = c.clip_vec[None].copy() if mat is None else np.vstack([mat, c.clip_vec[None]])
    return kept


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


BUCKET_ORDER = ["trái nhiều", "trái", "thẳng", "phải", "phải nhiều",
                "ngửa", "cúi", "nghiêng", "sau lưng", "không rõ mặt"]


def yaw_histogram(cands: list[Candidate]) -> list[tuple[str, int]]:
    """Đếm số ảnh theo từng nhóm góc (kể cả sau lưng / nghiêng / không rõ mặt).

    Trước đây chỉ đếm theo yaw nên frame quay lưng (không có mặt, yaw = 0) bị
    báo nhầm thành "thẳng"; giờ dùng đúng nhóm mà coverage_pick dùng.
    """
    counts = Counter(yaw_bucket(c) for c in cands)
    return [(label, counts.get(label, 0)) for label in BUCKET_ORDER]
