# Đánh giá loop LOOK (Fable)

Phạm vi: chỉ đọc file, không chạy model, không render. Những chỗ ghi "chưa kiểm" là suy luận, cần thí nghiệm ở mục 6 xác nhận.

Đã đọc: `LOOP.md`, `SPEC.md`, `lao_bay/*`, `look_and_feel.md`; bên `ebook_maker/skills/character-portrait/`: `build/`, `lookup/`,
`character-portrait-prompt/`, `character-portrait-score/`, `evals/run4`, `evals/run5`.

## Tóm tắt

Ý chính giữ được: nhân vật tự tra, tự viết, tự xem, tự sửa, 5 lượt. Nhưng bản nháp có bốn chỗ sẽ hỏng nếu làm đúng như viết:

1. **Tự chấm sẽ dễ gật.** Cùng một model vừa viết prompt vừa xem ảnh, lại còn nhớ prompt mình viết, thì nó đọc prompt chứ không đọc ảnh.
2. **Bằng chứng hiện có không đo đúng thứ loop cần.** run4 đo "ảnh có lộ đúng tâm trạng/tính cách không" trên một khuôn mặt do code cho sẵn. LOOK lại là phần mặt và dáng cố định, đúng phần mà công thức N1 cấm model viết (luật 9). Chưa có số liệu nào cho việc Gemma tự viết mặt.
3. **KB chưa khớp với nhân vật Việt lao động.** Mục dáng theo tuổi nói ngược với Lão Bảy; mục nghề lao động chỉ có 1 cue.
4. **Mỗi lần sửa chữ là ra một người khác.** ArcFace run4: cùng seed, cùng nhân vật, chỉ đổi đoạn tả thì độ giống chỉ 0,40–0,44 (khác người hẳn là 0,20). Sửa tự do 5 vòng là 5 người.

Cả bốn đều sửa được mà không đổi ý người dùng. Bản loop sửa ở mục 5.

## 1. Loop có chạy như thiết kế không

### 1.1 Tự chấm
- Rủi ro lớn nhất. Model nhỏ chấm thang 1–10 thường dồn về 7–8, và model thấy prompt của chính nó thì có xu hướng xác nhận. Loop như viết nhiều khả năng dừng ở vòng 1 hoặc 2 với lời khen chung chung. Chưa kiểm, nhưng `look_and_feel.md` đã ghi cùng kiểu lỗi: chỉ số tự động làm Qwen trông tốt nhất trong khi đọc thì không ra người.
- Nhập vai khi chấm thêm nhiễu. Lão Bảy "không rành máy móc", "cười xòa với lỗi người khác"; chấm bằng giọng lão thì dễ ra "ừ, cũng được".
- Cách giữ ý người dùng mà giảm thiên vị: tách **nhìn** khỏi **phán**. Lượt nhìn không được thấy prompt và không được thấy hồ sơ, chỉ trả lời bảng câu hỏi cố định về ảnh. Lượt phán mới là nhân vật: đọc kết quả nhìn, so với danh sách của mình, quyết sửa gì.

### 1.2 Mắt của Gemma 4 26B (chưa kiểm)
Dự đoán theo mức tin cậy:
- Khá chắc: giới, nhóm tuổi thô (trẻ / trung niên / già), tóc bạc hay hói, gầy hay béo, da sáng hay sạm, tư thế khom hay thẳng.
- Trung bình: tuổi chính xác tới ±10 năm, dáng "đậm chắc" so với "gầy gân", nét mặt khi không biểu cảm.
- Yếu: phân biệt người Kinh miền Trung với Đông Á nói chung (người chấm cũng khó); dấu nhỏ như sẹo mờ, chai tay, đồi mồi, móng tay bẩn trong ảnh toàn thân (chỉ vài điểm ảnh sau khi model thu nhỏ ảnh); chiều cao tuyệt đối khi ảnh không có vật so.
- Hệ quả: tiêu chí nào mắt không thấy được thì không đưa vào điểm. Dấu nhỏ cần ảnh cận (mặt, bàn tay) mới chấm được. Dân tộc và chiều cao nên để code ghim vào prompt, không để vòng lặp tranh cãi.
- Phải đo trước khi tin: xem mục 6, bước A, không tốn lượt render nào.

