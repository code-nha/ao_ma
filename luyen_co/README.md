# luyen_co

Lọc ra **đúng những frame có một người cụ thể** trong folder ảnh + video (CCTV),
ưu tiên giữ các frame có **góc mặt và dáng đa dạng nhất**, xuất thành ảnh crop
sẵn để đưa vào dataset (train LoRA nhân vật, dựng bộ ảnh chân dung…).

- **Đầu vào:** 1 folder chứa ảnh và/hoặc video, + **một hoặc nhiều ảnh tham chiếu**
  (có thể trỏ vào folder ảnh). Mỗi frame được so với **cả bộ tham chiếu, lấy điểm
  cao nhất** — đúng thực tế: một người có thể xuất hiện nhiều lần, nhiều năm,
  nhiều trang phục/góc khác nhau trong cùng khu vực.
- **Đầu ra:** `crops/` (**mặc định là nguyên frame** — giữ bối cảnh để biết người
  đó ở đâu, truy ra camera nào; `--save both` để có thêm ảnh crop quanh người),
  `metadata.jsonl` (nguồn, giây, bbox, điểm khớp, góc đầu, cỡ cảnh, pose), `report.csv`,
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
   mặt, **và** ngoại hình khớp "neo" của video (`≥ --anchor-th`) **hoặc**
   `body_sim ≥ --body-th`.
3. Track không có frame nào khớp mặt bị bỏ, trừ khi bật `--allow-body-only`
   (khi đó cần track ≥ `--min-track` frame và `body_sim ≥ --body-only-low`,
   mặc định 0.45). Ảnh quay lưng so với ảnh tham chiếu nhìn thẳng chỉ đạt cosine
   CLIP 0.55–0.65, nên **không** dùng `--body-th` 0.72 cho đường này.
   Dùng cờ này khi CCTV không bao giờ thấy mặt người mục tiêu — đổi lại dễ nhầm
   người mặc giống nhau: đo thực tế trên clip văn phòng, người mặc áo xanh vẫn
   bị lẫn với một người mặc áo đen đi qua cùng lối. `--color-th` chỉ lọc được
   người khác màu áo rõ rệt.
   - Nếu **không track nào** khớp mặt, bước xuất so **tương đối**: track có trung
     vị `body_sim` cao nhất là người mục tiêu, giữ các track
     `≥ --body-only-rel × mức tốt nhất` (mặc định 0.85) và ≥ `--body-only-low`.
     Nhờ vậy clip chỉ quay từ sau vẫn ra ảnh thay vì 0 ảnh.
4. **Quay lưng sau khi camera đã xác nhận mặt**: mỗi video có một "neo" ngoại
   hình, cập nhật **ngay theo từng frame** khớp mặt (trung bình dần vector CLIP)
   thay vì đợi track kết thúc — nhờ vậy frame không mặt ở đầu video hoặc ngay
   sau cắt cảnh vẫn có neo để so. Các track sau không thấy mặt vẫn được nhận nếu
   cosine với neo ≥ `--anchor-th` (0.60). Nhờ vậy lấy được ảnh sau lưng/dáng đi
   kể cả khi ảnh tham chiếu mặc trang phục khác. `--confirm-window` (mặc định
   0 = không giới hạn) đặt giới hạn thời gian nếu muốn chặt hơn.
5. Ảnh tham chiếu không có mặt → buộc phải dựa vào toàn thân, dùng cùng đường
   body-only ở mục 3.

Sau khi lọc trùng, ảnh được chọn theo `--select`:

- `coverage` (mặc định): nhóm theo **(nguồn, cảnh, góc)** — thẳng / trái / phải /
  trái nhiều / phải nhiều / **ngửa** / **cúi** / **nghiêng** / **sau lưng 3/4** /
  **sau lưng** / **không rõ mặt** — mỗi nhóm giữ ảnh chất lượng nhất, rồi thêm ảnh
  **khác biệt nhất** nếu `--per-bucket` > 1.
  - **sau lưng**: phần mặt bị khuất — `face_vis` (trung bình conf **mũi + 2 mắt**)
    < 0.60, trong khi vai > 0.45 và tai ≥ 0.25 (tai còn thấy nghĩa là keypoint
    đầu là thật, không phải model đoán bừa). Đo trên v1.mp4: frame quay lưng có
    `face_vis` 0.18–0.43, frame nhìn thẳng 0.73–0.97 — khoảng trống rộng nên
    cùng một đoạn đi bộ quay lưng không bị lật nhãn. (Cách cũ chỉ so conf **mũi**
    < 0.5: mũi nhảy 0.31 → 0.58 giữa hai frame liền nhau là nhãn lật ngay.)
  - **sau lưng 3/4**: cùng điều kiện trên nhưng `face_vis` 0.50–0.60 — mặt khuất
    một nửa, hướng cổ/vai khác hẳn ảnh chụp chính sau. Tách ra để ảnh 3/4 sau
    không bị ảnh chính sau đè mất suất.
  - **nghiêng**: yaw ≥ 70° (khi có mặt) hoặc vai/hông chồng nhau theo phương
    ngang (khi không có mặt) — bắt được cả ảnh hông/thân nghiêng ở xa.
  - **không rõ mặt**: không thấy mặt nhưng thân vẫn mở rộng (người ở xa, mặt
    quá nhỏ để SCRFD bắt). Nhóm này tách riêng khỏi "sau lưng".
  Nhờ tách 3 nhóm này, ảnh quay lưng **không còn bị ảnh nhìn thẳng ở xa chiếm
  mất suất** (lỗi trước đây: mọi frame không thấy mặt đều vào "sau lưng", xếp
  hạng theo `body_sim` nên frame xa, toàn thân giống tham chiếu hơn lại thắng).
  Trong nhóm không có điểm mặt, ảnh được xếp theo **kích thước người + độ nét**.
- `diversity`: chỉ giữ frame khác quá ngưỡng `--min-yaw` / `--min-pose`.

Sau bước chọn theo nhóm, cả 2 chế độ đều qua **lọc trùng ảnh** — đây là bước
quyết định "pose không bị lặp". Nguyên tắc: **3 trục đo độc lập**, hai ảnh chỉ bị
coi là trùng khi giống nhau ở **cả 3**:

| Trục | Đo bằng | Giống khi |
|---|---|---|
| cỡ cảnh | `shot_scale` (số "đầu" trong khung, cổ chân) | cùng mức |
| góc quay | `yaw`/`pitch` từ 5 landmark | `< --min-yaw`, hoặc cùng nhóm góc mà yaw không đo được (sau lưng / 3-4 sau / nghiêng / không rõ mặt) |
| dáng | **góc khớp** + toạ độ chuẩn hoá | `mean < --min-pose-deg` **và** `max < --min-pose-max-deg` **và** `< --min-pose` |

- **Dáng đo bằng góc khớp** (`pose_angles`, 11 góc: khuỷu, gối, nâng tay, dạng
  đùi × 2 bên, mở hai đùi, nghiêng thân, nghiêng vai). Góc **không phụ thuộc
  người to hay nhỏ trong khung**, nên trục "dáng" không lẫn với trục "cỡ cảnh".
  Đầu (mũi/mắt/tai) **không** dùng ở đây — hướng đầu là trục "góc quay".
- Góc nào có keypoint bị khuất (conf < 0.35) hoặc xương quá ngắn (< 10% chiều cao
  người, tức đang hướng vào camera) thì **bỏ góc đó** (nan) thay vì gán 0.5 như
  cách cũ — nhờ vậy keypoint thiếu không tạo ra "giống nhau giả tạo".
- Vì sao cần `--min-pose-max-deg`: trung bình 11 góc pha loãng ca "chỉ giơ một
  tay" (90°/11 ≈ 8°, lọt ngưỡng 20°) trong khi `max` bắt đúng 90°.
- **Gương**: dáng tay trái giơ lên và bản gương (tay phải giơ lên) được coi là
  **cùng dáng** (lấy min của 2 cách so) — không có bước này thì mỗi lần đổi bên
  là thêm một ảnh trùng ý nghĩa.
