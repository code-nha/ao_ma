# Review tổ chức kho nét cho nhan_vat (Fable)

Đã đọc: `KB_DESIGN.md`, `LOOK_SLOTS.md`, `SPEC.md`, `BACKLOG.md`, `kb/body.json`, `kb/body_report.md`, `kb/src/build_body.py`,
`experiments/luan_hoi.py`, `experiments/logs/luan_hoi.jsonl`, `stories/demo/registry.json`. Không gọi model, không dùng mạng.
Mọi con số "đề xuất" dưới đây (ngưỡng, kích thước menu) là điểm khởi đầu để chỉnh, chưa đo.

## 0. Những gì file hiện tại cho thấy (căn cứ của review)

| Quan sát | Ở đâu | Hệ quả cho thiết kế |
|---|---|---|
| Lần gọi nhân vật đã tốn **5.962–6.355 token đầu vào** chỉ với 18 ô thân; Luân hồi nhóm EFG 3.354–3.407 | `logs/luan_hoi.jsonl` | Vượt trần 3–4k ngay bây giờ. Thêm mặt, tóc, dấu vết (40 ô) thì cách "đưa hết ứng viên một lần" không dùng được. Giao diện truy vấn phải đóng gói theo ngân sách token. |
| Lão Bảy (nam, nhóm elderly) có `back.normal` = "ordinary straight back" cùng `posture.stooped-old` | `registry.json` | Đúng lỗi "bình thường theo tuổi": ô không nhắc tới tự nhận một cụm `normal` chung, mâu thuẫn với ô khác mà không luật nào bắt. |
| `freq` là một nhãn duy nhất cho mọi tuổi; `back.kyphosis` ghi `common` chỉ vì giới hạn ở elderly | `body.json` | Tần suất phải theo ngữ cảnh (giới, tuổi, dân tộc), không gắn cứng vào giá trị. |
| `is_normal()` nhận ra giá trị thường bằng tiền tố id `normal` | `luan_hoi.py` dòng 73 | Vai trò "nền" phải là trường dữ liệu, không nằm trong tên. |
| `build_body.py` đọc card từ `C:/Users/khoa/code_nha/ebook_maker/...` và ghi ra đường dẫn tuyệt đối | `kb/src/build_body.py` dòng 3, 37 | Trái ràng buộc "kho mới tự đứng được". Phải chép các card đang dùng sang kho mới. |
| `causes` có 60 thẻ tự do, khoảng 30 thẻ chỉ xuất hiện 1–2 lần (`busy`, `status`, `growth`, `custom`…) | `body.json` | Code không lọc được theo thẻ tự do. Cần bảng thẻ đóng. |
| Sổ nét lưu id trần, không ghi phiên bản kho | `registry.json` | Gộp hay tách giá trị sẽ làm sai trần dùng lại. |
| Trích dẫn chỉ ở mức "card ủng hộ nét này" | `body_report.md` | Cần ghi rõ loại quan hệ giữa giá trị và thẻ. |

## 1. Bốn tầng có hợp không

Hướng đúng, nhưng nên sửa ba chỗ.

**Giữ:** `sources`, `catalog`.

**Sửa `cards` thành `evidence`, tách hai loại:**
- thẻ chữ (trích dẫn, định nghĩa thuật ngữ, nhãn thuộc tính của bộ ảnh): JSONL;
- bảng số (nhân trắc, tỉ lệ nhãn theo giới và tuổi): CSV dạng dài. Số liệu là dữ liệu bảng, nhét vào thẻ chữ thì code không tính được.

**Bỏ `views` dưới dạng file dựng sẵn cho từng người dùng.** Menu phụ thuộc giới × tuổi × dân tộc × sổ nét của story × trạng thái thân
đã chọn; hai chiều sau thay đổi theo từng lần gọi nên không dựng trước được. Thay bằng:
- một file biên dịch duy nhất `build/kb.json` (không commit, dựng lại bằng script);
- một module Python `lookkb` làm mọi truy vấn lúc chạy (mục 7).

