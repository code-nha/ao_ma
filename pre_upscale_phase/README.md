# pre_upscale_phase

Chuẩn bị phim DVD (ISO / MKV, NTSC, thường bị telecine) cho pipeline upscale
`RelayVSR Film Upscale` trên senlab (ComfyUI), rồi ghép phụ đề + audio gốc vào
bản upscale khi tải về. Senlab chỉ lo video; phụ đề do bên này lo.

## Cần có
- ffmpeg/ffprobe ≥ 8 có demuxer `dvdvideo` (đang dùng 9.0.2, winget Gyan.FFmpeg)
- Python 3.12+
- Chỉ cho OCR: Tesseract (`scoop install tesseract`, 5.5.3) +
  `eng.traineddata` từ tessdata_best, và `.venv`:
  `uv venv .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt`

## Quy trình
1. **Chuẩn bị** — ghi đường dẫn vào `input.txt` (mỗi dòng 1 file, có ngoặc kép
   cũng được), rồi:
   ```
   python prep_upscale.py               # --test 60 để thử 60s, --crf 15 cho file nhỏ hơn
   ```
   `python prep_upscale.py --check` chỉ in bảng phân loại. Tự chọn theo idet +
   fieldmatch + fps: `.ivtc` (telecine NTSC → 23.976), `.fm` (khớp field, không
   decimate), `.bwdif` (interlaced thật), `.copy` (ISO progressive, chỉ tách),
   `skip` (progressive sẵn, gửi file gốc). x264 crf 12, giữ độ phân giải + SAR,
   audio a:0, giữ sub.
   File progressive 29.97 nên chạy thêm `python dupcheck.py "file"` (đếm frame lặp
   theo nhịp 1/5). Nếu báo DECIMATE → `--mode decimate`; nếu decoder ra ~24
   frame/s dù header 29.97 (soft telecine) → `--mode cfr24`. Cả hai ra 23.976,
   x4 nhanh hơn ~20%.
2. **Upscale** — user tự chuyển file lên senlab, chạy node với
   **deinterlace=off cho MỌI file đã qua prep_upscale** (.ivtc / .fm / .bwdif /
   .copy và cả file `skip` gửi nguyên gốc), crop_black_bars=auto.
   Lý do: MPEG-2 encode kiểu xen dòng báo interlaced=True ở mọi frame dù nội
   dung progressive, nên auto sẽ bwdif nhầm và làm mềm hình (senlab đã test).
   Chỉ để auto với file chưa ai kiểm tra. Tải về file output **kèm `job.json`** của job
   (`output/relayvsr_film/<tên>_<jobid>_chunks/job.json`), không cần các chunk.
3. **OCR phụ đề** (khi phim có sub bitmap DVD — sub bitmap sẽ bị dẹt vì node cắt viền):
   ```
   .venv\Scripts\python ocr_vobsub.py "H:\...\phim.mkv"
   ```
   Ra `<tên gốc>.<lang>.srt` + `<tên gốc>.<lang>.ocr-review.txt` (dòng cần soát).
4. **Ghép** — video upscale + audio gốc + SRT (mặc định, bỏ sub bitmap):
   ```
   python mux_subs.py "phim_upscale.mp4" "H:\...\phim gốc.mkv"
   python mux_subs.py --list pairs.txt   # mỗi dòng: "upscale" | "gốc"
   ```
   Offset lấy từ `job.json` → HHMMSS trong tên file → 0.

## Lịch sử xử lý
Cả 3 script ghi mỗi file đã xử lý (ok / error / skip / missing) vào
`history.csv` (UTF-8 BOM, mở bằng Excel được; gitignore vì là trạng thái máy này).
```
python history.py              # xem tóm tắt
python history.py --step prep  # chỉ bước prep (hoặc ocr / mux)
```

## Ghi chú kỹ thuật
- Phim HK trên DVD NTSC: idet báo interlaced TFF nhưng `fieldmatch` khớp
  72–87% → telecine/hybrid → `fieldmatch,yadif=deint=interlaced,decimate` (23.976).
- Sub DVD: chỉ số màu 0 = nền (spec SPU); `ocr_vobsub.py` bóc lớp viền từ ngoài
  vào, chỉ giữ lớp trong cùng làm chữ (giữ khe hở dấu "!").
- `out/` — báo cáo + ffprobe/idet của 2 phim mẫu gửi senlab (sample .mkv bị gitignore).
