# PLAN cho Codex — Bộ định tuyến LLM-first (giữ kiến trúc, rule = fallback)

> **Thay thế** `codex_extract_before_route_prompt.md` (bản đó đổi kiến trúc + nặng rule → bỏ).
>
> Ràng buộc bắt buộc:
> - **KHÔNG đổi kiến trúc pipeline** (thứ tự stage giữ nguyên: preprocess → guardrail pre → **route** → extract(advise/knowledge) → RAG → LLM → guardrail post).
> - **KHÔNG thêm rule-based/NLP** (keyword list, regex, pronoun-detect, phân loại bằng heuristic). Rule/deterministic chỉ được tồn tại làm **FALLBACK cuối**.
> - Trọng tâm nghiên cứu là **LLM**: để LLM ra quyết định, không phải luật.

---

## 1. Vấn đề (đã quan sát trong production)
Router hiện tại = **semantic embedding** (`AITeamVN/Vietnamese_Embedding`, index 1040 dòng tiếng Việt) làm primary, **rule keyword** (`intent_router.py`) làm fallback. Nó misroute:
- Câu **tiếng Anh** → embed lệch → `clarify`/`reject`.
- **Follow-up ngắn** ("chin", "ớt bôi lên má trị được không") → router không có history → `clarify`/`reject`, vứt ngữ cảnh.
- Nuance advise-vs-clarify sai do confidence thấp.

Gốc: quyết định định tuyến đang do **embedding + keyword** (NLP), không phải LLM hiểu ngữ cảnh.

---

## 2. Giải pháp — thêm **LLM Router** làm bộ quyết định chính
Giữ nguyên **stage router** (trả về `RouteDecision`), chỉ đổi thứ tự ưu tiên cái điền vào nó:

```
Ưu tiên quyết định route:
  1) LLM Router (generative, đọc message + history)      ← MỚI, chính
  2) Semantic embedding router                            ← fallback nếu LLM lỗi/timeout
  3) Rule keyword router (intent_router.py)               ← fallback cuối cùng
```

- **LLM Router** đọc **câu hiện tại + tối đa 3 lượt history**, xuất JSON `{"intent": "<advise|knowledge|clarify|reject>", "confidence": 0..1}`. Vì là LLM đọc ngữ cảnh nên **tự xử tiếng Anh, follow-up, nuance** — **không cần** keyword/pronoun/regex.
- Semantic + rule router **không xoá**, chỉ **hạ xuống fallback** → thoả "giữ kiến trúc" + "rule chỉ fallback".

---

## 3. Thiết kế chi tiết

### D1 — LLMRouter class
- File mới `src/acne_llm/chat/llm_router.py`, mẫu theo `llm_extractor.py`:
  - `class LLMRouter(backend, model, timeout)`.
  - `classify(clean_text, history) -> RouteDecision`:
    - build prompt: INPUT_JSON `{clean_text, clean_text_no_accent, history[-3:]}` (đúng contract như intentRouter Modelfile).
    - gọi backend `generate_text(..., response_format=<json schema intent+confidence>, temperature=0.0)`.
    - parse **khoan dung** (như extractor D đã làm: chấp thiếu/thừa key, coerce) → `RouteDecision(primary_intent, confidence, source="llm", reason_code="llm_router")`.
    - Lỗi/timeout/JSON hỏng → raise `RouterFallback` để caller rơi xuống semantic.
- **Không** dùng keyword/regex trong class này.

### D2 — Model `acnellm-intent` (Ollama) khớp 4 route repo
- Sửa `model/intentRouter/Modelfile` (mình đã tạo, nhưng đang dùng 6 nhãn) → **map thẳng về 4 nhãn repo**: `advise | knowledge | clarify | reject`.
  - advise = tư vấn ca cá nhân; knowledge = hỏi kiến thức chung; clarify = mơ hồ/thiếu dữ kiện để tư vấn; reject = ngoài phạm vi.
  - Output phẳng `{"intent": "...", "confidence": ...}` (1 tầng, tránh lỗi ngoặc như đã gặp).
  - **Thêm history vào contract few-shot**: vài ví dụ có `history` để model học dùng ngữ cảnh (vd user trước hỏi mụn, lượt này "chin"/"ớt bôi" → advise).
- `keep_alive=-1`, `num_predict` nhỏ (~48), `temperature 0.1`.

### D3 — Wiring trong `intake.py` (thay đổi TỐI THIỂU, không đổi thứ tự stage)
- Tại chỗ hiện gọi router (~L475–503), đổi **thứ tự thử**:
  ```
  llm_router = getattr(c, "llm_router", None)
  if llm_router is not None:
      try:    route_decision = llm_router.classify(clean_text, history)   # đọc history
      except RouterFallback:  route_decision = <semantic như cũ>
  else:
      route_decision = <semantic như cũ>            # rồi rule như cũ
  ```
