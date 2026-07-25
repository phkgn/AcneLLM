# PLAN cho Codex — Đôn EXTRACTOR lên TRƯỚC ROUTER (extract-first)

> Mục tiêu: sửa 2 lỗi thật đã quan sát trong production:
> 1. **Misroute**: câu advise rõ ràng / follow-up ngắn / product-safety bị router semantic (embedding tiếng Việt) đẩy sang `clarify`/`reject` do confidence thấp.
> 2. **Mất thông tin**: nhánh `clarify`/`reject` return SỚM **trước** extractor → dữ kiện lâm sàng user cung cấp bị vứt, session không tích luỹ → hội thoại không hội tụ về `advise`.
>
> Cách sửa gốc: **extract TRƯỚC route**, rồi cho router dùng chính slot đã trích + ngữ cảnh session để quyết định (override khi tín hiệu mạnh). Và **luôn fold** dữ kiện, kể cả lượt clarify.

---

## 1. Bối cảnh — luồng HIỆN TẠI (`src/acne_llm/chat/intake.py::run_intake`)

Thứ tự đang chạy (số dòng tham chiếu, có thể lệch nhẹ):
```
preprocess → clean_text                                   (~L273)
rule parse (deterministic) → base_user, _extraction_conf  (~L285)
safety_terms                                              (~L293)
guardrails.pre_check(base_user)  → REFUSE nếu injection    (~L299)
scope/OOS check (hard) → REJECT sớm                        (~L403/446)
ROUTE: semantic_router.classify(clean_text)               (~L475)   ← ROUTER Ở ĐÂY
   ├─ reject → return sớm  (no extract/RAG)                (~L521)
   ├─ clarify → return sớm (no extract/RAG)                (~L542)   ← VỨT DỮ KIỆN
   └─ advise/knowledge:
        EXTRACTOR (llm) → base_user = extracted.user       (~L570)   ← GHI ĐÈ rule
        guardrails.pre_check lại + medication_check         (~L609)
        is_personal_case = advise → fold + confirmed_profile(~L647)
        completeness                                        (~L725)
return IntakeResult
```

Vấn đề cấu trúc:
- Extractor **sau** router → router không có slot để quyết định; và clarify/reject **không bao giờ** chạy extractor.
- `base_user = extracted.user` **ghi đè** kết quả rule → khi 1.5B ra rỗng thì mất luôn extraction tốt của rule (đã quan sát: `lesions=[]` dù câu rõ ràng).
- Fold gắn cứng vào `is_personal_case == advise` → clarify/knowledge không tích luỹ context.

---

## 2. Luồng ĐÍCH (extract-first)

```
preprocess → clean_text
rule parse → base_user_rule, _extraction_conf, safety_terms
guardrails.pre_check(base_user_rule)      → REFUSE nếu injection
scope/OOS HARD → REJECT sớm               (giữ nguyên: guardrail cứng vẫn trước extract)
──────────────────────────────────────────  ↓ MỚI
EXTRACTOR (nếu đáng chạy) → extracted_user
MERGE: user = merge(base_user_rule, extracted_user)   # LLM đè chỗ có, rule lấp chỗ trống
guardrails.pre_check(user) + medication_check → REFUSE nếu đòi thuốc kê đơn
FOLD: nếu user có tín hiệu lâm sàng cá nhân → fold vào session profile (KHÔNG phụ thuộc nhãn route)
ROUTE: route_decision = refine(semantic.classify(clean_text), user, session, flags)
   ├─ reject (soft) → return   (dữ kiện ĐÃ fold ở trên)
   ├─ clarify        → return   (dữ kiện ĐÃ fold)
   └─ advise/knowledge → completeness → return
```

Điểm khác cốt lõi: extractor + merge + fold **nằm trước** route; route có thêm lớp **override** dùng slot + session.

---

## 3. Thiết kế chi tiết (4 phần)

### D1 — Reorder: extractor trước router
- Trong `run_intake`, **di chuyển khối extractor** (hiện ~L570–607) lên **trước** khối `ROUTE` (~L475).
- **Giữ nguyên trước extract:** `guardrails.pre_check` (injection) và các early-return **hard scope/OOS** (guardrail cứng quyết định OOS trước, không cần trích).
- **Chuyển xuống sau extract:** hai early-return của ROUTER — `reject` (soft OOS) và `clarify`.
- Xoá điều kiện "extractor chỉ chạy cho advise/knowledge" (vì route chưa biết) — thay bằng **gate chi phí** ở D5.

