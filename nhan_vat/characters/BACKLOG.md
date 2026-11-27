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
- Đã quyết (2026-11-25): SOUL chỉ giải thích nét mặt khi nghỉ, dáng đứng, dáng đi; nếp nhăn do thói quen biểu cảm không dẫn SOUL.
- Đã quyết (2026-11-25): người từng niềng răng được chọn `teeth.veneers` (bọc sứ) thì cứ để, hơi vô lý nhưng thú vị; không thêm giá trị riêng.
- Nhánh "hết lượt kiểm mà còn mâu thuẫn thì đưa ô về nét nền" đã chạy thử (2026-11-25, t_lan, bước kiểm giả lập luôn báo
  mâu thuẫn): bỏ đúng ô phụ chọn sau cùng, mâu thuẫn thứ hai dùng chung ô đó được coi là đã giải. Chưa gặp trong lần chạy thật.
- Luân hồi kiểm mâu thuẫn đôi khi trả lời lan man rồi tự rút lại; code bỏ qua câu dài hơn 300 ký tự nhưng vẫn ghi vào
  `rule_candidates.jsonl`.
- Nhân vật thử `t_lan`, `t_lao_bay_twin` và các story `acc*` là dữ liệu nghiệm thu, chưa commit.

## Vòng ảnh tự chấm (`experiments/look_loop.py`, ghi 2026-11-25)
Lão Bảy chạy 3 lần (30 ảnh): cơ chế chạy đúng (chọn lại ô, nhấn mạnh, nhân vật nói "yes" thì chốt). Còn yếu:
mắt Gemma và nhân vật chấm quá dễ (LOOK "thấp đậm, cơ rắn chắc" mà ảnh vẽ ông già gầy vẫn được điểm cao và "yes"); câu nhấn
"strongly visible" quá tay (môi tím như son). Cổng dân tộc đã bỏ: model không phân được.

Task:
1. Thử `gemma4:31b` (có trên wee, nhìn được ảnh) làm mắt và nhân vật, so với `gemma4:26b`. Báo wee_admin trước vì đổi model
   làm wee nạp lại.
2. Đổi cách hỏi trước: mắt tả ảnh mà không thấy checklist (dáng, tay, môi, da...), rồi một lời gọi text so lời tả với LOOK.
   Lý do: đọc sẵn câu "short stocky frame" rồi hỏi "có thấy không" thì dễ gật.
Thử trên 30 ảnh đã có (`experiments/look_loop/lao_bay/`), không cần senlab: Claude gắn đáp án các ô dễ thấy làm chuẩn so.
Kết quả (2026-11-25, `experiments/eval_eye.py`, 10 ảnh x 8 ô; 2 ô đáp án "không": thân đậm, cơ rắn chắc). Đáp án do Claude
gắn bằng mắt, một đáp án chung cho cả 10 ảnh; ô `arms` đáng bàn. Giây = trung bình mỗi ảnh tính từ log.
| | bắt "không" | đúng "có" | giây/ảnh |
|---|---|---|---|
| 26b checklist (cách cũ) | 2/20 (18 trượt phần lớn là "not visible") | 60/60 | ~3 |
| 26b tả mù rồi so, trước sửa | 20/20 | 42/60 | ~4 |
| 26b tả mù rồi so, sau sửa lời gọi so | 20/20 | 55/60 (5 trượt đều là `arms`) | ~4 |
| 31b checklist (trước sửa) | 11/20 | 59/60 | ~35 |
| 31b tả mù rồi so (trước sửa) | 20/20 | 49/60 | ~40 |
Sửa lời gọi so: người tả nói "none" khi thấy được mà không có nét; thang yes/partly/no kèm ví dụ. Cảnh báo: ví dụ trong lời gọi so
lấy từ chính các ô đang chấm (forearms, stocky) và chỉ thử trên 10 ảnh một nhân vật: số 55/60 là trong mẫu, chưa kiểm ngoài mẫu.
Mắt tả mù đã vào look_loop (giữ 26b).

Các lần chạy hôm 2026-11-26 (thư mục `experiments/look_loop/lao_bay/<ts>/`; Fable kiểm lại số liệu, xem `TONG_KET_20261125-26.md`):
- `20261126_204828` (từ LOOK gốc): 0.61-0.76, không "yes". Lỗi: chọn lại `frame` "thấp đậm" (đang có) bị loại khỏi menu nên
  thành "xương xẩu góc cạnh"; câu ghi chú "trông héo" cũng góp phần.