**Thêm bốn thứ đề xuất chưa có:**
1. `vocab.json`: danh sách đóng cho ô, nhóm, dải tuổi, quần thể, thẻ nguyên nhân, trục thân (mục 5). Mọi file khác chỉ được dùng thẻ
   có trong đây.
2. `rules.jsonl`: luật loại trừ ngoài phần trục (mục 5).
3. Bia mộ và chuyển hướng id ngay trong catalog (mục 3): không bao giờ xóa dòng.
4. `check.py` cùng bộ nhân vật mẫu để chạy thử khô (mục 6).

**Đưa tiếng Việt ra khỏi đường đi của agent.** Trường `vi` chỉ phục vụ người xem. Để ở file phụ `vi.jsonl` (id → vi); file biên dịch
cho model không chứa nó. `luan_hoi.py` hiện in `kb['slots'][s]['vi']` vào tiêu đề menu gửi cho Gemma: nên bỏ.

## 2. Định dạng lưu và chỗ đặt

**Nguồn sự thật: JSONL trong git, một file cho mỗi ô, một dòng cho mỗi giá trị, sắp theo id.**

| Kiểu truy vấn hoặc cập nhật | Vì sao JSONL theo ô hợp |
|---|---|
| Agent chưng cất sửa một ô | Đọc đúng một file 15–40 dòng (khoảng 1–2k token), không phải nạp cả kho 170 KB. |
| Thêm giá trị | Thêm một dòng; diff git là một dòng; hai phiên sửa hai ô không đụng nhau. |
| Code lọc theo thẻ | Kho cỡ 471 giá trị, lớn lên vài nghìn: nạp cả vào bộ nhớ rồi lọc bằng Python là đủ nhanh. |
| Kiểm tra | Mỗi dòng tự đủ nghĩa, kiểm từng dòng, báo lỗi theo file:dòng. |

**Không lấy SQLite làm nguồn sự thật:** file nhị phân không diff được, không review được, agent phải viết SQL để sửa. Chỉ nên thêm
SQLite như một bản dựng (`build/kb.sqlite`) khi bảng số nhân trắc lớn và cần truy vấn tùy ý. Bản đầu chưa cần.

**Không giữ dạng `id|sex|phrase|...` 8 cột của `kb/src/*.txt`:** gọn nhưng không thêm trường được (tần suất theo điều kiện, trục,
trạng thái).

**Chỗ đặt:** thư mục riêng ở gốc repo `ao_ma-nhan_vat/look_kb/`, không nằm trong `characters/`. Lý do: `characters/` chứa thư mục
theo id nhân vật (`lao_bay`, `stories`), kho là dữ liệu dùng chung cho `experiments/` và sau này cho đạo diễn. Nếu muốn ít xáo trộn
thì giữ `characters/kb/` cũng chạy được; cấu trúc bên trong mới là phần quan trọng.

```
look_kb/
  README.md            hợp đồng cho agent, tối đa một trang, tiếng Anh
  vocab.json           ô, nhóm, dải tuổi, quần thể, thẻ nguyên nhân, trục
  sources.jsonl        một dòng mỗi nguồn
  evidence/<source_id>.jsonl   thẻ chữ, mỗi nguồn một file
  stats/<source_id>.csv        bảng số dạng dài
  catalog/<slot>.jsonl         kho nét, mỗi ô một file
  rules.jsonl
  vi.jsonl
  patches/             lịch sử thao tác của agent chưng cất (mục 6)
  tools/build.py  tools/check.py  lookkb.py
  build/               không commit: kb.json, report.md
```
File gốc lớn (PDF, bộ ảnh) để ngoài repo; `sources.jsonl` ghi đường dẫn, ngày lấy, sha256 và ghi chú giấy phép.

## 3. Lược đồ, id, gộp/tách/bỏ

