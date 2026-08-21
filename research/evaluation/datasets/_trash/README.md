# `_trash/` — xoá được

Không dòng code nào tham chiếu, và không artifact nào phụ thuộc. Giữ tạm cho tới
2026-11-20 rồi xoá cả thư mục. ~8,1 MB.

| File | Vì sao bỏ |
|---|---|
| `intake_eval.v2.partial.jsonl` | md5 **trùng khít** `intake_eval.v2.jsonl` — bản sao y hệt, 7,8 MB |
| `intake_eval.v2.smoke.partial.jsonl` | md5 **trùng khít** `intake_eval.v2.smoke.jsonl` |
| `intake_eval.v2.smoke.audit.jsonl` | 0 tham chiếu |
| `eval_set.jsonl` | chỉ xuất hiện trong ví dụ ở docstring `registry.py:4`, không phải lời gọi |
| `sample.jsonl` | 0 tham chiếu |

Khác `archive/` ở chỗ: `archive/` có artifact phụ thuộc nên **không được xoá**,
còn ở đây thì không có gì phụ thuộc.
