# Nhiệm vụ Codex: Ghép model Unified Intake thành 1 runtime hoàn chỉnh, gọn hoá architecture, KHÔNG crash

Bạn là agent thực thi. Tích hợp model `acne-intake` (Qwen2.5-3B, đã finetune) thay **2 LLM path cũ**
(`llm_router` + `llm_extractor`) thành **một runtime hoàn chỉnh**, dồn script không dùng vào `legacy/`,
và **đảm bảo runtime không crash + đúng format từ trước intake LLM đến sau output intake LLM**.

**Đọc trước, bắt buộc:**
1. `docs/UNIFIED_INTAKE_INTEGRATION_PLAN.md` — thiết kế adapter + wiring (làm ĐÚNG theo).
2. `src/acne_llm/chat/intake.py` — luồng gọi `c.llm_router.classify()` + `c.llm_extractor.run()`.
3. `src/acne_llm/chat/llm_extractor.py` + `llm_router.py` — chữ ký + parser tái dùng.
4. `src/acne_llm/di.py` — nơi dựng router/extractor/backend.

---

## Ràng buộc cứng (vi phạm = fail)

1. **KHÔNG deploy, KHÔNG chạy ollama, KHÔNG train.** Chỉ được chạy `pytest -q` (+ ruff nếu có). Không gọi model thật.
2. **KHÔNG đổi `intake.py`.** Interface `classify()` / `run()` phải giữ nguyên chữ ký để `intake.py` không phải sửa.
3. **Flag-gated.** Toàn bộ hành vi mới sau `settings.intake_mode` (`unified` | `legacy`). Mặc định giữ `legacy` để test cũ không đổi kết quả.
4. **KHÔNG BAO GIỜ để exception thoát khỏi intake.** Mọi lỗi model/JSON/contract → raise `RouterFallback`/`ExtractorFallback` (đã có), để `intake.py` chạy fallback. Runtime tuyệt đối không crash vì output model xấu.
5. **Giữ nguyên lớp an toàn + fallback** — xem bảng MOVE/KEEP bên dưới. Nhầm lẫn move `normalizer.py` là hỏng safety substrate = fail.

---

## Phần A — Gọn hoá architecture: thư mục `legacy/`

Tạo `src/acne_llm/chat/legacy/` và di chuyển ĐÚNG các file **chỉ dùng khi `intake_mode=legacy`**:

**MOVE vào `chat/legacy/`:**
- `llm_router.py`  → `legacy/llm_router.py`
- `llm_extractor.py` → `legacy/llm_extractor.py`

**KHÔNG MOVE (đây là fallback/substrate ACTIVE cho cả unified mode — để nguyên chỗ cũ):**
- `intent_router.py`  (rule router — fallback đường cùng)
- `semantic_router.py` (fallback tầng giữa)
- `normalizer.py`      (safety substrate always-on)
- `extraction_confidence.py` (substrate + fallback)
- `guardrails/*`       (red-flag/OOD/drug — chạy độc lập)

**Trước khi move — tách parser dùng chung** để unified adapter không phụ thuộc file legacy:
- Tạo `src/acne_llm/chat/_intake_parse.py`, chuyển vào đó các helper mà `llm_extractor.py` đang có và unified sẽ tái dùng: `_scalar_node`, `_list_nodes`, `_enum_fr`, `_int_fr`, `_bool_fr`, `_to_user_input`, `_to_extraction_confidence`, `_extract_json`, `_validate_contract`, các enum set (`_LESION`, `_SKIN`, …) và `_OLLAMA_JSON_SCHEMA`.
- `legacy/llm_extractor.py` import lại từ `_intake_parse` (không nhân bản code).
- Cập nhật mọi import trỏ tới đường mới. Chạy `pytest` xác nhận không gãy import.

---

## Phần B — Adapter `unified_intake.py` (runtime hợp nhất)

Tạo `src/acne_llm/chat/unified_intake.py` theo PLAN §2:

- `class UnifiedIntake` giữ 1 `OllamaBackend(intake_model)`, một `_infer(clean_text, history) -> dict`:
  gọi `generate_text(system=<anchor runtime>, user=<clean_text (+≤3 history)>, temperature=0.0,
  response_format=<UNIFIED_SCHEMA>)`, `_extract_json` → `json.loads` → **`_validate_contract`**.
  **Memoize theo `clean_text`** (per-turn) để `classify()` và `run()` chỉ tốn 1 inference.