### Một giá trị trong catalog
```json
{"id": "back.kyphosis", "slot": "back", "role": "value", "status": "active",
 "sex": "any", "age": [65, 120], "pop": ["any"],
 "phrase": "strongly hunched old back",
 "causes": ["ageing", "illness"], "needs": [],
 "sets": {"spine": 3}, "req": {},
 "claims": ["upper_back"],
 "freq": [{"band": "u", "basis": "est"},
          {"when": {"age": [75, 120]}, "band": "c", "basis": "est"}],
 "ev": [{"c": "loomis.k00117", "rel": "describes"}],
 "since": 2, "rev": 1}
```
- `role`: `baseline` (nền, xem mục 7) hoặc `value`. Thay cho việc đoán qua tiền tố id.
- `age`: khoảng số, không dùng tên dải. Dải tuổi đổi sau này thì không phải viết lại giá trị.
- `needs`: điều kiện ngoài thân mà code kiểm được nếu IDENTITY có trường tương ứng (`wealth`, `era>=1990`, `childbirth`).
  Thiếu trường thì để Luân hồi xét.
- `sets`, `req`, `claims`: phần luật, giải thích ở mục 5.
- `ev[].rel`: `describes` (thẻ tả đúng nét này), `supports` (ủng hộ gián tiếp), `freq` (cho con số). Giá trị không có `ev` là
  kiến thức chung; không cần chữ `general`.
- `rev` tăng khi đổi `phrase`; `since` là phiên bản kho lúc thêm.

### Một thẻ căn cứ
```json
{"id": "loomis.k00117", "source": "loomis", "kind": "quote", "loc": "ch.2 p.31",
 "text": "Very tall men tend to look lanky, with long limbs.", "slots": ["height", "frame"]}
```
Thẻ số nằm trong `stats/<source>.csv`, cột: `measure, sex, age_lo, age_hi, pop, stat, value, n, year, loc`
(ví dụ `stature_cm, male, 60, 69, vn, p50, 160.2, ...`; con số trong ví dụ chỉ minh họa hình dạng).
Id thẻ = `source_id` + số thứ tự trong nguồn, không dùng lại. Các card `kXXXXX` đang trích (309 giá trị trích từ 8 sách) chép sang
`evidence/` với tiền tố nguồn để kho không còn phụ thuộc `ebook_maker`.

### Id ổn định
- Giữ dạng có nghĩa `slot.slug[-m|-f]`: agent chưng cất và người đọc log hiểu ngay.
- Ba luật cứng: id **không đổi tên**, **không dùng lại**, dòng **không bị xóa**. Đổi cụm tiếng Anh thì tăng `rev`, id giữ nguyên.
- Model nhỏ **không cần thấy id kho**. `lookkb` cấp khóa ngắn theo từng lần gọi (`b3`, `b4`…) và tự ánh xạ lại. Lợi: bớt khoảng
  5–8 token mỗi dòng menu, enum trong schema ngắn hơn, và đổi id không ảnh hưởng prompt.

### Gộp, tách, bỏ
| Thao tác | Ghi trong catalog | Sổ nét cũ xử lý thế nào |
|---|---|---|
| Gộp A vào B | A: `status: "merged", "into": ["B"]` | `resolve(A)` trả B; số đếm của A cộng vào B. |
| Tách A thành B, C | A: `status: "split", "into": ["B","C"]` | Lựa chọn cũ của nhân vật vẫn là A (vẫn tra được cụm từ để vẽ lại). Khi tính trần, A tính cho **cả** B và C (thận trọng). |
| Bỏ A | A: `status: "retired"` | Vẫn tra được; không bao giờ xuất hiện trong menu mới. |

Sổ nét nên lưu thêm `kb_version` và chụp lại `phrase` lúc chọn (LOOK.body.json đã có `phrases`). Số đếm (`counts`) nên **tính lại từ
`chars`** mỗi lần nạp thay vì lưu riêng: hết lệch khi gộp/tách và bỏ được đoạn cộng trừ tay trong `luan_hoi.py`.

## 4. Tần suất

Ba nguyên tắc.

