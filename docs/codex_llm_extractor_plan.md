# Codex Handoff — Thêm path LLM extractor (`acne-extractor:1.5b`)

> **Vai trò của bạn (Codex):** hiện thực đúng plan này. Đây là plan + skeleton hint;
> bạn ráp code vào codebase thật, giữ nguyên contract, viết test, chạy eval.
> **Không** refactor ngoài phạm vi. **Không** đụng vào các cổng guardrail/scope/refuse.

---

## 0. Mục tiêu

Thêm một path mới dùng model Ollama **`acne-extractor:1.5b`** để thay 3 hàm rule-based
trong `run_intake` (extraction + confidence + intent). Model nhả **1 JSON duy nhất**,
adapter tách thành 3 object mà pipeline hiện tại đang tiêu thụ. Bật/tắt bằng env flag,
**mặc định bật**, lỗi thì **fallback** về path rule cũ. Toàn bộ phần sau intake giữ nguyên.

**Quyết định đã chốt (không bàn lại):**
- Model làm **full intent**: `primary_intent` + `query_subject` (self/non_self) + `turn_type`
  → prompt phải nạp **history rút gọn**.
- Confidence: adapter dựng **đủ `ExtractionConfidence`** (FieldResult mỗi field, `method="llm"`).
- Legacy: `normalizer` / `intent_router` / `extraction_confidence` **giữ live làm fallback**,
  chỉ đánh dấu legacy trong docstring — KHÔNG archive, KHÔNG xoá.
- Rollout: env flag `EXTRACTOR_MODE`, default `llm` — **giữ `llm` là default kể cả khi eval cho thấy rule nhỉnh hơn**. Eval để đo/cải thiện, không dùng để đổi default.
- Base model của `acne-extractor:1.5b`: **`qwen2.5:1.5b`**.

---

## 1. Ba hàm bị thay (đều nằm trong `src/acne_llm/chat/intake.py::run_intake`)

| # | Hàm hiện tại | Dòng (~) | Output object | Ai tiêu thụ downstream |
|---|---|---|---|---|
| A | `normalize_chat_message(...)` | 328 | `base_user: UserInput` | guardrails.pre_check, scope check, fold_history_facts, extracted_entities_from_user, snapshot |
| B | `extract_with_confidence(...)` | 334 | `_extraction_conf: ExtractionConfidence` | build_confirmed_profile (ngưỡng 0.82), check_completeness |
| C | `route_intent(...)` | 545 | `route_decision: RouteDecision` | mọi nhánh route sau đó, planner gating, retrieval |

**Model = drop-in producer của A+B+C.** Mọi thứ khác trong `run_intake` giữ nguyên.

### Luồng thật (KHÔNG phải 1→model→4→5 tuyến tính)

```
1. preprocess (prepare_user_text)  -> clean_text, clean_text_no_accent
        │
   ┌────▼──────────────────────────────────────────────┐
   │  MODEL PATH (mới)                                   │
   │   acne-extractor:1.5b  -> JSON                      │
   │   adapter -> base_user + extraction_conf + route    │
   │   (validate fail -> FALLBACK 3 hàm A/B/C rule)      │
   └────┬──────────────────────────────────────────────┘
        │   (base_user, extraction_conf, route_decision)
2. guardrails.pre_check(base_user)         -> refuse?      [GIỮ NGUYÊN, luật]
3. _is_genital_scope / _scope_check_compat -> refuse?      [GIỮ NGUYÊN, luật]
4. _is_complaint(clean_text)               -> clarify?     [GIỮ NGUYÊN, luật, bỏ qua route]
5. (route_decision đã có từ model/adapter)
6. route reject -> refuse?                                  [GIỮ NGUYÊN, luật]
7. fold_history_facts(base_user, history)  -> user          [GIỮ NGUYÊN, luật]
8. build_confirmed_profile(extraction_conf,…)               [đọc confidence]
9. medication_safety_refusal(user, safety_terms) -> refuse? [GIỮ NGUYÊN, luật]
10. override clarify->advise                                 [GIỮ NGUYÊN, luật]
11. check_completeness(user, confidence=extraction_conf)     [đọc confidence]
12. planner / retrieval / prompt / generate (7B)             [GIỮ NGUYÊN]
```

