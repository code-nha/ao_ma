# Kho nét LOOK (v3)

Kho cho agent (Gemma qua `kbq.py`, Opus khi chưng cất), không phải cho người đọc. Cách truy vấn: xem `AGENTS.md` (tiếng Anh).
v3 thêm: **bộ lọc theo đời sống** (mức sống, nghề, ăn uống, rượu, thuốc, nơi ở, thế hệ, dân tộc), **luật lý do** cho nét hiếm/nổi
bật, và **mặt, tóc tự nhiên, dấu vết** (nhóm B, C, H của `../LOOK_SLOTS.md`). `body.json` (v1) đã bị thay thế, không dùng.
Bản 2026-11-24 thêm **số thật**: chiều cao theo năm sinh (NCD-RisC), béo/gầy theo tuổi (NCD-RisC BMI 2024, WHO STEPS VN),
mặt/đầu/mũi người Kinh (2 bài báo), từ vựng chuẩn (DVI, NCIC, TT 22, NIH EoM), nền màu da theo nghề/nơi ở, luật lý do chặt
hơn. Số nào lấy từ đâu: mục "Số liệu từ đâu" trong `report.md`.

## Bố cục
| file | là gì | sửa tay? |
|---|---|---|
| `vocab.json` | danh sách đóng: 42 ô (thứ tự prompt A → B → C → D-G → H), dải tuổi, nguyên nhân, trục ẩn, vùng, **facets** đời sống + bảng từ khóa đọc IDENTITY/STYLE/LIFE, luật lý do (`cite`), chỗ đặt dấu vết (`marks`) | có, cẩn thận |
| `catalog/<ô>.jsonl` | giá trị, mỗi dòng một giá trị, mỗi ô một file | **có: nguồn sự thật** |
| `vi.jsonl` | nghĩa tiếng Việt (id → vi), chỉ cho người xem; không gửi model | có |
| `evidence/<nguồn>.jsonl` | thẻ căn cứ chép từ ebook_maker (`*_pf.jsonl`: thẻ sách mặt, id `pf.kXXXXX`) | có |
| `sources.jsonl` | mỗi nguồn một dòng (`terms`, `license_needed: false`) | có |
| `rules.jsonl` | luật loại trừ cặp giá trị mà trục/vùng không nói được (`kind: exclude`), và gợi ý mềm (`kind: hint`, có `basis`, không bao giờ là mâu thuẫn) | có |
| `stats.json` | số liệu chưng cất (chiều cao, BMI, STEPS, mặt Kinh, MAAD, ANSUR); `kb.json` chỉ giữ phần `height` | sinh bởi `src/distill_*.py` |
| `standards.json` | thuật ngữ chuẩn (`ncic_*:`, `dvi:`, `tt22:`, `vn_conv:`, `eom:`) + mã NCIC cho từng dấu vết x chỗ | sinh bởi `src/distill_vocab.py` |
| `evidence/num/*.csv` | bảng số có file, sha256, bảng/trang hoặc dòng gốc để kiểm lại | sinh bởi `src/distill_*.py` |
| `tests/golden.jsonl` | ca phải bắt / phải cho qua / nền phải bị che; menu theo facts; lý do; đọc facts | có |
| `ids.lock`, `kb.json`, `report.md` | sinh ra | không |
| `kbq.py` / `kb.py` | module truy vấn / CLI kiểm, dựng | |
| `src/` | script một lần (lịch sử): `migrate_v2.py`, `v3_face_life.py` + `face_bch.txt` (nguồn soạn ban đầu của B, C, H); chưng cất số: `pdf_text.py` (PDF -> text), `distill_ncdrisc.py`, `distill_tables.py` (STEPS + bài báo Kinh, chép tay có bảng/trang), `distill_maad.py` (đọc dòng CSV 3,3 triệu ảnh), `distill_ansur.py`, `distill_vocab.py`, rồi `v4_distill.py` (áp vào catalog) và `v4_golden.py`. Dữ liệu gốc ở `C:/Users/khoa/data/nhan_vat_sources` (manifest.jsonl); chạy Python với `-I` | các script chưng cất chạy lại được (idempotent) |

Trường của một giá trị: `sex`, `age` [từ, đến], `phrase` (tiếng Anh, chỉ cái mắt thấy), `causes` (thẻ đóng), `freq`
(common/uncommon/rare theo giới/dải tuổi; **mặc định cho người Kinh / Đông Nam Á**), `sal` (plain/mild/marked), `baseline_for`
(nhóm giới-dải tuổi, hoặc `european/male-young` cho nền theo dân tộc), `dims`, `regions`, **`needs`** (điều kiện đời sống, xem
dưới), **`fit`** (thẻ đời sống làm nét này dễ gặp hơn: lên đầu menu), `ev`, `status`; ô `marks` có thêm `locs` (chỗ được đặt).
Thêm: `z` [từ, đến] (chỉ ô `height`: dải z so với cùng giới x lớp sinh x dân tộc; menu in thêm `(~158-167 cm)`), `std` (danh
sách thuật ngữ chuẩn trong `standards.json`). `freq` có `basis: stat` phải có `p` (và `src` ghi bảng); `proxy` (MAAD, ANSUR)
không bao giờ đặt tần suất cho người Việt.

## Bộ lọc đời sống
- Code đọc **facts** từ IDENTITY (trường nào đọc facet nào: `vocab.fact_fields`) và STYLE (dòng "eating and drinking",
  "grooming"...): `python -I kb.py facts ../lao_bay`. Lão Bảy: `poor`, `sea`, `outdoor-manual`, `plain-diet`, `drinks`,
  `smoker`, `kinh`, `coastal`, `rural`, `born-pre1960`.