**a. Tần suất là hàm của ngữ cảnh.** Lưu thành danh sách dòng có điều kiện; dòng khớp và cụ thể nhất thắng (dòng không có `when` là
mặc định). Mỗi dòng ghi `basis`:
- `stat`: có con số đúng quần thể, kèm `p` và `ev`;
- `proxy`: con số của quần thể khác (ví dụ Đông Á dùng tạm cho người Việt), kèm `p`, `ev`, và quần thể gốc;
- `est`: ước lượng của agent, chỉ có `band`.

**b. Model chỉ thấy nhãn, code giữ con số.** `band` suy từ `p` theo ngưỡng cố định trong `vocab.json`. Đề xuất khởi đầu:
`common` ≥ 15%, `uncommon` 2–15%, `rare` < 2% trong nhóm cùng giới, cùng dải tuổi, cùng quần thể. Khi có `p`, script tự tính `band`;
agent không viết tay cả hai.

**c. Với đại lượng liên tục, định nghĩa giá trị bằng phân vị, đừng gán tần suất.** `LOOK_SLOTS.md` đã định nghĩa chiều cao là "so với
người cùng giới, cùng quốc tịch". Vậy:
```json
{"id": "height.tall-m", "measure": {"name": "stature", "q": [0.85, 0.97]}}
```
Tần suất = 0,97 − 0,85 theo định nghĩa, đúng với mọi quần thể mà không cần số liệu. Bảng nhân trắc chỉ dùng để đổi phân vị ra cm khi
đạo diễn hoặc prompt ảnh cần số. Với đại lượng có ngưỡng tuyệt đối (BMI cho `fat`), ghi `"measure": {"name": "bmi", "range": [25, 30]}`
và để `build.py` tính `p` cho từng ô (giới, dải tuổi, quần thể) từ `stats/` khi có; chưa có thì rơi về `est`.

**Chuỗi lùi quần thể** khai trong `vocab.json`: `vn → sea → east_asia → any`. Lùi một bậc thì `basis` thành `proxy`.

**Hệ quả cho luật chọn:** "tối đa 1 nét hiếm" và nhãn `[near-plain]` phải tính theo ngữ cảnh của nhân vật. Lưng gù ở tuổi 75 là
`common` (được làm nét phụ); cùng nét đó ở tuổi 30 là `rare`. Tóc đen ở tuổi 70 trở thành `uncommon` thay vì nền.

`build/report.md` nên in tỉ lệ `stat / proxy / est` theo ô: đó là thước đo tiến độ thay dần ước lượng mà `BACKLOG.md` đang cần.

## 5. Luật loại trừ

Liệt kê từng cặp cấm thì số luật tăng theo bình phương số giá trị và agent thêm giá trị mới phải biết hết các giá trị khác. Đề xuất
hai cơ chế, cơ chế đầu gánh phần lớn.

### a. Trục thân (khai ngay trên giá trị)
`vocab.json` khai một ít trục có thang số, ví dụ `fat` 0–5, `muscle` 0–4, `frame` 0–4, `spine` 0–3, `mobility` 0–3.
- Giá trị **đặt** trục bằng `sets`: `fat.obese-m` có `"sets": {"fat": 5}`; `frame.stocky-m` có `"sets": {"frame": 3}`.
- Giá trị **đòi** khoảng trục bằng `req`: `chest.ribs-showing-m` có `"req": {"fat": [0, 1]}`.

Code áp dụng: gom `sets` của mọi lựa chọn thành trạng thái thân; một lựa chọn vi phạm nếu `req` của nó không chứa trạng thái. Hai
`sets` khác nhau trên cùng trục cũng là vi phạm. Trục chưa ai đặt thì lấy giá trị của nền theo tuổi. Lưu ý ví dụ trong đề bài
("stocky frame" + "ribs showing") là quan hệ giữa khung xương và mỡ: không nên cấm cứng (người khung to vẫn có thể gầy trơ xương vì
đói); luật đúng là `ribs-showing` đòi `fat ≤ 1`, còn mâu thuẫn thật là khi một ô khác đã đặt `fat ≥ 3`.

Lợi thêm: trạng thái trục chính là thứ đạo diễn cần để suy khả năng hành động (vác nổi không, chạy nhanh không), không phải đọc lại
cụm từ.

