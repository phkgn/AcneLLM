# `archive/` — thế hệ bộ đề cũ

**Không xoá thư mục này.** Mỗi file ở đây là bộ đề mà một artifact trong
`reports/` đã chạy trên đó. Xoá đi là artifact ấy mất khả năng truy nguồn.

Tên file: `<khâu>_<mục đích>.<thế hệ>_<số dòng>.jsonl`. Số dòng nằm trong tên là
cố ý — nó là thứ đã ngăn được vụ hai file trùng tên mô tả ở dưới.

| File | Dòng | `dataset_version` | sha256 | Run nào đã chạy |
|---|---:|---|---|---|
| `generator_eval.v2_0_197.jsonl` | 197 | `v2.0` | `8e93cd998bc5…` | `full_eval_1` (06-08) |
| `generator_eval.v3_1_195.jsonl` | 195 | `v3.1` | `a00e23a0ec78…` | `full_eval_part2` (07-08) · `v2_round2` (18-08) · `rescore_gpt/v2` · `rescore_luna/v2` (19-08) |
| `generator_eval.v3_1_199.jsonl` | 198 | `v3.1` | `d8b3713e9f51…` | chưa run nào dùng |

Tên cũ, để đối chiếu artifact:

```
generator_eval.v2_0_197.jsonl  ←  datasets/eval_set.v3.jsonl.bak
                                  (và trước nữa: datasets/eval_set.v3.jsonl)
generator_eval.v3_1_195.jsonl  ←  datasets/eval_set.v3.jsonl
generator_eval.v3_1_199.jsonl  ←  datasets/generated_v3_1/eval_set.v3.jsonl
```

---

## Vụ hai file cùng tên — đã xử lý 2026-08-20

Trước đó có hai file tên `eval_set.v3.jsonl` ở hai thư mục, **khác nội dung hoàn
toàn**: 0 câu trùng văn bản, dù trùng 117 `sample_id`. `sample_id` gán theo chỉ số
sinh (`q-{index:04d}`) nên id va nhau giữa các thế hệ mà nội dung khác hẳn.

Ba pool câu hỏi độc lập, không pool nào chung với pool nào một câu nào:

```
pool 1:  v2_0_197  →  v3_1_195   (bỏ 2 câu q-r001, q-c001, đổi nhãn v2.0 → v3.1)
pool 2:  v3_1_199                (độc lập, chưa dùng)
pool 3:  generated_v3_2 (145)    ← bộ chính thức hiện nay
```

Hệ quả đã xảy ra thật: `v1_round1` chạy pool 3, `v2_round2` chạy pool 1. Chúng
trùng **114 `sample_id`** nhưng **0 câu hỏi giống nhau**. Mọi phép bắt cặp v1↔v2
dựa trên 114 id đó đều ghép câu trả lời của v1 cho câu A với câu trả lời của v2
cho câu B — bootstrap, CI và McNemar ở §4 `FINALIZE.md` phải tính lại sau khi
chạy lại v2 trên pool 3.

Nguyên nhân gốc: `run_ablation.py:84` mặc định trỏ pool 1, còn `e2e.ps1:27` ép
pool 3 bằng cờ `--dataset`. Hai cửa vào, hai bộ đề. Đã thống nhất về pool 3.
