# Đánh giá loop LOOK (bản opus)

Đọc: `characters/LOOP.md`, `SPEC.md`, `lao_bay/*`, `look_and_feel.md`; bên `ebook_maker/skills/character-portrait/`: `build/`,
`character-portrait-prompt/`, `lookup/` (có chạy thử `lookup()` trên máy, không gọi model), `evals/run4/` (formula_n1, picks,
arcface, prompts), `evals/run5/` (formula_build, gen_build), `evals/flow1/` (FLOW + notes). Không gọi Ollama, ComfyUI hay mạng.

Giữ nguyên ý người dùng: nhân vật tự tra, tự viết prompt (prompt = LOOK), tự xem ảnh, tự chấm theo IDENTITY + SOUL, sửa, tối đa
5 vòng, biết giới hạn. Các đề xuất bên dưới chỉ thay **cách** làm từng bước, không thay chủ thể.

---

## 0. Tóm tắt ngắn

Ý tưởng đúng hướng và khớp bài học của harness (kiểm tra sau khi sinh rồi sinh lại tốt hơn dặn "đừng"). Nhưng bản nháp hiện tại
có ba lỗ lớn:

1. **Người viết tự chấm khi đang nhìn prompt của chính mình** gần như chắc chắn sẽ "duyệt", vì model chấm cái nó *định* vẽ chứ
   không chấm cái nó *thấy*. Phải tách bước "tả ảnh mù" (không thấy prompt, không thấy hồ sơ) khỏi bước "so với mình".
2. **Kết quả run4 không chuyển sang được bài toán này.** run4 thử phần *biểu cảm/tính cách* trên một khối nhận dạng mặt do code
   viết sẵn (công thức N1 luật 9: "Do not describe face anatomy... the code already describes the face"). LOOK lại chính là cái
   khối nhận dạng đó (khung mặt, mắt, mũi, da, dáng). Chưa có thí nghiệm nào đo "model nhỏ tự viết giải phẫu mặt/dáng" tốt hay
   xấu. Bài học N2 (cue chồng cue → cường điệu) thì chuyển được, và còn nguy hiểm hơn ở đây.
3. **Prompt chữ không giữ được một con người.** ArcFace run4: cùng khối nhận dạng, cùng seed, chỉ đổi đoạn biểu cảm mà độ giống
   chỉ ~0,44 (người khác hẳn ~0,20). Nghĩa là LOOK dạng chữ cho ra một *kiểu người*, không phải *một người*. Nếu cần nhân vật ra
   cùng một mặt ở mọi cảnh, đầu ra của loop phải gồm cả **ảnh neo + seed**, không chỉ chữ.

---

## 1. Loop có chạy như thiết kế không

### 1.1 Thiên vị tự chấm
- Cùng một model, cùng một context: khi chấm, Gemma đã có trong đầu prompt nó viết, nên nó sẽ "thấy" những gì nó đã viết (hiệu
  ứng xác nhận) và cho điểm cao. Với model nhỏ thì còn thêm thói chiều lòng: hỏi "đây có phải là mình không?" thì câu trả lời dễ
  nhất là "có, khá giống".
- Câu hỏi "đây có phải là mình không?" quá mở. Không có tiêu chí cố định thì điểm vòng 2 và vòng 4 không so được với nhau.
- Kinh nghiệm flow1 (notes mục 5) đã chỉ ra đúng điều này: một model đóng hai vai thì không giữ được tách vai; vai phân xử
  có xu hướng xử "partly" cho an toàn. FLOW1 còn chốt luật "không bao giờ để nhân vật tự tả thân hình của mình làm kết quả".
  Loop này cho nhân vật tự tả **và** tự chấm, nên phải bù bằng tách lời gọi.
