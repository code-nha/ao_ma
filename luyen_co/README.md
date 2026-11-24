# luyen_co

Lọc ra **đúng những frame có một người cụ thể** trong folder ảnh + video (CCTV),
ưu tiên giữ các frame có **góc mặt và dáng đa dạng nhất**, xuất thành ảnh crop
sẵn để đưa vào dataset (train LoRA nhân vật, dựng bộ ảnh chân dung…).

- **Đầu vào:** 1 folder chứa ảnh và/hoặc video, + 1 ảnh tham chiếu rõ nhất của
  người cần tìm.
- **Đầu ra:** `crops/` (**mặc định là nguyên frame** — giữ bối cảnh để biết người
  đó ở đâu, truy ra camera nào; `--save both` để có thêm ảnh crop quanh người),
  `metadata.jsonl` (nguồn, giây, bbox, điểm khớp, góc đầu, pose), `report.csv`,
  `summary.txt`, `sheet.jpg` (bảng ảnh xem nhanh).

## Cách hoạt động

| Bước | Model | Việc làm |
|---|---|---|
| Phát hiện người + pose | YOLOv8n-pose (ONNX) | bbox người + 17 keypoint |
| Phát hiện mặt | SCRFD 10G (`buffalo_l`) | bbox + 5 landmark, chạy trên vùng crop người nên bắt được mặt nhỏ |
| Danh tính khuôn mặt | ArcFace R50 (`buffalo_l`) | vector 512 chiều, cosine với mặt trong ảnh tham chiếu |
| Ngoại hình toàn thân | CLIP ViT-B/32 vision (ONNX) | vector 512 chiều, so khớp khi mặt bị che/quay lưng, đồng thời đo độ đa dạng |
| Liên kết theo thời gian | IoU + khoảng cách tâm (numpy) | gán track, tự cắt track khi đổi cảnh |

**Quyết định nhận frame** (theo từng frame, không nhận cả track):

1. Frame thấy mặt và `face_sim ≥ --face-th` → nhận.
2. Frame **không** thấy mặt chỉ được nhận khi track đó đã có ít nhất 1 frame khớp
   mặt, **và** `body_sim ≥ --body-th`.
3. Track không có frame nào khớp mặt bị bỏ, trừ khi bật `--allow-body-only`
   (khi đó cần track ≥ `--min-track` frame và trung vị `body_sim ≥ --body-th`).
   Dùng cờ này khi CCTV không bao giờ thấy mặt người mục tiêu — đổi lại dễ nhầm
   người mặc giống nhau: đo thực tế trên clip văn phòng, người mặc áo xanh vẫn
   bị lẫn với một người mặc áo đen đi qua cùng lối. `--color-th` chỉ lọc được
   người khác màu áo rõ rệt.
4. **Quay lưng sau khi camera đã xác nhận mặt**: mỗi video có một "neo" ngoại
   hình lấy từ track đã khớp mặt (trung bình vector CLIP của track đó). Các
   track sau không thấy mặt vẫn được nhận nếu cosine với neo ≥ `--anchor-th`
   (0.60). Nhờ vậy lấy được ảnh sau lưng/dáng đi kể cả khi ảnh tham chiếu mặc
   trang phục khác. `--confirm-window` (mặc định 0 = không giới hạn) đặt giới
   hạn thời gian nếu muốn chặt hơn.
5. Ảnh tham chiếu không có mặt → buộc phải dựa vào toàn thân, khuyến nghị nâng
   `--body-th`.

Sau khi lọc trùng, ảnh được chọn theo `--select`:

- `coverage` (mặc định): nhóm theo **(nguồn, cảnh, góc mặt)** — thẳng / trái /
  phải / trái nhiều / phải nhiều / **sau lưng** (frame không thấy mặt hoặc mặt
  khớp yếu) — mỗi nhóm giữ ảnh chất lượng nhất, rồi thêm các ảnh **khác biệt
  nhất** với ảnh đã giữ (tối đa `--per-bucket`, mặc định 2). Nhờ vậy frame quay
  lưng ở xa/nhỏ vẫn được lấy nếu nó là tư thế khác, không bị ảnh gần-đẹp hơn
  "đè" mất.
