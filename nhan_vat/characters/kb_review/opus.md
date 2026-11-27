# Review tổ chức kho nét (KB) cho nhan_vat — Opus

Đã đọc: KB_DESIGN.md, LOOK_SLOTS.md, kb/body.json, kb/body_report.md, kb/src/build_body.py, experiments/luan_hoi.py, SPEC.md,
BACKLOG.md. Không gọi model, không lên mạng.

## 0. Những điều thấy trong code hiện tại (ảnh hưởng tới thiết kế)

1. **"Bình thường" nhận ra bằng đuôi id** (`is_normal`: id kết thúc bằng `normal…`). Mỗi ô chỉ có một `normal` cho mọi tuổi:
   `back.normal` = "ordinary straight back" được gắn `[normal]` cho cả người 70 tuổi. Đây chính là lỗi "bình thường theo tuổi".
2. **`freq` là một nhãn duy nhất** cho mọi giới/tuổi/dân tộc. `back.kyphosis` ghi `common` nhưng thật ra chỉ phổ biến ở người già;
   `rule_errors` lại dùng `freq == common` để quyết định "near-plain" → nhập nhằng hai khái niệm: **mức phổ biến** (bao nhiêu người
   có) và **độ nổi** (người khác có để ý không). Cần tách.
3. **Sổ nét (`registry.json`) đếm theo id giá trị**, không ghi phiên bản kho. Đổi tên hay xóa id là sổ cũ hỏng âm thầm.
4. **Luật mâu thuẫn hoàn toàn do LLM** (`SYS_CHECK`), tốn thêm một lời gọi mỗi vòng và không lặp lại được.
5. **Nhóm gọi model cố định** (`GROUPS` A / D / EFG). Nhóm D của nữ đã ~100 dòng menu (~2k token) + hồ sơ nhân vật; thêm mặt
   (19 ô) là vỡ ngân sách 3–4k nếu không có bộ chia tự động.
6. **Trích dẫn `kXXXXX` trỏ sang file card của ebook_maker** (`build_body.py` đọc thẳng `ebook_maker/work/...`). Kho mới chưa tự
   đứng được.
7. **30/471 cụm có chữ chỉ nguyên nhân** ("from heavy lifting", "from decades of stooped fieldwork"). SPEC nói LOOK "không lý do";
   nguyên nhân đã có ở trường `causes`, nên cụm chỉ nên tả cái mắt thấy.

## 1. Thiết kế 4 tầng có đúng cho agent không?

Hướng đúng (tách bằng chứng khỏi giá trị, có id ổn định, dựng ra thứ cho máy ăn). Nhưng nên chỉnh:

| Tầng | Đề nghị | Lý do |
|---|---|---|
| `sources/` | **Giữ, gọn lại thành 1 file** `sources.jsonl` | Vài chục nguồn, mỗi nguồn một dòng; file gốc để ngoài repo, ghi sha256 |
| `cards/` | **Giữ**, một file mỗi nguồn `cards/<source>.jsonl`; thêm loại `stat` có số liệu máy đọc được | Số liệu nhân trắc phải để code tính tần suất, không để LLM đọc lại văn |
| `catalog/` | **Giữ**, một file mỗi ô | Đơn vị cập nhật tự nhiên của agent chưng cất là một ô |
| `views/` | **Bỏ dạng thư mục file**. Thay bằng thư viện truy vấn `kbq.py` + một file dựng `build/kb.json` | Menu theo (giới × tuổi × dân tộc × sổ nét) là phép lọc vài mili giây trên ~vài nghìn bản ghi. Lưu sẵn thành file thì bùng tổ hợp và dễ cũ |
| **thêm** `vocab.json` | danh sách đóng: ô, facet, dải tuổi, cây dân tộc, nguyên nhân, chiều ẩn (dims), vùng cơ thể, thẻ bối cảnh | Code kiểm được mọi thẻ; agent không tự bịa thẻ mới |
| **thêm** `rules.jsonl` | luật loại trừ/đòi hỏi giữa giá trị | Xem mục 5 |
| **thêm** `build/` (sinh ra) | `kb.json` (giá trị đang dùng + bảng chuyển id + luật), `report.md`, `ids.lock` | Một artefact duy nhất mà Luân hồi load; `ids.lock` để phát hiện id bị xóa |

