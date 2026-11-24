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


def dedupe(cands: list[Candidate], dup_sim: float = 0.97, min_gap: float = 0.35,
           frame_dedupe: bool = False) -> list[Candidate]:
    """Bỏ frame gần như trùng: sát thời gian trong cùng track, hoặc ngoại hình quá giống.

    So sánh ngoại hình bằng 1 phép nhân ma trận mỗi frame (BLAS) thay vì vòng
    lặp Python, để video CCTV vài chục nghìn frame vẫn chạy nhanh.

    `frame_dedupe`: dùng khi file xuất ra là **cả khung hình** (`--save full`/`both`).
    Lúc đó hai track trong cùng một frame cho ra **đúng một tấm ảnh** (cùng
    `full_jpeg`, không phụ thuộc box), nên chỉ giữ bản xếp hạng cao nhất. Đo trên
    bộ 32 video: 2 frame bị xuất 2 lần, hai file **byte-identical**
    (`CxzjgbihCyq` frame 437, `Instagram 1750172524` frame 36). Với `--save crop`
    thì **không** bật: hai box khác nhau là hai crop khác nhau, đều dùng được.
    """
    from collections import defaultdict

    if frame_dedupe:
        # giữ bản tốt nhất mỗi (nguồn, frame) — không cần ngưỡng nào, đây là trùng tuyệt đối
        best: dict[tuple[str, int], Candidate] = {}
        for c in cands:
            key = (c.source, c.frame_idx)
            cur = best.get(key)
            if cur is None or _rank_key(c) > _rank_key(cur):
                best[key] = c
        cands = [c for c in cands if best[(c.source, c.frame_idx)] is c]

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
    if abs(a.yaw) >= YAW_SATURATED or abs(b.yaw) >= YAW_SATURATED:
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


def _yaw_family(c: Candidate, min_yaw: float = 20.0) -> int:
    """Phía quay: −1 = quay trái, 0 = gần chính diện, +1 = quay phải."""
    if c.yaw <= -min_yaw:
        return -1
    if c.yaw >= min_yaw:
        return 1
    return 0


def _same_side(a: Candidate, b: Candidate) -> bool:
    """Hai ảnh cùng phía quay (cùng trái / cùng phải / cùng chính diện)."""
    return _yaw_family(a) == _yaw_family(b)


def _heads(c: Candidate) -> float:
    """Số 'đầu' trong khung (person_h / face_px); 0 nếu không thấy mặt."""
    return c.person_h / c.face_px if c.face_px > 0 else 0.0


# Zoom là đại lượng **liên tục**, nên so bằng log tỉ lệ người/khung chứ không so
# "số đầu" (person_h / face_px) — số đầu chia cho bbox mặt SCRFD, mà bbox mặt lệch
# 20–30% chỉ vì detector, không phải vì camera đổi cự ly. Đo trên obj_1: hai frame
# cách nhau 0.5 s của cùng một cú máy cho số đầu 8.99 vs 6.67 (1.35×, tưởng "khác
# cỡ cảnh") trong khi tỉ lệ người/khung chỉ lệch 13%.
# Ngưỡng 0.16 ≈ lệch ±17%: đủ rộng cho cụm v1 34.0/34.5/35.0/36.5 s (lệch 1.8–15.5%),
# nhưng vẫn tách được ca 6.0 s vs 17.0 s (lệch 18%, cận cảnh đứng nói vs trung cảnh
# đang đi — hai ảnh khác nhau thật).
ZOOM_TOL = 0.16
# "Thấy cổ chân" chỉ đáng tin khi người đã gần lấp kín khung; ở cảnh xa, conf
# keypoint cổ chân lật loạn (đo trên obj_1: lật giữa hai frame cách nhau 0.5 s).
FEET_KEY_FRAC = 0.85


