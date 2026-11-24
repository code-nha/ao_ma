# Kho nét THÂN (body.json), bản thử 1

> **ĐÃ BỊ THAY THẾ (2026-11-24).** `body.json` và `src/build_body.py`, `src/body_*.txt` là kho v1, giữ lại để tra cứu, không còn
> được dùng. Kho hiện hành là v2: `catalog/*.jsonl` + `vocab.json`, dựng bằng `kb.py build`, truy vấn qua `kbq.py` (xem `README.md`).
> Mọi id của v1 giữ nguyên trong v2.

File: `kb/body.json`, 18 ô (nhóm A, D, E, F, G), **471 giá trị**. JSON hợp lệ (đã load bằng python). Mọi ô có giá trị `thường`
(`.normal-m` / `.normal-f`, hoặc `.normal` cho cả hai giới). Không cụm nào dùng beautiful/handsome/attractive/perfect/flawless;
mọi cụm 3–10 chữ, không quần áo, không kiểu tóc, không đồ vật.

## Số giá trị theo ô
Cột "Nam"/"Nữ" = số giá trị dùng được cho giới đó (riêng giới + `any`). "Sách" = tỉ lệ giá trị có trích card.

| ô | nhóm | chỉ nam | chỉ nữ | any | **Nam** | **Nữ** | sách |
|---|---|---|---|---|---|---|---|
| height | A | 8 | 7 | 0 | 8 | 7 | 60% |
| frame | A | 9 | 8 | 0 | 9 | 8 | 94% |
| fat | A | 15 | 13 | 0 | 15 | 13 | 78% |
| muscle | A | 18 | 14 | 0 | 18 | 14 | 71% |
| fat_where | A | 12 | 15 | 0 | 12 | 15 | 85% |
| shoulders | D | 16 | 14 | 0 | 16 | 14 | 83% |
| chest | D | 16 | 18 | 0 | 16 | 18 | 82% |
| waist_belly | D | 15 | 17 | 0 | 15 | 17 | 87% |
| hips | D | 14 | 16 | 0 | 14 | 16 | 83% |
| back | D | 2 | 2 | 13 | 15 | 15 | 70% |
| body_skin | D | 20 | 20 | 0 | 20 | 20 | 45% |
| arms | E | 15 | 13 | 0 | 15 | 13 | 71% |
| hands | E | 4 | 2 | 20 | 24 | 22 | 34% |
| nails | E | 1 | 2 | 13 | 14 | 15 | 0% |
| legs | F | 17 | 17 | 0 | 17 | 17 | 44% |
| feet | F | 1 | 1 | 18 | 19 | 19 | 15% |
| posture | G | 2 | 2 | 19 | 21 | 21 | 91% |
| gait | G | 1 | 2 | 19 | 20 | 21 | 54% |

Các ô khác nhau theo giới (chest, waist_belly, hips, arms, legs, shoulders, body_skin, fat, muscle, fat_where, height, frame)
đều viết tách nam/nữ, không có cụm unisex.

## Nguồn
- **309/471 (66%)** giá trị có trích ít nhất một card (`kXXXXX`), **162 (34%)** là `general` (kiến thức chung).
- Card được dùng đến từ 8 sách (file card chỉ có 8 slug, không phải 11): aesthetic surgery (180 lượt trích), magic garment (62),
  photographer's guide to posing (56), figure drawing / Loomis (54), anatomy for sculptors (42), reading faces (26), force (23),
  picture perfect posing (20).
- Lưu ý: trích dẫn ở mức "card ủng hộ nét này", không phải card mô tả đúng từng chữ. Nhiều card sách posing/aesthetic nói
  về cách chụp hoặc chuẩn đẹp; mình chỉ trích khi card mô tả được hình dạng cơ thể (ví dụ card về ngực xệ sau sinh, mỡ hông,
  bụng tách cơ sau sinh). Card build.json là bản nén của chính các card này nên không trích riêng.

## Lỗ hổng chính
1. **Sách mỏng về người lao động và người châu Á.** Gần như toàn bộ nét lao động (vai chai do gánh, lưng còng do làm đồng,
   chân đất, bàn chân bè, tay ngâm nước, chân người đạp xích lô, dáng đi quen sông nước) là `general`. Chỉ có 1 card
   (k00089, "lean hard-muscled men do hard physical work") nói về lao động.
2. **Móng (0%) và bàn chân (15%)** hầu như không có trong sách; toàn bộ là kiến thức chung.
3. **Da thân (45%)**: sách chỉ có rạn da, da chùng, da trắng/đỏ. Lông người châu Á (thường ít lông), lang ben, rôm sảy,
   cháy nắng theo vệt áo, đồi mồi là `general`.
4. **Tần suất (`freq`)** là ước lượng, không có số liệu theo dân tộc; nhất là chiều cao "so với người cùng quốc tịch" chưa
   có mốc số cho người Việt.
5. **Bệnh và tật** còn mỏng: chỉ có vài nét (vẹo cột sống, bạch biến, vảy nến, ngón dùi trống, phù chân, một chân teo).
   Chưa có nét do tai nạn lao động, di chứng bại liệt, chất độc da cam; những thứ này có thể thuộc ô `marks` (nhóm H).
6. **height, frame** ít giá trị (7–9 mỗi giới), đúng theo yêu cầu, nhưng chưa có giá trị tỉ lệ (thân dài chân ngắn đã nằm ở `legs`).
7. Một số giá trị `gait`/`posture` khó thấy trong ảnh tĩnh (đi lê, kéo chân); cần cụm "mid-stride…" khi ghép prompt.

## Ghi chú kỹ thuật
Nguồn soạn dạng dòng `id|sex|phrase|vi|freq|ages|causes|cards` và script dựng/kiểm tra nằm ở scratchpad phiên này
(`build_body.py`, `body_a.txt`, `body_d.txt`, `body_efg.txt`); script kiểm: trùng id, chữ cấm, số chữ 3–10, card tồn tại,
mỗi ô có giá trị `thường`.
