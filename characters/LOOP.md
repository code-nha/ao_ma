# Loop LOOK: nhân vật tự tra cứu, tự prompt, tự chấm (bản nháp để đánh giá)

Ý của người dùng: LOOK chính là prompt tạo ảnh do nhân vật tự viết. Nhân vật tra cứu một knowledge base chưng cất từ gói sách,
tự viết prompt, xem ảnh, tự chấm theo IDENTITY và SOUL, rồi sửa. Tối đa 5 vòng mỗi nhân vật, và nhân vật biết giới hạn này.

## Thành phần
- **Knowledge base (KB):** chưng cất từ các gói sách (`H:/My Drive/book_packages`, trên Google Drive). Hiện đã có (repo
  `C:\Users\khoa\code_nha\ebook_maker`, thư mục `skills/character-portrait/`):
  - `build/build.json`: bảng dáng người (`base/<giới>-<tuổi>`, `build/*`, `life/*`, `means/*`, `need/*`, `trait/*`), mỗi mục có
    cues, reads_as, tells, pitfalls, trạng thái ok/thin; `build/coverage.md`;
  - `character-portrait-prompt/references/`: tra cứu mặt theo tuổi, cảm xúc, tính cách, từng bộ phận mặt; `lookup/` là code tra;
  - `evals/run4/formula_n1.md`: công thức mặt N1 (dáng chuẩn theo giới-tuổi + 10 luật).
- **Nhân vật:** Gemma 4 26B (Ollama, máy dùng chung) nhập vai, đọc IDENTITY, SOUL, LIFE, STYLE của mình (`characters/<id>/`,
  đặc tả `characters/SPEC.md`).
- **Máy vẽ:** Qwen Image 2.1 trên ComfyUI (máy senlab), ~1 ảnh / vài chục giây đến vài phút.
- **Mắt:** chính nhân vật (Gemma 4 có nhìn ảnh) xem ảnh và chấm.

## Các bước
1. Nhân vật đọc file của mình, biết mình có **5 lượt** vẽ.
2. Nhân vật tra KB (chọn mục, đọc cues) cho mặt và dáng.
3. Nhân vật viết LOOK = prompt tạo ảnh tiếng Anh (chỉ ngoại hình nhìn thấy được: mặt, tóc tự nhiên, dáng, dấu vết; khung ảnh,
   ánh sáng, quần áo trung tính do code thêm).
4. Vẽ ảnh.
5. Nhân vật xem ảnh, chấm điểm theo IDENTITY và SOUL ("đây có phải là mình không?"), ghi chỗ sai và định sửa gì.
6. Nếu đạt hoặc hết 5 lượt thì dừng, giữ bản tốt nhất làm LOOK; chưa đạt thì sửa prompt, quay lại bước 2 hoặc 3.

## Đã biết từ thí nghiệm trước
- run4 (mặt, ghép ảnh với hồ sơ, người chấm): N1 80% đúng, N0 (không công thức) 78%, N2 (thêm cue tra cứu) 65%; N2 làm nét mặt
  bị cường điệu và mất vẻ kín đáo. Đoán mò là 25%.
- run5 (dáng toàn thân, có/không bảng dáng) đã có prompt, chưa render.
- Gemma tự viết STYLE/LOOK (lao_bay/*.gemma2.md): LOOK dạng cụm từ, nhìn thấy được thì ổn; xưng hô trong STYLE rối.
- Bảng dáng mạnh ở mục theo tuổi, yếu ở nghề lao động, chấn thương, can thiệp.
