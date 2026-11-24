# Lọc ảnh trùng (góc / zoom / pose) — tổng kết lỗi và cách đã sửa

Tài liệu này ghi lại **toàn bộ** các lần lỗi "ảnh gần giống vẫn lọt" trong pipeline
`luyen_co`, nguyên nhân gốc của từng lần, cách đã sửa, và những điểm còn hở.
Mục đích: có đủ dữ kiện để đánh giá lại thiết kế từ đầu, thay vì vá tiếp.

---

## 1. Bài toán

Đầu vào: một thư mục video/ảnh (nhiều nguồn: clip điện thoại, clip catwalk, phỏng
vấn, ảnh tĩnh), một ảnh tham chiếu `main.jpg` của **một người cụ thể**.

Đầu ra: vài chục frame cắt quanh người đó, dùng làm dataset LoRA. Yêu cầu:

- đúng người;
- **đa dạng**: góc quay khác nhau, cỡ cảnh (zoom) khác nhau, tư thế khác nhau;
- **không trùng**: hai ảnh mà nhìn vào thấy "cùng một tấm" thì chỉ giữ một;
- ảnh phải dùng được (không mờ, không rác, không phải frame chuyển cảnh).

Quy mô hiện tại: 20 video → 1325 frame → 123 track → **110 ảnh** cuối.

## 2. Kiến trúc hiện tại

Ba trục được đo **độc lập**, mỗi trục là một hàm thuần trên `Candidate`:

| Trục | Hàm | Tín hiệu |
|---|---|---|
| Cỡ cảnh (zoom) | `shot_scale()` | `person_h / face_px` = số "đầu" trong khung; dự phòng `person_h / src_h`; cờ thấy cổ chân |
| Góc quay | `yaw_bucket()` | yaw/pitch từ 5 landmark đầu (mũi, 2 mắt, 2 tai), có xét "mặt khuất" |
| Dáng (pose) | `pose_angles()` | 11 góc khớp: khuỷu L/R, gối L/R, nâng tay L/R, dạng đùi L/R, mở hai đùi, nghiêng thân, nghiêng vai |

Hai ảnh bị coi là **trùng** khi giống nhau ở **cả ba** trục (`_same_pose()` →
`_same_framing()` AND pose AND góc). Đây là logic **AND của ba ngưỡng cứng**.

Luồng chọn (theo thứ tự trong `pipeline.py::export`):

```
dedupe (bit-exact) → drop_tiny_frames → drop_blurry_faces → drop_bad_frames
→ coverage_pick (1 ảnh / nguồn·cảnh·nhóm góc) → drop_similar (CLIP cùng nhóm)
→ [shot_coverage_pick nếu --shot-per-bucket > 0]
→ distinct_pose_pick (greedy, giữ ảnh khác mọi ảnh đã giữ) → --limit
```

Tham số hiện tại (`Config`):

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `min_yaw` | 25° | lệch góc đầu tối thiểu để coi là "khác góc" |
| `min_pose_deg` | 20° | lệch góc khớp **trung bình** tối thiểu (11 góc) |
| `min_pose_max_deg` | 45° | lệch góc khớp **lớn nhất** cho phép |
| `near_dup_th` | 0.84 | cùng bên + cùng cỡ cảnh + CLIP ≥ 0.84 ⇒ trùng |
| `_same_framing` | head_tol 0.30, frac_tol 0.12 | cùng cỡ cảnh |
| `face_sharp_ratio` | 0.35 | bỏ frame mặt mờ so với trung vị cảnh |
| `spark_ratio` / `blur_ratio` | 4.0 / 0.25 | bỏ frame hiệu ứng / mờ hẳn |
| `JOINT_CONF` / `BONE_MIN` / `POSE_MIN_ANGLES` | 0.35 / 0.10 / 4 | điều kiện đo góc khớp |

## 3. Các lần lỗi và cách sửa (theo thứ tự thời gian)

### 3.1 Mất hết ảnh "sau lưng" (lỗi đầu tiên)
- **Triệu chứng**: clip chỉ quay từ sau → 0 ảnh; clip có cảnh quay lưng → mất sạch.
- **Nguyên nhân**: lọc theo `yaw` một mình. Quay lưng thì YOLO vẫn đoán mũi với
  conf cao (0.58) nên yaw ≈ 0 và bị xếp vào "thẳng"; đồng thời CLIP ảnh lưng so
  với ảnh tham chiếu nhìn thẳng chỉ đạt 0.55–0.65, dưới ngưỡng nhận người 0.72.
- **Sửa**: thêm `face_vis()` = trung bình conf của **mũi + 2 mắt**; dưới 0.60 ⇒
  mặt bị khuất, tách hẳn nhóm "sau lưng" / "sau lưng 3/4" khỏi "không rõ mặt".
  Nhận người bằng `keep_best_body_tracks()`: khi không track nào khớp mặt, so
  **tương đối** theo trung vị `body_sim` thay vì ngưỡng tuyệt đối.