**Nguyên tắc rào:** model chỉ *cung cấp dữ liệu* cho các cổng luật; nó **không thay**
bất kỳ cổng refuse/clarify/override nào. Các cổng đó vẫn chạy và giữ quyền ưu tiên.

---

## 2. Contract bắt buộc (output phải GIỐNG HỆT, không "tương tự")

### 2.1 `UserInput` — `src/acne_llm/schemas/core.py`
`model_config = ConfigDict(extra="forbid")` ở `UserContext`, `AcneClinicalInput`, `UserInput`.
→ **Bất kỳ key thừa nào trong JSON model** (ví dụ nhét `confidence`) → `ValidationError`.
→ Confidence **BẮT BUỘC** là object riêng, KHÔNG nằm trong UserInput.

Cấu trúc phải dựng:
```python
UserInput(
  description=<clean_text>,               # bắt buộc, min_length=1
  mode=<mode truyền vào từ run_intake>,   # "llm_only" | "hybrid"
  context=UserContext(
    age, sex, skin_type, is_pregnant, is_breastfeeding,
    allergies=[], current_products=[], medications=[], duration_weeks,
  ),
  clinical=AcneClinicalInput(             # None nếu không có tín hiệu lâm sàng
    lesion_types=[...],                   # Literal enum, xem core.py
    inflammation_level="none|mild|moderate|severe|unknown",
    lesion_distribution=[...], scarring_signs=[...],
    hormonal_factors=[...], treatment_goals=[...], ...
  ),
)
```
> **Enum values** phải copy đúng từ `core.py` (comedone/whitehead/…; dry/oily/…; male/female/other).
> Prompt model phải liệt kê whitelist enum; adapter phải drop giá trị lạ (không để lọt vào pydantic).

### 2.2 `ExtractionConfidence` — `src/acne_llm/chat/extraction_confidence.py`
Dataclass, mỗi field là `FieldResult` (scalar) hoặc `ListFieldResult` (list). Xem
`schemas/extraction.py`. Consumer gọi `.is_confident(thr)`, `.confident_values(thr)`,
`.max_confidence`, `.confidence`.

**Field completeness/profile THỰC SỰ đọc** (`completeness._ALL_FIELDS`) — bắt buộc có confidence:
```
lesion_types, distribution, inflammation, is_pregnant, is_breastfeeding,
allergies, skin_type, age, duration_weeks, hormonal_factors,
scarring_signs, treatment_goals
```
Các field còn lại của `ExtractionConfidence` (sex, products, medications, red_flags):
để `FieldResult.none()` / `ListFieldResult.empty()` nếu model không nhả — vẫn hợp lệ.

> **Schema change nhỏ cần làm:** `schemas/extraction.py::Method` hiện là
> `Literal["exact","pattern","fuzzy","fallback","none"]`. **Thêm `"llm"`** và
> `METHOD_BASE_CONFIDENCE["llm"] = 0.0` (vì luôn truyền confidence tay từ model).

### 2.3 `RouteDecision` — `src/acne_llm/chat/intent_router.py`
```python
RouteDecision(
  primary_intent="advise|knowledge|clarify|reject",
  query_subject="self|non_self",
  confidence=<float 0..1>,
  source="llm",                 # phân biệt với "rule"
  turn_type="answer|question|...",
  route_flags=[...],
  detected_language="vi|en|unknown",
  reason_code="llm_extractor",
)
```

---

## 3. JSON schema model `acne-extractor:1.5b` phải nhả

Model nhận (trong prompt): `clean_text`, `clean_text_no_accent`, và **history rút gọn**
(2-3 turn gần nhất, role+nội dung ngắn) để quyết `query_subject`/`turn_type`.

