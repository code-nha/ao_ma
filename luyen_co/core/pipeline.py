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
import shutil
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import cv2

from .arcface import FaceEmbedder, cosine
from .frames import iter_video, list_inputs, video_duration
from .onnx_models import POSE_MODEL, ensure_models, log
from .reid import BodyEmbedder, hist_similarity, torso_hist
from .scrfd import FaceDetector
from .select import (coverage_pick, dedupe, distinct_pose_pick, diverse_gate,
                     drop_similar, drop_tiny_frames, head_pose,
                     keep_best_body_tracks, pick_diverse, pose_vector, yaw_bucket,
                     yaw_histogram)
from .tracker import IoUTracker
from .types import Candidate
from .utils import (crop_xyxy, encode_jpeg, expand_box, iou_matrix, laplacian_var,
                    others_area_fraction, read_image, write_image)
from .yolo_pose import PersonDetector


@dataclass
class Config:
    refs: list[Path]
    out: Path
    fps: float = 2.0
    face_th: float = 0.40
    body_th: float = 0.72
    color_th: float = 0.3
    min_person: int = 64
    min_person_score: float = 0.5
    max_overlap: float = 0.35
    max_other_area: float = 0.10
    min_blur: float = 25.0
    crop_margin: float = 0.12
    save: str = "full"              # full | crop | both
    min_yaw: float = 25.0           # chênh góc camera tối thiểu giữa 2 ảnh giữ lại
    min_pose: float = 0.08          # chênh pose keypoint tối thiểu (0–1)
    confirm_window: float = 0.0     # giây: 0 = không giới hạn (neo theo video)
    anchor_th: float = 0.60         # cosine với "neo" (ngoại hình đã xác nhận trong video)
    select: str = "coverage"        # coverage = đủ góc; diversity = ngưỡng yaw/pose
    per_bucket: int = 3             # số ảnh tối đa mỗi nhóm góc (coverage); bước lọc tư thế sẽ tỉa
    dup_sim: float = 0.97
    min_gap: float = 0.35
    limit: int = 0
    device: str = "auto"
    imgsz: int = 640
    tiles: int = 1
    conf: float = 0.35
    face_conf: float = 0.5
    max_frames: int = 0
    start: float = 0.0
    end: float | None = None
    min_track: int = 3
    allow_body_only: bool = False
    body_only_low: float = 0.45     # sàn body_sim khi chỉ có toàn thân
    body_only_rel: float = 0.85     # giữ track có body_sim >= rel × track tốt nhất
    skip_ref: bool = True
    max_per_track: int = 300
    sheet: int = 60
    clean: bool = False
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
    # (face_max, body_med, face_sims từng frame, body_sims từng frame) để ước lượng
    # số frame nhận được ở các ngưỡng khác nhau mà không phải quét lại
    track_scores: list[tuple[float, float, list[float], list[float]]] = field(default_factory=list)


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)


class Pipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        ensure_models()
        self.detector = PersonDetector(POSE_MODEL, cfg.device, conf=cfg.conf,
                                       imgsz=cfg.imgsz, tiles=cfg.tiles)
        self.face_det = FaceDetector(device=cfg.device, conf=cfg.face_conf)
        self.face_emb = FaceEmbedder(device=cfg.device)
        self.body_emb = BodyEmbedder(device=cfg.device)
        self.stats = Stats()
        self.accepted: list[Candidate] = []
        # mốc thời gian đã xác nhận mặt (mỗi nguồn), để nhận cả frame quay lưng
        self.confirmed: dict[str, list[list[float]]] = {}
        # "neo" ngoại hình theo từng video: lấy từ track đã khớp mặt
        self.anchors: dict[str, dict] = {}
        # nhiều ảnh tham chiếu: so với cả bộ, lấy điểm cao nhất (đối tượng có thể
        # xuất hiện nhiều lần, nhiều năm, nhiều trang phục/góc khác nhau)
        self.ref_faces: list[np.ndarray] = []
        self.ref_bodies: list[np.ndarray] = []
        self.ref_torsos: list[np.ndarray] = []
        self.ref_note = ""
        self.ref_warnings: list[str] = []
        self.ref_info: dict = {}
        self._ref_paths = {p.resolve() for p in cfg.refs}
        self._staging = cfg.out / ".staging"
        self._stage_idx = 0
        self._frame_cache: tuple[tuple[str, int], bytes] | None = None
        self._load_refs()

    # ------------------------------------------------------------------ tham chiếu
    def _load_refs(self) -> None:
        loaded = 0
        for ref_path in self.cfg.refs:
            img = read_image(ref_path)
            if img is None:
                self.ref_warnings.append(f"không đọc được ảnh tham chiếu: {ref_path}")
                continue
            h, w = img.shape[:2]
            persons = self.detector.detect(img)
            if persons:
                person = max(persons, key=lambda p: (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]))
                box = person.box
            else:
                box = np.array([0, 0, w - 1, h - 1], dtype=np.float32)
            crop = crop_xyxy(img, expand_box(box, 0.2, w, h))
            tight = crop_xyxy(img, box) if crop.size else crop
            body = self.body_emb.embed(tight) if tight.size else None
            torso = torso_hist(tight) if tight.size else None
            if body is not None:
                self.ref_bodies.append(body)
            if torso is not None:
                self.ref_torsos.append(torso)

            faces = self.face_det.detect(crop if crop.size else img)
            if not faces:
                faces = self.face_det.detect(img)
            if faces:
                face = max(faces, key=lambda f: (f.box[2] - f.box[0]) * (f.box[3] - f.box[1]))
                emb = self.face_emb.embed_face(crop if crop.size else img, face.kps)
                if emb is not None:
                    self.ref_faces.append(emb)
                    if not self.ref_info:
                        self.ref_info = {
                            "face_px": int(max(face.box[2] - face.box[0], face.box[3] - face.box[1])),
                            "face_score": round(face.score, 2),
                            "person_h": int(box[3] - box[1]) if persons else 0,
                            "blur": round(laplacian_var(crop if crop.size else img), 1),
                            "size": f"{w}×{h}",
                        }
            loaded += 1

        self.ref_note = (f"{loaded} ảnh tham chiếu · {len(self.ref_faces)} có mặt, "
                         f"{len(self.ref_bodies)} có toàn thân")
        if not self.ref_faces:
            self.ref_warnings.append(
                "không ảnh tham chiếu nào phát hiện được mặt → chỉ so khớp toàn thân "
                "(nên thêm ảnh thấy rõ mặt để chính xác hơn)")
        elif self.ref_info.get("face_px", 0) < 50:
            self.ref_warnings.append(
                f"mặt trong ảnh tham chiếu đầu tiên chỉ ~{self.ref_info['face_px']}px — "
                f"nên thêm ảnh lớn/rõ hơn")

    # ------------------------------------------------------------------ frame
    def _match_person(self, frame: np.ndarray, person, t: float, frame_idx: int,
                      source: str, kind: str, track_id: int,
                      others: list | None = None, scene: int = 0) -> Candidate | None:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = person.box
        person_h = int(y2 - y1)
        if person_h < self.cfg.min_person or (x2 - x1) < 12:
            return None
        if person.score < self.cfg.min_person_score:
            return None
        # yêu cầu "mỗi ảnh 1 người": bỏ frame có người khác chồng lên người mục tiêu
        if others and self.cfg.max_overlap > 0:
            for o in others:
                iou = float(iou_matrix(person.box[None], o.box[None])[0, 0])
                if iou > self.cfg.max_overlap:
                    return None

        box = expand_box(person.box, self.cfg.crop_margin, w, h)
        # "mỗi ảnh 1 người": người khác chiếm quá nhiều diện tích crop thì bỏ
        if others and self.cfg.max_other_area > 0:
            frac = others_area_fraction(box, [o.box for o in others])
            if frac > self.cfg.max_other_area:
                return None
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
            emb = self.face_emb.embed_face(ctx, best_face.kps)
            face_sim = max((cosine(r, emb) for r in self.ref_faces), default=-1.0)
            yaw, pitch = head_pose(best_face.kps)

        tight = crop_xyxy(frame, person.box)
        clip_vec = self.body_emb.embed(tight) if tight.size else None
        body_sim = max((cosine(r, clip_vec) for r in self.ref_bodies), default=-1.0)
        color_sim = max((hist_similarity(r, torso_hist(tight)) for r in self.ref_torsos), default=-1.0) if tight.size else -1.0

        full_jpeg = None
        if self.cfg.save in ("full", "both"):
            key = (source, frame_idx)
            if self._frame_cache is None or self._frame_cache[0] != key:
                self._frame_cache = (key, encode_jpeg(frame, 92))
            full_jpeg = self._frame_cache[1]

        return Candidate(
            source=source, kind=kind, t=float(t), frame_idx=frame_idx, track_id=track_id,
            box=person.box, person_score=person.score, face_sim=face_sim, body_sim=body_sim,
            color_sim=color_sim,
            yaw=float(yaw), pitch=float(pitch), blur=float(blur), person_h=person_h,
            jpeg=encode_jpeg(crop, self.cfg.jpeg_quality),
            kpts=person.kpts, clip_vec=clip_vec, full_jpeg=full_jpeg,
            src_w=int(w), src_h=int(h), scene=int(scene),
            pose_vec=pose_vector(person.kpts, person.box),
        )

    def _body_ok(self, c: Candidate, th: float | None = None,
                 color: float | None = None) -> bool:
        """Khớp toàn thân: CLIP đủ giống VÀ màu áo/quần không lệch quá.

        `th` / `color` cho phép ghi đè ngưỡng (dùng ở chế độ chỉ-toàn-thân, nơi
        ảnh nhìn từ sau khác màu áo phía trước nên không so màu được).
        """
        th = self.cfg.body_th if th is None else th
        color = self.cfg.color_th if color is None else color
        if c.body_sim < th:
            return False
        if color > 0 and c.color_sim >= 0 and c.color_sim < color:
            return False
        return True

    def _accept(self, buf: list[Candidate]) -> tuple[list[Candidate], float, float, bool]:
        """Quyết định theo track nhưng giữ/bỏ từng frame (không nhận cả track).

        - Frame thấy mặt khớp (>= face_th) → nhận.
        - Frame không thấy mặt chỉ được nhận khi track đã được xác nhận bằng
          ít nhất 1 frame thấy mặt, VÀ toàn thân + màu áo đủ giống.
        - Ảnh tham chiếu không có mặt (vd. chụp từ phía sau), hoặc bật
          --allow-body-only: chỉ dùng body với **sàn thấp** (`body_only_low`);
          bước chọn cuối mới lọc tương đối giữa các track (xem `_filter_body_only`).

        Trả (frame nhận, face_max, body_med, nhận_theo_toàn_thân?).
        """
        cfg = self.cfg
        face_max = max((c.face_sim for c in buf if c.has_face), default=-1.0)
        body_med = float(statistics.median([c.body_sim for c in buf])) if buf else -1.0
        confirmed = bool(self.ref_faces) and face_max >= cfg.face_th
        anchor = self.anchors.get(buf[0].source)
        body_only = False

        def anchor_ok(c: Candidate) -> bool:
            """Giống ngoại hình đã xác nhận trong chính video này."""
            if anchor is None or c.clip_vec is None:
                return False
            return float(np.dot(anchor["clip"], c.clip_vec)) >= cfg.anchor_th

        def body_only_pick() -> list[Candidate]:
            # ảnh lưng so với ref nhìn thẳng chỉ ~0.55–0.65, nên không thể đòi
            # body_th 0.72 ở đây; ngưỡng tương đối áp ở export khi biết mọi track
            if len(buf) < cfg.min_track:
                return []
            return [c for c in buf
                    if self._body_ok(c, th=cfg.body_only_low, color=0.0)]

        if not self.ref_faces:
            # tham chiếu không có mặt → buộc phải dựa vào toàn thân
            kept = body_only_pick()
            body_only = bool(kept)
        elif confirmed:
            # track đã có frame khớp mặt; các frame còn lại (quay lưng, hoặc mặt
            # bị nhận nhầm sang hướng khác) được xét bằng neo ngoại hình của video
            kept = [c for c in buf
                    if c.face_sim >= cfg.face_th
                    or (c.face_sim < cfg.face_th and anchor_ok(c))
                    or (not c.has_face and self._body_ok(c))]
        elif anchor_ok(buf[0]) or any(anchor_ok(c) for c in buf):
            kept = [c for c in buf if c.face_sim < cfg.face_th and anchor_ok(c)]
        elif cfg.allow_body_only:
            # track không có frame nào khớp mặt: chỉ nhận khi người dùng cho phép,
            # dễ nhầm người mặc giống → mặc định tắt
            kept = body_only_pick()
            body_only = bool(kept)
        else:
            kept = []
        return kept, face_max, body_med, body_only

    def _near_confirmed(self, source: str, buf: list[Candidate]) -> bool:
        window = self.cfg.confirm_window
        if window <= 0 or not buf:
            return True
        t0, t1 = buf[0].t, buf[-1].t
        for a, b in self.confirmed.get(source, []):
            gap = max(a - t1, t0 - b, 0.0)
            if gap <= window:
                return True
        return False

    def _remember(self, source: str, buf: list[Candidate]) -> None:
        """Ghi khoảng thời gian đã khớp mặt (để `--confirm-window` dùng)."""
        intervals = self.confirmed.setdefault(source, [])
        lo, hi = buf[0].t, buf[-1].t
        for it in intervals:
            if lo <= it[1] + 30 and hi >= it[0] - 30:
                it[0], it[1] = min(it[0], lo), max(it[1], hi)
                break
        else:
            intervals.append([lo, hi])

    def _update_anchor(self, source: str, clip_vec: np.ndarray | None) -> None:
        """Cập nhật "neo" ngoại hình ngay từ một frame đã khớp mặt.

        Cập nhật theo từng frame (không đợi track kết thúc) để frame quay lưng ở
        đầu video hoặc ngay sau cắt cảnh vẫn có neo mà so. Lỗi cũ: neo chỉ được
        tạo lúc flush track, nên frame không mặt bị xét *trước* khi neo tồn tại
        → bị bỏ oan (đo trên v1.mp4: mất các frame 10–11 s).
        """
        if clip_vec is None:
            return
        v = np.asarray(clip_vec, dtype=np.float32)
        n = float(np.linalg.norm(v))
        if n <= 1e-9:
            return
        v = v / n
        anchor = self.anchors.get(source)
        if anchor is None:
            self.anchors[source] = {"clip": v.astype(np.float32), "n": 1}
            return
        k = int(anchor.get("n", 1))
        merged = anchor["clip"] * k + v
        merged = merged / max(1e-9, float(np.linalg.norm(merged)))
        anchor["clip"] = merged.astype(np.float32)
        anchor["n"] = k + 1

    def _flush(self, tid: int, buf: list[Candidate]) -> None:
        if not buf:
            return
        kept, face_max, body_med, body_only = self._accept(buf)
        self.stats.tracks += 1
        self.stats.track_face.append(face_max)
        self.stats.track_body.append(body_med)
        self.stats.track_scores.append((face_max, body_med,
                                        [c.face_sim for c in buf],
                                        [c.body_sim for c in buf]))
        if bool(self.ref_faces) and face_max >= self.cfg.face_th:
            self._remember(buf[0].source, buf)
        if not kept:
            return
        self.stats.accepted_tracks += 1
        self.stats.accepted += len(kept)
        # ghi ngay ra đĩa, chỉ giữ metadata trong RAM: CCTV vài giờ có thể ra
        # hàng chục nghìn frame, giữ JPEG trong bộ nhớ sẽ phình lên hàng GB
        self._staging.mkdir(parents=True, exist_ok=True)
        for c in kept:
            c.body_only = body_only
            self._stage_idx += 1
            path = self._staging / f"{self._stage_idx:07d}.jpg"
            path.write_bytes(c.jpeg)
            c.staged = path
            c.jpeg = b""
        self.accepted.extend(kept)
        tag = " · chỉ toàn thân" if body_only else ""
        log(f"  track {tid}: nhận {len(kept)}/{len(buf)} frame "
            f"(mặt max {face_max:.2f}, body med {body_med:.2f}){tag}")

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
        scene = 0
        prev_hist = None
        started = time.time()
        duration = video_duration(path)
        log(f"video {path.name} …" + (f" ({duration / 60:.1f} phút)" if duration else ""))
        for t, frame in iter_video(path, cfg.fps, cfg.start, cfg.end):
            frame_idx += 1
            if cfg.max_frames and frame_idx > cfg.max_frames:
                break
            self.stats.frames += 1
            if frame_idx == 1 and cfg.tiles > 1:
                fh, fw = frame.shape[:2]
                if min(fh, fw) / cfg.tiles < 360:
                    log(f"  cảnh báo: --tiles {cfg.tiles} quá lớn so với khung {fw}×{fh} — "
                        f"người có thể bị cắt qua ô, nên dùng tiles nhỏ hơn")

            # đổi cảnh → chốt track cũ, tránh gộp 2 người khác nhau vào 1 track
            hist = self._hist(frame)
            if prev_hist is not None and self._is_cut(prev_hist, hist):
                for tid in list(buffers):
                    self._flush(tid, buffers.pop(tid))
                tracker = IoUTracker(max_age=max_age)
                cuts += 1
                scene += 1
            prev_hist = hist

            persons = self.detector.detect(frame)
            if persons:
                ids = tracker.update(np.stack([p.box for p in persons]))
                for i, (person, tid) in enumerate(zip(persons, ids)):
                    n_persons += 1
                    self.stats.persons += 1
                    others = [p for j, p in enumerate(persons) if j != i]
                    cand = self._match_person(frame, person, t, frame_idx, str(path),
                                              "video", tid, others, scene)
                    if cand is not None:
                        self.stats.candidates += 1
                        if cand.face_sim >= cfg.face_th:
                            self._update_anchor(str(path), cand.clip_vec)
                        self._add(tid, buffers[tid], cand)
            else:
                tracker.update(np.empty((0, 4), np.float32))

            for tid in tracker.stale():
                self._flush(tid, buffers.pop(tid, []))
                tracker.drop(tid)

            if frame_idx % 100 == 0:
                el = time.time() - started
                rate = el / max(1, frame_idx)
                eta = ""
                if duration and t > 0:
                    eta = f" · còn ~{(duration - t) * rate / 60:.0f} phút"
                pct = f" · {100 * t / duration:.0f}%" if duration else ""
                log(f"  {frame_idx} frame ({t:.0f}s{pct}) · {n_persons} người · "
                    f"{rate:.3f}s/frame{eta}")

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
        others = [p for p in persons if p is not best]
        cand = self._match_person(img, best, 0.0, 0, str(path), "image", 0, others)
        if cand is None:
            return
        self.stats.persons += 1
        self.stats.candidates += 1
        if cand.face_sim >= self.cfg.face_th:
            self._update_anchor(str(path), cand.clip_vec)
        buf = [cand]
        self._flush(0, buf)

    # ------------------------------------------------------------------ chạy
    def run(self, input_dir: Path, recursive: bool = False) -> None:
        self._input_dir = input_dir
        if self._staging.exists():
            shutil.rmtree(self._staging)
        self._staging.mkdir(parents=True, exist_ok=True)
        videos, images = list_inputs(input_dir, recursive)
        if self.cfg.skip_ref:
            before = len(videos) + len(images)
            videos = [v for v in videos if v.resolve() not in self._ref_paths]
            images = [i for i in images if i.resolve() not in self._ref_paths]
            if before != len(videos) + len(images):
                log("bỏ qua ảnh tham chiếu nằm trong folder quét (--include-ref để giữ)")
        if not videos and not images:
            raise SystemExit(f"không tìm thấy ảnh/video trong {input_dir}")
        log(f"{len(videos)} video, {len(images)} ảnh · backend {self.detector.backend}")
        for v in videos:
            self.process_video(v)
        for i in images:
            self.process_image(i)

    # ------------------------------------------------------------------ xuất
    def _filter_body_only(self, cands: list[Candidate]) -> list[Candidate]:
        """Lọc lần cuối cho các frame chỉ nhận nhờ toàn thân (`_accept`).

        `_accept` nhận với sàn thấp (`--body-only-low`) vì ảnh quay lưng so với
        ảnh tham chiếu nhìn thẳng chỉ đạt cosine CLIP 0.55–0.65. Ngưỡng thật được
        áp ở đây, khi đã biết toàn bộ track của lần chạy:

        - Có ít nhất 1 track khớp mặt → giữ track toàn thân có trung vị
          `body_sim >= --body-th` (chặt, như cũ).
        - Không track nào khớp mặt (clip chỉ quay từ sau) → so **tương đối**:
          giữ các track có trung vị `>= max(--body-only-low, --body-only-rel ×
          track tốt nhất)`. Nhờ vậy clip toàn cảnh lưng vẫn ra ảnh thay vì 0 ảnh.
        """
        body = [c for c in cands if c.body_only]
        if not body:
            return cands
        faces = [c for c in cands if not c.body_only]
        th = 0.0
        if faces:
            from collections import defaultdict

            by_track: dict[tuple[str, int], list[float]] = defaultdict(list)
            for c in body:
                by_track[(c.source, c.track_id)].append(c.body_sim)
            med = {k: float(np.median(v)) for k, v in by_track.items()}
            kept = [c for c in body if med[(c.source, c.track_id)] >= self.cfg.body_th]
            if len(kept) != len(body):
                log(f"lọc toàn thân theo --body-th {self.cfg.body_th:.2f}: "
                    f"{len(body)} → {len(kept)} frame")
        else:
            kept, th = keep_best_body_tracks(body, self.cfg.body_only_low,
                                             self.cfg.body_only_rel)
            log(f"không track nào khớp mặt → giữ track toàn thân tốt nhất "
                f"(ngưỡng tương đối {th:.2f} = {self.cfg.body_only_rel:.2f} × tốt nhất, "
                f"sàn {self.cfg.body_only_low:.2f}): {len(body)} → {len(kept)} frame")
        self.body_only_th = th
        return faces + kept

    def export(self) -> list[tuple[Candidate, Path]]:
        cfg = self.cfg
        cfg.crops_dir.mkdir(parents=True, exist_ok=True)
        if cfg.clean:
            old = [p for p in cfg.crops_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png")]
            for p in old:
                p.unlink()
            if old:
                log(f"đã xoá {len(old)} ảnh cũ trong {cfg.crops_dir}")
        self.body_only_th = 0.0
        accepted = self._filter_body_only(self.accepted)
        self.accepted = accepted                 # để summary/report khớp số thật
        self.stats.accepted = len(accepted)
        cands = dedupe(accepted, cfg.dup_sim, cfg.min_gap)
        before = len(cands)
        cands = drop_tiny_frames(cands)
        if len(cands) != before:
            log(f"bỏ frame người quá bé so với cùng cảnh: {before} → {len(cands)} frame")
        before = len(cands)
        if cfg.select == "coverage":
            cands = coverage_pick(cands, cfg.per_bucket)
            after_cov = len(cands)
            cands = drop_similar(cands, 0.93)
            log(f"chọn theo độ phủ góc (tối đa {cfg.per_bucket} ảnh/nhóm): "
                f"{before} → {after_cov} → {len(cands)} ảnh")
        else:
            cands = diverse_gate(cands, cfg.min_yaw, cfg.min_pose)
            if len(cands) != before:
                log(f"lọc đa dạng (yaw {cfg.min_yaw}°, pose {cfg.min_pose}): "
                    f"{before} → {len(cands)} ảnh")
        if cfg.min_yaw > 0 or cfg.min_pose > 0:
            n_before = len(cands)
            cands = distinct_pose_pick(cands, cfg.min_yaw, cfg.min_pose)
            self.pose_gate = (n_before, len(cands))
            if len(cands) != n_before:
                log(f"lọc trùng tư thế (góc camera < {cfg.min_yaw:.0f}° và pose "
                    f"< {cfg.min_pose:.2f} coi là một): {n_before} → {len(cands)} ảnh")
        if cfg.limit and cfg.limit < len(cands):
            cands = pick_diverse(cands, cfg.limit)
            cands.sort(key=lambda c: (c.source, c.t))
        self.selected_cands = cands
        self.stats.selected = len(cands)

        rows: list[tuple[Candidate, Path, Path | None]] = []
        used: set[str] = set()
        for c in cands:
            stem = _safe(Path(c.source).stem)
            base = (f"{stem}__img" if c.kind == "image"
                    else f"{stem}__{int(round(c.t * 1000)):09d}ms__t{c.track_id:03d}")
            full_path = crop_path = None
            if cfg.save in ("full", "both") and c.full_jpeg:
                full_path = self._alloc(cfg.crops_dir, base, used)
                full_path.write_bytes(c.full_jpeg)
            if cfg.save in ("crop", "both") or (cfg.save == "full" and not c.full_jpeg):
                crop_path = self._alloc(cfg.crops_dir, base + "__crop" if cfg.save == "both" else base, used)
                if c.staged is not None and c.staged.exists():
                    c.staged.replace(crop_path)
                else:
                    crop_path.write_bytes(c.jpeg)
            rows.append((c, full_path or crop_path, crop_path))
        shutil.rmtree(self._staging, ignore_errors=True)

        self._write_metadata(rows)
        self._write_report()
        self._write_sheet(rows)
        return rows

    @staticmethod
    def _alloc(folder: Path, base: str, used: set[str]) -> Path:
        """Tên file không trùng (thêm _2, _3… nếu cần)."""
        name = f"{base}.jpg"
        n = 1
        while name in used:
            n += 1
            name = f"{base}_{n}.jpg"
        used.add(name)
        return folder / name

    def _write_metadata(self, rows: list[tuple[Candidate, Path, Path | None]]) -> None:
        import json

        with open(self.cfg.out / "metadata.jsonl", "w", encoding="utf-8") as fh:
            for c, dst, crop_path in rows:
                rec = {
                    "path": str(dst.relative_to(self.cfg.out)).replace("\\", "/"),
                    "source": c.source, "kind": c.kind, "t": round(c.t, 3),
                    "frame": c.frame_idx, "track": c.track_id,
                    "box": [round(float(v), 1) for v in c.box],
                    "person_score": round(c.person_score, 4),
                    "face_sim": round(c.face_sim, 4) if c.has_face else None,
                    "body_sim": round(c.body_sim, 4),
                    "color_sim": round(c.color_sim, 4),
                    "yaw": round(c.yaw, 1), "pitch": round(c.pitch, 1),
                    "bucket": yaw_bucket(c),
                    "blur": round(c.blur, 1), "person_h": c.person_h,
                    "crop_margin": self.cfg.crop_margin,
                    "src_width": c.src_w,
                    "src_height": c.src_h,
                }
                if crop_path is not None and crop_path != dst:
                    rec["crop_path"] = str(crop_path.relative_to(self.cfg.out)).replace("\\", "/")
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _calibration_lines(self) -> list[str]:
        """Bảng ước lượng số frame nhận được ở các ngưỡng khác nhau.

        Tính từ điểm của từng frame đã lưu trong lần chạy này, nên bro thấy ngay
        nên đặt --face-th bao nhiêu mà không phải quét lại video.
        """
        cfg, st = self.cfg, self.stats
        out = ["ước lượng số frame thô (trước lọc trùng) nếu đổi ngưỡng, "
               "tính từ lần chạy này:"]
        for th in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55):
            frames = sum(
                1
                for face_max, _, fs, bs in st.track_scores
                for f, b in zip(fs, bs)
                if f >= th or (f < 0 and face_max >= th and b >= cfg.body_th)
            )
            mark = "  ← đang dùng" if abs(th - cfg.face_th) < 1e-6 else ""
            out.append(f"  --face-th {th:.2f} → {frames:6d} frame{mark}")
        if cfg.allow_body_only or not self.ref_faces:
            out.append("  (chế độ chỉ toàn thân — nhận theo từng frame, sàn --body-only-low)")
            for th in (0.40, 0.45, 0.50, 0.55, 0.60):
                frames = sum(1 for _, _, _, bs in st.track_scores for b in bs if b >= th)
                mark = "  ← đang dùng" if abs(th - cfg.body_only_low) < 1e-6 else ""
                out.append(f"  --body-only-low {th:.2f} → {frames:6d} frame{mark}")
        return out

    def _write_report(self) -> None:
        cfg, st = self.cfg, self.stats
        lines = [
            "luyen_co — báo cáo lọc frame theo người tham chiếu",
            f"thời điểm: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"tham chiếu: {len(cfg.refs)} ảnh ({self.ref_note})",
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
        lines.extend(self._calibration_lines())
        n_body = sum(1 for c in self.accepted if c.body_only)
        if n_body:
            th = getattr(self, "body_only_th", 0.0)
            why = (f"ngưỡng tương đối {th:.2f}" if th > 0
                   else f"--body-th {cfg.body_th:.2f}")
            lines.append("")
            lines.append(f"frame chỉ nhận nhờ toàn thân (không có mặt khớp): {n_body} "
                         f"frame · lọc bằng {why}")
        lines.append("")
        lines.append("nhóm góc của TẤT CẢ frame nhận được (trước lọc trùng & chọn):")
        lines.extend(f"  {label:12s} {n:5d}" for label, n in yaw_histogram(self.accepted))
        gate = getattr(self, "pose_gate", None)
        if gate and gate[0] != gate[1]:
            lines.append("")
            lines.append(f"lọc trùng tư thế (góc camera < {cfg.min_yaw:.0f}° và pose "
                         f"< {cfg.min_pose:.2f} coi là một): {gate[0]} → {gate[1]} ảnh")
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

    def _write_sheet(self, rows: list[tuple[Candidate, Path, Path | None]]) -> None:
        if not self.cfg.sheet or not rows:
            return
        cols, cell, pad = 6, 180, 24
        items = rows[: self.cfg.sheet]
        n_rows = math.ceil(len(items) / cols)
        sheet = np.full((n_rows * (cell + pad + 14), cols * cell, 3), 255, np.uint8)
        for i, (c, dst, _crop) in enumerate(items):
            img = cv2.imdecode(np.fromfile(str(dst), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            h, w = img.shape[:2]
            s = min(cell / w, cell / h)
            thumb = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
            r, col = divmod(i, cols)
            y0, x0 = r * (cell + pad + 14), col * cell
            sheet[y0:y0 + thumb.shape[0], x0:x0 + thumb.shape[1]] = thumb
            label = f"{c.t:5.1f}s {yaw_bucket(c)}"
            cv2.putText(sheet, label, (x0 + 2, y0 + cell + 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (30, 30, 30), 1, cv2.LINE_AA)
        write_image(self.cfg.out / "sheet.jpg", sheet, 90)
