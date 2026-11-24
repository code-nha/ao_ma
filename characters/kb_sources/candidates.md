# Nguồn dữ liệu miễn phí cho KB ngoại hình nhân vật (ứng viên)

Ngày khảo sát: 2026-11-24. Chỉ đọc trang web, **chưa tải dataset nào**.
Mục đích dùng: nghiên cứu cá nhân, phi thương mại. Nguồn nào phải mua hoặc thương lượng giấy phép đều bị loại.

Quy ước độ tin cậy:
- **[Đã kiểm]** = đã mở được trang/tìm thấy bằng chứng trực tiếp trong phiên này.
- **[Kiểm một phần]** = có bằng chứng gián tiếp (kết quả tìm kiếm, trang phụ), chưa đọc được trang gốc hoặc nội dung chi tiết.
- **[Chưa kiểm]** = biết là có tồn tại nhưng phiên này không xác minh được; cần bạn mở tay trước khi tin.

Nhóm: (1) nhân trắc/thống kê cơ thể, (2) dataset mặt/thân có nhãn thuộc tính, (3) từ vựng nhận dạng, (4) dấu hiệu nghề nghiệp/y khoa nhìn thấy được, (5) khác.

---

## A. Shortlist 10 nguồn giá trị nhất (xếp hạng)

| # | Nguồn | Nhóm | Lấp slot nào | Điều kiện | Vì sao đứng đây |
|---|---|---|---|---|---|
| 1 | NCD-RisC (chiều cao, BMI theo nước × giới × tuổi × năm) | 1 | chiều cao, độ béo/gầy | Tải thẳng CSV, không đăng ký; không ghi license | Nguồn duy nhất cho phân phối VN + cả ĐNÁ theo thế hệ (nhân vật 20 tuổi vs 70 tuổi cao khác nhau) |
| 2 | Báo cáo WHO STEPS Việt Nam 2021 (và 2015) | 1 | BMI, vòng eo, thừa cân theo tuổi × giới × thành thị/nông thôn | PDF tự do, CC BY-NC-SA 3.0 IGO | Số đo thật của người lớn VN 18–69, có vòng eo/hông |
| 3 | Bài nhân trắc đầu mặt người Kinh 18–25 (ĐH Y Hà Nội: 7.376 người Hà Nội + Bình Dương; 2.462 ảnh chuẩn hoá Bình Dương) | 1/2 | dạng đầu, dạng mặt, dạng mũi, hàm, tần suất theo giới | PDF tự do trên trang tạp chí, không ghi license | Tần suất dạng mặt *của người Việt*, không phải ngoại suy từ dataset Tây |
| 4 | Interpol DVI – mẫu Ante-Mortem (vàng) 2018/2023 | 3 | toàn bộ: vóc, đầu, tóc, trán, mày, mắt, mũi, tai, miệng, răng, cằm, tay chân, sẹo, xăm, dị tật | PDF tự do, không đăng ký | Bộ khung slot chuẩn quốc tế, có sẵn danh sách lựa chọn cho từng bộ phận |
| 5 | Mẫu Quyết định truy nã VN (TT 22/2014/TT-BCA, mẫu 30a–30dQĐ) + các thông báo truy nã công khai | 3 | cao, màu da, tóc, lông mày, sống mũi, dái tai, mắt, đặc điểm khác | Văn bản pháp luật công khai | Từ vựng tiếng Việt chính thống; thông báo thật = kho câu mô tả tự nhiên |
| 6 | Elements of Morphology (NIH) | 3 | đầu-mặt, quanh mắt, tai, mũi-nhân trung, môi-miệng, bàn tay-chân | Web tự do | Định nghĩa chính xác từng nét (kèm hình), tránh từ mơ hồ |
| 7 | AIST Anthropometric Database 1991-92 (Nhật) – bảng thống kê | 1 | ~250 kích thước: đầu, tay, chân, vòng, bề dày nếp da; có nhóm 60+ | Thống kê dùng không cần xin; raw data phải email xin (miễn phí) | Bộ Đông Á chi tiết nhất có nhóm người già; tỉ lệ thân thể |
| 8 | ANSUR II (US Army) | 1 | khung xương, tỉ lệ vai/hông/tay/chân, tương quan giữa các số đo | CSV tải thẳng, public release | Raw từng người → học tương quan (cao thì tay dài bao nhiêu); cần hiệu chỉnh vì là lính Mỹ |
| 9 | NCIC SMT codes (scars/marks/tattoos) + NamUs | 3 | sẹo, bớt, xăm, khuyên, dị tật, bộ phận giả, vị trí trên cơ thể | Công khai | ~939 mã dấu vết × vị trí, dùng làm danh mục "marks" |
| 10 | MAAD-Face (47 thuộc tính, chỉ nhãn) | 2 | từ vựng + đồng xuất hiện thuộc tính mặt/tóc/râu/phụ kiện | CSV trên GitHub Releases, CC BY-SA 4.0 | Bảng nhãn lớn nhất không cần giữ ảnh; yếu về ĐNÁ |