### 1.3 Trôi nhân dạng giữa các vòng
- Số liệu sẵn có: `run4/arcface.md`, giữ người 0,403–0,444 khi chỉ đổi đoạn tả tâm trạng, cùng seed. Tức Qwen Image không giữ mặt qua thay đổi chữ.
- Trong loop, "sửa prompt" ở vòng 3 sẽ đổi cả những chỗ vòng 2 đã đúng. Điểm lên xuống thất thường, không hội tụ.
- Giảm: giữ seed cố định suốt loop; LOOK chia ô (slot), mỗi vòng chỉ được sửa tối đa 2 ô, các ô khác code giữ nguyên từng chữ. Vẫn sẽ trôi, nhưng ít hơn và biết trôi do ô nào.
- Một điều nên nói thẳng: LOOK bằng chữ không xác định một khuôn mặt. Sau loop, thứ giữ nhân dạng cho các cảnh sau là **ảnh được chọn** (làm ảnh tham chiếu), còn LOOK là mô tả đi kèm. Nếu chỉ lưu chữ, mỗi lần vẽ lại sẽ ra anh em họ.

### 1.4 Biết mình có 5 lượt
- Lợi: có cớ để dừng, tránh sửa mãi.
- Hại có thể gặp (chưa kiểm): model nhỏ không biết chia ngân sách; tới "lượt cuối" dễ chấp nhận cho xong; hoặc đem con số vào lời nhập vai.
- Đề nghị giữ ý người dùng nhưng đổi cách nói: không ghi "bạn có 5 lượt" một lần ở đầu, mà ghi ở cuối prompt mỗi vòng dạng ghi chú đạo diễn "Lượt 2/5. Bản tốt nhất đang là lượt 1." (cuối prompt là chỗ ảnh hưởng mạnh nhất, theo `look_and_feel.md` 1.3). Quyền dừng thuộc về code.
- Có nên nói hay không là một nhánh của thí nghiệm (mục 6, L2 so với L3).

### 1.5 Luật dừng và giữ bản nào
- Bản nháp ghi "đạt thì dừng" nhưng chưa định nghĩa "đạt"; ghi "giữ bản tốt nhất" nhưng không nói so bằng gì. Nếu so bằng điểm tự chấm từng vòng thì các điểm đó không cùng thước.
- Đề nghị: danh sách tiêu chí lập **một lần trước vòng 1** rồi khóa; mọi vòng chấm theo đúng danh sách đó. Bản tốt nhất = điểm cao nhất theo danh sách khóa, hòa thì lấy bản sớm hơn. Không bao giờ lấy "bản cuối" mặc định.
- Dừng khi: mọi tiêu chí cứng đạt và tiêu chí mềm đủ ngưỡng; hoặc 2 vòng liền không hơn bản tốt nhất; hoặc hết 5 lượt.

### 1.6 Lệch giữa LOOP và SPEC
- SPEC: LOOK là bảng cụm từ gồm cả bàn chân, dáng đi, sẹo ở chân. LOOP: LOOK là prompt ảnh. Một ảnh không chứa hết (dáng đi không vẽ được; mặt và bàn chân không cùng độ phân giải).
- `LOOK.gemma2.md` hiện là tiếng Việt, có chỗ không nhìn thấy trong ảnh đứng ("ngồi xổm", "dáng đi chậm") và vài chỗ tự mâu thuẫn nhẹ ("người nhỏ nhưng dày", "cánh tay nhỏ" với "thịt săn").
- Cách gộp: LOOK = bảng ô bằng cụm từ tiếng Anh do nhân vật viết; code ghép các ô thành 2 prompt (cận mặt, toàn thân). Nhân vật vẫn là người viết từng chữ tả mình, nên "prompt chính là LOOK" vẫn đúng. Ô không vẽ được (dáng đi) vẫn nằm trong LOOK nhưng đánh dấu "không chấm bằng ảnh".