Không cần tầng "baseline" riêng: đánh dấu ngay trên giá trị (`baseline_for`), xem mục 3 và 7.

**Facet cho ô nhiều trục.** Ô mặt như `eyes` (to/nhỏ; một mí/hai mí; xếch/rủ; sâu/lồi), `nose`, `brows`, `mouth` có nhiều trục độc
lập. Một giá trị gộp nhiều trục (ví dụ "small monolid upturned eyes") làm menu nổ tổ hợp và trần dùng lại vô nghĩa. Đề nghị chia
thành **facet**: `eyes.size`, `eyes.lid`, `eyes.tilt`, `eyes.set`, `eyes.depth`; mỗi facet có baseline riêng, mỗi nhân vật một giá
trị mỗi facet. Menu vẫn trình theo ô (các facet của `eyes` đứng chung) để model thấy bức tranh. Ô thân hiện tại đa số là một trục,
giữ nguyên.

**`marks` nhiều giá trị.** Một pick = (id loại dấu, id vị trí) với vị trí lấy từ `vocab.regions`. Sổ nét đếm theo id loại dấu.

## 2. Định dạng lưu và chỗ đặt

**Nguồn sự thật: JSONL, một file mỗi ô, một giá trị mỗi dòng.** Lý do theo cách dùng:
- *Cập nhật*: agent chưng cất làm việc theo từng ô; một file ô ~20–60 dòng (2–6k token) đọc trọn được trong một lượt. Sửa một
  giá trị = sửa một dòng → git diff gọn, review được, ít xung đột khi hai phiên cùng sửa hai ô khác nhau.
- *Truy vấn*: không truy vấn thẳng nguồn; `build` gom tất cả thành `build/kb.json` (<1–2 MB kể cả khi có mặt/tóc/dấu), Python load
  vào bộ nhớ một lần. Lọc theo thẻ trên vài nghìn bản ghi nhanh hơn SQLite và không phụ thuộc gì.
- *Không chọn SQLite làm nguồn*: file nhị phân, không diff/merge được, agent sửa qua SQL dễ sai. Chỉ cân nhắc SQLite **như artefact
  dựng** khi vượt ~20k giá trị hoặc cần truy vấn ad-hoc.
- *Không chọn mỗi giá trị một file*: hàng nghìn file, khó duyệt, khó review.
- *Bỏ định dạng `id|sex|phrase|...`* của `kb/src/*.txt`: gọn khi soạn nhưng không chứa được tần suất theo tầng, dims, vùng,
  trạng thái. Chuyển một lần sang JSONL bằng script.

**Chỗ đặt** (giữ trong `characters/kb/`, vì luan_hoi.py đã trỏ vào đó):

```
characters/kb/
  vocab.json              danh sách đóng (ô, facet, dải tuổi, cây dân tộc, causes, dims, regions, ctx tags)
  sources.jsonl           mỗi nguồn một dòng
  cards/<source>.jsonl    thẻ chưng cất, một file mỗi nguồn
  catalog/<slot>.jsonl    giá trị, một file mỗi ô (facet nằm trong file của ô)
  rules.jsonl             luật giữa giá trị
  tests/golden_conflicts.jsonl   các cặp phải bị bắt / phải được cho qua
  tools/kb.py             CLI: migrate | check | build | find | stats
  kbq.py                  thư viện truy vấn cho luan_hoi.py và các agent
  build/kb.json           SINH RA (commit, có kb_version = hash nội dung)
  build/report.md         SINH RA: độ phủ, % có nguồn, thay đổi so với bản trước
  build/ids.lock          SINH RA: mọi id từng tồn tại
```
File gốc của nguồn (CSV, PDF, ảnh) để **ngoài repo**, đường dẫn tương đối theo biến `KB_RAW_ROOT`, kèm sha256 trong
`sources.jsonl`. Commit `build/kb.json` để mọi lần chạy thí nghiệm tái lập được theo `kb_version`.