Ghi chú thẳng: **không có nguồn mở nào cho tần suất nét mặt người ĐNÁ ở quy mô lớn.** FairFace có nhãn "Southeast Asian" nhưng chỉ có tuổi/giới/chủng tộc, không có nét mặt. Phần tần suất nét mặt người Việt phải ghép từ các bài báo y khoa VN (mục 3) và phán đoán.

## B. Kế hoạch tải trước (bạn tự làm; tổng dung lượng nhỏ)

1. **NCD-RisC**: `data-downloads-height.html` (file country .zip, trẻ + vị thành niên 1985–2019), trang BMI người lớn (2 zip age-specific nam/nữ theo nước), và từ `archives.html` file `NCD_RisC_eLife_2016_height_age18_countries.csv` (chiều cao người lớn theo năm sinh). Lọc: Viet Nam, Lào, Campuchia, Thái Lan, Indonesia, Philippines, Myanmar, Malaysia.
2. **WHO STEPS VN 2021**: PDF báo cáo 101 trang (3,9 MB). Chép tay bảng BMI/vòng eo theo nhóm tuổi × giới. Không cần microdata.
3. **2 bài nhân trắc đầu mặt người Kinh** (PDF vài trăm KB mỗi bài) + lần theo tài liệu tham khảo của chúng để lấy thêm bài về mũi, mắt, môi, mặt nghiêng.
4. **Interpol AM form 2023** (bản flat ~3 MB) → rút danh sách slot + giá trị thành `vocab_dvi.md`.
5. **Mẫu truy nã 30aQĐ** + thu ~50 thông báo truy nã/tìm người thân công khai làm mẫu câu tiếng Việt.
6. **Elements of Morphology**: đọc web, chép thuật ngữ theo 6 vùng.
7. **AIST 91-92**: tải gói thống kê (Excel/CSV) từ trang; chỉ email xin raw nếu thấy cần.
8. **ANSUR II**: 2 CSV (~3 MB) + Measurer's Handbook.
9. **NCIC SMT**: bảng mã (qua tài liệu NIST hoặc ecfr.io).
10. **MAAD-Face.csv** (để sau cùng; chỉ lấy danh sách 47 nhãn và ma trận đồng xuất hiện).

Việc cần bạn tự làm tay (đăng ký/đồng ý điều khoản): xin raw AIST (email + bản đồng ý), CFD (form có ghi trường đại học), IFLS (form RAND), WHO NCD microdata (đồng ý điều khoản – nhưng xem cảnh báo ở mục C1.3).

---

## C. Chi tiết từng nguồn

### Nhóm 1 – Nhân trắc và thống kê cơ thể

**1.1 NCD-RisC (NCD Risk Factor Collaboration)** — [Đã kiểm]
- URL: https://www.ncdrisc.org/data-downloads-height.html ; https://www.ncdrisc.org/data-downloads-adiposity.html ; bản cũ: https://ncdrisc.org/archives.html
- Cho slot: chiều cao (trẻ/vị thành niên 5–19 theo tuổi, 1985–2019, 200 nước; người lớn theo năm sinh trong file eLife 2016), BMI trung bình và tỉ lệ gầy/béo người lớn theo nước × giới × nhóm tuổi.
- Định dạng/kích thước: CSV và ZIP chứa CSV; có file riêng từng nước. Nhỏ (cỡ MB).
- Điều khoản: trang không có license; chỉ ghi "© Copyright 2026 NCD Risk Factor Collaboration. All Rights Reserved." Các bài báo gốc là open access. Dùng số liệu cho nghiên cứu cá nhân + ghi nguồn là ổn; đừng phát tán lại file.
- Đăng ký: không.
- Lưu ý: đây là **ước lượng mô hình** (trung bình + khoảng bất định), không phải phân phối cá thể → tự gán độ lệch chuẩn (~5,5–6 cm cho chiều cao). Không tách vùng miền trong nước.
- Kết luận: **dùng**.

**1.2 Báo cáo "National survey on the risk factors of NCDs in Viet Nam, 2021" (WHO STEPS)** — [Đã kiểm]
- URL: https://www.who.int/publications/i/item/9789290620266
- Cho slot: thừa cân/béo phì, BMI, vòng eo/hông theo nhóm tuổi (18–29, 30–49, 50–69) × giới; có so sánh 2015–2021. Bảng chi tiết chưa đọc được (trang giới thiệu không liệt kê), cần mở PDF.
- Định dạng: PDF 101 trang, 3,9 MB.
- License: "CC BY-NC-SA 3.0 IGO".
- Đăng ký: không.
- Kết luận: **dùng**.

**1.3 WHO NCD Microdata Repository – Viet Nam STEPS 2021** — [Đã kiểm]
- URL: https://extranet.who.int/ncdsmicrodata/index.php/catalog/948
- Nội dung: 4.435 người, 186 biến; có đo chiều cao, cân nặng, vòng eo, vòng hông; trọng số mẫu.
- Điều khoản: phải đồng ý điều kiện truy cập, gồm "non-commercial, not-for-profit public health purposes only", báo trước cho WHO khi công bố, mời điều phối viên khảo sát làm đồng tác giả.
- Kết luận: **loại (microdata)** — mục đích của ta không phải y tế công cộng nên không khớp điều khoản. Dùng báo cáo 1.2 thay thế.