def _same_framing(a: Candidate, b: Candidate, head_tol: float = 0.30,
                  frac_tol: float = ZOOM_TOL) -> bool:
    """Hai ảnh cùng cỡ cảnh — so **độ phóng** (log tỉ lệ người/khung), không so nhãn.

    Vì sao không dùng "số đầu" (`person_h / face_px`): nó chia cho bbox mặt do
    SCRFD đo, nên bbox mặt to/nhỏ hơn 20–30% là đủ để hai khung y hệt rơi vào hai
    mức liền kề (`trung cảnh` vs `trung cận`). Ca thật 70.0/70.5 s: số đầu 4.11 vs
    3.53 nhưng cùng chiếm 91% khung. Số đầu vẫn được dùng làm **dự phòng** khi
    thiếu tỉ lệ người/khung.

    Cùng cỡ cảnh khi `|log(fa/fb)| ≤ frac_tol` (mặc định 0.16 ≈ ±17%) với
    `f = person_h / src_h`. Trước đây ngưỡng là 12% *tương đối* cộng điều kiện
    cổ chân bằng nhau; đo trên cụm `v1.mp4` 34.0/34.5/35.0/36.5 s thì chính hai
    điều kiện đó tách rời 4 ảnh gần như một (foot flag lật, tỉ lệ lệch 12.3%).

    Cờ cổ chân chỉ còn là **cờ hoà giải**, và chỉ xét khi cả hai ảnh đã chiếm
    ≥ `FEET_KEY_FRAC` khung — lúc đó "thấy bàn chân hay không" mới thật là khác
    biệt toàn thân vs cận cảnh (giữ được test `toan_than_khac_can_canh`).
    """
    fa = a.person_h / max(1, a.src_h)
    fb = b.person_h / max(1, b.src_h)
    if fa > 0 and fb > 0:
        if abs(math.log(fa / fb)) > frac_tol:
            return False
        if feet_visible(a) != feet_visible(b) and min(fa, fb) >= FEET_KEY_FRAC:
            return False
        return True
    # thiếu tỉ lệ người/khung (hiếm): rơi về số đầu như cũ
    ha, hb = _heads(a), _heads(b)
    return ha > 0 and hb > 0 and max(ha, hb) <= (1 + head_tol) * min(ha, hb)


# |yaw| ≥ 70: 5 landmark đầu đã bị kẹp trục, pitch chỉ còn là nhiễu (xem `_yaw_dist`)
YAW_SATURATED = 70.0
# dưới mức này coi như **không thấy mặt** ⇒ yaw chỉ là số 0 mặc định, không phải "nhìn thẳng"
FACE_VIS_KNOWN = 0.60
# nhóm mà người đang quay lưng — dùng được cả khi yaw là số mặc định
_BACK_BUCKETS = {"sau lưng", "sau lưng 3/4"}


def _yaw_is_placeholder(c: Candidate) -> bool:
    """`yaw` có phải số mặc định vì không thấy mặt không (chứ không phải góc đo được).

    Đo trên obj_1 (cụm `v1.mp4`): frame 34.0 s không detect được mặt ⇒ `yaw = 0.0`;
    frame 35.0 s thấy mặt nghiêng ⇒ `yaw = −90.0`. Hai ảnh **cùng một góc nhìn** mà
    hiệu yaw là 90°, đủ để trục góc quay tách chúng ra. Gốc lỗi: số 0 mặc định bị
    đem so như một phép đo thật.

    Tín hiệu chắc chắn nhất là `face_px == 0`: SCRFD không tìm thấy mặt nên pipeline
    gán yaw = pitch = 0.0 (pipeline.py, `head_pose` chỉ chạy khi có `faces`). Chỉ khi
    cả ba điều kiện đó cùng đúng mới coi là mặc định — nhờ vậy dữ liệu tổng hợp
    (test) đặt yaw khác 0 mà không cần bbox mặt vẫn được tôn trọng.

    Thêm nhánh `face_vis < 0.60` cho ca SCRFD vẫn bắt được mặt nhưng mặt bị khuất
    (nghiêng hẳn/quay lưng): lúc đó yaw đo được nhưng rất nhiễu.

    `|yaw| ≥ 70` **không** coi là mất thông tin: dấu và độ lớn vẫn phản ánh hướng
    quay, hai ảnh −90° và −40° là hai hướng khác nhau thật.
    """
    if c.face_px <= 0 and c.yaw == 0.0 and c.pitch == 0.0:
        return True
    vis = face_vis(c)
    return vis >= 0 and vis < FACE_VIS_KNOWN


