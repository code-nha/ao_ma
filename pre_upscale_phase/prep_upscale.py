"""Chuẩn bị file DVD (ISO / MKV / VOB...) cho pipeline upscale của senlab.

Đọc input.txt (mỗi dòng 1 đường dẫn, có thể có dấu ngoặc kép; dòng trống
hoặc bắt đầu bằng # bị bỏ qua), xử lý TUẦN TỰ từng file:

  - ISO: lấy title dài nhất bằng demuxer dvdvideo của ffmpeg.
  - Tự phân loại bằng idet + fieldmatch + fps:
      telecine/hybrid, nguồn 29.97 -> ivtc: fieldmatch,yadif=deint=interlaced,decimate (23.976)
      khớp field, nguồn 25/23.976  -> fm:   fieldmatch,yadif=deint=interlaced (giữ fps,
                                             KHÔNG decimate - decimate chỉ đúng với NTSC)
      interlaced thật              -> bwdif=mode=send_frame (giữ fps)
      progressive, ISO             -> copy: chỉ tách ra MKV, không encode lại
      progressive, file thường     -> skip: không cần convert, gửi thẳng file gốc
  - Encode: libx264 crf 12, preset slow, tune film, yuv420p; giữ nguyên độ
    phân giải và SAR (không scale, không crop).
  - Chỉ giữ audio track đầu tiên (copy); giữ mọi luồng phụ đề (copy).
  - Output: cùng thư mục với file gốc, tên "<tên gốc>.<mode>.mkv".
    Ghi ra .part.mkv rồi đổi tên khi xong; file output đã có thì bỏ qua.

Dùng:
  python prep_upscale.py                 # đọc input.txt cạnh script
  python prep_upscale.py list.txt
  python prep_upscale.py --check        # chỉ in bảng phân loại, không convert gì
  python prep_upscale.py --test 60       # chỉ convert 60s từ phút 10 (thử)
  python prep_upscale.py --crf 15        # file nhỏ hơn
  python prep_upscale.py --mode ivtc     # ép mode: auto|ivtc|fm|bwdif|copy|none
                                         # (none = encode không lọc, kể cả file progressive)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from history import record

FILTERS = {
    "ivtc": "fieldmatch,yadif=deint=interlaced,decimate",
    "fm": "fieldmatch,yadif=deint=interlaced",
    "bwdif": "bwdif=mode=send_frame",
    "prog": None,
    # chỉ dùng khi ép --mode (dupcheck.py báo):
    "decimate": "decimate",       # file đã progressive nhưng lặp 1/5 frame (pulldown dup) -> 23.976
    "cfr24": "fps=24000/1001",    # soft telecine (cờ RFF, decoder ra ~24 frame/s) -> 23.976 CFR theo pts
}
NTSC_FPS = 30000 / 1001
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


def video_info(src: Path, title: int | None) -> dict:
    r = run(["ffprobe", "-v", "error", *input_args(src, title), "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,width,height,avg_frame_rate,r_frame_rate",
             "-of", "default=nw=1"])
    info = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    fps = 0.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        n, _, d = info.get(key, "0/0").partition("/")
        try:
            fps = float(n) / float(d or 1)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        if fps:
            break
    return {"codec": info.get("codec_name", "?"),
            "res": f'{info.get("width", "?")}x{info.get("height", "?")}', "fps": fps}


def classify(src: Path, title: int | None, fps: float) -> tuple[str, str]:
    """Trả về (mode, lý do). mode: ivtc | fm | bwdif | copy | skip"""
    dur = duration(src, title)
    start = PROBE_START if dur > PROBE_START + 120 else max(0.0, dur / 3)
    raw = idet_counts(src, title, start, "idet")
    tot = sum(raw.get(f"multi_{k}", 0) for k in ("TFF", "BFF", "Progressive", "Undetermined")) or 1
    prog = raw.get("multi_Progressive", 0) / tot
    if prog >= 0.8:
        why = f"progressive {prog:.0%}"
        if title is not None:
            return "copy", why + ", ISO -> tách ra MKV"
        return "skip", why + ", gửi file gốc"
    fm = idet_counts(src, title, start, "fieldmatch,idet")
    stot = sum(fm.get(f"single_{k}", 0) for k in ("TFF", "BFF", "Progressive", "Undetermined")) or 1
    ratio = fm.get("single_Progressive", 0) / stot
    why = f"interlaced; sau fieldmatch progressive {ratio:.0%}"
    if ratio < 0.6:
        return "bwdif", why
    if abs(fps - NTSC_FPS) < 0.05:
        return "ivtc", why
    return "fm", why + f"; {fps:.3f}fps không phải NTSC -> không decimate"


def detect_mode(src: Path, title: int | None) -> str:
    return classify(src, title, video_info(src, title)["fps"])[0]


def resolve_mode(src: Path, mode_opt: str) -> tuple[int | None, dict, str, str]:
    title = None
    if src.suffix.lower() == ".iso":
        title = iso_best_title(src)
    info = video_info(src, title)
    if mode_opt == "auto":
        mode, why = classify(src, title, info["fps"])
    elif mode_opt == "none":
        mode, why = "prog", "ép: encode không lọc"
    elif mode_opt == "ivtc" and abs(info["fps"] - NTSC_FPS) >= 0.05:
        mode, why = "fm", f"ép ivtc nhưng {info['fps']:.3f}fps không phải NTSC -> fm (không decimate)"
    else:
        mode, why = mode_opt, "ép"
    return title, info, mode, why


def out_path(src: Path, mode: str, test: float | None) -> Path:
    return src.with_name(src.stem + f".{mode}" + (f".test{int(test)}s" if test else "") + ".mkv")


def convert(src: Path, mode_opt: str, test: float | None, crf: int = 12) -> None:
    if not src.exists():
        log(f"KHÔNG TÌM THẤY: {src}")
        record("prep", "missing", src)
        return
    log(f"=== {src}")
    title, info, mode, why = resolve_mode(src, mode_opt)
    if title is not None:
        log(f"  dùng title {title}")
    log(f"  {info['codec']} {info['res']} {info['fps']:.3f}fps: {why} -> {mode}")

    if mode == "skip":
        log("  không cần convert - gửi thẳng file gốc lên senlab")
        record("prep", "skip", src, None, f"không cần convert: {why}")
        return
    dst = out_path(src, mode, test)
    if dst.exists():
        log(f"  đã có, bỏ qua: {dst.name}")
        record("prep", "skip", src, dst, f"mode={mode} đã có")
        return
    part = dst.with_name(dst.stem + ".part.mkv")

    inp = input_args(src, title)
    seek: list[str] = []
    if test:
        if title is None:
            seek = ["-ss", str(PROBE_START)]
        else:
            inp = inp[:-2] + ["-ss", str(PROBE_START)] + inp[-2:]
    if mode == "copy":
        vcodec = ["-c:v", "copy"]
    else:
        vf = FILTERS[mode]
        vcodec = [*(["-vf", vf] if vf else []), *[x.format(crf=crf) for x in ENCODE]]
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", "-stats",
           *seek, *inp, "-map", "0:v:0", "-map", "0:a:0?", "-map", "0:s?",
           *vcodec, "-c:a", "copy", "-c:s", "copy", "-dn",
           *(["-t", str(test)] if test else []),
           "-max_muxing_queue_size", "4096", str(part)]
    log(f"  -> {dst.name}  (mode={mode})")
    t0 = time.time()
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        log(f"  LỖI ffmpeg (rc={rc}); giữ lại {part.name} để xem")
        record("prep", "error", src, part, f"mode={mode} ffmpeg rc={rc}", (time.time() - t0) / 60)
        return
    part.replace(dst)
    mins = (time.time() - t0) / 60
    log(f"  xong sau {mins:.1f} phút: {dst}")
    detail = f"mode={mode}" + ("" if mode == "copy" else f" crf={crf}") + (f" test={test:g}s" if test else "")
    record("prep", "ok", src, dst, detail, mins)


def check(items: list[Path], mode_opt: str) -> None:
    """In bảng phân loại, không convert, không ghi history."""
    global log
    loud = log
    log = lambda msg: None  # noqa: E731
    rows, count = [], {}
    try:
        for src in items:
            if not src.exists():
                rows.append(("MISSING", "", "", "", src.name, ""))
                count["missing"] = count.get("missing", 0) + 1
                continue
            title, info, mode, why = resolve_mode(src, mode_opt)
            done = mode != "skip" and out_path(src, mode, None).exists()
            rows.append((mode + (" (đã có)" if done else ""), info["codec"], info["res"],
                         f"{info['fps']:.3f}", src.name, why))
            count[mode] = count.get(mode, 0) + 1
            loud(f"  {mode:6} {src.name}")
    finally:
        log = loud
    print()
    print(f"{'MODE':14} {'CODEC':10} {'RES':9} {'FPS':7} FILE  - lý do")
    for m, c, r, f, n, why in rows:
        print(f"{m:14} {c:10} {r:9} {f:7} {n}  - {why}")
    print("\nTổng:", ", ".join(f"{k}={v}" for k, v in count.items()))
    print("ivtc/fm/bwdif = encode lại; copy = tách ISO ra MKV; skip = gửi thẳng file gốc")


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("list", nargs="?", default=str(Path(__file__).with_name("input.txt")))
    ap.add_argument("--mode", choices=["auto", "ivtc", "fm", "bwdif", "copy", "none", "decimate", "cfr24"], default="auto")
    ap.add_argument("--check", action="store_true", help="chỉ in bảng phân loại, không convert")
    ap.add_argument("--crf", type=int, default=12, help="x264 crf (mặc định 12; 14–16 cho file nhỏ hơn)")
    ap.add_argument("--test", type=float, metavar="GIÂY", help="chỉ convert N giây từ phút 10 để thử")
    a = ap.parse_args()
    items = read_list(Path(a.list))
    log(f"{len(items)} file trong {a.list}")
    if a.check:
        check(items, a.mode)
        return 0
    if sys.platform == "win32":  # giữ máy không ngủ khi đang chạy; tự hết khi tiến trình thoát
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS|ES_SYSTEM_REQUIRED
    for i, src in enumerate(items, 1):
        log(f"[{i}/{len(items)}]")
        try:
            convert(src, a.mode, a.test, a.crf)
        except Exception as e:  # một file lỗi không chặn các file sau
            log(f"  LỖI: {e!r}")
            record("prep", "error", src, None, repr(e))
    log("HẾT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
