"""Ghép phụ đề (và audio gốc) vào phim đã upscale.

Lấy VIDEO từ file upscale; lấy AUDIO + PHỤ ĐỀ từ file gốc (MKV/ISO/...), tất cả
copy nguyên, không encode lại. File sub rời cạnh file gốc ("<tên>.srt" hoặc
"<tên>.eng.srt" từ ocr_vobsub.py) được ghép vào và đặt làm mặc định; khi đã có
sub rời thì bỏ sub bitmap (tránh bị dẹt do node cắt viền), --keep-bitmap-subs
để giữ cả hai. Output: cạnh file upscale, tên "<tên upscale>.subs.mkv".

Mặc định dùng audio gốc a:0 (AC3 5.1 tốt hơn AAC stereo mà node tạo ra).
IVTC giữ nguyên timestamp nên audio/sub gốc vẫn khớp với video upscale.

Dùng:
  python mux_subs.py UPSCALED ORIGINAL
  python mux_subs.py --list pairs.txt      # mỗi dòng: "upscaled" | "original"
Tuỳ chọn:
  --start GIÂY      video upscale bắt đầu từ giây này của phim gốc (khi node
                    chỉ chạy một đoạn start/end). Mặc định tự lấy:
                    1) "start" trong job.json của node (tải kèm, để cạnh file
                       upscale; nên đổi tên thành "<tên upscale>.job.json" nếu
                       nhiều phim chung thư mục)
                    2) dự phòng: HHMMSS trong tên "<tên>_HHMMSS-HHMMSS_x4_<jobid>.mp4"
                    3) không có gì -> 0 (chạy cả phim)
  --upscaled-audio  giữ audio của file upscale thay vì audio gốc
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from history import record
from prep_upscale import input_args, iso_best_title, log, run

SUB_EXT = (".srt", ".ass", ".ssa", ".sup", ".idx")


def dur(args: list[str]) -> float:
    r = run(["ffprobe", "-v", "error", *args, "-show_entries", "format=duration", "-of", "csv=p=0"])
    try:
        return float(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 0.0


def count_streams(args: list[str], kind: str) -> int:
    r = run(["ffprobe", "-v", "error", *args, "-select_streams", kind, "-show_entries", "stream=index", "-of", "csv=p=0"])
    return len([x for x in r.stdout.split() if x.strip()])


def job_id(up: Path) -> str | None:
    """jobid = 10 ký tự hex ở cuối tên output của node: ..._<jobid>.mp4"""
    m = re.search(r"_([0-9a-fA-F]{10})$", up.stem)
    return m.group(1).lower() if m else None


def find_job_json(up: Path) -> Path | None:
    """Tìm job.json của node cạnh file upscale (user tải kèm), theo thứ tự:
    <tên upscale>.job.json · file .json có <jobid> trong tên · job.json duy nhất
    trong thư mục · <...>_<jobid>_chunks/job.json."""
    d = up.parent
    jid = job_id(up)
    cands = [d / f"{up.stem}.job.json"]
    if jid:
        cands += sorted(p for p in d.glob("*.json") if jid in p.name.lower())
        cands += sorted(d.glob(f"*_{jid}_chunks/job.json"))
    cands += [d / "job.json"]
    for p in cands:
        if p.is_file():
            return p
    return None


def start_from_job(up: Path) -> tuple[float, Path] | None:
    p = find_job_json(up)
    if not p:
        return None
    try:
        return float(json.loads(p.read_text(encoding="utf-8"))["start"] or 0), p
    except (ValueError, KeyError, TypeError) as e:
        log(f"  job.json lỗi ({p.name}): {e!r}")
        return None


def start_from_name(up: Path) -> float | None:
    """Dự phòng: <tên>_HHMMSS-HHMMSS_x2|x4_<id>.mp4 -> giây bắt đầu (mất phần lẻ giây)."""
    m = re.search(r"_(\d{2})(\d{2})(\d{2})-\d{6}_x\d+_", up.name)
    if not m:
        return None
    h, mi, se = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + se


def resolve_start(up: Path) -> float:
    j = start_from_job(up)
    if j is not None:
        log(f"  start lấy từ {j[1].name}: {j[0]:.3f}s")
        return j[0]
    s = start_from_name(up)
    if s:
        log(f"  CẢNH BÁO: không thấy job.json, start lấy từ tên file: {s:.0f}s (có thể lệch <1s)")
        return s
    if job_id(up):
        log("  không thấy job.json; tên file không có HHMMSS -> coi start = 0 "
            "(nếu node chạy một đoạn thì tải kèm job.json hoặc dùng --start)")
    return 0.0


def find_ext_subs(orig: Path) -> list[Path]:
    """File sub rời cạnh file gốc: "<tên>.srt" hoặc "<tên>.<lang>.srt" (…ass/ssa/sup)."""
    found = []
    for p in sorted(orig.parent.iterdir()):
        n = p.name
        if p.suffix.lower() in SUB_EXT and n.startswith(orig.stem + ".") and p != orig:
            mid = n[len(orig.stem) + 1:-len(p.suffix)]
            if "." not in mid:  # bỏ "<tên>.ivtc.xxx.srt" lạ; chấp nhận "" hoặc "eng"
                found.append(p)
    return found


def sub_lang(orig: Path, s: Path) -> str | None:
    mid = s.name[len(orig.stem) + 1:-len(s.suffix)]
    return mid if re.fullmatch(r"[a-z]{2,3}", mid) else None


def mux(up: Path, orig: Path, start: float | None, upscaled_audio: bool, keep_bitmap: bool = False) -> bool:
    log(f"=== {up.name}  <=  {orig.name}")
    if start is None:
        start = resolve_start(up)
    for p in (up, orig):
        if not p.exists():
            log(f"  KHÔNG TÌM THẤY: {p}")
            record("mux", "missing", p)
            return False
    title = iso_best_title(orig) if orig.suffix.lower() == ".iso" else None
    o_in = input_args(orig, title)
    # Dời video upscale tới mốc `start` rồi cắt phía output: cắt chính xác,
    # không bị nhảy về keyframe như seek đầu vào khi copy.
    up_in = (["-itsoffset", str(start)] if start else []) + ["-i", str(up)]

    v_dur = dur(["-i", str(up)])
    o_dur = dur(input_args(orig, title)) - start
    if abs(v_dur - o_dur) > 2:
        log(f"  CẢNH BÁO: video upscale {v_dur:.1f}s, gốc (từ {start}s) {o_dur:.1f}s — "
            "lệch, có thể node đã cắt đoạn (dùng --start); output sẽ cắt theo độ dài video")

    ext_subs = find_ext_subs(orig)
    n_sub = count_streams(input_args(orig, title), "s")
    # Có SRT (vd từ ocr_vobsub.py) thì mặc định bỏ sub bitmap: bitmap 720x480
    # sẽ bị dẹt khi node đã cắt viền đen.
    use_bitmap = n_sub > 0 and (keep_bitmap or not ext_subs)
    log(f"  phụ đề: {len(ext_subs)} file rời {[s.name for s in ext_subs]}, "
        f"{n_sub} luồng bitmap trong file gốc ({'giữ' if use_bitmap else 'bỏ'})")
    if not ext_subs and not use_bitmap:
        log("  không có phụ đề — vẫn ghép audio gốc")

    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
           *up_in, *o_in]
    for s in ext_subs:
        cmd += ["-sub_charenc", "UTF-8", "-i", str(s)] if s.suffix.lower() == ".srt" else ["-i", str(s)]
    cmd += ["-map", "0:v:0", "-map", "0:a:0?" if upscaled_audio else "1:a:0?"]
    meta: list[str] = []
    for i, s in enumerate(ext_subs):
        cmd += ["-map", f"{i + 2}:s:0"]
        lang = sub_lang(orig, s)
        if lang:
            meta += [f"-metadata:s:s:{i}", f"language={lang}"]
    if use_bitmap:
        cmd += ["-map", "1:s?"]
    out = up.with_name(up.stem + ".subs.mkv")
    part = out.with_name(out.stem + ".part.mkv")
    cmd += ["-c", "copy", *meta, *(["-ss", str(start)] if start else []), "-t", f"{v_dur:.3f}",
            "-disposition:s:0", "default", str(part)]
    if subprocess.run(cmd).returncode != 0:
        log(f"  LỖI ffmpeg; giữ lại {part.name}")
        record("mux", "error", up, part, f"gốc={orig.name}")
        return False
    part.replace(out)
    log(f"  xong: {out}")
    subs = "+".join([s.name[len(orig.stem) + 1:] for s in ext_subs] + (["bitmap"] if use_bitmap else [])) or "không sub"
    record("mux", "ok", up, out, f"gốc={orig.name} start={start:g}s sub={subs}")
    return True


def read_pairs(path: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        a, sep, b = line.partition("|")
        if not sep:
            log(f"bỏ qua dòng thiếu '|': {line}")
            continue
        pairs.append((Path(a.strip().strip('"')), Path(b.strip().strip('"'))))
    return pairs


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("upscaled", nargs="?")
    ap.add_argument("original", nargs="?")
    ap.add_argument("--list", help='file cặp: "upscaled" | "original" mỗi dòng')
    ap.add_argument("--start", type=float, default=None, help="mặc định: job.json của node, rồi tên file, không có thì 0")
    ap.add_argument("--upscaled-audio", action="store_true")
    ap.add_argument("--keep-bitmap-subs", action="store_true", help="giữ cả sub bitmap DVD khi đã có SRT")
    a = ap.parse_args()
    if a.list:
        pairs = read_pairs(Path(a.list))
    elif a.upscaled and a.original:
        pairs = [(Path(a.upscaled.strip('"')), Path(a.original.strip('"')))]
    else:
        ap.error("cần UPSCALED ORIGINAL hoặc --list")
    ok = sum(mux(u, o, a.start, a.upscaled_audio, a.keep_bitmap_subs) for u, o in pairs)
    log(f"HẾT: {ok}/{len(pairs)} thành công")
    return 0 if ok == len(pairs) else 1


if __name__ == "__main__":
    sys.exit(main())