## 3. Schema

### Giá trị (một dòng trong `catalog/<slot>.jsonl`)
```json
{"id": "back.stooped-old", "slot": "back", "facet": null, "sex": "any", "age": [60, 120],
 "phrase": "back permanently bent forward at the waist", "vi": "lưng còng gập ngang hông",
 "salience": "marked",
 "freq": [{"when": {}, "cls": "rare", "basis": "est"},
          {"when": {"band": "elderly"}, "cls": "uncommon", "basis": "est"},
          {"when": {"band": "elderly", "ctx": "manual-labour"}, "cls": "common", "basis": "est"}],
 "baseline_for": [],
 "dims": {"age_look": [2, 3]},
 "regions": ["upper_back", "lower_back"],
 "causes": ["manual-labour", "ageing"],
 "ctx_needs": {}, "ctx_never": {"era": []},
 "concept": "back.bent",
 "evidence": [{"card": "c.ebm.k00089", "support": "related"}],
 "status": "active", "since": "2026-11-24"}
```
- `phrase`: tiếng Anh, 3–10 chữ, **chỉ cái mắt thấy** (không from/after/due to), không quần áo/kiểu tóc/đồ vật/chữ đẹp. Đây là
  thứ duy nhất (cùng id) đưa vào model và prompt ảnh. `vi` chỉ cho người xem (viewer), không gửi model.
- `age`: **khoảng tuổi số** thay cho danh sách dải; code tự quy ra dải. Số liệu thật đến theo khoảng tuổi không khớp dải của mình.
- `salience`: `plain | mild | marked` — độ nổi, quyết định có được làm nét nhận diện không. Tách hẳn khỏi `freq`.
- `freq`: danh sách hàng có điều kiện (mục 4).
- `baseline_for`: các tầng (`"m.elderly"`, `"any.middle"`…) mà giá trị này là "bình thường". Thay cho đuôi `normal` trong id.
- `dims`, `regions`: dùng cho luật tự động (mục 5) và sau này cho đạo diễn suy khả năng hành động.
- `ctx_needs` / `ctx_never`: thẻ bối cảnh từ IDENTITY (nghề, mức sống, thời đại). Code lọc cứng được phần lớn "không thể có"
  (ngư dân nghèo không bọc răng sứ) trước khi tới Luân hồi.
- `concept`: gom các bản nam/nữ hoặc các bản theo tuổi của cùng một nét (để thống kê, ánh xạ số liệu, đa dạng chéo giới).

### Thẻ (một dòng trong `cards/<source>.jsonl`)
```json
{"id": "c.ncdrisc.0012", "src": "ncdrisc_height", "kind": "stat",
 "claim": "Mean height of Vietnamese men born 1950-1954, measured as adults.",
 "loc": "country file, rows VNM male 1950-1954",
 "data": {"measure": "height_cm", "pop": "vietnam", "sex": "male", "birth": [1950, 1954], "mean": 0, "sd": 0, "n": null},
 "tags": ["height"], "status": "active"}
```
`kind`: `stat` (có `data` máy đọc), `fact` (một câu diễn giải ≤ 40 chữ), `vocab` (danh sách thuật ngữ từ phiếu nhận dạng/danh mục
phác họa, mỗi thuật ngữ kèm định nghĩa ngắn), `obs` (quan sát từ ảnh có nhãn). Chỉ diễn giải ngắn, không chép đoạn dài từ sách.
Thẻ sách cũ nhập với id `c.ebm.k00089` (giữ số cũ để truy ngược), chỉ nhập ~200 thẻ đang được trích.

### Nguồn (một dòng trong `sources.jsonl`)
`{"id","title","kind": "book|dataset|stats|manual|paper","url","terms": "public domain | CC BY 4.0 | research-only ...",
"free": true, "retrieved": "2026-11-24", "raw": "relative/path", "sha256", "covers": ["height","fat"], "notes"}` —
`check` từ chối nguồn không có `terms` hoặc `free != true`.

