# So ảnh vẫn lỗi: "gần giống góc — zoom — pose" (phân tích bằng số, 2026-11-24)

Trả lời câu "vì sao vẫn còn ảnh gần giống lọt" bằng **đo lại độc lập** trên `output/obj_1`
(99 ảnh), không dùng lại logic quyết định của pipeline. Đã qua **review độc lập bằng
`deepseek-v4-pro`** — phần bị phản biện và phần đã kiểm chứng lại ghi ở mục 5.

## 0. Cách đo

- Audit trên **person crop tái tạo** (full frame + `metadata.box` + `crop_margin 0.12`) —
  đúng thứ `copygate` nhìn thấy — với đúng cấu hình `copygate` (SIFT 512 / ratio 0.75 /
  reproj 4.0), và thêm cấu hình nhạy hơn (2048 features, ratio 0.80).
- Audit trên **full frame** (đúng thứ được ghi ra đĩa) để so hai không gian.
- Soi bằng mắt: `sheet_99.jpg` (99 ảnh + chỉ số), montage từng cụm.

| Không gian so | cặp khớp | mạnh nhất còn lọt |
|---|---|---|
| person crop (copygate đang dùng) | 24 cặp ≥15 inlier | 57 inlier (ratio 0.11) |
| full frame (file xuất ra) | 77 cặp ≥20 inlier | 1024 inlier (ratio 1.00, hai file **byte-identical**) |

## 1. Bằng chứng trực tiếp: cụm `v1.mp4` — 4 ảnh gần như một

Ảnh 91 (34.0 s), 92 (34.5 s), 93 (35.0 s), 94 (36.5 s): cùng sân khấu, cùng zoom, cùng
tư thế giơ tay cầm mic. Đo pose khớp (có xét ảnh gương):

| cặp | pose lệch tb/max | cửa thoát |
|---|---|---|
| 91 ↔ 92 | **2.96 / 6.40** | `feet` False vs True ⇒ `_same_framing` False |
| 91 ↔ 93 | **6.48 / 17.60** | `feet` False vs True (chặn **trước** yaw) |
| 92 ↔ 93 | **5.02 / 11.20** | `feet` khớp, framing khớp ⇒ **yaw 0.0 vs −90.0**, `_yaw_dist`=90 ≥ 25 |
| 93 ↔ 94 | **7.00 / 14.60** | số "đầu" 8.99 vs 6.67 = **1.35×** > 1.30, frac 12.3% > 12% |

Bốn cặp, **ba loại cửa thoát** — và cặp 92↔93 là ca tôi gán sai lúc đầu (đã sửa lại đây).

## 2. Nguyên nhân gốc

### 2.1 `_same_framing` đo zoom bằng proxy nhiễu, và `feet` là cổng cứng (nặng nhất)
`feet_visible` (select.py:647) lật chỉ vì conf của keypoint cổ chân; `_same_framing`
(select.py:173) biến nó thành "khác cỡ cảnh". Ca 91↔92 cách nhau 0.5 s, cùng khung,
`feet` False → True. Cùng chỗ đó, "số đầu" = `person_h/face_px` chia cho bbox mặt SCRFD
(93↔94: 8.99 vs 6.67 = 1.35×) trong khi zoom thật lệch ~12% (`person_h` 737 vs 647).
Đây là **3/4 cặp** của cụm v1.

### 2.2 yaw bão hoà ±90 nhưng vẫn được dùng làm cổng cứng
`yaw = 0.0` khi không thấy mặt, `yaw = −90.0` khi thấy mặt nghiêng → cùng một góc nhìn bị
coi là lệch 90°. Ca 92↔93 (pose lệch 5°/11°, framing khớp) chỉ bị chặn bởi yaw.

### 2.3 `copy_veto` yếu trên crop: ngưỡng 45 nằm giữa hai lớp
Đo lại (đúng cấu hình copygate): chỉ 24 cặp ≥15 inlier; mạnh nhất còn lọt **57**
(Facebook 1750183430, 46.53 ↔ 60.51, pose 26.5/114.2); một cặp **đúng bằng 45**
(CrxeWeKBXtQ 13.50 ↔ 21.00, pose NaN, ratio 0.09) vẫn trong output. Bộ 99 ảnh có các cặp
trùng thị giác tập trung **15–57**, không phải "46–77" như bộ 110 ảnh dùng để hiệu chỉnh
⇒ ngưỡng tuyệt đối đang cắt vào giữa lớp. (Số 45 ở đây là của crop tái tạo; crop thật
lệch ±1–2 inlier nên ranh giới còn mờ hơn.)