**1.4 Tổng điều tra dinh dưỡng 2019–2020 (Viện Dinh dưỡng + UNICEF)** — [Kiểm một phần]
- Không tìm được link PDF báo cáo gốc trong phiên này; chỉ có báo chí. Số chắc chắn duy nhất: nam 18 tuổi 168,1 cm, nữ 156,2 cm (2020), nam 2010 là 164,4 cm; thừa cân-béo phì trẻ học đường 8,5% → 19%. Mức tăng của nữ so với 2010 **các báo ghi lệch nhau** (1,4 / 2,4 / 2,6 cm) → đừng dùng con số đó.
- Chiều cao chỉ đo ở nhóm dưới 25 tuổi (theo báo chí) → không có bảng người lớn theo tuổi.
- Việc cần làm: tìm "Báo cáo tóm tắt Tổng điều tra dinh dưỡng 2019-2020" trên viendinhduong.vn / unicef.org/vietnam.
- Kết luận: **có thể dùng** (nếu tìm được PDF; nếu không, chỉ dùng 2 con số trên làm mốc đối chiếu với NCD-RisC).

**1.5 AIST Anthropometric Database 1991-92 (Nhật)** — [Đã kiểm]
- URL: https://www.airc.aist.go.jp/dhrt/91-92/index.html ; danh mục: https://www.airc.aist.go.jp/dhrt/91-92/data/list.html ; cổng chung: https://www.airc.aist.go.jp/dhrt/dhdb.html
- Nội dung: ~500 người (217 nam + 204 nữ tuổi 18–29; 50 nam + 50 nữ tuổi 60+), ~250 kích thước (đầu, cao đứng/ngồi, chi, bề rộng, bề dày, vòng, bàn tay, bàn chân, cân nặng, nếp da).
- Định dạng: bảng thống kê (trung bình, SD, bách phân vị) xem trên web và tải được; gói đầy đủ có raw từng người (Excel + CSV).
- Điều khoản: thống kê dùng không cần xin — "使用申請、同意書の提出などは必要ありません"; raw data miễn phí ("提供は無料です") nhưng phải email xin và ký bản đồng ý. Chân trang vẫn ghi "No reproduction or republication without written permission" → không phát tán lại.
- Đăng ký: thống kê không; raw có (email + consent form, không phải thương lượng).
- Kết luận: **dùng** (thống kê). Lưu ý dữ liệu 1991–92, người Nhật.
- Liên quan, cùng site [Kiểm một phần]: AIST 1997-98 (có manual), AIST/HQL 2003 (file thống kê + định nghĩa đo công khai), cơ sở dữ liệu bàn tay (`/dhrt/hand/`). Chưa đọc điều khoản riêng từng bộ.

**1.6 ANSUR II (US Army Anthropometric Survey, 2012; công khai 2017)** — [Đã kiểm]
- URL: https://www.openlab.psu.edu/ansur2/ ; bản gốc: https://ph.health.mil/topics/workplacehealth/ergo/Pages/Anthropometric-Database.aspx
- Nội dung: 4.082 nam + 1.986 nữ, 93 số đo trực tiếp + biến nhân khẩu (tuổi, chủng tộc tự khai: có mã Asian, Pacific Islander).
- Định dạng: 2 CSV (~1 MB + ~2 MB), báo cáo 444 trang, Measurer's Handbook 263 trang.
- Điều khoản: quân đội Mỹ ghi "cleared for UNLIMITED PUBLIC RELEASE"; trang PSU không ghi license riêng.
- Đăng ký: không.
- Hạn chế: lính Mỹ (khoẻ, trẻ, đã qua tuyển chọn); nhóm Asian nhỏ (một bài báo dùng tập con ghi 240 người, chưa đếm trên file đầy đủ).
- Kết luận: **dùng** — chủ yếu để học *tương quan giữa các số đo*, không lấy trị tuyệt đối.

**1.7 Size Korea (KATS)** — [Chưa kiểm]
- URL: https://sizekorea.kr (WebFetch lỗi chứng chỉ TLS, không mở được).
- Theo thông cáo chính phủ: khảo sát lần 8 (2020–2021) đo 6.839 người 20–69 tuổi, 137 mục đo trực tiếp + 293 mục 3D; từ 2015 có thể nhận dữ liệu qua web. **Chưa xác minh** điều kiện tải, phí, đăng ký, license.
- Kết luận: **có thể dùng** — bạn mở tay; nếu cần tài khoản Hàn hoặc xin duyệt thì bỏ.