### D2 — Merge LLM ∪ rule (hết mất dữ kiện)
- Thay `base_user = extracted.user` bằng hàm **`merge_user(rule_user, llm_user)`**:
  - Scalar (age, sex, skin_type, is_pregnant, is_breastfeeding, duration_weeks): lấy **LLM nếu có giá trị**, ngược lại lấy rule.
  - List (lesion_types, lesion_distribution, medications, allergies, current_products, scarring/hormonal/goals): **hợp (union)**, khử trùng lặp không phân biệt hoa/thường/dấu.
  - `inflammation_level`: ưu tiên LLM nếu ≠ null/"unknown", ngược lại rule.
  - An toàn (medications/allergies/pregnancy/breastfeeding): giữ nguyên cơ chế raw-safety-override đang có (OR với regex), áp **sau** merge.
- Nếu extractor `ExtractorFallback` (lỗi thật) → chỉ dùng rule (như hiện tại).
- Đặt `merge_user` trong `llm_extractor.py` hoặc `normalizer`/util; có unit test riêng.

### D3 — Router override dùng slot + session (sửa misroute)
Sau khi có `route_decision = semantic.classify(...)`, áp lớp **refine** (deterministic, không gọi LLM):
- **(a) Tín hiệu lâm sàng cá nhân mạnh** → ép `advise`:
  nếu `user.clinical` có `lesion_types` hoặc `lesion_distribution` (đã trích/merge) **và** có chủ thể cá nhân (đã có personal pronoun trong `clean_text` hoặc profile session đang mở) → `primary_intent = "advise"` (override `clarify`/`reject` khi semantic conf thấp). Ghi `reason_code="override_clinical_signal"`.
- **(b) Follow-up trong session mụn** → không cho rớt `reject`/`clarify` oan:
  nếu **session đã có case mụn** (confirmed_profile/фold non-empty) **và** lượt hiện tại ngắn (≤ ~12 từ) **và** không phải chuyển chủ đề rõ ràng → giữ `advise` (port logic `short_followup_in_session` từ `intent_router.py` sang path này). `reason_code="followup_in_session"`.
- **(c) Product-safety** → phải được TRẢ LỜI, không clarify:
  nếu `route_flags` có `product_safety_check` hoặc `urgency_red_flag` (guardrail đã gắn) → ép tối thiểu `advise` (để câu kiểu "bôi ớt lên mặt trị được không" được cảnh báo, không bị hỏi lại). `reason_code="safety_needs_answer"`.
- **KHÔNG override** khi thật sự OOS: nếu extractor rỗng **và** không có personal signal **và** không session-case → giữ nguyên quyết định semantic (reject/clarify hợp lệ).
- Đặt hàm `refine_route(semantic_decision, user, clean_text, session_profile, route_flags) -> RouteDecision` cạnh `semantic_router` hoặc trong `intake`.

### D4 — Luôn fold khi có tín hiệu cá nhân (không gắn nhãn route)
- Tách fold ra khỏi `is_personal_case == advise`. Điều kiện fold mới: **user có tín hiệu lâm sàng cá nhân** (lesion/distribution/personal facts) → fold + `turn_snapshot`, **bất kể** route là advise/clarify/knowledge.
- Vẫn **không** fold khi là câu hỏi kiến thức chung không có dữ kiện cá nhân (giữ chống nhiễm profile).
- `_snapshot_for_persistence` (runtime.py) đổi điều kiện tương ứng: persist khi có snapshot cá nhân, không chỉ khi `primary_intent=="advise"`.

### D5 — Gate chi phí cho extractor (kiểm soát latency)
- Extractor giờ chạy cho mọi lượt in-scope → tránh gọi 1.5B trên chitchat/OOS vô nghĩa:
  chỉ gọi **LLM extractor** khi `acne_signal == True` **hoặc** session đang có case mụn. Ngược lại (không acne-signal, không session-case) → dùng **rule** (rẻ) hoặc bỏ trích. Rule parse vẫn luôn chạy làm nền.
- Giữ `keep_alive=-1`; cân nhắc nâng `extractor_timeout` 20→30s trong `config.py`/`.env` (tách PR).

---