- **Không** đổi các early-return, không đổi vị trí extractor, không thêm heuristic.
- LLM router nhận `history` (repo đã có `history` trong `run_intake`) → **fix follow-up** mà không cần keyword.

### D4 — DI (`di.py`)
- Khởi tạo `llm_router` khi bật cờ: backend Ollama model `acnellm-intent` (tái dùng pattern extractor backend, `keep_alive=-1`, timeout ~8s), wire vào Container.
- Cờ config `router_mode: Literal["llm","semantic"] = "llm"` (mặc định llm; đặt "semantic" để tắt, so sánh A/B).

### D5 — Rule/NLP về đúng vai fallback
- **KHÔNG xoá** `semantic_router.py` và `intent_router.py` — chỉ để làm fallback theo thứ tự §2.
- **Không thêm** keyword mới ở bất kỳ đâu trong đường quyết định route.
- Extractor: giữ **LLM extractor primary** (đã vậy); rule extraction chỉ chạy khi `ExtractorFallback` (đã vậy). Không thêm hậu xử lý rule.

---

## 4. Không đụng tới (giữ nguyên)
- Thứ tự pipeline, các stage, guardrail pre/post, RAG, prompt build, LLM 7B.
- Vị trí extractor (vẫn sau route, chỉ advise/knowledge).
- Cơ chế an toàn (raw-safety-override, medication_check, drug rewrite).

---

## 5. Edge cases
1. LLM router **timeout/JSON hỏng** → fallback semantic → rule (không bao giờ chết).
2. Câu **tiếng Anh** → LLM router hiểu → route đúng (không phụ thuộc embedder tiếng Việt).
3. **Follow-up ngắn** trong session → LLM router thấy history → advise/tiếp tục.
4. **OOS thật** ("goku…") → LLM router → reject.
5. LLM router trả nhãn ngoài 4 enum → coi như low-confidence → fallback semantic.

---

## 6. Files
| File | Việc |
|---|---|
| `src/acne_llm/chat/llm_router.py` (mới) | `LLMRouter.classify(clean_text, history)` + `RouterFallback`; parse khoan dung; không keyword. |
| `model/intentRouter/Modelfile` | Map 4 nhãn repo + few-shot có history + output phẳng. |
| `src/acne_llm/chat/intake.py` | Đổi thứ tự thử router: LLM → semantic → rule. Truyền `history`. |
| `src/acne_llm/di.py` | Khởi tạo `llm_router` (model `acnellm-intent`), cờ `router_mode`. |
| `src/acne_llm/config.py` | `router_mode`, `router_model`, `router_timeout`. |
| `tests/` | Test router (mục 7). |

---

## 7. Tests
- LLMRouter: mock backend trả JSON hợp lệ → RouteDecision đúng; trả rác/timeout → `RouterFallback`.
- Wiring: LLM router lỗi → dùng semantic; semantic lỗi → dùng rule (thứ tự fallback).
- Hành vi (mock LLM router):
  - English acne question → advise.
  - history=[hỏi mụn], msg="chin" → advise (dùng context).
  - msg="ớt bôi lên má trị được không" + session mụn → advise (được trả lời, không clarify).
  - OOS → reject.
- Regression: `router_mode="semantic"` → hành vi cũ y nguyên (cờ tắt LLM router).

---

## 8. Acceptance
- [ ] 3 câu từng lỗi (English advise, "chin", "ớt bôi lên má") → route **advise** qua LLM router.
- [ ] Không thêm bất kỳ keyword/regex nào vào đường quyết định route.
- [ ] Rule & semantic router chỉ chạy khi LLM router fail.
- [ ] Kiến trúc pipeline không đổi (diff chỉ ở stage router + DI + Modelfile).
- [ ] `pytest -q` xanh; cờ `router_mode` bật/tắt được.

---

## 9. Trade-off
- +1 call LLM nhỏ (1.5B, warm keep_alive=-1, output ~10 token) mỗi lượt cho routing. Chấp nhận được vì mục tiêu là LLM-driven; nếu cần giảm chi phí sau này, có thể chuyển sang **LLM chỉ chạy khi semantic low-confidence** (hybrid) — nhưng KHÔNG dùng keyword để quyết định.

*Plan giữ nguyên kiến trúc, đưa quyết định định tuyến về cho LLM, đẩy toàn bộ rule/NLP xuống fallback.*
