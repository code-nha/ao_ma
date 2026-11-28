# nhan_vat

Harness nhỏ để model chạy local đóng một nhân vật. Nhân vật nói chuyện nhiều lượt với nhân vật khác mà vẫn giữ vai, và tự quyết
ngoại hình của mình: chọn nét từ kho nét, rồi xem ảnh của chính mình và sửa.

Nhân vật mẫu: **Lão Bảy**, 70 tuổi, ngư dân (`characters/lao_bay/`).

## Hai mảng việc

**1. Hội thoại giữ vai.** Hai nhân vật nói chuyện với nhau qua một "đạo diễn" viết bằng luật (cắt cảnh, nhắc vai, sinh lại lượt
lẫn vai). Đạo diễn v2 đang là chuẩn: lẫn vai 0% sau khi sinh lại. Kết quả và cách đo: `experiments/TEST_PROTOCOL.md`; bài học
và định hướng: `look_and_feel.md`.

**2. Ngoại hình (LOOK).** Người viết truyện chỉ viết IDENTITY, SOUL, LIFE. Nhân vật tự viết STYLE và tự xây LOOK:
1. `luan_hoi.py`: code đọc đời sống từ hồ sơ, lọc kho nét, nhân vật chọn giá trị cho từng ô (mặt, tóc, dáng, dấu vết); code và
   Luân hồi kiểm mâu thuẫn và lý do. Kết quả: `characters/<id>/LOOK.kb.json` và sổ nét của story.
2. `look_loop.py`: vẽ ảnh từ LOOK (Qwen Image trên ComfyUI), "mắt" tả ảnh mù rồi so với LOOK, nhân vật xem ảnh của mình và
   nhấn mạnh hoặc chọn lại nét; tối đa 5 vòng.

Trạng thái và việc còn lại: `characters/BACKLOG.md`.

## Bố cục

| Đường dẫn | Là gì |
|---|---|
| `HARNESS.md` | kiến trúc harness: lời gọi model, đạo diễn, Luân hồi, vòng ảnh, log, cách mở rộng, chỗ yếu |
| `look_and_feel.md` | mục tiêu, bài học từ thí nghiệm, định hướng |
| `kling_look_and_feel.md` | dùng Kling cho hình ảnh nhân vật: element, giới hạn, credit, quy trình, nhật ký thử |
| `characters/SPEC.md` | bộ file nhân vật: IDENTITY, SOUL, LIFE, STYLE, LOOK (bản cho model: `SPEC.en.md`) |
| `characters/LOOK_SLOTS.md` | khung 42 ô LOOK |
| `characters/LOOP.md` | thiết kế vòng ảnh |
| `characters/KB_DESIGN.md` | thiết kế kho nét |
| `characters/BACKLOG.md` | việc còn lại, kết quả các lần chạy |
| `characters/<id>/` | hồ sơ một nhân vật; `*.md` tiếng Việt cho người, `*.en.md` tiếng Anh cho model |
| `characters/stories/<story>/registry.json` | sổ nét của một story (để các nhân vật không trùng nét quá nhiều) |
| `characters/kb/` | kho nét: `catalog/<ô>.jsonl` là nguồn sự thật, `kb.py` kiểm và dựng, `kbq.py` để truy vấn; xem `kb/README.md` |
| `characters/kb_review/`, `loop_review/` | các bản review thiết kế (Opus, Fable) |
| `characters/t_lan/`, `t_lao_bay_twin/`, `stories/acc*` | nhân vật và story thử, dữ liệu nghiệm thu |
| `experiments/` | script thí nghiệm (bảng dưới) |
| `experiments/logs/` | log JSONL, mỗi dòng một lượt hoặc một lời gọi |
| `experiments/look_loop/<id>/<ts>/` | mỗi lần chạy vòng ảnh: LOOK và prompt từng vòng; ảnh PNG chỉ có trên máy (không commit) |
| `viewer/` | trang web xem log |

## Script

Chạy trong `experiments/`, luôn với `python -I`. Tham số đầy đủ: docstring đầu mỗi file.

| Script | Làm gì |
|---|---|
| `dialogue_director_v2.py` | hội thoại hai nhân vật có đạo diễn (chuẩn); `_v2_en` bản tiếng Anh, `_v3`, `_v31` đang gác |
| `dialogue_director.py`, `dialogue_test.py`, `drift_test.py` | các bản trước: đạo diễn v1, không đạo diễn, thử một lượt |
| `score.py`, `rescore.py` | chấm log hội thoại theo `TEST_PROTOCOL.md` |
| `vram_probe.py` | đo VRAM và tốc độ theo num_ctx (máy riêng, không chạy trên wee) |
| `char_style_look.py` | nhân vật tự viết STYLE (và LOOK dạng văn, bản cũ) |
| `luan_hoi.py` | chọn LOOK từ kho nét; `--redo` cho look_loop chọn lại vài ô |
| `look_loop.py` | vòng ảnh: vẽ, mắt chấm, nhân vật tự sửa |
| `eval_eye.py` | so các cách hỏi "mắt" trên ảnh đã có |
| `body_prompt_test.py` | thử cách viết thân người trong prompt Qwen |
| `choose_test.py`, `choose_test_report.py`, `choose_rate.py` | thử cho nhân vật tự chọn bản cuối (đã bỏ, xem BACKLOG) |

Ví dụ:
```
cd nhan_vat/experiments
python -I dialogue_director_v2.py 8000 1
python -I luan_hoi.py lao_bay --story acc5 --api http://wee:11435
python -I look_loop.py lao_bay --api http://wee:11435 --server http://senlab:8188
```

Kho nét:
```
cd nhan_vat/characters/kb
python -I kb.py check
python -I kb.py build
```

Xem log: `python viewer/serve.py` (trong `nhan_vat/`), mở http://localhost:8765.

## Máy

- **Ollama local:** `gemma4:e4b-it-q4_K_M` cho các thí nghiệm hội thoại.
- **wee** (`http://wee:11435`, dùng chung): `gemma4:26b` cho Luân hồi, nhân vật, mắt. Gọi tuần tự, `think: false`, không gửi
  `options`, `num_ctx`, `keep_alive` (đổi những thứ này làm wee nạp lại model). Đợt lớn hỏi người quản wee trước.
- **senlab** (`http://senlab:8188`, ComfyUI dùng chung): Qwen Image 2.1. Gửi từng ảnh một, báo trước khi chạy, gặp lỗi CUDA thì
  dừng. `look_loop.py` cần harness `render_t2i.py` của Qwen ở `C:\Users\khoa\xyz\hoa_si\qwen\research_v2\harness`.

## Quy ước

- Tài liệu cho người: tiếng Việt. Mọi thứ đưa cho model: tiếng Anh (file `*.en.md`, kho nét).
- Kho nét chỉ dùng nguồn không cần mua hay xin giấy phép; mỗi giá trị ghi nguồn.
- Python chỉ dùng thư viện chuẩn; riêng `characters/kb/src/pdf_text.py` (đọc PDF nguồn khi chưng cất) cần `pypdf`.
