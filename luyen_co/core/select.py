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


def _yaw_dist(a: Candidate, b: Candidate) -> float:
    """Khoảng cách góc đầu (độ) giữa 2 ảnh.

    Bỏ pitch khi |yaw| ≥ 70°: ở góc đó 5 landmark không đo được nữa (yaw bị kẹp
    ±90, pitch nhảy loạn tới ±89), nên hiệu pitch chỉ là nhiễu — nếu vẫn tính
    thì hai frame cùng một dáng dựa tường bị coi là "khác góc" oan.
    """
    dy = float(a.yaw - b.yaw)
    if abs(a.yaw) >= 70 or abs(b.yaw) >= 70:
        return abs(dy)
    return float(math.hypot(dy, a.pitch - b.pitch))


def _pose_dist(a: Candidate, b: Candidate) -> float:
    """Khoảng cách dáng: trung bình |chênh| trên 34 chiều keypoint chuẩn hoá."""
    if a.pose_vec is None or b.pose_vec is None:
        return 9.9
    return float(np.mean(np.abs(a.pose_vec - b.pose_vec)))


# nhóm mà yaw không đo được (mặt khuất / thân nhìn ngang): so theo nhóm là đủ
NO_FACE_BUCKETS = {"sau lưng", "sau lưng 3/4", "không rõ mặt", "nghiêng"}
SOFT_BUCKETS = NO_FACE_BUCKETS


def _same_pose(a: Candidate, b: Candidate, min_yaw: float, min_pose: float) -> bool:
    """Cùng một tư thế: góc camera na ná VÀ dáng gần như nhau.

    Chỉ cần MỘT trong hai khác là ảnh đáng giữ (khác góc thì đổi hướng nhìn,
    khác dáng thì đổi tư thế).

    Với 3 nhóm mà yaw không đo được (quay lưng / nghiêng / không rõ mặt, yaw bị
    kẹp ±90 nên hay bằng nhau) thì so theo nhóm là đủ. Các nhóm còn lại phải so
    **khoảng cách góc thật**, không dùng "cùng nhóm" — vì "trái nhiều" trải tới
    180°, hai frame −30° và −65° cùng nhóm nhưng khác hướng hẳn.
    """
    if _pose_dist(a, b) >= min_pose:
        return False
    bucket = yaw_bucket(a)
    if bucket == yaw_bucket(b) and bucket in SOFT_BUCKETS:
        return True
    return _yaw_dist(a, b) < min_yaw


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
        if any(k.source == c.source and _same_pose(c, k, min_yaw, min_pose) for k in kept):
            continue
        kept.append(c)
    return kept


def drop_tiny_frames(cands: list[Candidate], ratio: float = 0.2,
                     ref_min: int = 400) -> list[Candidate]:
    """Bỏ frame mà người bé tí so với frame to nhất trong **cùng cảnh**.

    Clip quay tay thường có lúc máy ở xa: người chỉ còn ~110 px trong khi cùng
    cảnh đó có frame 950 px. Keypoint ở 110 px nhiễu tới mức pose không còn so
    được, nên lọc trùng tư thế coi chúng là "khác dáng" và giữ lại — kết quả là
    2–3 tấm gần như y hệt nhau, chỉ khác kích thước (đo trên clip bảo vệ:
    33.5 s h=948 / 34.0 s h=111 / 38.5 s h=109, CLIP 0.88–0.96).

    Chỉ áp khi trong cảnh có frame đủ lớn (≥ `ref_min`), và chỉ cắt phần quá
    nhỏ (< 20% frame to nhất) — ảnh "toàn thân ở xa" thật (268 px trong cảnh
    976 px) vẫn được giữ.
    """
    ref: dict[tuple[str, int], int] = {}
    for c in cands:
        key = (c.source, c.scene)
        ref[key] = max(ref.get(key, 0), c.person_h)
    out = []
    for c in cands:
        biggest = ref[(c.source, c.scene)]
        if biggest >= ref_min and c.person_h < ratio * biggest:
            continue
        out.append(c)
    return out


