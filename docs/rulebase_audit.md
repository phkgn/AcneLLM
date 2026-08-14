# Rule-base audit — baseline AcneLLM

Quét ngày 2026-07-25. Tiêu chí xếp hạng: **khi rule bắn nhầm thì mất gì**, không phải rule to hay nhỏ.

Tổng: ~2.977 keyword literal / 14 file.

## Reachability — còn tồn đọng bao nhiêu khi runtime khỏe

Loại bỏ phần chỉ chạy khi LLM fail, và phần không ai gọi:

| | Literals | Ghi chú |
|---|---:|---|
| Tổng quét được | 2977 | |
| − `fallback/intent_router.py` | −351 | chỉ chạy khi unified intake **và** semantic router cùng fail |
| − `QUESTION_TERMS` | −153 | `intake._is_knowledge_question` (:144) **không ai gọi**; `normalizer` có bản regex riêng. Bản còn lại nằm trong router fallback |
| − `CASE_INTAKE_TERMS` | −168 | `_should_check_completeness` (:202) return sớm ở nhánh advise/knowledge → dòng `contains_any` **không bao giờ tới** |
| **Còn hoạt động** | **2305** | |

Phân bố phần đang chạy:

| Module | Literals | % | Vai trò |
|---|---:|---:|---|
| `chat/normalizer.py` | 1096 | 48% | substrate an toàn, chạy trước LLM |
| `guardrails/runner.py` | 789 | 34% | scope + refusal |
| `chat/_safety.py` | 143 | 6% | hậu xử lý |
| `chat/session.py` | 100 | 4% | ngữ cảnh + tombstone |
| `COMPLAINT_TERMS` | 79 | 3% | `_is_complaint` |
| `chat/intake.py` | 42 | 2% | scope + safety signal |
| `guardrails/ood_detector.py` | 42 | 2% | PII |
| `chat/completeness.py` | 12 | <1% | |
| `chat/_retrieval.py` | 2 | <1% | |

**82% nằm ở hai file substrate an toàn** (`normalizer` + `runner`) — chạy trước LLM, deterministic, sai theo hướng bảo thủ. Đây là chỗ rule *nên* ở.

Phần thực sự gây lỗi quyết định chỉ là **221 literal (~7%)**: `COMPLAINT_TERMS` 79 + `session.py` 100 + `intake.py` 42. Vấn đề không phải khối lượng mà là 221 literal đặt sai chỗ.

Không tính trong 2977: `chat/intent_router.py.bak.20260529` (660 dòng, không import).

| File | Literals |
|---|---:|
| `chat/normalizer.py` | 1096 |
| `guardrails/runner.py` | 789 |
| `chat/_terms.py` | 400 |
| `chat/routing/intent_router.py` | 351 |
| `chat/_safety.py` | 143 |
| `chat/session.py` | 100 |
| `chat/intake.py` | 42 |
| `guardrails/ood_detector.py` | 42 |
| `chat/completeness.py` | 12 |
| `chat/_retrieval.py` | 2 |

---

## Tier 1 — Short-circuit toàn pipeline

Return **trước** khi LLM được gọi. Sai ở đây không tầng nào dưới sửa được.

### 1.1 `_social_reply` — `chat/orchestrator.py:36`
- **Quyết định:** trả `fixed_reply` cứng, bỏ qua intake + RAG + LLM.
- **Kích hoạt:** `re.fullmatch` cho ok/ha/hi + substring "cảm ơn", "dừng lại", "không muốn hỏi nữa".
- **Bảo vệ hiện có:** `len(lowered.split()) > 8 → return None`; nhánh "cảm ơn" loại trừ khi có acne term hoặc dấu `?`.
- **Rủi ro:** trung bình. Guard khá chặt, nhưng "thôi không hỏi" nằm trong câu dài >8 từ thì thoát, còn câu ngắn thì bị nuốt.
- **Đề xuất:** hạ xuống prompt-signal.

### 1.2 `_is_complaint` — `chat/intake.py:243`, gọi tại `:567`
- **Quyết định:** ép `intent=clarify`, `effective_mode=clarify`, trả chuỗi xin lỗi hardcode. Bỏ extraction, RAG, LLM.
- **Kích hoạt:** `COMPLAINT_TERMS` (`_terms.py:118`, ~60 literal, **viết không dấu**) + `len(split) <= 20` + `history` không rỗng.
- **Rủi ro: CAO — đã xác nhận false positive.**

