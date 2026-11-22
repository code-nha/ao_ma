"""Chuẩn bị file DVD (ISO / MKV / VOB...) cho pipeline upscale của senlab.

Đọc input.txt (mỗi dòng 1 đường dẫn, có thể có dấu ngoặc kép; dòng trống
hoặc bắt đầu bằng # bị bỏ qua), convert TUẦN TỰ từng file:

  - ISO: lấy title dài nhất bằng demuxer dvdvideo của ffmpeg.
  - Tự phát hiện field bằng idet + fieldmatch:
      telecine/hybrid -> fieldmatch,yadif=deint=interlaced,decimate (23.976)
      interlaced thật -> bwdif=mode=send_frame (giữ 29.97)
      progressive     -> không lọc
  - libx264 crf 12, preset slow, tune film, yuv420p; giữ nguyên độ phân giải
    và SAR (không scale, không crop).
  - Chỉ giữ audio track đầu tiên (copy); giữ mọi luồng phụ đề (copy).
  - Output: cùng thư mục với file gốc, tên "<tên gốc>.<mode>.mkv".
    Ghi ra .part.mkv rồi đổi tên khi xong; file output đã có thì bỏ qua.

Dùng:
  python prep_upscale.py                 # đọc input.txt cạnh script
  python prep_upscale.py list.txt
  python prep_upscale.py --test 60       # chỉ convert 60s từ phút 10 (thử)
  python prep_upscale.py --crf 15        # file nhỏ hơn
  python prep_upscale.py --mode ivtc     # ép mode: auto|ivtc|bwdif|none
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

FILTERS = {
    "ivtc": "fieldmatch,yadif=deint=interlaced,decimate",
    "bwdif": "bwdif=mode=send_frame",
    "prog": None,
}
ENCODE = ["-c:v", "libx264", "-crf", "{crf}", "-preset", "slow", "-tune", "film", "-pix_fmt", "yuv420p"]
PROBE_START = 600  # giây; bỏ qua logo/intro khi phân tích field
PROBE_FRAMES = 1800


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def read_list(path: Path) -> list[Path]:
    items = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip().strip('"').strip("'").strip()
        if line and not line.startswith("#"):
            items.append(Path(line))
    return items


def iso_best_title(src: Path) -> int:
    """Trả về số title dài nhất trong ISO."""
    best, best_dur = 1, -1.0
    for t in range(1, 100):
        r = run(["ffprobe", "-v", "error", "-f", "dvdvideo", "-title", str(t), "-i", str(src),
                 "-show_entries", "format=duration", "-of", "csv=p=0"])
        if r.returncode != 0:
            break
        try:
            dur = float(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            continue
        log(f"  title {t}: {dur / 60:.1f} phút")
        if dur > best_dur:
            best, best_dur = t, dur
    return best


def input_args(src: Path, title: int | None) -> list[str]:
    if title is not None:
        return ["-f", "dvdvideo", "-title", str(title), "-i", str(src)]
    return ["-i", str(src)]


def duration(src: Path, title: int | None) -> float:
    r = run(["ffprobe", "-v", "error", *input_args(src, title), "-show_entries", "format=duration", "-of", "csv=p=0"])
    try:
        return float(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 0.0


def idet_counts(src: Path, title: int | None, start: float, vf: str) -> dict[str, int]:
    pre = ["-ss", str(start)] if title is None else []
    inp = input_args(src, title)
    if title is not None:  # dvdvideo: -ss đặt sau -title, trước -i
        inp = inp[:-2] + ["-ss", str(start)] + inp[-2:]
    r = run(["ffmpeg", "-hide_banner", "-nostdin", *pre, *inp, "-map", "0:v:0", "-vf", vf,
             "-frames:v", str(PROBE_FRAMES), "-an", "-sn", "-f", "null", "-"])
    out = {}
    # lấy lần in cuối cùng (bản tổng kết)
    for key, pat in {"single": r"Single frame detection: (.*)", "multi": r"Multi frame detection: (.*)"}.items():
        m = re.findall(pat, r.stderr)
        if m:
            nums = dict((k, int(v)) for k, v in re.findall(r"(TFF|BFF|Progressive|Undetermined):\s*(\d+)", m[-1]))
            out.update({f"{key}_{k}": v for k, v in nums.items()})
    return out


def detect_mode(src: Path, title: int | None) -> str:
    dur = duration(src, title)
    start = PROBE_START if dur > PROBE_START + 120 else max(0.0, dur / 3)
    raw = idet_counts(src, title, start, "idet")
    tot = sum(raw.get(f"multi_{k}", 0) for k in ("TFF", "BFF", "Progressive", "Undetermined")) or 1
    if raw.get("multi_Progressive", 0) / tot >= 0.8:
        log(f"  idet: progressive {raw.get('multi_Progressive', 0)}/{tot} -> prog")
        return "prog"
    fm = idet_counts(src, title, start, "fieldmatch,idet")
    stot = sum(fm.get(f"single_{k}", 0) for k in ("TFF", "BFF", "Progressive", "Undetermined")) or 1
    ratio = fm.get("single_Progressive", 0) / stot
    mode = "ivtc" if ratio >= 0.6 else "bwdif"
    log(f"  idet interlaced; sau fieldmatch progressive {ratio:.0%} -> {mode}")
    return mode


def convert(src: Path, mode_opt: str, test: float | None, crf: int = 12) -> None:
    if not src.exists():
        log(f"KHÔNG TÌM THẤY: {src}")
        return
    log(f"=== {src}")
    title = None
    if src.suffix.lower() == ".iso":
        title = iso_best_title(src)
        log(f"  dùng title {title}")

    mode = detect_mode(src, title) if mode_opt == "auto" else ("prog" if mode_opt == "none" else mode_opt)
    tag = f".{mode}" + (f".test{int(test)}s" if test else "")
    dst = src.with_name(src.stem + tag + ".mkv")
    if dst.exists():
        log(f"  đã có, bỏ qua: {dst.name}")
        return
    part = dst.with_name(dst.stem + ".part.mkv")

    inp = input_args(src, title)
    seek: list[str] = []
    if test:
        if title is None:
            seek = ["-ss", str(PROBE_START)]
        else:
            inp = inp[:-2] + ["-ss", str(PROBE_START)] + inp[-2:]
    vf = FILTERS[mode]
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", "-stats",
           *seek, *inp, "-map", "0:v:0", "-map", "0:a:0?", "-map", "0:s?",
           *(["-vf", vf] if vf else []), *[x.format(crf=crf) for x in ENCODE], "-c:a", "copy", "-c:s", "copy", "-dn",
           *(["-t", str(test)] if test else []),
           "-max_muxing_queue_size", "4096", str(part)]
    log(f"  -> {dst.name}  (mode={mode})")
    t0 = time.time()
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        log(f"  LỖI ffmpeg (rc={rc}); giữ lại {part.name} để xem")
        return
    part.replace(dst)
    log(f"  xong sau {(time.time() - t0) / 60:.1f} phút: {dst}")


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("list", nargs="?", default=str(Path(__file__).with_name("input.txt")))
    ap.add_argument("--mode", choices=["auto", "ivtc", "bwdif", "none"], default="auto")
    ap.add_argument("--crf", type=int, default=12, help="x264 crf (mặc định 12; 14–16 cho file nhỏ hơn)")
    ap.add_argument("--test", type=float, metavar="GIÂY", help="chỉ convert N giây từ phút 10 để thử")
    a = ap.parse_args()
    items = read_list(Path(a.list))
    log(f"{len(items)} file trong {a.list}")
    for i, src in enumerate(items, 1):
        log(f"[{i}/{len(items)}]")
        try:
            convert(src, a.mode, a.test, a.crf)
        except Exception as e:  # một file lỗi không chặn các file sau
            log(f"  LỖI: {e!r}")
    log("HẾT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