### 3.2 Clip quay tay chỉ ra 5 ảnh
- **Nguyên nhân**: union-find/gom cụm nối chuỗi — camera di động làm A≈B≈C… nên
  cả đoạn phim sập thành một cụm (81 frame → 6 ảnh).
- **Sửa**: bỏ gom cụm, dùng **greedy duyệt theo chất lượng giảm dần**
  (`_rank_key`) — giữ 17 ảnh thay vì 6. Thêm `drop_tiny_frames` (bỏ frame người
  quá bé) và nâng `per_bucket` 1 → 3.

### 3.3 "Pose lặp quá nhiều" (lỗi lớn nhất, sửa nhiều vòng)
- **Nguyên nhân 1**: `coverage_pick` chỉ giới hạn 1 ảnh / (nguồn, cảnh, nhóm góc);
  5 frame catwalk liên tiếp với đầu quay ±20° rơi vào 5 nhóm khác nhau ⇒ 5 ảnh
  gần như y hệt (pose cách nhau 0.019–0.058).
- **Sửa 1**: thêm `distinct_pose_pick` — greedy, giữ ảnh nếu nó khác **mọi** ảnh
  đã giữ (so 3 trục).
- **Nguyên nhân 2**: đo dáng bằng toạ độ keypoint chuẩn hoá trong bbox
  (`_pose_dist`, 34 chiều). Bbox bị chính dáng làm nhiễu: giơ tay ra là bbox rộng
  ra, mọi toạ độ x bị nén lại, khoảng cách nhảy vọt dù người không đổi dáng.
  Đo trên obj_1: **47 cặp** ảnh trùng dáng + trùng góc + trùng cỡ cảnh vẫn lọt.
- **Sửa 2**: đo bằng **góc khớp** (`pose_angles`, 11 góc). Góc không phụ thuộc
  bbox, không phụ thuộc người to/nhỏ trong khung, không phụ thuộc vị trí.
  `_pose_dist` chỉ còn là **dự phòng** khi không đo được góc nào.
- **Sửa 3**: thêm **ảnh gương = cùng dáng** (`POSE_MIRROR_IDX`/`SIGN`) — dáng
  nhìn sang trái và sang phải là một, không tính là hai tư thế.
- **Sửa 4**: `max` góc lệch (45°) quan trọng hơn trung bình — trung bình 11 góc
  pha loãng "chỉ một tay giơ lên" thành 90/11 ≈ 8°.

### 3.4 Ba trục lẫn vào nhau
- **Nguyên nhân**: một ảnh cận cảnh và một ảnh toàn thân cùng dáng bị coi là
  trùng, vì chỉ so góc + dáng.
- **Sửa**: thêm trục **cỡ cảnh** vào điều kiện trùng; hai ảnh chỉ bị coi là trùng
  khi giống **cả ba** trục.

### 3.5 Frame chuyển cảnh chồng mờ (cross-dissolve) lọt vào dataset
- **Triệu chứng**: ảnh có 2 bóng người chồng lên nhau.
- **Đã thử và thất bại**: lọc theo `blur` cả frame — frame hỏng vẫn "nét" theo
  Laplacian (2525) so với frame sạch cùng cảnh (2677–4620). Thử cả bộ dò
  temporal dissolve ở mức frame → **61/150 frame** của clip cắt nhanh bị báo nhầm,
  đã revert hoàn toàn.
- **Sửa đúng**: Laplacian trên **vùng mặt** 112×112 — frame hỏng chỉ **23**, frame
  sạch cùng clip **90–161**. Ngưỡng so **tương đối** với trung vị của chính cảnh
  (vì mặt nhỏ trong ảnh toàn cảnh vốn mờ hơn).

### 3.6 Frame rác khác
| Loại | Tín hiệu | Ngưỡng |
|---|---|---|
| Hiệu ứng lấp lánh/glitch | `spark_fraction()` — đốm sáng V≥235, S<90 | ≥ 4× trung vị cảnh, ≥ 0.03 |
| Mờ hẳn (người ở xa) | `blur` cả frame | < 0.25 × trung vị cảnh |
| Cận cảnh mặt hỏng | CU/ECU + `face_sim < face_th` | 0.40 |

### 3.7 Ảnh "na ná" lọt qua cả 3 trục (4 cặp)
- **Triệu chứng**: 4 ảnh MC đang nói (45.0 / 52.5 / 56.5 / 60.5 s), cùng váy, cùng
  bối cảnh, cùng khung, CLIP 0.843–0.893 — vẫn lọt vì góc đầu lệch vài chục độ.
