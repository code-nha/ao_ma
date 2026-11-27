# Nguồn đã tải (shortlist 1–10)

Ngày tải: 2026-11-24. Thư mục gốc: `C:\Users\khoa\data\nhan_vat_sources\` (ngoài repo).
Danh mục từng file (URL nguồn, đường dẫn, dung lượng, sha256, ngày, dòng license): `C:\Users\khoa\data\nhan_vat_sources\manifest.jsonl`.
Tất cả đều tải thẳng, không đăng nhập, không điền form, không email ai. Không mở/chạy file nào đã tải (chỉ kiểm định dạng, giải nén zip có CSV).

**Tổng: 10/10 nguồn có dữ liệu, 704 file, ~760 MB** (gồm cả CSV đã giải nén từ zip). Lỗi chặn hoàn toàn: không có. Bỏ một phần: xem mục "Bỏ qua".

## Bảng tổng hợp

| # | Thư mục | Đã tải | Dung lượng | Ghi chú / license |
|---|---|---|---|---|
| 1 | `01_ncdrisc` | Chiều cao người lớn theo năm sinh (eLife 2016, CSV 2,4 MB, có 202 dòng Viet Nam); chiều cao trẻ 5–19 tuổi theo nước (Lancet 2020, zip → CSV 15,9 MB); BMI người lớn theo tuổi × nước, nam và nữ (Nature 2026, 2 zip → 2 CSV ~70 MB mỗi file); BMI chuẩn hoá tuổi theo nước (Nature 2026, CSV 9,2 MB) | 8 file, 233,5 MB | Không có license; chỉ "© Copyright 2026 NCD Risk Factor Collaboration. All Rights Reserved." Giữ nguyên file toàn cầu, chưa lọc VN/ĐNÁ. Zip đã giải nén vào thư mục con cùng tên. |
| 2 | `02_who_steps_vn` | Báo cáo STEPS VN 2021 (PDF 4,0 MB, từ IRIS WHO); báo cáo STEPS VN 2015 (PDF 1,4 MB, từ cdn.who.int) | 2 file, 5,4 MB | 2021: CC BY-NC-SA 3.0 IGO. 2015: không thấy dòng license; nội dung bên trong chưa mở kiểm (máy không có thư viện đọc PDF), chỉ biết là PDF hợp lệ. Không tải microdata. |
| 3 | `03_kinh_face_papers` | Bài TCNCYH 2023 (nhân trắc đầu mặt 7.376 người Kinh, PDF 8 trang); bài Tạp chí Y học VN về dạng mặt Bình Dương (PDF 4 trang) | 2 file, 0,5 MB | Không ghi license. Bài 2 lấy từ bản đăng lại trên vnras.com vì link gốc tapchiyhocvietnam.vn trả 404. |
| 4 | `04_interpol_dvi` | Mẫu AM 2023 (flat, PDF 3,2 MB); bộ mẫu PM (PDF 17 trang, 5,5 MB) | 2 file, 8,7 MB | Không thấy license; mẫu công khai. Link PM bản `/en/` trả 403, bản không có `/en/` tải được. |
| 5 | `05_tt22_2014_bca` | Trang thuvienphapluat: Mẫu 30aQĐ (truy nã giai đoạn điều tra) và 30bQĐ (giai đoạn truy tố, xét xử), có mục "Đặc điểm nhân dạng"; toàn văn TT 22/2014 trên thuviennhadat.vn (HTML) | 3 file, 0,7 MB | Văn bản pháp luật công khai; site đăng lại là tư nhân. Lưu HTML. |
| 6 | `06_nih_elements_morphology` | Trang chủ, trang tài liệu tham khảo, 6 trang mục lục vùng và 400 trang định nghĩa thuật ngữ (HTML), chia theo 6 thư mục: 1_head_face, 2_periorbital, 3_ear, 4_nose_philtrum, 5_lips_mouth, 6_hands_feet | 408 file, 7,9 MB | Trang chỉ ghi "Published 2009 Wiley-Liss, Inc."; không có license rõ. Chỉ lưu HTML, không tải ảnh minh hoạ. |
| 7 | `07_aist_1991-92` | Trang giới thiệu + trang danh mục 254 kích thước; sổ tay đo (PDF 91-92_anthrop_manual.pdf); 254 bảng thống kê (mỗi kích thước một ảnh GIF: bách phân vị, trung bình, SD, N cho trẻ/già × nam/nữ) | 257 file, 9,1 MB | "使用申請、同意書の提出などは必要ありません" (thống kê không cần xin); chân trang: "No reproduction or republication without written permission". **Bảng thống kê chỉ có dạng ảnh GIF** (file .lzh trên trang cũng chỉ chứa đúng ảnh này) → muốn dùng số phải OCR/chép tay. |
| 8 | `08_ansur2` | ANSUR_II_MALE_Public.csv (4.082 người), ANSUR_II_FEMALE_Public.csv (1.986 người), Measurer's Handbook (TR11-017, 263 trang), Memorandum for Record giải thích biến (MFR, 8 trang) | 4 file, 8,4 MB | Trang PSU không ghi license riêng; nguồn quân đội ghi "cleared for UNLIMITED PUBLIC RELEASE". Không tải báo cáo tóm tắt 444 trang (TR15-007, 7,3 MB) vì ngoài phạm vi; có thể tải sau nếu cần. |
| 9 | `09_ncic_smt_namus` | Bảng mã SMT đủ 939 mã (10 file JSON từ API ecfr.io, phân trang 100) + trang HTML SMT + danh mục các bộ mã; thêm bộ mã EYE, HAIR, SKIN (nhỏ, cùng nhóm mô tả người); NamUs user guide nhập hồ sơ mất tích (PDF 3,9 MB) | 16 file, 4,3 MB | ecfr.io là công cụ độc lập, không chính thức (NIEM 5.2, 12/2022); mã NCIC là tài liệu chính phủ Mỹ công khai. |
| 10 | `10_maad_face` | MAAD_Face.csv (481 MB, 47 thuộc tính, chỉ nhãn) + README | 2 file, 481,2 MB | CC BY-SA 4.0 (theo README). Ổ C: còn 378 GB trước khi tải → đạt điều kiện ≥ 20 GB. **Không tải** file .pkl (717 MB) theo quy tắc ưu tiên CSV, không dùng pickle. Không tải ảnh. |

## Lỗi gặp phải và cách xử lý

- NCD-RisC: máy chủ hay trả lỗi 421 (Misdirected Request) với `www.ncdrisc.org` và ngắt kết nối giữa chừng. Lần tải đầu bị cụt file; đã tải tiếp (resume) đến đúng `content-length` và kiểm zip (`unzip -t` không lỗi). manifest ghi sha256 của bản đầy đủ.
- vbpl.vn (CSDL quốc gia) đã chuyển sang ứng dụng JavaScript, curl không lấy được nội dung văn bản; thuvienphapluat trang tìm kiếm trả 403; hethongphapluat trả 500; trolyluat trả 403. Đã dùng trang biểu mẫu của thuvienphapluat + toàn văn trên thuviennhadat.
- Mẫu 30cQĐ, 30dQĐ (giai đoạn thi hành án) và 31aQĐ (đình nã) chưa lưu riêng: không tìm được URL trang biểu mẫu tương ứng; nội dung mục nhân dạng giống 30a/30b.

## Bỏ qua (cần người làm tay hoặc ngoài phạm vi)

- AIST 1991-92 **toàn bộ số liệu dạng Excel/CSV** (thống kê và từng người): chỉ cấp qua email + bản đồng ý → không làm. Nếu cần số dạng bảng thay vì ảnh GIF, bạn tự email xin.
- WHO STEPS VN microdata: không tải (theo yêu cầu; điều khoản chỉ cho y tế công cộng).
- MAAD-Face .pkl: không tải (đã có CSV cùng nội dung).
- ANSUR II báo cáo tóm tắt 444 trang: không tải (ngoài danh sách được duyệt).

## Việc bạn cần làm tay

1. Mở `02_who_steps_vn\WHO_STEPS_VietNam_2015_report.pdf` xem đúng là báo cáo STEPS VN 2015 (tên file trên CDN WHO khớp, nhưng chưa đọc được nội dung).
2. Nếu muốn mẫu 30c/30d/31a: mở TT 22/2014 trên thuvienphapluat hoặc vbpl.vn bằng trình duyệt và lưu tay.
3. AIST: hoặc chấp nhận OCR 254 ảnh GIF, hoặc email AIST xin gói Excel/CSV (miễn phí, có bản đồng ý).
4. Kiểm lại hiệu lực hiện tại của TT 22/2014/TT-BCA (các trang đăng lại không ghi rõ).