```
True  | toi khong dung retinol nua      ← "khong dung" khớp "không đúng"
True  | em khong hieu cach boi bha
True  | em hoi lai bac si roi
True  | toi noi roi ma da van khong het
True  | biet roi nhung van bi lai
False | tôi không dùng retinol nữa      ← cùng câu, có dấu
```

Bỏ dấu tiếng Việt tạo đồng âm. Điều kiện `and history` khiến nó chỉ chạy từ turn 2 — đúng vùng người dùng báo tiến triển.
- **Đề xuất:** hạ xuống prompt-signal, hoặc tối thiểu bỏ `"khong dung"`, `"khong hieu"`, `"hoi lai"`, `"noi roi"`, `"biet roi"`.

### 1.3 `GuardrailRunner._scope_refusal_if_out_of_scope` — `guardrails/runner.py:357`
- **Quyết định:** refusal, chặn toàn bộ.
- **Kích hoạt:** `_ACNE_SCOPE_TERMS`, `_GENITAL_BODY_TERMS`, `_OUT_OF_SCOPE_INTENT_TERMS` (789 literal).
- **Rủi ro:** chấp nhận được — đây là tầng an toàn, sai theo hướng bảo thủ là đúng thiết kế.
- **Đề xuất:** giữ. Rule đúng chỗ.

---

## Tier 2 — Cắt ngữ cảnh / trạng thái (SUBTRACT)

Không chặn pipeline nhưng xoá thông tin, nên LLM không có cơ hội sửa.

### 2.1 `is_contextual_followup` + `select_relevant_history` — `chat/session.py:302`, `:341`
- **Quyết định:** history có tới prompt của model 7B hay không.
- **Trạng thái:** đã nới — thêm `_PROGRESS_REPORT_MARKERS`, cửa sổ 2 → 6 turn, budget 1200 → 2000.
- **Còn lại:** vẫn là whitelist. Câu trần thuật lạ vẫn trượt.

### 2.2 `_MAX_HISTORY_TURNS` / `_is_followup` — `chat/unified_intake.py`
- **Trạng thái:** `_is_followup` + `_FOLLOWUP_PREFIXES` **đã xoá**. Cửa sổ 3 message vẫn còn (đếm message chứ không đếm lượt → user turn gốc bị đẩy ra từ turn 3).

### 2.3 `format_history_block(max_turns=...)` — `llm/prompt_builder.py:425`
- **Trạng thái:** hardcode `max_turns=2` **đã sửa** → dùng `HISTORY_WINDOW_TURNS`.

### 2.4 `_mentions_stop` / `_STOP_PRODUCT_TERMS` — `chat/session.py:444`, **13 call site**
- **Quyết định:** hoạt chất ở lại hay bị gỡ khỏi profile → feed `guardrails 20 drugs`.
- **Trạng thái:** alias key `salicylic_acid` vs giá trị thật `salicylic acid` **đã sửa**.
- **Lỗ còn lại (đã xác nhận):**

```
'retinol tôi ngưng rồi, giờ dùng bha'   -> ['salicylic acid', 'retinol']  ✗ stop-word đứng sau
'tôi chuyển sang bha thay cho retinol'  -> ['salicylic acid', 'retinol']  ✗ thay thế ngầm
```

`_mentions_stop` chỉ soi 40 ký tự **trước** tên chất. Tiếng Việt đảo đề ngữ thường xuyên.
- **Ghi chú:** rule này sai theo hướng **an toàn** (giữ thừa thuốc → cảnh báo thừa). Là rule hiếm hoi xứng đáng ở lại.

### 2.5 `snapshot_topic_shift` — `chat/session.py:606`
- Marker `"chuyển sang"`, `"nói nhầm"`, `"không phải ở"` reset `lesion_distribution` / `lesion_types`.
- **Không nhất quán:** `"chuyển sang"` là shift marker cho clinical nhưng **không** nằm trong `_STOP_PRODUCT_TERMS` — cùng cụm từ, hai hành vi.

### 2.6 `_is_acne_scope` — `chat/intake.py:82` (`_ALLOWED_ACNE_REGION_TERMS`)
- Sinh `acne_signal` → là một trong ba điều kiện của `should_retrieve` (`orchestrator.py:186`). Sai → mất RAG.

### 2.7 `_NEGATE_PREGNANCY_TERMS` / `_NEGATE_BREASTFEEDING_TERMS` — `chat/session.py:436`, `:440`
- Gỡ cờ thai kỳ. **Sai theo hướng nguy hiểm** (gỡ nhầm → mất chống chỉ định retinoid). Đáng soát kỹ nhất trong Tier 2.

