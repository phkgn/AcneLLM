# Codex task — đo tác động của việc gỡ rule-based khỏi context handling

## Bối cảnh

Runtime vừa gỡ 3 rule cầm control-flow. Trước đó, câu follow-up dạng trần thuật
("tôi đã thử X rồi vẫn không đỡ") trượt hết whitelist tiền tố → prompt gửi cho
model 7B có `history=0` → bot hỏi lại đúng thứ người dùng vừa trả lời.

Đã gỡ:

| Rule | Vị trí cũ | Thay bằng |
|---|---|---|
| `_is_complaint` + `COMPLAINT_TERMS` (79 literal) | `chat/intake.py`, `chat/_terms.py` | không còn; intent do intaker quyết |
| `is_contextual_followup` + `_FOLLOWUP_REFERENCES` + `_PROGRESS_REPORT_MARKERS` | `chat/session.py` | `select_relevant_history` luôn trả cửa sổ 6 turn |
| `_is_followup` + `_FOLLOWUP_PREFIXES` | `chat/unified_intake.py` | history luôn được gửi cho intaker |

Đã sửa kèm: `prompt_builder.py` hardcode `max_turns=2` → `HISTORY_WINDOW_TURNS=6`;
`HISTORY_CHAR_BUDGET` 1200 → 2000; alias key `salicylic_acid` vs `salicylic acid`
trong `_mentions_stop`; guard `_has_established_case` hạ `clarify → advise` khi
phiên đã có case thật.

535 unit test pass. **Chưa có số đo e2e.** Đó là việc của task này.

## Mục tiêu

Trả lời hai câu, bằng số:

1. Việc gỡ rule có cải thiện multi-turn không, và cải thiện bao nhiêu?
2. Nó có làm hỏng single-turn không (regression)?

## Việc cần làm

### 1. Nối `d5_multiturn` vào experiment e2e

`evaluation/datasets/v1/d5_multiturn.jsonl` (72 mẫu, có `conversation_history`)
đã tồn tại và `evaluation/adapters/sse_api.py:65` đã đọc field đó, nhưng
`evaluation/configs/experiments/e2e_sse.yaml` đang trỏ `d2_test.jsonl`.

Tạo `evaluation/configs/experiments/multiturn_ablation.yaml`:

- `tier: t4`, `dataset: evaluation/datasets/v1/d5_multiturn.jsonl`
- chỉ chạy `s3.yaml` (production), không cần S0–S2 — đây là ablation runtime, không phải so model
- `seed: 42`, `chat_mode: auto`

**Xác minh trước khi chạy:** adapter phải thực sự replay `conversation_history`
vào session (gọi `/api/v1/chat/stream` nhiều lượt cùng `session_id`, hoặc seed
session store trực tiếp). Nếu nó chỉ gửi `user_query` thì toàn bộ phép đo vô
nghĩa — sửa adapter trước, và ghi rõ đã sửa gì.

### 2. Chạy ablation before/after

Hai nhánh git, cùng model `acnellm-v2-q4`, cùng seed:

- **before**: commit ngay trước loạt thay đổi này
- **after**: HEAD

Metric bắt buộc, per-sample:

| Metric | Nguồn | Vì sao |
|---|---|---|
| `clarify_rate` | `route_metadata.primary_intent == "clarify"` | bug gốc là clarify sai. Kỳ vọng giảm mạnh |
| `history_turns_in_prompt` | log `PREPROCESS` / prompt thực gửi | kỳ vọng > 0 ở mọi mẫu có history |
| `prompt_tokens` | `GENERATE status=prompt_ready approx_tokens` | canh trần `num_ctx=3072` |
| `intent_accuracy` | so với `intent_label` trong dataset | |
| `stale_fact_rate` | xem §3 | |
| `latency_ms` p50/p95 | log `OUTPUT total_ms` | prompt dài hơn ⇒ prefill lâu hơn trên CPU |

### 3. Metric mới — `stale_fact_rate`

Chưa có metric nào bắt lỗi này, mà nó là rủi ro chính khi gửi nhiều history hơn.

Định nghĩa: mẫu có `conversation_history` chứa một sản phẩm/thuốc, và turn sau
tuyên bố ngưng/đổi nó. Fail nếu câu trả lời cuối vẫn coi chất đó là đang dùng.

Đã biết `_mentions_stop` thủng hai chỗ — dùng làm seed case:

```
'retinol tôi ngưng rồi, giờ dùng bha'    -> ['salicylic acid', 'retinol']  ✗ stop-word đứng sau tên chất
'tôi chuyển sang bha thay cho retinol'   -> ['salicylic acid', 'retinol']  ✗ thay thế ngầm, không có stop-word
```

Viết ~15 mẫu vào `evaluation/datasets/drafts/` theo schema d5, gắn
`annotation_status=draft`, **không freeze**. Chạy qua `datasets/check_contamination.py`
trước khi dùng.

### 4. Regression single-turn

Chạy `d2_test` + `d4_safety` + `d7_adversarial` trên cả hai nhánh. Đây là gate:
**bất kỳ sụt nào ở `d4_safety` là chặn merge**, không thương lượng — vừa gỡ một
rule từng ép clarify, nên phải chứng minh không mở đường cho câu unsafe.

### 5. Báo cáo

`evaluation/reports/multiturn_ablation_<date>.md`, theo mẫu
`reports/debug_findings_20260717.md` đã có. Bắt buộc:

- bảng before/after mọi metric, kèm n và khoảng tin cậy
- mọi mẫu regress, trích prompt thật
- kết luận đi/không đi cho từng thay đổi riêng lẻ

## Ràng buộc

- `fallback_model: null` trong mọi system config (R4 của harness).
- Không sửa `src/acne_llm/` trong task này — trừ khi tìm ra bug, thì report riêng.
- Không freeze dataset mới. Chỉ ghi vào `drafts/`.
- Ngân sách API cho sinh draft: $2.50, dùng guard sẵn có của `generate_drafts`.

## Hai chỗ đã biết là nợ, đừng report lại như phát hiện mới

1. **`normalized_query` của knowledge turn giờ lẫn turn cá nhân trước đó.**
   Đã đánh dấu `ponytail:` trong `chat/session.py`. Bỏ referential check bằng
   keyword thì không còn gì phân biệt "Retinol là gì?" (tự đứng được) với
   "Còn loại này có nguy hiểm không?" (cần ngữ cảnh). Cách sửa đúng là intaker
   phát một field `referential: bool`, cần datagen hỗ trợ.
   **Đo giúp mức thiệt hại trên `d8_qrels`** để biết có đáng sửa gấp không.

2. **Intaker 3B có 180/180 mẫu multi-turn gán nhãn `clarify`** trong
   `datagen/intakedata/output/intake/intake.train.jsonl`. Model học "có history
   ⇒ clarify". Guard `_has_established_case` chỉ chặn hậu quả. Nếu `clarify_rate`
   sau khi sửa vẫn cao, nguyên nhân nằm ở đây chứ không phải ở runtime.

## Định nghĩa hoàn thành

- `multiturn_ablation.yaml` chạy được từ sạch, có lệnh trong README
- Bảng before/after đủ 6 metric
- `stale_fact_rate` cài xong + ~15 draft sample
- `d4_safety` không sụt
- Report merge được vào `evaluation/reports/`
