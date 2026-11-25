# ao_ma — tải video từ web & lọc ảnh dựng dataset LoRA

Hai công cụ chính, đều nằm trong `luyen_co/`:

| Công cụ | Việc | File | Đầu ra |
|---|---|---|---|
| **Web down video** | Tải video/ảnh từ link (YouTube, TikTok, Facebook, Instagram, trang có `.mp4`/`.m3u8`) | `luyen_co/download_ui.py` | `downloads/` |
| **Tool filter ảnh** | Lọc ảnh đạt chuẩn (kích thước, nén, nét, đúng người, khung hình, đa dạng) và chép ra thư mục train | `luyen_co/filter_dataset.py` | `flter/` hoặc `train_*/images/` |

Luồng đầy đủ:

```
link web ──download_ui.py──► downloads/ ──(luyen_co.py: cắt frame, tuỳ chọn)──► crops/
                                                                                  │
                                          filter_dataset.py ◄──────────────────────┘
                                                    │
                                          train_*/images/  ──►  train LoRA
```

## Cấu trúc repo

```
luyen_co/            # pipeline + 2 công cụ (branch feat/luyen_co)
  download_ui.py     # 1. web down video
  filter_dataset.py  # 2. tool filter ảnh
  luyen_co.py        # (tuỳ chọn) cắt frame của một người từ video/ảnh theo ảnh tham chiếu
  filter_requirements.md   # tiêu chuẩn lọc ảnh chi tiết
  README.md          # tài liệu sâu của pipeline cắt frame
  docs/              # ghi chú thiết kế, handoff
pre_upscale_phase/   # (branch feat/pre_upscale_phase) chuẩn bị DVD trước khi upscale
```

---

# 0. Cài đặt (một lần)

```powershell
cd luyen_co
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt           # opencv, numpy, onnxruntime-directml, av
pip install -r requirements-ui.txt        # yt-dlp — chỉ cần cho download_ui.py
```

- Python 3.12, Windows. Chạy được trên CPU; có GPU DX12 thì nhanh hơn nhiều
  (`onnxruntime-directml` là mặc định trong `requirements.txt`).
- Model ONNX nằm ở `luyen_co/models/`, tự tải lần đầu chạy pipeline (~640 MB).
  `filter_dataset.py` dùng lại chính các model đó (`core/scrfd.py`, `core/arcface.py`,
  `core/reid.py`, `core/yolo_pose.py`).

---

# 1. Web down video

## Chạy

```powershell
cd luyen_co
.venv\Scripts\python.exe download_ui.py
```

Mở **http://127.0.0.1:8765** (tự mở trình duyệt).

| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `--host` | `127.0.0.1` | địa chỉ lắng nghe |
| `--port` | `8765` | cổng |
| `--out` | `downloads` | thư mục lưu file tải về |
| `--max-height` | `1080` | cạnh ngắn tối đa (video dọc vẫn đúng chiều) |
| `--no-browser` | — | không tự mở trình duyệt |

Ví dụ:

```powershell
.venv\Scripts\python.exe download_ui.py --port 9000 --out D:\cctv_test --no-browser
```

## Dùng trên giao diện

1. Dán link vào ô **URLs** — mỗi dòng một link, dán được cả chục link một lúc.
2. Chọn **chất lượng** (cạnh ngắn tối đa).
3. Link cần đăng nhập (Facebook/Instagram riêng tư) thì chọn **cookie trình duyệt**
   (`chrome` / `edge` / `firefox`) hoặc trỏ tới file `cookies.txt` (định dạng Netscape).
4. Bấm tải; danh sách job hiện tiến độ, file về nằm trong `--out`.

**Nhận được:**

- YouTube, TikTok, Facebook, Instagram (cả reel video **và** post ảnh / carousel).
- Trang bất kỳ có thẻ `<video>`, link `.mp4` hoặc `.m3u8` trực tiếp.
- Cách làm: ưu tiên `yt-dlp`; nếu yt-dlp không hỗ trợ trang đó thì tự bóc link media
  trong HTML rồi tải trực tiếp.

**Lưu ý**

- `yt-dlp` lỗi "Unsupported URL" với trang mới → `pip install -U yt-dlp`.
- Tải hàng loạt dễ bị chặn tạm thời; nghỉ một lúc rồi tải tiếp.
- Chỉ tải nội dung bạn có quyền sử dụng.

## Tiếp theo

- File tải về là **ảnh** → đưa thẳng vào tool filter (mục 2).
- Là **video** và cần cắt frame của một người cụ thể → chạy `luyen_co.py`
  (xem `luyen_co/README.md`), rồi lọc `crops/` bằng tool filter.

---

# 2. Tool filter ảnh

## Chạy nhanh

```powershell
cd luyen_co
.venv\Scripts\python.exe -X utf8 filter_dataset.py `
  --src F:\pic\phuong_mai `
  --dst output\train_pm_4lop\images --report-dir output\train_pm_4lop `
  --ref sample\obj_1\main.jpg --min-face-sim 0.38 `
  --workflow max-fill --min-jpeg-quality 85 --clean
```

- `--src` nhận **nhiều thư mục** (lọc chung một bộ, lọc trùng xuyên nguồn luôn).
- `--dst` chỉ chứa ảnh; báo cáo để ở `--report-dir` (đừng để chung thư mục ảnh).
- Video trong `--src` bị **bỏ qua** tự động.
- Lần đầu ~2–4 phút cho 500 ảnh; các lần sau có cache, đổi ngưỡng chỉ ~20–40 giây.

## Nó kiểm gì

