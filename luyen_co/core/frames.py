"""Đọc frame video theo nhịp cố định (mặc định 2 fps) và đọc ảnh rời.

PyAV giải mã bằng ffmpeg nên đọc được hầu hết container CCTV (H.264/H.265,
MPEG-TS, .dav, .mkv…). Nếu PyAV lỗi thì fallback sang OpenCV.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".ts", ".m2ts", ".mpg", ".mpeg",
              ".flv", ".wmv", ".webm", ".m4v", ".3gp", ".dav", ".264", ".h264", ".h265"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def list_inputs(folder: Path, recursive: bool = False) -> tuple[list[Path], list[Path]]:
    """(danh sách video, danh sách ảnh) trong folder, đã sort."""
    it = folder.rglob("*") if recursive else folder.glob("*")
    videos, images = [], []
    for p in sorted(it):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in VIDEO_EXTS:
            videos.append(p)
        elif ext in IMAGE_EXTS:
            images.append(p)
    return videos, images


def _iter_av(path: Path, fps: float, start: float, end: float | None) -> Iterator[tuple[float, np.ndarray]]:
    import av

    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        tb = stream.time_base
        if start > 0 and tb is not None:
            try:
                container.seek(int(start / tb), stream=stream, backward=True)
            except Exception:
                pass
        next_t = max(0.0, start)
        step = 1.0 / fps
        for frame in container.decode(stream):
            t = frame.time
            if t is None and frame.pts is not None and tb is not None:
                t = float(frame.pts * tb)
            if t is None:
                continue
            t = float(t)
            if t + 1e-6 < start:
                continue
            if end is not None and t > end:
                break
            if t + 1e-6 >= next_t:
                yield t, frame.to_ndarray(format="bgr24")
                next_t += step
    finally:
        container.close()


def _iter_cv(path: Path, fps: float, start: float, end: float | None) -> Iterator[tuple[float, np.ndarray]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if start > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
    step = 1.0 / fps
    next_t = max(0.0, start)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if t <= 0:
                t = next_t
            if end is not None and t > end:
                break
            if t + 1e-6 >= next_t:
                yield t, frame
                next_t = max(next_t + step, t + 1e-3)
    finally:
        cap.release()


def iter_video(path: Path, fps: float = 2.0, start: float = 0.0,
               end: float | None = None) -> Iterator[tuple[float, np.ndarray]]:
    """Sinh (giây, frame BGR) theo nhịp `fps`."""
    try:
        gen = _iter_av(path, fps, start, end)
        first = next(gen)
    except StopIteration:
        return
    except Exception:
        gen, first = None, None

    if gen is not None and first is not None:
        yield first
        for item in gen:
            yield item
        return

    for item in _iter_cv(path, fps, start, end):
        yield item


def video_duration(path: Path) -> float:
    """Độ dài video (giây), 0 nếu không đọc được."""
    try:
        import av

        with av.open(str(path)) as container:
            if container.duration:
                return float(container.duration) / 1_000_000
            stream = container.streams.video[0]
            if stream.duration and stream.time_base:
                return float(stream.duration * stream.time_base)
    except Exception:
        pass
    cap = cv2.VideoCapture(str(path))
    try:
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        f = cap.get(cv2.CAP_PROP_FPS) or 0
        return float(n / f) if n > 0 and f > 0 else 0.0
    finally:
        cap.release()