def distinct_pose_pick(cands: list[Candidate], min_yaw: float = 25.0,
                       min_pose: float = 0.08) -> list[Candidate]:
    """Mỗi tư thế (góc camera + dáng) chỉ giữ **một** ảnh tốt nhất.

    Duyệt theo **chất lượng giảm dần** (`_rank_key`: điểm mặt, kích thước người,
    độ nét); giữ ảnh nếu nó khác mọi ảnh đã giữ. Không gom cụm kiểu union-find
    vì nối chuỗi làm sập cả một đoạn phim: clip quay bằng điện thoại (camera di
    động, dáng đổi dần) có A≈B≈C… nên union-find gộp 81 frame còn 6 ảnh, trong
    khi duyệt tham lam giữ được 17 ảnh — đúng ý "đừng bỏ phí frame".

    Vì sao cần bước này: `coverage_pick` chỉ giới hạn 1 ảnh cho mỗi *(nguồn,
    cảnh, nhóm góc)*, nên 5 frame catwalk liên tiếp với đầu quay ±20° vẫn vào 5
    nhóm khác nhau dù dáng gần như y hệt (đo trên obj_1: pose cách nhau
    0.019–0.058) — đúng lỗi "pose lặp quá nhiều".
    """
    if min_yaw <= 0 and min_pose <= 0:
        return list(cands)
    kept: list[Candidate] = []
    for c in sorted(cands, key=_rank_key, reverse=True):
        if any(k.source == c.source and _same_pose(c, k, min_yaw, min_pose) for k in kept):
            continue
        kept.append(c)
    kept.sort(key=lambda c: (c.source, c.t))
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
FACE_VIS_34 = 0.50     # khuất nặng (< 0.50) = chính sau; khuất một nửa = 3/4 sau
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
    """Nhóm góc: sau lưng / 3/4 sau / nghiêng / không rõ mặt, còn lại theo yaw/pitch.

    Trước đây mọi frame không thấy mặt (kể cả người ở xa, mặt quá nhỏ) đều bị
    gom vào "sau lưng", nên ảnh quay lưng thật bị ảnh nhìn thẳng ở xa "đè" mất.
    Giờ tách 3 nhóm riêng: mũi khuất → sau lưng, thân hẹp → nghiêng, còn lại
    → không rõ mặt.

    "Sau lưng" tách đôi theo mức khuất mặt: khuất gần hết (`face_vis` < 0.50)
    là chính sau; khuất một nửa (0.50–0.60) là **3/4 sau** — hướng cổ và vai
    khác hẳn ảnh chụp chính diện lưng, nên để chung một nhóm là mất ảnh.
    """
    if _facing_away(c):
        return "sau lưng" if face_vis(c) < FACE_VIS_34 else "sau lưng 3/4"
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
    if c.has_face and yaw_bucket(c) not in NO_FACE_BUCKETS:
        return (c.face_sim, c.person_h, c.blur)
    return (-1.0, c.person_h, c.blur)