- `20261126_205635`: chọn lại trùng giá trị cũ -> nhấn mạnh chạy đúng 3 lần. Lỗi: câu "Why: trông yếu" bị hiểu là tả bản thân,
  cơ thành `muscle.normal-m`, kéo theo thêm `fat.normal-m` và `arms` đổi. 0.60-0.76, không "yes".
- `body_test_20261126_211318` (6 ảnh): tả thân bằng hình dáng cụ thể thì `frame` "yes" 6/6; nhưng `fat` "no" 4/6 (bụng ở v1, v2),
  `arms` "no" 3/6, `muscle` chưa lần nào "yes" trọn. Cả 3 biến thể đều có "solid heavy torso", nên chưa chứng minh cụm đó gây
  bụng. `paint` đang dùng là ghép từ v1 và v3, chưa render đúng tổ hợp đó trước khi đưa vào kho.
- `20261126_211737` (có `paint`): 0.67, 0.74, 0.79, 0.69, 0.70; không "yes". Vòng 3 (almost, 0.79) mắt chấm `frame` "no" cả
  hai ảnh ("average width, lean"): điểm cao là nhờ cơ và tay, thân chỉ trung bình. Vòng 3 chỉ xin chọn lại `face_shape` (giữ
  nguyên mặt đang có, là nét nền) nhưng nét nền không có trong menu nên thành "deflated face"; Luân hồi kiểm báo
  mâu thuẫn muscle/arms (hai ô không đụng tới) rồi chọn lại cả hai thành `muscle.old-strong-m` và `arms.forearms-m` (không gầy hơn;
  vòng 4 mắt còn chấm `frame` "yes"). Vòng 4-5 có 6 nét nổi bật, quá giới hạn 5, không bị chặn.
- `20261126_212733` (từ LOOK gốc): frame/muscle/arms giữ nguyên 5 vòng; Luân hồi kiểm không báo mâu thuẫn nào nên nhánh lọc
  mâu thuẫn chưa được chạy tới. Vòng 2 lại xin giữ mặt cũ (nét nền) và lại bị đẩy sang "deflated"; sau đó ông xin mặt hóp mà Qwen
  vẫn vẽ mặt đầy. Vậy chuyện "đổi ý qua lại ở mặt" lần đầu là do menu ép, không phải nhân vật. 0.61-0.76, không "yes".
Trạng thái: LOOK.kb.json và sổ acc5 được chép tay về bản vòng 3 của `20261126_211737`; các nét đã chọn giống hệt commit
13988df, chỉ khác `paint`, `kb_version`, khối `render` và ý `mouth`. Chưa lần nào với mắt mới đạt "yes". Bản LOOK gốc = HEAD; bản
"yes" hôm 25 = `20261125_213116/r5_LOOK.kb.json`.

Đã sửa sau khi Fable kiểm (2026-11-26, chỉ kiểm khô, chưa chạy thật):
- chọn lại: giá trị đang có (cả nét nền) được đặt đầu menu (`role_menu(include=)`); kiểm khô `face_shape` thấy đúng;
- luan_hoi không gửi `options` (temperature, num_predict) lên wee nữa (có từ trước, trái quy tắc wee);
- hết lượt sửa mà quá 5 nét nổi bật: bỏ các nét nổi bật mới chọn; `remaining_errors` đếm cả lỗi này;
- lượt kiểm cuối khi --redo chỉ bỏ ô đang chọn lại, không bỏ ô khóa;
- look_loop: không có "yes" thì "almost" thắng "no" khi chọn bản.
Chạy thật kiểm sửa (2026-11-26, `20261126_214750`, từ LOOK của HEAD, 10 ảnh): 0.74, 0.68, 0.79, 0.74, 0.71; cả 5 vòng "almost",
không "yes". Vòng 1-4 ông chỉ xin nhấn mạnh (môi, nếp nhăn, răng, thân, da), vòng 5 mới xin chọn lại `face_shape` nhưng vòng cuối
không chạy chọn lại: các sửa trong luan_hoi không được chạy tới. Luật chọn bản mới chạy: chọn vòng 3 (almost, 0.79; mắt chấm
`frame` "no" cả hai ảnh, muscle/arms "yes"). LOOK.kb.json = bản đó (picks giống HEAD, thêm khối `render`).
Kiểm riêng (gọi `luan_hoi --redo` thật trên wee, không render, đúng yêu cầu vòng 5, rồi trả LOOK và sổ về như trước):
- không gửi options: lời gọi chạy bình thường;
- Luân hồi kiểm lại báo nhầm muscle/arms (hai ô khóa): lần này bị lọc bỏ, không chọn lại ô nào khác; `rule_candidates.jsonl`
  ghi `acted: false`;
