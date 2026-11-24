"""OCR phụ đề bitmap DVD (VobSub / dvd_subtitle) sang SRT bằng Tesseract.

Lý do: sub bitmap vẽ trên canvas 720x480; khi node upscale cắt viền đen, player
ép canvas vào khung đã cắt nên sub bị dẹt. SRT là chữ nên hiển thị đúng ở mọi
khung hình và sắc nét ở 4K.

Cần: Tesseract (scoop install tesseract) + eng.traineddata (tessdata_best),
      .venv có av, pillow, pytesseract.

Dùng:
  .venv\\Scripts\\python ocr_vobsub.py "F:\\tmp\\Video\\phim.mkv"
  ... --stream 0 --lang eng --workers 6
Output (cạnh file gốc):
  <tên gốc>.<lang>.srt          phụ đề chữ
  <tên gốc>.<lang>.ocr-review.txt   các dòng Tesseract kém tự tin, để soát
mux_subs.py tự nhận file .srt cùng tên (xem SUB_EXT bên đó).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import av
import pytesseract
from PIL import Image, ImageOps

from history import record

SCALE = 3          # phóng bitmap trước khi OCR (sub DVD chữ cao ~20px)
PAD = 20
LOW_CONF = 75


@dataclass
class Event:
    start: int  # ms
    end: int
    img: Image.Image
    text: str = ""
    conf: float = 0.0


def text_mask(idx: bytes, w: int, h: int) -> Image.Image:
    """Từ ảnh chỉ số màu (≤4 màu) dựng ảnh chữ đen trên nền trắng.

    Theo spec DVD SPU, chỉ số 0 = nền (nếu không có 0 thì lấy màu chiếm nhiều
    nhất ở mép). Sau đó bóc lớp: lớp kế tiếp là màu có tỉ lệ điểm sát lớp
    ngoài cao nhất (viền ngoài -> viền trong -> ...). Chỉ lớp TRONG CÙNG là
    chữ — giữ được khe hở như giữa thân và chấm của dấu "!".
    """
    cnt = Counter(idx)
    if 0 in cnt:
        bg = 0
    else:
        border = [idx[i] for i in range(w)] + [idx[(h - 1) * w + i] for i in range(w)]
        border += [idx[y * w] for y in range(h)] + [idx[y * w + w - 1] for y in range(h)]
        bg = Counter(border).most_common(1)[0][0]
    remaining = [k for k in cnt if k != bg]
    if not remaining:
        return Image.new("L", (w, h), 255)
    outer = {bg}
    while len(remaining) > 1:
        touch = Counter()
        for y in range(h):
            row = y * w
            for x in range(w):
                v = idx[row + x]
                if v in outer:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and idx[ny * w + nx] in outer:
                        touch[v] += 1
                        break
        layer = max(remaining, key=lambda k: touch[k] / cnt[k])
        outer.add(layer)
        remaining.remove(layer)
    fill = remaining[0]
    lut = [0 if i == fill else 255 for i in range(256)]
    return Image.frombytes("L", (w, h), idx).point(lut)


def extract(path: Path, stream_no: int) -> tuple[list[Event], str]:
    opts = {}
    fmt = None
    if path.suffix.lower() == ".iso":
        fmt = "dvdvideo"
        opts = {"title": "1"}  # TODO: chọn title dài nhất nếu ISO có sub
    c = av.open(str(path), format=fmt, options=opts)
    s = c.streams.subtitles[stream_no]
    lang = (s.metadata.get("language") or "und").lower()
    tb = float(s.time_base)
    events: list[Event] = []
    for p in c.demux(s):
        if p.pts is None:
            continue
        rects = s.codec_context.decode(p)
        start = round(p.pts * tb * 1000)
        dur = round((p.duration or 0) * tb * 1000)
        if events and events[-1].end <= events[-1].start:  # sub trước không có duration
            events[-1].end = start
        if not rects:  # gói "xoá màn hình"
            continue
        # gộp mọi rect của gói vào 1 ảnh theo toạ độ
        x0 = min(r.x for r in rects); y0 = min(r.y for r in rects)
        x1 = max(r.x + r.width for r in rects); y1 = max(r.y + r.height for r in rects)
        canvas = Image.new("L", (x1 - x0, y1 - y0), 255)
        for r in rects:
            canvas.paste(text_mask(bytes(r.planes[0]), r.width, r.height), (r.x - x0, r.y - y0))
        events.append(Event(start, start + dur, canvas))
    c.close()
    return events, lang


def ocr(ev: Event, lang: str) -> None:
    img = ev.img.resize((ev.img.width * SCALE, ev.img.height * SCALE), Image.LANCZOS)
    img = ImageOps.expand(img, PAD, fill=255)
    psm = 7 if ev.img.height < 40 else 6  # 1 dòng / nhiều dòng
    d = pytesseract.image_to_data(img, lang=lang, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(d["text"]):
        if word.strip():
            lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(word)
            confs.append(float(d["conf"][i]))
    ev.text = clean("\n".join(" ".join(ws) for ws in lines.values()))
    ev.conf = min(confs) if confs else 0.0


FIXES = [
    (re.compile(r"(?<![A-Za-z])\|(?![A-Za-z])"), "I"),
    (re.compile(r"(?<![A-Za-z])l(?=['’]?[mdl]?\b)(?=\s|'|’)"), "I"),  # "l'm", "l will"
    (re.compile(r"\s+([,.!?;:])"), r"\1"),
    (re.compile(r"[‘’`]"), "'"),
    (re.compile(r"[“”]"), '"'),
    (re.compile(r"\b[Ii]'s\b"), "It's"),                      # "i's" -> "It's"
    (re.compile(r"\bls\b"), "Is"),                            # "ls she" -> "Is she"
    (re.compile(r"\bOKI"), "OK!"),
    (re.compile(r"(?<=[a-z]) (Is|In|It)\b"), lambda m: " " + m.group(1).lower()),  # "She Is sick"
    (re.compile(r"(?<!\d)(\d) ?[O0](?!\w)"), r"\g<1>0"),      # "1 O year" -> "10"
    (re.compile(r"(?<![\d\w])(\d) (\d+)\b"), r"\1\2"),        # "1 0" -> "10", "1 993" -> "1993"
]


def clean(t: str) -> str:
    for pat, rep in FIXES:
        t = pat.sub(rep, t)
    return "\n".join(line.strip() for line in t.splitlines() if line.strip())


def ts(ms: int) -> str:
    h, ms = divmod(ms, 3_600_000); m, ms = divmod(ms, 60_000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--stream", type=int, default=0, help="thứ tự luồng phụ đề (0 = đầu tiên)")
    ap.add_argument("--lang", default=None, help="ngôn ngữ Tesseract (mặc định: eng)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dump", action="store_true", help="lưu ảnh từng sub vào thư mục <tên>.ocr-img để soát")
    a = ap.parse_args()

    src = Path(a.source.strip('"'))
    t0 = time.time()
    print(f"Đọc phụ đề: {src}")
    events, lang = extract(src, a.stream)
    tlang = a.lang or "eng"
    print(f"  {len(events)} sub, ngôn ngữ luồng: {lang}; OCR bằng tesseract '{tlang}'")
    with ThreadPoolExecutor(a.workers) as ex:
        for i, _ in enumerate(ex.map(lambda e: ocr(e, tlang), events), 1):
            if i % 100 == 0:
                print(f"  OCR {i}/{len(events)}", flush=True)

    tag = lang if lang != "und" else tlang
    srt = src.with_name(f"{src.stem}.{tag}.srt")
    review = src.with_name(f"{src.stem}.{tag}.ocr-review.txt")
    n = 0
    bad = []
    with srt.open("w", encoding="utf-8") as f:
        for ev in events:
            if not ev.text:
                bad.append((ev, "(trống)"))
                continue
            n += 1
            f.write(f"{n}\n{ts(ev.start)} --> {ts(max(ev.end, ev.start + 500))}\n{ev.text}\n\n")
            if ev.conf < LOW_CONF:
                bad.append((ev, f"conf {ev.conf:.0f}"))
    with review.open("w", encoding="utf-8") as f:
        for ev, why in bad:
            f.write(f"{ts(ev.start)}  [{why}]  {ev.text!r}\n")
    if a.dump:
        d = src.with_name(f"{src.stem}.ocr-img"); d.mkdir(exist_ok=True)
        for ev in events:
            ev.img.save(d / f"{ts(ev.start).replace(':', '-').replace(',', '.')}.png")
    print(f"  xong: {srt.name} ({n} dòng); cần soát: {len(bad)} -> {review.name}")
    record("ocr", "ok", src, srt, f"{n} dòng, cần soát {len(bad)}", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