### 2.4 So và xuất ở hai không gian khác nhau
`--save` mặc định `full` (pipeline.py:71) ⇒ file ghi ra là **cả khung hình**
(`c.full_jpeg`), nhưng `dedupe` + `copy_veto` chỉ đọc `c.jpeg` = **crop quanh người**
(pipeline.py:289; `copygate._read_gray` copygate.py:65). Hệ quả: quyết định trùng/không
trùng được đưa ra trên một ảnh **khác** ảnh giao cho người dùng, và trên full frame các
cặp này có 100–1024 inlier (mạnh hơn hẳn 15–57 trên crop).

Ca lộ ra ngoài: `...DQyPcOfAaWg___000038000ms__t001.jpg` và `..._t002.jpg` **byte-identical**
(SHA256 `A5C45558075450B1`, 154 181 B). Nhưng đây **không phải lỗi dedupe**: hai bản ghi là
**hai người khác nhau** trong cùng một frame — track 1 box `[274.9,41.5,701.1,1228.4]`
`face_sim 0.191`, track 2 box `[3.2,31.3,266.5,1173.5]` `face_sim None, body_sim 0.605`.
Lỗi thật là **nhận sai người** (đúng mục 1 ưu tiên của HANDOFF); việc xuất full frame chỉ
làm nó hiện ra thành hai file giống nhau. Gộp hai ảnh đó bằng hình học sẽ là **sai**.

### 2.5 `_pose_disagrees` bất đối xứng và mù khi pose = NaN
copygate.py:141–143: pose không đo được ⇒ trả `False` (không phản đối) ⇒ **mặc nhiên cho
SIFT quyết**. Đây là chỗ duy nhất trong hệ không có veto nào. Trên bộ này chưa thấy ca sai
(đã soi cặp sofa 87 inlier bị gộp: hai ảnh **cùng dáng**, gộp đúng — xem 5.3), nhưng cấu
trúc là hở.

### 2.6 Tham lam theo thứ tự: có, nhưng ví dụ tôi đưa ra lúc đầu là SAI
Bản nháp đầu nói "60.51 bị bỏ, giữ 46.53 và 65.5". Kiểm lại: **60.51 vẫn trong output**
(pose `[64.4, 6.0, None, None, 155.1, 176.2, None, None, None, 9.1, 177.4]`), **65.516 mới
là ảnh bị bỏ**. Tôi đọc nhầm file stale trong `dropped_copies/` (xem 2.7). Kết luận về
phụ thuộc thứ tự vẫn đúng về nguyên tắc, nhưng **chưa có ca cụ thể nào chứng minh trên
bộ này** — hạ xuống mức "giả thuyết".

### 2.7 Rác vận hành ở CẢ HAI thư mục xuất
`--clean` mặc định tắt (pipeline.py:625):
- `crops/` có **110 file** trong khi metadata **99** → 11 ảnh đã bị loại vẫn nằm đó
  (kể cả 3 cặp xuyên nguồn). Trỏ LoRA training vào `crops/` là học luôn 11 ảnh trùng.
- `dropped_copies/` có **12 file** trong khi chỉ 11 cặp bị bỏ → 1 file stale (`60.51s`,
  chính là cái làm tôi kết luận sai ở 2.6).
Rác tích luỹ mỗi lần chạy lại, và **làm nhiễu cả việc điều tra**.

### 2.8 Chỉ `copy_veto` là xuyên nguồn
Mọi ngưỡng mềm (`dedupe`, `coverage_pick`, `drop_similar`, `distinct_pose_pick`,
`diverse_gate`) đều scope theo `source`. Cặp khác nguồn đo được **16–33 inlier**, dưới
ngưỡng 40 ⇒ lọt. Hai kênh re-up cùng một khoảnh khắc vẫn có thể vào dataset 2 lần.

## 3. Giải pháp, kèm thử nghiệm trên 99 ảnh

### 3.1 Luật nào gộp cái gì (đo trên full frame, 1220 cặp có khớp)

| Luật | số cặp gộp | gộp oan (pose lệch ≥ 40°) |
|---|---|---|
| hiện tại: `inl ≥ 45` & pose khớp | 26 | 0 |
| `inl ≥ 55` vô điều kiện | 28 | 0 |
| `inl ≥ 35` & pose khớp | 30 | 0 |
| `inl ≥ 35` & (pose **hoặc** zoom khớp) | 47 | **2** |
| `inl ≥ 45` & cùng-khung (scale 0.92–1.09, `|rot| < 6°`) & pose khớp | **16** | **0** |