**1.8 NHANES (CDC, Mỹ)** — [Kiểm một phần]
- URL: https://wwwn.cdc.gov/nchs/nhanes/ ; bản gộp CSV: https://www.openlab.psu.edu/nhanes/
- Nội dung: file Body Measures (BMX) mỗi chu kỳ 2 năm: cao, nặng, vòng eo, vòng tay… kèm tuổi, giới, chủng tộc (có nhóm Non-Hispanic Asian từ 2011, không tách nước gốc trong bản công khai).
- Điều khoản: dữ liệu công khai, miễn phí, không đăng ký.
- Kết luận: **có thể dùng** — dùng cho đường cong thay đổi theo tuổi (lùn đi, bụng to ra khi già), ít giá trị riêng cho VN.

**1.9 Indonesia Family Life Survey (IFLS, RAND)** — [Kiểm một phần]
- URL: https://www.rand.org/health/surveys/FLS/IFLS/access.html
- Nội dung: khảo sát hộ gia đình Indonesia nhiều vòng; có đo sức khoẻ (chưa tự xác minh biến cao/nặng trong file công khai).
- Điều khoản: miễn phí, phải điền form đăng ký; cam kết không phát tán lại, không nhận diện người trả lời, gửi trích dẫn cho RAND khi công bố.
- Kết luận: **có thể dùng** — raw người ĐNÁ theo tuổi × giới × nông thôn/thành thị; công xử lý lớn, để sau.

**1.10 Nguồn VN/Á khác đã dò mà không dùng được ngay**
- "Atlat nhân trắc học người Việt Nam trong lứa tuổi lao động" (1986) [Chưa kiểm]: chỉ thấy được trích dẫn, không có bản số hoá hợp pháp; một bài 2020s nhận xét là đã lỗi thời. **Loại** (không truy cập được).
- Đề tài chỉ số nhân trắc người lao động VN của VNNIOSH [Kiểm một phần]: chỉ có tên đề tài, không có dữ liệu công khai. **Loại**.
- GB/T 10000-2023 "Kích thước cơ thể người trưởng thành Trung Quốc" [Chưa kiểm]: bản tiếng Anh bán ~485 USD (**loại**); bản tiếng Trung có thể xem miễn phí trên openstd.samr.gov.cn nhưng chưa xác minh. **Có thể dùng** nếu xem được online.
- DHS Việt Nam 1997/2002 [Kiểm một phần]: mẫu là phụ nữ đã kết hôn 15–49; không thấy bằng chứng có đo chiều cao người lớn. **Loại** (cũ, không khớp nhu cầu).
- KNHANES (Hàn), CHNS (Trung Quốc) [Chưa kiểm]: thường miễn phí sau đăng ký; chưa xác minh điều khoản hiện tại. Để dự phòng.

### Nhóm 2 – Dataset mặt/thân có nhãn thuộc tính (chỉ lấy nhãn, không giữ ảnh)

**2.1 MAAD-Face** — [Đã kiểm]
- URL: https://github.com/pterhoer/maad-face (file ở GitHub Releases, tag MAADFACE)
- Nội dung: 47 thuộc tính nhị phân (giá trị 1 / -1 / 0 = không xác định) cho ảnh VGGFace2 (~3,3 triệu ảnh, ~123,9 triệu nhãn). Danh sách 47 tên nằm trong hình/bài báo arXiv 2012.01030, chưa chép được.
- Định dạng: `MAAD-Face.csv` và `.pkl`; dung lượng không ghi (ước vài trăm MB). Ảnh không kèm theo.
- License: "licensed under the terms of the Attribution-ShareAlike 4.0 International".
- Đăng ký: không.
- Hạn chế: người nổi tiếng, lệch phương Tây, lệch đẹp; nhãn sinh tự động.
- Kết luận: **dùng** cho từ vựng + đồng xuất hiện; **không** dùng làm tần suất cho người Việt.

**2.2 FairFace** — [Đã kiểm]
- URL: https://github.com/joojs/fairface
- Nội dung: 108.501 ảnh (YFCC-100M/Flickr); nhãn: 7 nhóm chủng tộc (có "Southeast Asian"), 2 giới, 9 nhóm tuổi (0–2 … 70+). Không có nhãn nét mặt.
- Định dạng: 2 file nhãn train/val (Google Drive), tách khỏi ảnh.
- License: "License: CC BY 4.0".
- Đăng ký: không.
- Kết luận: **có thể dùng** — ít giá trị cho từ vựng; dataset được cân bằng cố ý nên tần suất không phản ánh dân số. Chỉ hữu ích nếu sau này muốn lấy mẫu ảnh ĐNÁ để tự gán nhãn.

**2.3 CelebA** — [Đã kiểm]
- URL: https://mmlab.ie.cuhk.edu.hk/projects/CelebA.html
- Nội dung: >200K ảnh người nổi tiếng, 40 thuộc tính nhị phân (file "Attributes Annotations" trên Google Drive/Baidu).
- Điều khoản: "available for non-commercial research purposes only".
- Kết luận: **có thể dùng** (chỉ danh sách 40 nhãn). Lệch người nổi tiếng/đẹp; có nhãn chủ quan kiểu "Attractive" → ngược mục tiêu "không làm đẹp". MAAD-Face bao trùm tốt hơn.