Model nhả **đúng 1 JSON** dạng:
```jsonc
{
  "context": {
    "age": {"value": 22, "confidence": 0.9},
    "sex": {"value": "female", "confidence": 0.8},
    "skin_type": {"value": "oily", "confidence": 0.7},
    "is_pregnant": {"value": false, "confidence": 0.95},
    "is_breastfeeding": {"value": false, "confidence": 0.95},
    "duration_weeks": {"value": 8, "confidence": 0.6},
    "allergies": [{"value": "benzoyl_peroxide", "confidence": 0.8}],
    "current_products": [{"value": "...", "confidence": 0.7}],
    "medications": [{"value": "...", "confidence": 0.7}]
  },
  "clinical": {
    "lesion_types": [{"value": "papule", "confidence": 0.85}],
    "inflammation_level": {"value": "moderate", "confidence": 0.7},
    "lesion_distribution": [{"value": "cheeks", "confidence": 0.8}],
    "scarring_signs": [], "hormonal_factors": [], "treatment_goals": []
  },
  "intent": {
    "primary_intent": "advise",
    "query_subject": "self",
    "turn_type": "answer",
    "detected_language": "vi",
    "confidence": 0.9
  }
}
```
**Contract cứng với model (ghi trong system prompt):**
- CHỈ in JSON, không markdown, không giải thích.
- `value` là `null` khi không trích được (đừng đoán bừa field an toàn).
- Enum phải nằm trong whitelist (liệt kê trong prompt).
- `confidence` ∈ [0,1].

---

## 4. Modelfile / system prompt viết lại

File: `model/Modelfile` (hiện có; xem `model/Modelfile.bak.*` để đối chiếu style).
Cần cập nhật SYSTEM để:
1. Định nghĩa nhiệm vụ: trích xuất + phân loại intent cho hội thoại tư vấn mụn tiếng Việt.
2. Dán **whitelist enum** (lesion_types, skin_type, sex, inflammation_level, distribution…).
3. Dán **JSON schema output** (mục 3) + ví dụ few-shot (2-3 cặp input→JSON), gồm 1 ví dụ
   `query_subject=non_self` (hỏi giùm người khác) và 1 ví dụ `primary_intent=knowledge`.
4. Nhấn: chỉ JSON, null khi không chắc, không bịa field an toàn.

> **`model/Modelfile.extractor` đã được viết sẵn** (base `qwen2.5:1.5b`, whitelist enum + 3 few-shot gồm ca `non_self`/`knowledge` và `clarify`). Codex dùng luôn, chỉ tinh chỉnh nếu eval đòi.
> Lệnh build: `ollama create acne-extractor:1.5b -f model/Modelfile.extractor`.
> Lưu ý enum: distribution dùng `cheeks` (không phải `cheek`); `scarring_signs`/`hormonal_factors`/`treatment_goals` là `list[str]` tự do, không whitelist.

---

## 5. File cần tạo / sửa

| File | Hành động |
|---|---|
| `src/acne_llm/chat/llm_extractor.py` | **TẠO** — gọi Ollama, parse+validate, dựng 3 object, raise `ExtractorFallback` khi lỗi |
| `src/acne_llm/schemas/extraction.py` | **SỬA** — thêm `"llm"` vào `Method` + `METHOD_BASE_CONFIDENCE` |
| `src/acne_llm/chat/intake.py` | **SỬA** — thêm nhánh model ở đầu `run_intake` (sau prepare_user_text), fallback về A/B/C |
| `src/acne_llm/config.py` + `config/settings.py` | **SỬA** — thêm `extractor_mode`, `extractor_model`, `extractor_timeout` |
| `.env` / `.env.example` | **SỬA** — `EXTRACTOR_MODE=llm`, `EXTRACTOR_MODEL=acne-extractor:1.5b`, `EXTRACTOR_TIMEOUT=20` |
| `model/Modelfile.extractor` | **TẠO** — system prompt + schema |
| `src/acne_llm/chat/normalizer.py`, `intent_router.py`, `extraction_confidence.py` | **SỬA docstring** — thêm ghi chú `LEGACY: fallback path khi EXTRACTOR_MODE=rule hoặc model lỗi` |
| `tests/test_llm_extractor.py` | **TẠO** |
| `scripts/eval_extraction*.py` | **SỬA/DÙNG** — thêm nhánh so `llm` vs `rule` + accuracy intent |

---

## 6. Skeleton hint