- `diversity`: chỉ giữ frame khác quá ngưỡng `--min-yaw` / `--min-pose`.

Trước khi ghi ảnh còn một bước **lọc đa dạng**: một frame bị bỏ nếu **vừa** gần
góc đầu (`< --min-yaw` độ) **vừa** gần dáng (`< --min-pose`) so với frame đã giữ
trong cùng nguồn. Mục đích không phải lấy thật nhiều ảnh, mà lấy **vài ảnh khác
nhau làm bằng chứng nhận dạng** (thẳng / trái / phải / nghiêng / quay lưng /
toàn thân ở xa). Đặt `--min-yaw 0 --min-pose 0` để tắt.

Sau đó mới lọc trùng (`--dup-sim`, `--min-gap`) và tuỳ chọn `--limit N` (greedy
farthest-point trên vector [góc đầu, 17 keypoint, CLIP]).

## Cài đặt

Windows + GPU rời (DirectML, **không cần** cài CUDA/cuDNN):

```powershell
uv venv luyen_co\.venv --python 3.12
uv pip install --python luyen_co\.venv\Scripts\python.exe -r luyen_co\requirements.txt
```

Máy Linux hoặc đã có CUDA 12: thay `onnxruntime-directml` bằng
`onnxruntime-gpu` trong `requirements.txt` — code tự chọn provider theo thứ tự
CUDA → DirectML → CPU.

Lần chạy đầu tự tải model (~640 MB) vào `luyen_co/models/`:
`yolov8n-pose.onnx`, `clip_vision.onnx`, `buffalo_l.zip`
(SCRFD `det_10g.onnx` + ArcFace `w600k_r50.onnx`).

## Dùng

```powershell
# quét cả folder, mỗi giây lấy 2 frame
python luyen_co.py --input "D:\cctv\cam_01" --ref "D:\ref\chi_ay.jpg" --out out_chi_ay

# chỉ 200 ảnh đa dạng nhất
python luyen_co.py --input D:\cctv --ref ref.jpg --limit 200

# kiểm tra ảnh tham chiếu trước khi quét (kích thước mặt, độ nét, cảnh báo)
python luyen_co.py --input D:\cctv --ref ref.jpg --check

# quét thử 1 phút đầu, 5 frame/giây
python luyen_co.py --input D:\cctv --ref ref.jpg --end 60 --fps 5
```