### b. Vùng thân và luật cặp
- `claims`: mỗi giá trị khai vùng nó mô tả (`belly`, `upper_back`…). Hai lựa chọn không phải nền cùng `claims` một vùng thì code báo
  "tả một chỗ hai lần" (đúng lỗi bụng bị tả ở cả `fat_where` và `waist_belly` mà `SYS_CHAR` đang phải dặn bằng lời).
- `rules.jsonl` cho phần còn lại, dùng bộ chọn theo id, ô hoặc thẻ:
```json
{"id": "r007", "type": "exclude", "a": "posture.stooped-old", "b": "back.baseline@18-64", "why": "a stooped stance needs a bent back"}
{"id": "r012", "type": "requires", "a": "tag:childbirth", "ctx": {"sex": "female"}, "why": "..."}
```

### Áp dụng ở đâu
1. **Trước khi chọn (ngăn):** khi nhân vật chọn theo từng nhóm ô (mục 7), `lookkb.menu()` bỏ sẵn các ứng viên trái với trạng thái đã
   chốt ở nhóm trước. Ngăn từ đầu rẻ hơn sửa sau: log cho thấy vòng sửa hiện tốn thêm 1–2 lần gọi 6k token.
2. **Sau khi chọn (kiểm):** `lookkb.check(picks, ctx)` trả danh sách vi phạm kèm `why` của luật; dùng làm lời nhắc sửa.
3. **Lưới cuối:** giữ `SYS_CHECK` của Luân hồi (chỉ khoảng 200–300 token), nhưng mỗi mâu thuẫn nó bắt được mà code không bắt thì ghi
   vào `logs/rule_candidates.jsonl`. Agent chưng cất đọc file đó để viết luật mới. Luật được khai thác từ lỗi thật, không phải nghĩ
   trước cho đủ.

## 6. Quy trình khi có nguồn mới

1. **Đăng ký nguồn** vào `sources.jsonl`: id, loại, ghi chú giấy phép, ngày lấy, sha256, quần thể mà nguồn phủ.
2. **Trích** thành `evidence/<source>.jsonl` hoặc `stats/<source>.csv`. Bộ dữ liệu và bảng số trích bằng script; văn bản do Opus
   trích. Mỗi nguồn một file nên trích lại một nguồn là thay một file.
3. **Chưng cất theo từng ô, đầu ra là bản vá.** Với mỗi ô bị ảnh hưởng, agent nhận: file của ô, các thẻ mới gắn với ô, `vocab.json`.
   Agent **không sửa catalog trực tiếp** mà viết `patches/<ngày>-<source>.jsonl` gồm các thao tác:
   `add`, `attach_ev`, `set_freq`, `rephrase`, `merge`, `split`, `retire`, `add_rule`.
   `tools/apply_patch.py` kiểm rồi áp. Nhờ vậy agent không thể lỡ tay đổi tên hay xóa id, và mỗi nguồn để lại một dấu vết xem lại được.
4. **`check.py`** (danh sách dưới). Lỗi thì không dựng.
5. **`build.py`** → `build/kb.json` + `build/report.md` (số giá trị theo ô × giới × dải tuổi, tỉ lệ `stat/proxy/est`, số thêm, gộp,
   bỏ so với bản trước); tăng `kb_version`.
6. **Hồi quy không gọi model:** chạy khô `lookkb.pack()` trên bộ nhân vật mẫu (ít nhất nam/nữ × 4 dải tuổi) để đo token từng lần gọi;
   nạp lại mọi `stories/*/registry.json` và xác nhận mọi id tra được.

### Các kiểm tra của `check.py`
**Từng dòng**
- đúng lược đồ; thẻ chỉ lấy từ `vocab.json`; `age` nằm trong 18–120;
- id không trùng, kể cả dòng đã gộp hoặc bỏ; chuỗi `into` không vòng và kết thúc ở dòng `active`;
- `phrase`: 3–10 chữ, ASCII, không chữ cấm (danh sách trong `build_body.py`), không từ quần áo, kiểu tóc, đồ vật; giá trị riêng một
  giới không chứa từ của giới kia;
