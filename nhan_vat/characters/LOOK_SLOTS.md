# Khung ô LOOK (bản nháp 1)

LOOK là ngoại hình nhìn thấy được, cố định ở tuổi trong IDENTITY. Nhân vật **chọn giá trị cho từng ô** từ menu của kho nét
(knowledge base); code ghép các ô thành prompt tạo ảnh theo thứ tự cố định. Nhờ có ô, code đếm được nét nào cả dàn nhân vật đã
dùng và cấm dùng lại quá nhiều.

Giá trị trong bảng dưới chỉ là ví dụ để thấy độ rộng. Kho nét thật sẽ có nhiều biến thể hơn, mỗi biến thể kèm:
- `id`, cụm từ tiếng Anh để đưa vào prompt, mô tả tiếng Việt;
- **mức phổ biến** ngoài đời (`thường` / `ít` / `hiếm`), theo giới, tuổi, dân tộc nếu có số liệu;
- ràng buộc (ví dụ "chỉ từ tuổi 50", "nam", "do nắng gió", "do lao động");
- nguồn (sách, khối, trích dẫn).

Mọi ô đều có giá trị **`thường`** (trung bình, không nổi bật). Người thật phần lớn các ô là bình thường.

## A. Tổng thể
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `height` | so với người cùng giới, cùng quốc tịch | rất thấp, thấp, trung bình, cao, rất cao |
| `frame` | khung xương | nhỏ, mảnh, vừa, to, thô |
| `fat` | mỡ toàn thân | gầy trơ xương, gầy, vừa, đẫy, mập, béo phì |
| `muscle` | cơ | teo, mềm, bình thường, săn, nở |
| `fat_where` | mỡ dồn ở đâu | bụng, eo hông, đùi mông, mặt cổ, đều |

## B. Đầu và mặt
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `head` | hình đầu | tròn, dài, to so với thân, nhỏ, gáy bẹt |
| `face_shape` | khung mặt | trái xoan, tròn, vuông, chữ điền, dài, tam giác ngược, kim cương, mặt bánh đúc, mặt lưỡi cày |
| `forehead` | trán | cao, thấp, rộng, hẹp, dô, phẳng, lẹm |
| `brows` | lông mày | rậm, thưa, mảnh; ngang, cong, xếch, rủ; giao nhau, mất đuôi, lệch |
| `eyes` | mắt | to, nhỏ, híp; xa nhau, gần nhau; sâu, lồi; một mí, mí lót, hai mí, mí sụp; xếch, rủ đuôi |
| `under_eye` | dưới mắt | phẳng, bọng, quầng thâm, túi mỡ, nếp chân chim |
| `nose` | mũi | sống thấp, cao, gồ, gãy lệch, khoằm; đầu to, tròn, nhọn, hếch; cánh rộng, hẹp |
| `cheeks` | gò má, má | gò cao, gò nhô, phẳng; má hóp, má bầu, má xệ |
| `mouth` | miệng, môi | rộng, hẹp; dày, mỏng, môi trên mỏng; khóe trễ, khóe cong; môi thâm, nứt |
| `teeth` | răng | đều, hô, móm, khểnh, thưa, sứt, mẻ, ố vàng, đen trầu, mất vài cái, răng giả, bọc vàng |
| `jaw_chin` | hàm, cằm | vuông, bạnh, nhọn, lẹm, tròn, chẻ, đôi cằm, nọng |
| `ears` | tai | nhỏ, to, vểnh, áp sát, dái dày, dái mỏng, tai lệch |
| `neck` | cổ | ngắn, dài, to, gầy, nọng, yết hầu lộ, gân cổ |
| `skin_tone` | màu da | thang sáng → sẫm; sắc vàng, hồng, nâu, xám |
| `skin_texture` | da mặt | mịn, lỗ chân lông to, nhờn, khô, mụn, sẹo rỗ, nám, tàn nhang, đồi mồi, sạm nắng, đỏ gân máu |
| `wrinkles` | nếp nhăn | không, nếp trán, chân chim, rãnh mũi má, nếp cổ, nhăn sâu khắp mặt |
| `facial_hair` | lông mặt | không, lún phún, râu quai nón, ria, chòm râu, ria mép nữ, lông mặt rậm |
| `asymmetry` | bất cân xứng | không rõ, mắt lệch, miệng lệch, mũi lệch, một bên mặt xệ |
| `resting_face` | nét mặt quen khi không biểu cảm | trầm, cau, hiền, ngơ, khinh khỉnh, mệt mỏi, căng, lơ đãng |

## C. Tóc tự nhiên (không kiểu tóc)
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `hair_color` | màu | đen, nâu đen, nâu, muối tiêu, bạc trắng, cháy nắng |
| `hair_texture` | chất | thẳng, gợn, xoăn, rễ tre, mảnh mềm |
| `hair_density` | độ dày | dày, vừa, mỏng |
| `hairline` | chân tóc, hói | thấp, cao, hói hai bên trán, hói đỉnh, hói gần hết, chân tóc nhọn |

## D. Thân
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `shoulders` | vai | rộng, hẹp; ngang, xuôi; lệch, nhô xương |
| `chest` | ngực | lép, phẳng, vừa, nở, to, chảy xệ |
| `waist_belly` | eo, bụng | eo thon, eo thẳng, bụng phẳng, bụng mỡ, bụng bia cứng, bụng xệ, rạn bụng |
| `hips` | hông, mông | hẹp, vừa, rộng, mông lép, mông to |
| `back` | lưng | thẳng, gù, ưỡn, cong vẹo |
| `body_skin` | da thân | mịn, sạm cháy nắng theo vệt áo, lông nhiều, rạn, đồi mồi, nhăn chùng |

