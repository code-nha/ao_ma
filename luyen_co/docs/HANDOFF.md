# HANDOFF — trạng thái & việc tiếp theo

> File này để mở session mới đọc trước. Cập nhật lần cuối: commit `1a4e534`.

## 1. Đang ở đâu

- Repo: `C:\Users\khoa\code_nha\ao_ma-luyen_co`, nhánh `feat/luyen_co`
  (worktree riêng, **không** làm trên `ao_ma` chính).
- Sub-project: `luyen_co/` — lọc frame của **một người cụ thể** từ thư mục video/ảnh
  để dựng dataset LoRA.
- Trạng thái: **99 ảnh** cho `sample/obj_1` (20–21 video), 68 test pass,
  commit `1a4e534` đã push.
- Đầu ra: `luyen_co/output/obj_1/` — `crops/`, `metadata.jsonl`, `summary.txt`,
  `report.csv`, `sheet.jpg`, `sheet_shot.jpg`, `copy_pairs.txt`, `dropped_copies/`,
  `sheet_copy.jpg`. Toàn bộ `output/` nằm trong `.gitignore`.

Chạy lại:

```powershell
cd luyen_co
.venv\Scripts\python.exe -X utf8 luyen_co.py --input sample\obj_1 --ref sample\obj_1\main.jpg --out output\obj_1
```

(~125 s, DirectML, model tự tải vào `luyen_co/models/`.)

## 2. Pipeline & tham số

```
dedupe → drop_tiny_frames → drop_blurry_faces → drop_bad_frames
→ coverage_pick → drop_similar → [shot_coverage_pick] → distinct_pose_pick
→ copy_veto → [--limit]
```

| Tham số | Mặc định | Nghĩa |
|---|---|---|
| `--per-bucket` | 3 | ảnh tối đa mỗi nhóm góc ở bước coverage |
| `--min-yaw` | 25 | lệch góc đầu tối thiểu |
| `--min-pose-deg` / `--min-pose-max-deg` | 20 / 45 | lệch góc khớp TB / lớn nhất |
| `--near-dup-th` | 0.84 | cùng bên + cùng cỡ cảnh + CLIP ≥ mức này ⇒ trùng |
| `--shot-per-bucket` | 0 | trần mỗi ô (góc × cỡ cảnh); **đang tắt** |
| `--copy-min-inl` / `--copy-min-ratio` | 45 / 0.06 | ngưỡng cổng trùng thật (cùng nguồn) |
| `--no-copy-gate` | — | tắt cổng trùng thật |

Ba trục đo độc lập: **cỡ cảnh** (`shot_scale`, số "đầu" = `person_h/face_px`),
**góc quay** (`yaw_bucket`, 11 nhóm), **dáng** (`pose_angles`, 11 góc khớp,
ảnh gương = cùng dáng).

## 3. Lịch sử sửa (đã xong, đã push)

| Commit | Nội dung |
|---|---|
| `459145c` | nhận đúng frame "sau lưng" (conf mũi+2 mắt), hết 0 ảnh cho clip chỉ quay lưng |
| `5334872` | lọc trùng tư thế theo góc camera + pose |
| `164231d` | clip quay tay ra đủ ảnh: bỏ union-find (sập 81→6), greedy theo chất lượng, `drop_tiny_frames` |
| `97ebcfe` | xoá script chẩn đoán tạm |
| `d6e77d8` | đo cỡ cảnh, tách "sau lưng 3/4", thêm `--shot-per-bucket` |
| `266a1d4` | đo dáng bằng **góc khớp** (11 góc) thay toạ độ bbox — 47 cặp trùng lọt đã bị bắt |
| `9892a4f` | bỏ frame chuyển cảnh chồng mờ bằng Laplacian **vùng mặt** (23 vs 90–161) |
| `7c534fb` | bỏ ảnh hỏng (lấp lánh / mờ hẳn / cận cảnh mặt hỏng) + near-dup cùng bên |
| `5837c41` | near-dup áp cả phía chính diện (`_yaw_family`, không đòi \|yaw\|≥20) |
| `f4b1c4f` | so cỡ cảnh bằng **số đo** thay nhãn (`_same_framing`) |
| `1a4e534` | **copy_veto**: chặn ảnh trùng thật bằng SIFT + RANSAC, **xuyên mọi nguồn** |

Chi tiết nguyên nhân từng lỗi: `luyen_co/docs/dedupe-notes.md`.

## 4. Vòng sửa mới nhất (`1a4e534`)

Review độc lập (SIFT + RANSAC, không dùng `core.select`) tìm ra 5–6 cặp na ná thật
trên 110 ảnh, trong đó **2 cặp xuyên nguồn** mà kiến trúc cũ **không thể thấy** —
cả 4 hàm dedupe đều scope theo `source`.

`core/copygate.py` hỏi câu khác: *"hai ảnh có phải cùng một khung hình không"*,
trả lời bằng số inlier SIFT sau RANSAC homography, chạy xuyên mọi nguồn.

- Ngưỡng đo từ dữ liệu: trùng thật **46–77 inlier**, không trùng **≤ 39**.
- Chặn gộp oan vì phông nền: cùng nền sofa khác dáng vẫn cho **87 inlier** ⇒ nếu
  dáng lệch ≥ 12° (tb) hoặc ≥ 30° (max) thì không gộp.
- Kết quả: **110 → 99 ảnh**, 11 cặp bỏ (3 cặp xuyên nguồn, 190/198/61 inlier).
  Cặp mạnh nhất còn sót: 41 inlier.
