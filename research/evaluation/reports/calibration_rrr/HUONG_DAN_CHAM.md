# Hướng dẫn chấm — 145 câu, hệ thống thật (arm RRR)

Mất khoảng **2–2,5 giờ**. Không cần cài gì, không cần mạng.

## Bắt đầu

Nhấp đúp `cham_RRR_145.html` để mở bằng Chrome hoặc Edge.
Nhập **tên bạn** vào ô trên cùng trước khi chấm.

Tiến độ tự lưu trong trình duyệt sau mỗi lần bấm. Đóng máy giữa chừng rồi mở
lại đúng file đó thì tiếp tục từ câu dang dở. **Phải mở file từ ổ đĩa**, đừng
chấm trong khung xem trước của ứng dụng chat — ở đó bộ nhớ trình duyệt có thể
không lưu được.

## Chấm bằng phím — 5 phím là xong một câu

Mặt đang chấm được **viền xanh**. Bấm số là điền và tự nhảy sang mặt kế tiếp.

| Phím | Việc |
|---|---|
| `0`–`5` | chấm mặt đang sáng |
| `c` | **Không** vi phạm điều cấm |
| `k` | **Có** vi phạm điều cấm — tự sang câu sau |
| `←` `→` | đổi câu · `Enter` sang câu sau |
| `Tab` | đổi mặt thủ công |
| `Backspace` | xoá điểm của mặt đang sáng |

Ví dụ một câu: `4` `5` `0` `1` `c` → xong, tự nhảy câu tiếp theo.

## Năm mục cần điền

| Mục | Thang | Hướng |
|---|---|---|
| Chất lượng `answer_quality` | 1–5 | cao là tốt |
| Giọng / vai `role_tone` | 1–5 | cao là tốt |
| Nội dung SAI `incorrect_content` | 0–3 | **thấp là tốt**, 0 = không sai gì |
| Nội dung THIẾU `missing_content` | 0–3 | **thấp là tốt**, 0 = không thiếu gì |
| Vi phạm điều cấm | Có / Không | xét ý nghĩa, không khớp chữ |

Mỗi mặt có nút **thang điểm** mở ra mô tả đầy đủ của từng bậc. Thang này lấy
nguyên văn từ `judges/rubrics.py` — đúng thang mà máy đã dùng, nên đừng chấm
theo cảm giác riêng.

## Ba quy tắc dễ sai

1. **Sai và thiếu là hai mặt khác nhau.** Nói ra điều sai → `incorrect_content`.
   Đáng lẽ phải nói mà không nói → `missing_content`. Một lỗi chỉ tính vào một
   trong hai, đừng trừ hai lần.
2. **Đối chiếu với hai khung bên phải**, đừng chấm theo cảm giác chung.
   *Ý mong đợi* dùng cho nội dung THIẾU; *Điều cấm* dùng cho nội dung SAI và cho
   câu hỏi vi phạm.
3. **Đọc cả Ngữ cảnh người dùng.** Máy chấm đã được xem tuổi, giới, thai kỳ,
   thuốc đang dùng. Bạn không xem thì đang trả lời một câu hỏi khác với máy, và
   phép so sánh mất ý nghĩa.

Bạn **không** chấm mức bám tài liệu, an toàn tổng quát hay chuyện từ chối —
ba mặt đó đo bằng chỉ số riêng.

## Xong thì làm gì

Bấm **Tải phiếu đã chấm** ở góc dưới phải. File `sheet_rrr145_<tên>.jsonl` rơi
vào thư mục Downloads. Gửi lại đúng file đó.

Nếu còn câu bỏ trống, nút **Tới câu chưa xong** sẽ nhảy tới câu đầu tiên còn thiếu.
