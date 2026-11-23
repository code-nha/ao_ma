"""Kiểm tra frame lặp (pulldown còn sót) trong file đã progressive.

Với mỗi file: lấy vài đoạn 60s rải đều, chạy mpdecimate (log debug), đếm frame
bị coi là trùng và xem chúng có rơi theo nhịp 1/5 không (telecine đã deinterlace
kiểu "blend/dup" để lại 1 frame lặp mỗi 5 frame).

  python dupcheck.py "file1" "file2" ...
  python dupcheck.py --fieldmatch "nguồn_interlaced.mkv"   # thêm đo fieldmatch nhiều đoạn

Kết luận:
  dup ~20% và dồn vào 1 vị trí mod 5  -> decimate về 23.976 có lợi
  dup thấp / rải rác                   -> giữ nguyên 29.97 (video thật hoặc cảnh tĩnh)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

WINDOWS = (0.15, 0.35, 0.55, 0.75)
SECS = 60


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def mpdecimate_flags(p: Path, ss: float) -> list[bool]:
    """True = frame bị coi là trùng với frame trước (sẽ bị drop)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "debug", "-ss", f"{ss:.0f}", "-i", str(p),
                        "-t", str(SECS), "-an", "-sn", "-vf", "mpdecimate=max=0", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    flags = []
    for line in r.stderr.splitlines():
        if "Parsed_mpdecimate" in line:
            if " keep " in line or line.rstrip().endswith("keep"):
                flags.append(False)
            elif " drop " in line or line.rstrip().endswith("drop"):
                flags.append(True)
    return flags


def cadence(flags: list[bool]) -> tuple[float, float]:
    """(tỉ lệ dup, tỉ lệ dup rơi vào vị trí mod-5 phổ biến nhất)."""
    if not flags:
        return 0.0, 0.0
    drops = [i for i, f in enumerate(flags) if f]
    ratio = len(drops) / len(flags)
    # khoảng cách giữa 2 frame lặp liên tiếp; bỏ gap=1 (chuỗi lặp liền = cảnh tĩnh/tối).
    # Pulldown: gap 4-6 (nhịp hay lệch 1 frame sau cắt cảnh/chỗ nối).
    gaps = [b - a for a, b in zip(drops, drops[1:]) if b - a > 1]
    if not gaps:
        return ratio, 0.0
    return ratio, sum(4 <= g <= 6 for g in gaps) / len(gaps)


def fieldmatch_ratio(p: Path, ss: float) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-ss", f"{ss:.0f}", "-i", str(p), "-t", str(SECS),
                        "-an", "-sn", "-vf", "fieldmatch,idet", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.findall(r"Single frame detection: TFF:\s*(\d+) BFF:\s*(\d+) Progressive:\s*(\d+) Undetermined:\s*(\d+)", r.stderr)
    if not m:
        return -1
    t, b, pr, u = map(int, m[-1])
    return pr / max(1, t + b + pr + u)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--fieldmatch", action="store_true")
    a = ap.parse_args()
    for p in a.files:
        if not p.exists():
            print(f"KHÔNG THẤY: {p}")
            continue
        dur = duration(p)
        print(f"=== {p.name}  ({dur / 60:.1f} phút)")
        tot_r, tot_c, n = 0.0, 0.0, 0
        for w in WINDOWS:
            ss = dur * w
            flags = mpdecimate_flags(p, ss)
            r, c = cadence(flags)
            extra = ""
            if a.fieldmatch:
                extra = f"  fieldmatch progressive {fieldmatch_ratio(p, ss):.0%}"
            print(f"  @{ss / 60:5.1f}ph  {len(flags):5d} frame  dup {r:5.1%}  nhịp-1/5 {c:5.1%}{extra}")
            tot_r += r
            tot_c += c
            n += 1
        r, c = tot_r / n, tot_c / n
        verdict = "DECIMATE được (pulldown lặp 1/5)" if r > 0.15 and c > 0.7 else "giữ nguyên"
        print(f"  => dup TB {r:.1%}, nhịp {c:.0%}: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