**2.4 UTKFace** — [Đã kiểm]
- URL: https://susanqq.github.io/UTKFace/
- Nội dung: >20.000 ảnh; nhãn trong tên file: tuổi 0–116, giới, chủng tộc 5 lớp (White, Black, Asian, Indian, Others).
- Điều khoản: "available for non-commercial research purposes only" (nguyên văn có lỗi chính tả "avaiable").
- Kết luận: **loại** — không có nhãn nét mặt, "Asian" gộp chung, không thêm gì so với FairFace.

**2.5 Chicago Face Database (CFD, CFD-MR, CFD-India)** — [Đã kiểm]
- URL: https://www.chicagofaces.org/download/
- Nội dung: ảnh chuẩn hoá + **norming data**: số đo khuôn mặt khách quan (theo measurement guide) và đánh giá chủ quan; CFD-MR 88 người đa chủng, CFD-India 142 người. Có link riêng `cfd301norms.zip` (norming + codebook) và `cfdmguide.pdf`.
- Điều khoản: "free of charge for non-commercial scientific research purposes only"; cấm phát tán lại, cấm đưa lên dịch vụ đám mây/AI.
- Đăng ký: bản đầy đủ cần form (tên, email, **trường đại học**, mô tả nghiên cứu). Hai link norming/guide có vẻ tải thẳng nhưng vẫn chịu cùng điều khoản.
- Kết luận: **có thể dùng** — chỉ lấy measurement guide (định nghĩa cách đo mặt) và norming; không đưa ảnh vào pipeline AI. Không có người ĐNÁ. Nếu bạn không có danh nghĩa đại học thì bỏ bản đầy đủ.

**2.6 Chưa xác minh, ghi để dò sau** — [Chưa kiểm]
- AFAD (Asian Face Age Dataset, >160K ảnh, chỉ nhãn tuổi/giới; không tìm thấy license).
- PA-100K / RAP (thuộc tính người đi đường: dáng, tóc, quần áo; quay ở Trung Quốc) — không xác minh được license trong phiên này.
- Không tìm thấy dataset mở nào có nhãn nét mặt chi tiết riêng cho người Việt/ĐNÁ.

### Nhóm 3 – Từ vựng nhận dạng

**3.1 Interpol DVI forms** — [Kiểm một phần]
- URL: trang chính https://www.interpol.int/en/How-we-work/Forensics/Disaster-Victim-Identification-DVI (trả 403 với công cụ tự động; mở bằng trình duyệt). File: https://www.interpol.int/content/download/5324/file/AM2023_enGB_Flat_Ver1.0.3.pdf (AM vàng, 2023, ~3 MB, ~16 trang — link trả về PDF thật); PM hồng: https://www.interpol.int/en/content/download/5325/file/PMFormSet_en-GB.pdf
- Nội dung: khối 100 hành chính, 200 nhân thân, 300 vật dụng, **400 mô tả cơ thể** (có mục "Distinctive feature(s)"), 600 răng, 700 thông tin bổ sung. Có bản EN/FR/ES/AR.
- Lưu ý: PDF mã hoá nên không trích được chữ trong phiên này → **chưa tự đọc danh sách lựa chọn từng mục**; mô tả trên dựa vào đoạn trích tìm kiếm.
- Điều khoản: mẫu công khai để các nước dùng; không thấy dòng license.
- Đăng ký: không.
- Kết luận: **dùng** — làm khung slot chính.

**3.2 Mẫu Quyết định truy nã Việt Nam** — [Đã kiểm]
- URL: https://luatvietnam.vn/hinh-su/thong-tu-22-2014-tt-bca-bo-cong-an-87772-d1.html (Thông tư 22/2014/TT-BCA, hiệu lực 17/07/2014; link PDF gốc trên moj.gov.vn trả 404)
- Nội dung: mục "Đặc điểm nhân dạng" trong mẫu 30aQĐ–30dQĐ gồm 7 trường: **chiều cao, màu da, tóc, lông mày, sống mũi, dái tai, mắt** + "Đặc điểm khác".
- Điều khoản: văn bản quy phạm pháp luật, công khai.
- Chưa rõ: tình trạng hiệu lực hiện tại (trang ghi "đang cập nhật").
- Bổ sung: thông báo truy nã thật trên báo và VNeID dùng đúng bộ từ này (ví dụ "lông mày rậm, sống mũi cao, dái tai nhỏ") → kho mẫu câu.
- Kết luận: **dùng**.

**3.3 "Đặc điểm nhân dạng" trên CMND/CCCD** — [Kiểm một phần]
- Chỉ tìm được bài giải thích luật: nhân dạng là "đặc điểm cá biệt và ổn định bên ngoài" (Luật CCCD 2014), ví dụ sẹo, nốt ruồi, kèm vị trí. Không tìm được văn bản quy định cách ghi chi tiết (link Thông tư 27/2012 trả 404).
- Kết luận: **có thể dùng** — chỉ lấy quy ước mô tả (loại dấu + kích thước + khoảng cách tới mốc trên mặt). Giá trị từ vựng thấp hơn 3.2.