## 2. Knowledge base và tra cứu

### 2.1 Cái gì đã sẵn
| Tài sản | Dùng được cho loop? |
|---|---|
| `lookup/lookup.py` + `lookup.json` (61 mục, 52 ok) | Có sẵn code, trả khối ≤ ~2,5k ký tự theo giới×tuổi, tâm trạng, tính cách. Nhưng phạm vi là **nét mặt và biểu cảm**, không phải cấu trúc mặt |
| `build/build.json` (51 mục, 40 ok) | Có bảng dáng; `run5/gen_build.py` đã có sẵn cách tra: model chọn họ từ menu (JSON có enum), code lấy cue trong 1.300 ký tự |
| `character-portrait-prompt/references/feature-*.md` | Có kiến thức từng bộ phận mặt, nhưng là file rời theo luật `[r…]`, chưa có khóa tra cho model nhỏ |
| `character-portrait-score/` | Có rubric 0–10 và references để chấm; viết cho model lớn, quá dài cho một lượt 3k token |
| `evals/run4/formula_n1.md` | 10 luật viết biểu cảm; luật 9 cấm tả cấu trúc mặt vì code đã tả. Không áp thẳng cho LOOK |

### 2.2 Chỗ hổng
- **Mặt cố định theo vùng miền.** Chỉ có `ethnicity/east-asian` 5 cue, kèm lời dặn "dùng nhiều nhất một, nhẹ tay". Không có gì cho người Việt, càng không có theo vùng, thời đại, mức sống.
- **Dáng chuẩn là dáng sách vẽ phương Tây.** `base/male-elderly` ghi "gầy yếu, cơ mềm", "bàn tay gầy gần như không mỡ", "mỡ cao, bụng nhô". Lão Bảy 70 tuổi còn đi biển thì bàn tay to chai, thân săn. Đưa cue này vào là kéo nhân vật về ông già trung bình.
- **Nghề và đời sống mỏng.** `life/manual-labour` 1 cue từ 1 sách (thin). Không có nắng gió biển, thiếu ăn thời nhỏ, răng, da. Mà đây chính là phần LIFE của nhân vật in lên người.
- **Chấn thương, sẹo, tật:** gần như trống (LOOP.md cũng đã ghi).
- Tức là với Lão Bảy, phần KB mạnh nhất (tuổi) lại sai hướng, phần cần nhất (nghề, vùng) lại yếu. Phần Gemma tự viết trong `LOOK.gemma2.md` (da sạm dày, tay chai, đồi mồi) đúng hơn cue trong bảng.

### 2.3 Về kết quả N2 kém hơn
- Tính lại từ `picks.jsonl` + `tasks.json`: N0 31/40, N1 32/40, N2 26/40; mỗi nhóm 10 bài, một người chấm. Chênh 6 cặp trên 40 chưa đủ chắc về thống kê, nhưng cùng chiều với ArcFace (N2 giữ người kém nhất, 0,403) và ghi chú của người chấm.
- Đáng chú ý hơn: **N0 ≈ N1**. Gemma 26B không cần công thức cũng đạt 78%. Kiến thức thêm vào chưa cho thấy lợi, có khi hại.
- run5 nhánh B2 (có cue) cần 4 lần sinh lại trên 16 prompt, B0 không lần nào: cue làm model viết lấn sang mặt, quần áo, đồ vật.
- Giải thích hợp lý: cue làm prompt dài và dồn nhiều dấu hiệu, Qwen Image vẽ đậm tất cả, ra cường điệu.
- Kết luận cho loop: **không tra trước rồi nhồi cue vào vòng 1**. Vòng 1 để nhân vật viết bằng hiểu biết của nó. KB chỉ dùng ở hai chỗ: (a) lập danh sách kiểm, (b) khi một ô bị chấm sai thì tra đúng ô đó, lấy 1–2 cue. Gọi là "tra khi hỏng".