Tham số đáng chú ý:

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--fps` | 2 | số frame lấy mỗi giây; CCTV người đi bộ 1–2 là đủ, cần nhiều dáng hơn thì 3–5 |
| `--face-th` | 0.45 | cosine ArcFace tối thiểu; máy ảnh mờ/nén mạnh có thể hạ 0.35–0.40 |
| `--body-th` | 0.72 | cosine CLIP toàn thân; chỉ dùng khi không thấy mặt |
| `--color-th` | 0.3 | tương quan màu áo/quần tối thiểu khi so toàn thân (0 = tắt) |
| `--min-person` | 64 | chiều cao người tối thiểu (px) — bỏ người quá nhỏ, không dùng được |
| `--min-blur` | 25 | phương sai Laplacian tối thiểu — bỏ frame nhoè |
| `--min-person-score` | 0.5 | ngưỡng tin cậy detection người — tăng để bớt vật thể giống người |
| `--max-overlap` | 0.35 | bỏ frame có người khác chồng lên người mục tiêu quá IoU này |
| `--max-other-area` | 0.10 | bỏ frame mà người khác chiếm quá 10% diện tích crop (giữ đúng "1 ảnh 1 người") |
| `--dup-sim` | 0.97 | cosine coi là trùng hẳn |
| `--min-gap` | 0.35 | giây tối thiểu giữa 2 ảnh cùng track |
| `--save` | full | `full` = nguyên frame (có bối cảnh), `crop` = chỉ quanh người, `both` = cả hai |
| `--min-yaw` | 20 | chênh góc đầu tối thiểu (độ) để giữ thêm ảnh |
| `--min-pose` | 0.10 | chênh dáng (keypoint chuẩn hoá) tối thiểu để giữ thêm ảnh; 0 = tắt lọc đa dạng |
| `--confirm-window` | 0 | giới hạn giây tới mốc đã khớp mặt khi nhận frame quay lưng (0 = không giới hạn) |
| `--anchor-th` | 0.60 | cosine tối thiểu với neo ngoại hình của video |
| `--select` | coverage | `coverage` = đủ góc mỗi cảnh; `diversity` = theo ngưỡng yaw/pose |
| `--per-bucket` | 2 | số ảnh tối đa cho mỗi nhóm góc (khi `--select coverage`) |
| `--limit` | 0 | 0 = giữ hết sau lọc trùng; >0 = chọn N ảnh đa dạng nhất |
| `--tiles` | 1 | chia frame thành lưới tiles×tiles trước khi detect; dùng cho CCTV 4K/góc rộng có người rất nhỏ |
| `--allow-body-only` | tắt | nhận track không hề khớp mặt, chỉ dựa vào toàn thân |
| `--clean` | tắt | xoá ảnh cũ trong `<out>/crops` trước khi ghi kết quả mới |
| `--include-ref` | tắt | vẫn xử lý ảnh tham chiếu nếu nó nằm trong folder quét |
| `--device` | auto | `auto` / `gpu` / `cpu` |

## Chỉnh ngưỡng

Chạy một lượt với mặc định, mở `summary.txt` xem phân bố `face_sim` /
`body_sim` theo track và độ phủ góc đầu. Trong đó có sẵn bảng **ước lượng số
frame thô nhận được ở từng mức `--face-th` (0.30 → 0.55)**, tính từ chính dữ
liệu vừa quét — nên chọn ngưỡng không cần chạy lại video:

- Có track đúng người nhưng `face_sim` thấp (0.3–0.45) → hạ `--face-th` xuống
  ngay dưới mức đó.
- Có ảnh người khác lọt vào → tăng `--face-th` / `--body-th`, hoặc tăng
  `--min-person-score`, `--min-blur`.
- Ra 0 ảnh nhưng người mục tiêu có trong video (CCTV chỉ quay lưng) → bật
  `--allow-body-only`, nâng `--body-th` dần (0.75 → 0.8) và soát `sheet.jpg`.
- Ảnh ra quá ít → giảm `--min-blur`, `--min-person`, tăng `--fps`.
- Ảnh ra quá nhiều bản gần giống → tăng `--min-gap`, giảm `--dup-sim`
  (vd. 0.95), hoặc dùng `--limit`.

`sheet.jpg` là cách nhanh nhất để kiểm tra bằng mắt: nếu toàn ảnh đúng người và
góc đầu trải từ trái sang phải thì cấu hình đã ổn.

### Gợi ý ngưỡng theo chất lượng nguồn

Đo trên clip phim bị hạ xuống 360p, H.265 crf 30 (mô phỏng CCTV nén mạnh):
`face_sim` tụt còn 0,26–0,81 (đa số 0,3–0,45) trong khi bản gốc 720p là 0,6–0,98.

| Nguồn | Gợi ý |
|---|---|
| 1080p trở lên, nét | mặc định (`--face-th 0.45 --min-person 64 --min-blur 25`) |
| 720p, nén vừa | `--face-th 0.40 --min-person 50` |
| ≤ 360p hoặc nén mạnh | `--face-th 0.35 --min-person 40 --min-blur 15` |
| Camera hồng ngoại / đen trắng | hạ thêm ~0.05 so với bảng trên (đo thực tế: `face_sim` 0.59 so với 0.98 bản màu) |
| Chỉ thấy lưng, không bao giờ thấy mặt | thêm `--allow-body-only --body-th 0.78` |
| Đám đông, cần nhiều ảnh hơn | nâng `--max-other-area` lên 0.2–0.3 (đổi lại crop có thể dính người bên cạnh) |

Luôn soát `sheet.jpg` sau khi hạ ngưỡng: hạ quá tay sẽ bắt đầu lẫn người khác.

## Kiểm thử

Đã chạy thật trên 2 clip phim 60 s (1 clip một người, 1 clip đông người) dùng
chính frame phim làm ảnh tham chiếu:

| Ca | Kết quả |
|---|---|
| Clip 60 s, ref = mặt nhân vật nữ | 121 frame → 16 track → 19 ảnh, đúng người, yaw trải +31°…−90° |
| Clip đông người (3–7 người/frame) | 16 ảnh, crop đúng nhân vật trong đám đông, không lẫn người khác |
| Ref phim A quét cả phim A + phim B | 16 ảnh đều của phim A, **0 ảnh** từ phim B |
| 2 bản upload khác nhau của cùng bài diễn văn (480p), cùng folder có clip đám đông | 112 ảnh đúng người (mặt 0,47–0,55 vì ref chỉ 57 px), **0 ảnh** từ clip đám đông; `--limit 24` ra bộ 24 ảnh trải đều 2 video |
| Clip CCTV văn phòng 1080p tải từ YouTube, ref là người mặc áo xanh (không thấy mặt) | body-only bám đúng người đi bộ 2,5–37 s; loại được người mặc áo vàng nhờ `--color-th`; **lẫn một người khác mặc đồ tối** ở 51–58 s (giới hạn của so khớp toàn thân) |
| Folder rỗng / video hỏng / ảnh hỏng | báo lỗi hoặc bỏ qua, không crash |
| Đường dẫn có dấu tiếng Việt + `--recursive` | chạy đúng |
| Ref không có mặt (chỉ thân) | cảnh báo, tự chuyển sang so khớp toàn thân |
| Ảnh lẻ trong folder | nhận/loại theo cùng ngưỡng với video |

Tốc độ đo trên clip đông người: ~0,05 s/frame khi 1–2 người, ~0,11 s/frame khi
3–7 người (RTX 2070 Max-Q, DirectML, 1280×720).

### Người rất nhỏ trong khung lớn (`--tiles`)

Khung 4K thu cả frame về 640 px thì người 1–2 m chỉ còn 30–50 px, YOLO bỏ sót.
`--tiles N` chia frame thành lưới N×N (chồng lấn 20%) để giữ chi tiết. Đo trên
khung 3840×2160 với người dán ở nhiều kích thước:

| Người cao | tiles=1 | tiles=2 | tiles=4 |
|---|---|---|---|
| 110 px | 0 | 0 | **1** |
| 160 px | 0 | **1** | **1** |
| 220 px | 0 | **1** | **1** |

Đổi lại chậm hơn N² lần. Chỉ dùng khi khung ≥ 1080p và người nhỏ; với video
480p–720p người thường đã đủ to, bật tiles sẽ cắt người qua nhiều ô và làm
detection tệ đi.

Có test cho phần logic thuần (không cần model/GPU):

```powershell
uv pip install --python luyen_co\.venv\Scripts\python.exe pytest
luyen_co\.venv\Scripts\python.exe -m pytest luyen_co\tests -q
```

## Hiệu năng (RTX 2070 Max-Q, DirectML)

| Model | DirectML | CPU |
|---|---|---|
| YOLOv8n-pose 640² | ~17 ms | ~60 ms |
| SCRFD 640² | ~27 ms | ~121 ms |
| ArcFace 112² | ~14 ms | ~107 ms |
| CLIP 224² | ~20 ms | ~56 ms |

Thực tế ~0,05 s/frame khi có 1–2 người (đã gồm giải mã video) → 1 giờ CCTV ở
2 fps (7200 frame) mất khoảng 6–8 phút. CPU chậm hơn ~3–8 lần.

## Giới hạn & lưu ý

- **Mặt nhỏ / nhoè**: CCTV góc rộng, người cách xa >10 m thường chỉ còn 20–30 px
  mặt. ArcFace vẫn có thể khớp nhưng điểm sẽ thấp; khi đó toàn thân là cứu cánh
  và `--body-th` cần chỉnh theo dữ liệu thật.
- **Đổi quần áo trong cùng video**: CLIP toàn thân sẽ trượt; ưu tiên mặt.
- **Nhiều người mặc giống nhau** (đồng phục): body-only dễ nhầm — nên giữ
  `--face-th` và kiểm tra `sheet.jpg`.
- **Góc đầu** là ước lượng từ 5 landmark (không phải số đo chính xác), đủ để
  phân loại trái/thẳng/phải/cúi/ngửa và để chọn bộ ảnh đa dạng.
- **Cảnh cắt** được phát hiện bằng histogram + sai khác điểm ảnh; phim cắt nhanh
  có thể vẫn lọt, nhưng vì quyết định theo từng frame nên ít ảnh hưởng.
- **Folder có nhiều bản encode của cùng một video** (vd. `.raw` + `.ivtc`): ảnh sẽ
  lặp giữa các file vì lọc trùng chỉ chạy trong từng file nguồn — chỉ đưa một bản
  vào folder quét, hoặc lọc theo tên trước.
- **Video rất dài**: ảnh nhận được ghi ngay ra `<out>/.staging/` rồi mới chuyển
  vào `crops/`, nên RAM chỉ giữ metadata (~2 KB/frame); 8 giờ CCTV không bị phình
  bộ nhớ.
- Ảnh crop giữ nguyên độ phân giải gốc của nguồn, không upscale.

## Kiếm dữ liệu test từ web

`download_ui.py` là web UI nhỏ để tải clip từ YouTube / TikTok / Facebook /
Instagram / trang web có `<video>` về máy:

```powershell
uv pip install --python luyen_co\.venv\Scripts\python.exe -r luyen_co\requirements-ui.txt
python luyen_co\download_ui.py --out luyen_co\downloads      # mở http://127.0.0.1:8765
```

- dán nhiều link một lúc (mỗi dòng một link); video cần đăng nhập thì dùng
  cookie trình duyệt **hoặc** dán đường dẫn `cookies.txt` (Netscape) export từ
  extension — cách sau vẫn dùng được khi trình duyệt đang mở
- **Facebook Stories (`facebook.com/stories/...`) không tải được**: yt-dlp chỉ có
  extractor cho `/video/`, `/reel/`, `/watch`, `story.php`, và story thì bắt
  đăng nhập. Cách chắc ăn: mở story trên Chrome → F12 → tab Network → lọc
  `media`/`mp4` → copy URL CDN → dán vào ô link của UI này (tải trực tiếp)
- tải bằng yt-dlp, **ưu tiên H.264 + AAC** và `-movflags +faststart` — tránh combo
  AV1/VP9 + Opus trong MP4 làm VLC nháy/khựng vài giây đầu khi mở file
- **deno**: nếu máy có deno (kể cả cài bằng winget mà chưa vào PATH), tool tự dò
  và bật `js_runtimes` + `remote_components=ejs:github` để YouTube trả đủ format
  (đo thực tế: 45 format, H.264 tới 1080p). Thiếu deno thì chỉ thiếu format, vẫn tải được.
- file cũ tải bằng bản trước (AV1/VP9) thì tick **"tải lại/ghi đè"** để lấy bản
  H.264; mã codec hiện ngay cạnh tiến độ từng job
- trang lạ thì tự bóc link `.mp4 / .m3u8` trong HTML và fallback sang ffmpeg cho HLS
- xem tiến độ / tốc độ / lỗi ngay trên trang, có nút mở thư mục
- xong thì trỏ pipeline vào chính folder đó:
  `python luyen_co.py --input luyen_co\downloads --ref anh.jpg`

## Cấu trúc

```
luyen_co/
  luyen_co.py        CLI
  download_ui.py     web UI tải video test từ URL (yt-dlp)
  core/
    onnx_models.py   tải model + chọn execution provider
    yolo_pose.py     phát hiện người + keypoint (có --tiles)
    scrfd.py         phát hiện mặt
    arcface.py       embedding mặt
    reid.py          embedding toàn thân (CLIP)
    tracker.py       gán track theo thời gian
    frames.py        đọc frame video / ảnh
    select.py        góc đầu, pose, lọc trùng, chọn đa dạng
    pipeline.py      ghép các bước + xuất kết quả
  tests/             pytest cho phần logic thuần
  models/            model ONNX (tự tải, gitignore)
  downloads/         video tải từ web UI (gitignore)
```