### Id ổn định; gộp, tách, bỏ
- Dạng `slot[.facet].slug[-m|-f]`, chữ thường, gạch nối. **Không bao giờ đổi tên, không bao giờ xóa dòng, không bao giờ dùng lại.**
- **Gộp** A vào B: dòng A thành `{"status": "merged", "into": "B", ...}` (giữ phrase cũ).
- **Tách** A thành B, C: A thành `{"status": "split", "into": ["B", "C"]}`.
- **Bỏ**: `{"status": "deprecated", "reason": "..."}`; không lên menu nhưng vẫn tra được cụm.
- `kbq.resolve(id)` đi theo `into` (kiểm không vòng lặp, đích phải `active`). Khi đếm trần dùng lại: id đã gộp đếm cho B; id đã
  tách **đếm cho mọi con** (thận trọng, giữ đa dạng).
- `check` so với `build/ids.lock`: id biến mất → lỗi.
- `registry.json` và `LOOK.*.json` ghi thêm `kb_version`; LOOK vẫn giữ bản chụp `phrases` (đã có) nên luôn vẽ lại được dù kho đổi.
- Không cần file redirect riêng: tombstone nằm ngay trong file ô, một chỗ để tìm.

## 4. Mức phổ biến

**Nguyên tắc:** nhãn `common/uncommon/rare` là thứ model thấy; con số `p` chỉ có khi có thẻ `stat`. **LLM không bao giờ bịa `p`**;
ước lượng của agent chỉ được ghi nhãn với `basis: "est"`.

- **Hàng có điều kiện**: `when` có thể chứa `sex`, `band` (hoặc `age: [a,b]`), `eth` (nút trong cây dân tộc), `ctx` (thẻ nghề/mức
  sống). Mỗi hàng: `cls`, `basis` (`stat | est | general`), tùy chọn `p`, `pop`, `cards`.
- **Phân giải** cho một nhân vật: lấy hàng khớp **cụ thể nhất** (nhiều khóa nhất); hòa thì `stat` thắng `est`. Dân tộc đi ngược
  cây: `kinh → vietnam → southeast_asia → asia → global`. Hàng `when: {}` là mặc định bắt buộc.
- **Ngưỡng từ số liệu** (cố định trong `vocab.json`, để đổi một chỗ): `common ≥ 10%`, `uncommon 2–10%`, `rare < 2%` số người trong
  tầng có nét đó. `build` tự tính `cls` từ `p`; agent không gõ tay.
- **Đại lượng liên tục** (chiều cao, BMI/mỡ, có thể sải vai): định nghĩa giá trị bằng **khoảng z-score** so với tầng của nhân vật,
  ví dụ `height.short-m: {"metric": "height_z", "range": [-2, -1]}`. Thẻ `stat` cho mean/sd theo giới × **năm sinh** × quốc gia.
  Tần suất suy thẳng từ phân phối chuẩn (~14% cho [-2,-1], ~2% cho < -2). Cách này giải đúng "thấp so với người cùng quốc tịch" và
  hiệu ứng thế hệ (người Việt sinh 1950 thấp hơn người sinh 2000). Nguồn miễn phí hợp: NCD-RisC (chiều cao theo năm sinh, theo
  nước), NHANES (public domain, đo cơ thể chi tiết nhưng là dân Mỹ — chỉ dùng cho tỉ lệ/hình dạng, không cho mức tuyệt đối).
- **Nhãn hiển thị cho model** tính theo tầng: Luân hồi và nhân vật thấy `common/uncommon/rare` **của chính tầng nhân vật**, và thẻ
  `[normal]` lấy từ `baseline_for`, không từ id.
- Báo cáo `build/report.md` ghi tỉ lệ `basis` theo ô để biết chỗ nào còn đoán.

## 5. Luật loại trừ / tương thích

Ba cơ chế, rẻ trước đắt sau, tất cả do **code** áp:

1. **Chiều ẩn (dims) dạng khoảng** — gánh phần lớn mâu thuẫn thân. `vocab.dims`: `adiposity` (-3..+3), `muscularity` (-2..+3),
   `frame` (-2..+2), `age_look` (0..3), `sun` (0..3), `labour` (0..3), `grooming` (0..3). Mỗi giá trị (không bắt buộc) ràng một vài
   chiều thành khoảng: `frame.stocky-m: {"frame": [1,2], "adiposity": [-1,3]}`, `chest.ribs-m: {"adiposity": [-3,-2]}`. Một bộ pick
   hợp lệ khi **giao các khoảng trên mỗi chiều khác rỗng**. "stocky frame" + "ribs showing" bị bắt mà không cần viết luật cặp. Gắn
   dims là việc của agent chưng cất trên từng giá trị, ở ngay dòng đó → cập nhật cục bộ, không phải sửa bảng cặp N².
2. **Vùng cơ thể (regions)** — chống "tả cái bụng hai lần". Hai pick không baseline từ hai ô khác nhau cùng phủ một vùng → báo
   "double description", trừ khi `rules.jsonl` có cặp `compatible`.
3. **Luật tường minh** trong `rules.jsonl`, cho những gì hai cơ chế trên không nói được:
   `{"id": "R0007", "kind": "exclude|requires|discourage", "a": "<selector>", "b": "<selector>", "why": "...", "since": "..."}`,
   selector là `id`, `slot:*`, `tag:<cause>`, `ctx:<tag>`. `discourage` chỉ đẩy xuống cuối menu, không cấm. Luật cũng có id ổn định
   và trạng thái như giá trị.

**Code áp ở đâu:**
- *Lọc menu* (`kbq.menu`): bỏ giá trị trái `age`, `sex`, `ctx_needs/ctx_never`, luật `exclude` với ctx; nếu đã có pick khóa sẵn
  (ví dụ chạy lại một ô, hoặc thứ tự A → D → EFG), bỏ luôn giá trị xung đột dims với pick đó.
- *Kiểm sau khi chọn* (`kbq.check(picks, ctx)`): trả danh sách lỗi có câu giải thích máy sinh, ví dụ
  `"adiposity: frame.stocky-m needs -1..3, chest.ribs-m needs -3..-2"` → đưa thẳng vào vòng "FIX THESE PROBLEMS".
- *Giai đoạn chuyển tiếp*: giữ `SYS_CHECK` của LLM làm lưới thứ hai, **ghi log mỗi xung đột LLM bắt mà code không bắt**; agent chưng
  cất định kỳ duyệt log đó để thêm dims/luật. Khi tỉ lệ bỏ sót ~0 thì tắt lời gọi LLM (tiết kiệm một call mỗi vòng trên máy dùng chung).
- *Kiểm chính kho*: mọi tổ hợp baseline của một tầng phải qua `check` (baseline không được tự mâu thuẫn); `tests/golden_conflicts.jsonl`
  phải bị bắt đúng.

## 6. Quy trình khi có nguồn mới

1. **Đăng ký nguồn**: thêm dòng `sources.jsonl` (điều khoản, sha256, đường dẫn file gốc ngoài repo).
2. **Ra thẻ**:
   - Bảng số (nhân trắc, khảo sát): **script** đọc CSV → thẻ `stat`. Không cho LLM chép số.
   - Văn bản (y học lao động, phiếu DVI, danh mục phác họa): Opus đọc từng phần → thẻ `fact`/`vocab` ngắn, có `loc`.
   - Bộ ảnh có nhãn thuộc tính: script đếm nhãn → thẻ `obs` với tỉ lệ theo tầng (nếu bộ có nhãn tuổi/giới/dân tộc).
3. **Chưng cất từng ô**: với mỗi ô bị nguồn chạm tới, Opus nhận *file ô hiện tại + thẻ mới liên quan* (lọc bằng `tags`) và sửa file ô:
   thêm giá trị, thêm `evidence`, chuyển `basis general → book/stat`, thêm hàng `freq`, gộp/tách theo luật tombstone. Trước khi thêm,
   chạy `kb.py find "<phrase>"` (so trùng bằng Jaccard chữ + cùng ô/giới) để tránh trùng nghĩa.
