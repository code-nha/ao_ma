# nhan_vat: look and feel

Mục tiêu: một harness nhỏ để LLM chạy local đóng một nhân vật và nói chuyện nhiều lượt với nhân vật khác mà vẫn ra người. Nhân vật cần giữ vai, giọng nói có hồn, câu chuyện có tiến triển, và hành xử giống người thật.

Tài liệu này gồm ba phần: những điều đã rút ra từ thí nghiệm, định hướng, và các đề xuất đang để ngỏ. Chi tiết số liệu nằm trong `experiments/TEST_PROTOCOL.md` và `experiments/logs/`. Xem log bằng `python viewer/serve.py`.

---

## 1. Những điều đã rút ra

### 1.1 Hai kết quả đáng giá nhất
1. **Đạo diễn (director v2) là thiết kế cốt lõi.** Có đạo diễn, model nhỏ giữ được vai qua câu chuyện dài tùy ý. Không có đạo diễn, model hỏng vai từ khoảng 2k token.
2. **Ở tiếng Anh, Gemma 4 E4B (chạy local, 8GB) ngang Gemma 4 26B.** Khoảng cách giữa hai model chỉ lộ ra ở tiếng Việt.

### 1.2 Hỏng vai do cách tổ chức prompt, không do độ dài context
- Hỏi một lượt thì Gemma E4B vẫn đúng vai tới ~49k token. Kiểu test này không lộ ra vấn đề.
- Hội thoại nhiều lượt mà không có đạo diễn thì lẫn vai từ ~2k token, tới ~6k là hỏng hẳn và kẹt trong vòng lặp chào tạm biệt. Nguyên nhân là **hai nhân vật kéo nhau trôi**: lời thoại dồn chung một context, mỗi bên bắt chước giọng bên kia.
- Quy tắc rút ra: **mỗi lần gọi model chỉ nên đọc ≤ ~3k token** (khoảng 2.400 chữ tiếng Việt, 18–25 lượt thoại). Câu chuyện vẫn dài bao nhiêu cũng được, miễn lời thoại cũ được nén lại.

### 1.3 Đạo diễn v2 làm gì
| Cơ chế | Tác dụng |
|---|---|
| Chia **cảnh**. Hết cảnh thì lời thoại bị bỏ, chỉ giữ **tóm tắt 2 câu, chỉ ghi sự việc** | Giữ prompt ngắn. Tóm tắt không ghi "bài học" nên các cảnh sau không bị kéo về cùng một chủ đề |
| **Ghi chú riêng ở cuối prompt**: mục tiêu riêng của nhân vật, nhịp truyện tiếp theo, nhắc vai. Nhân vật kia không thấy | Phần cuối prompt ảnh hưởng mạnh nhất tới model. Bí mật của mỗi người không lọt sang người kia |
| **Nhịp truyện** đẩy câu chuyện đi tiếp. Chặn chào tạm biệt khi cảnh chưa xong | Câu chuyện có tiến triển, hết vòng lặp tạm biệt |
| **Sinh lại** câu bị lẫn vai (bắt bằng regex), tối đa 2 lần | Lẫn vai còn 0% |
| Phát hiện **lặp ý** thì chèn sự kiện hoặc yêu cầu đổi chủ đề. **Cấm cụm từ** bị lặp quá nhiều | Giảm câu chuyện đi vòng quanh |

Đã thử và đang **tạm gác**:
- **v3 (sổ nhớ):** sau mỗi cảnh, trích ra "chuyện đã kể / điều đã biết / việc đã làm" dạng JSON. Đạo diễn dùng sổ này để đổi những chuyện đã kể rồi.
- **v3.1:** chặn kể lại ngay lúc sinh, đánh dấu mục tiêu đã xong. Bão 99 giảm từ 6 cảnh xuống 1, nhưng chạy chậm hơn ~35%.

### 1.4 Model
| Model | Đánh giá |
|---|---|
| **gemma4:26b (máy wee)**: model chính | Tiếng Việt tốt nhất: giọng miền Trung, có qua có lại, phản ứng đúng vai (nghe Minh nói tiếng Anh thì gắt "cái từ chi nghe lạ tai quá"). Tiếng Anh ngang E4B |
| **gemma4:e4b (local)**: dự phòng | Nhanh, chạy trọn trên 8GB. Tiếng Anh tốt. Tiếng Việt kém một bậc: lạm dụng "cái", hay giảng "cái tâm" |
| qwen3.5:9b: loại | Qua regex thì gần như không lỗi, nhưng **đọc thì không ra người**: văn vẻ, dài, giảng đạo lý, mâu thuẫn tiểu sử. Tiếng Việt còn lẫn chữ Trung và sai xưng hô. Lỗi giống nhau ở cả hai ngôn ngữ |

Benchmark tiếng Anh (EQ-Bench Creative Writing, RP-Bench) cũng xếp họ Gemma 4 đầu nhóm model nhỏ.

### 1.5 Đánh giá
- **Thước đo chính là chất lượng lời thoại**, phải đọc cùng một cảnh của các model đặt cạnh nhau. Chỉ số regex (lẫn vai, xưng hô, lặp, độ dài) chỉ là điều kiện cần. Chính các chỉ số đó đã khiến Qwen trông như tốt nhất.
- Những lỗi regex không bắt được: lão tự xưng "thầy", chữ Trung lọt vào câu, câu bị cắt ngang, giảng đạo lý, nhại lời người kia, mâu thuẫn tiểu sử, giọng văn viết thay vì giọng nói.
- Thông tin nào nằm trong persona thì model sẽ **lôi ra kể đi kể lại** (Hoàng Sa, bão 99, năm 14 tuổi). Cảnh mà giao nhiệm vụ "kể chuyện X" thì model cũng kể X nhiều lần trong cùng cảnh.
- Ghi "đừng làm X" trong prompt có tác dụng yếu với model nhỏ, có khi còn gợi ý ngược. Kiểm tra sau khi sinh rồi sinh lại thì hiệu quả hơn.