| Cổng | Ngưỡng mặc định | Đo bằng |
|---|---|---|
| Cạnh ngắn | ≥ 768px (mục tiêu 1024) | kích thước file |
| Chất lượng JPEG | ≥ 85 | bảng nén trong header, **không giải mã ảnh** |
| Có mặt, mặt đủ lớn | mặt ≥ 80px, cách mép ≥ 1.2% cạnh ngắn | SCRFD |
| Đúng người | ArcFace cosine ≥ 0.38 với `--ref` | ArcFace R50 |
| Không có người khác | mặt khác < 22% mặt chính, người khác < 30% | SCRFD + YOLO |
| Độ nét | Laplacian mặt 112×112 ≥ 55, cả ảnh ≥ 40 | OpenCV |
| Độ sáng | TB vùng mặt 62–212, lệch chuẩn ≥ 14 | OpenCV |
| Không cắt sát | mặt ≤ 75% chiều cao khung | SCRFD |
| Không trùng | MD5 + dHash 64 bit (kể cả ảnh lật), ngưỡng 6 | numpy |

Thêm 3 trần đa dạng: tối đa 3 ảnh/cụm look (CLIP ≥ 0.88), 12%/nguồn, 2 ảnh/10 giây.

## Chia khung hình (4 lớp)

| Lớp | Cách xác định | Dải tỉ lệ mục tiêu |
|---|---|---|
| Cận mặt | chiều cao mặt / chiều cao ảnh ≥ **0.34** | 20–35% |
| Ngang vai, ngực | ≥ **0.20** | 30–45% |
| Ngang eo | < 0.20 và số "đầu" từ cằm xuống đáy < **4.5** | 15–30% |
| Toàn thân | số "đầu" từ cằm xuống đáy ≥ 4.5 | 10–20% |

Chỉnh ngưỡng: `--close-frac`, `--chest-frac`, `--waist-extent`.

## Hai workflow chọn ảnh

| Workflow | Cách chạy | Kết quả |
|---|---|---|
| `max-fill` *(khuyến nghị)* | `--workflow max-fill` | Lấy **hết** ảnh cận + ngang vai đạt cổng, rồi bù ngang eo + toàn thân cho đủ dải tỉ lệ. Ảnh bù được chọn greedy, bị trừ điểm nếu trùng look hoặc dồn một nhóm góc |
| `ratio` | `--workflow ratio --target-close 0.40` | Ép đúng một tỉ lệ cận mặt cố định, cắt bớt ảnh vai/eo. Có thể cắt thêm ảnh cận từ ảnh gốc bằng `--face-crops` |

## Đầu ra

```
output\train_pm_4lop\
├── images\              ← ảnh đạt (JPEG RGB), trỏ thẳng vào đây khi train
├── filter_report.csv    ← mọi số đo từng ảnh + lý do loại
├── filter_summary.txt   ← báo cáo tổng: tỉ lệ, góc, nguồn, chất lượng JPEG
├── sheet_flter_*.jpg    ← contact sheet để soi mắt
├── sheet_facecrop_*.jpg ← nếu bật --face-crops
└── filter_cache.json    ← cache số đo, xoá đi nếu muốn đo lại từ đầu
```

Cột đáng chú ý trong `filter_report.csv`: `short_side`, `jpeg_q`, `face_sim`,
`face_frac`, `extent`, `sharp_face`, `lum_face`, `class`, `score`, `reason`.

## Lệnh hay dùng

```powershell
# Chỉ đo, không chép ảnh (xem phân bố trước khi chọn ngưỡng)
.venv\Scripts\python.exe -X utf8 filter_dataset.py `
  --src D:\anh --dst out --analyze-only

# Lọc nhiều nguồn thành một bộ
.venv\Scripts\python.exe -X utf8 filter_dataset.py `
  --src F:\pic\phuong_mai F:\pic\me_lan `
  --dst output\train\images --report-dir output\train `
  --ref sample\obj_1\main.jpg --workflow max-fill

# Bỏ vài ảnh đã soi thấy lỗi (kính râm, watermark, tóc che mặt…)
.venv\Scripts\python.exe -X utf8 filter_dataset.py `
  --src F:\pic\phuong_mai --dst output\train\images --report-dir output\train `
  --ref sample\obj_1\main.jpg --skip-list output\train\skip.txt

# Nới chất lượng nếu nguồn bị nén lại (mặc định 85)
.venv\Scripts\python.exe -X utf8 filter_dataset.py `
  --src F:\pic\phuong_mai --dst output\train\images --report-dir output\train `
  --min-jpeg-quality 80

# Không có ảnh tham chiếu thì bỏ --ref (tắt cổng "đúng người")
```

## Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách sửa |
|---|---|
| 0 ảnh đạt | soi `filter_report.csv` cột `reason`; thường do `jpeg_quality` hoặc `small` — hạ `--min-jpeg-quality` / `--min-side` |
| Ảnh "đạt" mà trông lệch | đổi ngưỡng phân loại khung hình, rồi soi lại `sheet_flter_*.jpg` |
| Sửa ngưỡng mà kết quả không đổi | xoá `filter_cache.json` hoặc thêm `--no-cache` |
| Chậm | thêm `--no-persons` (bỏ YOLO), hoặc `--device cpu` nếu DirectML lỗi |
| Lẫn ảnh người khác | hạ `--min-face-sim`? **không** — tăng lên (0.45) và kiểm bằng sheet |

Tiêu chuẩn chi tiết + nhật ký thay đổi: [`luyen_co/filter_requirements.md`](luyen_co/filter_requirements.md).
Tài liệu pipeline cắt frame: [`luyen_co/README.md`](luyen_co/README.md).