- Lưu vết: `copy_pairs.txt` + `dropped_copies/` + `sheet_copy.jpg`.

Ba lỗi đã vá trong lúc làm (đừng lặp lại):
1. `Candidate.jpeg` bị **xoá** sau khi stage ra đĩa (`pipeline.py:439`) ⇒ cổng phải
   đọc từ `c.staged`, không thì lặng lẽ không bắt được gì.
2. Ngưỡng của bản review (50/0.22) tính theo cách đếm keypoint khác ⇒ vô dụng;
   phải tự đo lại.
3. `_rank_key` hoà ở cả 3 tiêu chí ⇒ thêm khoá phụ `(t, source)` cho kết quả
   không phụ thuộc thứ tự.

## 5. Việc tiếp theo (theo thứ tự ưu tiên)

1. **Đúng người — nặng hơn lỗi trùng ảnh.** 38/110 ảnh không detect được mặt, tất
   cả `body_sim` < 0.72 (min 0.429), chỉ vào được bằng nhánh "neo ngoại hình"
   `anchor_ok` (`pipeline.py` ~dòng 348). Trong đó **1 ảnh là người khác** (đàn ông
   mặc vest, cosine với neo của video = **0.609**, sát ngưỡng `anchor_th = 0.60`).
   Neo CLIP cấp-video thực chất là bộ dò **bối cảnh**, không phân biệt người.
2. **Mất cân bằng look.** 8/99 ảnh cùng một váy vàng cùng sân khấu; `--shot-per-bucket`
   đang tắt nên không có trần theo ô (góc × cỡ cảnh).
3. **Hai trục đo sai bản chất.** `person_h/face_px` làm proxy zoom: tương quan
   **âm** với `person_h/src_h`; 3 ảnh cho "12–31 đầu" vô lý (mặt 40–89 px trong
   người 1087–1277 px). `yaw` bão hoà ±90, `pitch` lẫn yaw (corr +0.47 ⇒ 19 "ngửa"
   vs 2 "cúi"). Gợi ý: `cv2.solvePnP` với 5 điểm chuẩn; zoom đo bằng
   `log(person_h/src_h)` + vector 17 bit "khớp nào còn trong khung".
4. **Chưa có ground-truth.** Mọi ngưỡng đang hiệu chỉnh trên chính tập đang chấm.
   Cần 150–300 cặp dán nhãn 3 mức (2 = trùng, 1 = cùng look, 0 = khác), đo
   recall@precision≥0.9.
5. **copy_veto còn hở**: ngưỡng inlier tuyệt đối 45 là ranh giới mờ (cặp 41 inlier
   vẫn nằm trong output); gộp oan khi hai ảnh cùng phông nền. Cần cách tách "người
   trùng" khỏi "nền trùng" — chưa giải.

## 6. Quy ước làm việc

- Trả lời **tiếng Việt, ngắn gọn**, đi thẳng vào số liệu.
- Sửa xong thì **commit + push luôn**, không hỏi lại.
- Test: `cd luyen_co; .venv\Scripts\python.exe -X utf8 -m pytest tests -q`.
- Script chẩn đoán tạm để ở `%TEMP%`, **không** commit vào repo.
- Không đưa `output/` vào git.
- Người dùng toàn báo lỗi bằng cách **chỉ ra tên file cụ thể** → luôn mở đúng ảnh
  đó ra soi trước khi sửa, đừng sửa mò.
- Một số quyết định đã chốt: `--per-bucket 3`; chấp nhận giữ 1 đại diện cho cụm
  trùng; dataset ~99 ảnh là chấp nhận được.

## 7. Ghi chú về model

Session này chạy `deepseek-flash`. Route `deepseek-official/deepseek-v4-pro` đã được
bật trong setting (`subagent-model-selection-settings`), nhưng policy được **ghi vào
session lúc session bắt đầu** — session cũ vẫn bị chặn với lỗi
`without a recorded model-selection policy`. Session mới thì gọi được.

## 8. Việc của session mới (Pro)

Đọc thêm `luyen_co/docs/dedupe-notes.md` + `core/copygate.py` + `core/select.py` +
`core/pipeline.py` (`Config`, `export`), rồi trả lời:

1. Review trước (chạy trên flash) đúng ở đâu, **sai/kết luận vội** ở đâu?
2. `copy_veto` hiện gộp oan khi hai ảnh cùng **phông nền** (cặp sofa khác dáng cho
   87 inlier), và ngưỡng inlier tuyệt đối 45 là ranh giới mờ (cặp 41 inlier vẫn
   lọt). Tách "người trùng" khỏi "nền trùng" mà **không** cần model segmentation
   thì làm thế nào?
3. Lỗi 38 ảnh không có mặt / 1 ảnh sai người: thiết kế lại bước nhận người (hiện
   dùng `anchor_th` cosine CLIP cấp-video) cho đúng.
4. Nếu chỉ được làm **một** thay đổi tiếp theo: chọn gì, thay hàm nào, tham số nào?
5. Cách đo khách quan **không** dùng lại logic quyết định.

Ràng buộc: Windows, Python 3.12, ONNX Runtime **DirectML** (không CUDA, không torch
CUDA). Model sẵn có: YOLOv8n-pose, SCRFD det_10g, ArcFace R50, CLIP ViT-B/32.
Chạy offline. Đề xuất thêm model phải nêu rõ có bản ONNX không và chi phí.