### 6.1 `src/acne_llm/chat/llm_extractor.py`
```python
"""LLM extraction path — thay normalizer + extraction_confidence + intent_router
trên happy path. Lỗi bất kỳ -> ExtractorFallback -> caller dùng path rule cũ."""
from __future__ import annotations
import json
from dataclasses import dataclass

from ..schemas import UserInput, UserContext, AcneClinicalInput
from ..schemas.extraction import FieldResult, ListFieldResult
from .extraction_confidence import ExtractionConfidence
from .intent_router import RouteDecision
from ..llm.ollama_backend import OllamaBackend

# whitelist enum copy từ schemas/core.py — dùng để lọc giá trị lạ TRƯỚC pydantic
_LESION = {"comedone","whitehead","blackhead","closed_comedone","papule",
           "pustule","nodule","cyst","scar","post_inflammatory_hyperpigmentation","other"}
_SKIN = {"dry","oily","combination","sensitive","normal","unknown"}
# ... (distribution, inflammation, sex tương tự)


class ExtractorFallback(Exception):
    """Raise khi model lỗi/timeout/JSON hỏng/validate fail -> caller fallback rule."""


@dataclass
class LLMExtractResult:
    user: UserInput
    confidence: ExtractionConfidence
    route: RouteDecision


class LLMExtractor:
    def __init__(self, backend: OllamaBackend, model: str, timeout: float):
        self._llm, self._model, self._timeout = backend, model, timeout

    def run(self, *, clean_text: str, clean_text_no_accent: str,
            mode: str, history: list) -> LLMExtractResult:
        try:
            raw = self._call(clean_text, clean_text_no_accent, history)
            data = json.loads(_extract_json(raw))
            user = _to_user_input(data, clean_text, mode)      # lọc enum + pydantic validate
            conf = _to_extraction_confidence(data)             # dựng FieldResult method="llm"
            route = _to_route_decision(data)                   # primary_intent/query_subject/turn_type
        except ExtractorFallback:
            raise
        except Exception as exc:                               # timeout, JSON, ValidationError...
            raise ExtractorFallback(str(exc)) from exc
        return LLMExtractResult(user, conf, route)

    def _call(self, clean_text, clean_text_no_accent, history) -> str:
        prompt = _build_prompt(clean_text, clean_text_no_accent, history)
        return self._llm.generate_text(prompt, model=self._model, timeout=self._timeout)


def _fr(node) -> FieldResult:
    if not node or node.get("value") is None:
        return FieldResult.none()
    return FieldResult.make(node["value"], "llm", confidence=float(node.get("confidence", 0.0)))

def _lfr(nodes, allowed=None) -> ListFieldResult:
    items = []
    for n in (nodes or []):
        v = n.get("value")
        if v is None or (allowed and v not in allowed):
            continue
        items.append(FieldResult.make(v, "llm", confidence=float(n.get("confidence", 0.0))))
    return ListFieldResult(items=tuple(items))

# _to_user_input / _to_extraction_confidence / _to_route_decision / _build_prompt / _extract_json:
#   - _to_user_input: lọc enum bằng _LESION/_SKIN..., bỏ giá trị lạ, rồi UserInput(...) (extra=forbid sẽ ép đúng)
#   - _to_extraction_confidence: map 12 field completeness đọc + phần còn lại none()/empty()
#   - _to_route_decision: RouteDecision(..., source="llm", reason_code="llm_extractor")
#   - _extract_json: reuse pattern OllamaQAGenerator._extract_json (bóc JSON khỏi text thừa)
```

### 6.2 Nhánh tích hợp trong `intake.py::run_intake`
Chèn NGAY SAU `prepared = prepare_user_text(...)` và `history = store.get_history(...)`,
TRƯỚC block `normalize_chat_message` hiện tại:
```python
base_user = None
_extraction_conf = None
route_override_from_llm = None   # RouteDecision hoặc None

if getattr(c.settings, "extractor_mode", "rule") == "llm" and getattr(c, "llm_extractor", None):
    try:
        res = c.llm_extractor.run(
            clean_text=clean_text, clean_text_no_accent=clean_text_no_accent,
            mode=mode, history=history,
        )
        base_user, _extraction_conf, route_override_from_llm = res.user, res.confidence, res.route
        logger.info("[{}] EXTRACTOR=llm ok", sid_short)
    except ExtractorFallback as exc:
        logger.warning("[{}] EXTRACTOR llm fallback -> rule ({})", sid_short, exc)

if base_user is None:                       # rule path (fallback hoặc mode=rule)
    base_user = normalize_chat_message(raw_message, mode=mode,
                                       clean_text=clean_text, clean_text_no_accent=clean_text_no_accent)
if _extraction_conf is None:
    _extraction_conf = extract_with_confidence(raw_message, clean_text=clean_text,
                                               clean_text_no_accent=clean_text_no_accent)
```
Tại chỗ gọi `route_intent(...)` (dòng ~545) — dùng route của model nếu có, KHÔNG bỏ luật:
```python
route_decision = route_override_from_llm or route_intent(
    clean_text, base_user, history, settings=..., current_clinical=current_clinical)
```
> Các cổng `_is_complaint` (clarify) và mọi refuse/override giữ NGUYÊN thứ tự — chúng vẫn
> có thể ghi đè `route_decision` của model. KHÔNG được đưa route model lên trước các cổng đó.