### 2.4 Hình thức KB cho model nhỏ
- **Tra bằng khóa, không tìm tự do.** Model chọn id từ menu ngắn bằng JSON có enum (đúng cách `b2_block` và `family_menu()` đang làm). Tìm tự do trên 200k ký tự thì model nhỏ không làm nổi trong 3k token và sẽ bịa.
- Menu ≤ ~60 dòng, mỗi dòng id + vài bí danh Việt/Anh (~600–800 token). Chọn tối đa 3 id mỗi lần tra.
- Mỗi mục trả về: tối đa 2 cue + 1 "tell" + 1 "avoid"; cả khối ≤ 600 ký tự cho một ô. Mục `thin` thì ghi rõ là yếu hoặc không trả.
- Khóa nên theo **ô của LOOK** (mặt-da, mặt-khung, tay, thân, tư thế, dấu vết) × nguồn (tuổi, nghề, khí hậu, thiếu ăn, bệnh), để "ô tay bị sai" tra thẳng ra "tay + lao động". Hiện khóa đang theo họ tính cách/nhu cầu, hợp với biểu cảm hơn là với LOOK.
- Cue phải ghi kèm điều kiện áp dụng ("người già ít vận động", "người lao động tay chân lâu năm") để mục tuổi không đè mục nghề. Khi hai mục mâu thuẫn, thứ tự ưu tiên: LIFE/nghề > tuổi chuẩn.
- "Avoid" trong KB nên chuyển thành **kiểm sau khi viết** bằng code hoặc bằng lượt nhìn, vì dặn "đừng" trong prompt yếu với model nhỏ.

## 3. Chấm điểm

### 3.1 Danh sách kiểm, lập một lần
Trước vòng 1, nhân vật đọc IDENTITY + SOUL + LIFE và viết danh sách 8–12 mục "nhìn ảnh là phải thấy", mỗi mục là một câu hỏi mắt trả lời được. Code kiểm định dạng rồi khóa lại. Ví dụ cho Lão Bảy:

| Loại | Mục | Gốc |
|---|---|---|
| cứng | nam | IDENTITY |
| cứng | trông 65–75 tuổi | IDENTITY |
| cứng | người Đông Nam Á, da sạm nắng | IDENTITY (quê, nghề) |
| cứng | không béo, không yếu ớt; thân săn | LIFE (đi biển cả đời), SOUL (còn tự nuôi mình) |
| cứng | bàn tay to, thô | nghề vá lưới, kéo lưới |
| mềm | lưng hơi khom nhưng đứng vững | tuổi + nghề |
| mềm | mặt lúc nghỉ: trầm, hiền, không cau có | SOUL |
| mềm | không chải chuốt, không đẹp hóa | SPEC |
| mềm | "nhìn là thấy mình" | nhân vật tự cảm |

Mục "không ghi gì về cơ thể" trong IDENTITY vẫn giữ: danh sách này suy ra từ sự thật, không thêm sự thật mới.

### 3.2 Thang và ngưỡng
- Mỗi mục 0 / 1 / 2 (không / hơi / rõ). Không dùng thang 1–10 tổng.
- Đạt = mọi mục cứng ≥ 1 và không quá một mục cứng ở mức 1; trung bình mục mềm ≥ 1,3. Con số ngưỡng cần chỉnh sau thí nghiệm.
- So được giữa các vòng vì: danh sách khóa, bảng câu hỏi lượt nhìn cố định, seed cố định, cùng khung ảnh.