### 2.8 `_GENITAL_FILTER_TERMS` — `chat/session.py:27`
- Lọc turn khỏi history chống session poisoning. Sai theo hướng an toàn. Giữ.

---

## Tier 3 — Router fallback

### 3.1 `chat/routing/intent_router.py` — 351 literal, 14 danh sách
`_FOLLOWUP_SHORT_TERMS`, `_KNOWLEDGE_RANKING_TERMS`, `_PRODUCT_QUERY_TERMS`, `_FOOD_KNOWLEDGE_TERMS`, `_PERSONAL_TERMS`, `_CASE_TERMS`, `_ADVICE_QUESTION_TERMS`, `_URGENT_EVALUATION_TERMS`, `_EMOTIONAL_TERMS`, `_CRISIS_TERMS`, `_PROGRESS_TERMS`, `_SAFETY_PRODUCT_TERMS`, `_URGENCY_TERMS`, `_MULTI_CONDITION_TERMS`.

- **Blast radius: thấp.** Chỉ chạy khi unified intake **và** semantic router cùng fail.
- **Ghi chú:** có sẵn khái niệm `progress_followup` mà `unified_intake` không dùng — logic trùng lặp giữa hai tầng.
- Còn file chết `chat/intent_router.py.bak.20260529` (660 dòng).

---

## Tier 4 — Rule extractor

### 4.1 `chat/normalizer.py` — 1096 literal, 11 bảng ánh xạ
`_SEX_TERMS`, `_PRODUCT_TERMS`, `_MEDICATION_TERMS`, `_DISTRIBUTION_TERMS`, `_LESION_TERMS`, `_HORMONAL_TERMS`, `_ALLERGY_TERMS`, `_TREATMENT_GOAL_TERMS`, `_RED_FLAG_TERMS`, `_SKIN_TYPE_QUESTION_MARKERS`, `_ACNE_RESOLVED_PATTERNS` / `_ACNE_PRESENT_PATTERNS`.

- **Chạy mọi turn** tại `intake.py:302` → `base_user`.
- Chỉ bị LLM ghi đè khi `intent ∈ {advise, knowledge}` **và** `extractor_mode == "llm"` **và** không raise `ExtractorFallback`.
- **Với clarify / reject, output của rule là output cuối** — LLM extraction không bao giờ chạy.
- **Đây là khối lớn nhất và trùng lặp nhiều nhất với intaker 3B.** Cùng một việc (BHA → salicylic acid, phủ định, canonical hoá) làm hai lần bằng hai cơ chế.
- **Đề xuất:** ứng viên số một để co lại sau khi intaker được retrain — giữ làm fallback thuần, ngừng chạy vô điều kiện.

---

## Tier 5 — Post-processing

| Rule | Vị trí | Việc |
|---|---|---|
| `get_safety_suffix` | `chat/_safety.py:152` (143 literal) | chèn cảnh báo an toàn vào output |
| `check_completeness` | `chat/completeness.py` (12 literal) | nối câu hỏi bổ sung |
| inline citation | `chat/runtime.py:321`, `orchestrator.py:312` — `re.search(r"\[\d+\]")` | ép `[1]` |
| CJK strip | `chat/orchestrator.py:305` | xoá ký tự Trung/Nhật/Hàn |

Blast radius thấp, chạy sau khi đã có nội dung. Giữ.

---

## Config chết phát hiện kèm

| Hằng | Vấn đề |
|---|---|
| `session_history_char_budget = 3000` (`config.py:234`) | **không ai đọc**; giá trị thật là `HISTORY_CHAR_BUDGET` trong `session.py`. Comment mô tả hành vi không tồn tại |
| `ASSISTANT_TURN_MAX = 200` (`session.py:41`) | khai báo, **không dùng ở đâu**. Cắt thật do `per_turn = char_budget // len(tail)` |
| `chat/intent_router.py.bak.20260529` | file backup 660 dòng còn trong `src/` |

---

## Thứ tự đề xuất

1. **Tier 1** — hạ `_is_complaint` và `_social_reply` từ control-flow xuống prompt-signal. Rẻ, đổi hành vi người dùng thấy được.
2. **Tier 2.7** — soát `_NEGATE_PREGNANCY_TERMS`; đây là rule duy nhất sai theo hướng nguy hiểm.
3. **Tier 2.4/2.5** — vá lỗ B/C của `_mentions_stop`, đồng bộ `"chuyển sang"` giữa product và clinical.
4. **Tier 4** — sau khi retrain intaker: ngừng chạy `normalizer.py` vô điều kiện, giữ làm fallback thuần.
5. Dọn config chết + file `.bak`.