- Duyệt theo **chất lượng giảm dần**, giữ ảnh nếu nó khác mọi ảnh đã giữ —
  **không nối chuỗi**. Nối chuỗi (A≈B, B≈C ⇒ gộp cả A và C) làm sập cả một
  clip quay tay: 81 frame của clip bảo vệ chỉ còn 6 ảnh, trong khi duyệt tham
  lam giữ được 12–17 ảnh tuỳ ngưỡng.
- Trước bước đó còn lọc **frame người quá bé so với cùng cảnh** (< 20% chiều cao
  frame to nhất trong cảnh, khi cảnh đó có frame ≥ 400 px): ở 110 px keypoint
  nhiễu đến mức pose không so được, nên 2–3 tấm nhìn y hệt nhau vẫn lọt.
- `pitch` bị bỏ khỏi phép so góc khi `|yaw| ≥ 70°`, vì ở góc đó 5 landmark
  không đo được nữa (giá trị bị kẹp ±89) nên hiệu pitch chỉ là nhiễu.

Vì sao cần bước này: chọn theo nhóm chỉ giới hạn vài ảnh cho mỗi *(nguồn, cảnh,
nhóm góc)*, nên 5 frame catwalk liên tiếp với đầu quay ±29° vẫn vào 5 nhóm khác
nhau dù dáng gần như y hệt — đo trên obj_1, các frame 4.0/5.0/6.0/7.0/7.5 s chỉ
cách nhau 0.019–0.058 về pose. Với `--per-bucket 3` (mặc định) rồi lọc tư thế:
13 video của obj_1 ra **112 ảnh** (trước là 54), riêng clip bảo vệ quay tay
78 s ra **12 ảnh** (trước 5). Đặt `--min-yaw 0 --min-pose 0 --min-pose-deg 0` để tắt.

Kiểm chứng trên bộ 112 ảnh đó (đếm lại **mọi cặp cùng nguồn** bằng `pose_deg`
ghi trong `metadata.jsonl`): **0 cặp** còn vi phạm quy tắc 3 trục. Trước khi đổi
sang góc khớp, cùng phép đếm cho ra **47 cặp** trùng dáng + trùng góc + trùng cỡ
cảnh mà vẫn còn cả hai — tất cả là do `_pose_dist` (toạ độ chuẩn hoá theo bbox)
giữ lại oan.

Ảnh trùng giữa **hai video khác nhau** thì cố ý **không** gộp: khác nguồn, khác
ánh sáng/bối cảnh vẫn có ích cho dataset. Nếu muốn gộp cả liên-nguồn thì bỏ điều
kiện `k.source == c.source` trong `distinct_pose_pick`.

Sau đó mới lọc trùng (`--dup-sim`, `--min-gap`) và tuỳ chọn `--limit N` (greedy
farthest-point trên vector [góc đầu, 17 keypoint, CLIP]).

### Góc quay & cỡ cảnh

Bộ lọc đang đo **3 trục**, trong đó 2 trục dùng được:

| Trục | Đo bằng | Nhãn | Ghi chú |
|---|---|---|---|
| Ngang (yaw) | 5 landmark SCRFD | `thẳng` ±10°, `trái`/`phải` 10–25°, `trái nhiều`/`phải nhiều` 25–70°, `nghiêng` ≥ 70° | yaw bị kẹp ±90 nên không chia được 8 hướng đều |
| Dọc (pitch) | 5 landmark SCRFD | `ngửa` > 15°, `cúi` < −15° | |
| Cao độ máy | — | — | **không đo** (cần biết điểm tụ dọc; sai số lớn, không đáng) |
| Cỡ cảnh | px mặt + px người | 6 mức bên dưới | quyết định ảnh có ích cho LoRA hay không |

Cỡ cảnh (`shot` trong `metadata.jsonl`) — video nén không đọc được tiêu cự nên
"zoom" chỉ đo gián tiếp qua chủ thể chiếm bao nhiêu khung. Metric chính là
**số "đầu" trong khung** = `person_h / face_px` (thân người ≈ 7,5 đầu, bbox mặt
của SCRFD ≈ 0,78 đầu):