### 3.3 Lượt nhìn và lượt phán
- **Lượt nhìn** (trung tính, không nhập vai, không thấy prompt, không thấy hồ sơ): nhận ảnh, trả JSON theo bảng câu hỏi cố định: giới, tuổi ước lượng (một số), vóc (gầy/vừa/đậm/béo), cơ, da, tóc, tư thế, bàn tay, nét mặt, dấu vết thấy được, lỗi giải phẫu. Chạy riêng cho ảnh mặt và ảnh toàn thân.
- **Code** đổi câu trả lời thành điểm cho các mục cứng (tuổi ước lượng có nằm trong khoảng không, vóc có đúng nhóm không). Phần này không qua tay nhân vật.
- **Lượt phán** (nhân vật, có nhập vai): nhận ảnh + kết quả lượt nhìn + danh sách khóa, chấm các mục mềm, nói ô nào sai và muốn sửa ra sao. Đây là chỗ "nhân vật tự chấm" theo ý người dùng.

### 3.4 Có cần giám khảo ngoài không
- Trong vòng lặp sản xuất: không bắt buộc, lượt nhìn mù ở trên đã là một nửa giám khảo ngoài.
- Trong thí nghiệm: **bắt buộc**, nếu không thì không biết điểm tự chấm có nghĩa gì. Hai thước ngoài rẻ nhất:
  1. Ghép mù kiểu run4: người chấm nhận N ảnh cuối + N hồ sơ, ghép cặp. Đã có sẵn `viewer.py`, `make_csv.py`.
  2. Chọn mù giữa hai ảnh: ảnh vòng 1 và ảnh loop chọn, thứ tự ngẫu nhiên, hỏi "ảnh nào đúng người trong hồ sơ hơn". Đo thẳng câu hỏi "loop có làm ảnh tốt lên không".
- ArcFace dùng để đo trôi giữa các vòng và độ ổn định qua seed, không dùng để đo đúng sai.

## 4. Chi phí và vận hành

Số đo sẵn có: Gemma 26B trên wee ~2–3 giây một lượt chữ (run5, 300–1.000 token vào); Qwen Image ~18–21 giây một ảnh (run4, 120 ảnh). Lượt có ảnh của Gemma chưa đo, đoán 5–15 giây.

Một nhân vật, loop sửa ở mục 5:
| Việc | Số lượt | Thời gian ước |
|---|---|---|
| Lập danh sách kiểm, viết LOOK lượt 1 | 2 lượt chữ | ~6 s |
| Mỗi vòng: sửa ô (1), render mặt + toàn thân (2 ảnh), nhìn (2), phán (1), tra khi hỏng (0–1) | 4–5 lượt Gemma + 2 ảnh | ~1,5–2 phút |
| 5 vòng | ~22 lượt Gemma + 10 ảnh | ~8–10 phút |
| Kiểm ổn định bản chọn trên 2 seed khác | 4 ảnh + 4 lượt nhìn | ~2 phút |

Tổng khoảng 10–12 phút một nhân vật nếu hai máy rảnh. Rẻ. Chỗ vướng là điều phối chứ không phải thời gian:
- wee dùng chung: hỏi `wee_admin` trước, gửi tuần tự, không gửi `num_ctx`/`keep_alive`. Loop đan xen wee → senlab → wee nên mỗi vòng chờ cả hai máy; nên chạy theo lô (viết hết vòng 1 cho mọi nhân vật, rồi render cả lô, rồi nhìn cả lô) như run4/run5 đã làm.
- Cần xác nhận trước: endpoint Gemma trên wee có nhận ảnh không, nhận mấy ảnh một lượt, ảnh tốn bao nhiêu token so với trần ~3k. Nếu chỉ một ảnh một lượt thì so sánh A/B phải ghép hai ảnh thành một bằng code.
- Mỗi lượt phải ≤ ~3k token: file nhân vật của Lão Bảy (IDENTITY + SOUL + LIFE) đã ~1k token; cộng STYLE gemma2 (~1,5k) là sát trần. Lượt viết LOOK không cần STYLE đầy đủ, chỉ cần mục "Vẻ" và "Cử".
- Ghi log JSONL từng vòng (ô, prompt, seed, ảnh, kết quả nhìn, điểm, quyết định) theo định dạng viewer đọc được.