### 1.6 Vận hành
- Ollama: dùng `think: false`, `temperature` 0.8, `num_ctx` 8192 khi chạy local.
- Máy wee (dùng chung): phải hỏi session `wee_admin` trước, gửi từng request một, **không gửi `num_ctx` và `keep_alive`**. Các script đã tự xử lý việc này khi có `--api`.
- Gemma thỉnh thoảng lặp chữ ("nó nó nó…"). Nếu không chặn, câu lỗi đó nằm lại trong prompt và làm hỏng mọi lượt sau.

---

## 2. Định hướng

1. **Đạo diễn là trung tâm, nhân vật là diễn viên.** LLM không phải tự giữ vai, tự nhớ hay tự dẫn truyện. Đạo diễn (code, có quy tắc rõ ràng) lo việc đó. LLM chỉ cần diễn cho hay ở từng lượt.
2. **Mỗi lượt, model chỉ thấy đúng phần nó cần:** persona, những gì đã xảy ra (nén lại), cảnh hiện tại, và chỉ thị riêng. Không bao giờ đưa cho model toàn bộ lịch sử.
3. **Persona tách khỏi code**, viết thành file để người viết truyện chỉnh được mà không động vào harness.
4. **Đánh giá bằng cách đọc.** Mọi thay đổi đều phải được đọc so với bản trước, không chỉ nhìn bảng số.
5. **Model chạy local là mặc định, máy mạnh dùng khi cần.** Thiết kế phải chạy được trên E4B, và chạy tốt hơn khi có 26B.

---

## 3. Đề xuất (đang để ngỏ, chưa đủ trừu tượng)

Các ý dưới đây là bản nháp để bàn tiếp, chưa chốt. Hiện chúng đang quá cụ thể, cần tìm ra lớp trừu tượng chung trước khi viết code.

### 3.1 Tách persona thành file
Theo quy ước của các harness kiểu OpenClaw:
- **IDENTITY:** sự thật ngắn (tên, tuổi, nghề, quan hệ).
- **SOUL:** giá trị, thế giới quan, cách phản ứng, giới hạn.
- **STYLE:** giọng nói, xưng hô, từ cấm, độ dài, kèm **ví dụ câu tốt và câu xấu lấy từ log**.

Bài học từ thí nghiệm:
- Lý lịch dài nên chuyển sang một **kho chuyện** để đạo diễn chọn chuyện chưa kể, không để hết trong persona.
- Phần nhắc vai ở cuối prompt nên **sinh tự động từ STYLE**.
- Kịch bản cảnh **không thuộc persona**.

### 3.2 Hai tầng còn thiếu
1. **Thế giới và thông tin bất cân xứng.** Cần biết cảnh này liên quan tới những ai, kể cả người không có mặt. Đạo diễn giữ **sự thật gốc**, còn mỗi nhân vật chỉ thấy những gì mình biết hoặc tin, kể cả niềm tin sai, và biết người kia biết gì. Khi có người nói dối, cả lời nói lẫn sự thật đều được ghi lại, và người nghe tin hay không tùy theo mức tin tưởng. Thiếu tầng này thì các cảnh lừa lọc, đấu trí không thể có kịch tính.
2. **Công thức ra quyết định có cảm xúc.** Nhân vật có nhu cầu, nỗi sợ, tính khí, cộng thêm một **trạng thái giống hormone** thay đổi theo từng lượt (giận, sợ, tự ái, say, mệt…, tăng vọt khi bị kích hoạt và phai dần theo thời gian). Ở những lượt phải chọn, phần lý trí cân với phần bốc đồng, cảm xúc càng mạnh thì càng thiếu lý trí. **LLM không tự quyết, chỉ diễn quyết định** do đạo diễn đưa ra, như vậy nhân vật vừa nhất quán vừa có lúc làm điều dại dột giống người.

Câu hỏi còn mở:
- Lớp trừu tượng chung cho "thế giới, hiểu biết, cảm xúc, quyết định" là gì? Mục tiêu là cùng một bộ máy dùng được cho cảnh tâm sự lẫn cảnh đấu trí, không phải viết luật riêng cho từng cảnh.
- Phần nào để code tính (đúng, ổn định), phần nào giao cho LLM (linh hoạt, có hồn)?
- Làm sao giữ chi phí mỗi lượt thấp (prompt ≤ 3k token, ít lần gọi thêm) để vẫn chạy được trên E4B?

### 3.3 Việc nhỏ còn tồn
- Đưa bước **S3 chấm lời thoại** vào quy trình test: bắt lỗi tự động cộng chấm mù theo tiêu chí.
- Sửa v2:
  - "cái" nằm trong danh sách hư từ nên bộ cấm không bắt được "cái tâm";
  - regex bắt nhầm cụm "hai đứa mình";
  - Minh hay bọc chữ trong `*...*`;
  - 26B hay chốt lượt bằng một câu đạo lý.
- Chưa test gemma4:12b.
- Session `ebook_maker` đang cần định dạng profile nhân vật để làm skill tạo ảnh chân dung. Định dạng này nên lấy từ IDENTITY và phần ngoại hình, sau khi chốt cấu trúc persona.