def _same_pose(a: Candidate, b: Candidate, min_yaw: float, min_pose: float,
               min_pose_deg: float = 20.0, min_pose_max_deg: float = 45.0,
               near_dup_th: float = 0.84) -> bool:
    """Cùng một tấm ảnh về mặt thông tin: giống CẢ 3 TRỤC (cỡ cảnh, góc, dáng).

    Ba trục được đo độc lập nên ảnh chỉ bị coi là trùng khi giống nhau ở cả ba:
      - **cỡ cảnh** khác nhau (cận cảnh vs toàn thân) → 2 ảnh khác nhau, giữ cả hai;
      - **dáng** (góc khớp) khác → giữ;
      - **góc quay** khác → giữ.
    Trước đây chỉ xét góc + dáng, nên một ảnh cận cảnh và một ảnh toàn thân cùng
    dáng bị coi là trùng dù nhìn ra hai thứ hoàn toàn khác nhau.

    Dáng đo bằng **góc khớp** là chính; `_pose_dist` (toạ độ chuẩn hoá trong
    bbox) chỉ dùng **dự phòng** khi không đo được góc nào (thiếu keypoint). Lý do:
    toạ độ chuẩn hoá theo bbox bị chính bbox làm nhiễu — giơ tay ra là bbox rộng
    ra, mọi toạ độ x bị nén lại, `_pose_dist` nhảy vọt dù người không đổi dáng.
    Đo trên obj_1: 47 cặp ảnh trùng dáng & góc & cỡ cảnh đã bị `_pose_dist` giữ
    lại oan. Góc khớp không phụ thuộc bbox nên không mắc lỗi đó.

    Góc quay: với 4 nhóm mà yaw không đo được (sau lưng / 3-4 sau / nghiêng /
    không rõ mặt, yaw bị kẹp ±90 nên hay bằng nhau) thì so theo nhóm là đủ. Các
    nhóm còn lại phải so **khoảng cách góc thật**, không dùng "cùng nhóm" — vì
    "trái nhiều" trải tới 180°, hai frame −30° và −65° cùng nhóm nhưng khác hướng.

    Nếu **một trong hai** ảnh không thấy mặt (`_yaw_is_placeholder`: yaw chỉ là số 0
    mặc định) thì bỏ phép so yaw, chỉ còn cỡ cảnh + dáng + **hướng thân** (nhóm
    "sau lưng" vẫn dùng được) quyết. Trước đây yaw mặc định 0.0 của ảnh không mặt bị
    đem so với yaw thật của ảnh có mặt, nên hai frame cùng một cú máy (0° vs −90°) bị
    coi là khác hướng và cùng lọt.
    """
    if not _same_framing(a, b):
        return False
    # Cùng PHÍA quay (chính diện / trái / phải) + cùng cỡ cảnh + ngoại hình gần
    # như y hệt ⇒ trùng nhau về ý nghĩa, dù góc đầu lệch vài chục độ. Đo trên
    # clip 1750183430: 4 ảnh MC đang nói (45.0 / 52.5 / 56.5 / 60.5 s) cùng váy,
    # cùng bối cảnh, cùng khung hình, CLIP 0.843–0.893; và 3 ảnh 67.0 / 68.0 /
    # 68.5 s (CLIP 0.953–0.966) lọt qua bộ lọc vì mỗi ảnh rơi vào nhóm góc khác
    # nhau (thẳng / trái / không rõ mặt) — đúng lỗi "pose lặp quá nhiều".
    # Ảnh cùng phía nhưng KHÁC ngoại hình (CLIP thấp) vẫn được giữ.
    if near_dup_th > 0 and a.clip_vec is not None and b.clip_vec is not None \
            and _same_side(a, b) and float(np.dot(a.clip_vec, b.clip_vec)) >= near_dup_th:
        return True
    ang = pose_angle_dist(a, b)
    if ang is not None:
        if ang[0] >= min_pose_deg or ang[1] >= min_pose_max_deg:
            return False
    elif _pose_dist(a, b) >= min_pose:      # dự phòng: không đo được góc khớp
        return False
    if _yaw_is_placeholder(a) or _yaw_is_placeholder(b):
        # yaw của ảnh không thấy mặt chỉ là số 0 mặc định: hiệu hai con số không
        # mang thông tin. Nhưng **hướng thân** thì vẫn còn trong nhóm góc, nên chỉ
        # bỏ phép so yaw, không bỏ luôn "mặt hướng về phía nào": một ảnh nhìn thẳng
        # và một ảnh quay lưng (bucket sau lưng) là hai ảnh khác nhau thật
        # (ca v1.mp4 17.0 s nhìn thẳng vs 17.5 s quay lưng).
        ba = yaw_bucket(a) in _BACK_BUCKETS
        bb = yaw_bucket(b) in _BACK_BUCKETS
        return ba == bb
    bucket = yaw_bucket(a)
    if bucket == yaw_bucket(b) and bucket in SOFT_BUCKETS:
        return True
    return _yaw_dist(a, b) < min_yaw


