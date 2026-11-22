# Upscale prep — 2 phim HK DVD (gửi senlab_admin)

Đầy đủ ffprobe JSON: `angel1.ffprobe.json`, `devils.ffprobe.json`. idet (3000 frame từ 10:00): `*.idet.txt`.

## Raped By an Angel 1 (1995) — `Raped By an Angel 1 (1995) DVD5.mkv`
- Video: MPEG-2 720x480, SAR 8:9 / DAR 4:3, 29.97, field_order tt, letterbox
- Audio: #1 AC3 5.1 384k, lang=chi, title "Surround 5.1" (track duy nhất, coi là tiếng Quảng Đông)
- Sub: dvd_subtitle eng
- Duration 1:35:21
- idet: Repeated N2630/T167/B204 · Single TFF2501 P16 U484 · Multi TFF3001
- Sau `fieldmatch` (1800 frame): P1304 / combed 389 / U108 → ~72% khớp được → **hybrid: telecine + đoạn interlaced thật**. IVTC + yadif=deint=interlaced dọn phần còn lại.

## Devils Woman (1996) — `Devils Woman 1996 NTSC DVD5.iso`
- 1 title duy nhất (`-f dvdvideo -title 1`), 1:34:29
- Video: MPEG-2 720x480, SAR 8:9 / DAR 4:3, 29.97, TFF, letterbox
- Audio: a:0 AC3 4.0 320k, a:1 AC3 2.0 320k — **không có tag ngôn ngữ**; đoán a:0 (4.0) là Quảng Đông, a:1 là Quan Thoại — CHƯA xác minh (cần nghe)
- Sub: không có trong title
- idet: Repeated N2538/T232/B231 · Single TFF2260 P334 U406 · Multi TFF3001
- Sau `fieldmatch`: P1562 / combed 68 / U171 → ~87% → **telecine** (pattern không đều nên Repeated Fields thấp hơn 3:2 chuẩn)

## Sample (60s từ 10:00)
| file | nội dung |
|---|---|
| `*_sample_raw.mkv` | copy thô MPEG-2 + tất cả audio |
| `*_sample_ivtc.mkv` | `fieldmatch,yadif=deint=interlaced,decimate` → 23.976, x264 crf12 slow film, audio copy |
| `*_sample_bwdif.mkv` | `bwdif=mode=send_frame` → 29.97, cùng encode (để so) |

Tất cả giữ 720x480 SAR 8:9. Đề xuất: dùng bản **IVTC** cho cả hai, chạy node với deinterlace=off.