**3.4 NCIC codes – Scars, Marks, Tattoos (SMT) và mô tả cá nhân** — [Đã kiểm]
- URL: https://ecfr.io/ncic/sets/SMT (công cụ tra cứu độc lập, 939 giá trị theo NIEM 5.2, 12/2022; có API công khai `/ncic/api/v1/sets`); bản gốc cũ: NCIC Code Manual trên ojp.gov; bảng mã sẹo trong tài liệu NIST.
- Nội dung: mã cho sẹo, bớt, đổi màu da, xăm, xăm đã xoá, dị tật, bộ phận giả, bệnh mắt… × vị trí cơ thể. Bộ mã tóc/mắt/màu da có trong NCIC Code Manual Part 4 (chưa tự xem bảng).
- Điều khoản: tài liệu chính phủ Mỹ công khai; trang ecfr.io tự mô tả là "an independent eCFR.io research tool" (không chính thức).
- Đăng ký: không.
- Kết luận: **dùng** — danh mục "marks × vị trí".

**3.5 NamUs (Mỹ)** — [Kiểm một phần]
- URL: https://namus.nij.ojp.gov ; hướng dẫn nhập hồ sơ: `…/media/document/userguide-enteringmpcases.pdf` (3,7 MB, PDF có thật nhưng không trích được chữ).
- Nội dung (theo đoạn trích): mục Physical Description, "Add Distinctive Physical Features" theo loại (xăm, khuyên, sẹo…) + ô mô tả tự do; worksheet cũ có tóc đầu, lông cơ thể, râu, mắt, móng, bộ phận nhân tạo.
- Xem hồ sơ công khai không cần tài khoản; tài khoản chuyên môn thì cần đăng ký.
- Kết luận: **có thể dùng** — trùng nhiều với DVI + NCIC; lợi thế là hồ sơ thật có mô tả tự do bằng lời.

**3.6 Elements of Morphology (NIH/NHGRI)** — [Đã kiểm]
- URL: https://elementsofmorphology.nih.gov/
- Nội dung: thuật ngữ chuẩn mô tả hình thái, 6 phần: đầu và mặt, vùng quanh mắt, tai, mũi và nhân trung, môi/miệng/vùng miệng, bàn tay và bàn chân; mỗi thuật ngữ có định nghĩa + hình minh hoạ. Từ 6 bài AJMG 2009.
- Điều khoản: trang chỉ ghi "Published 2009 Wiley-Liss, Inc."; một danh bạ bên thứ ba ghi public domain (chưa xác nhận). Đọc và dùng thuật ngữ thì ổn; đừng sao lại hình.
- Đăng ký: không.
- Lưu ý: thiên về bất thường, nhưng định nghĩa hai cực của từng nét (mũi rộng/hẹp, tai thấp, mí…) dùng tốt cho biến thể bình thường.
- Kết luận: **dùng**.

**3.7 Human Phenotype Ontology (HPO)** — [Kiểm một phần]
- URL: https://human-phenotype-ontology.github.io/license.html ; file: http://purl.obolibrary.org/obo/hp.obo
- Nội dung: ontology kiểu hình (đã nhập thuật ngữ Elements of Morphology), có cấu trúc cây, máy đọc được.
- Điều khoản: miễn phí; điều kiện là ghi nguồn, hiển thị phiên bản, và không sửa nội dung file.
- Kết luận: **có thể dùng** — tiện nếu cần bản máy đọc được của 3.6; phần lớn nhánh là bệnh lý, phải lọc.

**3.8 FISWG "Facial Image Comparison Feature List for Morphological Analysis"** — [Kiểm một phần]
- Danh sách nét mặt dùng trong giám định so sánh khuôn mặt (rất hợp nhu cầu). Bản FISWG miễn phí được cho là ở fiswg.org/documents nhưng URL thử trả 404; bản ASTM E3149 (19 trang) là **bản bán** → loại bản ASTM.
- Kết luận: **có thể dùng** nếu bạn tìm được PDF FISWG miễn phí trên fiswg.org.

### Nhóm 4 – Dấu hiệu nghề nghiệp và y khoa nhìn thấy được

**4.1 Nhân trắc đầu mặt người Kinh 18–25 (Tạp chí Nghiên cứu Y học, 2023)** — [Đã kiểm]
- URL: https://tapchinghiencuuyhoc.vn/index.php/tcncyh/article/view/1358
- Nội dung: 7.376 người Kinh ở Hà Nội và Bình Dương, đo trực tiếp, phân loại Martin–Saller. Dạng đầu "rất ngắn" nam 40,32% / nữ 44,73%; mặt "rất rộng" ở nam 45,6%, nữ chủ yếu "trung bình" 37,4%; mũi "trung bình" nam 43% / nữ 46%; hàm dưới rộng nam 92,93% / nữ 98,44%.
- Điều khoản: có link PDF; trang không ghi license nội dung. Trích số liệu + ghi nguồn.
- Kết luận: **dùng**.