def coverage_pick(cands: list[Candidate], per_bucket: int = 2,
                  bucket_dup: float = 0.93) -> list[Candidate]:
    """Chọn ảnh theo độ phủ góc: mỗi nhóm giữ tối đa `per_bucket` ảnh tốt nhất.

    Nhóm góc gồm: thẳng / trái / phải / trái nhiều / phải nhiều / ngửa / cúi /
    nghiêng / sau lưng 3/4 / sau lưng / không rõ mặt. Nhờ tách "sau lưng" và
    "nghiêng" khỏi "không rõ mặt", mỗi nhóm luôn có suất riêng — ảnh quay lưng
    thật không còn bị ảnh người ở xa (mặt không detect được) chiếm mất.

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
                "ngửa", "cúi", "nghiêng", "sau lưng 3/4", "sau lưng", "không rõ mặt"]


def yaw_histogram(cands: list[Candidate]) -> list[tuple[str, int]]:
    """Đếm số ảnh theo từng nhóm góc (kể cả sau lưng / nghiêng / không rõ mặt).

    Trước đây chỉ đếm theo yaw nên frame quay lưng (không có mặt, yaw = 0) bị
    báo nhầm thành "thẳng"; giờ dùng đúng nhóm mà coverage_pick dùng.
    """
    counts = Counter(yaw_bucket(c) for c in cands)
    return [(label, counts.get(label, 0)) for label in BUCKET_ORDER]


# ---------------------------------------------------------------------- cỡ cảnh
# Thang cỡ cảnh (shot scale). Video nén không đọc được tiêu cự nên "zoom" chỉ đo
# được gián tiếp qua chủ thể chiếm bao nhiêu khung:
#   - `person_h / face_px` → còn bao nhiêu "đầu" trong khung (thân người ≈ 7,5 đầu;
#     bbox mặt của SCRFD ≈ 0,78 đầu nên tỉ lệ này là số đầu thấy được, hơi rộng)
#   - cổ chân (kpts 15/16) có thấy → chắc chắn cả người nằm trong khung
#   - `person_h / src_h` → dự phòng khi không thấy mặt
# Ngưỡng dưới đây hiệu chỉnh bằng 112 ảnh obj_1 (xem sheet_shot.jpg): chọn ảnh sát
# biên mỗi mức rồi soi bằng mắt.
SHOT_ORDER = ["đặc tả", "cận cảnh", "trung cận", "trung cảnh", "toàn thân", "viễn cảnh"]

# nhãn ngắn cho sheet.jpg (cv2.putText chỉ vẽ được ASCII)
SHOT_ABBR = {"đặc tả": "ECU", "cận cảnh": "CU", "trung cận": "MCU",
             "trung cảnh": "MS", "toàn thân": "FS", "viễn cảnh": "LS"}

# số "đầu" thấy được → mức cỡ cảnh; dưới ngưỡng đầu tiên là đặc tả, trên ngưỡng
# cuối là viễn cảnh
SHOT_HEAD_STEPS = [1.6, 2.6, 3.8, 5.8, 9.6]
SHOT_HEAD_LABELS = ["đặc tả", "cận cảnh", "trung cận", "trung cảnh", "toàn thân"]

SHOT_MCU = 0.85        # không thấy mặt: người chiếm ≥ 85% khung → trung cận
SHOT_MS = 0.50         # người chiếm ≥ 50% khung → trung cảnh
SHOT_FS = 0.25         # người chiếm ≥ 25% khung → toàn thân / viễn cảnh
ANKLE_VIS = 0.5        # conf cổ chân đủ cao → thấy cả bàn chân trong khung


def feet_visible(c: Candidate) -> bool:
    """Có thấy cổ chân không — dấu hiệu chắc nhất của ảnh "toàn thân"."""
    kp = c.kpts
    if kp is None or len(kp) < 17:
        return False
    return max(float(kp[15, 2]), float(kp[16, 2])) >= ANKLE_VIS


def _shot_from_body(person: float) -> str:
    """Đoán cỡ cảnh khi không có mặt: chỉ còn tỉ lệ người/khung."""
    if person >= SHOT_MCU:
        return "trung cận"
    if person >= SHOT_MS:
        return "trung cảnh"
    return "toàn thân" if person >= SHOT_FS else "viễn cảnh"


def shot_scale(c: Candidate) -> str:
    """Cỡ cảnh: đặc tả / cận cảnh / trung cận / trung cảnh / toàn thân / viễn cảnh.

    Thứ tự ưu tiên:
      1. Thấy cổ chân → cả người trong khung: "toàn thân" nếu người ≥ 25% chiều
         cao khung, ngược lại "viễn cảnh". Đây là tín hiệu chắc nhất, và nó sửa
         đúng lỗi "người kín khung nhưng vẫn là toàn thân" (chân đặt sát mép).
      2. Không thấy mặt → đoán theo tỉ lệ người/khung (`_shot_from_body`).
      3. Còn lại: đếm số "đầu" trong khung = `person_h / face_px`. Người ≈ 7,5 đầu
         nên ảnh 2 đầu là cận cảnh (đầu + vai), 3 đầu là trung cận (ngực), 5 đầu
         là trung cảnh (eo/hông), 7,5–9,6 đầu là toàn thân.

    Không dùng `face_px / src_h` trực tiếp vì nó lẫn "máy quay gần" với "người to
    trong khung": cùng 1 khung 1280px, mặt 190px là trung cảnh ở ảnh chụp cả
    người, nhưng là cận cảnh nếu người bị cắt ngang ngực — tỉ lệ người/mặt phân
    biệt được hai ca đó.
    """
    h = max(1, c.src_h)
    person = c.person_h / h
    if feet_visible(c):
        return "toàn thân" if person >= SHOT_FS else "viễn cảnh"
    if c.face_px <= 0:
        return _shot_from_body(person)
    heads = c.person_h / c.face_px
    for label, step in zip(SHOT_HEAD_LABELS, SHOT_HEAD_STEPS):
        if heads < step:
            return label
    return "viễn cảnh"


def shot_histogram(cands: list[Candidate]) -> list[tuple[str, int]]:
    """Đếm số ảnh theo từng cỡ cảnh (thứ tự từ gần tới xa)."""
    counts = Counter(shot_scale(c) for c in cands)
    return [(label, counts.get(label, 0)) for label in SHOT_ORDER]


def shot_coverage_pick(cands: list[Candidate], per_cell: int = 2) -> list[Candidate]:
    """Giới hạn số ảnh cho mỗi ô (nhóm góc × cỡ cảnh).

    `coverage_pick` chỉ chia suất theo góc, nên một nhóm góc mà toàn ảnh trung
    cảnh sẽ chiếm hết suất và dataset không còn ảnh gần/xa nào khác. Bước này
    chặn thêm theo cỡ cảnh: mỗi cặp (góc, cỡ cảnh) giữ tối đa `per_cell` ảnh
    tốt nhất theo `_rank_key`.

    Lưu ý: bước này chỉ **bỏ bớt**, không tạo ra cỡ cảnh đang thiếu — summary sẽ
    liệt kê ô trống để biết cần quay thêm loại cảnh nào.
    """
    if per_cell <= 0 or not cands:
        return list(cands)
    counts: Counter = Counter()
    kept: list[Candidate] = []
    for c in sorted(cands, key=_rank_key, reverse=True):
        key = (yaw_bucket(c), shot_scale(c))
        if counts[key] >= per_cell:
            continue
        counts[key] += 1
        kept.append(c)
    kept.sort(key=lambda c: (c.source, c.t))
    return kept