- mọi `ev.c` tồn tại; dòng `stat` có `p` trong 0–1 và có `ev`.

**Theo ô**
- cụm gần trùng trong cùng ô (so tập từ đã chuẩn hóa) → báo để gộp;
- **đúng một nền** cho mỗi (ô, giới, từng tuổi 18–100, quần thể mặc định): không hở, không chồng;
- mỗi (ô, giới, dải tuổi) có đủ số giá trị tối thiểu (đề xuất ≥ 6) và có cả ba mức tần suất;
- ô dạng phân hoạch (`height`, `fat`): tổng `p` hoặc tổng khoảng phân vị không vượt 1.

**Toàn kho**
- luật trỏ tới bộ chọn có thật; `sets`/`req` nằm trong thang của trục;
- thân toàn nền của mọi (giới, dải tuổi) qua hết luật;
- mỗi giá trị không phải nền có ít nhất một thân hoàn chỉnh hợp lệ chứa nó (không có giá trị chết);
- mọi gói của `pack()` trên bộ mẫu nằm dưới ngân sách token;
- script không chứa đường dẫn tuyệt đối; dựng hai lần cho cùng kết quả.

## 7. Giao diện truy vấn cho agent

Agent và `luan_hoi.py` chỉ đi qua `lookkb`, không tự đọc file.

```python
kb  = lookkb.load()                               # build/kb.json
ctx = lookkb.Ctx(sex="male", age=70, pop="vn", facts={"manual-labour", "poverty"})

kb.baseline(slot, ctx)             -> giá trị nền cho ô ở ngữ cảnh này
kb.menu(slot, ctx, register, state=None, k=12)    -> ứng viên đã lọc, đã xếp
kb.pack(slots, ctx, register, budget=1800)        -> [gói]: text menu + bảng khóa ngắn→id + enum cho schema
kb.check(picks, ctx)               -> [vi phạm: id luật, các ô, câu giải thích]
kb.state(picks, ctx)               -> trạng thái trục (cho bước kiểm và cho đạo diễn)
kb.band(id, ctx)                   -> common / uncommon / rare trong ngữ cảnh
kb.resolve(id)                     -> id hiện hành + trạng thái
kb.assemble(picks, ctx)            -> prompt ảnh theo thứ tự A → H
```
Cho agent chưng cất (dòng lệnh, đầu ra nhỏ): `lookkb slot <ô>` (file ô + thống kê), `lookkb gaps <ô>` (giá trị `est` hoặc không có
`ev`), `lookkb near "<cụm>"` (tìm giá trị gần trùng trước khi thêm), `lookkb why <id>` (các thẻ căn cứ).

### Kích thước
- Một dòng menu: `khóa | phrase | band | tối đa 2 nguyên nhân`, khoảng 15–18 token.
- `menu()` trả tối đa `k` = 12–14 giá trị mỗi ô: nền luôn có, sau đó ưu tiên giá trị story chưa dùng, chia đều ba mức tần suất. Ô nào
  còn nhiều hơn `k` thì lấy mẫu có hạt giống theo (story, nhân vật): mỗi nhân vật thấy một tập con khác nhau, tự nó đã tăng đa dạng.
- `pack()` thay cho `GROUPS` cố định: nhồi ô vào gói cho tới ngân sách. Hồ sơ Lão Bảy (IDENTITY + SOUL + LIFE) khoảng 676 chữ, tức
  khoảng 900–1.000 token; cộng lời hệ thống thì còn chừng 1.800 token menu mỗi lần gọi, khoảng 7–8 ô. Bốn mươi ô là 5–6 lần gọi Luân hồi.