**4.2 Kích thước mặt theo dạng mặt, người Kinh 18–25 tại Bình Dương (Tạp chí Y học Việt Nam)** — [Đã kiểm, qua trang đăng lại]
- URL: https://vnras.com/phan-tich-kich-thuoc-khuon-mat-theo-hinh-dang-khuon-mat-nguoi-viet-tu-18-den-25-tuoi-tai-tinh-binh-duong/
- Nội dung: 2.462 người (1.328 nữ, 1.134 nam), ảnh chuẩn hoá: mặt oval 66,3%, vuông 26,6%, tam giác 7,1%. Tỉ lệ theo giới và số đo chi tiết nằm trong PDF (chưa mở). Số/năm tạp chí gốc chưa rõ.
- Kết luận: **dùng** (chỉ 3 lớp dạng mặt, chỉ tuổi 18–25 — phải tự ngoại suy cho tuổi khác).
- Cùng loại, dò tiếp [Kiểm một phần]: mô mềm mặt nghiêng 183 sinh viên Huế (kiểu mặt nghiêng lồi chiếm đa số); hình thái mũi 149 ca tại BV 175 (mẫu là bệnh nhân thẩm mỹ, lệch). **Không tìm được** nghiên cứu dân số về tỉ lệ mắt một mí/hai mí, hói, bạc tóc ở người Việt.

**4.3 Thang chấm nếp nhăn/lão hoá da cho người Á (open access, PMC)** — [Kiểm một phần]
- URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC12445401 (thang ảnh-số nếp nhăn mặt người Trung Quốc: trán, gian mày, đuôi mắt, rãnh mũi-má; 10 mức; dựng từ 5.310 ảnh phụ nữ); https://pmc.ncbi.nlm.nih.gov/articles/PMC11116842 (so thang Hàn vs thang da trắng trên cohort Singapore/Malaysia: thang Hàn tách **nhăn** và **rối loạn sắc tố**); https://pmc.ncbi.nlm.nih.gov/articles/PMC11569137
- Cho slot: da theo tuổi — mức nhăn từng vùng, đồi mồi/nám như một trục riêng (điểm quan trọng: người Á lão hoá bằng sắc tố nhiều hơn bằng nếp nhăn).
- Điều khoản: bài open access (license cụ thể từng bài chưa đọc); dùng thang mô tả bằng lời, không sao ảnh.
- Kết luận: **dùng** (lấy định nghĩa mức độ bằng chữ).