Luật cuối gộp đúng các ca đang lỗi (byte-identical, Facebook 48.0↔55.0 = 356 inlier, cả
cụm `v1` 34.0/34.5/35.0/36.5/58.0 = 60–145 inlier, DQyPc 24.5↔25.0, Facebook 68.5↔71.5)
và **không** gộp 86↔87 (scale 1.26 = khác zoom thật, cần giữ cho đa dạng).
Chú ý: luật này chạy trên **full frame**; trên **crop** cụm v1 chỉ có ≤16 inlier nên không
luật inlier nào chạm tới — sửa `copy_veto` một mình **không** giải quyết được cụm v1.

### 3.2 Thứ tự nên làm

1. **`_same_framing`** (select.py:155–175): bỏ "số đầu", đo zoom bằng
   `|log(person_h/src_h)|` với ngưỡng ~0.22 (≈ ±25%); `feet` từ điều kiện cứng xuống
   **cờ hoà giải**, chỉ xét khi cả hai `person_h/src_h > 0.85` (giữ lại tác dụng tách
   toàn thân vs cận cảnh mà không để nhiễu keypoint chặn). → bắt 91↔92, 91↔93, 93↔94.
   Rủi ro thấp nhất, không model mới, không đổi kiến trúc.
2. **yaw bão hoà = không đo được**: `|yaw| ≥ 70` hoặc `face_px == 0` hoặc `face_vis < 0.6`
   ⇒ đánh dấu unknown, **không dùng yaw để tách** cặp đó; để pose + zoom + hình học quyết.
   → bắt 92↔93.
3. **`copy_veto` dùng `box` để tách người khỏi nền**: chia inlier thành **trong box người**
   vs **ngoài box**, chỉ gộp khi inlier-trong-box cao **và** homography là gần-similarity
   (`scale 0.8–1.25`, `|rot| < 12°`); inlier nhiều mà phần lớn ở ngoài box ⇒ "cùng nền,
   khác người" ⇒ không gộp. Đồng thời làm `_pose_disagrees` **đối xứng** và **bắt buộc có
   pose** (NaN thì không được tự động cho SIFT quyết).
4. **Dọn cả `crops/` và `dropped_copies/`** trước mỗi lần ghi, không phụ thuộc `--clean`.
   (Rác đang làm sai cả điều tra — 2.6.)
5. **Ground-truth 150–300 cặp** dán nhãn 3 mức, đo `recall@precision ≥ 0.9`, rồi mới chốt
   các con số 0.84 / 45 / 30% / 12° / 20°. Hiện tất cả vẫn là số đoán trên chính tập đang chấm.

### 3.3 Điều KHÔNG nên làm
- **Không** "so full frame trần trụi": cùng cảnh khác zoom/khác dáng sẽ thành trùng
  (sofa 87 inlier, 86↔87 47 inlier scale 1.26). Nếu đổi không gian so thì **bắt buộc** kèm
  ràng buộc similarity ≈ identity + inlier-trong-box (3.2 mục 3).
- **Không** gộp cặp byte-identical bằng hình học: hai ảnh đó là hai **người khác nhau**;
  phải sửa bước nhận người (HANDOFF mục 5.1), không phải dedupe.

## 4. Cách đo khách quan (không dùng lại logic quyết định)

1. **pHash/aHash** trên các file xuất: đếm cặp Hamming < 8, mục tiêu **0** (hôm nay ≥1).
2. **Đếm cụm theo thời gian**: số ảnh `v1.mp4` có `33.5 ≤ t ≤ 37.0` trong metadata —
   hôm nay **4**, mục tiêu sau fix **1**.
3. **Full-frame SIFT + similarity filter + tỉ lệ inlier trong box** để liệt kê "cùng cảnh";
   xác nhận cụm v1 sập còn 1 **mà không** gộp cặp khác người (DQyPc `t001/t002`) và
   không gộp cặp khác zoom (86↔87 scale 1.26).
4. Đọc `dropped_copies/` để kiểm **gộp oan** — sau khi đã dọn rác.

## 5. Kết quả review độc lập (`deepseek-v4-pro`)

**VERDICT: OK-WITH-CHANGES.** Review đồng ý phần cơ chế và 2/3 số liệu, phản biện 4 điểm;
tôi đã kiểm chứng lại từng điểm:

| Review nói | Kiểm chứng | Kết luận |
|---|---|---|
| Cặp byte-identical là **hai người khác** (box lệch hẳn) ⇒ lỗi nhận người, không phải dedupe | metadata idx 41/42: box `[274.9…]` vs `[3.2…]`, `face_sim 0.191` vs `None`/`body_sim 0.605` | **Đúng** — đã sửa lại 2.4 |
| Ví dụ "60.51 bị bỏ" sai; 60.51 vẫn giữ, 65.516 mới bị bỏ | metadata có 60.51; 65.516 không có | **Đúng** — do tôi đọc file stale trong `dropped_copies/`; đã sửa 2.6 |
| Cặp 91↔93 bị chặn bởi `feet` chứ không phải yaw; yaw rò ở **92↔93** | `feet`: 91 False, 93 True; 92 True | **Đúng** — đã sửa bảng mục 1 |
| `--clean` tắt cũng làm `dropped_copies/` tồn rác (12 vs 11) | đúng, có file `60510ms` stale | **Đúng** — đã thêm vào 2.7 |
| Cặp sofa 87 inlier (**đã bị gộp**) là **gộp oan**, hai dáng ngồi khác hẳn | soi ảnh: hai ảnh **cùng dáng** ngồi, cùng bộ đồ, gộp **đúng**; docstring copygate mô tả sai cặp này | **Sai** — không phải gộp oan |
| "77 cặp full ≥15" không tái lập (họ đo 65/98/165 tuỳ config) | con số 77 của tôi là **≥20 inlier** với config 1024/0.80/3.0 | **Đúng** — đã ghi rõ config |

Điểm review đúng và **quan trọng nhất về thứ tự**: đừng đổi sang "so full frame" trước —
nó khuếch đại khớp nền; sửa **phép đo zoom trong `_same_framing`** trước (rủi ro thấp,
chạm 3/4 cặp), rồi **yaw bão hoà**, sau đó mới tới `copy_veto` + tách inlier theo box.
Tôi giữ nguyên đề xuất đó ở 3.2.

Tiêu chí chấp nhận (chốt): pHash các file xuất = 0 cặp gần trùng; cụm `v1.mp4`
`t ∈ [33.5, 37]` còn **1** ảnh; không gộp cặp khác người `DQyPcOfAaWg t001/t002`;
không gộp cặp khác zoom `86↔87`.

## 6. Kết quả sau khi sửa (2026-11-24 23:48)

Đã sửa 3 chỗ, đúng thứ tự 3.2 (1→2, và mục 3 vừa đủ để không gộp oan khác zoom):

| Chỗ sửa | Nội dung |
|---|---|
| `select._same_framing` | zoom = `|log(person_h/src_h)| ≤ 0.16`; `feet` chỉ còn cờ hoà giải khi cả hai ≥ 0.85 khung; "số đầu" chỉ còn là dự phòng |
| `select._yaw_is_placeholder` | `face_px = yaw = pitch = 0` hoặc `face_vis < 0.60` ⇒ yaw là số mặc định, không dùng để tách; chỉ còn phân biệt **hướng thân** (nhóm "sau lưng") |
| `copygate.copy_veto` | chỉ xét gộp khi `_same_framing(c, k)` — hai ảnh khác zoom thật thì không phải bản sao (chặn ca 12.0 s vs 17.0 s của `v1.mp4`, 47 inlier, scale 1.26) |
| `copygate._pose_disagrees` | kết luận "khác dáng" bằng **số khớp lệch** (≥ 2 khớp > 30°) hoặc **median** ≥ 12°, không dùng trung bình+max. Cặp 46.5 ↔ 60.5 s (57 inlier) có 1 khớp lệch 114° nhưng median chỉ 9.3 → trước bị chặn oan, nay gộp đúng |

Đo lại trên `output/obj_1_fix4`:

| Tiêu chí | Trước | Sau |
|---|---|---|
| cụm `v1.mp4` `t ∈ [33.5, 37.0]` | 4 ảnh (34.0 / 34.5 / 35.0 / 36.5) | **1 ảnh** (35.0) |
| cặp byte-identical (DQyPc 38.0 s t001/t002) | có | **hết** |
| pHash: số cặp Hamming < 8 | 3 | 2 |
| giữ đủ cặp khác zoom 12.0 / 17.0 | có | **có** |
| tách được 6.0 (cận cảnh) vs 17.0 (trung cảnh) | có | **có** (`ZOOM_TOL 0.16` chứ không 0.22) |
| số ảnh cuối | 99 | 106 |
| test | 68 pass | **73 pass** (thêm 5 test cho đúng các ca này) |

