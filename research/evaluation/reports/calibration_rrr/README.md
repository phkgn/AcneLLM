# calibration_rrr — chấm tay toàn bộ 145 câu arm RRR

Nguồn: `reports/v2_full/ablation/results.json`, arm `RRR`, 145/145 hàng `ok`.
Thứ tự đã trộn bằng seed 42; `row_id` là khoá ghép giữa phiếu và file khoá.

| File | Vai trò |
|---|---|
| `cham_RRR_145.html` | phiếu chấm offline, mở bằng trình duyệt |
| `HUONG_DAN_CHAM.md` | hướng dẫn cho người chấm |
| `sheet_rrr145.jsonl` | phiếu rỗng dạng JSONL (dự phòng, nếu chấm bằng tay ngoài web) |
| `key_rrr145.jsonl` | **file khoá — đừng mở trước khi chấm xong** |
| `phan_tich_rrr145.py` | phân tích kết quả |

## Vì sao phiếu không hiện điểm của máy

Nhìn thấy điểm máy trước khi chấm là bị neo (anchoring); κ đo được sau đó là
κ của một người đã bị mồi, không phải κ thật. Điểm máy nằm trong `key_rrr145.jsonl`.

## Phiếu cho người xem đúng những gì máy đã xem

Máy chấm nhận: câu hỏi, **ngữ cảnh người dùng**, ý mong đợi, điều cấm, câu trả lời
(`runners/run_ablation.py::_judge_prompt`). Phiếu này hiện đủ cả năm. Bộ phiếu 60
câu trước đây thiếu ngữ cảnh người dùng — chênh lệch thông tin đầu vào làm κ đo
độ lệch dữ liệu chứ không đo chất lượng judge.

## Phân tích sau khi chấm

```powershell
# 1. chỉ số bổ sung + kiểm định cổng an toàn
.\.venv\Scripts\python.exe research\evaluation\reports\calibration_rrr\phan_tich_rrr145.py `
    <đường dẫn phiếu đã chấm>

# 2. artifact κ theo đúng định dạng repo (4 trục)
.\.venv\Scripts\python.exe -m evaluation.judges.calibrate --import <phiếu đã chấm> `
    --key research\evaluation\reports\calibration_rrr\key_rrr145.jsonl `
    --output research\evaluation\reports\calibration_rrr\judge_calibration_rrr145.json
```

## Đọc kết quả: đừng trích riêng Cohen's κ

RRR có phân bố lệch nặng — 78/145 hàng nằm đúng ở `answer_quality = 3`. Cohen's κ
phạt rất nặng khi marginal lệch như vậy: hai bên có thể đồng ý phần lớn số hàng mà
κ vẫn gần 0. Đó là **κ paradox** (Feinstein & Cicchetti 1990), không phải bằng chứng
judge kém.

`phan_tich_rrr145.py` vì thế báo thêm **Gwet's AC1** (ổn định trước marginal lệch),
**percent agreement** và **percent agreement ±1 bậc**. Khi viết vào đồ án, trích cả
cụm, đừng trích mỗi κ.

## Giới hạn của bộ này

Chấm một arm cho được điểm tuyệt đối của sản phẩm và kiểm định cổng an toàn, nhưng
**không validate được bất kỳ delta nào** giữa các arm. Mọi kết luận so sánh của
`v2_full` vẫn dựa trên LLM judge.

Bộ calibration cũ (`reports/calibration/`, n=60, κ=0,10) đo trên **lần sinh khác**
và **judge khác** — chỉ 2/145 câu trả lời trùng với `v2_full`. Không được carry-forward
con số κ đó sang `v2_full`.