4. **`kb.py check`** (chặn commit nếu lỗi):
   - schema, thẻ nằm trong `vocab`, id đúng dạng, không trùng, không mất so với `ids.lock`, tombstone trỏ tới id `active`, không vòng;
   - cụm: 3–10 chữ, ASCII tiếng Anh, không chữ đẹp, không chữ nguyên nhân (`from|after|due to|because`), không từ quần áo/kiểu tóc/đồ vật;
   - mọi `evidence.card` tồn tại; mọi thẻ trỏ tới nguồn có `free: true`; `basis: stat` phải có thẻ `stat`;
   - **ma trận độ phủ**: mỗi (ô/facet × giới × dải tuổi) có đúng một baseline và ≥ 8 giá trị dùng được, ≥ 1 `uncommon`, ≥ 1 `rare`;
   - luật: selector trỏ tới thứ tồn tại; baseline của mỗi tầng qua `check`; golden conflicts đúng;
   - ngân sách: menu đầy đủ của tầng lớn nhất, ở dạng render, không vượt ngân sách mỗi ô (mục 7).
5. **`kb.py build`**: dựng `build/kb.json` (chỉ `active` + bảng resolve + freq đã phân giải sẵn theo tầng), `report.md` (độ phủ, %
   theo `basis`, danh sách thay đổi so với bản trước), `ids.lock`, `kb_version`.
6. **Hồi quy nhỏ**: chạy `luan_hoi.py --dry` cho 2–3 nhân vật mẫu (trẻ/già, nam/nữ) để xem số token mỗi call; không cần gọi model.

Thay đổi nhỏ (vài giá trị) đi đúng quy trình đó nhưng chỉ đụng một hai file ô; không dựng lại thẻ.

## 7. Giao diện truy vấn cho agent

`kbq.py` (code gọi; model chỉ thấy text render):

| Hàm | Trả về | Ghi chú |
|---|---|---|
| `ctx_from_identity(text) -> Ctx` | sex, age, band, eth_chain, birth_year, era, ctx tags (nghề, mức sống) | Một chỗ duy nhất parse IDENTITY |
| `baseline(slot, ctx) -> Value` | giá trị "bình thường" **của tầng** | Giải bài người 70 tuổi |
| `menu(slot, ctx, registry=None, locked=None, limit=20) -> [Item]` | id, phrase, freq_cls (theo tầng), salience, is_baseline, typical_for_age, used | Đã lọc cứng + luật + trần dùng lại |
| `plan_calls(slots, ctx, budget_tokens=3500, profile_tokens=N) -> [[slot]]` | các nhóm ô cho từng lời gọi | Thay `GROUPS` cố định |
| `render(menus, mode="luan_hoi"\|"character") -> str` | text gọn | Luân hồi thấy `causes`; nhân vật không cần |
| `check(picks, ctx) -> [Conflict]` | lỗi có câu giải thích | dims + regions + rules |
| `resolve(id) -> [id]` | id hiện hành | dùng khi đọc registry/LOOK cũ |
| `phrase(id)` / `prompt(picks, ctx)` | cụm / đoạn prompt ảnh theo thứ tự A → H | chỉ ô không baseline + ô bắt buộc |
| `capabilities(picks)` (sau) | sức vác, tốc độ, dẻo dai từ dims | cho đạo diễn |
| `evidence(id)` | thẻ + nguồn | chỉ cho agent chưng cất/người xem |

**Kích thước:** mỗi dòng menu ≤ ~18 token (`- back.stooped-old | back permanently bent forward at the waist | uncommon`); mỗi ô ≤ 20
dòng (baseline + 19); mỗi lời gọi ≤ ~100 dòng menu (~1.8k token) + hồ sơ ≤ ~1.2k → dưới 3.5k. Khi vượt, `menu` cắt theo thứ tự ưu
tiên: baseline → nét "typical for age" → chưa ai dùng → giữ ít nhất 1 `rare` và 2 `uncommon` → phần còn lại xoay vòng theo seed
(để các nhân vật khác nhau thấy các phần khác nhau của kho lớn).

