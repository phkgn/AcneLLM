# Plan tích hợp Unified Intake model vào repo + test production

> Đưa model `acne-intake` (Qwen2.5-3B Q4, đã finetune + verify) thay **2 LLM path cũ**
> (`llm_router` + `llm_extractor`), **giữ nguyên** lớp rule-based làm fallback + safety substrate.
> Bọc sau cờ `intake_mode` → bật/tắt không revert code.

---

## 0. Nguyên tắc

1. **Không đụng `intake.py`.** Nó gọi qua interface `c.llm_router.classify()` và `c.llm_extractor.run()` — giữ nguyên interface là xong.
2. **Giữ substrate + fallback.** `normalizer.py`, `extraction_confidence.py`, `intent_router.py`, `semantic_router.py` KHÔNG xóa.
3. **Flag-gated.** `intake_mode=unified` bật model mới; `legacy` giữ nguyên 2 module cũ. Rollback = flip cờ.
4. **Single-turn sạch mỗi request** (bài học từ test: session REPL nhồi context làm hỏng confidence). Adapter gọi 1 prompt/turn, chỉ nối ≤3 history cho case followup có chủ đích.
5. **Constrained decoding** ở serve (JSON schema) → format ≈ 0.

---

## 1. Chuẩn bị serve (Ollama)

- Đăng ký model: đặt gguf + Modelfile vào `model/intake/`, `ollama create acne-intake -f Modelfile`.
  (Modelfile SYSTEM = anchor byte-identical với train — đã verify parity.)
- `.env`: thêm
  ```
  INTAKE_MODEL=acne-intake
  INTAKE_MODE=unified          # unified | legacy
  INTAKE_TIMEOUT=60
  ```
- `config/settings.py`: thêm `intake_model`, `intake_mode`, `intake_timeout`.

---

## 2. Adapter mới — `src/acne_llm/chat/unified_intake.py` (~150–220 dòng)

**Một class, một lần inference/turn, hai interface.** TÁI DÙNG parser sẵn có, không viết lại.

```
class UnifiedIntake:
    def __init__(self, llm: OllamaBackend, model: str, timeout: float): ...

    # gọi model 1 lần, cache theo clean_text (per-turn), trả dict JSON hợp nhất
    def _infer(self, clean_text, history) -> dict:
        raw = self._llm.generate_text(system=_RUNTIME_SYSTEM, user=<clean_text (+≤3 history)>,
                                      temperature=0.0, response_format=<UNIFIED_SCHEMA>)
        data = json.loads(_extract_json(raw))
        # memoize: self._cache[hash(clean_text)] = data

    # --- interface 1: thay LLMRouter ---
    def classify(self, clean_text, history) -> RouteDecision:
        data = self._infer(clean_text, history)
        return RouteDecision(primary_intent=_coerce_intent(data),
                             confidence=_coerce_confidence(data),
                             source="llm", reason_code="unified_intake")
        # lỗi -> raise RouterFallback  (giữ nguyên chuỗi fallback semantic->rule)

    # --- interface 2: thay LLMExtractor ---
    def run(self, *, clean_text, clean_text_no_accent, mode, history) -> LLMExtractResult:
        data = self._infer(clean_text, history)               # cache hit từ classify()
        user = _to_user_input(data, clean_text, mode)          # TÁI DÙNG từ llm_extractor.py
        conf = _to_extraction_confidence(data, clean_text=clean_text)  # TÁI DÙNG
        return LLMExtractResult(user=user, confidence=conf)
        # lỗi -> raise ExtractorFallback

    def close(self): ...
```

**Vì sao tái dùng được:** JSON hợp nhất có `intent`/`confidence` ở root (router đọc) và `context`/`clinical` dạng
`{value,confidence}` (đúng thứ `_to_user_input`/`_to_extraction_confidence`/`_scalar_node`/`_enum_fr` đang parse).
→ import thẳng các helper đó, không copy.

**Cache/parity:** `classify()` chạy trước (routing) → inference + cache; `run()` (extraction, chỉ khi advise)
đọc cache → đúng mục tiêu **2 call → 1**. Invalidate theo turn (clean_text đổi).

---

## 3. Wiring `di.py` (~20 dòng, sau cờ)

```python
if settings.intake_mode == "unified":
    intake_backend = OllamaBackend(model=settings.intake_model, fallback_model=None, ...)
    unified = UnifiedIntake(intake_backend, settings.intake_model, settings.intake_timeout)
    llm_router    = unified          # cùng instance
    llm_extractor = unified          # -> 1 inference phục vụ cả .classify() và .run()
else:
    # nhánh legacy: giữ y nguyên LLMRouter/LLMExtractor như hiện tại
    ...
# semantic_router + rule vẫn dựng như cũ (fallback)
```