## 5. Loop sửa lại

Giữ: nhân vật tự tra, tự viết, tự xem, tự chấm, tự sửa; tối đa 5 lượt; nhân vật biết đang ở lượt mấy.

**Bước 0 – Lập danh sách (1 lượt chữ, nhân vật).**
Vào: IDENTITY, SOUL, LIFE, mục Vẻ + Cử của STYLE. Ra: JSON 8–12 mục kiểm (cứng/mềm, gốc). Code kiểm và khóa.

**Bước 1 – Viết LOOK lượt 1 (1 lượt chữ, nhân vật, chưa tra KB).**
Vào: hồ sơ như trên + khuôn ô. Ra: JSON các ô tiếng Anh, mỗi ô ≤ 20 từ: `stature, face_shape, eyes_brows, nose_mouth, face_skin_age, resting_expression, hair, torso, arms_hands, legs_feet, posture, marks, gait (không vẽ)`.
Code kiểm sau khi viết (kiểu `check()` của run5): độ dài, không quần áo, không đồ vật, không số tuổi, không từ đẹp hóa; sai thì sinh lại tối đa 2 lần.
Code ghim sẵn: giới, nhóm tuổi, "Vietnamese", khung ảnh, ánh sáng, quần áo trung tính, seed.

**Bước 2 – Vẽ (2 ảnh).** Code ghép ô thành prompt cận mặt và prompt toàn thân. Cùng seed mọi vòng.

**Bước 3 – Nhìn (2 lượt có ảnh, trung tính, mù).** Vào: một ảnh + bảng câu hỏi. Ra: JSON quan sát. Code tính điểm mục cứng.

**Bước 4 – Phán (1 lượt có ảnh, nhân vật).**
Vào: hồ sơ rút gọn, danh sách khóa, kết quả nhìn, điểm mục cứng, ảnh; cuối prompt là ghi chú "Lượt k/5. Bản tốt nhất: lượt j, điểm x."
Ra: JSON điểm mục mềm, tối đa 2 ô muốn sửa kèm lý do một câu.

**Bước 5 – Code quyết.**
- Tính tổng điểm, cập nhật bản tốt nhất.
- Dừng nếu đạt (3.2), hoặc 2 vòng liền không hơn bản tốt nhất, hoặc k = 5.
- Nếu bản mới kém bản tốt nhất: vòng sau sửa **từ bản tốt nhất**, không từ bản vừa hỏng.

**Bước 6 – Tra khi hỏng + sửa (1–2 lượt chữ, nhân vật).**
Với mỗi ô bị chọn sửa: nhân vật chọn tối đa 2 khóa từ menu KB (JSON enum), code trả ≤ 2 cue + 1 avoid mỗi khóa. Nhân vật viết lại **chỉ ô đó**; code giữ nguyên các ô khác. Quay lại bước 2.

**Kết thúc.** Vẽ bản tốt nhất thêm 2 seed, chạy lượt nhìn. Nếu mục cứng rớt ở seed khác thì đánh dấu LOOK "chưa vững" để người viết truyện xem. Lưu: LOOK (các ô), ảnh được chọn làm ảnh tham chiếu, log.

## 6. Thí nghiệm nhỏ

