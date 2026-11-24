# Backlog: nhân vật và ngoại hình

## Kho nét cần nguồn ngoài sách (ghi 2026-11-24)
Kho nét chỉ lấy từ gói sách không đủ. Sách là sách phương Tây cho họa sĩ, nhà điêu khắc, bác sĩ thẩm mỹ, thợ ảnh: thiếu thân người
lao động, người Việt và châu Á, tần suất thật ngoài đời. Kho nét nhóm thân (`kb/body.json`) có 34% giá trị là kiến thức chung, riêng
ô móng 0% từ sách, bàn chân 15%.

Cần tìm nguồn khác, ví dụ:
- số liệu nhân trắc người Việt và châu Á (chiều cao, cân nặng, BMI theo tuổi và vùng; khảo sát y tế, dinh dưỡng);
- tài liệu y khoa và nghề nghiệp về dấu vết lao động (ngư dân, nông dân, bốc vác, thợ…), bệnh thường gặp, lão hóa;
- bộ dữ liệu ảnh có nhãn thuộc tính khuôn mặt và cơ thể (để lấy danh mục nét và tần suất);
- ảnh tư liệu, phóng sự về người Việt các nghề, các vùng.

Việc cần làm: chọn nguồn, xin phép tải nếu cần, chưng cất vào kho nét với nguồn ghi rõ, thay dần các giá trị `general`.

## Còn lại sau đợt nghiệm thu tầng chọn nét (2026-11-25)
- SOUL hiện chỉ được giải thích nét mặt khi nghỉ, dáng đứng, dáng đi. Nếp nhăn do thói quen biểu cảm (cau mày) có nên dẫn SOUL
  không: chờ người dùng quyết.
- `teeth.veneers` (bọc sứ) bị chọn cho người từng niềng răng: cần giá trị "răng đều sau niềng" riêng.
- Nhánh "hết lượt kiểm mà còn mâu thuẫn thì đưa ô về nét nền" đã có code nhưng chưa gặp trong lần chạy thật nào.
- Luân hồi kiểm mâu thuẫn đôi khi trả lời lan man rồi tự rút lại; code bỏ qua câu dài hơn 300 ký tự nhưng vẫn ghi vào
  `rule_candidates.jsonl`.
- Nhân vật thử `t_lan`, `t_lao_bay_twin` và các story `acc*` là dữ liệu nghiệm thu, chưa commit.

## Khác
- Kho nét nhóm mặt, tóc, dấu vết chưa dựng.
- Luật loại trừ giữa các giá trị trong kho (hiện tạm dùng Luân hồi kiểm mâu thuẫn sau khi chọn).
- STYLE: xưng hô còn rối, cần bước kiểm tra sau khi sinh.
- run5 (dáng toàn thân) chưa render.
