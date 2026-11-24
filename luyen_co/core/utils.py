"""Tiện ích ảnh, hình học và I/O dùng chung cho pipeline luyen_co."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


# ---------------------------------------------------------------- đọc / ghi ảnh
# cv2.imread/imwrite dùng ANSI trên Windows nên chết với đường dẫn có dấu tiếng
# Việt; đi qua numpy.fromfile / tofile thì an toàn.


def read_image(path: str | Path) -> np.ndarray | None:
    """Đọc ảnh BGR, trả None nếu không đọc được."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None
    return img


def write_image(path: str | Path, img: np.ndarray, quality: int = 95) -> bool:
    """Ghi ảnh BGR ra file (hỗ trợ đường dẫn Unicode)."""
    path = Path(path)
    ext = path.suffix or ".jpg"
    ok, buf = cv2.imencode(ext, img, [cv2.IMWRITE_JPEG_QUALITY, quality]
                           if ext.lower() in (".jpg", ".jpeg") else [])
    if not ok:
        return False
    buf.tofile(str(path))
    return True


def encode_jpeg(img: np.ndarray, quality: int = 95) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


# -------------------------------------------------------------------- hình học


def letterbox(img: np.ndarray, size: int, pad_color: tuple[int, int, int] = (114, 114, 114)):
    """Resize giữ tỉ lệ rồi pad thành size×size. Trả (ảnh, ratio, left, top)."""
    h, w = img.shape[:2]
    ratio = min(size / h, size / w)
    nh, nw = max(1, int(round(h * ratio))), max(1, int(round(w * ratio)))
    interp = cv2.INTER_AREA if ratio < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(img, (nw, nh), interpolation=interp)
    out = np.full((size, size, 3), pad_color, dtype=np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    out[top:top + nh, left:left + nw] = resized
    return out, ratio, left, top


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU giữa 2 tập box xyxy."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    ax1, ay1, ax2, ay2 = a[:, 0:1], a[:, 1:2], a[:, 2:3], a[:, 3:4]
    bx1, by1, bx2, by2 = b[None, :, 0], b[None, :, 1], b[None, :, 2], b[None, :, 3]
    ix1, iy1 = np.maximum(ax1, bx1), np.maximum(ay1, by1)
    ix2, iy2 = np.minimum(ax2, bx2), np.minimum(ay2, by2)
    iw, ih = np.clip(ix2 - ix1, 0, None), np.clip(iy2 - iy1, 0, None)
    inter = iw * ih
    area_a = np.clip(a[:, 2] - a[:, 0], 0, None) * np.clip(a[:, 3] - a[:, 1], 0, None)
    area_b = np.clip(b[:, 2] - b[:, 0], 0, None) * np.clip(b[:, 3] - b[:, 1], 0, None)
    union = area_a[:, None] + area_b[None, :] - inter
    return inter / np.maximum(union, 1e-9)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_th: float) -> np.ndarray:
    """NMS trả về index giữ lại (đã sort theo score giảm dần)."""
    if len(boxes) == 0:
        return np.empty((0,), dtype=np.int64)
    order = np.argsort(-scores)
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        ious = iou_matrix(boxes[i:i + 1], boxes[order[1:]])[0]
        order = order[1:][ious <= iou_th]
    return np.asarray(keep, dtype=np.int64)


def nms_containment(boxes: np.ndarray, scores: np.ndarray, iou_th: float = 0.5,
                    contain_th: float = 0.8) -> np.ndarray:
    """NMS + gộp box bị box khác "nuốt" phần lớn.

    Khi chạy theo tile, cùng một người có thể ra nhiều box lệch nhau (đầu/thân),
    IoU thấp nên NMS thường không gộp; box nhỏ nằm gần trọn trong box lớn thì bỏ.
    """
    if len(boxes) == 0:
        return np.empty((0,), dtype=np.int64)
    order = np.argsort(-scores)
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        ious = iou_matrix(boxes[i:i + 1], boxes[rest])[0]
        # phần diện tích box còn lại nằm trong box đang giữ
        inter = ious * (np.clip(boxes[rest, 2] - boxes[rest, 0], 0, None)
                        * np.clip(boxes[rest, 3] - boxes[rest, 1], 0, None))
        area_rest = np.clip(boxes[rest, 2] - boxes[rest, 0], 0, None) * \
            np.clip(boxes[rest, 3] - boxes[rest, 1], 0, None)
        contained = inter / np.maximum(area_rest, 1e-9)
        order = rest[(ious <= iou_th) & (contained <= contain_th)]
    return np.asarray(keep, dtype=np.int64)


def clip_box(box: np.ndarray, w: int, h: int) -> np.ndarray:
    return np.array([max(0.0, box[0]), max(0.0, box[1]),
                     min(float(w - 1), box[2]), min(float(h - 1), box[3])], dtype=np.float32)


def expand_box(box: np.ndarray, margin: float, w: int, h: int) -> np.ndarray:
    """Nới box theo % cạnh dài hơn, rồi kẹp trong khung."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    dx, dy = bw * margin, bh * margin
    return clip_box(np.array([box[0] - dx, box[1] - dy, box[2] + dx, box[3] + dy]), w, h)


def box_iou_center_dist(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """(IoU, khoảng cách tâm chuẩn hoá theo kích thước trung bình)."""
    iou = float(iou_matrix(a[None], b[None])[0, 0])
    aw, ah = a[2] - a[0], a[3] - a[1]
    bw, bh = b[2] - b[0], b[3] - b[1]
    ca = np.array([(a[0] + a[2]) / 2, (a[1] + a[3]) / 2])
    cb = np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
    scale = max(1.0, (aw + ah + bw + bh) / 4)
    return iou, float(np.linalg.norm(ca - cb) / scale)


def box_area(b: np.ndarray) -> float:
    return float(max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]))


def others_area_fraction(crop_box: np.ndarray, others: list[np.ndarray]) -> float:
    """Phần diện tích crop bị người khác chiếm (0–1), để loại frame nhiều người."""
    area = box_area(crop_box)
    if area <= 0:
        return 1.0
    covered = 0.0
    for o in others:
        ix1 = max(crop_box[0], o[0])
        iy1 = max(crop_box[1], o[1])
        ix2 = min(crop_box[2], o[2])
        iy2 = min(crop_box[3], o[3])
        if ix2 > ix1 and iy2 > iy1:
            covered += (ix2 - ix1) * (iy2 - iy1)
    return min(1.0, covered / area)


def laplacian_var(img: np.ndarray) -> float:
    """Độ nét tương đối (variance of Laplacian) trên ảnh xám."""
    if img.size == 0:
        return 0.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def crop_xyxy(img: np.ndarray, box: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 0, 3), dtype=np.uint8)
    return img[y1:y2, x1:x2].copy()


def l2norm(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v
