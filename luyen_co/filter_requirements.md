# Yêu cầu lọc ảnh — dataset LoRA

Cập nhật **2026-11-25** (thay bản 3 lớp bằng bản 4 lớp khung hình + dải tỉ lệ).
Áp dụng cho mọi thư mục nguồn; hiện tại: `F:\pic\phuong_mai` (nguồn chính) và
`output/obj_1/crops`. **Video bỏ qua** — chỉ lấy ảnh tĩnh.

---

## 1. Số lượng và độ nét

| Tiêu chí | Yêu cầu | Tối thiểu |
|---|---|---|
| Số ảnh | **80–150** | **55** |
| Cạnh ngắn | **≥ 1024px** | **768px**, nhỏ hơn thì bỏ (không phóng to) |
| Chất lượng JPEG | **≥ q90** | **q85** |
| Định dạng | JPEG hoặc PNG, RGB | — |

## 2. Tỉ lệ khung hình

| Loại ảnh | Tỉ lệ | Với 55 ảnh | Mô tả |
|---|---|---|---|
| Cận mặt | **20–35%** | 11–19 | Mặt chiếm khoảng nửa khung trở lên, thấy đủ tóc, cằm, một phần vai |
| Ngang vai, ngang ngực | **30–45%** | 17–25 | Thấy rõ mặt cùng phần trên quần áo |
| Ngang eo | **15–30%** | 8–16 | Mặt vẫn rõ, không bị che |
| Toàn thân | **10–20%** | 5–10 | Bắt buộc nếu muốn tạo ảnh toàn thân |

Tổng các dải: 75–130%. Không có tỉ lệ cố định — chỉ cần **rơi vào dải** của từng
lớp; khi số ảnh tăng thì cả 4 lớp đều phải có mặt.

## 3. Độ nét

- Không nhòe do **chuyển động** (motion blur).
- Không **vỡ khối vì nén** (blockiness).
- Không **filter đậm**, không **làm mịn da quá tay** (beauty cam).
- Frame cắt từ video: chỉ lấy frame **nét và rõ mặt**.

## 4. Đa dạng

- **Góc mặt**: chính diện, nghiêng 3/4, nghiêng hẳn, hơi ngẩng, hơi cúi.
- **Biểu cảm**: bình thường, cười, cười hở răng, nghiêm.
- **Ánh sáng & bối cảnh**: trong nhà, ngoài trời, ngày, đêm. Đừng quá nhiều ảnh
  cùng một buổi chụp.
- **Quần áo & kiểu tóc**: càng đa dạng càng tốt, để LoRA chỉ học khuôn mặt chứ
  không học luôn bộ đồ.

## 5. Tránh

- Ảnh có người khác — nếu có thì crop để chỉ còn nhân vật.
- Mặt bị che: kính râm, tay, khẩu trang, tóc che nửa mặt.
- Filter đậm, beauty cam, làm mịn da quá tay.
- Ảnh trùng hoặc gần trùng nhau.
- Ảnh có chữ, logo hay watermark đè lên mặt.
- Cắt sát chỉ còn mặt (mất tóc, cằm hoặc vai).

---

## 6. Script kiểm những gì (ánh xạ yêu cầu → cờ)