- `needs` = danh sách điều kiện, **chỉ cần một điều kiện đúng**; trong một điều kiện, facet nào nhân vật có thẻ thì phải khớp,
  facet chưa biết thì cho qua. Ví dụ bụng bia: `[{"diet": ["well-fed","overfed"]}, {"alcohol": ["heavy-drinker"]}]` → ông ngư
  dân nghèo ăn đạm bạc, thỉnh thoảng một ly rượu sẽ không thấy nó trong menu.
- Giá trị của dân tộc khác (mắt xanh, tóc vàng...) có `needs: [{"eth": [...]}]`; `mixed` qua được mọi điều kiện dân tộc.
- LIFE chỉ cho **thẻ nguyên nhân** từng mục (`cause_keywords`), không cho facet. Bệnh/thương tích trong mục kể người khác chết
  (vợ chết vì bệnh) không tính là của nhân vật. Chỉ đọc phần sự kiện, bỏ dòng "Interpretation:"; từ khóa chặt hơn ("con trai lên
  Đà Nẵng" không còn là sinh nở; "mua ghe" không còn là làm nghề nước); `cause_only_sex`: sinh nở chỉ cho nữ.
- **Nền theo đời sống**: tra nền theo thứ tự `kinh/<nhóm>` (dân tộc) -> `<thẻ life/place>/<nhóm>` (`vocab.baseline_facets`) ->
  `<nhóm>`. Nam làm ngoài trời (outdoor-manual, sea, farm, street, military) mặc định da `skin_tone.deeptan` + rám chỗ hở
  `body_skin.farmertan-m`; nữ ngoài trời `golden`; nam nông thôn/ven biển/vùng cao `golden`, nữ `olive`; dân văn phòng thành thị
  giữ da sáng mặc định.

## Luật lý do (code kiểm)
Giá trị **hiếm** hoặc **nổi bật** (marked, không phải nền) phải có `cite`: `LIFE <số>`, `IDENTITY <trường>`, hoặc `SOUL` (chỉ
cho `resting_face`, `posture`, `gait`). Mục được dẫn phải tồn tại và **phải mang một nguyên nhân của giá trị** (không còn miễn
cho nguyên nhân chung): `IDENTITY Age` mang ageing/hormones (45+) hoặc youth (< 30), Nationality/Hometown mang
genetics/climate, SOUL mang temperament/stress/low-mood. Lời giải thích (`why` + ý bước 1) không được nhận một nguyên nhân cụ
thể (injury, illness, alcohol...) mà mục được dẫn và facts không cho thấy: "đục thủy tinh thể" dẫn LIFE 5 (bão) bị từ chối;
dẫn IDENTITY Age thì qua; nhưng nói "from an old injury" thì bị từ chối. Ví dụ "dragging one foot" (illness)
dẫn LIFE 5 (bão) → bị từ chối. Tối đa một nét hiếm không có LIFE giải thích. Menu bước 2 ghi sẵn lý do hợp lệ cạnh mỗi nét hiếm/nổi bật
(`cite: LIFE 1 / IDENTITY Occupation`, hoặc `cite: none in your files`) để Gemma khỏi dẫn sai (lần chạy 3 dẫn STYLE/SOUL nên bị bỏ 3 nét).

## Thêm một giá trị
1. `python -I kb.py find "cụm tiếng anh"` để chắc không trùng nghĩa.
2. Thêm một dòng vào `catalog/<ô>.jsonl` (id `ô.slug[-m|-f]`), thêm nghĩa vào `vi.jsonl`. Ô dễ mâu thuẫn thì ghi `dims`/`regions`
   (mặt: `fat` cho má hóp/cằm đôi, `lines` nếp nhăn, `scalp` tóc/hói, `grey` tóc bạc, `teeth` số răng). Có điều kiện đời sống thì
   ghi `needs`/`fit`. Ô `marks`: cụm có `{loc}`, ghi `locs` (nhóm `face`, `neck`, `arms`, `torso`, `legs` hoặc chỗ cụ thể).
3. `python -I kb.py build`.

**Id không bao giờ đổi tên, xóa hay dùng lại.** Gộp: `"status": "merged", "into": [...]`; tách: `"split"`; bỏ: `"deprecated"`.
Sửa cụm từ thì giữ id, tăng `rev`. `check` báo lỗi nếu id trong `ids.lock` biến mất.

## Thêm một nguồn
1. Dòng mới trong `sources.jsonl` (chỉ nguồn miễn phí: `license_needed: false`, ghi `terms`).
2. Thẻ vào `evidence/<id nguồn>.jsonl` (`id`, `source`, `kind`, `text` diễn giải ngắn, `loc`).
3. Sửa từng ô bị ảnh hưởng (`ev`, `freq` với `basis: stat` phải có `p`). 4. `python -I kb.py build`.

## Kiểm và dựng
```
python -I kb.py check     # lược đồ, từ vựng đóng (cả facets, needs, fit, locs), chữ cấm, căn cứ, ids.lock, mỗi ô x giới x dải
                          # tuổi đúng một nền, nền không mâu thuẫn, golden tests, ngân sách menu
python -I kb.py build     # kiểm rồi ghi kb.json, ids.lock, report.md
python -I kb.py menu male 70 --tags poor,sea,plain-diet teeth marks   # xem menu theo facts + ước lượng token
python -I kb.py facts ../lao_bay                                      # code đọc được gì từ hồ sơ
```
Mâu thuẫn mà Luân hồi (LLM) bắt được còn code bỏ sót nằm ở `experiments/logs/rule_candidates.jsonl` (`code_found: false`):
đọc định kỳ để thêm `dims`/`regions`/luật và một ca vào `tests/golden.jsonl`.