def diverse_gate(cands: list[Candidate], min_yaw: float = 12.0,
                 min_pose: float = 0.08, min_pose_deg: float = 20.0,
                 min_pose_max_deg: float = 45.0,
                 near_dup_th: float = 0.84) -> list[Candidate]:
    """Chỉ giữ frame khác biệt đủ rõ so với các frame đã giữ (cùng nguồn).

    Một frame bị bỏ khi giống ảnh đã giữ ở cả 3 trục (cỡ cảnh + góc + dáng) —
    tức là hai ảnh gần như cùng một tư thế. Thực tế chỉ cần vài ảnh khác nhau
    làm bằng chứng nhận dạng, không cần 20 ảnh cùng một pose.
    """
    if min_yaw <= 0 and min_pose <= 0 and min_pose_deg <= 0:
        return list(cands)
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda x: (x.source, x.t)):
        if any(k.source == c.source
               and _same_pose(c, k, min_yaw, min_pose, min_pose_deg, min_pose_max_deg,
                              near_dup_th)
               for k in kept):
            continue
        kept.append(c)
    return kept


def drop_blurry_faces(cands: list[Candidate], ratio: float = 0.35,
                      ref_min: float = 60.0) -> list[Candidate]:
    """Bỏ frame mà **vùng mặt** mờ hẳn so với các frame cùng cảnh.

    `blur` của cả frame không bắt được frame chuyển cảnh chồng mờ (cross-dissolve):
    hai cảnh chồng lên nhau nên ảnh vẫn "nét" theo Laplacian — đo trên clip
    1750183430, frame hỏng ở t=72.0 s có blur 2525, frame sạch cùng cảnh 2677–4620.
    Nhưng **mặt** thì bị hai bóng chồng nhau: Laplacian vùng mặt (112×112) chỉ
    **23**, trong khi các frame sạch của cùng clip là **90–161**.

    Vì độ nét vùng mặt phụ thuộc kích thước mặt (mặt nhỏ trong ảnh toàn cảnh mờ
    hơn một cách tự nhiên), ngưỡng được so **tương đối** với trung vị của chính
    cảnh đó, và chỉ áp khi cảnh có ảnh mặt đủ nét (`ref_min`) — giống cách
    `drop_tiny_frames` xử lý frame người quá bé. Frame không thấy mặt thì bỏ qua.
    """
    if ratio <= 0:
        return list(cands)
    by_scene: dict[tuple[str, int], list[float]] = {}
    for c in cands:
        if c.face_blur > 0:
            by_scene.setdefault((c.source, c.scene), []).append(c.face_blur)
    med = {k: float(np.median(v)) for k, v in by_scene.items()}
    out: list[Candidate] = []
    for c in cands:
        m = med.get((c.source, c.scene), 0.0)
        if c.face_blur > 0 and m >= ref_min and c.face_blur < ratio * m:
            continue
        out.append(c)
    return out


