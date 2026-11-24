"""Quản lý model ONNX: tải về khi thiếu, tạo session ưu tiên GPU.

Toàn bộ model đều là ONNX chạy bằng onnxruntime, không cần torch:
  - yolov8n-pose.onnx      phát hiện người + 17 keypoint (Xenova/yolov8-pose-onnx)
  - clip_vision.onnx       embedding toàn thân (CLIP ViT-B/32 vision encoder)
  - buffalo_l/det_10g.onnx phát hiện mặt (SCRFD 10G)
  - buffalo_l/w600k_r50.onnx  embedding khuôn mặt (ArcFace ResNet50)

Backend: ưu tiên CUDA nếu máy có (onnxruntime-gpu + CUDA), rồi DirectML
(onnxruntime-directml, chạy trên mọi GPU DX12 của Windows), cuối cùng là CPU.
"""

from __future__ import annotations

import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import onnxruntime as ort

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"

# tên -> (url, file đích)
FILES: dict[str, tuple[str, str]] = {
    "pose": ("https://huggingface.co/Xenova/yolov8-pose-onnx/resolve/main/yolov8n-pose.onnx",
             "yolov8n-pose.onnx"),
    "clip": ("https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model.onnx",
             "clip_vision.onnx"),
    "buffalo": ("https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
                "buffalo_l.zip"),
}

# sau khi giải nén buffalo_l.zip
SCRFD_MODEL = MODEL_DIR / "buffalo_l" / "det_10g.onnx"
ARCFACE_MODEL = MODEL_DIR / "buffalo_l" / "w600k_r50.onnx"
POSE_MODEL = MODEL_DIR / "yolov8n-pose.onnx"
CLIP_MODEL = MODEL_DIR / "clip_vision.onnx"


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 / total
                    sys.stderr.write(f"\r  {dest.name}: {done / 1e6:6.1f}/{total / 1e6:.1f} MB ({pct:5.1f}%)")
                    sys.stderr.flush()
        sys.stderr.write("\n")
    tmp.replace(dest)


def ensure_models() -> None:
    """Tải model còn thiếu (~640 MB cho lần đầu)."""
    for name, (url, filename) in FILES.items():
        dest = MODEL_DIR / filename
        if dest.exists() and dest.stat().st_size > 0:
            continue
        log(f"tải model {filename} …")
        _download(url, dest)
    if not SCRFD_MODEL.exists():
        log("giải nén buffalo_l.zip …")
        with zipfile.ZipFile(MODEL_DIR / "buffalo_l.zip") as zf:
            zf.extractall(MODEL_DIR / "buffalo_l")
    missing = [p.name for p in (SCRFD_MODEL, ARCFACE_MODEL, POSE_MODEL, CLIP_MODEL) if not p.exists()]
    if missing:
        raise RuntimeError(f"thiếu model: {', '.join(missing)} (xoá {MODEL_DIR} rồi chạy lại để tải)")


def providers_for(device: str) -> list[str]:
    """Chọn execution provider theo `--device` (auto|gpu|cpu)."""
    avail = ort.get_available_providers()
    if device == "cpu":
        return ["CPUExecutionProvider"]
    order = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "DmlExecutionProvider"]
    chosen = [p for p in order if p in avail]
    if not chosen:
        if device == "gpu":
            log("cảnh báo: không có GPU provider, chạy CPU (chậm hơn nhiều)")
    return chosen + ["CPUExecutionProvider"]


def create_session(path: str | Path, device: str = "auto") -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.log_severity_level = 3
    provs = providers_for(device)
    sess = ort.InferenceSession(str(path), so, providers=provs)
    return sess


def session_info(sess: ort.InferenceSession) -> str:
    """Mô tả ngắn backend đang dùng, in lúc khởi động."""
    used = sess.get_providers()
    return used[0] if used else "?"
