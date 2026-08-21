# `datasets/` — bộ đề cho eval

**Quy tắc: thư mục nói vai trò, tên file nói thế hệ và số dòng.**

| Thư mục | Nghĩa |
|---|---|
| `active/` | **HAI BỘ CHÍNH.** Mọi runner mặc định trỏ vào đây |
| `extra/` | Bộ phụ, chỉ chạy tay khi cần một phép đo riêng |
| `archive/` | Thế hệ cũ. **Không xoá** — artifact cũ chỉ truy được nguồn nếu còn |
| `_trash/` | Bản sao trùng lặp / 0 tham chiếu. Xoá lúc nào cũng được (~8,1 MB) |
| (gốc) | Script sinh dữ liệu + `policy_cases.jsonl` là đầu vào của chúng |

---

## `active/` — hai bộ chính

| File | Dòng | Khâu | Ai đọc |
|---|---:|---|---|
| `generator_eval.v3_2_145.jsonl` | 145 | **2 + 3** | `run_ablation.py:84` · `run_retrieval.py:47` · `full_evaluation.py:38` · `e2e.ps1` · `dashboards/generate_all.py` · `tests/test_dataset_dedup.py` |
| `generator_eval.v3_2_145.smoke.jsonl` | 10 | smoke | `full_evaluation --smoke` |
| `intake_eval.v2_1500.jsonl` | 1500 | **1** | `run_intake.py:55` (mặc định) · `e2e.ps1` |
| `intake_eval.v2_1500.audit.jsonl` | 2290 | — | nhật ký sinh, `_paths_for` tự tạo cạnh file chính |

**Vì sao khâu 2 và 3 dùng chung một file:** ablation bắt cặp chỉ hợp lệ khi mọi
arm trả lời cùng một câu. Tách ra hai bộ là `RRR − RNR` mất nghĩa ngay — đúng lỗi
đã xảy ra giữa `v1_round1` và `v2_round2`, xem `archive/README.md`.

**Đừng đổi tên file trong `active/`.** `make_intake_set_v2._paths_for` tự suy
`.partial` và `.audit` từ `--out`, nên đổi tên file chính là gãy resume. Và
`MANIFEST.json` khoá theo tên file — đổi thì phải freeze lại.

---

## `extra/` — chạy tay

| File | Dòng | Dùng khi nào |
|---|---:|---|
| `intake_eval.v1_353.jsonl` | 353 | Bộ intake hội thoại tự nhiên: mỗi dòng khai nhiều field chồng nhau. Trả lời *"model xoay xở ra sao khi người ta khai lộn xộn"*. **Lỗ đã biết:** `is_breastfeeding` chỉ có `true` trên 35 dòng khai — không đo được nhận nhầm |
| `intake_pregnancy_probe_41.jsonl` | 41 | Ca đối kháng cho `is_pregnant`: quá khứ, tự đính chính, quy nhầm chủ ngữ. Ba nhóm `active/` không có |
| `intake_eval.v2_smoke_10.jsonl` | 10 | Output của `make_intake_set_v2 --smoke` |

```bash
python -m evaluation.runners.run_intake \
    --dataset research/evaluation/datasets/extra/intake_pregnancy_probe_41.jsonl \
    --output research/evaluation/reports/pregnancy_probe/report.json
```

---

## Đọc số intake cho đúng

`intake_eval.v2_1500` phân tầng theo `meta.quota_path`: mỗi dòng dò đúng **một**
field, các field còn lại để `null` theo thiết kế. Chấm một field trên cả 1490 dòng
là gộp cả nghìn dòng nền `null` vào mẫu số.

| Field | sàn nếu chấm cả bộ | sàn nếu lọc `quota_path` | n |
|---|---:|---:|---:|
| `is_pregnant` | 0,960 | **0,500** | 60 |
| `is_breastfeeding` | 0,960 | **0,500** | 60 |
| `sex` | 0,940 | **0,333** | 90 |
| `age` | 0,952 | **0,167** | 60 |
| `skin_type` | 0,872 | **0,167** | 180 |
| `inflammation_level` | 0,599 | **0,200** | 150 |
| `lesion_types` | 0,646 | **0,100** | 300 |
| `lesion_distribution` | 0,589 | **0,091** | 330 |

`run_intake` đã có `extraction.field_accuracy_by_quota` — **đó mới là bảng nên
trích**. Bảng `field_accuracy` cũ giữ lại để đối chiếu, không để báo cáo.

`intent` thì mọi dòng đều có gold nên vẫn chấm trên cả 1490, nhưng phải báo
**macro-F1 kèm bảng từng lớp**: 94% số dòng là `advise`, nên accuracy tổng 95,8%
gần như chính là tỉ lệ nền.

---

## Nợ đã biết

`generator_eval.v3_2_145` thiếu `forbidden_claims` ở 37/145 câu (đều là
`knowledge`/`advise`; ca `reject`/`clarify` vẫn đủ). **Không vá** — v1 đã được cả
ba judge chấm với đúng bộ này, thêm trường bây giờ làm v2 được chấm bằng barem
khác v1. Ghi vào phần giới hạn của báo cáo.

Cả hai bộ generator đều có `clinical_risk_level = null` và
`annotation_status = synthetic_pending_review` ở 100% số dòng — chưa phân tầng rủi
ro lâm sàng, chưa câu nào được người duyệt tay.

`registry.load_dataset` có kiểm sha theo `MANIFEST.json`, nhưng **chưa runner nào
gọi nó** — cả ba dùng `read_jsonl` thẳng. Chỗ duy nhất gọi thật là `e2e.ps1`. Bật
guard cho runner thì làm **sau** khi chạy xong v2: `load_dataset` điền thêm
`OPTIONAL_DEFAULTS` nên `_dataset_fingerprint` sẽ đổi và mất khả năng nối arm mới
vào artifact đang có.

---

## Sinh lại

```bash
python -m evaluation.datasets.make_eval_set --generate --model deepseek-v4-pro \
       --n 100 --policy-n 45          # -> active/generator_eval.v3_2_145.jsonl
python -m evaluation.datasets.make_intake_set_v2 --yes --model deepseek-v4-pro
python -m evaluation.datasets.registry freeze evaluation/datasets/active
```

Sinh lại là tạo **thế hệ mới**, không phải sửa thế hệ cũ. Đặt tên mới kèm số dòng,
đừng ghi đè — ghi đè là mọi artifact cũ mất khả năng so sánh trong im lặng.