- `.classify(self, clean_text, history) -> RouteDecision`: đọc `intent`/`confidence` từ dict,
  trả `RouteDecision(source="llm", reason_code="unified_intake")`. Lỗi → `raise RouterFallback`.
- `.run(self, *, clean_text, clean_text_no_accent, mode, history) -> LLMExtractResult`:
  dùng dict cache, gọi `_to_user_input` + `_to_extraction_confidence` (từ `_intake_parse`).
  Lỗi → `raise ExtractorFallback`.
- `.close()`.
- **Single-turn kỷ luật:** chỉ nối history khi thực sự là case follow-up; không đổ toàn bộ hội thoại vào prompt.

---

## Phần C — Wiring `di.py` (sau cờ)

```python
if settings.intake_mode == "unified":
    intake_backend = OllamaBackend(model=settings.intake_model, fallback_model=None, ...)
    unified = UnifiedIntake(intake_backend, settings.intake_model, settings.intake_timeout)
    llm_router = unified
    llm_extractor = unified            # cùng instance -> 1 inference cho cả 2 interface
else:
    from .chat.legacy.llm_router import LLMRouter
    from .chat.legacy.llm_extractor import LLMExtractor
    # dựng như cũ
```
`semantic_router` + rule vẫn dựng nguyên. Thêm `settings.intake_model/intake_mode/intake_timeout`
(đọc `.env`: `INTAKE_MODEL`, `INTAKE_MODE=legacy` mặc định, `INTAKE_TIMEOUT`).

---

## Phần D — Đảm bảo đúng format + KHÔNG crash (3 ranh giới)

1. **Trước intake LLM:** validate input (clean_text không rỗng; history cắt ≤3, đúng {role,content}). Sai → dùng deterministic path, không gọi model với rác.
2. **Output intake LLM:** constrained schema + `_validate_contract` (root là object; nếu có intent phải ∈ {advise,knowledge,clarify,reject}; confidence ∈ [0,1]; enum ngoài tập → drop về null như parser hiện có). Bất kỳ lệch → Fallback, **không raise ra ngoài**.
3. **Sau intake:** luôn trả `RouteDecision` hợp lệ + `UserInput` Pydantic hợp lệ. Nếu Pydantic validate fail → Fallback về deterministic, không để `ValidationError` nổi lên.

Thêm **guard chống crash**: bọc `_infer`/parse trong try/except rộng → mọi `Exception` (kể cả JSON, kiểu, timeout, key thiếu) chuyển thành `RouterFallback`/`ExtractorFallback`. Không có đường nào để exception thô thoát khỏi `classify()`/`run()`.

---

## Phần E — Test (chỉ pytest, không deploy)

Thêm `tests/chat/test_unified_intake.py`:
- Parse JSON hợp nhất hợp lệ → `RouteDecision` + `UserInput` đúng field/enum.
- 1 inference/turn (mock backend, đếm số lần gọi = 1 cho classify+run cùng clean_text).
- **Fuzz không-crash:** JSON hỏng, rỗng, thiếu key, enum lạ, confidence ngoài [0,1], input cực dài, non-JSON prose → **phải raise đúng Fallback, không raise Exception khác, không crash**.
- Single-turn: history dài không làm hỏng prompt.

Integration: chạy `intake.py` với `intake_mode=unified` (mock/patch backend trả JSON cố định) cho 5 ca
(advise/knowledge/negation/reject/clarify) → route + extract đúng; và xác nhận `intake_mode=legacy` giữ nguyên hành vi cũ (test cũ vẫn xanh).

Regression: **toàn bộ test cũ phải xanh** với default `intake_mode=legacy`.

---

## Definition of Done
- [ ] `chat/legacy/` chứa `llm_router.py` + `llm_extractor.py`; `_intake_parse.py` tách parser dùng chung; import cập nhật.
- [ ] `unified_intake.py` + `di.py` wiring sau cờ; `intake.py` KHÔNG đổi.
- [ ] 3 ranh giới format có guard; không đường nào để exception thoát khỏi `classify()`/`run()`.
- [ ] `pytest -q` xanh toàn bộ (cũ + mới); fuzz không-crash pass.
- [ ] `normalizer.py`/`intent_router.py`/`semantic_router.py`/`extraction_confidence.py`/`guardrails` KHÔNG bị move.
- [ ] Báo cáo: cây file sau refactor, diff tóm tắt, kết quả pytest. KHÔNG chạy ollama/train/deploy.