- Cách bù (vẫn là "nhân vật tự chấm"): chia bước chấm thành hai lời gọi:
  1. **Mắt (mù):** Gemma nhận *chỉ ảnh* và một phiếu câu hỏi cố định ("người này trông bao nhiêu tuổi? giới? người vùng nào?
     cao/thấp, gầy/đậm? da? có sẹo/chai thấy được không? nét mặt khi nghỉ?"). Không có prompt, không có hồ sơ. Trả JSON.
  2. **Nhân vật so:** nhân vật đọc IDENTITY/SOUL/LIFE của mình + bảng đối chiếu (do code dựng) giữa "mình là" và "mắt thấy",
     rồi quyết định sửa gì. Đến đây nhân vật vẫn là người phán, nhưng phán trên bằng chứng chứ không trên ý định.
- Phần "đúng/sai" của các mục cứng (giới, nhóm tuổi, dân tộc) nên để **code** so (chuỗi với chuỗi), không để model so.

### 1.2 Gemma 4 26B nhìn ảnh có đáng tin không
Chưa có số đo trong repo; dưới đây là đánh giá theo kinh nghiệm chung về VLM cỡ này, cần thí nghiệm xác nhận (mục 5):

| Thứ cần thấy | Độ tin dự đoán | Ghi chú |
|---|---|---|
| Giới | cao | gần như không sai |
| Nhóm tuổi (trẻ/trung niên/già) | khá | đoán số tuổi lệch ±10 là thường; "70" và "60" khó phân biệt. Hỏi theo dải, không hỏi số |
| Dân tộc | thấp–vừa | phân biệt Đông Á / Đông Nam Á / Âu được, nhưng "Kinh miền Trung" so với "người Hoa" thì không. Chỉ nên kiểm "trông Đông Nam Á, không trông Đông Á lai Âu" |
| Dáng (cao/thấp, gầy/đậm) | thấp ở ảnh nửa người | không có vật so sánh thì không biết cao hay thấp; ảnh nửa người không thấy chân. Cần ảnh toàn thân riêng |
| Dấu vết nhỏ (sẹo mờ, chai tay, đồi mồi, móng bẩn) | thấp | ở 896×1152 bàn tay chiếm vài chục pixel; model sẽ "thấy" thứ được hỏi tới. Chỉ hỏi dạng "có thấy X không, chỉ ra ở đâu", và chấp nhận "không thấy" |
| Nét mặt khi nghỉ | vừa | VLM hay đọc quá lên ("hiền", "từng trải") theo khuôn mẫu tuổi; dễ bị gợi ý |
| "Đẹp hóa" | vừa | đây là lỗi hay gặp nhất của Qwen Image (da quá mịn, răng quá đều, cơ quá nét), Gemma bắt được nếu hỏi thẳng |

Hệ quả: tiêu chí chấm chỉ nên gồm những thứ Gemma thấy được ổn định. Dấu vết nhỏ và chiều cao **không nên tính điểm qua mắt
Gemma**; hoặc bỏ khỏi vòng chấm, hoặc kiểm bằng cách khác (ảnh cận tay, người chấm).

### 1.3 Trôi nhận dạng giữa các vòng
- Đổi một cụm từ trong prompt là đổi cả mặt, kể cả khi giữ seed (ArcFace run4 ~0,44). Nhân vật sửa "mũi thấp" thì có thể mất
  luôn "khung mặt vuông" đã được khen ở vòng trước. Loop dễ dao động thay vì hội tụ.
- Cách giảm:
  - giữ **cùng seed (hoặc cùng 2 seed)** suốt 5 vòng, để khác biệt giữa các vòng chủ yếu do prompt;
  - mỗi vòng chỉ được sửa **tối đa 2–3 mục**, các mục khác code khóa nguyên văn (LOOK dạng ô, xem mục 5);
  - code ghi diff giữa các vòng, nhân vật thấy "vòng trước sửa gì → mắt thấy gì đổi", để biết sửa nào có tác dụng.

### 1.4 Biết "5 lượt" thì sao
- Tốt: nhân vật không cầu toàn vô hạn; có lý do để ưu tiên lỗi lớn trước (giới/tuổi/dân tộc rồi mới tới nốt ruồi).
- Xấu, có hai kiểu với model nhỏ: (a) vòng cuối hạ chuẩn để "đạt" cho xong; (b) vòng đầu sửa ồ ạt cả chục mục. Cả hai đều làm
  điểm mất ý nghĩa.
- Giữ ý người dùng nhưng đặt chỗ cho đúng: **người viết (nhân vật) biết số lượt** ("còn 3 lượt, sửa cái lớn nhất"); **mắt mù
  không biết** đây là vòng mấy; và **luật đạt do code quyết**, không do nhân vật tuyên bố "đạt rồi".

### 1.5 Luật dừng và giữ bản nào
- Bản nháp nói "giữ bản tốt nhất" nhưng không nói đo "tốt nhất" thế nào. Điểm tuyệt đối từ model nhỏ trôi theo vòng (vòng sau
  hay được cho điểm cao hơn chỉ vì "đã sửa"). Nên:
  - **mục cứng** (đúng/sai, code so) là cổng: bản nào trượt cổng không được giữ;
  - giữa các bản qua cổng, chọn bằng **so cặp mù**: đưa Gemma hai ảnh A/B (thứ tự ngẫu nhiên, không biết vòng) + hồ sơ, hỏi
    "ảnh nào hợp người này hơn, vì sao". Bản thắng làm "champion", vòng mới chỉ thay khi thắng champion. So cặp ổn định hơn chấm
    thang 10 rất nhiều với model nhỏ.
- Dừng khi: (1) qua mọi mục cứng **và** mục mềm đạt ngưỡng (vd ≥ 80% "có"), hoặc (2) hai vòng liên tiếp không thắng được
  champion, hoặc (3) hết 5 vòng. Kết quả luôn là champion, không phải bản cuối.

---

## 2. Knowledge base và tra cứu

### 2.1 Hiện có gì, dùng được tới đâu

| Tài sản | Dạng | Dùng được cho loop? |
|---|---|---|
| `lookup/lookup.json` + `lookup.py` | khóa theo giới×tuổi, emotion, trait, ethnicity; code cắt ≤ ~2,5k ký tự | **dùng được ngay** cho mặt, đúng dạng cần cho model nhỏ |
| `build/build.json` | 51 mục dáng: base/giới-tuổi, build, life, means, need, trait; cues/tells/pitfalls | dùng được cho dáng; mục `base/*` mạnh, `life/*` và `means/*` yếu |
| `character-portrait-prompt/references/` | ~200k ký tự, hàng trăm file luật kèm số đo mm, độ, "grade 4 rhytids" | **không đưa cho model nhỏ**. Đây là nguyên liệu thô để chưng cất, không phải KB để tra |
| `evals/run4/formula_n1.md` | 10 luật viết biểu cảm | dùng cho phần nét mặt quen khi nghỉ; nhưng luật 9 (không tả giải phẫu) **ngược** với mục đích LOOK, phải viết công thức mới |
| `evals/run5/formula_build.md` | 8 luật viết dáng | gần đúng ý; chưa có kết quả render |

### 2.2 Thử `lookup()` cho lão Bảy (chạy code, không gọi model)
`lookup({sex: male, age: 70, mood: "bình thản", personality: ["mộc mạc","cứng đầu","hay cười xòa"], ethnicity: "Vietnamese"})`
trả 2.129 ký tự, và cho thấy đúng các nguy cơ:
- **7 dấu tuổi cùng lúc** (rãnh mũi-miệng sâu, nếp giữa mày, chảy hàm, má hóp, mắt sâu, môi mỏng, da thuộc có đồi mồi). Viết hết
  vào prompt là ra ông cụ 90 tuổi ốm yếu, đúng cơ chế cường điệu của N2. SKILL.md của lookup đã dặn "do not stack", nhưng dặn
  "đừng" thì model nhỏ ít nghe.
- **Cue mâu thuẫn nhau:** "sagging jowls, a softer jawline" (tuổi) đi cùng "angular chin and a defined jawline" (cứng đầu); mood
  calm-neutral có "eyes closed" và "hands resting in a pocket or holding a jacket" (không hợp LOOK). Model nhỏ sẽ bê cả hai.
- **Dân tộc trượt:** khóa chỉ khớp chuỗi `east-asian`; "Vietnamese" không ra gì. Mục duy nhất lại dựa trên số đo người Hoa
  (Farkas). Người Kinh là Đông Nam Á; Qwen Image vốn kéo mặt về Đông Á. Đây là **lỗ lớn nhất** cho bộ nhân vật toàn người Việt.
- "mộc mạc" → NO VISIBLE BASIS (đúng, và đó là hành vi tốt: không bịa).
- `build.json` `base/male-elderly` có "Very old: thin and frail, soft muscles" trong khi lão Bảy 70 tuổi vẫn chèo ghe; `life/manual-labour`
  chỉ có 1 cue ("lean, hard-muscled"), không có gì về ngư dân, nắng biển, chai tay, lưng chèo. Bảng không biết phân xử "già" với
  "lao động" khi chúng đụng nhau.

### 2.3 Vì sao N2 làm mặt tệ hơn, và áp sang đây
Xem prompt N2 của cô Hiền: "lower lip pushed outward... chin bunched... brows draw together... knuckles slightly pale". Cue từ
sách là cue cho **mức mạnh nhất** của cảm xúc (sách giải phẫu biểu cảm tả đỉnh). Model nhỏ chép 4–6 cue vào một đoạn → mọi kênh
cùng hét → cường điệu, mất vẻ kín đáo. Với LOOK, cùng cơ chế sẽ làm mọi dấu tuổi, dấu nghề, dấu dân tộc cùng lúc lên mức cao.

Bài học cho thiết kế KB:
1. **Ít cue, có mức độ.** Mỗi mục chỉ đưa 2–3 cue, mỗi cue có nhãn mức (nhẹ/vừa/rõ) và nhãn kênh (khung mặt, mắt, da...). Code
   chọn *một* cue mỗi kênh, không để model chọn từ cả rổ.
2. **Bảng phân xử xung đột do code giữ**: thứ tự ưu tiên khung xương (lớn lên ở đâu) > tuổi > nghề/đời sống > tính cách; tính cách
   chỉ được ghi vào nét mặt khi nghỉ và tư thế (đúng SPEC). Cặp cue mâu thuẫn (jawline mềm vs góc cạnh) khai báo sẵn trong KB.
3. **Ngân sách cố định:** mỗi lời gọi viết chỉ thấy ≤ ~1,2k token KB (khoảng 12–15 cue), phần còn lại cho hồ sơ + phản hồi vòng trước.

### 2.4 KB nên có dạng gì cho model nhỏ
- **Khóa, không tìm tự do.** Model nhỏ không biết hỏi gì trong 200k ký tự. Code biết IDENTITY (giới, tuổi, dân tộc, quê, nghề,
  thời đại) → tự tra các ô cứng. Model chỉ được chọn trong **menu ngắn** cho các ô mềm (life, trait, need), như `family_menu()`
  và bước map trong run4/run5 đã làm (enum trong schema, tối đa 4–6 họ).
- Vòng 2+ thì tra theo **lỗi**: nếu mắt mù nói "trông 85 tuổi, gầy yếu" mà hồ sơ là 70, chèo ghe, code tra ô "tuổi giảm nhẹ" /
  "lao động" và đưa lại 2–3 cue sửa. Tức là KB cần thêm dạng **"triệu chứng → cue sửa"** (vd "trông già quá" → bớt dấu nào,
  thêm gì), không chỉ dạng "thuộc tính → cue".
- Mỗi cue tiếng Anh, viết sẵn ở dạng **đưa thẳng vào prompt Qwen** được (cụm ngắn, nhìn thấy được), để model không phải dịch
  và viết lại (viết lại là chỗ cường điệu chen vào).
- Các ô cần **bổ sung trước khi chạy thật** (theo mức quan trọng với bộ nhân vật người Việt):
  1. `ethnicity/southeast-asian` hoặc `ethnicity/vietnamese-kinh` (và các dân tộc khác nếu có), kèm biến thể theo miền; đồng thời
     sửa `lookup.py` khớp bí danh ("Vietnamese", "Kinh", "người Việt") thay vì khớp chuỗi đúng.
  2. `life/outdoor-sun` (da phơi nắng, nếp nheo mắt, gáy sạm), `life/fisher` hoặc mở rộng `life/manual-labour` (bàn tay, cẳng tay,
     lưng, chân trần), `life/injury-scar`, dáng đi.
  3. Mục "già mà còn làm" để chặn `base/*-elderly` kéo về "frail".
  4. Chuẩn tầm vóc người Việt theo thế hệ (sinh 1956 ở làng chài thời chiến thì thấp, gầy là có lý).
- Coverage của chính bảng đã nói `life/manual-labour`, `life/alcohol`, `trait/tense`... là `thin`. Với LOOK, các ô `life/*` lại là
  phần quan trọng nhất (SPEC: "Nghề, thói quen và sự kiện trong LIFE để lại dấu").

---

## 3. Chấm điểm nên ra sao

### 3.1 Tiêu chí lấy từ IDENTITY và SOUL, đóng băng từ vòng 0
Vòng 0 (một lời gọi, có thể là chính nhân vật) dựng **phiếu tiêu chí** từ IDENTITY/SOUL/LIFE; code kiểm phiếu (mỗi dòng phải trỏ
về một dòng hồ sơ) rồi **khóa** cho cả 5 vòng. Phiếu gồm câu hỏi mà mắt mù trả lời được:

| Loại | Ví dụ (lão Bảy) | Cách chấm | Trọng số |
|---|---|---|---|
| Cứng (cổng) | nam; trông 65–75; trông người Việt/Đông Nam Á; một người, mặt rõ | code so JSON mắt mù với IDENTITY | trượt một mục = trượt |
| Nhận dạng | da sạm nắng; dáng nhỏ, chắc, không béo, không yếu; tóc muối tiêu tự nhiên | mắt mù có/một phần/không | 2 |
| Dấu đời (LIFE) | tay thô (chỉ khi ảnh có tay rõ); nếp nheo mắt do nắng | có/không/không thấy được | 1 (không thấy được = bỏ, không trừ) |
| SOUL (không trái) | nét mặt khi nghỉ không kiêu, không dữ, không u sầu; không trông giàu, không trông thành thị | có/không | 1 |
| Không đẹp hóa | da không mịn như sáp, không cơ bụng, răng không đều trắng | có/không | 2 |

- **SOUL chấm theo kiểu "không trái", không theo kiểu "phô ra".** Chấm "có thể hiện cứng đầu không" sẽ đẩy nhân vật thêm cue cứng
  đầu ở vòng sau, đúng đường N2. SPEC đã nói tính cách chỉ in vào nét mặt quen và tư thế; vậy chỉ cần ảnh không *phản* tính cách.
- Thang: **có / một phần / không / không thấy được**, không dùng thang 1–10. Điểm = tổng trọng số "có" (+½ "một phần") / tổng
  trọng số các mục thấy được. Cùng phiếu, cùng seed → điểm giữa các vòng so được.
- Đạt: qua cổng cứng **và** điểm ≥ 0,8 **và** thắng (hoặc hòa) champion ở so cặp mù.

### 3.2 Có cần người chấm riêng không
Có, ít nhất trong giai đoạn thử:
- **Mắt mù của Gemma** (lời gọi riêng, không prompt) đã là "người chấm khác" ở mức rẻ nhất, nên luôn có.
- **Đo bằng công cụ** (rẻ, khách quan, có sẵn): `insightface buffalo_l` (đã dùng ở run4 cho ArcFace) còn trả **tuổi và giới**.
  Đó là kiểm tra cổng cứng miễn phí, chạy CPU, không tốn máy dùng chung. ArcFace giữa các vòng còn đo luôn độ trôi nhận dạng.
- **Ghép mù kiểu run4** cho thí nghiệm: người (hoặc Claude/Opus nhìn ảnh) nhận 4 ảnh + 4 hồ sơ cùng giới, cùng dải tuổi và ghép.
  Đây là thước đo thật cho câu hỏi "LOOK có mang được *người này* không", tách bạch khỏi tự chấm. Chỉ dùng khi đánh giá thiết kế,
  không cần trong vận hành.
- Quan trọng nhất là đo **độ khớp giữa tự chấm và người chấm**: nếu tự chấm cho điểm cao ở những ảnh mà người ghép sai, thì tự
  chấm vô dụng, dù loop có "hội tụ".

---

## 4. Chi phí và tính thực tế

Mỗi vòng (đề xuất ở mục 5):

| Bước | Lời gọi | Máy | Ước lượng |
|---|---|---|---|
| map menu mềm (vòng 0) | 1 text | wee | ~2 s (run4: 2,0 s, 1,5k token) |
| dựng phiếu tiêu chí (vòng 0) | 1 text | wee | ~5 s |
| viết/sửa LOOK | 1 text (+0–2 sinh lại do code kiểm) | wee | 3–10 s (run4: 2,8 s/1,1k token) |
| render | 2 ảnh (2 seed) | senlab | 2 × (30 s – vài phút) |
| insightface tuổi/giới/ArcFace | 0 | CPU local | vài giây |
| mắt mù | 2 vision (1/ảnh) | wee | 10–30 s mỗi ảnh (ảnh tốn token, Ollama xử lý vision chậm hơn text) |
| so cặp với champion | 1 vision (2 ảnh) | wee | 15–40 s |
| nhân vật so và quyết định sửa | gộp vào lời gọi "viết/sửa" vòng sau | | |

- Tổng một nhân vật, đủ 5 vòng: ~20–25 lời gọi Gemma (≈ 10 vision) + 10 render. Thời gian: text ~1 phút, vision ~5–8 phút, render
  5–30 phút. **Nút cổ chai là render và vision, không phải viết.** Thực tế ~15–40 phút/nhân vật.
- Máy dùng chung: wee phải hỏi `wee_admin`, gửi tuần tự, không gửi `num_ctx`/`keep_alive`; senlab đang làm upscale. Hai máy xen
  kẽ tự nhiên (Gemma nghỉ khi senlab vẽ), nên chạy **pipeline tuần tự theo hàng đợi**, theo lô ban đêm, ghi JSONL từng bước để
  dừng giữa chừng vẫn nối lại được (và xem bằng viewer).
- Kiểm token: lời gọi viết/sửa = hồ sơ (IDENTITY+SOUL+LIFE lão Bảy ~1,2k token tiếng Việt) + KB ≤1,2k + phiếu + phản hồi vòng
  trước ~0,4k → ~3k, vừa sát ngưỡng. **Không đưa STYLE** vào lời gọi viết LOOK (STYLE toàn quần áo, xưng hô; LOOK không cần), và
  không đưa toàn bộ lịch sử 5 vòng, chỉ champion + vòng vừa rồi.
- Ảnh nửa người không chấm được dáng/chân; ảnh toàn thân thì mặt nhỏ. Nên: vòng 1–3 ảnh nửa người (mặt + tay), sau khi mặt qua
  thì 1–2 vòng toàn thân (khung run5) cho dáng. Hoặc mỗi vòng 1 nửa người + 1 toàn thân thay cho 2 seed, đổi lại kém chắc về seed.

---

## 5. Đề xuất cụ thể

### 5.1 LOOK nên là ô, không phải đoạn văn tự do
SPEC đang tả LOOK là cụm từ theo mục (tiếng Việt, đạo diễn đọc để suy "có vác nổi không"); LOOP lại nói LOOK = prompt tiếng Anh.
Gộp hai ý: **LOOK = các ô cố định, giá trị là cụm từ tiếng Anh nhìn thấy được** (tầm vóc, khung mặt, mắt, mày, mũi, miệng, da,
dấu tuổi, nét mặt khi nghỉ, tóc tự nhiên, thân, tay, chân, tư thế, dấu vết). Code ghép ô thành prompt Qwen (thêm câu mở, ánh
sáng, quần áo trung tính, nền). Vậy "prompt chính là LOOK" vẫn đúng, nhưng:
- mỗi vòng nhân vật chỉ sửa ô, code giữ nguyên các ô khác → bớt trôi;
- code kiểm từng ô: độ dài, không quần áo/đồ vật, không lý do/cảm nghĩ, không số đo, mỗi ô ≤ 1 cue cường độ "rõ";
- đạo diễn đọc được ô, bản tiếng Việt sinh lại từ ô nếu cần.

Bản `lao_bay/LOOK.gemma2.md` cho thấy vì sao cần kiểm từng ô: "răng rụng vài chiếc, nướu sẫm màu" (ảnh mặt nghỉ không thấy), "gốc
móng thường có vết bẩn cũ" (quá nhỏ), "thường để xõa tự nhiên" (là kiểu tóc, SPEC cấm), "không có mỡ thừa" lại đi với "bụng hơi
lùm lùm", "cánh tay nhỏ" với "bàn tay to". Viết thì ổn, nhưng không phải chữ nào cũng vẽ được hay chấm được.

### 5.2 Loop sửa lại

```
Vòng 0 (một lần)
  C0 code: đọc IDENTITY → khóa cứng (giới, dải tuổi, dân tộc, thời đại) → tra ô base/ethnicity/age.
  C1 Gemma (nhân vật, text): IDENTITY+SOUL+LIFE + menu ngắn → chọn ≤4 họ life/trait/need (enum).      [~2k token]
  C2 Gemma (nhân vật, text): hồ sơ → phiếu tiêu chí 8–12 câu, mỗi câu trỏ về dòng hồ sơ. Code kiểm, khóa.
  C3 code: tra KB theo khóa + họ đã chọn; chọn ≤1 cue/kênh, giải xung đột theo thứ tự ưu tiên; ≤1,2k token.

Vòng k = 1..5 (nhân vật biết "đây là lượt k/5")
  1 Gemma (nhân vật, text) viết/sửa LOOK dạng ô.
      vào: hồ sơ (không STYLE) + cue KB + [k>1: champion LOOK, bảng "mình là / mắt thấy" của champion và vòng trước,
           cue sửa tra theo lỗi] + "còn N lượt, sửa tối đa 3 ô, lỗi cổng trước".
      ra: JSON {ô: cụm từ} + "sửa ô nào, vì sao" (1 dòng/ô).
  2 code kiểm ô (cấm quần áo/đồ vật/số đo/lý do; ô không sửa phải giữ nguyên văn) → sinh lại ≤2 lần với gợi ý cụ thể.
  3 code ghép prompt; render 2 seed cố định (giữ suốt 5 vòng).
  4 code: insightface tuổi/giới mỗi ảnh; ArcFace so với champion (ghi độ trôi).
  5 Gemma (mắt mù, vision, không prompt, không hồ sơ, không số vòng): trả lời phiếu tiêu chí cho từng ảnh.
  6 code: tính cổng + điểm (trung bình 2 seed); dựng bảng "mình là / mắt thấy".
  7 Gemma (vision, mù vòng): so cặp ảnh vòng k với champion, thứ tự ngẫu nhiên, theo hồ sơ → A/B/hòa + lý do.
  8 code: cập nhật champion; dừng nếu (qua cổng & điểm ≥0,8 & không thua champion) hoặc 2 vòng liền không thắng hoặc k=5.

Ra: LOOK = ô của champion; kèm ảnh neo + seed + điểm + nhật ký 5 vòng (JSONL cho viewer).
```

Ghi chú:
- Bước 1 và 7 là "nhân vật tự chấm, tự sửa" theo đúng ý người dùng; bước 5 là "mắt" của chính Gemma nhưng tách context nên không
  thấy ý định của mình.
- Nếu muốn đúng nghĩa "nhân vật tự nhìn mình", có thể để bước 7 nhập vai ("mày là lão Bảy, ảnh nào là mày?"), nhưng chỉ sau khi
  bước 5 mù đã chạy, và kết quả so cặp không được ghi đè cổng cứng.
- Vòng 1–3 nửa người, vòng 4–5 toàn thân nếu mặt đã qua (dáng ít trôi mặt hơn).

### 5.3 Thí nghiệm nhỏ để kiểm loop

**Câu hỏi:** (a) loop có làm ảnh khớp người hơn không; (b) tự chấm có đáng tin không; (c) cue KB giúp hay hại khi viết giải phẫu.

**Nhân vật:** 8, chia **2 nhóm × 4 cùng giới, cùng dải tuổi** để ghép mù có nghĩa (vd 4 nam 60–75 nghề khác nhau: ngư dân, thầy
giáo về hưu, xe ôm, chủ tiệm vàng; 4 nữ 25–35: công nhân, giáo viên, tiểu thương, nhân viên văn phòng). Viết IDENTITY/SOUL/LIFE
theo SPEC. Ít nhất 6/8 là người Việt để lộ lỗ dân tộc.

**Nhánh (cùng seed, cùng code ghép):**
- L0: một lượt, không KB (Gemma viết LOOK từ hồ sơ, như `LOOK.gemma2`);
- L1: một lượt, có KB đã lọc (≤1 cue/kênh);
- L5: loop đầy đủ 5 vòng, có KB, có mắt mù + so cặp;
- (tùy, nếu đủ máy) L5-self: loop 5 vòng nhưng tự chấm kiểu bản nháp (cùng context, thấy prompt) để đo thiên vị.

**Đo:**
1. **Ghép mù** (chính): mỗi nhóm 4 ảnh × 4 hồ sơ, người dùng ghép như run4 (viewer run4 dùng lại được); cũng cho Claude ghép
   để có người chấm thứ hai. Đoán mò 25%. So L0/L1/L5.
2. **Cổng cứng tự động:** insightface tuổi lệch (|tuổi đoán − tuổi hồ sơ|), giới đúng; người chấm đánh dấu "trông Việt / không".
3. **Đẹp hóa / cường điệu:** người chấm 1–3 mỗi ảnh (như cột beauty trong picks).
4. **Độ tin tự chấm:** tương quan giữa điểm Gemma (bước 6) và kết quả ghép người; với L5-self, chênh điểm tự chấm so với người.
5. **Hội tụ:** điểm và ArcFace theo vòng; bao nhiêu nhân vật dừng sớm; champion là vòng mấy.
6. **Giữ người qua seed:** LOOK cuối render thêm 2 seed mới; ArcFace giữa các seed (mốc run4: 0,44 cùng seed). Nếu thấp như cũ thì
   xác nhận cần ảnh neo/image-edit cho các cảnh sau.

**Cỡ:** 8 nhân vật × (L0 2 ảnh + L1 2 ảnh + L5 ≤10 ảnh) ≈ 110 render, ~120 lời gọi Gemma (~50 vision). Một đến hai đêm trên
senlab + wee. Nhỏ, nhưng đủ để thấy chênh lớn (vd 50% → 80% ghép đúng); chênh nhỏ thì không kết luận được và phải nói rõ vậy.

**Trước thí nghiệm, làm rẻ trước:** (i) thêm ô dân tộc Việt + sửa khớp bí danh; (ii) lọc cue ≤1/kênh và bảng xung đột; (iii) kiểm
riêng "mắt" Gemma trên ~20 ảnh run4/run5 đã có (đã biết hồ sơ): hỏi tuổi/giới/dân tộc/dáng, đối chiếu. Bước (iii) không tốn
render và trả lời luôn câu hỏi 1.2; nếu mắt Gemma sai tuổi/dân tộc quá nhiều thì cả loop phải dựa vào insightface + người.

---

## 6. Kết luận

Loop **đáng làm**, và tinh thần "nhân vật tự xây LOOK" giữ được. Nhưng ở dạng hiện tại nó sẽ chủ yếu tự duyệt chính mình: cùng
context viết và chấm, tiêu chí mở, điểm tuyệt đối, cue KB đổ cả rổ, và không đo được nó có mang được *một người* hay không. Ba
thay đổi đáng làm nhất: (1) tách **mắt mù** khỏi người viết và dùng **phiếu tiêu chí đóng băng** + cổng cứng do code/insightface so,
chọn bản giữ bằng **so cặp với champion**; (2) biến KB thành **tra theo khóa, ≤1 cue/kênh, có bảng xung đột và cue sửa theo lỗi**,
và vá ngay lỗ **dân tộc Việt** cùng các ô `life/*` lao động ngoài trời; (3) LOOK dạng **ô cố định**, mỗi vòng sửa ≤3 ô, cùng seed,
và lưu **ảnh neo + seed** cùng LOOK vì chữ một mình không giữ được mặt. Trước khi xây cả loop, chạy thử rẻ "mắt Gemma" trên ảnh
run4/run5 đã có; kết quả đó quyết định loop dựa vào Gemma được tới đâu.