def drop_bad_frames(cands: list[Candidate], face_th: float = 0.40,
                    spark_ratio: float = 4.0, spark_min: float = 0.03,
                    blur_ratio: float = 0.25) -> tuple[list[Candidate], dict[str, int]]:
    """Bỏ frame hỏng kiểu "không phải ảnh chụp thật", so với chính cảnh đó.

    Ba loại, đo trên obj_1:

    1. **Hiệu ứng lấp lánh / chuyển cảnh** (`spark`): clip edit hay chèn hiệu ứng
       hạt sáng khi chuyển cảnh — người bị phủ kín hạt, không dùng được. Tỉ lệ
       điểm sáng cực đại cục bộ: frame hỏng **0.097 / 0.082**, frame sạch cùng
       clip **0.003–0.014** → bỏ khi `spark > 4 × trung vị cảnh` và `> 0.03`.
    2. **Mờ hẳn so với cảnh** (`blur`, Laplacian crop người): frame người bé tí
       ở xa, nhoè: blur **42** trong khi trung vị cảnh **606** → bỏ khi
       `blur < 0.25 × trung vị cảnh`.
    3. **Cận cảnh mà mặt không dùng được**: ảnh đặc tả/cận cảnh là để học nét
       mặt, nên nếu `face_sim < face_th` (mặt không khớp) thì ảnh vô nghĩa —
       đo thật: một frame cận cảnh bị nhoè lia máy có `face_sim` 0.098.

    Trả (frame giữ, số frame bị bỏ theo từng lý do).
    """
    reasons = {"hiệu ứng lấp lánh": 0, "mờ hẳn so với cảnh": 0, "cận cảnh mặt hỏng": 0}

    def medians(attr: str) -> dict[tuple[str, int], float]:
        by: dict[tuple[str, int], list[float]] = {}
        for c in cands:
            by.setdefault((c.source, c.scene), []).append(float(getattr(c, attr)))
        return {k: float(np.median(v)) for k, v in by.items()}

    blur_med = medians("blur") if blur_ratio > 0 else {}
    spark_med = medians("spark") if spark_ratio > 0 else {}

    out: list[Candidate] = []
    for c in cands:
        key = (c.source, c.scene)
        if spark_ratio > 0 and c.spark > spark_min and \
                c.spark > spark_ratio * max(spark_med.get(key, 0.0), 1e-4):
            reasons["hiệu ứng lấp lánh"] += 1
            continue
        if blur_ratio > 0 and c.blur < blur_ratio * blur_med.get(key, 0.0):
            reasons["mờ hẳn so với cảnh"] += 1
            continue
        if shot_scale(c) in ("đặc tả", "cận cảnh") and c.face_sim < face_th:
            reasons["cận cảnh mặt hỏng"] += 1
            continue
        out.append(c)
    return out, reasons


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
                       min_pose: float = 0.08, min_pose_deg: float = 20.0,
                       min_pose_max_deg: float = 45.0,
                       near_dup_th: float = 0.84) -> list[Candidate]:
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
    if min_yaw <= 0 and min_pose <= 0 and min_pose_deg <= 0:
        return list(cands)
    kept: list[Candidate] = []
    for c in sorted(cands, key=_rank_key, reverse=True):
        if any(k.source == c.source
               and _same_pose(c, k, min_yaw, min_pose, min_pose_deg, min_pose_max_deg,
                              near_dup_th)
               for k in kept):
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