### 6.3 Rào safety song song (bắt buộc)
`_extract_safety_terms(clean_text, base_user)` và `guardrails.pre_check` / `medication_safety_refusal`
**giữ nguyên** và vẫn chạy trên raw text / base_user. Vì model có thể trích thiếu field an toàn,
thêm: **OR tín hiệu safety từ regex raw-text với field model** trước khi vào guardrail
(ví dụ nếu regex bắt "mang thai" mà model để `is_pregnant=false`, set `is_pregnant=True`).
Đặt logic OR này trong `_to_user_input` hoặc ngay sau khi có `base_user` — ghi rõ comment
`# safety net: regel raw-text override model để hard-refuse không phụ thuộc 1.5b`.

### 6.4 Config
```python
# config/settings.py
extractor_mode: str = "llm"            # "llm" | "rule"
extractor_model: str = "acne-extractor:1.5b"
extractor_timeout: float = 20.0
```
Wire vào DI (`src/acne_llm/di.py`): tạo `llm_extractor = LLMExtractor(OllamaBackend(...), extractor_model, extractor_timeout)` và gắn vào Container.

---

## 7. Tests — `tests/test_llm_extractor.py`
- JSON hợp lệ → `_to_user_input` ra `UserInput` đúng field, enum lạ bị drop.
- Confidence map: `_to_extraction_confidence` → `.is_confident(thr)` / `.confident_values(thr)` hoạt động; 12 field completeness có mặt.
- Route: `_to_route_decision` set `source="llm"`, đủ primary_intent/query_subject/turn_type.
- **Fallback:** model trả JSON hỏng / thiếu field / raise timeout → `ExtractorFallback` → `run_intake` dùng path rule (mock `c.llm_extractor.run` raise, assert kết quả == rule path).
- **Safety net:** raw text "đang mang thai" + model `is_pregnant=false` → `base_user.context.is_pregnant is True`.
- E2E: một lượt `run_intake(mode="llm")` không refuse, ra IntakeResult hợp lệ.

## 8. Verification / eval (bắt buộc trước khi tin path llm)
- Chạy `scripts/eval_extraction.py` trên `data/golden_extraction_gen.jsonl` cho cả `EXTRACTOR_MODE=rule` và `=llm`, so P/R/F per-field. Path llm **không được tụt** so với rule ở field an toàn.
- Thêm đo **accuracy intent** (primary_intent + query_subject) so với nhãn — vì đây là phần 1.5b dễ lệch nhất.
- Chạy full `pytest -q` đảm bảo không vỡ test cũ.
- Báo cáo số liệu để đo và cải thiện prompt/Modelfile. **Default vẫn là `llm` bất kể kết quả** — không đổi sang rule. Lưới safety regex song song (6.3) là lớp bảo vệ khi model trích thiếu; đó là lý do giữ được default llm an toàn.

## 9. Ràng buộc tuyệt đối (đừng vi phạm)
- KHÔNG thay/di chuyển bất kỳ cổng refuse/scope/complaint/medication/override nào.
- KHÔNG nhét confidence vào `UserInput` (extra=forbid).
- KHÔNG xoá 3 module rule — chúng là fallback path.
- KHÔNG để hard-refuse phụ thuộc một mình model — luôn OR với regex raw-text.
- Mọi lỗi model → `ExtractorFallback` → path rule; không được để exception nổi lên làm hỏng lượt chat.
```