| Cỡ cảnh | Nhãn | `person_h / face_px` | Người thấy được |
|---|---|---|---|
| đặc tả | `ECU` | < 1.6 | mặt gần nửa khung |
| cận cảnh | `CU` | 1.6 – 2.6 | đầu + vai |
| trung cận | `MCU` | 2.6 – 3.8 | ngực trở lên |
| trung cảnh | `MS` | 3.8 – 5.8 | eo/hông trở lên |
| toàn thân | `FS` | 5.8 – 9.6 | đầu → bàn chân |
| viễn cảnh | `LS` | ≥ 9.6 | người lẫn cảnh |

Hai ngoại lệ được xét **trước** bảng trên:

1. **Thấy cổ chân** (conf keypoint 15/16 ≥ 0.5) → chắc chắn cả người trong khung:
   `toàn thân` nếu người ≥ 25% chiều cao khung, ngược lại `viễn cảnh`. Nhờ vậy
   người đứng sát máy, chân chạm mép khung vẫn là `toàn thân` chứ không bị đếm
   đầu xếp nhầm thành `cận cảnh`.
2. **Không thấy mặt** (`face_px = 0`, thường là ảnh quay lưng ở xa) → chỉ còn
   tỉ lệ người/khung: ≥ 0.85 `trung cận`, ≥ 0.50 `trung cảnh`, ≥ 0.25 `toàn thân`,
   còn lại `viễn cảnh`.

Không dùng `face_px / src_h` trực tiếp vì nó lẫn "máy quay gần" với "người to
trong khung": cùng khung 1280 px, mặt 190 px là trung cảnh nếu thấy cả người
nhưng là cận cảnh nếu người bị cắt ngang ngực. Ngưỡng hiệu chỉnh bằng cách soi
ảnh sát biên từng mức trên 112 ảnh obj_1.

- `--shot-per-bucket N` (mặc định 0 = tắt): giới hạn `N` ảnh cho mỗi ô
  **(nhóm góc × cỡ cảnh)**. Không có nó, cỡ cảnh dồn hết vào một mức: 112 ảnh
  obj_1 chia ra `MS` 41 / `FS` 46 / `MCU` 20 / `CU` 3 / `LS` 2 / **`ECU` 0**;
  bật `--shot-per-bucket 2` còn 45 ảnh với phân bố phẳng hơn (`FS` 18 / `MS` 13 /
  `MCU` 9 / `CU` 4 / `LS` 1).
- Bước này chỉ **bỏ bớt**, không tự sinh ra cỡ cảnh đang thiếu — `summary.txt`
  liệt kê mức đang trống, muốn có phải quay thêm nguồn gần hơn/xa hơn.

### Frame chuyển cảnh chồng mờ (bị "bóng ma")

Clip Facebook/TikTok hay chuyển cảnh bằng cross-dissolve: hai cảnh chồng mờ lên
nhau ~0.5–1.5 s. Frame ở giữa **không dùng được** (mặt thành 2 bóng, người thứ
hai hiện lên nửa vời) nhưng `--min-blur` **không bắt được**, vì hai ảnh nét chồng
lên nhau nên Laplacian của cả frame vẫn cao — đo trên clip `1750183430`, frame
hỏng ở 72.0 s có blur **2525**, frame sạch cùng cảnh 2677–4620.

Cách bắt: đo **độ nét vùng mặt** (Laplacian trên crop mặt 112×112). Mặt bị chồng
bóng thì nhoè hẳn: frame hỏng **23**, các frame sạch cùng clip **90–161**. Ngưỡng
so **tương đối** với trung vị của chính cảnh đó (`--face-sharp-ratio`, mặc định
0.35) nên không phụ thuộc mặt to/nhỏ.

- Khi bỏ, pipeline **không tự bịa ra ảnh khác**: nếu quanh đó có frame sạch thì
  frame đó vốn đã nằm trong tập ứng viên và sẽ được chọn bình thường; còn nếu
  cả cụm đều hỏng/đều bị người khác đứng cạnh thì mất đúng 1 suất — bỏ hẳn vẫn
  tốt hơn nhét ảnh bóng ma vào dataset.
