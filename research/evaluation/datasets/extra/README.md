# `extra/` — bộ đề chạy tay

Không nằm trong `full_evaluation` hay `e2e.ps1`. Chạy khi cần một phép đo riêng,
luôn phải chỉ định `--dataset` tường minh.

| File | Dòng | Vai |
|---|---:|---|
| `intake_eval.v1_353.jsonl` | 353 | Bộ intake **hội thoại tự nhiên** — mỗi dòng khai nhiều field chồng nhau (age 50%, sex 42%, products 42%). Bổ trợ cho `active/intake_eval.v2_1500` vốn cô lập từng biến |
| `intake_pregnancy_probe_41.jsonl` | 41 | Ca **đối kháng** cho `is_pregnant` |
| `intake_eval.v2_smoke_10.jsonl` | 10 | Output `make_intake_set_v2 --smoke`, kiểm ống nước |

## Lỗ đã biết của `intake_eval.v1_353`

`is_breastfeeding` có **35 dòng khai, tất cả đều `true`, 0 dòng `false`**. Không
đo được chuyện model nhận nhầm người không cho con bú thành đang cho bú — với hệ
thống mà cho con bú là chống chỉ định retinoid, đó là lỗ không vá được bằng cách
cắt lát nào. `active/intake_eval.v2_1500` chia đúng 30/30.

Đổi lại v1 cân hơn ở `lesion_types` (entropy 0,95 so với 0,54 — v2 có 71% là
`papule` do các ca advise khai kèm ngoài ý muốn) và ở `intent` (0,47 so với 0,21).

## Vì sao probe thai kỳ vẫn cần

`active/intake_eval.v2_1500` đã có 60 dòng thai kỳ chia đều 30/30, nên probe
**không** còn để bù cỡ mẫu. Nó còn vì ba nhóm đối kháng mà v2 không có:

- quá khứ — *"trước em mang thai nhưng giờ sinh rồi"*
- tự đính chính
- quy nhầm chủ ngữ — *"chị tôi đang mang thai"*

Đúng ba nhóm khiến lớp regex ghi đè trạng thái thai kỳ sai 3/13 và bị gỡ khỏi
runtime tháng 8. Từ đó **không còn gì phía sau intaker** ở trục này.
