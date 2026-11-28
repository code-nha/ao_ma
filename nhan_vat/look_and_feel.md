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

---

## 4. Ảnh nhân vật trên Kling (tra cứu 2026-11-28, chưa test)

Kling MCP có bộ tool **Element** để lưu nhân vật rồi dùng lại qua nhiều cảnh, giúp giữ cùng một khuôn mặt. Tài khoản đang dùng gói VIP Standard. Mọi job tạo ảnh hoặc video đều tốn credit, nên phải chốt tham số trước khi chạy. Riêng tạo, sửa, xem element thì không phải là job tạo ảnh.

**Giới hạn khi tạo (chốt 2026-11-28):**
- **Ảnh:** độ phân giải **từ 2K trở xuống**. Không dùng 4K, 8K.
- **Video:** độ phân giải **từ 2K trở xuống**, tức chọn `720p` hoặc `1080p`, không dùng `4k`. Thời lượng **tối đa 5s**.
- Luôn truyền rõ `duration` và độ phân giải, đừng dựa vào mặc định. Ví dụ `kling-video-v4_0` mặc định `duration` 10s.
- Theo `who_am_i` (MCP 1.3.3), `kling-video-v2_5`, `v2_6` chỉ có 5s hoặc 10s, `kling-video-o1` ở `text_to_video` cũng vậy, nên với mấy lựa chọn này chỉ được chọn 5s.

### 4.1 Tool
| Tool | Việc |
|---|---|
| `element_create` | Tạo nhân vật từ ảnh có sẵn. Tool này **không tự vẽ** |
| `element_list` / `element_get` | Xem danh sách / chi tiết |
| `element_update` / `element_delete` | Sửa / xoá. Update ghi đè toàn bộ, nên phải `element_get` trước rồi gửi lại đủ trường |
| `file_upload` | Đưa ảnh trên máy lên Kling để lấy URL. Element chỉ nhận URL public |

Dùng được ở đâu:
- **Element kiểu ảnh:** `image_to_image` (kể cả kling-image-o1) và `image_to_video` với model nào có tham số `elements`.
- **Element kiểu video:** chỉ `image_to_video` với `kling-video-v3_0` / `v3_0_omni`.
- `text_to_image` và `text_to_video` **không dùng được element**.

### 4.2 Spec cứng
Hai nguồn lệch nhau thì lấy mức chặt hơn.
- PNG/JPG, ≤ 30MB, dưới 4K, mỗi cạnh ≥ 300px.
- Tỉ lệ khung **từ 1:2 tới 2:1**. Tool upload của MCP chặn ở 1:2, còn docs API của Kling cho tới 1:2.5.
- Kiểu ảnh: **1 ảnh cover + 1–3 ảnh phụ**, tổng 2–4 ảnh, không tạo được từ 1 ảnh.
  - **Cover không đổi được sau khi tạo**, muốn đổi phải xoá rồi tạo lại.
  - Ảnh phụ thì thay được, nhưng mỗi lần update là thay cả danh sách.
- Kiểu video: 1 clip 3–60s, fps > 23.8, cạnh ngắn ≥ 700px, ≤ 4K, không HDR.
- Phải có ít nhất 1 tag (`Characters / Animals / Items / Costumes / Scenes / Effects / Others`). Giọng `.mp3` thì không bắt buộc.

### 4.3 Cách làm ảnh tham chiếu
Phần này lấy từ guide, chủ yếu của bên thứ ba.
- **Cover chụp chính diện**, rõ mặt, đủ sáng, nhân vật nổi bật, nền trơn. Chỉ 1 người, không chữ, không watermark.
- **Ảnh phụ phải khác góc.** Gợi ý hay gặp là đủ 4 ảnh: chính diện, nghiêng, sau lưng, cận chi tiết. Chưa có tài liệu chính thức nào của Kling xác nhận con số 4.
- **Cả bộ chung một mặt, một dáng người.** Đúng nguyên tắc chân dung đã chốt: cố định mặt và dáng, còn tóc và quần áo đổi theo cảnh. Đồ trong ảnh tham chiếu dễ bị bê nguyên sang cảnh mới, nên để đồ đơn giản, trung tính, rồi tả trang phục trong prompt của từng cảnh.
- Thiếu góc thì vẽ bổ sung bằng model ảnh trước, rồi mới tạo element.
- Nên ghi thêm **mô tả bằng chữ** cho element.

### 4.4 Quy trình và cách dùng
1. Vẽ nhân vật bằng `text_to_image`. Bước này tốn credit. Có thể bật `story_mode` của kling-image-v4 để ra một bộ ảnh nhiều góc.
2. Chọn cover và ảnh phụ, `file_upload` nếu ảnh đang ở trên máy, rồi `element_create`.
3. **Gắn element vào job** `image_to_image` / `image_to_video`. Lỗi hay gặp nhất là tạo element xong mà quên gắn.
4. **Test 1 shot ngắn trước**, xem nhân vật ở vài góc, ổn rồi mới làm nhiều cảnh.

Khi viết prompt:
- Prompt từng cảnh **tả hành động, không tả lại ngoại hình**, vì ngoại hình đã nằm trong element. Câu mô tả nhân vật nếu có thì giữ y nguyên chữ giữa các lần chạy, viết lại kiểu khác là dễ trôi.
- Mặt bị trôi thì **sửa ảnh tham chiếu**, đừng cố chỉnh prompt.
- Image-to-video giữ nhân vật tốt hơn text-to-video. Kling 3.0 giữ mặt khá ổn nhưng vẫn có lúc trôi.

Nguồn: [Kling Element Library guide](https://kling.ai/quickstart/klingai-element-library-3-user-guide), [Kling character consistency](https://kling.ai/quickstart/ai-video-character-consistency), [Kling API – Elements](https://kling.ai/document-api/api/video/4-0/elements.md), [Magic Hour – Kling 3.0 guide](https://magichour.ai/blog/kling-30-reference-guide), [Atlas Cloud – Kling 3.0 consistency](https://www.atlascloud.ai/blog/guides/how-to-use-kling-3.0-for-character-consistency), [invideo – Kling Omni Elements](https://invideo.io/blog/kling-omni-elements/), và mô tả tool của Kling MCP 1.3.3.