## 4. Edge cases (bắt buộc xử đúng)
1. **Extractor rỗng nhưng rule có** → merge giữ được rule (D2). Không còn `lesions=[]` oan.
2. **Extractor lỗi (timeout/JSON hỏng)** → `ExtractorFallback` → dùng rule (giữ nguyên).
3. **Follow-up ngắn "chin" / "ớt bôi lên má"** trong session mụn → override (b)/(c) → advise, không reject/clarify.
4. **Câu kiến thức chung** ("BHA vs AHA") không personal → không fold, route knowledge như cũ.
5. **OOS thật** ("goku đẹp trai ko") → extractor rỗng + không personal + không session-case → giữ reject.
6. **Chitchat** ("cảm ơn shop") → không acne-signal → D5 bỏ qua LLM extractor; route social/clarify như cũ.
7. **An toàn**: mọi raw-safety-override (pregnancy/breastfeeding/medications) vẫn chạy sau merge; medication_check refuse vẫn trước LLM 7B.

---

## 5. File cần sửa
| File | Việc |
|---|---|
| `src/acne_llm/chat/intake.py` | Reorder extractor lên trước route (D1); gọi `merge_user` (D2); `refine_route` (D3); đổi điều kiện fold (D4); gate chi phí (D5). |
| `src/acne_llm/chat/llm_extractor.py` | Thêm `merge_user(rule_user, llm_user)` (hoặc để util riêng) + unit test. |
| `src/acne_llm/chat/semantic_router.py` **hoặc** `intent_router.py` | Thêm `refine_route(...)` (override clinical/followup/safety). Tái dùng `_FOLLOWUP_SHORT_TERMS` sẵn có. |
| `src/acne_llm/chat/runtime.py` | `_snapshot_for_persistence`: persist theo tín hiệu cá nhân, không chỉ `advise` (D4). |
| `src/acne_llm/config.py` | (tuỳ) `extractor_timeout` 20→30. |
| `tests/test_intake.py`, `tests/test_llm_extractor.py`, `tests/test_semantic_router*.py` | Cập nhật + thêm test (mục 6). |

---

## 6. Tests
- `merge_user`: LLM có/rule có/cả hai → union đúng; scalar LLM đè rule; rule lấp chỗ LLM null; safety OR giữ nguyên.
- Extract-first: lượt `clarify`/`reject` **vẫn** có `turn_snapshot`/fold khi câu có dữ kiện lâm sàng.
- `refine_route`:
  - clinical signal + personal → advise (dù semantic trả clarify/reject).
  - follow-up ngắn trong session-case → advise.
  - `product_safety_check` flag → ≥ advise.
  - OOS thật (rỗng, không personal, không session) → giữ reject.
- Regression: OOS/chitchat/knowledge không bị override sai; không fold câu kiến thức chung.
- Latency-gate: không có acne-signal & không session-case → **không** gọi LLM extractor (mock backend assert 0 call).

---

## 7. Acceptance criteria
- [ ] Reproduce case cũ: "tôi có cục mụn đỏ ở má, đau, 2 tháng…" → advise, extractor+rule merge cho `lesion_types` không rỗng, RAG chạy, trả lời cá nhân hoá.
- [ ] "ớt bôi lên má trị được không" (follow-up) → **advise + cảnh báo**, không clarify.
- [ ] "chin" (trả lời câu hỏi bot) trong session → advise/tiếp tục, không reject.
- [ ] Clarify turn có dữ kiện → snapshot được fold (kiểm qua session store).
- [ ] OOS/chitchat vẫn reject/social đúng; không tăng gọi 1.5B trên các lượt này.
- [ ] `pytest -q` toàn xanh.

---

## 8. Trade-off & rollout
- **Chi phí**: extractor có thể chạy nhiều lượt hơn → giảm bằng D5 (chỉ khi acne-signal/session-case) + rebuild `acne-extractor:1.5b` (schema phẳng) + `keep_alive=-1`.
- **Rollout an toàn**: bọc thay đổi sau cờ config `intake_extract_before_route: bool = True` để bật/tắt so sánh A/B; mặc định bật.
- Thứ tự guardrail (pre injection/hard-OOS trước extract; post-rewrite sau LLM) **giữ nguyên** — không đụng lớp an toàn.

---

*Plan implement-ready. Không đổi hành vi guardrail an toàn; chỉ đổi thứ tự extract/route + thêm merge/override/fold.*