`intake.py` không đổi: `c.llm_router.classify()` và `c.llm_extractor.run()` giờ trỏ vào cùng `UnifiedIntake`.

---

## 4. Số phận từng script cũ

| File | Vai trò cũ | Sau tích hợp |
|---|---|---|
| `llm_router.py` | LLM router riêng | **Bypass** khi `unified`; giữ cho nhánh `legacy` + rollback. Xóa sau khi unified ổn định. |
| `llm_extractor.py` | LLM extractor riêng | **Parser được TÁI DÙNG** (`_to_user_input`, `_to_extraction_confidence`, `_scalar_node`, `_enum_fr`…). Đường `.run()` LLM riêng bypass ở `unified`. Giữ file. |
| `intent_router.py` | Rule router | **GIỮ** — fallback đường cùng khi model lỗi. |
| `semantic_router.py` | Semantic router | **GIỮ** — fallback tầng giữa. |
| `normalizer.py` | Deterministic parse | **GIỮ** — safety substrate always-on (chặn thuốc/thai kỳ chạy trước model). |
| `extraction_confidence.py` | Deterministic conf | **GIỮ** — substrate + fallback. |
| `guardrails/*` | Red-flag/OOD/drug | **GIỮ** — bắt trầm cảm/red-flag độc lập model (test đã cho thấy đây là việc của substrate, không phải intake). |

Tóm: **không xóa gì ngay.** `unified` chỉ *chen vào* vị trí 2 LLM adapter; mọi lớp an toàn/fallback nguyên vẹn.
Sau 1–2 tuần chạy ổn, cân nhắc dọn `llm_router.py` + đường `.run()` của `llm_extractor.py`.

---

## 5. Test production (thứ tự)

1. **Unit** (`tests/chat/test_unified_intake.py`): parse JSON hợp nhất → RouteDecision + UserInput đúng;
   cache 1 inference/turn; JSON hỏng/enum lạ → raise Router/ExtractorFallback đúng; single-turn (không nối history sai).
2. **Integration qua `intake.py`**: chạy pipeline thật với `intake_mode=unified`, kiểm 5 ca đã test tay
   (advise/knowledge/negation/reject/clarify) + đảm bảo hard block thuốc/thai kỳ vẫn kích hoạt (substrate).
3. **A/B eval offline**: chạy `data/intent_classify.test.jsonl` (260) + benchmark hiện có
   (`data/eval/benchmark.jsonl`, `evaluation/`) trên `legacy` vs `unified`. So intent-acc, field exact-match,
   latency (kỳ vọng unified nhanh hơn: 2 call → 1). Chốt ngưỡng: unified không tệ hơn legacy.
4. **Red-flag/safety regression**: bộ `data/eval/safety_set.jsonl` + ca "trầm cảm/chảy máu" — xác nhận reject +
   guardrails đẩy sang hỗ trợ, model không bịa clinical.
5. **Shadow/canary**: bật `unified` cho % nhỏ traffic (hoặc chạy song song ghi log so sánh) trước khi 100%.

---

## 6. Rollout & rollback

- `INTAKE_MODE=legacy` (mặc định) → deploy code, chưa đổi hành vi.
- Bật `unified` ở staging → chạy test 1–4 → canary prod → 100%.
- **Rollback = set `INTAKE_MODE=legacy`** (không revert code, không redeploy model cũ).

---

## 7. Điểm đã biết cần theo dõi (từ test tay)

- **Canonicalization** (differin→adapalene) model đôi khi miss → `retrieval_query.py` đã canonical hóa ở build-query nên RAG vẫn đúng; theo dõi, thêm data nếu cần.
- **Confidence**: chạy đúng khi single-turn (0.5 mơ hồ … 0.95 rõ). BẮT BUỘC gọi single-turn/stateless — adapter đã thiết kế vậy.
- **Latency**: đo thực tế 3B Q4 trên hạ tầng serve; kỳ vọng giảm ~1 vòng inference so với legacy.

---

## 8. Checklist Definition of Done

- [ ] `ollama create acne-intake` OK, `ollama show --system` = anchor đúng.
- [ ] `unified_intake.py` + unit test xanh.
- [ ] `di.py` wiring sau cờ; `intake.py` không đổi.
- [ ] Integration 5 ca + hard-block substrate pass.
- [ ] A/B eval: unified ≥ legacy về intent-acc/field-match, latency giảm.
- [ ] Safety regression pass.
- [ ] Canary ổn → bật 100%; tài liệu rollback = flip cờ.
