# Hướng dẫn chấm — 60 câu tư vấn da mụn

Cảm ơn bạn giúp. Việc này mất khoảng **60–90 phút**, không cần cài gì.

---

## Làm sao để bắt đầu

Nhấp đúp vào file **`cham.html`**. Nó mở bằng trình duyệt (Chrome, Edge, Firefox
đều được). Không cần mạng, không cần cài phần mềm.

Nhập **tên bạn** vào ô trên cùng trước khi chấm.

---

## Bạn đang chấm cái gì

Mỗi màn hình có một **câu hỏi** của người dùng và một **câu trả lời** do máy viết.
Việc của bạn là cho điểm câu trả lời đó theo 4 tiêu chí.

Bên phải màn hình có hai khung quan trọng:

- **Ý mong đợi** — những điều một câu trả lời tốt *nên* nói
- **Điều cấm** — những điều câu trả lời *không được* nói

**Hãy đối chiếu với hai khung này khi chấm.** Đừng chấm theo cảm giác chung.

---

## Bốn tiêu chí

### 1. `answer_quality` — Chất lượng (1 đến 5, **cao là tốt**)

Câu trả lời có đúng và có dùng được không.

- **1** — Sai kiến thức y khoa, hoặc làm theo thì có hại
- **2** — Không sai nhưng thiếu gần hết ý mong đợi, đọc xong không biết làm gì
- **3** — Đúng, có ý chính, nhưng thiếu ít nhất một ý quan trọng
- **4** — Đúng, đủ ý chính, làm theo được. Chỉ thiếu chi tiết nhỏ
- **5** — Đúng, phủ hết ý mong đợi, làm theo được ngay, không lan man

### 2. `role_tone` — Giọng điệu (1 đến 5, **cao là tốt**)

Có đúng vai một trợ lý tư vấn không (không phải bác sĩ).

- **1** — Sai vai: khẳng định chắc chắn bị bệnh gì, hoặc kê đơn thuốc cho người này
- **2** — Đúng vai nhưng khô cứng, nhiều thuật ngữ khó hiểu
- **3** — Rõ ràng, đúng vai, nhưng máy móc
- **4** — Rõ ràng, thận trọng đúng mức, có nhắc đi khám khi cần
- **5** — Như 4, và còn điều chỉnh theo hoàn cảnh người hỏi mà vẫn gọn

### 3. `incorrect_content` — Nội dung SAI (0 đến 3, ⚠️ **THẤP là tốt**)

Đếm những điều câu trả lời **có nói ra** mà sai. Đối chiếu khung **Điều cấm**.

- **0** — Không có gì sai
- **1** — Có chi tiết thiếu chính xác nhưng vô hại
- **2** — Sai rõ ràng, nhưng làm theo chỉ mất công chứ không hại sức khoẻ
- **3** — Sai tới mức làm theo thì **có hại**: sai chống chỉ định, sai tương tác
  thuốc, hoặc bịa ra thông tin y khoa không có thật

### 4. `missing_content` — Nội dung THIẾU (0 đến 3, ⚠️ **THẤP là tốt**)

Đếm những điều **đáng lẽ phải nói mà không nói**. Đối chiếu khung **Ý mong đợi**.

- **0** — Không sót ý quan trọng nào
- **1** — Thiếu chi tiết phụ, vẫn làm đúng được
- **2** — Thiếu ít nhất một ý quan trọng, hoặc thiếu cảnh báo cần có
- **3** — Thiếu gần hết ý mong đợi

---

## Ba điều dễ nhầm

**Hai tiêu chí cuối ngược chiều.** `incorrect_content` và `missing_content` thì
**0 là tốt nhất**, càng cao càng tệ. Hai cái đầu thì ngược lại. Giao diện có
nhãn đỏ "THẤP LÀ TỐT" để nhắc.

**Một lỗi chỉ tính vào một chỗ.** Nếu câu trả lời **nói sai** → tính vào
`incorrect_content`. Nếu nó **không nói** điều cần nói → tính vào
`missing_content`. Đừng trừ điểm hai lần cho cùng một lỗi.

**Không chấm ba thứ này:** câu trả lời có trích nguồn không, có an toàn không,
có từ chối đúng lúc không. Ba thứ đó được đo bằng cách khác.

---

## Vài lưu ý để kết quả dùng được

**Chấm một mạch trong ngày**, đừng chia nhiều buổi cách xa nhau. Tiêu chuẩn chấm
của con người trôi theo thời gian.

**Đọc thang điểm trước khi chấm câu đầu tiên.** Mỗi tiêu chí có nút *"thang
điểm"* bung ra mô tả đầy đủ.

**Đừng bàn với người khác trong lúc chấm.** Mục đích là lấy đánh giá độc lập.

Bạn không cần biết câu trả lời nào do phiên bản nào của máy viết — và thực tế
là **không thể biết**, các câu đã được trộn ngẫu nhiên. Đó là chủ ý.

---

## Xong thì làm gì

Bấm nút **Tải kết quả** ở góc dưới bên phải.

Trình duyệt sẽ tải về một file tên `calibration_<tên bạn>.jsonl`. **Gửi lại file
đó.** Vậy là xong.

---

## Nếu gặp trục trặc

**Lỡ đóng trình duyệt** — không sao, mở lại `cham.html` là điểm còn nguyên, nó
tự lưu sau mỗi lần bấm.

**Bấm nhầm điểm** — bấm số khác đè lên là được.

**Muốn xem lại câu trước** — dùng nút *Trước / Sau*, hoặc phím mũi tên trái/phải.

**Nút Tải kết quả báo còn thiếu câu** — thanh tiến độ trên cùng cho biết đã chấm
đủ bao nhiêu câu. Quay lại chấm nốt, hoặc bấm đồng ý nếu bạn cố ý bỏ qua.