### Còn lại (chưa sửa, cần quyết định tham số hoặc ground-truth)

1. **`Facebook 1750183430` 68.0 s vs 68.5 s** — pHash cách 3 bit, nhìn như một tấm. Thoát vì
   cách nhau 0.5 s > `min_gap 0.35` (bit-exact dedupe không bắt) và CLIP < 0.97 (dedupe
   ngoại hình cũng không bắt). Sửa đúng phải là **chọn theo plateau thời gian** (3.2 mục 5),
   không phải hạ `dup_sim` — hạ sẽ ăn vào các frame khác.
2. **`v1.mp4` 22.5 s vs 25.0 s** — pHash 4 bit, cùng cú máy, người to lên 32%
   (432 px vs 595 px). Theo trục zoom hiện tại là "khác cỡ cảnh" nên giữ cả hai; muốn gộp
   phải có ngưỡng zoom khác đi kèm ràng buộc hình học, tức là mục 3.2.3 (inlier trong box).
3. **Churn do tham lam**: 20 ảnh bị bỏ, 28 ảnh mới vào so với `obj_1`. Không có ảnh sai rõ
   ràng, nhưng chứng tỏ kết quả còn phụ thuộc thứ tự ⇒ vẫn cần gom cụm (3.2 mục 5) trước khi
   chốt dataset.
4. **Ngưỡng `copy_min_inl = 45`** giữ nguyên: cặp 45-inlier (`CrxeWeKBXtQ` 13.5 ↔ 21.0) vẫn
   nằm trong output. Chỉ nên đổi sau khi có bộ nhãn.

## 7. Lượt chạy với 32 video (13 video mới bổ sung, 2026-11-25)

Đầu vào tăng 21 → **32 video** (2650 frame, 259 track). Phát hiện thêm một lỗi cấu trúc:

### Xuất full frame ⇒ hai track trong cùng một frame cho ra hai file giống nhau
`--save` mặc định `full` nên file ghi ra là **cả khung hình**, không phụ thuộc `box`.
Nhưng `dedupe` chỉ so `clip_vec` của **crop người** (khác nhau giữa hai track) và
`min_gap 0.35 s` không bắt (cùng `t`). Kết quả: **2 frame bị xuất 2 lần, hai file
byte-identical** — `CxzjgbihCyq` frame 437 (t=218.0, track 1 & 2), `Instagram 1750172524`
frame 36 (t=17.5, track 2 & 3). SHA256 khớp từng byte.

**Sửa**: `select.dedupe(..., frame_dedupe=...)` — chỉ bật khi `save in ("full","both")`;
giữ **một** bản xếp hạng cao nhất cho mỗi `(source, frame)`. Không dùng ngưỡng nào
(đây là trùng tuyệt đối). Với `--save crop` thì **không** bật, vì hai box khác nhau là
hai crop khác nhau, đều dùng được.

### Kết quả lượt này

| Tiêu chí | Lượt 99 ảnh (21 video) | Lượt này (32 video) |
|---|---|---|
| số ảnh cuối | 99 → 106 (sau fix) | **168** |
| frame bị xuất 2 lần (byte-identical) | có 1 cặp | **0** |
| pHash cặp gần trùng (< 8 bit) | 3 | **1** |
| cụm `v1.mp4` 34.0–36.5 s | 4 | **1** |
| `crops/` vs `metadata.jsonl` | 110 vs 99 (11 rác) | **168 vs 168** |
| cặp bị bỏ (`copy_pairs.txt`) | 11 | 34 (22 xuyên nguồn) |

Cặp 22 xuyên nguồn phần lớn là **cùng một tấm** thật, nhiều cặp 512 inlier (kịch trần
1024/2) — đúng loại lỗi "re-up cùng sự kiện" mà `copy_veto` sinh ra để bắt. Còn
**28/32 video** đóng góp ảnh; 4 video không có frame nào nhận (không khớp người/mặt).

### Còn lại
- `v1.mp4` **22.5 vs 25.0 s**: pHash lệch 4 bit, cùng cú máy nhưng người to lên 32% ⇒
  trục zoom coi là khác cỡ cảnh. Sửa đúng là `copy_veto` tách inlier **trong box người**
  (đang so trên crop nên người và nền lẫn nhau), không phải nới ngưỡng zoom.