## E. Tay
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `arms` | cánh tay | mảnh, gầy gân, tròn mềm, săn, nở, da chùng |
| `hands` | bàn tay | nhỏ, to, ngón dài, ngón ngắn mập, khớp to, chai, nứt, run |
| `nails` | móng (tự nhiên) | ngắn sạch, ngắn bẩn, gãy, dày vàng, cắn móng |

## F. Chân
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `legs` | chân | thẳng, vòng kiềng, chữ X, ngắn so với thân, dài; đùi to, bắp chân to, cẳng gầy |
| `feet` | bàn chân | nhỏ, to, bè, ngón xòe, gót nứt, chai, vẹo ngón cái |

## G. Tư thế và dáng đi
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `posture` | đứng | thẳng, khom, ưỡn ngực, đổ vai, đầu đưa trước, nghiêng một bên |
| `gait` | đi | nhanh gọn, chậm chắc, lê, khập khiễng, lắc hông, vung tay |

## H. Dấu vết
| ô | thuộc tính | ví dụ giá trị |
|---|---|---|
| `marks` | nhiều giá trị, có vị trí | sẹo (mổ, bỏng, dao, rắn cắn), chai, bớt, nốt ruồi (to, có lông), hình xăm, mất ngón, khuyết tật, vết tiêm |

## Quy trình chọn giá trị
1. **Kho nét (rất lớn):** mỗi ô có nhiều biến thể, tiếng Anh. Từ ngữ **tách theo giới** ở những ô khác nhau giữa nam và nữ
   (ngực, eo, hông, tay, chân, lông mặt, chân tóc…), và gắn thẻ tuổi, dân tộc, nguyên nhân (nắng gió, lao động, sinh nở…).
2. **Code lọc cứng** theo thẻ: giới, dải tuổi.
3. **Luân hồi** (một LLM riêng, không phải nhân vật): đọc IDENTITY + SOUL (+ LIFE), với mỗi ô chọn từ kho những giá trị **có thể
   có** ở người này.
   - **Thả rộng:** danh sách ứng viên phải rộng (ví dụ 10–20 giá trị mỗi ô), gồm cả `thường`, nét lạ, nét không đẹp. Chỉ loại
     những gì thật sự không thể (ngư dân nghèo không có răng bọc sứ, người 70 tuổi không có da căng mịn). Mục tiêu là đa dạng và để
     nhân vật sáng tạo, không phải chọn sẵn cho nhân vật.
   - **Trí nhớ theo story:** trong cùng một story, Luân hồi nhớ những giá trị nào đã được các nhân vật trước dùng (sổ nét của
     story). Giá trị dùng nhiều thì bị cắt bớt khỏi danh sách hoặc đẩy xuống cuối; giá trị chưa ai dùng được ưu tiên.
4. **Nhân vật chọn** một giá trị cho mỗi ô trong danh sách của Luân hồi, theo luật dưới đây. Luân hồi ghi kết quả vào sổ nét của
   story.

## Luật chọn
1. **Mọi ô phải có giá trị.** Nhân vật được chọn `thường` cho bất cứ ô nào.
2. **Nét nhận diện:** mỗi nhân vật chọn **2–4 ô nổi bật** (không phải `thường`), là những nét người khác nhớ khi gặp. Các ô còn lại
   nên ở mức `thường` hoặc gần `thường`.
3. **Mức phổ biến:** tối đa 1 nét `hiếm` mỗi người, trừ khi LIFE giải thích được (ví dụ tai nạn để lại sẹo).
4. **Ràng buộc theo đầu vào:**
   - IDENTITY (giới, tuổi, quốc tịch, dân tộc, quê, nghề, vị trí xã hội, thời đại) giới hạn menu: ví dụ không có tóc bạc trắng ở
     tuổi 20 nếu không có lý do, không có răng bọc sứ đắt tiền ở ngư dân nghèo.
   - LIFE để lại dấu ở `marks`, `skin_texture`, `hands`, `posture`… nếu hợp lý.
   - SOUL và STYLE chỉ chạm tới `resting_face`, `posture`, `gait` và những gì do thói quen mà ra (mỡ, cơ, da, móng). Khung xương, hình
     mặt, mắt, mũi **không** suy ra từ tính cách.
5. **Không có ô "đẹp".** Không dùng các chữ beautiful, handsome, attractive, perfect, flawless trong prompt.

## Luật đa dạng (Luân hồi giữ, theo từng story)
- **Sổ nét của story:** mỗi lần một nhân vật chốt LOOK, Luân hồi ghi lại cặp (ô, giá trị) của nhân vật đó, chia theo nhóm cùng giới
  và cùng dải tuổi trong story.
- **Trần dùng lại:** một giá trị không `thường` chỉ được dùng tối đa N lần trong nhóm (ví dụ 20% số nhân vật, ít nhất 2). Quá trần thì
  Luân hồi bỏ giá trị đó khỏi danh sách của nhân vật sau.
- **Nét nhận diện không trùng:** hai nhân vật cùng nhóm không được có chung quá 1 nét nhận diện.
- **Đo:** độ giống mặt (ArcFace) giữa mọi cặp ảnh trong nhóm; cặp nào giống quá ngưỡng thì báo để nhân vật sau sửa.

## Đầu ra
LOOK lưu dạng có cấu trúc: `{ô: giá trị}` + cụm tiếng Anh của từng ô + ảnh được chọn + seed. Code ghép prompt theo thứ tự A → H,
chỉ đưa vào các ô không `thường` và các ô bắt buộc (`height`, `frame`, `fat`, `face_shape`, `skin_tone`, `hair_color`), để prompt gọn
và máy vẽ dồn sức vào nét nhận diện.