| Yêu cầu | Cờ | Mặc định | Cách đo |
|---|---|---|---|
| Số ảnh 80–150, tối thiểu 55 | `--workflow max-fill`, `--max-images 200` | — | lấy tối đa cận+vai rồi bù toàn thân cho đủ 25% |
| Cạnh ngắn ≥ 768 (mục tiêu 1024) | `--min-side`, `--ideal-side` | 768 / 1024 | kích thước file |
| JPEG ≥ q85 (mục tiêu q90) | `--min-jpeg-quality` | 85–90 | so bảng lượng tử trong header với 100 bảng chuẩn IJG |
| Không vỡ khối vì nén | *báo cáo* | — | `blockiness` = gradient ở biên khối 8×8 / gradient trung bình |
| Không nhòe do chuyển động | `--min-face-sharp`, `--min-img-sharp` | 55 / 40 | Laplacian vùng mặt 112×112 + cả ảnh |
| Đủ sáng, không bệt | `--min-lum`, `--max-lum`, `--min-face-std` | 62 / 212 / 14 | độ sáng & độ lệch chuẩn vùng mặt |
| Mặt rõ, không bị cắt | `--min-face-px`, `--face-border` | 80 / 0.012 | SCRFD + khoảng cách mặt tới mép |
| Không cắt sát chỉ còn mặt | `--max-face-frac` | 0.75 | chiều cao mặt / chiều cao khung |
| Không có người khác | `--max-other-face`, `--max-other-person` | 0.22 / 0.30 | SCRFD nhiều mặt + YOLO nhiều người |
| Đúng người | `--ref`, `--min-face-sim` | — / 0.38 | ArcFace cosine với ảnh tham chiếu |
| Chia 4 lớp khung hình | `--close-frac`, `--chest-frac`, `--waist-frac` | 0.34 / 0.22 / 0.13 | chiều cao hộp mặt / chiều cao ảnh |
| Không trùng / gần trùng | `--dup-hamming` | 6 (10 nếu cùng nguồn & ≤2.5s) | MD5 + dHash 64 bit (kể cả bản lật) |
| Đừng quá nhiều ảnh cùng buổi chụp | `--look-sim`, `--per-look`, `--source-share`, `--per-window` | 0.88 / 3 / 12% / 2 mỗi 10s | CLIP + nguồn + cửa sổ thời gian |
| Watermark / kính râm / tóc che | `--skip-list` | — | **soi mắt** trên `sheet_*.jpg` rồi liệt kê file |

## 7. Vận hành

- Nguồn: `--src` (một hoặc nhiều thư mục; chỉ file ảnh, video bị bỏ qua).
- Đích: `--dst` — **chép** ảnh đạt, không sửa ảnh gốc; `--clean` xoá ảnh cũ trước.
- Báo cáo: `filter_report.csv` (mọi số đo + lý do loại từng ảnh),
  `filter_summary.txt`, `sheet_flter_*.jpg`, `sheet_facecrop_*.jpg`.
- Số đo cache ở `filter_cache.json`: đổi ngưỡng chỉ cần chạy lại.

## 8. Kết quả đang có

| Bộ | Tổng | Cận | Vai/ngực | Ngang eo | Toàn thân | Có nằm trong dải spec? |
|---|---|---|---|---|---|---|
| `output/train_pm_4lop` | **120** | 30 (25%) | 46 (38%) | 26 (22%) | 18 (15%) | ✓ cả 4 lớp và tổng |
| `output/train_55pm` | 55 | 22 (40%) | 19 (34.5%) | — | 14 (25.5%) | bản 3 lớp cũ |
| `output/train_pm_maxfill` | 145 | 29 (20%) | 80 (55%) | — | 36 (25%) | bản 3 lớp cũ |

Lệnh tạo bộ 4 lớp:

```powershell
cd luyen_co
.venv\Scripts\python.exe -X utf8 filter_dataset.py --src F:\pic\phuong_mai `
  --dst output\train_pm_4lop\images --report-dir output\train_pm_4lop `
  --ref sample\obj_1\main.jpg --min-face-sim 0.38 `
  --workflow max-fill --min-jpeg-quality 85 --clean
```

## 9. Ghi chú triển khai

- Bản 2026-11-25 chuyển từ **3 lớp** (cận / vai-ngực / toàn thân) sang **4 lớp**
  (cận / vai-ngực / **ngang eo** / toàn thân) và từ tỉ lệ cố định sang **dải tỉ lệ**.
- Ngưỡng phân loại: `--close-frac 0.34`, `--chest-frac 0.20` theo hộp mặt; riêng
  ranh giới **eo / toàn thân** đo bằng `--waist-extent 4.5` = số "đầu" từ cằm
  xuống đáy ảnh (≥4.5 là thấy tới đùi/gối/bàn chân, tức toàn thân).
- Quota khi chọn = **trung điểm các dải** (27.5 / 37.5 / 22.5 / 15%), chuẩn hoá về 100%.
- Ngưỡng 34% cho "cận mặt" tương đương **cả đầu chiếm ~50% khung** vì hộp mặt
  SCRFD chỉ tính từ lông mày tới cằm (không gồm trán/tóc). Nếu hiểu "mặt" là hộp
  mặt thuần thì ngưỡng phải là ~0.45–0.50, khi đó nguồn hiện tại gần như không có
  ảnh cận.