- **Sửa**: thêm luật **near-dup**: cùng **phía** quay + cùng cỡ cảnh + CLIP ≥ 0.84
  ⇒ trùng, bất kể góc lệch bao nhiêu.
- **Hở tiếp**: 3 ảnh 67.0 / 68.0 / 68.5 s (CLIP 0.953–0.966) vẫn lọt, vì luật cũ
  đòi |yaw| ≥ 20° mới xét. **Sửa**: dùng `_yaw_family()` (chính diện / trái /
  phải) thay cho |yaw| ≥ 20.

### 3.8 Hai ảnh "cùng cỡ cảnh" bị coi là khác cỡ cảnh
- **Triệu chứng**: cặp 70.0 s và 70.5 s lọt. Hai khung gần như y hệt (người chiếm
  91% khung), chỉ vì bbox mặt 282 vs 330 px nên số "đầu" là 4.11 vs 3.53 → rơi
  vào 2 mức liền kề ("trung cảnh" vs "trung cận").
- **Sửa**: `_same_framing()` so **số đo** (số đầu lệch ≤ 30%, hoặc tỉ lệ
  người/khung lệch ≤ 12% + cùng trạng thái thấy cổ chân), **không** so nhãn.

## 4. Vì sao vẫn "chưa triệt để"

Đây là phần quan trọng nhất. Các điểm hở **có thật**, không phải thiếu may:

1. **Hàm đánh giá trùng với hàm quyết định.** Script audit dùng đúng `_same_pose`
   để kiểm tra kết quả của `_same_pose`, nên nó luôn báo "0 cặp trùng còn sót".
   Con số 0 đó **không có giá trị kiểm chứng** — nó chỉ chứng minh code chạy đúng
   như code. Không có bộ ground-truth (cặp ảnh dán nhãn trùng/không trùng) nào cả.
2. **Phép AND của ba ngưỡng cứng quá dễ dãi.** Chỉ cần **một** trục lệch quá
   ngưỡng là giữ cả hai ảnh. Ngưỡng nào cũng có vùng biên; ba ngưỡng ⇒ ba vùng
   biên, và mọi cặp rơi vào bất kỳ vùng biên nào đều lọt. Không có "điểm tổng"
   để nói "cặp này 92% là trùng".
3. **Không có gom cụm toàn cục.** Quyết định là **tham lam, phụ thuộc thứ tự**:
   ảnh giữ sớm chặn ảnh sau; chuỗi A≈B, B≈C nhưng A≁C thì tuỳ thứ tự mà giữ 1
   hay 2 ảnh. Union-find thì sập cả đoạn (lỗi 3.2). Cả hai đều sai kiểu khác nhau.
4. **Ngưỡng góc khớp rất rộng so với ngữ nghĩa "cùng dáng".** 20° trung bình /
   45° max là *rất* nhiều — một cánh tay hạ thấp 30° vẫn "cùng dáng".
5. **NaN làm mất tín hiệu mạnh nhất.** Chỉ cần 4/11 góc đo được là kết luận; nếu
   < 4 thì rơi về `_pose_dist` — đúng cái metric đã chứng minh là hỏng. Ảnh bị
   khuất nhiều (ngồi, tay trước người) đi qua nhánh yếu.
6. **`yaw` bão hoà.** 5 landmark không đo được yaw ngoài ±90°, pitch nhiễu tới
   ±89°; đã phải bỏ pitch khi |yaw| ≥ 70. Hai ảnh −85° và −60° được coi là "khác
   góc" dù cùng nhìn gần như một hướng.
7. **CLIP là embedding *ngoại hình*, không phải *copy detection*.** Cùng người
   nhưng đổi bộ đồ / đổi ánh sáng ⇒ CLIP tụt dưới 0.84 ⇒ lọt dù pose y hệt.
   Ngược lại cùng bộ đồ + cùng bối cảnh ⇒ CLIP 0.9+ ⇒ gộp oan hai dáng khác nhau.
   Ảnh lưng còn tệ hơn (CLIP 0.55–0.65).
8. **Zoom trôi (handheld zoom/pan).** Dedupe so từng cặp frame rời rạc, nên một
   cú zoom chậm tạo ra chuỗi frame mỗi cái "khác đủ ngưỡng" — không có khái niệm
   "plateau" (đoạn đứng yên) để lấy một đại diện.
9. **Nhãn và số đo lẫn lộn.** Chỗ thì so `bucket == bucket`, chỗ thì so
   `_yaw_dist()`, chỗ thì so `_yaw_family()`. Ba cách so cùng một trục.
10. **Ngưỡng hiệu chỉnh trên đúng bộ dữ liệu đang chấm.** Mọi con số (0.84, 20°,
    45°, 0.30, 0.12) được chỉnh tay bằng cách soi `sheet_audit.jpg` của obj_1 —
    không có tập validation riêng, nên không biết chúng có tổng quát không.