**4.4 Bệnh da nghề nghiệp ở Việt Nam** — [Kiểm một phần]
- Công nhân chế biến thuỷ sản Cần Thơ (Tạp chí Y học Cộng đồng, 2025; https://tapchiyhcd.vn): 9,3% (35/376) có bệnh da nghề nghiệp; trong số mắc: hội chứng Raynaud 51,4%, viêm quanh móng 25,7%, nấm móng 20%, viêm da tiếp xúc 2,9%. Một công ty, không khái quát được.
- Nông dân trồng lúa dùng nước thải ở Nam Định (2007; https://pubmed.ncbi.nlm.nih.gov/18005315/): tỉ suất mắc mới bệnh da 21%/năm. Chưa xác nhận open access.
- **Không tìm thấy** số liệu VN về chai tay, da cháy nắng của ngư dân/nông dân.
- Kết luận: **có thể dùng** — vài con số neo, phần còn lại phải viết theo hiểu biết lâm sàng chung.

**4.5 Răng miệng Việt Nam** — [Kiểm một phần]
- Điều tra răng miệng toàn quốc 2019: chỉ thấy bài phân tích nha chu theo tỉnh (Asia Pac J Public Health 2022, chưa rõ open access). Điều tra 1999 (công bố 2009): người lớn DMFT trung bình 4,98, phần lớn là sâu chưa chữa; 85% trẻ 6–17 có sâu răng. Người 65–74: có luận án ở dspace.ut.ee. **Không có** số toàn quốc về mất răng/lệch khớp cắn người lớn 2019.
- Kết luận: **có thể dùng** — đủ để gán xác suất "răng xấu/sâu chưa chữa" cao ở người lớn tuổi, nông thôn; số liệu cũ.

**4.6 Tần suất dấu hiệu da thường gặp** — [Kiểm một phần]
- Bạch biến: meta-analysis PLoS ONE 2016 (https://pmc.ncbi.nlm.nih.gov/articles/PMC5038943, open access): ~0,1% dân số ở châu Á (nghiên cứu cộng đồng). Bài 2024 (JEADV Clin Pract): Đông Á 0,12%, người lớn 0,70% toàn cầu — hai bài phân vùng khác nhau, không so trực tiếp.
- Nám: không có số liệu dân số VN; chỉ có chuỗi ca bệnh viện. Con số "40% ở ĐNÁ" trôi nổi, nguồn không rõ → **không dùng**.
- Bớt bẩm sinh, số nốt ruồi ở người Á: chưa tìm.
- Kết luận: **có thể dùng** (bạch biến); các mục khác còn trống.

### Nhóm 5 – Mở rộng đa dạng

**5.1 Wikimedia Commons – cây thể loại người Việt theo nghề** — [Đã kiểm]
- URL: https://commons.wikimedia.org/wiki/Category:People_of_Vietnam_by_occupation
- Nội dung: 83 thể loại con; ví dụ Farmers from Vietnam (56 file), Buddhist monks of Vietnam (84), Students in Vietnam (107), Military people (87), Politicians (114). Mỗi file có license riêng (CC/PD) và có thể có structured data "depicts" (P180); truy vấn qua Commons Query Service (cần đăng nhập tài khoản Wikimedia).
- Hạn chế: số lượng nhỏ, metadata không mô tả ngoại hình; nghiêng về người nổi tiếng.
- Kết luận: **có thể dùng** — làm ảnh tham chiếu để tự quan sát/gán nhãn theo nghề, không phải nguồn thống kê.

**5.2 Photothèque EFEO (Viện Viễn Đông Bác Cổ)** — [Kiểm một phần]
- URL: https://collection.efeo.fr
- Ảnh dân tộc học Đông Dương có chú thích; nhưng tái sử dụng phải liên hệ thư viện ảnh, nội dung được bảo hộ.
- Kết luận: **loại** làm nguồn dữ liệu (cần xin phép). Xem bằng mắt để tham khảo thì được.

---

## D. Bảng tóm tắt kết luận

| Nguồn | Nhóm | Kết luận | Đăng ký? |
|---|---|---|---|
| NCD-RisC | 1 | dùng | không |
| WHO STEPS VN 2021 – báo cáo | 1 | dùng | không |
| WHO STEPS VN 2021 – microdata | 1 | loại (điều khoản chỉ cho y tế công cộng) | có |
| Tổng điều tra dinh dưỡng 2019–2020 | 1 | có thể dùng (chưa tìm được PDF) | không |
| AIST 1991-92 | 1 | dùng (thống kê) | raw: email xin |
| ANSUR II | 1 | dùng | không |
| Size Korea | 1 | có thể dùng (chưa kiểm) | chưa rõ |
| NHANES | 1 | có thể dùng | không |
| IFLS | 1 | có thể dùng | có (form) |
| Atlat nhân trắc VN 1986, VNNIOSH, DHS VN | 1 | loại (không truy cập được / không khớp) | – |
| GB/T 10000-2023 | 1 | bản dịch: loại (bán); bản Trung: chưa kiểm | – |
| MAAD-Face | 2 | dùng (nhãn) | không |
| FairFace | 2 | có thể dùng | không |
| CelebA | 2 | có thể dùng (danh sách nhãn) | không |
| UTKFace | 2 | loại (không có nhãn nét mặt) | không |
| Chicago Face Database | 2 | có thể dùng (guide + norming) | bản đầy đủ: form |
| Interpol DVI | 3 | dùng | không |
| Mẫu truy nã VN (TT 22/2014) | 3 | dùng | không |
| Nhân dạng trên CCCD | 3 | có thể dùng | không |
| NCIC SMT | 3 | dùng | không |
| NamUs | 3 | có thể dùng | không (xem công khai) |
| Elements of Morphology | 3 | dùng | không |
| HPO | 3 | có thể dùng | không |
| FISWG feature list | 3 | có thể dùng (chưa tìm được link); bản ASTM: loại (bán) | – |
| Nhân trắc đầu mặt người Kinh (2 bài) | 4 | dùng | không |
| Thang nếp nhăn/lão hoá người Á (PMC) | 4 | dùng | không |
| Bệnh da nghề nghiệp VN | 4 | có thể dùng | không |
| Răng miệng VN | 4 | có thể dùng | không |
| Bạch biến (meta-analysis) | 4 | có thể dùng | không |
| Wikimedia Commons | 5 | có thể dùng | truy vấn SPARQL: tài khoản |
| EFEO photothèque | 5 | loại (phải xin phép) | – |

## E. Lỗ hổng còn lại (chưa có nguồn mở)

- Chiều cao/cân nặng người lớn VN **theo vùng miền** và theo dân tộc: không tìm được bảng công khai.
- Tần suất nét mặt người Việt ngoài nhóm 18–25: mí mắt, dạng mũi chi tiết, môi, tai, đường chân tóc, hói, bạc tóc.
- Màu da (thang Fitzpatrick/ITA) phân bố ở VN.
- Dấu hiệu lao động tay chân (chai, móng, sạm nắng) có số liệu.
- Nám, bớt, nốt ruồi: tần suất dân số ở VN/ĐNÁ.

Các ô này tạm thời phải điền bằng phán đoán có ghi rõ "ước lượng", không gắn nguồn.

## F. Ghi chú kỹ thuật của phiên khảo sát

- Hai PDF (Interpol AM 2023, NamUs user guide) được công cụ fetch tự lưu vào thư mục tool-results của phiên khi mở link; không trích được chữ (thiếu thư viện PDF, file Interpol có mã hoá). Không tải dataset nào.
- Trang không mở được bằng công cụ: sizekorea.kr (lỗi TLS), interpol.int trang DVI (403), fiswg.org/documents.html (404), ncdrisc.org/data-downloads.html (421), 2 link PDF văn bản trên moj.gov.vn / vbpl.vn (404).
