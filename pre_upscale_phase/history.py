"""Sổ ghi nhận file đã xử lý, dùng chung cho prep_upscale / ocr_vobsub / mux_subs.

Mỗi lần một file xong (hoặc lỗi / bỏ qua) thì ghi thêm 1 dòng vào
history.csv cạnh script. CSV UTF-8 có BOM để mở thẳng bằng Excel.

Xem nhanh:  python history.py            (bảng tóm tắt, mới nhất ở cuối)
            python history.py --step prep
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

HISTORY = Path(__file__).with_name("history.csv")
FIELDS = ["time", "step", "status", "source", "output", "detail", "minutes", "size_mb"]


def record(step: str, status: str, source: Path | str, output: Path | str | None = None,
           detail: str = "", minutes: float | None = None) -> None:
    """step: prep | ocr | mux;  status: ok | error | skip | missing"""
    out = Path(output) if output else None
    size = f"{out.stat().st_size / 2**20:.1f}" if out and out.is_file() else ""
    row = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "step": step,
        "status": status,
        "source": str(source),
        "output": str(out) if out else "",
        "detail": detail,
        "minutes": f"{minutes:.1f}" if minutes is not None else "",
        "size_mb": size,
    }
    new = not HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", choices=["prep", "ocr", "mux"])
    a = ap.parse_args()
    if not HISTORY.exists():
        print("Chưa có history.csv")
        return 0
    with HISTORY.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if not a.step or r["step"] == a.step]
    for r in rows:
        name = Path(r["output"]).name if r["output"] else Path(r["source"]).name
        extra = " ".join(x for x in (r["detail"], r["minutes"] and f'{r["minutes"]}ph',
                                      r["size_mb"] and f'{r["size_mb"]}MB') if x)
        print(f'{r["time"]}  {r["step"]:<4} {r["status"]:<7} {name}  {extra}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
