# Quy trình test nhập vai cho model local

Mục tiêu: so sánh các model local (Ollama, GPU 8GB) với cùng một bài test. Bài test đo việc nhân vật giữ được vai khi hội thoại nhiều lượt với một nhân vật khác.

## Tóm tắt kết quả đến nay (gemma4:e4b-it-q4_K_M)

| Thí nghiệm | Kết quả |
|---|---|
| VRAM | Khoảng 3 GB, 100% chạy trên GPU tới 32k ctx, 50–60 tok/s |
| Hỏi một lượt, context đầy văn bản trung tính | Vẫn giữ vai tới ~49k token. Kiểu test này không làm lộ vấn đề |
| Hội thoại nhiều lượt, không có đạo diễn | Lẫn vai từ ~2k token. Từ ~6k thì gần như lượt nào cũng lẫn, kẹt trong vòng lặp chào tạm biệt |
| Có đạo diễn v1 (cắt cảnh, nhắc vai, sinh lại) | Lẫn vai còn 0.5%, nhưng hay xuống dòng và hay giảng đạo lý |
| **Có đạo diễn v2, đang dùng làm chuẩn** | Lẫn vai 0% sau khi sinh lại, 95% lượt lão xưng "lão", prompt mỗi lượt ≤ 3k token |
| Đạo diễn v3 / v3.1 (sổ nhớ, chặn kể lại) | Kể lại chuyện cũ ít hẳn, nhưng chậm hơn khoảng 35%. Đang tạm gác, vẫn giữ v2 làm chuẩn |

**Model chính (chọn ngày 2026-11-23): `gemma4:26b` trên máy wee**, chạy bằng `--model gemma4:26b --api http://wee:11435`. Lý do chọn:
- Lời thoại tiếng Việt tốt nhất trong 3 model đã thử: ra giọng miền Trung, hội thoại có qua có lại, ít kể lặp chuyện cũ.
- Tiếng Anh ngang Gemma E4B.

Gemma E4B chạy local là phương án dự phòng. Qwen 3.5 9B bị loại vì văn vẻ, giảng đạo lý, mâu thuẫn tiểu sử, lẫn chữ Trung.

Trước khi chạy trên wee phải hỏi session `wee_admin`. Gọi tuần tự từng request một, không gửi `num_ctx` và `keep_alive` (script đã tự bỏ hai tham số này khi gọi máy remote).

Bài học chính: với model nhỏ, độ dài context không phải thứ giới hạn. Thứ làm hỏng vai là hai nhân vật kéo nhau trôi khỏi vai khi lời thoại nhiều lượt dồn chung một context. Nên phải test bằng hội thoại nhiều lượt, không dùng câu hỏi một lượt.

## Các tham số cố định (không đổi giữa các model)

- Persona Lão Bảy và Minh, 10 cảnh, 7 sự kiện: đúng như trong `dialogue_director_v2.py`.
- `temperature` 0.8, `think: false`, `num_ctx` 8192 cho đạo diễn, 32768 cho stage 1.
- Seed 1. Muốn chắc hơn thì chạy thêm seed 9.
- Lão trả lời tối đa 160 token mỗi lượt. Đạo diễn sinh lại tối đa 2 lần.
- Tokenizer mỗi model khác nhau, nên "24k token" là xấp xỉ. Với Gemma, 1 token ≈ 0,8 chữ tiếng Việt.

## Các bước

Chạy trong thư mục `experiments/`. Thay `MODEL` bằng tên model trong Ollama.

| Stage | Lệnh | Thời gian (Gemma) | Đo cái gì |
|---|---|---|---|
| S0 VRAM | `python -I vram_probe.py 4096 8192 16384 32768 --model MODEL` | ~1 phút | Phần trăm chạy trên GPU, tok/s ở mỗi mức ctx |
| S1 không đạo diễn | `python -I dialogue_test.py 8000 300 1 --model MODEL` | ~4 phút | Model tự giữ vai tới đâu (ngưỡng bắt đầu lẫn vai) |
| S2 có đạo diễn v2 | `python -I dialogue_director_v2.py 24000 1 --model MODEL` | ~10 phút | Chất lượng khi chạy với harness thật |
| Chấm | `python -I score.py MODEL_A MODEL_B ...` | tức thì | Bảng điểm và cột đạt/trượt |

Log nằm trong `logs/`. Tên file có kèm tên model, trừ Gemma vẫn dùng tên cũ. Xem log trên viewer tại http://127.0.0.1:8765/.

Điều kiện trước khi chạy:
- Không có model nào khác đang chiếm GPU. Kiểm tra bằng `ollama ps`.
- Chạy xong thì `ollama stop MODEL` để giải phóng GPU.
- Không test các model `kev:*`, vì chúng đã được chuyển thành model ra quyết định.

## Tiêu chí đạt (S2, đạo diễn v2)

| Chỉ số | Ngưỡng |
|---|---|
| Chạy 100% trên GPU ở 8k ctx | bắt buộc |
| Lẫn vai sau sinh lại | ≤ 1% |
| Lẫn vai ở lần sinh đầu (đạo diễn phải sửa nhiều cỡ nào) | ≤ 10% |
| Lão có xưng "lão" | ≥ 90% |
| Xuống dòng | ≤ 5% |
| Chào tạm biệt | ≤ 5% |
| Lặp chữ kiểu "nó nó nó nó" | ≤ 2 lượt |
| Độ lặp nửa sau so với nửa đầu | tăng không quá 0.02 |

Các chỉ số chỉ để tham khảo, không tính đạt/trượt:
- motif bị lặp lại (Hoàng Sa, bão 99, "cái tâm", "tự nhiên");
- tỉ lệ lượt bị cấm cụm từ;
- độ "nhại lời": hai nhân vật lặp lại câu của nhau. Đo bằng độ trùng từ giữa một lượt và lượt ngay trước của người kia;
- số chữ mỗi lượt;
- số giây mỗi lượt;
- kết quả S1.

Phát hiện lẫn vai hiện chỉ dùng regex: xưng "ông", "Dạ", chêm tiếng Anh/emoji, "mình", nhận là AI hoặc viết code. Đọc vài cảnh trên viewer vẫn cần thiết để đánh giá giọng văn.