- `face_shape`: nét nền có trên menu nhưng model chọn `face_shape.rect-m` "broad rectangular face" theo câu ghi chú ("sturdier"),
  không theo chữ "want". Hợp ý ông nhưng cho thấy câu ghi chú vẫn nặng hơn "want".
Chưa được chạy tới: chặn quá 5 nét nổi bật, lượt kiểm cuối chỉ bỏ ô đang chọn lại.
Tác dụng phụ đã có: `rule_candidates.jsonl` thêm 3 dòng (2 là mâu thuẫn báo nhầm, ghi `acted: true`); kb.json và report.md
dựng lại; senlab có ảnh trong `output/nhan_vat/` (mỗi render lưu một bản).
Thử bước "chọn bản cuối" offline (2026-11-26, `experiments/choose_test.py`, đếm bằng `choose_test_report.py`, log
`experiments/logs/choose_test.jsonl`; ý của user, thiết kế do Fable đề xuất): nhân vật xem 2 bản (4 ảnh một lời gọi, không thấy
điểm), chọn A / B / neither. 110 lời gọi gemma4:26b, dừng trước phần "không lời tả":
- mọi cặp vòng trong 5 lần chạy, cả 2 thứ tự (100 lời gọi): chọn vị trí A 86%; chỉ 14/50 cặp chọn cùng một bản khi đảo thứ tự;
- cùng một vòng làm cả A và B: 5/5 chọn A, kèm lý do bịa ("ánh mắt ở bản A...");
- bản "yes" hôm 25 so với vòng bị chê "no": 4/4 chọn A, tức chọn cả bản bị chê khi nó đứng trước, lý do đổi theo ("môi tôi không tím").
Kết luận: với cách hỏi này 26b không có ý thích ổn định giữa 2 bản, chỉ chọn bản đứng trước. Không đưa vào look_loop. Nếu thử lại:
chấm từng bản riêng (mỗi lời gọi một bản, hỏi "đây có phải mình không" theo thang), hoặc 2 ảnh ghép một khung; đo lại thiên vị vị trí trước.
`still_missing` hay gặp nhất: muscle 34, arms 17, mouth 12, face_shape 12.
Thử chấm từng bản (2026-11-27, `experiments/choose_rate.py`, `--report`; log `experiments/logs/choose_rate.jsonl`): mỗi lời gọi
một bản (2 ảnh), chỉ ảnh và hồ sơ, chấm 1-10; 25 vòng + bản "yes" hôm 25, mỗi bản 2 lần (52 lời gọi):
- điểm dồn về 7 (31/52; 4 đến 9); chấm lại cùng bản: 11/26 trùng, lệch trung bình 0.73 điểm, 4 bản lệch từ 2;
- trong một lần chạy các vòng chỉ cách nhau 6-8 (ngang nhiễu); bản "yes" hôm 25 được 6.5, không cao hơn hai vòng bị chê "no"
  (7.5, 6.5); tương quan với điểm mắt -0.16;
- chỉ bắt được bản lệch hẳn: `20261126_214750` vòng 4 được 4 cả hai lần ("trông giống người Đông Nam Á/Polynesia hơn người Kinh").
Kết luận: 26b không phân biệt được các vòng gần nhau, cả khi so cặp lẫn khi chấm riêng. Giữ luật chọn của code.
Đã sửa look_loop (2026-11-27, chỉ kiểm khô, chưa chạy thật): SYS_ME báo luật chọn bản cuối từ vòng 1; vòng cuối báo "không vẽ
nữa", `changes` maxItems 0, nếu model vẫn trả thì ghi vào `changes_ignored`, không áp; `stop` vòng cuối ghi "last round".
Còn lại: `paint` cho mặt hóp và thử với thân đậm; `paint` cho các nét khác Qwen vẽ yếu; kiểm mắt tả mù ngoài mẫu (nhân vật khác,
ví dụ trong lời gọi so không lấy từ ô đang chấm); thử tả mù cho vai nhân vật; docstring đầu look_loop.py còn tả luật chọn bản cũ.

## Khác
- Kho nét nhóm mặt, tóc, dấu vết chưa dựng.
- Luật loại trừ giữa các giá trị trong kho (hiện tạm dùng Luân hồi kiểm mâu thuẫn sau khi chọn).
- STYLE: xưng hô còn rối, cần bước kiểm tra sau khi sinh.
- run5 (dáng toàn thân) chưa render.