# ----------------------------------------------------------------- góc khớp pose
# Dáng được đo bằng **góc khớp** thay vì toạ độ keypoint: góc không phụ thuộc
# người to hay nhỏ trong khung (cỡ cảnh) và không phụ thuộc vị trí trong khung,
# nên 3 trục "cỡ cảnh / góc quay / dáng" không lẫn vào nhau.
#
# Đầu (mũi, mắt, tai) **không** được dùng ở đây — hướng đầu là trục "góc quay",
# đã đo riêng bằng yaw/pitch. Nhờ vậy hai ảnh cùng dáng nhưng đầu quay khác nhau
# vẫn được coi là cùng dáng (khác góc), đúng như mong muốn.
JOINT_CONF = 0.35       # keypoint dưới mức này coi như không thấy
BONE_MIN = 0.10         # xương ngắn hơn 10% chiều cao người = đang hướng vào camera
POSE_MIN_ANGLES = 4     # cần ít nhất chừng này góc đo được mới dám kết luận

POSE_ANGLE_NAMES = ["khuỷu trái", "khuỷu phải", "gối trái", "gối phải",
                    "nâng tay trái", "nâng tay phải", "dạng đùi trái", "dạng đùi phải",
                    "mở hai đùi", "nghiêng thân", "nghiêng vai"]
# ảnh gương: đổi trái↔phải, góc có dấu (nghiêng thân / nghiêng vai) đổi dấu
POSE_MIRROR_IDX = np.array([1, 0, 3, 2, 5, 4, 7, 6, 8, 9, 10])
POSE_MIRROR_SIGN = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, -1, -1], np.float32)


def _vec_angle(u: np.ndarray, v: np.ndarray) -> float:
    """Góc giữa 2 vector (0–180°), nan nếu một vector bằng 0."""
    nu, nv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    if nu < 1e-6 or nv < 1e-6:
        return float("nan")
    c = float(np.dot(u, v) / (nu * nv))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _signed_angle(v: np.ndarray) -> float:
    """Góc có dấu của vector so với phương thẳng đứng hướng lên (dương = sang phải)."""
    return math.degrees(math.atan2(float(v[0]), -float(v[1])))


def pose_angles(c: Candidate) -> np.ndarray | None:
    """Vector 11 góc khớp (độ), nan ở góc không đo được.

    Gồm: khuỷu, gối, nâng tay, dạng đùi (mỗi thứ 2 bên), mở hai đùi, nghiêng
    thân, nghiêng vai. Góc nào cần keypoint bị khuất (conf < 0.35) hoặc xương quá
    ngắn (hướng vào camera → hình chiếu 2D bị co) thì để nan, **không** gán 0.5
    như cách cũ — nhờ vậy keypoint thiếu không tạo ra "giống nhau giả tạo".
    """
    kp = c.kpts
    if kp is None or len(kp) < 17:
        return None
    p = np.asarray(kp, np.float32)
    seen = p[:, 2] >= JOINT_CONF
    h = float(c.person_h) or float(np.ptp(p[:, 1]))
    min_len = BONE_MIN * max(1.0, h)

    def pt(i: int) -> np.ndarray:
        return p[i, :2]

    def bone(i: int, j: int) -> np.ndarray | None:
        if not (seen[i] and seen[j]):
            return None
        v = pt(j) - pt(i)
        return v if float(np.linalg.norm(v)) >= min_len else None

    out = np.full(len(POSE_ANGLE_NAMES), np.nan, np.float32)

    torso = None
    if seen[5] and seen[6] and seen[11] and seen[12]:
        t = (pt(5) + pt(6)) / 2 - (pt(11) + pt(12)) / 2
        if float(np.linalg.norm(t)) >= min_len:
            torso = t

    for slot, sh, el, wr in ((0, 5, 7, 9), (1, 6, 8, 10)):
        arm = bone(sh, el)
        if arm is None:
            continue
        fore = bone(el, wr)
        if fore is not None:                       # góc khuỷu
            out[slot] = _vec_angle(-arm, fore)
        if torso is not None:                      # nâng tay (0 = buông, 90 = ngang)
            out[4 + slot] = _vec_angle(torso, arm)

    thighs = {}
    for slot, hip, knee, ank in ((0, 11, 13, 15), (1, 12, 14, 16)):
        thigh = bone(hip, knee)
        if thigh is None:
            continue
        thighs[slot] = thigh
        shin = bone(knee, ank)
        if shin is not None:                       # góc gối
            out[2 + slot] = _vec_angle(-thigh, shin)
        if torso is not None:                      # dạng đùi
            out[6 + slot] = _vec_angle(-torso, thigh)
    if 0 in thighs and 1 in thighs:                # mở hai đùi
        out[8] = _vec_angle(thighs[0], thighs[1])

    if torso is not None:                          # nghiêng thân
        out[9] = _signed_angle(torso)
    if seen[5] and seen[6]:                        # nghiêng vai
        sline = pt(6) - pt(5)
        if float(np.linalg.norm(sline)) >= min_len:
            out[10] = math.degrees(math.atan2(float(sline[1]), float(sline[0])))

    if int(np.sum(~np.isnan(out))) < POSE_MIN_ANGLES:
        return None
    return out


