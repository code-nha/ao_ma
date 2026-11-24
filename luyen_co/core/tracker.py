"""Tracker IoU + khoảng cách tâm, đủ dùng cho frame lấy mẫu thưa (1–5 fps).

Mục đích không phải tracking chuẩn xác mà là gom các detection của cùng một
người thành 1 track để (a) quyết định danh tính theo cả track thay vì từng
frame, (b) tránh xuất 50 ảnh giống nhau của cùng một lúc.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .utils import box_iou_center_dist


@dataclass
class Track:
    id: int
    box: np.ndarray
    hits: int = 1
    missed: int = 0


class IoUTracker:
    def __init__(self, iou_th: float = 0.3, max_dist: float = 0.8, max_age: int = 20):
        self.iou_th = iou_th
        self.max_dist = max_dist
        self.max_age = max_age
        self.tracks: dict[int, Track] = {}
        self._next = 1

    def update(self, boxes: np.ndarray) -> list[int]:
        """Trả về track id cho từng box (thứ tự giữ nguyên)."""
        ids = [-1] * len(boxes)
        if len(boxes) == 0:
            for tr in self.tracks.values():
                tr.missed += 1
            return ids

        # điểm ghép = IoU + thưởng khi tâm gần nhau
        pairs: list[tuple[float, int, int]] = []
        for tid, tr in self.tracks.items():
            for j, box in enumerate(boxes):
                iou, dist = box_iou_center_dist(tr.box, box)
                if iou < self.iou_th and dist > self.max_dist:
                    continue
                score = iou + 0.5 * max(0.0, 1.0 - dist)
                pairs.append((score, tid, j))
        pairs.sort(reverse=True)

        used_tr: set[int] = set()
        for score, tid, j in pairs:
            if tid in used_tr or ids[j] != -1:
                continue
            tr = self.tracks[tid]
            tr.box = boxes[j]
            tr.hits += 1
            tr.missed = 0
            ids[j] = tid
            used_tr.add(tid)

        for j, box in enumerate(boxes):
            if ids[j] == -1:
                tid = self._next
                self._next += 1
                self.tracks[tid] = Track(id=tid, box=box)
                ids[j] = tid

        for tid, tr in self.tracks.items():
            if tid not in used_tr and ids.count(tid) == 0:
                tr.missed += 1
        return ids

    def stale(self) -> list[int]:
        """Track đã mất dấu quá max_age frame (nên flush và bỏ)."""
        return [tid for tid, tr in self.tracks.items() if tr.missed > self.max_age]

    def drop(self, tid: int) -> None:
        self.tracks.pop(tid, None)
