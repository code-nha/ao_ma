# Knowledge base cho nhan_vat: đề xuất tổ chức (bản nháp để Opus và Fable review)

## Ràng buộc từ người dùng
- Kho **mới, chỉ phục vụ nhan_vat**. Kho cũ của ebook_maker (thẻ sách, build.json, references/) để nguyên cho việc dịch sách,
  không gộp. Có thể chép dữ kiện từ đó sang nếu dùng được, nhưng kho mới tự đứng được.
- Kho dành cho **agent khai thác**, không phải người đọc: truy vấn hiệu quả và dễ cập nhật là quan trọng nhất.
- Nội dung đưa cho model là **tiếng Anh** (model nhỏ kém tiếng Việt).
- Chỉ dùng nguồn **không cần mua hay xin giấy phép**; mục đích nghiên cứu cá nhân, không thương mại.

## Ai dùng kho, dùng thế nào
| Người dùng | Việc | Giới hạn |
|---|---|---|
| Luân hồi (Gemma 4 26B, Ollama, máy dùng chung) | với mỗi ô LOOK, nhận menu giá trị đã lọc theo giới, tuổi; gạch giá trị không thể có; giữ sổ nét theo story | mỗi lần gọi nên ≤ ~3–4k token đầu vào |
| Nhân vật (cùng model) | chọn 2–4 nét nhận diện + tối đa 4 nét phụ từ danh sách ứng viên | như trên |
| Code | lọc cứng theo thẻ, trần dùng lại, kiểm luật, ghép prompt ảnh | không giới hạn |
| Sau này: đạo diễn | suy ra khả năng hành động từ LOOK (vác nổi không, chạy nhanh không) | |
| Agent chưng cất (Opus) | thêm, sửa, gộp giá trị khi có nguồn mới | |

Hiện có: `characters/kb/body.json` (471 giá trị, 18 ô thân, sinh bởi `kb/src/build_body.py`), `characters/LOOK_SLOTS.md`
(khung 40 ô), `experiments/luan_hoi.py` (luồng Luân hồi). Sắp thêm: ô mặt, tóc, dấu vết; nguồn mới (số liệu nhân trắc, bộ ảnh có
nhãn thuộc tính, phiếu nhận dạng kiểu Interpol DVI, danh mục nét phác họa, tài liệu y học lao động).

## Đề xuất của Claude (4 tầng)
1. `sources/`: danh mục nguồn (tên, loại, giấy phép, ngày lấy, nơi để file gốc; file gốc lớn để ngoài repo).
2. `cards/`: dữ kiện nhỏ đã chưng cất, mỗi thẻ có trích dẫn hoặc con số + nguồn; code kiểm được.
3. `catalog/`: kho nét theo ô; mỗi giá trị có id ổn định, cụm tiếng Anh, giới, tuổi, dân tộc, nguyên nhân, mức phổ biến (từ số
   liệu nếu có), danh sách thẻ căn cứ.
4. `views/`: dạng dựng ra bằng script cho từng người dùng (menu Luân hồi theo giới-tuổi…), không sửa tay.

Câu hỏi mở: định dạng lưu (JSONL, SQLite, nhiều file nhỏ), id ổn định khi gộp/tách giá trị, cách cập nhật từng phần khi thêm
nguồn, cách tính mức phổ biến khi có số liệu thật, cách giữ luật loại trừ giữa các giá trị, đặt kho ở đâu trong repo.