**Bài toán "bình thường theo tuổi"** giải bằng ba thứ cùng lúc:
1. `baseline_for` theo tầng: `back.normal` (baseline cho young/adult/middle) và một giá trị mới `back.normal-old` "slightly rounded
   upper back of an older person" (baseline cho elderly). Tương tự cho `skin`, `posture`, `gait`, `muscle`, `hands`… Ô nào chưa có
   baseline cho một tầng → `check` báo lỗi độ phủ.
2. `freq` theo tầng: còng lưng là `common` ở người già làm ruộng nhưng `rare` ở 25 tuổi; nhãn model thấy là nhãn của tầng.
3. Cờ `typical_for_age` (freq tầng = common và salience ≠ marked): được dùng ở `extras` thoải mái, nhưng **không tính là nét nhận
   diện** — một người 75 tuổi lưng hơi còng không phải "nét người khác nhớ". Luật `extras` trong `rule_errors` đổi từ
   `freq == common` sang `salience in (plain, mild)` hoặc `typical_for_age`.

Phụ: prompt ảnh bỏ ô baseline như hiện nay là đúng (máy vẽ tự vẽ người 70 tuổi có dấu tuổi), nhưng **menu và nhãn `[normal]`**
phải đúng tầng, nếu không model sẽ tưởng "lưng thẳng" là mặc định và chọn còng làm nét nổi.

## Kết luận

Ý tưởng 4 tầng đúng hướng nhưng **tầng `views/` là thừa**, còn **thiếu ba thứ quan trọng hơn**: từ vựng đóng (`vocab.json`), luật
máy kiểm được (dims dạng khoảng + regions + `rules.jsonl`), và baseline/tần suất **theo tầng** thay vì một nhãn cho mọi người.
Lưu bằng JSONL mỗi ô một file, dựng ra một `kb.json` duy nhất, truy vấn qua `kbq.py`; id không bao giờ đổi/xóa, gộp/tách bằng
tombstone, sổ nét ghi `kb_version`.

### Bản tối thiểu nên làm ngay
1. `tools/kb.py migrate`: chuyển `body.json` → `catalog/<slot>.jsonl` (giữ nguyên id), `ages` → `age` số, `freq` → một hàng mặc định
   `basis: est|general`, thêm `salience` (suy tạm: normal → plain, common → mild, còn lại → marked), `status: active`. Sửa 30 cụm có chữ
   nguyên nhân.
2. `vocab.json` nhỏ: dải tuổi, cây dân tộc (global → asia → southeast_asia → vietnam → kinh…), causes hiện có, 5 dims
   (adiposity, muscularity, frame, age_look, labour), regions thân.
3. `baseline_for` cho 18 ô thân × giới × 4 dải; thêm giá trị baseline cho người già ở những ô cần (back, posture, gait, body_skin,
   muscle, arms, hands). Bỏ `is_normal` theo đuôi id.
4. `sources.jsonl` + `cards/ebm_books.jsonl` (chỉ ~200 thẻ đang trích, diễn giải ngắn) → kho tự đứng, bỏ đường dẫn sang ebook_maker.
5. Gắn `dims` + `regions` cho các ô dễ mâu thuẫn (frame, fat, muscle, fat_where, chest, waist_belly, back, arms, legs);
   `rules.jsonl` + `tests/golden_conflicts.jsonl` khởi đầu ~10 cặp.
6. `kbq.py` với `ctx_from_identity`, `baseline`, `menu`, `plan_calls`, `render`, `check`, `resolve`; sửa `luan_hoi.py` dùng nó,
   giữ `SYS_CHECK` song song và log chỗ khác nhau; registry ghi `kb_version`.
7. `kb.py check` + `build` (kiểm như mục 6, ma trận độ phủ, `ids.lock`, `report.md`).

Để sau: thẻ `stat` chiều cao theo năm sinh và z-score; hàng `freq` theo tầng từ số liệu; facet cho mặt/tóc; `marks` (loại × vị trí);
`capabilities`; SQLite chỉ khi kho vượt ~20k giá trị.