- **Lần gọi nhân vật phải tách** (hiện 6k token, và STYLE 589 chữ chiếm phần không cần cho thân). Đề xuất hai bước:
  1. nhân vật nhận danh sách ô, mỗi ô 3 ví dụ ngắn, và chọn ô nào là nét nhận diện, ô nào là nét phụ;
  2. chỉ với các ô đã chọn (tối đa 8), nhận danh sách đầy đủ và chọn giá trị, theo thứ tự nhóm A trước để các nhóm sau được lọc theo
     trạng thái thân.
  Ô không được chọn nhận nền; không cần đưa ứng viên của chúng cho model.

### "Bình thường theo tuổi"
Nguyên nhân gốc: `normal` đang là một giá trị chung cho mọi tuổi và được gán ngay khi nhân vật không nhắc tới ô. Sửa bằng bốn điểm:
1. **Nền là hàm của (ô, giới, tuổi, quần thể).** Mỗi ô có vài dòng `role: "baseline"` với khoảng tuổi nối nhau, ví dụ cho `back`:
   18–44 "ordinary straight back"; 45–64 "back slightly rounded at the shoulders"; 65+ "back mildly stooped with age". `check.py`
   bảo đảm mỗi tuổi có đúng một nền.
2. **Nền được gán sau cùng, không phải lúc bắt đầu.** Ô không nhắc tới là "chưa đánh dấu"; `kb.baseline()` chỉ điền khi cần, và nền
   cũng mang `sets` nên bước kiểm thấy được nó.
3. **Model thấy nền bằng chính cụm từ của tuổi đó**, gắn nhãn `[ordinary for your age]`, thay cho chữ `normal` trừu tượng. Một người
   70 tuổi muốn lưng thẳng thì phải chọn giá trị "upright straight back", lúc này là `uncommon` và tính là nét riêng.
4. **Nền không vào prompt ảnh**, trừ sáu ô bắt buộc trong `LOOK_SLOTS.md`; ở đó dùng cụm nền theo tuổi. Nền không tính vào sổ nét.

Cùng cơ chế giải luôn hai việc khác: nền theo quần thể (màu tóc, màu da, chiều cao) và tần suất theo tuổi ở mục 4.

## Kết luận

Thiết kế bốn tầng đi đúng hướng nhưng còn là sơ đồ lưu trữ; ba thứ quyết định chất lượng cho agent chưa có trong đó: nền và tần suất
theo ngữ cảnh, luật khai ngay trên giá trị, và một module truy vấn đóng gói theo ngân sách token. Log hiện tại cho thấy cả ba đều đã
thành vấn đề thật với riêng 18 ô thân.

### Bản tối thiểu nên dựng ngay
1. Chuyển `body.json` thành `catalog/<slot>.jsonl` bằng script: `age` dạng số, `role`, `status`, `ev`; chép các card đang trích vào
   `evidence/`; bỏ đường dẫn sang `ebook_maker`.
2. `vocab.json`: gom 60 thẻ nguyên nhân về khoảng 20; khai dải tuổi và 4 trục (`fat`, `muscle`, `frame`, `spine`).
3. Nền theo tuổi cho 18 ô thân, và dòng tần suất có `when` ở những giá trị đổi mức theo tuổi. Tất cả vẫn là `est`.
4. `sets`/`req`/`claims` cho nhóm A và các ô `chest`, `waist_belly`, `back`, `arms`, `legs`, `posture`.
5. `lookkb.py` với `load`, `baseline`, `menu`, `pack`, `check`, `resolve`; sửa `luan_hoi.py` dùng nó, tách lần gọi nhân vật thành hai
   bước, sổ nét ghi `kb_version` và tính lại số đếm từ `chars`.
6. `check.py` với các kiểm tra từng dòng, kiểm nền, và kiểm ngân sách token trên bộ nhân vật mẫu.

### Để sau, khi có nguồn thứ hai
Bảng `stats/` và tần suất `stat`/`proxy`, chuỗi lùi quần thể, bản vá theo thao tác, khai thác luật từ log, SQLite.
Lý do hoãn: chưa có số liệu nào trong tay, và các trường cần thiết (`pop`, `basis`, `measure`) đã có chỗ sẵn trong lược đồ nên thêm
sau không phải đổi cấu trúc.