def pose_angle_deltas(a: Candidate, b: Candidate) -> np.ndarray | None:
    """|lệch| của **từng** góc khớp (đã xét ảnh gương), bỏ góc không đo được ở một bên.

    Trả `None` khi không đủ góc để kết luận. Có mảng này thì nơi gọi mới phân biệt được
    "lệch đều nhiều khớp" (dáng khác thật) với "chỉ một khớp lệch" (thường là keypoint
    nhiễu) — `pose_angle_dist` chỉ còn trung bình/max nên không phân biệt được.
    Đo trên obj_1 (cặp 87/88, cùng một khung, cách 14 s): 6 góc đo được, **chỉ 1 khớp
    lệch 114°** (khuỷu trái), 5 khớp còn lại lệch 3–17° → trung bình 26.5 nhưng median
    chỉ 9.3. Dùng trung bình sẽ kết luận oan "khác dáng".
    """
    va, vb = pose_angles(a), pose_angles(b)
    if va is None or vb is None:
        return None
    best: tuple[tuple[float, float], np.ndarray] | None = None
    for cand in (vb, vb[POSE_MIRROR_IDX] * POSE_MIRROR_SIGN):
        ok = ~(np.isnan(va) | np.isnan(cand))
        if int(ok.sum()) < POSE_MIN_ANGLES:
            continue
        d = np.abs(va[ok] - cand[ok])
        key = (float(d.mean()), float(d.max()))
        if best is None or key < best[0]:
            best = (key, d)
    return None if best is None else best[1]


def pose_angle_dist(a: Candidate, b: Candidate) -> tuple[float, float] | None:
    """(lệch góc trung bình, lệch góc lớn nhất) theo độ, có xét ảnh gương.

    Ảnh gương (dáng nhìn sang trái vs sang phải) được coi là **cùng dáng**: lấy
    min của hai cách so (giữ nguyên và lật trái-phải). Không có bước này thì mỗi
    lần đổi bên là thêm một ảnh trùng ý nghĩa.

    `max` là phần quan trọng nhất: trung bình 11 góc sẽ pha loãng "chỉ một tay giơ
    lên" (90°/11 ≈ 8°), trong khi `max` bắt được đúng 90°.

    Cần chi tiết từng khớp thì dùng `pose_angle_deltas`.
    """
    d = pose_angle_deltas(a, b)
    if d is None:
        return None
    return float(d.mean()), float(d.max())
