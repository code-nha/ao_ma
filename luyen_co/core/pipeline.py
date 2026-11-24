"""Pipeline chính: đọc folder đầu vào, xác thực người theo ảnh tham chiếu,
chọn frame và xuất crop + metadata.

Luồng chạy:
  1. Phân tích ảnh tham chiếu → embedding mặt (ArcFace) + embedding toàn thân (CLIP).
  2. Từng video: lấy mẫu frame theo --fps, YOLOv8-pose tìm người, tracker gán track.
     Mỗi person crop: chất lượng (kích thước, độ nét) → mặt (SCRFD + ArcFace) →
     toàn thân (CLIP) → lưu vào buffer của track.
  3. Khi track kết thúc: quyết định danh tính theo CẢ track (mặt tốt nhất + body
     trung vị) rồi mới nhận các frame của track đó.
  4. Gộp mọi frame nhận được, lọc trùng (thời gian + ngoại hình), tuỳ chọn chọn
     N frame đa dạng nhất, rồi ghi ảnh + metadata.jsonl + report.
"""

from __future__ import annotations

import csv
import math
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import cv2

from .arcface import FaceEmbedder, cosine
from .frames import iter_video, list_inputs
from .onnx_models import POSE_MODEL, ensure_models, log
from .reid import BodyEmbedder
from .scrfd import FaceDetector
from .select import dedupe, head_pose, pick_diverse, pose_vector, yaw_histogram
from .tracker import IoUTracker
from .types import Candidate
from .utils import (crop_xyxy, encode_jpeg, expand_box, laplacian_var, read_image,
                    write_image)
from .yolo_pose import PersonDetector


@dataclass
class Config:
    ref: Path
    out: Path
    fps: float = 2.0
    face_th: float = 0.45
    body_th: float = 0.72
    min_person: int = 64
    min_person_score: float = 0.5
    min_blur: float = 25.0
    crop_margin: float = 0.12
    dup_sim: float = 0.97
    min_gap: float = 0.35
    limit: int = 0
    device: str = "auto"
    imgsz: int = 640
    conf: float = 0.35
    face_conf: float = 0.5
    max_frames: int = 0
    start: float = 0.0
    end: float | None = None
    min_track: int = 3
    allow_body_only: bool = False
    max_per_track: int = 300
    sheet: int = 60
    jpeg_quality: int = 95

    @property
    def crops_dir(self) -> Path:
        return self.out / "crops"


@dataclass
class Stats:
    videos: int = 0
    images: int = 0
    frames: int = 0
    persons: int = 0
    candidates: int = 0
    tracks: int = 0
    accepted_tracks: int = 0
    accepted: int = 0
    selected: int = 0
    track_face: list[float] = field(default_factory=list)
    track_body: list[float] = field(default_factory=list)


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)


class Pipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        ensure_models()
        self.detector = PersonDetector(POSE_MODEL, cfg.device, conf=cfg.conf, imgsz=cfg.imgsz)
        self.face_det = FaceDetector(device=cfg.device, conf=cfg.face_conf)
        self.face_emb = FaceEmbedder(device=cfg.device)
        self.body_emb = BodyEmbedder(device=cfg.device)
        self.stats = Stats()
        self.accepted: list[Candidate] = []
        self.ref_face: np.ndarray | None = None
        self.ref_body: np.ndarray | None = None
        self.ref_note = ""
        self._load_ref()

    # ------------------------------------------------------------------ tham chiếu
    def _load_ref(self) -> None:
        img = read_image(self.cfg.ref)
        if img is None:
            raise FileNotFoundError(f"không đọc được ảnh tham chiếu: {self.cfg.ref}")
        h, w = img.shape[:2]
        persons = self.detector.detect(img)
        if persons:
            person = max(persons, key=lambda p: (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]))
            box = person.box
        else:
            box = np.array([0, 0, w - 1, h - 1], dtype=np.float32)
        crop = crop_xyxy(img, expand_box(box, 0.2, w, h))
        self.ref_body = self.body_emb.embed(crop) if crop.size else None

        faces = self.face_det.detect(crop if crop.size else img)
        if not faces:
            faces = self.face_det.detect(img)
        if faces:
            face = max(faces, key=lambda f: (f.box[2] - f.box[0]) * (f.box[3] - f.box[1]))
            self.ref_face = self.face_emb.embed_face(crop if crop.size else img, face.kps)
        self.ref_note = (f"tham chiếu: {w}×{h}, người={'có' if persons else 'không'}, "
                         f"mặt={'có' if self.ref_face is not None else 'KHÔNG'}")
        if self.ref_face is None:
            log("cảnh báo: ảnh tham chiếu không phát hiện được mặt → chỉ so khớp toàn thân "
                "(nên dùng ảnh thấy rõ mặt để chính xác hơn)")

    # ------------------------------------------------------------------ frame
    def _match_person(self, frame: np.ndarray, person, t: float, frame_idx: int,
                      source: str, kind: str, track_id: int) -> Candidate | None:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = person.box
        person_h = int(y2 - y1)
        if person_h < self.cfg.min_person or (x2 - x1) < 12:
            return None
        if person.score < self.cfg.min_person_score:
            return None

        box = expand_box(person.box, self.cfg.crop_margin, w, h)
        crop = crop_xyxy(frame, box)
        if crop.size == 0:
            return None
        blur = laplacian_var(crop)
        if blur < self.cfg.min_blur:
            return None

        # mặt: tìm trong vùng crop nới rộng để SCRFD có thêm ngữ cảnh
        ctx_box = expand_box(person.box, 0.25, w, h)
        ctx = crop_xyxy(frame, ctx_box)
        faces = self.face_det.detect(ctx) if ctx.size else []
        best_face, face_sim = None, -1.0
        yaw = pitch = 0.0
        if faces:
            def rank(f):
                up = 1.5 if (f.box[1] + f.box[3]) / 2 < ctx_box[1] + 0.6 * (ctx_box[3] - ctx_box[1]) else 1.0
                return (f.box[2] - f.box[0]) * (f.box[3] - f.box[1]) * f.score * up

            best_face = max(faces, key=rank)
            face_sim = cosine(self.ref_face, self.face_emb.embed_face(ctx, best_face.kps))
            yaw, pitch = head_pose(best_face.kps)

        clip_vec = self.body_emb.embed(crop)
        body_sim = cosine(self.ref_body, clip_vec)

        return Candidate(
            source=source, kind=kind, t=float(t), frame_idx=frame_idx, track_id=track_id,
            box=person.box, person_score=person.score, face_sim=face_sim, body_sim=body_sim,
            yaw=float(yaw), pitch=float(pitch), blur=float(blur), person_h=person_h,
            jpeg=encode_jpeg(crop, self.cfg.jpeg_quality),
            kpts=person.kpts, clip_vec=clip_vec,
            pose_vec=pose_vector(person.kpts, person.box),
        )

    def _accept(self, buf: list[Candidate]) -> tuple[list[Candidate], float, float]:
        """Quyết định theo track nhưng giữ/bỏ từng frame (không nhận cả track).

        - Frame thấy mặt khớp (>= face_th) → nhận.
        - Frame không thấy mặt chỉ được nhận khi track đã được xác nhận bằng
          ít nhất 1 frame thấy mặt, VÀ ngoại hình đủ giống (body_sim >= body_th).
        - Ảnh tham chiếu không có mặt (vd. chụp từ phía sau): chỉ dùng body,
          đòi hỏi trung vị body của cả track đủ cao.
        """
        cfg = self.cfg
        face_max = max((c.face_sim for c in buf if c.has_face), default=-1.0)
        body_med = float(statistics.median([c.body_sim for c in buf])) if buf else -1.0
        confirmed = self.ref_face is not None and face_max >= cfg.face_th

        if self.ref_face is None:
            # tham chiếu không có mặt → buộc phải dựa vào toàn thân
            kept = ([c for c in buf if c.body_sim >= cfg.body_th]
                    if body_med >= cfg.body_th and len(buf) >= cfg.min_track else [])
        elif confirmed:
            kept = [c for c in buf
                    if c.face_sim >= cfg.face_th
                    or (not c.has_face and c.body_sim >= cfg.body_th)]
        elif cfg.allow_body_only and body_med >= cfg.body_th and len(buf) >= cfg.min_track:
            # track không có frame nào khớp mặt: chỉ nhận khi người dùng cho phép,
            # dễ nhầm người mặc giống → mặc định tắt
            kept = [c for c in buf if c.body_sim >= cfg.body_th]
        else:
            kept = []
        return kept, face_max, body_med

    def _flush(self, tid: int, buf: list[Candidate]) -> None:
        if not buf:
            return
        kept, face_max, body_med = self._accept(buf)
        self.stats.tracks += 1
        self.stats.track_face.append(face_max)
        self.stats.track_body.append(body_med)
        if not kept:
            return
        self.stats.accepted_tracks += 1
        self.stats.accepted += len(kept)
        self.accepted.extend(kept)
        log(f"  track {tid}: nhận {len(kept)}/{len(buf)} frame "
            f"(mặt max {face_max:.2f}, body med {body_med:.2f})")

    def _add(self, tid: int, buf: list[Candidate], cand: Candidate) -> None:
        if len(buf) < self.cfg.max_per_track:
            buf.append(cand)
        elif cand.face_sim > buf[0].face_sim:
            buf.pop(0)
            buf.append(cand)

    # ------------------------------------------------------------------ video
    @staticmethod
    def _hist(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        return hist, gray

    @staticmethod
    def _is_cut(prev: tuple[np.ndarray, np.ndarray], cur: tuple[np.ndarray, np.ndarray]) -> bool:
        """Đổi cảnh: histogram đổi mạnh hoặc khung hình khác hẳn từng pixel."""
        corr = cv2.compareHist(prev[0], cur[0], cv2.HISTCMP_CORREL)
        diff = float(np.mean(np.abs(prev[1] - cur[1])))
        return corr < 0.4 or diff > 0.18

    def process_video(self, path: Path) -> None:
        cfg = self.cfg
        max_age = max(3, int(round(cfg.fps * 2)))
        tracker = IoUTracker(max_age=max_age)
        buffers: dict[int, list[Candidate]] = defaultdict(list)
        self.stats.videos += 1
        frame_idx = 0
        n_persons = 0
        cuts = 0
        prev_hist = None
        started = time.time()
        log(f"video {path.name} …")
        for t, frame in iter_video(path, cfg.fps, cfg.start, cfg.end):
            frame_idx += 1
            if cfg.max_frames and frame_idx > cfg.max_frames:
                break
            self.stats.frames += 1

            # đổi cảnh → chốt track cũ, tránh gộp 2 người khác nhau vào 1 track
            hist = self._hist(frame)
            if prev_hist is not None and self._is_cut(prev_hist, hist):
                for tid in list(buffers):
                    self._flush(tid, buffers.pop(tid))
                tracker = IoUTracker(max_age=max_age)
                cuts += 1
            prev_hist = hist

            persons = self.detector.detect(frame)
            if persons:
                ids = tracker.update(np.stack([p.box for p in persons]))
                for person, tid in zip(persons, ids):
                    n_persons += 1
                    self.stats.persons += 1
                    cand = self._match_person(frame, person, t, frame_idx, str(path), "video", tid)
                    if cand is not None:
                        self.stats.candidates += 1
                        self._add(tid, buffers[tid], cand)
            else:
                tracker.update(np.empty((0, 4), np.float32))

            for tid in tracker.stale():
                self._flush(tid, buffers.pop(tid, []))
                tracker.drop(tid)

            if frame_idx % 100 == 0:
                el = time.time() - started
                log(f"  {frame_idx} frame ({t:.0f}s) · {n_persons} người · "
                    f"{el / max(1, frame_idx):.3f}s/frame")

        for tid in list(buffers):
            self._flush(tid, buffers.pop(tid))
        log(f"xong {path.name}: {frame_idx} frame, {cuts} lần đổi cảnh, "
            f"{time.time() - started:.0f}s")

    # ------------------------------------------------------------------ ảnh lẻ
    def process_image(self, path: Path) -> None:
        img = read_image(path)
        if img is None:
            return
        self.stats.images += 1
        self.stats.frames += 1
        persons = self.detector.detect(img)
        if not persons:
            return
        best = max(persons, key=lambda p: (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]))
        cand = self._match_person(img, best, 0.0, 0, str(path), "image", 0)
        if cand is None:
            return
        self.stats.persons += 1
        self.stats.candidates += 1
        buf = [cand]
        self._flush(0, buf)

    # ------------------------------------------------------------------ chạy
    def run(self, input_dir: Path, recursive: bool = False) -> None:
        self._input_dir = input_dir
        videos, images = list_inputs(input_dir, recursive)
        if not videos and not images:
            raise SystemExit(f"không tìm thấy ảnh/video trong {input_dir}")
        log(f"{len(videos)} video, {len(images)} ảnh · backend {self.detector.backend}")
        for v in videos:
            self.process_video(v)
        for i in images:
            self.process_image(i)

    # ------------------------------------------------------------------ xuất
    def export(self) -> list[tuple[Candidate, Path]]:
        cfg = self.cfg
        cfg.crops_dir.mkdir(parents=True, exist_ok=True)
        cands = dedupe(self.accepted, cfg.dup_sim, cfg.min_gap)
        if cfg.limit and cfg.limit < len(cands):
            cands = pick_diverse(cands, cfg.limit)
            cands.sort(key=lambda c: (c.source, c.t))
        self.selected_cands = cands
        self.stats.selected = len(cands)

        rows: list[tuple[Candidate, Path]] = []
        used: set[str] = set()
        for c in cands:
            stem = _safe(Path(c.source).stem)
            if c.kind == "image":
                name = f"{stem}__img.jpg"
            else:
                name = f"{stem}__{int(round(c.t * 1000)):09d}ms__t{c.track_id:03d}.jpg"
            base, name = name, name
            n = 1
            while name in used:
                n += 1
                name = f"{base[:-4]}_{n}.jpg"
            used.add(name)
            dst = cfg.crops_dir / name
            dst.write_bytes(c.jpeg)
            rows.append((c, dst))

        self._write_metadata(rows)
        self._write_report()
        self._write_sheet(rows)
        return rows

    def _write_metadata(self, rows: list[tuple[Candidate, Path]]) -> None:
        import json

        with open(self.cfg.out / "metadata.jsonl", "w", encoding="utf-8") as fh:
            for c, dst in rows:
                fh.write(json.dumps({
                    "path": str(dst.relative_to(self.cfg.out)).replace("\\", "/"),
                    "source": c.source, "kind": c.kind, "t": round(c.t, 3),
                    "frame": c.frame_idx, "track": c.track_id,
                    "box": [round(float(v), 1) for v in c.box],
                    "person_score": round(c.person_score, 4),
                    "face_sim": round(c.face_sim, 4) if c.has_face else None,
                    "body_sim": round(c.body_sim, 4),
                    "yaw": round(c.yaw, 1), "pitch": round(c.pitch, 1),
                    "blur": round(c.blur, 1), "person_h": c.person_h,
                    "crop_margin": self.cfg.crop_margin,
                }, ensure_ascii=False) + "\n")

    def _write_report(self) -> None:
        cfg, st = self.cfg, self.stats
        lines = [
            "luyen_co — báo cáo lọc frame theo người tham chiếu",
            f"thời điểm: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"tham chiếu: {cfg.ref}  ({self.ref_note})",
            f"input: {self._input_dir}  ·  {st.videos} video, {st.images} ảnh",
            f"frame đã xử lý: {st.frames} · người phát hiện: {st.persons} · "
            f"ứng viên qua lọc chất lượng: {st.candidates}",
            f"track: {st.tracks} · nhận: {st.accepted_tracks} · "
            f"frame thô: {st.accepted} · sau lọc trùng: {st.selected}",
            f"tham số: fps={cfg.fps} face_th={cfg.face_th} body_th={cfg.body_th} "
            f"min_person={cfg.min_person} min_blur={cfg.min_blur} "
            f"dup_sim={cfg.dup_sim} limit={cfg.limit}",
            "",
        ]
        if st.track_face:
            fv = [v for v in st.track_face if v >= 0]
            bv = st.track_body
            lines.append(f"face_sim theo track: {len(fv)} track có mặt, "
                         f"max={max(fv, default=0):.2f}, min={min(fv, default=0):.2f}")
            lines.append(f"body_sim theo track: max={max(bv, default=0):.2f}, "
                         f"min={min(bv, default=0):.2f}")
            lines.append("phân bố face_sim (để chỉnh --face-th):")
            lines.extend(f"  ≥ {th:.2f}: {sum(1 for v in fv if v >= th)} track"
                         for th in (0.55, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25))
            lines.append("phân bố body_sim (để chỉnh --body-th):")
            lines.extend(f"  ≥ {th:.2f}: {sum(1 for v in bv if v >= th)} track"
                         for th in (0.85, 0.8, 0.75, 0.7, 0.65, 0.6))
        lines.append("")
        lines.append("độ phủ góc đầu của ảnh đã chọn:")
        lines.extend(f"  {label:12s} {n:5d}" for label, n in yaw_histogram(self.selected_cands))
        (self.cfg.out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

        by_source: dict[str, int] = defaultdict(int)
        for c in self.selected_cands:
            by_source[c.source] += 1
        with open(self.cfg.out / "report.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["source", "selected"])
            for src, n in by_source.items():
                w.writerow([src, n])

    def _write_sheet(self, rows: list[tuple[Candidate, Path]]) -> None:
        if not self.cfg.sheet or not rows:
            return
        cols, cell, pad = 6, 180, 24
        items = rows[: self.cfg.sheet]
        n_rows = math.ceil(len(items) / cols)
        sheet = np.full((n_rows * (cell + pad + 14), cols * cell, 3), 255, np.uint8)
        for i, (c, dst) in enumerate(items):
            img = cv2.imdecode(np.fromfile(str(dst), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            h, w = img.shape[:2]
            s = min(cell / w, cell / h)
            thumb = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
            r, col = divmod(i, cols)
            y0, x0 = r * (cell + pad + 14), col * cell
            sheet[y0:y0 + thumb.shape[0], x0:x0 + thumb.shape[1]] = thumb
            label = f"{c.t:8.1f}s yaw{c.yaw:+.0f}"
            cv2.putText(sheet, label, (x0 + 2, y0 + cell + 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (30, 30, 30), 1, cv2.LINE_AA)
        write_image(self.cfg.out / "sheet.jpg", sheet, 90)