**A. Đo mắt Gemma trước (không render, ~1 giờ).**
Dùng 120 ảnh sẵn có của run4 (biết giới, tuổi, nhân vật gốc):
- Cho Gemma ước tuổi, giới, vóc từng ảnh; so với hồ sơ gốc. Đo sai số tuổi và độ lặp lại (hỏi 2 lần cùng ảnh).
- Cho Gemma làm đúng 30 bài ghép của `tasks.json`; so với người (N0 78%, N1 80%, N2 65%; đoán mò 25%).
- Nếu Gemma ước tuổi lệch > 10 năm thường xuyên hoặc ghép < ~50%, thì không dùng Gemma làm mắt; đổi sang model nhìn khác hoặc để người chấm, và dừng ở đây.

**B. Bổ sung KB tối thiểu** trước khi so nhánh có tra: thêm vài mục nghề/khí hậu (lao động ngoài trời, biển, thiếu ăn thời nhỏ), ghi điều kiện áp dụng cho `base/*-elderly`.

**C. So bốn nhánh, 6 nhân vật.**
Nhân vật: Lão Bảy cùng 4 gốc run4 (cô Hiền, bé Na, Minh, Lan) và thêm 1 người khó (có dáng trái với tuổi chuẩn hoặc có dấu vết rõ). Cần viết đủ IDENTITY/SOUL/LIFE cho 5 người kia.

| Nhánh | Nội dung |
|---|---|
| L0 | viết một lần, không loop (mốc) |
| L1 | loop đúng như `LOOP.md`: tra trước, tự chấm tự do, sửa tự do, 5 lượt |
| L2 | loop sửa mục 5, tra khi hỏng |
| L3 | như L2 nhưng không cho biết số lượt (chỉ đo tác dụng của "biết 5 lượt") |

Mỗi nhánh × 6 nhân vật × 1 seed chính: tối đa 6 × (1 + 5 + 5 + 5) × 2 ≈ 190 ảnh, khoảng 1 giờ render, cộng ~400 lượt Gemma.

**Đo:**
1. Người chấm mù, từng nhân vật: xếp hạng 4 ảnh cuối (L0–L3) theo "đúng người trong hồ sơ". Thước chính.
2. Người chấm mù: ảnh vòng 1 so với ảnh loop chọn, ảnh nào đúng hơn. Tỉ lệ loop thắng > 50% rõ rệt mới đáng chạy loop.
3. Ghép mù 6 ảnh với 6 hồ sơ cho mỗi nhánh (kiểu run4).
4. Điểm tự chấm có đi cùng xếp hạng của người không (tương quan thứ hạng theo từng nhân vật). Thấp thì tự chấm vô dụng.
5. Tỉ lệ nhân vật "đạt" ngay vòng 1 ở L1 so với L2 (đo mức dễ gật).
6. ArcFace giữa các vòng liền nhau (đo trôi), và giữa 3 seed của bản chọn (đo vững).
7. Số vòng dùng, số lần chọn bản không phải bản cuối, L2 so với L3 ở vòng dừng và điểm.

6 nhân vật chỉ đủ thấy chênh lớn. Nếu L2 và L0 sát nhau thì kết luận trung thực là "chưa thấy loop có lợi", không phải "loop tốt hơn một chút".

## Kết luận

Ý tưởng đáng làm và rẻ (khoảng 10 phút một nhân vật), nhưng bản nháp hiện tại chưa nên chạy nguyên dạng. Nó dựa vào hai thứ chưa được kiểm: mắt của Gemma và độ trung thực của tự chấm; và dùng KB theo đúng cách đã cho kết quả xấu ở run4 N2, với các mục dáng đang nói ngược nhân vật mẫu. Sửa ba chỗ là đủ để thử nghiêm túc: tách lượt nhìn mù khỏi lượt nhân vật phán theo danh sách khóa từ trước; LOOK chia ô, seed cố định, mỗi vòng sửa tối đa 2 ô và luôn giữ bản tốt nhất; KB chỉ tra khi một ô bị chấm sai. Trước tất cả, chạy bước A trên 120 ảnh run4 có sẵn: nếu Gemma không nhìn ra tuổi và vóc thì cả loop không có nền.