- Đo trên obj_1: bỏ **5/598** frame, 112 → **110 ảnh** (mất 2 ảnh, không còn ảnh
  bóng ma nào).

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
| `--face-th` | 0.40 | cosine ArcFace tối thiểu; máy ảnh mờ/nén mạnh có thể hạ 0.30–0.35 |
| `--body-th` | 0.72 | cosine CLIP toàn thân; chỉ dùng khi không thấy mặt |
| `--color-th` | 0.3 | tương quan màu áo/quần tối thiểu khi so toàn thân (0 = tắt) |
| `--min-person` | 64 | chiều cao người tối thiểu (px) — bỏ người quá nhỏ, không dùng được |
| `--min-blur` | 25 | phương sai Laplacian tối thiểu — bỏ frame nhoè |
| `--face-sharp-ratio` | 0.35 | bỏ frame mà vùng **mặt** mờ dưới `ratio × trung vị cùng cảnh` — bắt frame chuyển cảnh chồng mờ (0 = tắt) |
| `--min-person-score` | 0.5 | ngưỡng tin cậy detection người — tăng để bớt vật thể giống người |
| `--max-overlap` | 0.35 | bỏ frame có người khác chồng lên người mục tiêu quá IoU này |
| `--max-other-area` | 0.10 | bỏ frame mà người khác chiếm quá 10% diện tích crop (giữ đúng "1 ảnh 1 người") |
| `--dup-sim` | 0.97 | cosine coi là trùng hẳn |
| `--min-gap` | 0.35 | giây tối thiểu giữa 2 ảnh cùng track |
| `--save` | full | `full` = nguyên frame (có bối cảnh), `crop` = chỉ quanh người, `both` = cả hai |
| `--min-yaw` | 25 | 2 ảnh lệch góc camera dưới mức này (độ) thì coi là cùng góc; phối với `--min-pose` để loại ảnh trùng tư thế |
| `--min-pose` | 0.08 | 2 ảnh lệch dáng dưới mức này (keypoint chuẩn hoá 0–1) thì coi là cùng dáng; 0 = tắt tầng này |
| `--min-pose-deg` | 20 | lệch **góc khớp** trung bình (độ) — ngưỡng chính của trục "dáng"; 0 = tắt tầng góc khớp |
| `--min-pose-max-deg` | 45 | một khớp lệch quá mức này (độ) là khác dáng, dù trung bình nhỏ (bắt ca "chỉ giơ một tay") |
| `--confirm-window` | 0 | giới hạn giây tới mốc đã khớp mặt khi nhận frame quay lưng (0 = không giới hạn) |
| `--anchor-th` | 0.60 | cosine tối thiểu với neo ngoại hình của video |
| `--select` | coverage | `coverage` = đủ góc mỗi cảnh; `diversity` = theo ngưỡng yaw/pose |
| `--per-bucket` | 3 | số ảnh tối đa cho mỗi nhóm góc (khi `--select coverage`); bước lọc trùng tư thế sau đó tỉa tiếp |
| `--shot-per-bucket` | 0 | >0: giới hạn số ảnh cho mỗi ô (nhóm góc × cỡ cảnh) để dataset không dồn vào một cỡ cảnh |
| `--limit` | 0 | 0 = giữ hết sau lọc trùng; >0 = chọn N ảnh đa dạng nhất |
| `--tiles` | 1 | chia frame thành lưới tiles×tiles trước khi detect; dùng cho CCTV 4K/góc rộng có người rất nhỏ |
| `--allow-body-only` | tắt | nhận track không hề khớp mặt, chỉ dựa vào toàn thân (dùng khi CCTV chỉ quay lưng) |
| `--body-only-low` | 0.45 | sàn `body_sim` cho frame nhận bằng toàn thân; ảnh lưng so với ref nhìn thẳng thường chỉ 0.55–0.65 nên đừng đặt cao hơn mức đó |
| `--body-only-rel` | 0.85 | khi không track nào khớp mặt: giữ track có `body_sim ≥ rel × track tốt nhất` (0.85 = giữ các track ngang mức tốt nhất) |
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
  `--allow-body-only` và **hạ** `--body-only-low` nếu vẫn 0 ảnh (xem mục 3 ở
  trên), rồi soát `sheet.jpg`. Đường body-only không dùng `--body-th`.