11. **Mất thông tin trước khi dedupe.** `coverage_pick` + `drop_similar` chạy
    trước, cắt theo nhóm góc; frame bị cắt sớm không bao giờ được so ở bước
    cuối. Lỗi ở bước trước không thể sửa ở bước sau.

## 5. Hướng có thể thay đổi (để review)

- **Copy-detection embedding thay CLIP** (SSCD, hay embedding chuyên near-dup):
  thiết kế đúng cho "cùng một cảnh, khác crop/zoom" — khác mục tiêu với CLIP.
- **Gom cụm toàn cục** (agglomerative + complete linkage, hoặc HDBSCAN) trên
  vector ghép [pose góc khớp, yaw, log(scale), ReID/appearance], chọn medoid mỗi
  cụm — bỏ hẳn tính phụ thuộc thứ tự.
- **Hợp điểm có trọng số** thay AND: `S = w·[pose, yaw, scale, appearance]`,
  hiệu chỉnh bằng logistic regression trên vài trăm cặp dán nhãn tay.
- **Chọn theo plateau thời gian**: phát hiện đoạn ổn định (đạo hàm pose/scale
  nhỏ) rồi lấy 1 đại diện mỗi đoạn — đúng bản chất video.
- **ReID embedding** (OSNet/CLIP-ReID) cho trục ngoại hình, tách khỏi pose.
- **Tập ground-truth nhỏ** (100–200 cặp) để đo precision/recall thật, thay cho
  việc soi bằng mắt.

## 6. Cách chạy lại

```powershell
cd luyen_co
.venv\Scripts\python.exe luyen_co.py --input sample\obj_1 --ref sample\obj_1\main.jpg --out output\obj_1
```

Kết quả tự kiểm: `output/obj_1/summary.txt`, `report.csv`, `sheet_audit.jpg`,
`sheet_shot.jpg`, `crops/`, `metadata.jsonl`.

---

## 7. Vòng sửa sau khi review độc lập (đã làm)

Bản review độc lập đo lại trên chính 110 ảnh (SIFT + RANSAC, **không** dùng
`core.select`) và tìm ra 5–6 cặp na ná thật, trong đó **2 cặp xuyên nguồn** mà
kiến trúc cũ **về nguyên tắc không thể thấy** — vì cả 4 hàm dedupe đều scope theo
`source`. Đã sửa bằng `core/copygate.py` (xem mục "Ảnh trùng thật" trong README):

- `copy_veto` chạy **xuyên mọi nguồn**, dựa trên inlier SIFT + RANSAC.
- Vá lỗi `Candidate.jpeg` bị xoá sau khi stage ra đĩa — nếu không, cổng lặng lẽ
  không bắt được gì (lần chạy đầu đúng là như vậy: 110 → 110).
- Hạ ngưỡng từ 50/0.22 xuống 45/0.06 sau khi tự đo: với bộ đặc trưng này, cặp
  trùng thật cho 46–77 inlier, cặp không trùng ≤ 39.
- Thêm chặn gộp oan vì **phông nền**: cùng nền sofa mà khác dáng vẫn cho 87
  inlier — nên nếu dáng lệch ≥ 12° (tb) hoặc ≥ 30° (max) thì không gộp.
- Lưu `copy_pairs.txt` + `dropped_copies/` + `sheet_copy.jpg` để soi lại.

Kết quả: **110 → 99 ảnh**, 11 cặp bị bỏ (3 cặp xuyên nguồn, 190/198/61 inlier).
Cặp mạnh nhất còn sót trong 99 ảnh: 41 inlier (dưới ngưỡng 45).

### Việc chưa làm (review chỉ ra, chưa sửa)

1. **38/110 ảnh không detect được mặt**, tất cả `body_sim` < 0.72 (min 0.429) —
   chúng chỉ vào được bằng nhánh "neo ngoại hình" `anchor_ok`; trong đó **1 ảnh
   là người khác** (đàn ông mặc vest, cosine với neo của video = 0.609, sát ngưỡng
   `anchor_th=0.60`). Đây là lỗi **đúng người**, nghiêm trọng hơn lỗi trùng ảnh.
2. **Mất cân bằng look**: 8/110 ảnh cùng một váy vàng cùng sân khấu; `shot_per_bucket`
   đang tắt nên không có trần theo ô (góc × cỡ cảnh).
3. Trục đo còn sai bản chất: `person_h / face_px` làm proxy zoom (tương quan âm
   với `person_h/src_h`, và 3 ảnh cho "12–31 đầu" vô lý), yaw/pitch từ 5 landmark
   bão hoà ±90 (pitch lẫn yaw: corr +0.47, 19 "ngửa" vs 2 "cúi").
4. Chưa có tập ground-truth: mọi ngưỡng vẫn hiệu chỉnh trên chính tập đang chấm.

