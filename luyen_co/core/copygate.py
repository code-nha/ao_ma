"""Chặn ảnh trùng thật bằng bằng chứng hình học (SIFT + RANSAC homography).

Ba trục hình học (cỡ cảnh / góc quay / dáng) trả lời câu hỏi *"hai ảnh này trông
giống nhau tới mức nào"* — một phép đo **mềm**, mỗi trục có vùng biên riêng, và
hai ảnh chỉ cần lệch **một** trục là thoát khỏi bộ lọc. Đo trên obj_1 (110 ảnh):
5–6 cặp trùng thật vẫn lọt, mỗi cặp thoát qua một trục khác nhau.

Cổng này hỏi câu khác hẳn: *"hai ảnh này có phải CÙNG MỘT khung hình không?"* —
và trả lời bằng bằng chứng hình học: bao nhiêu điểm đặc trưng khớp nhau **sau khi
ước lượng phép biến đổi đồng nhất bằng RANSAC**. Điểm khớp phải nhất quán với
một phép biến đổi toàn cục, nên nền trùng màu hay cùng bộ đồ không tạo ra bằng
chứng giả. Không phụ thuộc góc / cỡ cảnh / dáng, không cần model mới, không cần
nhãn, không cần GPU.

Vì sao không dùng CLIP cho việc này: CLIP là **embedding ngoại hình**, không phải
bộ dò bản sao. Đo trên 110 ảnh obj_1, tương quan hạng giữa CLIP và số inlier
SIFT chỉ **+0.25**; 3/5 cặp trùng thật có CLIP 0.745–0.832 (dưới ngưỡng 0.84),
trong khi 89 cặp **không** trùng có CLIP ≥ 0.84.

Vì sao chạy **xuyên nguồn**: hai kênh re-up cùng một sự kiện cho ra cùng một tấm
ảnh ở hai file khác nhau. Mọi bước dedupe khác đều scope theo `source` nên không
bao giờ nhìn thấy cặp đó (đo được 1 cặp CLIP 0.969, 77 inlier SIFT).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .select import _rank_key, _same_framing, pose_angle_deltas
from .types import Candidate

# cạnh dài của ảnh đưa vào SIFT: đủ chi tiết, đủ nhanh (110 ảnh ≈ 6 s)
FEATURE_SIDE = 384
# số đặc trưng tối đa mỗi ảnh — người bé trong khung vẫn còn vài trăm điểm
MAX_FEATURES = 512
# ngưỡng Lowe ratio-test: cặp khớp phải trội hơn hẳn cặp thứ hai
RATIO_TEST = 0.75
# cần chừng này cặp khớp tốt mới đủ để ước lượng homography (RANSAC cần ≥ 4)
MIN_MATCHES = 10
# sai số cho phép của một inlier khi ước lượng homography (px, trên ảnh 384)
RANSAC_REPROJ = 4.0

_SIFT = None


def _sift():
    """SIFT dùng chung, tạo một lần (khởi tạo tốn vài ms)."""
    global _SIFT
    if _SIFT is None:
        _SIFT = cv2.SIFT_create(nfeatures=MAX_FEATURES,
                                contrastThreshold=0.02, sigma=1.6)
    return _SIFT


def _read_gray(c: Candidate) -> np.ndarray | None:
    """Ảnh xám của crop người, đọc từ RAM hoặc từ file tạm.

    Pipeline stage crop ra đĩa rồi xoá `jpeg` để tiết kiệm RAM khi video dài
    (`c.staged`, pipeline.py:439), nên phải đọc lại từ đĩa — nếu chỉ dùng
    `c.jpeg` thì cổng này lặng lẽ không bắt được gì.
    """
    if c.jpeg:
        return cv2.imdecode(np.frombuffer(c.jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    p = c.staged
    if p is not None and Path(p).exists():
        return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_GRAYSCALE)
    return None


def _features(c: Candidate) -> tuple[np.ndarray | None, np.ndarray | None]:
    """(toạ độ keypoint, descriptor) của crop người; (None, None) nếu không đủ.

    Ảnh được thu về cạnh dài `FEATURE_SIDE` để phép so không phụ thuộc độ phân
    giải nguồn, và cân bằng sáng cục bộ (CLAHE) để hai bản nén khác nhau vẫn
    khớp được.
    """
    img = _read_gray(c)
    if img is None or img.size == 0:
        return None, None
    h, w = img.shape[:2]
    s = FEATURE_SIDE / max(h, w)
    if s < 1.0:
        img = cv2.resize(img, (max(1, int(round(w * s))), max(1, int(round(h * s)))),
                         interpolation=cv2.INTER_AREA)
    img = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(img)
    kp, des = _sift().detectAndCompute(img, None)
    if des is None or len(kp) < MIN_MATCHES:
        return None, None
    pts = np.float32([k.pt for k in kp]).reshape(-1, 1, 2)
    return pts, des


def copy_score(fa: tuple[np.ndarray | None, np.ndarray | None],
               fb: tuple[np.ndarray | None, np.ndarray | None]) -> tuple[int, float]:
    """(số inlier, tỉ lệ inlier) giữa hai ảnh — bằng chứng "cùng một khung hình".

    Inlier = cặp điểm khớp còn đúng sau khi ước lượng homography bằng RANSAC.
    Tỉ lệ chia cho **số keypoint ít hơn** của hai ảnh, nên ảnh nhỏ / ít chi tiết
    không bị phạt oan: cái được hỏi là "bao nhiêu phần của ảnh nghèo chi tiết hơn
    khớp được với ảnh kia".

    Đo trên obj_1: cặp trùng thật 97–242 inlier (tỉ lệ 0.23–0.60); cặp không
    trùng cao nhất 39 inlier (tỉ lệ 0.10).
    """
    pts_a, des_a = fa
    pts_b, des_b = fb
    if des_a is None or des_b is None:
        return 0, 0.0
    na, nb = len(pts_a), len(pts_b)
    if na < MIN_MATCHES or nb < MIN_MATCHES:
        return 0, 0.0
    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(des_a, des_b, k=2)
    good = [m for pair in matches if len(pair) == 2
            for m, n in (pair,) if m.distance < RATIO_TEST * n.distance]
    if len(good) < MIN_MATCHES:
        return 0, 0.0
    src = np.float32([pts_a[m.queryIdx, 0] for m in good])
    dst = np.float32([pts_b[m.trainIdx, 0] for m in good])
    _, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_REPROJ)
    if mask is None:
        return 0, 0.0
    inl = int(mask.sum())
    return inl, inl / float(min(na, nb))


def _pose_disagrees(a: Candidate, b: Candidate, max_mean: float, max_max: float) -> bool:
    """Hai ảnh cùng một khung hình thì dáng phải gần như y hệt.

    SIFT khớp được cả **phông nền**: hai frame cùng bối cảnh nhưng người đổi dáng
    vẫn cho 40–90 inlier (đo trên obj_1: cặp sofa ở 0.5 s / 5.0 s, hai dáng ngồi
    khác hẳn, 87 inlier). Nền khớp không chứng minh người trùng, nên dùng dáng làm
    điều kiện loại trừ: lệch quá mức thì **không** gộp, dù hình học khớp.

    Bất đối xứng có chủ ý: chỉ dùng để **cứu** ảnh (không gộp khi dáng khác), không
    dùng để gộp. Đo được góc → mới xét; không đo được (thiếu keypoint) thì để yên
    cho SIFT quyết, vì bỏ qua sẽ làm mất các cặp trùng thật ở cảnh xa.

    Kết luận dựa trên **số khớp lệch**, không dựa trung bình: một khớp lệch 114° kéo
    trung bình của 6 khớp lên 26.5° trong khi 5 khớp còn lại chỉ lệch 3–17° (median
    9.3) — đó là keypoint nhiễu của một cánh tay, không phải dáng khác. Vì vậy
    "khác dáng" = **≥ 2 khớp lệch > `max_max`** hoặc **median ≥ `max_mean`**.
    """
    d = pose_angle_deltas(a, b)
    if d is None:
        return False
    if int((d > max_max).sum()) >= 2:
        return True
    return float(np.median(d)) >= max_mean


def copy_veto(cands: list[Candidate], min_inl: int = 45, min_ratio: float = 0.06,
              cross_min_inl: int = 40, cross_min_ratio: float = 0.05,
              prefilter: float = 0.45,
              max_pose_mean: float = 12.0, max_pose_max: float = 30.0
              ) -> tuple[list[Candidate], list[tuple[Candidate, Candidate, int]]]:
    """Bỏ ảnh là **bản sao hình học** của một ảnh đã giữ, xuyên mọi nguồn.

    Duyệt theo chất lượng giảm dần (`_rank_key`): ảnh tốt hơn được giữ, ảnh sau
    bị bỏ nếu chứng minh được là cùng một khung hình với ảnh đã giữ. Nhờ duyệt
    theo hạng nên kết quả **không phụ thuộc thứ tự** candidate đầu vào.

    Hai mức ngưỡng vì ảnh cùng nguồn là cùng bản nén (khớp rất nhiều điểm), còn
    ảnh khác nguồn đã qua nén + re-encode nên mất chi tiết: đo được cặp trùng
    xuyên nguồn 77 inlier, trong khi cùng nguồn tới 242.

    Ngưỡng mặc định lấy từ đo trên 110 ảnh obj_1 với **chính** bộ đặc trưng này
    (SIFT 512 điểm, cạnh dài 384): cặp trùng thật 46–77 inlier, cặp không trùng
    cao nhất 39. `min_ratio` để rất thấp vì nó chỉ còn vai trò chặn ca suy biến
    (khớp được vài chục điểm trên ảnh cực ít chi tiết) — **inlier tuyệt đối** mới
    là tín hiệu tách hai lớp.

    `prefilter`: chỉ so SIFT khi hai ảnh cùng nguồn hoặc CLIP ≥ mức này — cắt
    phần lớn cặp chắc chắn khác nhau, giữ chi phí ~6 s cho 110 ảnh.

    Trả (danh sách giữ lại, danh sách cặp đã bỏ) để nơi gọi log được lý do.
    """
    feats: dict[int, tuple[np.ndarray | None, np.ndarray | None]] = {}

    def feat(c: Candidate):
        key = id(c)
        if key not in feats:
            feats[key] = _features(c)
        return feats[key]

    kept: list[Candidate] = []
    removed: list[tuple[Candidate, Candidate, int]] = []
    # `_rank_key` chỉ xét chất lượng (điểm mặt, cỡ người, độ nét); hai frame sát
    # nhau thường hoà ở cả ba, nên thêm (t, source) làm khoá phụ để kết quả
    # KHÔNG phụ thuộc thứ tự candidate đưa vào.
    for c in sorted(cands, key=lambda x: (_rank_key(x), x.t, x.source), reverse=True):
        dup_of = None
        dup_inl = 0
        for k in kept:
            same_source = k.source == c.source
            if not same_source:
                if c.clip_vec is None or k.clip_vec is None:
                    continue
                if float(np.dot(c.clip_vec, k.clip_vec)) < prefilter:
                    continue
            inl, ratio = copy_score(feat(c), feat(k))
            # "Cùng một khung hình" thì cỡ cảnh phải như nhau. Crop quanh người đã
            # chuẩn hoá kích thước, nên hai ảnh **khác zoom thật** (người ở xa vs
            # ở gần) vẫn cho 40–50 inlier trên crop — nếu không chặn, cặp 12.0 s /
            # 17.0 s của v1.mp4 (người ở xa vs gần, 47 inlier, scale 1.26) bị gộp
            # oan và mất một cỡ cảnh khỏi dataset.
            if not _same_framing(c, k):
                continue
            if same_source:
                if inl >= min_inl and ratio >= min_ratio:
                    if _pose_disagrees(c, k, max_pose_mean, max_pose_max):
                        continue          # cùng nền nhưng khác dáng: không phải bản sao
                    dup_of, dup_inl = k, inl
                    break
            elif inl >= cross_min_inl and ratio >= cross_min_ratio:
                dup_of, dup_inl = k, inl
                break
        if dup_of is not None:
            removed.append((c, dup_of, dup_inl))
            continue
        kept.append(c)
    kept.sort(key=lambda c: (c.source, c.t))
    return kept, removed