- Ảnh ra quá ít → giảm `--min-blur`, `--min-person`, tăng `--fps`.
- Ảnh ra quá nhiều bản gần giống → tăng `--min-gap`, giảm `--dup-sim`
  (vd. 0.95), hoặc dùng `--limit`.
- Vẫn còn **pose lặp** (nhiều tấm cùng dáng, chỉ quay đầu khác nhau) → tăng
  `--min-yaw` (30–35°) hoặc `--min-pose` (0.10–0.12). Ngược lại muốn giữ nhiều
  biến thể hơn thì hạ 2 ngưỡng này (hoặc tăng `--per-bucket`), đặt 0 để tắt hẳn bước lọc tư thế.

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
| Chỉ thấy lưng, không bao giờ thấy mặt | thêm `--allow-body-only` (mặc định `--body-only-low 0.45 --body-only-rel 0.85` đã đủ cho hầu hết clip) |
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
| Clip chỉ quay lưng (v1.mp4 lấy 17,6–27 s, **không frame nào thấy mặt**) | trước: **0 ảnh** kể cả khi bật `--allow-body-only` (body_sim 0.55–0,62 < ngưỡng cứng 0,72); giờ: 3 ảnh (2 `sau lưng`, 1 `nghiêng`), nhóm góc của frame nhận: 33 `sau lưng` / 4 `nghiêng` / 1 `không rõ mặt` |
| Trùng tư thế trên obj_1 (13 video, ref `main.jpg`) | trước: 54 ảnh, riêng clip bảo vệ quay tay 78 s chỉ 5 ảnh (nối chuỗi gộp 81 frame còn 6); giờ: **113 ảnh**, clip bảo vệ **12 ảnh**, không còn 2 tấm cùng dáng cùng khung |
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
- **Sau lưng / nghiêng** khi không có mặt dựa vào keypoint: `face_vis` (mũi +
  2 mắt) < 0.60 và vai > 0.45, tai ≥ 0.25 → sau lưng; vai/hông chồng nhau →
  nghiêng. Người ở rất xa, keypoint nhiễu có thể bị xếp nhầm nhóm — chỉ ảnh
  hưởng tới việc chọn ảnh, không ảnh hưởng nhận dạng. Soát `sheet.jpg` nếu thấy
  nhóm sai.
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
- **ô chọn chất lượng**: Cao nhất / 1080p / 720p / 480p, tính theo **cạnh ngắn**.
  Video dọc (Instagram Reel, TikTok) là 720×1280 — nếu lọc theo chiều cao như
  trước thì 1280 > 1080 nên **mọi bản 720p bị loại**, chỉ còn 540×960 (đo thực
  tế: reel 720p tải về thành file 107 KB nhoè). Giờ cap theo cạnh ngắn nên reel
  dọc lấy đúng 720p; job hiện cả **độ phân giải thật** (vd. `720×1280`) để kiểm
  tra ngay, không phải đoán qua dung lượng
- **tải được cả ảnh**: post ảnh / carousel Instagram (`/p/<code>/`) không có
  format video nên yt-dlp báo "No video formats found"; web UI nhận ra bài ảnh
  (playlist không có format) rồi lấy **từng ảnh con** qua
  `/p/<code>/media/?size=l` — đo thực tế: **1080×1619, 157–326 KB** (thumbnail
  mặc định chỉ 750×750). Ô chọn chất lượng chỉ áp cho video; ảnh luôn lấy cỡ
  lớn nhất nguồn trả. Bài của tài khoản riêng tư vẫn cần `cookies.txt`
- **cảnh báo không có tiếng**: có nguồn (nhất là Instagram reel) chỉ trả stream
  video-only, file tải về câm — job sẽ báo vàng "file không có tiếng"; cần tiếng
  thì dùng cookies đăng nhập để nguồn trả bản đầy đủ
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
    select.py        góc đầu, cỡ cảnh, pose, lọc trùng, chọn đa dạng
    pipeline.py      ghép các bước + xuất kết quả
  tests/             pytest cho phần logic thuần
  models/            model ONNX (tự tải, gitignore)
  downloads/         video tải từ web UI (gitignore)
```
