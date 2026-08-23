# FINDINGS / src.chat.routing

Module: `src/acne_llm/chat/routing/` — 7 file, **3.718 LOC** (`__init__.py` 10,
`intent_router.py` 669, `llm_extractor.py` 103, `llm_router.py` 162,
`rule_extractor.py` 406, `rule_normalizer.py` 1.975, `semantic_router.py` 393).

**Quy ước đếm khối** (giữ nguyên như `src.chat.session` và `src.db`): một
dataclass = **một** khối; các trường của nó mô tả trong mục 1 của khối đó, không
tách thành khối riêng. Method và property của lớp thì tách. Hàm lồng tách.

**Phép đếm khối (Bước 0)** — đếm bằng `ast` trên source rồi gộp trường dataclass:
- `__init__.py`: 1 lời khai = **1**
- `llm_extractor.py`: 1 lời khai + `_RUNTIME_SYSTEM` + `LLMExtractor` + 5 method
  + `_build_prompt` = **9**
- `llm_router.py`: 1 lời khai + 3 hằng + `RouterFallback` + `LLMRouter` + 5 method
  + 5 hàm module = **16**
- `semantic_router.py`: 1 lời khai + 3 hằng + `SemanticPrediction` + `route_decision`
  + `SemanticRouter` + 14 thành viên = **21**
- `rule_extractor.py`: 1 lời khai + 21 tên module = **22**
- `rule_normalizer.py`: 1 lời khai + 65 tên module + 1 hàm lồng = **67**
- `intent_router.py`: 1 lời khai + 31 tên module (gồm `RouteDecision`)
  + `RouteDecision.metadata` + 1 hàm lồng = **34**

→ **170 khối × 8 mục = 1.360 mục.**

---

## §1 — NÉN CÓ KHAI BÁO (đọc trước §5 và §6)

Hai file trong module này chứa các **bảng term** thuần dữ liệu: `intent_router.py`
có 18 tuple/frozenset chuỗi, `rule_normalizer.py` có 13 bảng
`list[tuple[nhãn, regex]]` cùng 6 tuple/dict hằng. Với **31 bảng term đó**, bốn
mục sau là hằng số của **dạng dữ liệu**, không phải của từng bảng, nên tôi phát
biểu một lần ở đây thay vì lặp 31 lần. Đây là nén **có khai báo**: phát biểu dưới
đây áp cho đúng 31/31 bảng, và bảng nào lệch đều được ghi đè tại chỗ.

- **Mục 2 — side effect:** không. Đều là hằng module, dựng một lần lúc import.
  Bảng nào gọi hàm để dựng (`_ALLERGY_TERMS` gọi `_allergy_pattern`) thì việc đó
  cũng chỉ chạy lúc import. {code}
- **Mục 3 — state:** immutable trên thực tế. Các bảng `list[tuple[...]]` của
  `rule_normalizer` **về kỹ thuật là list và sửa được**, nhưng grep toàn repo
  không có chỗ nào `.append`/`.remove` lên chúng. {code}
- **Mục 4 — lỗi:** bảng chứa regex raise `re.error` lúc **import** nếu pattern
  sai. Với `rule_normalizer` là lỗi lúc import của cả `chat/` — nhưng những bảng
  đó **không** compile sẵn (chuỗi thô, compile lại mỗi lần `re.search`), nên lỗi
  cú pháp regex chỉ nổ khi hàm tương ứng chạy lần đầu, không phải lúc import.
  Xem Q-12. {code}
- **Mục 7 — invariant:** mọi bảng đều liệt kê **song song có dấu và không dấu**
  (`"nguyên nhân", "nguyen nhan"`), vì các hàm gọi chúng chạy hai lượt qua
  `_texts_for_extraction` (bản có dấu + bản bỏ dấu). Nghĩa là **một khái niệm
  phải được viết ở hai chỗ**, và thiếu một biến thể là mất tín hiệu im lặng.
  Đây là invariant tốn kém nhất của module. {code}

Mục **1, 5, 6, 8** khai riêng cho từng bảng ở §5/§6, kèm mọi nhận xét riêng.

---

## `__init__.py`

### [x] docstring `routing/__init__.py:1-10`
1. in/out: 10 dòng lời khai; file không export gì. {doc}
2-5. không. {doc}
6. ai gọi: không ai đọc `__doc__`; package không có `__all__` và không re-export. {code}
7. invariant khai báo: "Đổi tên từ `chat/fallback` ở Phase 7. Tên cũ sai: nó nói
   'chỉ chạy khi vỡ', nhưng `intent_router.compute_route_flags` chạy trên 100%
   request. Ba tầng router thực tế: llm_router (UnifiedIntake) → semantic_router
   → route_intent (rule)". **Đối chiếu code:** `intake.py:~570` gọi
   `compute_route_flags` không điều kiện — lời khai thứ nhất đúng. Thứ tự ba tầng
   cũng khớp `intake.py`. {code+doc}
8. deprecated: không. {doc}

---

## `llm_extractor.py`

### [x] docstring `llm_extractor.py:1-5`
1. in/out: 5 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Legacy dedicated LLM extractor adapter... this rollback
   path". **Đối chiếu:** `di.py:165` import file này **bên trong nhánh `else`**
   của `if intake_mode == "unified"`. `.env` đặt `INTAKE_MODE=unified`, nên file
   này **không được import lần nào** trong production. Lời khai đúng và mạnh hơn
   nó tự nhận: không phải "rollback path", mà là code chưa từng chạy ở cấu hình
   hiện tại. Xem Q-01. {code+doc}
8. deprecated: chưa đánh dấu deprecated; nên đánh dấu. {code}

### [x] `_RUNTIME_SYSTEM` (`llm_extractor.py:33-36`)
1. in/out: chuỗi system prompt 2 câu tiếng Việt. {code}
2-4. không. {code}
5. config: hằng cứng; **không** đọc từ `model/*/prompts/`, khác generator vốn
   lấy prompt từ file (`system_prompt.v4.a.txt`). {code}
6. ai gọi: `_call:76`. {code}
7. invariant: gửi qua `generate_text(system=...)`, nhưng backend được `di.py:220`
   dựng với `use_modelfile_system=True` — `ollama_backend._build_messages:196`
   bỏ system message, để Modelfile SYSTEM tự lo. Chuỗi này không tới model; bản
   thật nằm ở `model/legacy/Modelfile.extractor` và **dài hơn hẳn**. Xem Q-02. {code}
8. deprecated: không. {code}

### [x] `LLMExtractor` (`llm_extractor.py:39-85`)
1. in/out: `LLMExtractor(backend, model, timeout)`. {code}
2. side effect: gọi Ollama. {code}
3. state: `_llm`, `_model`, `_timeout`. {code}
4. lỗi: mọi lỗi thành `ExtractorFallback`. {code}
5. config: `settings.extractor_model`, `settings.extractor_timeout`. {code}
6. ai gọi: `di.py:216` — chỉ ở nhánh legacy. {code}
7. invariant: docstring lớp nói "adapt its JSON contract"; hợp đồng parse nằm ở
   `chat/_intake_parse.py` dùng chung với `UnifiedIntake`. Đúng — file này import
   7 tên từ đó và không tự parse gì. {code}
8. deprecated: xem Q-01. {code}

### [x] `LLMExtractor.__init__` (`llm_extractor.py:42-45`)
1. in/out: `(backend: OllamaBackend, model: str, timeout: float) -> None`. {code}
2. side effect: không. {code}
3. state: 3 thuộc tính. {code}
4. lỗi: `float(timeout)` raise nếu không parse được. {code}
5. config: từ `di.py`. {code}
6. ai gọi: `di.py:216`. {code}
7. **invariant: `self._timeout` được gán và không bao giờ đọc.** Timeout thật đã
   được áp ở tầng HTTP khi `di.py:219` dựng `OllamaBackend(timeout=router_timeout)`.
   Thuộc tính ở đây là bản sao chết. `LLMRouter` cũng gán như vậy nhưng **có**
   property `timeout` phơi ra; lớp này thì không — bất đối xứng giữa hai adapter
   anh em. Xem Q-03. {code}
8. deprecated: không. {code}

### [x] `LLMExtractor.model` (property, `llm_extractor.py:47-49`)
1. in/out: `() -> str`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: grep `\.model\b` trong `chat/` — không caller nào đọc property này
   trên `LLMExtractor`. `utils/logging.py` đọc `settings.extractor_model` chứ
   không đọc object. {code}
7. invariant: chỉ đọc, không setter. {code}
8. deprecated: 0 caller. {code}

### [x] `LLMExtractor.run` (`llm_extractor.py:51-71`)
1. in/out: keyword-only `(clean_text, clean_text_no_accent, mode, history) -> LLMExtractResult`. {code}
2. side effect: một lời gọi Ollama. {code}
3. state: không. {code}
4. lỗi: `ExtractorFallback` được **re-raise nguyên** (`:66-67`) trước khi
   `except Exception` bọc — đúng thứ tự, giữ được thông điệp gốc từ
   `_validate_contract`. {code}
5. config: không. {code}
6. ai gọi: `intake.py` qua `c.llm_extractor.run(...)` — chỉ nhánh legacy. {code}
7. invariant: chuỗi 5 bước `_call → _extract_json → json.loads →
   _validate_contract → _to_user_input/_to_extraction_confidence`. Cùng đúng thứ
   tự với `UnifiedIntake.run`, nên hai đường cho cùng kết quả trên cùng JSON. {code}
8. deprecated: xem Q-01. {code}

### [x] `LLMExtractor._call` (`llm_extractor.py:73-80`)
1. in/out: `(clean_text, clean_text_no_accent, history) -> str`. {code}
2. side effect: HTTP tới Ollama. {code}
3. state: không. {code}
4. lỗi: mọi lỗi transport nổi lên `run` và thành `ExtractorFallback`. {code}
5. config: `temperature=0.0`, `response_format=_OLLAMA_JSON_SCHEMA`. {code}
6. ai gọi: `run:60`. {code}
7. invariant: `generate_text` **không nhận `num_predict`** (xem `src.llm`,
   `ollama_backend.py:222-224`), nên giới hạn 512 token của extractor chỉ đến từ
   `di.py:206` lúc dựng backend, không override được per-request. {code}
8. deprecated: không. {code}

### [x] `LLMExtractor.close` (`llm_extractor.py:82-85`)
1. in/out: `() -> None`. {code}
2. side effect: đóng HTTP client của backend. {code}
3. state: không của chính nó. {code}
4. lỗi: không bắt. {code}
5. config: không. {code}
6. ai gọi: `di.py:73-74` (`Container.close`). {code}
7. invariant: gác bằng `getattr` + `callable` thay vì gọi thẳng — phòng cho
   backend giả trong test. Trong chế độ unified, `di.py:158-159` gán **cùng một**
   `UnifiedIntake` cho cả `llm_router` lẫn `llm_extractor`, nên `Container.close`
   gọi `close()` **hai lần** trên cùng object. Xem Q-04. {code}
8. deprecated: không. {code}

### [x] `_build_prompt` (`llm_extractor.py:88-113`)
1. in/out: `(clean_text, clean_text_no_accent, history) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: 3 lượt gần nhất, mỗi lượt tối đa 300 ký tự — hằng cứng. {code}
6. ai gọi: `_call:74`. {code}
7. invariant: vòng lặp dựng `short_history` là **bản sao từng dòng** của
   `llm_router._short_history:94-108`. Hai file cạnh nhau, một bên tách hàm, một
   bên nội tuyến. Xem Q-05. {code}
8. deprecated: không. {code}

---

## `llm_router.py`

### [x] docstring `llm_router.py:1-7`
1. in/out: 7 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Any transport, model, JSON, or contract failure is
   converted to `RouterFallback` so intake can use the semantic router and then
   the legacy deterministic router without changing pipeline order."
   **Đối chiếu:** `classify:83-86` bọc `except Exception` → `RouterFallback`; 4
   hàm helper cũng raise `RouterFallback` trực tiếp. 5/5 đường lỗi đúng lời khai. {code+doc}
8. deprecated: cùng tình trạng `llm_extractor` — import trong nhánh `else` của
   `di.py:166`, không chạy ở `INTAKE_MODE=unified`. Xem Q-01. {code}

### [x] `_ALLOWED_INTENTS` (`llm_router.py:19-21`)
1. in/out: `frozenset({"advise","knowledge","clarify","reject"})`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_OLLAMA_JSON_SCHEMA:31` (qua `sorted(...)`), `_coerce_intent:147`. {code}
7. invariant: khớp đúng 4 giá trị của `PrimaryIntent`
   (`intent_router.py:31`) — nhưng là **bản sao thủ công**, không suy ra từ
   `typing.get_args(PrimaryIntent)`. Thêm một intent vào Literal mà quên bảng này
   thì router LLM từ chối intent mới và rơi fallback im lặng. {code}
8. deprecated: không. {code}

### [x] `_RUNTIME_SYSTEM` (`llm_router.py:22-25`)
1. in/out: chuỗi system prompt. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `classify:67`. {code}
7. invariant: cùng cơ chế `use_modelfile_system=True` như `llm_extractor`
   (`di.py:186`) — chuỗi này không tới model; bản thật ở `model/legacy/Modelfile`.
   Xem Q-02. {code}
8. deprecated: không. {code}

### [x] `_OLLAMA_JSON_SCHEMA` (`llm_router.py:26-41`)
1. in/out: dict JSON Schema — `intent` (enum), `confidence` (number 0..1),
   `required` cả hai, `additionalProperties: False`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `classify:70` (tham số `response_format`). {code}
7. invariant: schema **được Ollama ép ở phía server**, nhưng code vẫn kiểm lại
   toàn bộ ở `_coerce_intent`/`_coerce_confidence`. Hai lớp gác cho cùng một hợp
   đồng — đúng, vì `format` chỉ là gợi ý grammar và model vẫn trả rác được. {code}
8. deprecated: không. {code}

### [x] `RouterFallback` (`llm_router.py:44-45`)
1. in/out: lớp con `Exception`, không thân. {code}
2-3. không. {code}
4. lỗi: chính nó là tín hiệu. {code}
5. config: không. {code}
6. ai gọi: raise ở 6 chỗ trong file; bắt ở `intake.py`. {code}
7. invariant: kế thừa `Exception` trần (không `RuntimeError` như
   `BM25ChecksumError`) — nghĩa là `except Exception` ở `classify:83` **sẽ** bắt
   nó, và đó là lý do phải có `except RouterFallback: raise` ở `:81-82` đứng
   trước. Thứ tự đúng. {code}
8. deprecated: không. {code}

### [x] `LLMRouter` (`llm_router.py:48-91`)
1. in/out: `LLMRouter(backend, model, timeout)`. {code}
2. side effect: gọi Ollama. {code}
3. state: 3 thuộc tính. {code}
4. lỗi: `RouterFallback`. {code}
5. config: `settings.router_model` (`acnellm-intent`), `settings.router_timeout` (8.0). {code}
6. ai gọi: `di.py:188` — nhánh legacy. {code}
7. invariant: chỉ có `classify` là hành vi thật; lớp mỏng. {code}
8. deprecated: xem Q-01. {code}

### [x] `LLMRouter.__init__` (`llm_router.py:51-54`)
1. in/out: `(backend, model: str, timeout: float) -> None`. {code}
2-3. gán 3 thuộc tính. {code}
4. lỗi: `float(timeout)`. {code}
5. config: từ `di.py`. {code}
6. ai gọi: `di.py:188`. {code}
7. invariant: `self._timeout` không được dùng trong bất kỳ lời gọi nào — xem Q-03. {code}
8. deprecated: không. {code}

### [x] `LLMRouter.model` (property, `:56-58`)
1. in/out: `() -> str`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: 0 caller. {code}
7. invariant: chỉ đọc. {code}
8. deprecated: 0 caller. {code}

### [x] `LLMRouter.timeout` (property, `:60-62`)
1. in/out: `() -> float`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: **0 caller** — phơi ra một giá trị mà chính lớp cũng không dùng. {code}
7. invariant: `LLMExtractor` không có property tương ứng. Bất đối xứng. {code}
8. deprecated: 0 caller. Xem Q-03. {code}

### [x] `LLMRouter.classify` (`llm_router.py:64-86`)
1. in/out: `(clean_text: str, history: list) -> RouteDecision`. {code}
2. side effect: một lời gọi Ollama. {code}
3. state: không. {code}
4. lỗi: `RouterFallback` re-raise trước `except Exception`. {code}
5. config: `temperature=0.0`, `response_format=_OLLAMA_JSON_SCHEMA`. {code}
6. ai gọi: `intake.py` qua `c.llm_router.classify(...)`. {code}
7. **invariant: `RouteDecision` trả về có `route_flags=[]`** (default của
   dataclass). Đây chính là lý do `compute_route_flags` phải chạy riêng ở
   `intake.py` cho mọi đường — docstring `intent_router.py:6-11` nói đúng điều đó.
   Ngoài ra `turn_type` và `detected_language` cũng giữ default
   (`"answer"`, `"unknown"`), nên đường LLM không bao giờ phát hiện ngôn ngữ. {code}
8. deprecated: xem Q-01. {code}

### [x] `LLMRouter.close` (`llm_router.py:88-91`)
1. in/out: `() -> None`. {code}
2. side effect: đóng backend. {code}
3-4. như `LLMExtractor.close`. {code}
5. config: không. {code}
6. ai gọi: `di.py:78-79`. {code}
7. invariant: ở chế độ unified `Container.close` gọi `.close()` hai lần trên cùng
   object; `UnifiedIntake.close` idempotent nên vô hại (Q-04). {code}
8. deprecated: không. {code}

### [x] `_short_history` (`llm_router.py:94-108`)
1. in/out: `(history: list) -> list[dict[str, str]]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không — bỏ qua mọi turn sai hình dạng. {code}
5. config: 3 lượt, 300 ký tự — hằng cứng, trùng số với `llm_extractor`. {code}
6. ai gọi: `_build_prompt:117`. {code}
7. invariant: chấp nhận **cả** `Mapping` lẫn object có `.role/.content` — nghĩa
   là nó không tin `ConversationTurn` là kiểu duy nhất. Cùng cách viết ở
   `llm_extractor._build_prompt`. Bản sao — xem Q-05. {code}
8. deprecated: không. {code}

### [x] `_build_prompt` (`llm_router.py:111-122`)
1. in/out: `(clean_text: str, history: list) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `RouterFallback("router clean_text must be non-empty")` nếu text rỗng —
   raise **trước** khi gọi model, tiết kiệm một lượt. {code}
5. config: không. {code}
6. ai gọi: `classify:68`. {code}
7. invariant: gọi `strip_accents(clean_text)` để tự sinh bản không dấu, trong khi
   `llm_extractor._build_prompt` **nhận** `clean_text_no_accent` từ người gọi.
   Hai adapter, hai nguồn cho cùng một trường của payload — nếu `intake.py` từng
   chuẩn hoá khác `strip_accents` thì hai đường lệch nhau. {code}
8. deprecated: không. {code}

### [x] `_extract_json` (`llm_router.py:125-137`)
1. in/out: `(raw: str) -> str`; cắt phần giữa `{` đầu và `}` cuối. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: 2 nhánh `RouterFallback` (rỗng, không có object). {code}
5. config: không. {code}
6. ai gọi: `classify:72`. {code}
7. invariant: **trùng tên và gần trùng nội dung** với
   `_intake_parse._extract_json`, nhưng bản kia raise `ExtractorFallback`. Hai
   hàm cùng việc, hai kiểu lỗi. `text.rfind("}")` lấy dấu đóng **cuối cùng**, nên
   model trả hai JSON liên tiếp sẽ cho ra chuỗi không parse được → `json.loads`
   raise → `RouterFallback`. Fail-closed. {code}
8. deprecated: không. {code}

### [x] `_coerce_intent` (`llm_router.py:140-149`)
1. in/out: `(data: Any) -> PrimaryIntent`. {code}
2-3. không. {code}
4. lỗi: 3 nhánh `RouterFallback`. {code}
5. config: `_ALLOWED_INTENTS`. {code}
6. ai gọi: `classify:73`. {code}
7. invariant: `.strip().lower()` trước khi so — chấp nhận `"Advise "`. Intent
   ngoài enum **không** bị ép về mặc định mà làm cả lượt rơi fallback; đúng
   hướng an toàn cho một hệ y tế. {code}
8. deprecated: không. {code}

### [x] `_coerce_confidence` (`llm_router.py:152-162`)
1. in/out: `(data: Mapping) -> float`. {code}
2-3. không. {code}
4. lỗi: 3 nhánh `RouterFallback` — trong đó `isinstance(raw, bool)` bị chặn
   **trước** `float(raw)`, vì `float(True) == 1.0` sẽ lọt im lặng. Đây là chi
   tiết đúng mà nhiều code bỏ sót. {code}
5. config: không. {code}
6. ai gọi: `classify:74`. {code}
7. invariant: kiểm NaN bằng `confidence != confidence` rồi mới kẹp `[0,1]` —
   thứ tự bắt buộc, vì `max/min` với NaN cho kết quả phụ thuộc thứ tự toán hạng.
   Ba lớp gác (bool, NaN, kẹp) cho một số. Là hàm cẩn thận nhất module. {code}
8. deprecated: không. {code}

---

## `semantic_router.py`

### [x] docstring `semantic_router.py:1-6`
1. in/out: 6 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "Only the stratified *train* split is indexed"; "cached in
   a plain NumPy archive keyed by the train-file hash and local embedder model".
   **Đối chiếu:** `_read_train_rows:300` từ chối mọi nhãn ngoài 3 in-scope intent,
   nên file test/OOS không nạp được — lời khai 1 được **code cưỡng chế**, không
   chỉ hứa. `_cache_metadata:340-347` gồm `train_sha256` + `model_name` — lời khai
   2 đúng, và còn chặt hơn (thêm `schema_version`, `train_path`, `rows`). {code+doc}
8. deprecated: không. {doc}

### [x] `InScopeIntent` (`semantic_router.py:22`)
1. in/out: `Literal["advise","knowledge","clarify"]`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: chú thích kiểu cho `_IN_SCOPE_INTENTS`. {code}
7. invariant: **3** giá trị, trong khi `PrimaryIntent` có **4** (thêm `reject`).
   Cố ý: `reject` không phải nhãn train mà là kết quả của cổng khoảng cách OOS
   (`predict:175-189`). Sự khác biệt này không được ghi ở đâu ngoài chính tên. {code}
8. deprecated: không. {code}

### [x] `_IN_SCOPE_INTENTS` (`semantic_router.py:23-27`)
1. in/out: tuple 3 chuỗi. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `predict:180,199`, `_read_train_rows:300`, `_load_cache:329`. {code}
7. invariant: dùng ở **cả** đường validate dữ liệu train, đường validate cache, và
   đường dựng `vote_scores`. Một nguồn sự thật cho ba việc — đúng thiết kế. {code}
8. deprecated: không. {code}

### [x] `_CACHE_SCHEMA_VERSION` (`semantic_router.py:28`)
1. in/out: `int = 1`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_cache_metadata:342`. {code}
7. invariant: nằm trong metadata so sánh **bằng `!=` trên cả dict**
   (`_load_cache:319`), nên đổi số này làm cache cũ bị coi là khác và dựng lại.
   Cơ chế đúng, khác `SESSION_SCHEMA_VERSION` vốn so từng trường. {code}
8. deprecated: không. {code}

### [x] `SemanticPrediction` (`semantic_router.py:31-43`)
1. in/out: dataclass **frozen**, 9 trường chẩn đoán. {code}
2. side effect: không. {code}
3. state: immutable. {code}
4. lỗi: gán lại raise `FrozenInstanceError`. {code}
5. config: không. {code}
6. ai gọi: `predict` dựng; `classify` tiêu thụ; script hiệu chuẩn đọc trường
   chẩn đoán. {code}
7. invariant: docstring nói "Full classifier diagnostics used by
   calibration/evaluation" — `neighbor_indices` chỉ có nghĩa với người giữ file
   train, tức chỉ dùng được lúc hiệu chuẩn. Trường này mặc định `None` nên
   không bắt buộc. {code}
8. deprecated: không. {code}

### [x] `SemanticPrediction.route_decision` (`semantic_router.py:45-52`)
1. in/out: `() -> RouteDecision`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `classify:125`. {code}
7. **invariant đáng ngờ:** `confidence=max(0.0, min(1.0, self.nearest_similarity))`
   — dùng **độ tương đồng với láng giềng gần nhất** làm confidence, chứ không
   dùng `vote_margin` hay `vote_scores[top]`. Hệ quả: một truy vấn có 9 láng giềng
   chia đều 3 nhãn (margin ~0) vẫn nhận confidence cao nếu láng giềng số 1 rất
   gần. Hai đại lượng đo hai thứ khác nhau, và cái được chọn không phản ánh mức
   chắc chắn của **nhãn**. Xem Q-06. Cũng như `LLMRouter`, `route_flags` để rỗng. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter` (`semantic_router.py:55-393`)
1. in/out: keyword-only `SemanticRouter(embedder, train_path, cache_path, k,
   oos_distance_threshold, ambiguity_margin, eager)`. {code}
2. side effect: đọc file train, có thể encode toàn bộ tập và ghi cache. {code}
3. state: `_embeddings`, `_labels`, `_texts`, `_train_sha256`, `_cache_hit`. {code}
4. lỗi: `ValueError` cho mọi tham số ngoài miền; `FileNotFoundError` nếu thiếu
   train split. {code}
5. config: 5 field `Settings` (`semantic_router_train_path`, `_cache_path`, `_k`,
   `_oos_distance_threshold`, `_ambiguity_margin`) — tất cả đi qua `di.py`. {code}
6. ai gọi: `di.py`; `intake.py` (tầng 2). {code}
7. invariant: docstring lớp liệt kê 6 tham số nhưng **bỏ `eager`** — tham số thứ
   7, và là tham số quyết định startup có encode 100% tập hay không. Lời khai
   thiếu đúng cái tốn kém nhất. {code+doc}
8. deprecated: không. {code}

### [x] `SemanticRouter.__init__` (`semantic_router.py:70-101`)
1. in/out: keyword-only, 7 tham số. {code}
2. side effect: `_ensure_index()` khi `eager=True` (mặc định). {code}
3. state: khởi tạo 11 thuộc tính. {code}
4. lỗi: **4 kiểm tiền điều kiện** — embedder None, `k < 1`,
   `oos_distance_threshold` ngoài `[0,2]`, `ambiguity_margin` ngoài `[0,1]`. {code}
5. config: default `k=9`, `oos=0.483609`, `margin=0.08` — khớp `config.py:118-120`. {code}
6. ai gọi: `di.py`, test. {code}
7. invariant: miền `[0, 2]` cho `oos_distance_threshold` ở đây **rộng hơn**
   `[0, 1]` mà validator `config.py:129-137` cho phép. Miền `[0,2]` là đúng toán
   học (cosine distance), miền `[0,1]` của validator là ràng buộc chặt hơn thực
   tế — đã ghi ở `src.config`, nay xác nhận từ phía người dùng: lớp này chấp nhận
   giá trị mà `Settings` từ chối. Xem Q-07. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter.indexed_rows` (property, `:103-107`)
1. in/out: `() -> int`. {code}
2. side effect: `_ensure_index()` — property có thể encode cả tập. {code}
3. state: có thể điền index. {code}
4. lỗi: `assert self._labels is not None` — `assert` bị `python -O` gỡ. {code}
5. config: không. {code}
6. ai gọi: script hiệu chuẩn/eval; không có caller trong `src/`. {code}
7. invariant: một property mà việc đọc nó có thể tốn hàng chục giây. Ba property
   `indexed_rows`/`train_sha256`/`cache_hit` đều vậy. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter.train_sha256` (property, `:109-112`)
1. in/out: `() -> str`. {code}
2. side effect: `_ensure_index()`. {code}
3-4. như trên. {code}
5. config: không. {code}
6. ai gọi: script eval (ghi vào báo cáo để truy vết bộ train). {code}
7. invariant: trả `""` nếu index chưa dựng — nhưng `_ensure_index` chạy trước nên
   không xảy ra. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter.cache_hit` (property, `:114-117`)
1. in/out: `() -> bool`. {code}
2. side effect: `_ensure_index()`. {code}
3-4. như trên. {code}
5. config: không. {code}
6. ai gọi: script eval/test. {code}
7. invariant: chỉ có nghĩa **sau** lần dựng đầu tiên; gọi lại luôn trả cùng giá
   trị vì `_ensure_index` thoát sớm. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter.model_name` (property, `:119-121`)
1. in/out: `() -> str`. {code}
2. side effect: **không** gọi `_ensure_index` — khác 3 property trên. {code}
3. state: chỉ đọc. {code}
4. lỗi: không (`getattr` có default). {code}
5. config: không. {code}
6. ai gọi: `_cache_metadata:345`, các dòng log. {code}
7. invariant: fallback `type(self.embedder).__name__` — nghĩa là embedder giả
   trong test cho ra một `model_name` khác, nên cache của test không đụng cache
   thật. Hệ quả tốt, có vẻ tình cờ. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter.classify` (`semantic_router.py:123-125`)
1. in/out: `(text: str) -> RouteDecision`. {code}
2. side effect: qua `predict`. {code}
3. state: không. {code}
4. lỗi: từ `predict`. {code}
5. config: dùng ngưỡng của instance. {code}
6. ai gọi: `intake.py` — tầng 2 của ba tầng router. {code}
7. invariant: docstring nói "without any network dependency" — đúng, embedder là
   local `SentenceTransformer`. Đây là tầng router duy nhất chạy được khi Ollama
   chết mà vẫn dùng model. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter.predict` (`semantic_router.py:127-232`)
1. in/out: `(text, *, k=None, oos_distance_threshold=None, ambiguity_margin=None)
   -> SemanticPrediction`. {code}
2. side effect: `_ensure_index`; một lời gọi `embed_query` (có cache đĩa). {code}
3. state: không sửa. {code}
4. lỗi: 5 nhánh `ValueError` — text rỗng, lệch chiều embedding, norm không hữu
   hạn, similarity không hữu hạn, index rỗng. Đây là hàm kiểm đầu vào chặt nhất
   trong `src/`. {code}
5. config: ba tham số override cho hiệu chuẩn; mặc định lấy của instance. {code}
6. ai gọi: `classify:125`; script hiệu chuẩn. {code}
7. invariant: dùng `argpartition` O(n) rồi mới sort k phần tử — comment `:168`
   nói đúng lý do. Bỏ phiếu bằng `max(0, sim)**2 + 1e-9`: bình phương để láng
   giềng gần có trọng số lớn hơn (comment `:193-194`), `+1e-9` để nhãn có mặt
   không bao giờ nhận 0 tuyệt đối. `vote_scores` được dựng cho **cả 3** nhãn kể
   cả nhãn không có láng giềng nào, nên `ranked[1]` luôn tồn tại và
   `vote_margin` luôn tính được — không có `IndexError`. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter._ensure_index` (`semantic_router.py:234-275`)
1. in/out: `() -> None`. {code}
2. side effect: đọc train, có thể encode toàn tập và ghi cache; ghi 1 dòng log. {code}
3. state: đặt `_embeddings`, `_labels`, `_texts`, `_train_sha256`, `_cache_hit`. {code}
4. lỗi: từ `_read_train_rows` / `_validated_normalized_embeddings`. {code}
5. config: `train_path`, `cache_path`. {code}
6. ai gọi: `__init__`, 3 property, `predict`. {code}
7. **invariant: `self._texts` được gán ở `:274` và không đọc ở đâu.** Grep
   `_texts` trong file: chỉ `:97` (khởi tạo) và `:274` (gán). Trường chết — cùng
   hạng với `BM25Index.texts` (`src.rag` Q-05), nhưng ở đây chỉ tốn RAM chứ
   không tốn dung lượng file vì cache không lưu texts. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter._read_train_rows` (`semantic_router.py:277-307`)
1. in/out: `() -> tuple[list[dict[str,str]], str]`. {code}
2. side effect: đọc file. {code}
3. state: không. {code}
4. lỗi: `FileNotFoundError`; `ValueError` với **số dòng** cho 3 trường hợp
   (thừa/thiếu khoá, text rỗng, nhãn không hợp lệ). Thông điệp lỗi có
   `path:line` — dễ sửa dữ liệu nhất trong repo. {code}
5. config: `train_path`. {code}
6. ai gọi: `_ensure_index:237`. {code}
7. invariant: `set(row) != {"text","intent"}` — từ chối **cả** khoá thừa. Một
   file train có thêm cột `source` sẽ bị chặn thay vì âm thầm bỏ qua. Nghiêm ngặt
   hơn mọi loader khác trong repo. Nhược: thông điệp lỗi ở `:292` viết
   `"{'text','intent'}"` trong f-string nên hai dấu ngoặc nhọn được in ra như
   literal — may mà nó nằm ngoài phần `f"..."` (dòng thứ hai là chuỗi thường
   nối vào), nên in đúng. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter._load_cache` (`semantic_router.py:309-338`)
1. in/out: `(train_sha: str) -> tuple[np.ndarray, np.ndarray] | None`. {code}
2. side effect: đọc file `.npz`. {code}
3. state: không. {code}
4. lỗi: **bọc toàn bộ trong `try/except Exception`** → log warning và trả `None`
   (dựng lại). Cache hỏng không làm chết startup. {code}
5. config: `cache_path`. {code}
6. ai gọi: `_ensure_index:238`. {code}
7. **invariant: `np.load(..., allow_pickle=False)`** — chặn thực thi mã tuỳ ý từ
   file cache. Đây là điểm khác biệt lớn so với `BM25Index.load`, vốn
   `pickle.load` (xem `src.rag`). Cùng một repo, hai chuẩn an toàn cho cùng loại
   artifact. Ngoài ra 3 lớp kiểm sau khi nạp: metadata khớp, shape khớp, nhãn hợp
   lệ. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter._cache_metadata` (`semantic_router.py:340-347`)
1. in/out: `(train_sha: str, rows: int | None = None) -> dict`. {code}
2. side effect: gọi `_count_train_rows()` khi `rows` là None — **đọc lại file
   train lần thứ hai**. {code}
3. state: không. {code}
4. lỗi: từ `_count_train_rows`. {code}
5. config: `train_path`, `model_name`, `_CACHE_SCHEMA_VERSION`. {code}
6. ai gọi: `_load_cache:319` (không truyền `rows` → đọc lại file),
   `_save_cache:364` (truyền `rows` → không đọc lại). {code}
7. invariant: `str(self.train_path.resolve())` nằm trong metadata → **di chuyển
   repo sang thư mục khác làm cache mất hiệu lực** dù nội dung train không đổi.
   Với máy dev thì phiền, với build reproducible thì là tính năng. Không được ghi
   ở đâu. Xem Q-08. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter._count_train_rows` (`semantic_router.py:349-354`)
1. in/out: `() -> int`. {code}
2. side effect: đọc toàn bộ file train. {code}
3. state: không. {code}
4. lỗi: `OSError`/`UnicodeDecodeError`. {code}
5. config: `train_path`. {code}
6. ai gọi: `_cache_metadata:346` — tức mỗi lần kiểm cache. {code}
7. invariant: đếm `if line.strip()`, khớp đúng điều kiện bỏ dòng của
   `_read_train_rows:286` — hai phép đếm nhất quán. Nhưng file vừa được
   `_read_train_rows` đọc xong ở `_ensure_index:237`; đọc lại là thừa. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter._save_cache` (`semantic_router.py:356-375`)
1. in/out: keyword-only `(embeddings, labels, train_sha) -> None`. {code}
2. side effect: tạo thư mục, ghi `.tmp`, `replace()`. {code}
3. state: không. {code}
4. lỗi: `OSError`. {code}
5. config: `cache_path`. {code}
6. ai gọi: `_ensure_index:259`. {code}
7. **invariant: ghi ra file tạm rồi `Path.replace()` — thay thế nguyên tử.**
   Tiến trình chết giữa chừng để lại `.tmp` chứ không để lại cache hỏng. Đây là
   chuẩn mà `BM25Index.save` (`src.rag`) **không** theo. Hai artifact cùng vai
   trò, hai mức độ cẩn thận. {code}
8. deprecated: không. {code}

### [x] `SemanticRouter._validated_normalized_embeddings` (staticmethod, `:377-393`)
1. in/out: `(embeddings, *, expected_rows) -> np.ndarray`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: 3 nhánh `ValueError` — sai shape, rỗng/không hữu hạn, vector norm 0. {code}
5. config: không. {code}
6. ai gọi: `_ensure_index:255` (đường dựng mới), `_load_cache:322` (đường nạp cache). {code}
7. invariant: chuẩn hoá **lại** ngay cả khi `Embedder.embed_passages` đã
   `normalize_embeddings=True` — chuẩn hoá hai lần là idempotent nên vô hại, và
   nó bảo vệ đường nạp cache khỏi file được sinh bởi phiên bản cũ. Trả
   `ascontiguousarray` để phép nhân ma trận ở `predict:152` chạy trên bộ nhớ
   liền mạch. Chi tiết hiệu năng hiếm thấy trong repo. {code}
8. deprecated: không. {code}

---

## `intent_router.py`

### [x] docstring `intent_router.py:1-18`
1. in/out: 18 dòng lời khai — dài nhất trong `src/`. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: module có **hai vai**, và tên cũ `chat/fallback` chỉ mô tả
   đúng một; `compute_route_flags` chạy 100% request; bỏ nó thì cảnh báo khẩn cấp
   (`chat/_safety`) và guidance (`prompt_builder`) "chết im lặng";
   `route_intent`/`_rule_decision` là tier 3 thật, chỉ chạy khi Ollama chết.
   **Đối chiếu code:** `LLMRouter.classify:75-80` và
   `SemanticPrediction.route_decision:46-52` đều dựng `RouteDecision` **không**
   truyền `route_flags` → mặc định `[]`. Lời khai được code xác nhận. {code+doc}
8. deprecated: không. {doc}

### [x] `PrimaryIntent` (`intent_router.py:31`)
1. in/out: `Literal["advise","knowledge","clarify","reject"]`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `RouteDecision`, `llm_router._coerce_intent`, `semantic_router`. {code}
7. invariant: nguồn sự thật cho 4 intent, nhưng `llm_router._ALLOWED_INTENTS` là
   bản sao thủ công thay vì `get_args(PrimaryIntent)`. Xem khối đó. {code}
8. deprecated: không. {code}

### [x] `IntentSource` (`intent_router.py:32`)
1. in/out: `Literal["rule","semantic","llm"]`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: trường `source` của `RouteDecision`. {code}
7. invariant: ba giá trị khớp đúng ba tầng router mà docstring `__init__.py` mô
   tả. Ba tầng ↔ ba nguồn ↔ ba giá trị. Nhất quán. {code}
8. deprecated: không. {code}

### [x] `RouteDecision` (`intent_router.py:35-44`)
1. in/out: dataclass 8 trường — `primary_intent`, `confidence`, `source`
   (mặc định `"rule"`), `turn_type` (`"answer"`), `route_flags` (list rỗng),
   `detected_language` (`"unknown"`), `reason_code` (`"rule_default"`),
   `ambiguity_reason` (None). {code}
2. side effect: không. {code}
3. state: mutable — `_rule_decision` **append vào `route_flags`** của list được
   truyền vào (`:~440`, `:~590`). {code}
4. lỗi: không validate; `primary_intent` khai Literal nhưng dataclass không ép. {code}
5. config: không. {code}
6. ai gọi: cả ba tầng router dựng nó; `intake.py` và `orchestrator.py` đọc. {code}
7. invariant: 6/8 trường có default, nên `RouteDecision(primary_intent=..., confidence=...)`
   là lời gọi hợp lệ — và đó chính là cách hai tầng LLM/semantic gọi, để lại
   `route_flags` rỗng. Default rộng rãi là nguyên nhân trực tiếp của việc
   `compute_route_flags` phải chạy riêng. {code}
8. deprecated: không. {code}

### [x] `RouteDecision.metadata` (`intent_router.py:46-58`)
1. in/out: `() -> dict` 7 khoá (8 nếu có `ambiguity_reason`). {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `intake.py` (nhét vào `route_decision`/`route_metadata`),
   `orchestrator.py`, và cuối cùng vào `ConversationTurn.metadata`. {code}
7. **invariant tinh tế:** `"turn_type": self.turn_type if self.turn_type != "answer"
   else self.primary_intent` — khi `turn_type` còn mặc định, metadata **báo cáo
   intent thay cho turn_type**. Nghĩa là log/audit không phân biệt được "turn_type
   thật sự là advise" với "turn_type chưa từng được đặt". Chỉ một nhánh
   (`crisis_signal`, `:~575`) đặt `turn_type="safety_clarify"`. Xem Q-09. {code}
8. deprecated: không. {code}

### [x] `_FOLLOWUP_SHORT_TERMS` … `_MULTI_CONDITION_TERMS` — **18 bảng term**
(`_FOLLOWUP_SHORT_TERMS`, `_QUESTION_TERMS`, `_KNOWLEDGE_RANKING_TERMS`,
`_PRODUCT_QUERY_TERMS`, `_FOOD_KNOWLEDGE_TERMS`, `_PERSONAL_TERMS`, `_CASE_TERMS`,
`_ADVICE_QUESTION_TERMS`, `_URGENT_EVALUATION_TERMS`, `_EMOTIONAL_TERMS`,
`_CRISIS_TERMS`, `_PROGRESS_TERMS`, `_SAFETY_PRODUCT_TERMS`, `_URGENCY_TERMS`,
`_URGENT_CLINICAL_FLAGS`, `_MULTI_CONDITION_TERMS`, `_FOOD_EAT_RE`,
`_STOP_REPEAT_CHARS_RE`)

> Mười tám khối này dùng **nén có khai báo §1** cho mục 2/3/4/7. Dưới đây là mục
> 1/5/6/8 của từng bảng, cộng nhận xét riêng nơi bảng lệch khỏi phát biểu chung.

1. in/out: đều là `tuple[str, ...]` chuỗi thường, trừ `_URGENT_CLINICAL_FLAGS`
   (`frozenset` 5 mã cờ lâm sàng) và hai regex đã compile (`_FOOD_EAT_RE`,
   `_STOP_REPEAT_CHARS_RE`). {code}
5. config: **tất cả là hằng cứng**, không bảng nào có field `Settings` hay file
   YAML. Sửa một quy tắc định tuyến = sửa code + deploy. {code}
6. ai gọi: `_QUESTION_TERMS` 4 lần, `_CASE_TERMS`/`_PERSONAL_TERMS` 3 lần mỗi bảng,
   còn lại 1–2 lần, tất cả trong `compute_route_flags` và `_rule_decision`.
   `_URGENT_CLINICAL_FLAGS` chỉ dùng ở `_rule_decision:~500`. {code}
8. deprecated: không bảng nào đánh dấu deprecated. `_CRISIS_TERMS:~245` có
   comment `ponytail:` ghi lại việc **đã xoá** `"tu tu"` không dấu vì nó vừa là
   "tự tử" vừa là "từ từ" — lời khai này kiểm được: bảng hiện tại đúng là không
   còn chuỗi đó. {code+comment}

**Nhận xét riêng, lệch khỏi phát biểu chung:**
- `_SAFETY_PRODUCT_TERMS` chứa chuỗi `"+"`. Nó được dùng qua
  `_contains_product_safety_term`, hàm này khớp `"+"` như **chuỗi con thường**,
  nên **mọi** tin nhắn có dấu cộng đều nhận cờ `product_safety_check`. Xem Q-10.
- `_URGENCY_TERMS` chứa ba biến thể của một từ: `"sốt "`, `" sốt"`, `" sot "`.
  Bản không dấu chỉ khớp khi có khoảng trắng **cả hai bên**, nên "sot" đầu câu
  hoặc cuối câu trượt. Ba dòng cho một khái niệm, và vẫn sót.
- `_EMOTIONAL_TERMS:~238` có comment giải thích vì sao phải dùng cụm đầy đủ
  (`"chan"` đụng `"chẳng"`, `"hoang"` đụng `"khoảng"`) — lời khai đúng và bảng
  hiện tại tuân thủ nó.
- `_FOOD_EAT_RE` dùng `(?<!\w)…(?!\w)` (ranh giới từ thật), trong khi
  `_FOOD_KNOWLEDGE_TERMS` chứa `"ăn"` khớp chuỗi con. Hai cơ chế cho cùng một từ
  trong cùng một biểu thức điều kiện (`is_food_query`, `:~465`).

### [x] `normalize_for_repeat` (`intent_router.py:~300`)
1. in/out: `(text: str) -> str`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `is_repeated_question` (2 lần mỗi lượt lặp). {code}
7. invariant: bỏ mọi ký tự không phải `\w\s%+`, gộp khoảng trắng. Giữ `%` và `+`
   là có ý (nồng độ, "BHA+AHA"). Cờ `re.UNICODE` là thừa — trong Python 3, `\w`
   trên `str` đã là Unicode mặc định. {code}
8. deprecated: không. {code}

### [x] `is_repeated_question` (`intent_router.py:~306`)
1. in/out: `(message, history, recent_user_turns=6) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `recent_user_turns=6` — trùng số với `HISTORY_WINDOW_TURNS`, nhưng là
   hằng riêng, không import. {code}
6. ai gọi: `compute_route_flags:~400`. {code}
7. invariant: so **bằng chuỗi tuyệt đối** sau chuẩn hoá — "mụn bọc là gì" và
   "mụn bọc là gì ạ" là hai câu khác nhau. Cờ `repeated_question` vì thế chỉ bắt
   được người dùng gửi lại y hệt (copy-paste hoặc bấm gửi hai lần), không bắt
   được người hỏi lại cùng ý. {code}
8. deprecated: không. {code}

### [x] `_terms_regex` (`intent_router.py:~316`, `@lru_cache(maxsize=128)`)
1. in/out: `(terms: tuple[str, ...]) -> re.Pattern | None`. {code}
2. side effect: điền cache. {code}
3. state: cache toàn cục 128 entry. {code}
4. lỗi: `re.error` nếu `re.escape` cho ra pattern quá lớn — không xảy ra với các
   bảng hiện tại. {code}
5. config: `maxsize=128`. {code}
6. ai gọi: `_contains_any` — cửa duy nhất. {code}
7. invariant: sắp xếp term theo **độ dài giảm dần** trước khi `|`-join, để
   alternation ưu tiên cụm dài (`"nguyên nhân chính"` thắng `"nguyên nhân"`). Với
   `_contains_any` chỉ trả bool thì thứ tự không đổi kết quả, nhưng nó đúng nếu
   sau này có ai đọc `.group()`. `maxsize=128` so với ~20 bảng cố định + 1 bảng
   dựng-tại-chỗ (`_COMPARISON_MARKERS`) → cache không bao giờ bị đuổi. {code}
8. deprecated: không. {code}

### [x] `_contains_any` (`intent_router.py:~326`)
1. in/out: `(text: str, terms: tuple[str, ...]) -> bool`. {code}
2. side effect: qua `_terms_regex`. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: ~25 lần trong `compute_route_flags` và `_rule_decision`. Hàm được gọi
   nhiều nhất của module. {code}
7. invariant: `text.lower()` **bên trong** hàm, nhưng mọi caller đã truyền
   `lowered`. Hạ chữ hai lần trên mỗi lời gọi — 25 lần mỗi request. Vô hại về
   ngữ nghĩa, lãng phí về chi phí. Quan trọng hơn: hàm khớp **chuỗi con**, không
   ranh giới từ — mọi bảng term phải tự bảo vệ bằng cách viết cụm đủ dài, và
   comment ở `_EMOTIONAL_TERMS`/`_PERSONAL_TERMS` cho thấy điều đó đã cắn ít nhất
   hai lần. {code+comment}
8. deprecated: không. Đây là hàm được `_terms.py` cũ giữ và đã gộp vào file này. {code}

### [x] `_contains_product_safety_term` (`intent_router.py:~332`)
1. in/out: `(text: str) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_SAFETY_PRODUCT_TERMS`. {code}
6. ai gọi: `compute_route_flags:~407`. {code}
7. **invariant hỏng:** docstring nói "Match short ingredient aliases as tokens,
   never as substrings" — đúng cho `{"aha","bha","bpo"}`, nhưng **mọi term khác**
   dùng `term in text` thuần, gồm cả `"+"`. Lời khai đúng một nửa và nửa còn lại
   là nguồn dương tính giả. Xem Q-10. {code+doc}
8. deprecated: không. {code}

### [x] `_clinical_has_case_signal` (`intent_router.py:~342`)
1. in/out: `(clinical: AcneClinicalInput | None) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `_rule_decision:~495`. {code}
7. invariant: lọc `lesion_types` bỏ `"other"` (`:~345`) — quan trọng, vì
   `rule_normalizer._LESION_TERMS` có nhãn bắt-tất `"other"` khớp với mọi "bị
   mụn". Không lọc thì mọi câu nhắc mụn đều thành case cá nhân. `mild` chỉ tính
   là tín hiệu khi **kèm** lesion hoặc phân bố — bậc thang có chủ ý. {code}
8. deprecated: không. {code}

### [x] `_has_any_clinical_fact` (`intent_router.py:~361`)
1. in/out: `(user: UserInput) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `_rule_decision:~600`. {code}
7. **invariant:** danh sách `any((...))` gồm `clinical.inflammation_level` —
   trường này **luôn là chuỗi khác rỗng** sau `fold_history_facts` (xem
   `src.chat.session` Q-10, `"unknown"` luôn truthy). Comment ngay tại call site
   (`:~618`) đã biết: "_has_any_clinical_fact(user) sẽ luôn True sau fold → mọi
   thứ thành advise". Code vá bằng cách **không dùng** hàm này ở nhánh cuối, chỉ
   dùng ở một nhánh có kèm `is_advice_question`. Lỗi được biết, được né, nhưng
   hàm vẫn giữ nguyên khiếm khuyết. Xem Q-11. {code+comment}
8. deprecated: không. {code}

### [x] `compute_route_flags` (`intent_router.py:~383`)
1. in/out: `(message, user=None, history=None) -> list[str]`; 7 cờ có thể có. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không — mọi truy cập `user` đều gác None. {code}
5. config: 6 bảng term. {code}
6. ai gọi: `intake.py:~570` (mọi request, mọi router) và `_rule_decision:~430`. {code}
7. invariant: đây là hàm mà docstring module gọi là "vai thứ nhất". Nó **không
   gọi model**, chỉ khớp mẫu — nên nó vẫn chạy khi Ollama chết. Thứ tự cờ trong
   list là thứ tự kiểm, không có ý nghĩa ưu tiên. Cờ `urgency_red_flag` là cờ
   duy nhất kết hợp text **và** dữ liệu có cấu trúc (`red_flags_input`). {code}
8. deprecated: không. {code}

### [x] `_rule_decision` (`intent_router.py:~416-628`)
1. in/out: `(message, user, history, current_clinical=None) -> RouteDecision`;
   213 dòng, 11 nhánh trả về. {code}
2. side effect: không. {code}
3. state: **append vào `flags`** — list cục bộ, nhưng cùng list được nhét vào
   `RouteDecision.route_flags` nên người nhận giữ tham chiếu. {code}
4. lỗi: không raise. {code}
5. config: mọi ngưỡng là số cứng trong thân hàm (0.92, 0.90, 0.86, 0.84, 0.82,
   0.80, 0.75, 0.72, 0.70, 0.68, 0.58). Không giá trị nào ở `Settings`. {code}
6. ai gọi: `route_intent` — cửa duy nhất. {code}
7. **invariant: 11 nhánh, thứ tự quyết định tất cả.** Thứ tự thực tế:
   short_followup → urgent_personal_case → knowledge_ranking → product/food/
   mechanism → general_comparison → crisis_signal → personal_acne_case →
   contextual_personal_advice → question_without_case_signal → low_signal_default.
   Đáng chú ý: `crisis_signal` đứng **sau** bốn nhánh knowledge. Một câu vừa có
   tín hiệu khủng hoảng vừa có `"là gì"` sẽ được trả lời như câu hỏi kiến thức và
   **không** vào nhánh `safety_clarify`. Xem Q-13. Comment `:~604` giải thích
   đúng vì sao nhánh cuối chỉ dùng `has_case_signal` chứ không
   `_has_any_clinical_fact`. {code+comment}
8. deprecated: `_COMPARISON_MARKERS` được định nghĩa **trong thân hàm**
   (`:~549`), khác 18 bảng còn lại ở cấp module — dựng lại tuple mỗi lời gọi.
   `_terms_regex` vẫn cache trúng vì tuple bằng nhau, nên chỉ tốn phần dựng tuple. {code}

### [x] `_decision` (hàm lồng trong `_rule_decision`, `:~424-433`)
1. in/out: `(primary_intent, confidence, **kwargs) -> RouteDecision`. {code}
2. side effect: không. {code}
3. state: closure không bắt biến nào. {code}
4. lỗi: `TypeError` nếu `kwargs` có khoá không phải trường của `RouteDecision`. {code}
5. config: không. {code}
6. ai gọi: 10 nhánh trả về của `_rule_decision`. {code}
7. invariant: hàm này **không thêm gì** so với gọi thẳng `RouteDecision(...)` —
   nó chỉ chuyển hai tham số đầu thành positional. Một lớp bọc không mang giá
   trị; xoá được mà không đổi hành vi. {code}
8. deprecated: không đánh dấu, nhưng thừa. {code}

### [x] `route_intent` (`intent_router.py:~632-669`)
1. in/out: `(message, user, history, settings=None, classifier=None,
   current_clinical=None) -> RouteDecision`. {code}
2. **side effect: dựng một `Settings()` MỚI mỗi lần gọi** (`:~651`), tức đọc lại
   `.env` từ đĩa và chạy lại 6 validator — trên đường nóng của tầng fallback. {code}
3. state: không. {code}
4. lỗi: `try/except Exception` quanh việc dựng Settings → mặc định 0.55. {code}
5. **config: `route_min_confidence`, lấy sai đường.** Nó **không** dùng singleton
   `acne_llm.config.settings`, và **không** dùng tham số `settings` được truyền
   vào. Xem Q-14. {code}
6. ai gọi: `intake.py` — tầng 3. {code}
7. **invariant hỏng — nhánh chết:** luật hạ cấp chỉ kích hoạt khi
   `decision.confidence < route_min_confidence`. Confidence thấp nhất mà
   `_rule_decision` **có thể** trả là **0.58** (nhánh `low_signal_default`), còn
   `route_min_confidence` mặc định là **0.55**. 0.58 > 0.55 ở mọi nhánh, nên
   nhánh `route_confidence_below_threshold` **không bao giờ chạy** với cấu hình
   hiện tại. Liệt kê đủ 11 giá trị confidence để kiểm: 0.92, 0.90, 0.86, 0.84,
   0.82, 0.80, 0.75, 0.72, 0.70, 0.68, 0.58 — không giá trị nào < 0.55. Xem Q-15. {code}
8. deprecated: docstring `:~639-643` khai `classifier` "được giữ lại cho tương
   thích ngược nhưng KHÔNG còn được dùng". Đúng — grep trong thân hàm không có.
   Nhưng docstring **không** nói `settings` cũng vô dụng, mà nó vô dụng theo cách
   nguy hiểm hơn: hàm tự dựng Settings riêng thay vì dùng cái được đưa. {code+doc}

---

## `rule_extractor.py`

### [x] docstring `rule_extractor.py:1-18`
1. in/out: 18 dòng, gồm bảng confidence 4 mức. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "LEGACY: live fallback when `EXTRACTOR_MODE=rule` or the
   LLM extractor fails"; "KHÔNG sửa normalizer.py"; "Thuần rule + fuzzy, KHÔNG
   gọi LLM". **Đối chiếu:** import chỉ có `re`, `schemas.extraction`,
   `utils.fuzzy_match`, `rule_normalizer`, `preprocess` — không LLM. Đúng. Nhưng
   vế `EXTRACTOR_MODE=rule` **không đạt được**: `di.py:162-163` ép
   `settings.extractor_mode = "llm"` ở chế độ unified. Đường sống duy nhất còn
   lại là "LLM extractor fails". Xem Q-16. {code+doc}
8. deprecated: tự khai LEGACY. {doc}

### [x] `_FUZZY_MIN_LEN` (`rule_extractor.py:41`)
1. in/out: `int = 7`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `:43,46,74` (lọc 3 lexicon). {code}
7. invariant: comment `:38-40` nêu lý do đo được: token ngắn (spf, toner, kem,
   zinc, peel, bha) làm fuzzy khớp bừa với từ tiếng Việt, "nguyên nhân products
   precision thấp". Ngưỡng 7 loại hết nhóm đó. Cộng hưởng với `_LENGTH_GATE=0.6`
   trong `fuzzy_match` (xem `src.utils`): hai cổng độ dài nối tiếp. {code+comment}
8. deprecated: không. {code}

### [x] `PRODUCT_CANONICALS` (`rule_extractor.py:42-44`)
1. in/out: tuple chuỗi thường, lọc từ `nz._PRODUCT_TERMS` theo `len >= 7`. {code}
2. side effect: dựng lúc import. {code}
3. state: hằng module. {code}
4. lỗi: không. {code}
5. config: `_FUZZY_MIN_LEN`. {code}
6. ai gọi: `extract_with_confidence:~301`. {code}
7. invariant: `dict.fromkeys` giữ thứ tự và bỏ trùng; là **tên công khai** (không
   `_`) nhưng grep ngoài file = 0 caller. Công khai không lý do. {code}
8. deprecated: không. {code}

### [x] `MEDICATION_CANONICALS` (`rule_extractor.py:45-47`)
1. in/out: như trên, từ `nz._MEDICATION_TERMS`. {code}
2-5. như trên. {code}
6. ai gọi: `extract_with_confidence:~310`. {code}
7. invariant: cùng nhận xét; cũng công khai và cũng 0 caller ngoài. {code}
8. deprecated: không. {code}

### [x] `_ALLERGY_ALIAS_TO_LABEL` (`rule_extractor.py:48-73`)
1. in/out: dict `alias không dấu → nhãn schema`. {code}
2. side effect: **vòng `for` ở cấp module** (`:49`) chạy lúc import và để lại
   `_label`, `_pattern`, `_aliases`, `_alias`, `_alias_key` trong namespace module. {code}
3. state: hằng module (sau khi vòng lặp xong). {code}
4. lỗi: không. {code}
5. config: `nz._ALLERGY_TERMS`, `_FUZZY_MIN_LEN`. {code}
6. ai gọi: `ALLERGY_CANONICALS:74`, `extract_with_confidence:~318`. {code}
7. invariant: bỏ nhãn `"unknown"` (`:51-52`) để catch-all không vào tầng fuzzy —
   đúng, vì fuzzy với `"unknown"` sẽ khớp bừa. Alias được thêm tay cho 5 nhãn;
   14 nhãn còn lại chỉ có chính tên nhãn và biến thể `_`→khoảng trắng, nên
   `"doxycycline"` có alias còn `"clindamycin"` viết sai chính tả vẫn bắt được
   nhờ fuzzy, nhưng `"kháng sinh uống"` thì không map về nhãn nào. {code}
8. deprecated: không. {code}

### [x] `ALLERGY_CANONICALS` (`rule_extractor.py:74`)
1. in/out: `tuple(_ALLERGY_ALIAS_TO_LABEL)` — tuple các **khoá** (alias). {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: **0 chỗ.** `extract_with_confidence` truyền thẳng
   `_ALLERGY_ALIAS_TO_LABEL` cho `_list_vocab_aliases`, hàm này tự lấy
   `tuple(alias_to_label)` ở `:~191`. Biến này là bản sao thừa. {code}
7. invariant: tên công khai, 0 caller. {code}
8. deprecated: 0 caller. Xoá được. {code}

### [x] `_VOCAB_FUZZY_REVIEW` (`rule_extractor.py:78`)
1. in/out: `float = 0.82`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `extract_with_confidence:~299` (`max(fuzzy_review, 0.82)`). {code}
7. **invariant — hằng số không có tác dụng:** comment `:76-77` nói đây là "review
   floor RIÊNG cho field từ vựng: cao hơn ngưỡng chung để fuzzy CHỈ bắt sai chính
   tả thật". Nhưng `find_in_text` (`utils/fuzzy_match.py:98-105`) **vứt bỏ** mọi
   hit dưới `accept` ở dòng return, nên tham số `review` không ảnh hưởng kết quả
   (xem `src.utils` Q-02). Thứ thật sự lọc là `accept=0.86`. Hằng số này được
   tinh chỉnh và ghi chú cẩn thận cho một cổng không tồn tại. Xem Q-17. {code+comment}
8. deprecated: không đánh dấu, nhưng vô hiệu. {code}

### [x] `_NEGATION_RE` (`rule_extractor.py:81`)
1. in/out: regex `\b(?:không|khong|ko|chẳng|chang|chưa|chua)\b`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: **0 chỗ.** Grep `_NEGATION_RE` trong file: chỉ dòng định nghĩa.
   `_context_adjust` chỉ dùng `_QUESTION_RE` và `_PRONOUN_RE`. {code}
7. invariant: comment `:80` nói cả ba regex là "điều chỉnh ngữ cảnh (cộng vào
   confidence base)", nhưng regex phủ định không tham gia. Nghĩa là câu phủ định
   **không** bị trừ confidence. Xem Q-18. {code+comment}
8. deprecated: 0 caller. {code}

### [x] `_QUESTION_RE` (`rule_extractor.py:82`)
1. in/out: alias tới `nz._SKIN_TYPE_QUESTION_RE`. {code}
2-4. không. {code}
5. config: không. {code}
6. ai gọi: `_context_adjust:~110`. {code}
7. invariant: comment `:82` nói "tái dùng marker câu hỏi/so sánh đã có" — nhưng
   regex đó được viết cho **riêng skin_type** (`rule_normalizer:1113-1115` nói rõ
   ví dụ "da dầu có dễ bị mụn hơn da khô không"). Ở đây nó điều chỉnh confidence
   của **mọi** field. Tái dùng một bộ lọc chuyên biệt làm bộ lọc tổng quát. {code+comment}
8. deprecated: không. {code}

### [x] `_PRONOUN_RE` (`rule_extractor.py:83`)
1. in/out: regex 8 đại từ ngôi 1. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_context_adjust:~112`. {code}
7. invariant: chứa `em`, `con`, `cháu` với `\b` — `intent_router._PERSONAL_TERMS`
   có comment nói rõ **không** dùng `"em"`/`"con"` đứng một mình vì trùng từ
   thông thường ("em ơi", "con đường"). Hai file, hai kết luận trái ngược cho
   cùng một quan sát ngôn ngữ. Ở đây hậu quả nhẹ hơn (chỉ +0.05 confidence). {code}
8. deprecated: không. {code}

### [x] `_VITAMIN_LETTER_RE` (`rule_extractor.py:86`)
1. in/out: regex `vitamin\s+([a-z])\b`. {code}
2-4. không. {code}
5. config: hằng cứng. {code}
6. ai gọi: `_vitamin_letter_ok`. {code}
7. invariant: chỉ bắt **một** chữ cái sau "vitamin", nên "vitamin b5" không khớp
   `fullmatch` ở `:~97` → `_vitamin_letter_ok` trả True (cho qua). Đúng ý: cổng
   chỉ chặn nhóm một-chữ-cái. {code}
8. deprecated: không. {code}

### [x] `_vitamin_letter_ok` (`rule_extractor.py:89-99`)
1. in/out: `(canonical: str, text_no_accent: str) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `extract_with_confidence:~305` (trong `fuzzy_context_filter` của products). {code}
7. invariant: chặn đúng lỗi mà fuzzy dễ mắc — "vitamin k" và "vitamin c" chỉ khác
   một ký tự nên `fuzz.ratio` ≈ 0.90, thừa sức vượt `accept=0.86`. Đây là bản vá
   nhắm đúng cơ chế. Chỉ áp cho **products**, không áp cho medications. {code}
8. deprecated: không. {code}

### [x] `_context_adjust` (`rule_extractor.py:102-114`)
1. in/out: `(text: str, span_hint: str = "") -> float`; trả −0.10, 0, +0.05 hoặc −0.05. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: hai số cứng 0.10 và 0.05. {code}
6. ai gọi: `_scalar:~119`, `_list_from_pattern:~122`. {code}
7. **invariant: tham số `span_hint` được khai và không dùng trong thân hàm.**
   Tên gợi ý ý định ban đầu là điều chỉnh theo ngữ cảnh **quanh vị trí khớp**;
   thực tế hàm chỉ nhìn **toàn bộ text**. Nghĩa là một câu dài có một cụm hỏi ở
   cuối sẽ trừ điểm cho mọi field trích ở đầu câu. {code}
8. deprecated: tham số chết chưa đánh dấu. {code}

### [x] `_scalar` (`rule_extractor.py:117-122`)
1. in/out: `(value, text, *, fallback_methods=()) -> FieldResult`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `evidence=text[:60]`. {code}
6. ai gọi: `extract_with_confidence` cho `skin_type` và `sex`. {code}
7. **invariant: tham số `fallback_methods` khai keyword-only và không dùng.**
   Hai tham số chết trong hai hàm liền nhau. {code}
8. deprecated: tham số chết. {code}

### [x] `_list_from_pattern` (`rule_extractor.py:125-131`)
1. in/out: `(values: list[str], text: str) -> ListFieldResult`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: qua `_context_adjust`. {code}
6. ai gọi: 5 chỗ trong `extract_with_confidence` (lesion, distribution,
   treatment_goals, allergies-nhánh-không-ngữ-cảnh). {code}
7. invariant: **không** dedupe — nếu `values` có trùng thì `ListFieldResult` có
   trùng. Người gọi phải tự dedupe trước; `nz._merge_extracted` có làm. Phụ thuộc
   ngầm. {code}
8. deprecated: không. {code}

### [x] `_list_vocab` (`rule_extractor.py:134-172`)
1. in/out: `(pattern_values, text_no_accent, canonicals, *, accept, review,
   term_map=None, fuzzy_context_filter=None) -> ListFieldResult`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `accept`/`review` từ người gọi. {code}
6. ai gọi: products và medications. {code}
7. invariant: item khớp regex được thêm **trước**, và `seen` (khoá không dấu,
   thường) chặn fuzzy thêm lại — nên confidence pattern luôn thắng confidence
   fuzzy cho cùng chất. Đúng ý docstring. `fuzzy_context_filter` chỉ áp cho hit
   **fuzzy**, không áp cho hit pattern — nghĩa là regex đã tự lo ngữ cảnh
   (`_has_product_use_context`), fuzzy thì phải lo riêng. Bất đối xứng có chủ ý. {code}
8. deprecated: không. {code}

### [x] `_list_vocab_aliases` (`rule_extractor.py:175-198`)
1. in/out: như `_list_vocab` nhưng ánh xạ alias → nhãn schema. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `accept`/`review`. {code}
6. ai gọi: allergies, chỉ khi `_has_allergy_context` True. {code}
7. invariant: **không** có `fuzzy_context_filter` — allergies dựa hoàn toàn vào
   cổng `_has_allergy_context` ở ngoài. Nghĩa là một khi câu có động từ dị ứng,
   **mọi** chất fuzzy-khớp trong câu đều thành dị ứng, kể cả chất đứng ở mệnh đề
   khác ("em dị ứng BHA nhưng dùng niacinamide ổn"). {code}
8. deprecated: không. {code}

### [x] `_bool_from_patterns` (`rule_extractor.py:201-214`)
1. in/out: `(clean_text, clean_text_no_accent, *, positive, negative) -> FieldResult[bool]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: confidence cứng 0.90 cho cả True lẫn False. {code}
6. ai gọi: `is_pregnant` và `is_breastfeeding`. {code}
7. **invariant nguy hiểm:** kiểm **negative trước**, nên "không mang thai" → giá
   trị `False` với confidence 0.90. Không có kiểm phạm vi phủ định, không kiểm
   chủ ngữ. `chat/session/view.py:68` xếp `is_pregnant` vào `_UNGATED_FIELDS`
   (ngưỡng 0.0), nên `False` đó **luôn** vào `confirmed_profile`. Đây đúng là
   hướng hỏng mà `chat/session/fold.py:~205-215` đã xoá 17 keyword để tránh — với
   lý do ghi rõ "rule không bao giờ được tự hạ xuống False". Cùng nguyên tắc,
   hai file, hai kết luận. Xem Q-19. {code+comment}
8. deprecated: không. {code}

### [x] `_has_allergy_context` (`rule_extractor.py:217-222`)
1. in/out: `(clean_text, clean_text_no_accent) -> bool`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `nz._ALLERGY_REACTION_VERBS`. {code}
6. ai gọi: `extract_with_confidence:~319`. {code}
7. invariant: chạy verb regex trên **cả hai** bản text rồi thêm `allerg(y|ic)`
   tiếng Anh. Cổng này quyết định allergies đi đường fuzzy hay đường
   pattern-thuần — một boolean đổi cả cơ chế trích. {code}
8. deprecated: không. {code}

### [x] `extract_with_confidence` (`rule_extractor.py:225-345`)
1. in/out: `(message, *, fuzzy_accept=0.86, fuzzy_review=0.72, clean_text=None,
   clean_text_no_accent=None) -> ExtractionConfidence` (17 field). {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: hai ngưỡng fuzzy mặc định 0.86/0.72, **không** ở `Settings`. {code}
6. ai gọi: `intake.py` (đường rule fallback). {code}
7. invariant: docstring nói "Gọi lại chính extractor cũ → đảm bảo giá trị nhất
   quán với `normalize_chat_message`". **Đối chiếu:** đúng cho 13 field đi qua
   `nz._merge_extracted`/`nz._first_extracted`. **Sai cho `is_pregnant` và
   `is_breastfeeding`**: ở đây dùng `_bool_from_patterns` trả 3 trạng thái
   (True/False/none), còn `normalize_chat_message:~1930` dùng
   `_contains_positive` trả **bool 2 trạng thái**. Hai đường cho hai kiểu dữ
   liệu khác nhau cho cùng một trường an toàn. Xem Q-19. {code+doc}
8. deprecated: không. {code}

### [x] `_inflammation_confidence` (`rule_extractor.py:348-388`)
1. in/out: `(value, text, lesion_types) -> FieldResult[str]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: 4 mức confidence cứng (0.90, 0.75, 0.60, 0.45). {code}
6. ai gọi: `extract_with_confidence:~291`. {code}
7. invariant: `mild` không có tín hiệu rõ **và** không có lesion viêm → 0.45,
   dưới `CONTEXT_FIELD_THRESHOLD=0.60`, tức bị chặn khỏi profile. Docstring nói
   đúng ý đó ("dưới ngưỡng → đẩy clarify"). Biến `has_inflammatory` được tính
   nhưng chỉ dùng ở **một** nhánh; nhánh `else` gộp mọi trường hợp còn lại vào
   0.60 mà không phân biệt. {code}
8. deprecated: không. {code}

### [x] `_scarring_confidence` (`rule_extractor.py:391-406`)
1. in/out: `(values, lesion_types, red_flags) -> ListFieldResult[str]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: 3 mức cứng (0.88, 0.78, 0.65). {code}
6. ai gọi: `extract_with_confidence:~336`. {code}
7. invariant: `values` chỉ có thể là `"sẹo mụn"` hoặc `"thâm sau mụn"` — đó là
   toàn bộ đầu ra của `nz._extract_scarring_signs_from_extracted`. Nên nhánh
   `elif "scarring_risk" in red_flags` và nhánh `else` (0.65) **không bao giờ
   chạy**: hai nhánh đầu đã phủ hết miền giá trị. Hai nhánh chết. {code}
8. deprecated: không. {code}

---

## `rule_normalizer.py`

### [x] docstring `rule_normalizer.py:1-13`
1. in/out: 13 dòng. {doc}
2-5. không. {doc}
6. ai gọi: không ai. {code}
7. invariant khai báo: "LEGACY: live fallback when `EXTRACTOR_MODE=rule` or the
   LLM extractor fails"; "The goal is not perfect medical NLP"; và tách hai khái
   niệm `raw_for_llm` (chỉ NFC + bỏ control char, giữ emphasis) vs `clean_text`
   (full preprocess, chỉ dùng nội bộ cho regex). **Đối chiếu code:**
   `normalize_chat_message:~1866` đúng — `description=raw_for_llm`,
   `clean_text` chỉ là biến cục bộ. Lời khai thứ ba được code tôn trọng đầy đủ.
   Vế `EXTRACTOR_MODE=rule` thì cùng vấn đề với `rule_extractor` (xem Q-16). {code+doc}
8. deprecated: tự khai LEGACY. {doc}

### [x] **13 bảng term** — `_SKIN_TYPES`, `_SEX_TERMS`, `_PRODUCT_TERMS`,
`_MEDICATION_TERMS`, `_DISTRIBUTION_TERMS`, `_LESION_TERMS`, `_HORMONAL_TERMS`,
`_ALLERGY_TERMS`, `_TREATMENT_GOAL_TERMS`, `_RED_FLAG_TERMS`,
`_PRODUCT_CANONICAL_MAP`, `_ACNE_RESOLVED_PATTERNS`, `_ACNE_PRESENT_PATTERNS`

> 13 khối, dùng **nén có khai báo §1** cho mục 2/3/4/7. Mục 1/5/6/8 dưới đây.

1. in/out: 10 bảng đầu là `list[tuple[nhãn, regex_chuỗi]]`;
   `_PRODUCT_CANONICAL_MAP` là `dict[str, str]` (raw tiếng Việt → nhãn tiếng Anh);
   hai bảng cuối là `tuple[str, ...]` regex thuần. Chiếm **~950 trong 1.975 dòng**
   của file, tức gần một nửa file là bảng dữ liệu. {code}
5. config: **tất cả hằng cứng.** Không bảng nào đọc từ YAML hay `Settings`, khác
   `guardrails/` vốn nạp `config/guardrails.yaml`. Thêm một hoạt chất = sửa code. {code}
6. ai gọi: mỗi bảng có **đúng một** hàm `_extract_*` tiêu thụ, trừ ba ngoại lệ:
   `_PRODUCT_TERMS` và `_MEDICATION_TERMS` còn được `rule_extractor.py:43,46` đọc
   để dựng lexicon fuzzy; `_ALLERGY_TERMS` được `rule_extractor.py:49` đọc để dựng
   `_ALLERGY_ALIAS_TO_LABEL`. Ba bảng đó vì vậy là **giao diện công khai trên thực
   tế** dù mang tiền tố `_`. {code}
8. deprecated: không bảng nào đánh dấu. {code}

**Nhận xét riêng:**
- `_LESION_TERMS` có nhãn bắt-tất `"other"`. Hệ quả đo được: `_extract_lesions("em
  bị mụn, muốn tư vấn cách trị")` trả `['other']`. Đây là lý do
  `intent_router._clinical_has_case_signal:~345` phải lọc `!= "other"`, và cũng là
  lý do mọi câu nhắc "mụn" đều tạo ra một `AcneClinicalInput` khác None.
- `_ALLERGY_TERMS` là bảng duy nhất **sinh** regex bằng hàm (`_allergy_pattern`)
  thay vì viết tay, nên nó có cả chiều xuôi lẫn ngược cho mọi chất — nhất quán
  hơn 12 bảng còn lại.
- `_PRODUCT_CANONICAL_MAP` ánh xạ về nhãn tiếng Anh (gold label-space), nhưng chỉ
  phủ một phần `_PRODUCT_TERMS`; term không có trong map đi thẳng vào kết quả ở
  dạng tiếng Việt (`_extract_products:~1323`). Đầu ra vì thế **trộn hai không gian
  nhãn** trong cùng một list.

### [x] **15 hằng phụ trợ** — `_ALLERGY_REACTION_VERBS`, `_ALLERGY_REACTION_AFTER`,
`_AcneCount`, `_SkinType`, `_Sex`, `_LesionType`, `_Distribution`, `_Inflammation`,
`_INFLAMMATION_ORDER`, `_DISCONTINUE_CUE`, `_SKIN_TYPE_QUESTION_MARKERS`,
`_SKIN_TYPE_QUESTION_RE`, `_SEEK_TREATMENT_SIGNALS`, `_HAS_ACNE_SELF`,
`_ACTIVE_INFLAMMATORY_LESIONS`

> 15 khối, dùng **nén có khai báo §1** cho mục 2/3/4/7. Mục 1/5/6/8 dưới đây.

1. in/out: 6 `Literal` khai kiểu; 7 chuỗi regex; 1 dict thứ tự
   (`_INFLAMMATION_ORDER`); 1 frozenset (`_ACTIVE_INFLAMMATORY_LESIONS`). {code}
5. config: hằng cứng. {code}
6. ai gọi: mỗi hằng 1–3 chỗ trong cùng file, trừ `_SKIN_TYPE_QUESTION_RE` (còn
   được `rule_extractor.py:82` alias thành `_QUESTION_RE`) và
   `_ALLERGY_REACTION_VERBS` (còn được `rule_extractor.py:219`). {code}
8. deprecated: không. {code}

**Nhận xét riêng:**
- `_INFLAMMATION_ORDER` đặt `"unknown": 0` **và** `"none": 0` — hai giá trị cùng
  hạng, nên `_strongest_inflammation` giữ giá trị gặp trước. Trùng khớp với
  `chat/session/fold.py:102 _SEVERITY_ORDER`, là **bản sao thứ hai** của cùng
  bảng thứ tự trong repo.
- `_ACTIVE_INFLAMMATORY_LESIONS` (`:1832`) là frozenset 5 phần tử gồm `"other"`,
  trong khi `_extract_inflammation:~1730` định nghĩa lại một set cùng tên ý nghĩa
  **không** có `"other"` (4 phần tử). Hai định nghĩa cho cùng khái niệm, lệch một
  phần tử, cách nhau 100 dòng. Xem Q-20.
- `_SKIN_TYPE_QUESTION_MARKERS` được viết riêng cho skin_type nhưng bị
  `rule_extractor` tái dùng làm bộ lọc câu hỏi tổng quát — xem khối `_QUESTION_RE`.

### [x] `_allergy_pattern` (`rule_normalizer.py:633-637`)
1. in/out: `(substance: str) -> str`; trả `(?:xuôi|ngược)`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không (chỉ nối chuỗi). {code}
5. config: `_ALLERGY_REACTION_VERBS`, `_ALLERGY_REACTION_AFTER`. {code}
6. ai gọi: 20 lần lúc dựng `_ALLERGY_TERMS`. {code}
7. invariant: `substance` được nhúng **nguyên văn** vào regex, không `re.escape`
   — đúng ý, vì mọi lời gọi truyền sẵn một nhóm regex (`r"(?:salicylic(?:\s*acid)?|…)"`).
   Nhưng hợp đồng đó không được ghi ở đâu; truyền một chuỗi có `(` chưa đóng sẽ
   làm hỏng regex và chỉ nổ lúc `_extract_allergies` chạy lần đầu. {code}
8. deprecated: không. {code}

### [x] `_has` (`rule_normalizer.py:972-973`)
1. in/out: `(pattern: str, text: str) -> bool`. {code}
2. side effect: không. {code}
3. state: không (dựa vào cache regex nội bộ của module `re`). {code}
4. lỗi: `re.error` nếu pattern hỏng — **lúc chạy**, không lúc import. {code}
5. config: `re.IGNORECASE` cứng. {code}
6. ai gọi: **hàm được gọi nhiều nhất file** — hơn 120 chỗ. {code}
7. invariant: nhận **chuỗi** rồi để `re` tự cache compile (`re._cache`, 512 entry
   mặc định). Với ~950 dòng bảng regex, số pattern riêng biệt vượt xa 512 → cache
   bị đuổi liên tục và pattern phải compile lại nhiều lần trong một request. Đây
   là khác biệt lớn so với `intent_router._terms_regex` (lru_cache riêng, 128
   entry, không bao giờ đuổi). Xem Q-21. {code}
8. deprecated: không. {code}

### [x] `_dedupe` (`rule_normalizer.py:976-984`)
1. in/out: `(items: list[str]) -> list[str]`; giữ thứ tự. {code}
2-3. không side effect, không state. {code}
4. lỗi: `TypeError` nếu item không hashable. {code}
5. config: không. {code}
6. ai gọi: 12 chỗ. {code}
7. invariant: so sánh **phân biệt hoa thường và có dấu** — bản anh em
   `_dedupe_accent_insensitive` mới bỏ dấu. Hàm nào dùng bản nào là quyết định
   per-field, không có quy tắc chung: `_extract_lesions` dùng bản nhạy dấu,
   `normalize_chat_message:~1900` dùng bản không dấu cho products/medications.
   Đây là **bản sao thứ ba** của `_dedupe_values`/`_dedupe` trong repo (hai bản
   kia ở `chat/session/fold.py:65` và `utils/retrieval_query.py:50`). {code}
8. deprecated: không. {code}

### [x] `_dedupe_floats` (`rule_normalizer.py:986-994`)
1. in/out: `(items: list[float]) -> list[float]`. {code}
2-3. không. {code}
4. lỗi: `ValueError` nếu item không ép được sang float. {code}
5. config: làm tròn 8 chữ số. {code}
6. ai gọi: `_extract_concentrations:~1396`, `normalize_chat_message:~1912`. {code}
7. invariant: `round(x, 8)` để `0.1 + 0.2` và `0.3` coi là một — cần thiết vì
   nồng độ được tính bằng phép chia `/100.0`. Giữ **giá trị gốc** trong output,
   chỉ dùng giá trị làm tròn làm khoá — đúng cách. {code}
8. deprecated: không. {code}

### [x] `_texts_for_extraction` (`rule_normalizer.py:997-1002`)
1. in/out: `(clean_text, clean_text_no_accent=None) -> list[str]` (1 hoặc 2 phần tử). {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `normalize_chat_message:~1884`, `rule_extractor.py:~247`. {code}
7. **invariant nền tảng của cả module:** mọi extractor chạy **hai lượt** — một
   trên bản có dấu, một trên bản bỏ dấu — rồi hợp nhất. Đây là lý do 13 bảng term
   phải liệt kê song song hai biến thể (§1 mục 7), và là lý do chi phí regex nhân
   đôi. Chỉ thêm bản không dấu khi nó **khác** bản gốc, nên tin nhắn viết không
   dấu sẵn chỉ chạy một lượt. {code}
8. deprecated: không. {code}

### [x] `_merge_extracted` (`rule_normalizer.py:1005-1009`)
1. in/out: `(texts: list[str], extractor) -> list[str]`. {code}
2. side effect: qua extractor. {code}
3. state: không. {code}
4. lỗi: từ extractor. {code}
5. config: không. {code}
6. ai gọi: 9 chỗ ở `normalize_chat_message`, 7 chỗ ở `rule_extractor`. {code}
7. invariant: `str(x)` ép mọi kết quả về chuỗi rồi `_dedupe` nhạy dấu — nên nhãn
   trích từ bản có dấu và bản không dấu **không** gộp được nếu chúng khác nhau.
   Với các bảng trả nhãn tiếng Anh cố định (`"papule"`, `"nodule"`) thì không sao;
   với `_extract_products` trả term tiếng Việt thì "sữa rửa mặt" và "sua rua mat"
   là hai mục. Đó là lý do `normalize_chat_message` phải bọc thêm
   `_dedupe_accent_insensitive` cho đúng hai field đó. {code}
8. deprecated: không. {code}

### [x] `_dedupe_accent_insensitive` (`rule_normalizer.py:1012-1020`)
1. in/out: `(items: list[str]) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `normalize_chat_message:~1899,1902`, `rule_extractor.py:~295,296`. {code}
7. invariant: giữ **mục đầu tiên** gặp, tức bản có dấu thắng (vì
   `_texts_for_extraction` đặt bản có dấu trước). Hành vi mong muốn, nhưng phụ
   thuộc thứ tự của một hàm khác — ràng buộc ngầm. {code}
8. deprecated: không. {code}

### [x] `_first_extracted` (`rule_normalizer.py:1023-1028`)
1. in/out: `(texts, extractor)` → giá trị đầu tiên khác None. {code}
2. side effect: qua extractor. {code}
3. state: không. {code}
4. lỗi: từ extractor. {code}
5. config: không. {code}
6. ai gọi: 4 chỗ (age, sex, duration, và ở `rule_extractor`). {code}
7. invariant: dùng cho field **scalar** — bản có dấu luôn được thử trước, nên
   kết quả từ text gốc thắng. Đối xứng với `_merge_extracted` cho field list. {code}
8. deprecated: không. {code}

### [x] `_extract_acne_count` (`rule_normalizer.py:1034-1074`)
1. in/out: `(text) -> Literal["few","moderate_count","many"] | None`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: hai regex nội tuyến trong thân hàm. {code}
6. ai gọi: `_extract_inflammation:~1725` — **một chỗ duy nhất**. {code}
7. invariant: docstring nói "Không expose ra schema ngoài; chỉ dùng nội bộ trong
   `_extract_inflammation`" — đúng, grep xác nhận 1 caller. Nhưng kiểu trả về khai
   3 giá trị còn thân hàm **chỉ trả `"many"`, `"few"` hoặc None** — nhãn
   `"moderate_count"` không bao giờ được sinh. Literal khai rộng hơn hành vi. {code}
8. deprecated: không. {code}

### [x] `_extract_age` (`rule_normalizer.py:1077-1093`)
1. in/out: `(text) -> int | None`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: chặn tuổi hợp lý `5 <= age <= 80` cứng trong thân hàm. {code}
6. ai gọi: `_first_extracted` ở `normalize_chat_message` và `rule_extractor`. {code}
7. invariant: pattern 2 (`\b(\d{1,3})\s*t\b`) có negative lookahead loại
   `nay|rồi|qua|trước|sau|nữa|hơn` — comment `:1082-1083` giải thích đúng ("2t
   nay" là 2 tháng nay, không phải 2 tuổi). Nhưng danh sách loại trừ không có
   `"tuần"`/`"tháng"`, nên `"3t tháng"`... không xảy ra thực tế. Vòng lặp
   `for pattern` **không** `break` khi tuổi ngoài `[5,80]` mà thử pattern tiếp —
   đúng ý (số 3 trong "3t" bị loại, rồi thử pattern khác). {code}
8. deprecated: không. {code}

### [x] `_extract_duration_weeks` (`rule_normalizer.py:1096-1108`)
1. in/out: `(text) -> int | None`; quy mọi đơn vị về **tuần**. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: hệ số quy đổi cứng — năm×52, tháng×4, ngày÷7. {code}
6. ai gọi: `_first_extracted`. {code}
7. **invariant: lấy khớp ĐẦU TIÊN, không phải khớp liên quan nhất.** Regex khớp
   bất kỳ `<số> <đơn vị thời gian>` nào trong câu. "em 22 tuổi, bị mụn 3 tháng" —
   `\b(\d{1,3})\s*(năm|nam\b|ngày|…)` không khớp "22 tuổi" (tuổi không trong danh
   sách đơn vị) nên an toàn ở ví dụ này; nhưng "dùng BHA 2 tuần rồi ngưng, mụn 6
   tháng nay" trả **2 tuần** thay vì 24. Không có ưu tiên theo ngữ cảnh mụn.
   Tháng×4 (không phải 4.33) làm 12 tháng ra 48 tuần chứ không 52 — lệch với
   nhánh năm×52. {code}
8. deprecated: không. {code}

### [x] `_extract_skin_type` (`rule_normalizer.py:1131-1139`)
1. in/out: `(text) -> _SkinType | None`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_SKIN_TYPE_QUESTION_RE`, `_SKIN_TYPES`. {code}
6. ai gọi: `_extract_skin_type_from_texts` (2 lần). {code}
7. invariant: cổng câu-hỏi chạy **trước** mọi pattern, nên "da dầu có dễ bị mụn
   hơn da khô không" trả None — comment `:1113-1115` mô tả đúng ca đó. Vòng lặp
   trả **loại đầu tiên khớp** theo thứ tự `_SKIN_TYPES`, nên "da hỗn hợp thiên
   dầu" phụ thuộc thứ tự bảng chứ không phụ thuộc độ đặc hiệu. {code}
8. deprecated: không. {code}

### [x] `_extract_skin_type_from_texts` (`rule_normalizer.py:1142-1150`)
1. in/out: `(clean_text, clean_text_no_accent) -> _SkinType | None`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `normalize_chat_message:~1928`, `rule_extractor.py:~251`. {code}
7. **invariant riêng, không có ở field nào khác:** trước khi thử bản không dấu,
   nó chặn nếu bản **có dấu** chứa `\b(?:da|mặt)\s*đau\b` (`:1148`). Lý do không
   được ghi, nhưng suy ra được: bỏ dấu biến "da đau" thành "da dau", trùng với
   "da dầu" → "da dau". Một cổng chống nhập nhằng cụ thể, đúng chỗ. Đây là bằng
   chứng rằng chiến lược "chạy hai lượt có dấu/không dấu" tự nó sinh lỗi. {code}
8. deprecated: không. {code}

### [x] `_extract_sex` (`rule_normalizer.py:1156-1160`)
1. in/out: `(text) -> _Sex | None`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_SEX_TERMS`. {code}
6. ai gọi: `_first_extracted`. {code}
7. invariant: không có cổng câu-hỏi như skin_type. Comment ở
   `normalize_chat_message:~1918` nói rõ giới tính **không** được đoán từ đại từ
   "chị/em" vì không đáng tin — nên bảng `_SEX_TERMS` phải tự hẹp. Suy `female`
   từ hormonal factor được làm ở tầng trên, không ở đây. {code}
8. deprecated: không. {code}

### [x] `_discontinued_before` (`rule_normalizer.py:1172-1178`)
1. in/out: `(before: str) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_DISCONTINUE_CUE`; cửa sổ **30 ký tự cuối**, cho phép **0–2 từ** xen
   giữa cue và term. {code}
6. ai gọi: `_positive_mention:~1183`, `_has_product_use_context:~1198`. {code}
7. invariant: comment `:1166-1168` nêu đúng đánh đổi — chỉ nhận cue **sát** term
   để "không dùng X nữa" bị loại còn "không bị kích ứng khi dùng X" giữ lại.
   Cửa sổ 30 ký tự + tối đa 2 từ là bản chặt hơn hẳn
   `chat/session/fold.py:_mentions_stop` (40 ký tự, **không** giới hạn số từ).
   Hai cơ chế phủ định trong repo, cái ở đây tốt hơn. {code}
8. deprecated: không. {code}

### [x] `_positive_mention` (`rule_normalizer.py:1180-1186`)
1. in/out: `(pattern: str, text: str) -> bool`. {code}
2-3. không. {code}
4. lỗi: `re.error` nếu pattern hỏng. {code}
5. config: không. {code}
6. ai gọi: `_extract_canonical_ingredients._in_use`,
   `rule_extractor.py:~306` (fuzzy filter của products). {code}
7. invariant: **`finditer` — chỉ cần MỘT lần nhắc không bị phủ định là True.**
   Đúng cho "ngưng BHA hôm trước, giờ dùng BHA lại". Ngược lại, "dùng BHA rồi
   ngưng BHA" cũng True — không có khái niệm lần nhắc **cuối cùng** thắng. {code}
8. deprecated: không. {code}

### [x] `_has_product_use_context` (`rule_normalizer.py:1188-1238`)
1. in/out: `(lowered: str, term: str) -> bool`; 51 dòng, 12 nhánh. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: cửa sổ **80 ký tự trước** / **40 ký tự sau**, cứng. {code}
6. ai gọi: `_extract_products:~1320`. {code}
7. **invariant hỏng — `"da"` trong danh sách aspect marker.** Nhánh xác nhận
   `\b(?:đang|dang|đã|da|mới|moi|vừa|vua|từng|tung|hiện\s*tại|hien\s*tai)\b`
   (`:1224`) chứa `da` — vốn là dạng không dấu của `đã`, **nhưng cũng là từ "da"
   (skin), từ phổ biến nhất trong toàn bộ miền này**. Cùng lỗi với
   `_has_medication_use_context`; đo đạc ở khối đó. {code}
8. deprecated: không. {code}

### [x] `_extract_products` (`rule_normalizer.py:1315-1330`)
1. in/out: `(text) -> list[str]`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: `_PRODUCT_TERMS`, `_PRODUCT_CANONICAL_MAP`. {code}
6. ai gọi: `_merge_extracted` ở hai file. {code}
7. invariant: dùng `(?<!\w)…(?!\w)` (ranh giới từ thật) **rồi** mới hỏi ngữ cảnh
   dùng. Hai cổng nối tiếp. Term không có trong canonical map đi thẳng ra ở dạng
   gốc — xem nhận xét của `_PRODUCT_CANONICAL_MAP`. {code}
8. deprecated: không. {code}

### [x] `_extract_canonical_ingredients` (`rule_normalizer.py:1333-1366`)
1. in/out: `(products, medications, clean_text, clean_text_no_accent) -> list[str]`;
   chỉ sinh 3 nhãn: `salicylic_acid`, `glycolic_acid`, `tretinoin`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: 3 regex nội tuyến. {code}
6. ai gọi: `normalize_chat_message:~1906`. {code}
7. invariant: comment `:1359-1360` giải thích một cổng tinh tế — `VA` viết hoa
   được nhận là tretinoin, `va` viết thường thì không, vì "và" bỏ dấu cũng là
   "va". Đây là **cổng phân biệt hoa-thường duy nhất** trong toàn module, mọi chỗ
   khác đều `IGNORECASE`. Chỉ 3 hoạt chất được canonical hoá trong khi
   `_MEDICATION_TERMS` có hàng chục — trường `canonical_ingredients` vì thế phủ
   rất hẹp so với tên gọi. {code}
8. deprecated: không. {code}

### [x] `_in_use` (hàm lồng trong `_extract_canonical_ingredients`, `:1341-1352`)
1. in/out: `(text_pat: str, prod_med_pat: str) -> bool`. {code}
2. side effect: không. {code}
3. state: closure bắt `prod_med`, `clean_text`, `clean_text_no_accent`. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: 3 chỗ trong hàm cha. {code}
7. invariant: hai đường xác nhận — (a) chất đã có trong `products`/`medications`
   (đã qua cổng ngữ cảnh dùng) → chắc chắn đang dùng; (b) được nhắc trong text mà
   không bị phủ định. Đường (b) **yếu hơn hẳn** đường (a): nó chỉ kiểm phủ định,
   không kiểm "đang dùng". Nên "nghe nói BHA tốt" (không phủ định) → canonical
   ingredient `salicylic_acid`, dù `_extract_products` đã đúng đắn loại nó. Hai
   trường của cùng `AcneClinicalInput` bất đồng về cùng một chất. Xem Q-22. {code}
8. deprecated: không. {code}

### [x] `_extract_usage_frequencies` (`rule_normalizer.py:1369-1386`)
1. in/out: `(text) -> list[str]`; 2 nhãn (`twice_daily`, `every_other_day`). {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: 2 regex nội tuyến. {code}
6. ai gọi: `_merge_extracted` ở `normalize_chat_message:~1910`. {code}
7. invariant: chỉ 2 nhãn — không có `once_daily`, không có `weekly`. Người dùng
   nói "ngày 1 lần" cho ra list rỗng, không phân biệt được với "không nói gì".
   Trường này vì thế chỉ dùng được để phát hiện **hai** chế độ cụ thể. {code}
8. deprecated: không. {code}

### [x] `_extract_concentrations` (`rule_normalizer.py:1388-1396`)
1. in/out: `(text) -> list[float]`; chia 100 → tỉ lệ. {code}
2-3. không. {code}
4. lỗi: `try/except ValueError` bọc `float()` → bỏ qua. {code}
5. config: không. {code}
6. ai gọi: `normalize_chat_message:~1912`. {code}
7. **invariant: bắt MỌI số kèm `%` trong câu, không phân biệt nó thuộc về gì.**
   "BHA 2% dùng 50% số ngày" cho ra `[0.02, 0.5]`. Không có liên kết nào giữa
   nồng độ và hoạt chất — `concentrations` là list phẳng, `canonical_ingredients`
   là list phẳng khác, không ghép cặp. Với tư vấn thuốc bôi thì cặp (chất, nồng
   độ) mới có nghĩa. Xem Q-23. {code}
8. deprecated: không. {code}

### [x] `_has_medication_use_context` (`rule_normalizer.py:1398-1456`)
1. in/out: `(lowered: str, term: str) -> bool`; 59 dòng, 11 nhánh. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: cửa sổ 80/40 ký tự, cứng. {code}
6. ai gọi: `_extract_medications:~1463`; `rule_extractor.py:~313` (fuzzy filter). {code}
7. **invariant hỏng — đo được:** thứ tự nhánh là (1–4) loại trừ câu hỏi/nghe nói,
   (5) loại trừ phủ định, **(6) xác nhận aspect marker → `return True`**, rồi (7)
   mới loại trừ câu hỏi/giả định. Nhánh 6 chứa `da`, dạng không dấu của `đã`,
   trùng với từ "da" (skin). Vì nhánh 6 `return` trước nhánh 7, một câu hỏi thuần
   tuý có chữ "da" ở đầu bị ghi nhận là **đang dùng thuốc**. Chạy thật trên chính
   hàm này:

   | câu | kết quả |
   |---|---|
   | `da em bị mụn, tretinoin có tốt không?` | **True** (sai) |
   | `tretinoin có tốt không?` | False (đúng) |
   | `da mình dầu, isotretinoin là gì vậy ạ` | **True** (sai) |
   | `nghe nói isotretinoin hay lắm` | False (đúng) |
   | `em đang bôi tretinoin 3 tuần rồi` | True (đúng) |
   | `da khô có nên dùng doxycycline không` | False (đúng — nhánh 4 chặn trước) |

   Hai câu hỏi kiến thức bị ghi thành thuốc đang dùng, chỉ vì có chữ "da". Chuỗi
   này chảy vào `UserContext.medications` → `confirmed_profile` →
   `medication_safety_refusal`, cổng tất định mà `fold.py:3-4` gọi là cổng an toàn
   duy nhất. Xem Q-24. {code}
8. deprecated: không. {code}

### [x] `_extract_medications` (`rule_normalizer.py:1458-1465`)
1. in/out: `(text) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_MEDICATION_TERMS`. {code}
6. ai gọi: `_merge_extracted` ở hai file. {code}
7. invariant: ánh xạ tay `"ada" → "adapalene"` ngay trong biểu thức trả về
   (`:1465`) — **quy tắc canonical duy nhất** cho medications, trong khi products
   có cả một `_PRODUCT_CANONICAL_MAP`. Truyền generator vào `_dedupe`, hàm này
   khai `list[str]`; chạy được vì chỉ lặp, nhưng chú thích kiểu sai. {code}
8. deprecated: không. {code}

### [x] `_extract_distributions` (`rule_normalizer.py:1479-1480`)
1. in/out: `(text) -> list[_Distribution]`; một dòng, duyệt `_DISTRIBUTION_TERMS`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_DISTRIBUTION_TERMS`. {code}
6. ai gọi: `_merge_extracted` ở hai file. {code}
7. invariant: **không có cổng ngữ cảnh nào** — khác hẳn products/medications. Một
   câu hỏi kiến thức nhắc "mụn ở lưng" cũng sinh phân bố `back`. Ba mức nghiêm
   ngặt khác nhau cho ba nhóm field trong cùng module. {code}
8. deprecated: không. {code}

### [x] `_extract_lesions` (`rule_normalizer.py:1483-1484`)
1. in/out: `(text) -> list[_LesionType]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_LESION_TERMS`. {code}
6. ai gọi: `_merge_extracted`; kết quả còn được truyền vào `_extract_inflammation`. {code}
7. invariant: nhãn `"other"` bắt-tất khiến hàm gần như luôn trả list khác rỗng
   khi có chữ "mụn". Đo được: `_extract_lesions("em bị mụn, muốn tư vấn cách trị")`
   → `['other']`. Hệ quả dây chuyền: `clinical` không bao giờ là None cho câu
   nhắc mụn, và `_clinical_has_case_signal` phải lọc `"other"` ra. {code}
8. deprecated: không. {code}

### [x] `_extract_hormonal_factors` (`rule_normalizer.py:1487-1488`)
1. in/out: `(text) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_HORMONAL_TERMS`. {code}
6. ai gọi: `_merge_extracted`. {code}
7. invariant: kết quả được `normalize_chat_message:~1919-1923` dùng để **suy giới
   tính female** khi gặp `menstrual_cycle`/`pregnancy`/`postpartum`/`pcos`. Đây là
   trường duy nhất trong module có hệ quả suy diễn sang trường khác, và bốn nhãn
   đó phải khớp chính xác với `_HORMONAL_TERMS` — không có kiểm tra nào bảo đảm
   điều đó, nếu đổi tên nhãn thì suy diễn im lặng ngừng hoạt động. {code}
8. deprecated: không. {code}

### [x] `_extract_red_flags` (`rule_normalizer.py:1491-1511`)
1. in/out: `(text) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_RED_FLAG_TERMS` + một regex bổ sung nội tuyến. {code}
6. ai gọi: `_merge_extracted`; kết quả vào `red_flags_input`, rồi vào
   `intent_router.compute_route_flags` (`urgency_red_flag`) và
   `_URGENT_CLINICAL_FLAGS`. {code}
7. invariant: nhánh bổ sung cho `painful_lesions` đòi **đồng thời** ngữ cảnh
   mụn-đau trong cửa sổ 30 ký tự **và** `_is_self_description(text)` — cổng chặt
   nhất trong module, hợp lý vì cờ này đẩy thẳng lên `advise` confidence 0.92 ở
   `intent_router`. Đây là chỗ hiếm hoi mà mức nghiêm ngặt tương xứng với hậu quả. {code}
8. deprecated: không. {code}

### [x] `_extract_allergies` (`rule_normalizer.py:1514-1525`)
1. in/out: `(text) -> list[str]`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_ALLERGY_TERMS`. {code}
6. ai gọi: `_merge_extracted`. {code}
7. invariant: bỏ nhãn `"unknown"` khi có chất cụ thể (`:1522-1523`) — docstring
   giải thích đúng. Nhưng nhãn `"unknown"` **vẫn ở lại** khi không có chất nào,
   nghĩa là `UserContext.allergies` có thể chứa chuỗi `"unknown"` như một dị ứng
   thật, rồi được `PromptBuilder` in ra dưới dạng "dị ứng: unknown". Cần kiểm ở
   `src.chat` xem prompt có lọc không. {code}
8. deprecated: không. {code}

### [x] `_extract_treatment_goals` (`rule_normalizer.py:1560-1602`)
1. in/out: `(text) -> list[str]`; bảng + 3 quy tắc suy diễn. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_TREATMENT_GOAL_TERMS`, `_SEEK_TREATMENT_SIGNALS`, `_HAS_ACNE_SELF`,
   2 regex nội tuyến. {code}
6. ai gọi: `_merge_extracted`. {code}
7. invariant: ba quy tắc suy diễn đều đòi **hai** tín hiệu đồng thời
   (`clear_acne` = có mụn + tìm lời khuyên + không phải câu hỏi kiến thức thuần;
   `reduce_inflammation` = lesion viêm + tìm lời khuyên; `see_doctor` = tín hiệu
   nặng + có mụn). Thiết kế nhất quán. `clear_acne` được **chèn đầu list**
   (`["clear_acne"] + found`) trong khi hai nhãn kia `append` — thứ tự không được
   dùng ở hạ nguồn nên vô hại. {code}
8. deprecated: không. {code}

### [x] `_extract_scarring_signs_from_extracted` (`rule_normalizer.py:1605-1615`)
1. in/out: `(lesion_types, red_flags) -> list[str]`; tối đa 2 chuỗi tiếng Việt. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: `normalize_chat_message:~1905`, `rule_extractor.py:~285`. {code}
7. invariant: hàm duy nhất **không** đọc text — nó suy từ kết quả của hai
   extractor khác. Miền giá trị đóng: chỉ `"sẹo mụn"` và `"thâm sau mụn"`. Đó là
   lý do hai nhánh cuối của `rule_extractor._scarring_confidence` chết (xem khối
   đó). Đầu ra là **tiếng Việt** trong khi mọi nhãn lâm sàng khác là tiếng Anh —
   schema `scarring_signs` là free-text nên chấp nhận, nhưng không nhất quán. {code}
8. deprecated: không. {code}

### [x] `_strongest_inflammation` (`rule_normalizer.py:1628-1635`)
1. in/out: `(values: list[str | None]) -> _Inflammation | None`. {code}
2-3. không. {code}
4. lỗi: không (`.get(value, 0)` nuốt nhãn lạ). {code}
5. config: `_INFLAMMATION_ORDER`. {code}
6. ai gọi: `normalize_chat_message:~1893`, `rule_extractor.py:~289`. {code}
7. invariant: **không bao giờ hạ cấp** — dùng để hợp nhất kết quả của lượt có dấu
   và lượt không dấu. Cùng ngữ nghĩa với `chat/session/fold.py:_max_severity`,
   nhưng đó là bản sao thứ hai với bảng thứ tự riêng. Nhãn lạ tụt về hạng 0 im
   lặng, thua cả `"mild"`. {code}
8. deprecated: không. {code}

### [x] `_is_self_description` (`rule_normalizer.py:1638-1663`)
1. in/out: `(text) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: 2 regex nội tuyến. {code}
6. ai gọi: `_extract_red_flags:~1508`, `_extract_treatment_goals:~1573`,
   `_extract_inflammation:~1686,1793,1799`. {code}
7. invariant: đòi **đồng thời** đại từ ngôi 1 **và** mô tả triệu chứng — docstring
   nói rõ. Đây là cổng chống-suy-diễn tốt nhất trong module. Nhưng nó dùng
   `\b(?:tôi|toi|mình|minh|em|cháu|chau|con)\b` — cùng danh sách mà
   `intent_router._PERSONAL_TERMS` **từ chối** dùng vì `"em"`/`"con"` trùng từ
   thông thường. Vế thứ hai (mô tả triệu chứng) bù lại phần lớn rủi ro đó. {code}
8. deprecated: không. {code}

### [x] `_is_knowledge_question` (`rule_normalizer.py:1666-1681`)
1. in/out: `(text) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: 1 regex nội tuyến, 9 marker. {code}
6. ai gọi: `_extract_treatment_goals:~1574`, `_extract_inflammation:~1686`. {code}
7. invariant: 9 marker ở đây so với **18 mục** của
   `intent_router._KNOWLEDGE_RANKING_TERMS` — hai định nghĩa "câu hỏi kiến thức"
   trong hai file, không chia sẻ. Bản ở đây không có `"top 10"`, `"liệt kê"`,
   `"danh sách"`. Cùng khái niệm, hai độ phủ. {code}
8. deprecated: không. {code}

### [x] `_extract_inflammation` (`rule_normalizer.py:1684-1803`)
1. in/out: `(text, lesion_types) -> _Inflammation | None`; 120 dòng, 9 nhánh trả về. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config: 5 regex nội tuyến + `_extract_acne_count`. {code}
6. ai gọi: `normalize_chat_message:~1893`, `rule_extractor.py:~290`. {code}
7. invariant: thứ tự nhánh là toàn bộ logic — cổng câu-hỏi-kiến-thức → severe
   (5 đường) → `none` → moderate (2 đường) → mild (2 đường) → None. Ba đường
   severe phụ (máu, sốt, nodule+đau) đều đòi `_has_acne_context`, comment giải
   thích đúng lý do ("không fire trên 'bé bị sốt'"). Nhánh `none` đòi **cả**
   `_only_comedonal or _explicit_no_inflam` **và** `not _has_inflammatory_lesion`
   — đúng, ngăn "mụn bọc nhưng không đau" tụt xuống none. Suy moderate từ lesion
   đòi thêm `_is_self_description`, nên câu hỏi chung không sinh moderate. {code}
8. deprecated: hàm định nghĩa lại `_active_inflammatory_lesions` (4 phần tử,
   `:1730`) trong khi module đã có `_ACTIVE_INFLAMMATORY_LESIONS` (5 phần tử, có
   `"other"`, `:1832`). Hai set cùng tên ý nghĩa, lệch nhau, cách 100 dòng.
   Biến `_sequelae_lesions` (`:1731`) được gán và **không dùng**. Xem Q-20. {code}

### [x] `_acne_resolved` (`rule_normalizer.py:1837-1844`)
1. in/out: `(clean_text, clean_text_no_accent) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: `_ACNE_PRESENT_PATTERNS`, `_ACNE_RESOLVED_PATTERNS`. {code}
6. ai gọi: `normalize_chat_message:~1889`. {code}
7. invariant: kiểm **PRESENT trước RESOLVED** và thoát ngay khi thấy tín hiệu
   đang-có-mụn — comment `:1822` nói đúng lý do ("tránh suppress nhầm ca hỗn
   hợp"). Fail-safe đúng hướng: nghi ngờ thì coi như còn mụn. Chạy trên **cả hai**
   bản text cho mỗi pattern, tức 20 × 2 = 40 lần `re.search` mỗi tin nhắn. {code}
8. deprecated: không. {code}

### [x] `_contains_positive` (`rule_normalizer.py:1847-1850`)
1. in/out: `(text, positive: str, negative: str) -> bool`. {code}
2-3. không. {code}
4. lỗi: không. {code}
5. config: không. {code}
6. ai gọi: 4 chỗ ở `normalize_chat_message` (2 cho `is_pregnant`, 2 cho
   `is_breastfeeding`). {code}
7. **invariant hỏng — phủ định không có phạm vi:** hàm trả False nếu `negative`
   khớp **bất kỳ đâu** trong text, kể cả ở mệnh đề nói về người khác. "chị tôi
   không mang thai, em thì có" → `is_pregnant=False`. Đây đúng là hướng hỏng mà
   `chat/session/fold.py:~205-215` đã xoá 17 keyword để tránh, với lý do ghi rõ
   "rule không bao giờ được tự hạ xuống False". Cùng nguyên tắc, hai file, hai kết
   luận trái ngược. Xem Q-19. {code+comment}
8. deprecated: không. {code}

### [x] `normalize_chat_message` (`rule_normalizer.py:1853-1975`)
1. in/out: `(message, mode="auto", clean_text=None, clean_text_no_accent=None) -> UserInput`;
   123 dòng, hàm công khai **duy nhất** của file. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `pydantic.ValidationError` nếu `UserContext`/`AcneClinicalInput` từ chối
   giá trị — không bắt, nổi lên `intake.py`. {code}
5. config: `mode` được kẹp về `{"hybrid","llm_only"}`, mặc định `"hybrid"`. {code}
6. ai gọi: `intake.py` (đường rule fallback); test. {code}
7. **invariant: cổng dựng `clinical` bỏ sót hai trường.** Điều kiện `if (...)` ở
   `:~1958` liệt kê 10 thứ nhưng **không** có `treatment_goals` và
   `scarring_signs`. `scarring_signs` suy từ lesion/red_flags nên không thể khác
   rỗng một mình. `treatment_goals` thì có thể. Đo được:
   `"muốn trị dứt điểm"` → `goals=['clear_acne']`, `lesions=[]`, mọi thứ khác rỗng
   → `clinical=None` → **mục tiêu điều trị bị vứt**. Ba câu tôi thử có nhắc "mụn"
   đều thoát nhờ nhãn bắt-tất `"other"`, nên lỗi này hiếm chứ không phải không
   xảy ra. Xem Q-25.
   Ngoài ra `is_breastfeeding` nhánh thứ hai (`:~1949`) truyền negative pattern
   `r"\b(?:khong|ko|k)\b"` — **phủ định trần, không có tân ngữ**. Vế `is_pregnant`
   tương ứng thì đúng (`khong\s+(?:mang thai|co thai|bau)`). Tôi truy vế này tới
   cùng: vì hai vế nối bằng `or` và miền positive của vế 2 là **tập con** của vế 1,
   vế 2 không bao giờ cứu được một False thành True — nên đây là **nhánh chết**,
   không phải lỗi đang cắn. Ghi lại vì nó sẽ thành lỗi thật ngay khi ai đó sửa vế 1. {code}
8. deprecated: không. {code}

---

## §5 — Điều tìm được (câu hỏi)

**Q-01 — `llm_router.py` và `llm_extractor.py` (265 dòng) không chạy ở cấu hình
hiện tại.** `di.py:133` rẽ nhánh theo `intake_mode`; hai file này chỉ được
`import` **bên trong nhánh `else`** (`di.py:165-166`). `.env` đặt
`INTAKE_MODE=unified`, nên trong production Python còn chưa nạp chúng. Với khoá
luận: hoặc ghi rõ trong báo cáo rằng đây là đường A/B giữ lại có chủ đích, hoặc
xoá. Đừng để giám khảo tự phát hiện. {code}

**Q-02 (ĐÃ SỬA — nhẹ hơn tôi viết ban đầu) — hằng `_RUNTIME_SYSTEM` trong hai
adapter không được gửi, nhưng đó là thiết kế đúng.** Cả hai truyền
`generate_text(system=_RUNTIME_SYSTEM, ...)`, và `di.py:186`/`di.py:220` dựng
backend với `use_modelfile_system=True`, nên `ollama_backend._build_messages:196`
bỏ system message. Tôi đã đối chiếu với Modelfile thật thay vì dừng ở suy đoán:

- `model/intaker/Modelfile` SYSTEM so với `unified_intake._RUNTIME_SYSTEM`:
  **giống hệt nhau**, 3.322 ký tự, cùng sha256 sau khi chuẩn hoá khoảng trắng
  (`6ee28283b579feb8`). Hằng Python là bản sao có chủ đích của Modelfile.
- `model/legacy/Modelfile` và `model/legacy/Modelfile.extractor`: SYSTEM **khác**
  hai hằng Python, và **dài hơn hẳn** — Modelfile.extractor mở đầu bằng "Bạn là
  bộ TRÍCH XUẤT thông tin cho hệ tư vấn da mụn tiếng Việt. Bạn KHÔNG tư vấn…",
  trong khi hằng Python chỉ là hai câu. Bản thật nằm trong Modelfile.

Kết luận đúng: prompt tới model là bản trong Modelfile, và nó tốt hơn hoặc bằng
bản Python. Vấn đề còn lại **chỉ là dễ gây hiểu nhầm** — người đọc code thấy một
chuỗi system prompt và tưởng đó là thứ đang chạy. Với `unified_intake` thì hai
bản phải giữ đồng bộ bằng tay và không có test nào canh việc đó; đề xuất một test
so sha256 giữa Modelfile và hằng Python. {code}

**Q-03 — `_timeout` là bản sao chết ở cả ba adapter.**
`LLMExtractor:45`, `LLMRouter:54`, `UnifiedIntake:80` đều gán `self._timeout` và
không dùng. Timeout thật đã áp ở tầng HTTP khi `di.py` dựng
`OllamaBackend(timeout=...)`. `LLMRouter` còn phơi property `timeout` mà 0 caller
đọc. {code}

**Q-04 (ĐÃ TRẢ LỜI — không phải lỗi).** Ở chế độ unified, `di.py:158-159` gán
cùng một `UnifiedIntake` cho `llm_router` và `llm_extractor`, và `di.py:73-79`
gọi `.close()` trên cả hai. Tôi đã đọc `unified_intake.py:177-183`:
`close()` có cờ `self._closed` và `return` ngay ở lần gọi thứ hai. Idempotent
theo hợp đồng, không phải theo may mắn. Khép câu hỏi này. {code}

**Q-05 — `_short_history` có hai bản.** `llm_router.py:94-108` (hàm riêng) và
`llm_extractor.py:90-102` (nội tuyến trong `_build_prompt`). Cùng logic, cùng
hằng số 3 lượt / 300 ký tự. Hai file cạnh nhau. {code}

**Q-06 — semantic router dùng sai đại lượng làm confidence.**
`SemanticPrediction.route_decision:48` lấy `nearest_similarity`, tức độ giống với
**một** láng giềng gần nhất, chứ không lấy `vote_margin` hay `vote_scores[top]`.
Truy vấn có 9 láng giềng chia đều ba nhãn vẫn nhận confidence cao nếu láng giềng
số 1 rất gần. Confidence này chảy thẳng vào `RouteDecision.confidence` và vào
metadata/audit. Đề xuất: dùng `vote_scores[top]` hoặc tích hai đại lượng, và ghi
lại lựa chọn trong báo cáo. {code}

**Q-07 — hai miền hợp lệ cho `oos_distance_threshold`.**
`SemanticRouter.__init__:85` chấp nhận `[0, 2]` (đúng toán học cho cosine
distance); `config.py:129-137` chỉ cho `[0, 1]`. Lớp chấp nhận giá trị mà
`Settings` từ chối. Đã ghi ở `src.config`, nay xác nhận từ phía tiêu thụ. {code}

**Q-08 — cache semantic router gắn với đường dẫn tuyệt đối.**
`_cache_metadata:343` đưa `str(self.train_path.resolve())` vào metadata so sánh.
Đổi thư mục repo → cache bị coi là khác → encode lại toàn tập lúc khởi động.
Không được ghi ở đâu. {code}

**Q-09 — `RouteDecision.metadata` báo cáo intent thay cho turn_type.**
`intent_router.py:52`: `self.turn_type if self.turn_type != "answer" else
self.primary_intent`. Chỉ một nhánh (`crisis_signal`) từng đặt `turn_type`. Log
và audit vì thế không phân biệt được "turn_type là advise" với "turn_type chưa
bao giờ được đặt". {code}

**Q-10 — cờ `product_safety_check` bật trên mọi tin nhắn có dấu `+`.**
`_SAFETY_PRODUCT_TERMS` chứa `"+"`, và `_contains_product_safety_term` chỉ dùng
ranh giới từ cho `{aha, bha, bpo}`, còn lại khớp chuỗi con. Docstring nói ngược
lại. Cờ này đi vào `chat/_safety` và `prompt_builder`. {code}

**Q-11 — `_has_any_clinical_fact` mang khiếm khuyết đã biết và chưa sửa.**
Nó `any()` trên `clinical.inflammation_level`, trường luôn truthy sau
`fold_history_facts` (`src.chat.session` Q-10). Comment tại call site
(`intent_router:~618`) đã biết và **né** bằng cách không dùng hàm này ở nhánh
cuối. Nhưng nhánh `contextual_personal_advice` (`:~600`) **vẫn** dùng nó. Ở đó nó
đi kèm `is_advice_question` nên hậu quả hẹp hơn, không phải không có. {code}

**Q-12 — bảng regex của `rule_normalizer` không compile sẵn.** 13 bảng ~950 dòng
lưu regex ở dạng **chuỗi**, `_has` compile qua cache nội bộ của module `re`
(512 entry). Số pattern riêng biệt vượt xa 512 → đuổi cache và compile lại nhiều
lần mỗi request. Lỗi cú pháp regex cũng chỉ nổ lúc chạy, không lúc import. Sửa
rẻ: compile sẵn khi dựng bảng, như `_FOOTER_PATTERNS` của `rag/chunker.py` đã làm. {code}

**Q-13 — `crisis_signal` xếp sau bốn nhánh knowledge trong `_rule_decision`.**
Thứ tự nhánh: short_followup → urgent_personal_case → knowledge_ranking →
product/food/mechanism → general_comparison → **crisis_signal** → … Một câu vừa
mang tín hiệu khủng hoảng vừa chứa `"là gì"`/`"tại sao"` sẽ ra `knowledge` và
**không** vào `safety_clarify`. Đây là tầng 3, chỉ chạy khi Ollama chết — tức
đúng lúc hệ đang yếu nhất. Cần quyết: đẩy `crisis_signal` lên ngay sau
`urgent_personal_case`. {code}

**Q-14 — `route_intent` dựng một `Settings()` mới mỗi lần gọi.**
`intent_router.py:~651`: `from ...config import Settings as _S; _S().route_min_confidence`.
Mỗi lời gọi đọc lại `.env` từ đĩa và chạy lại 6 validator. Nó **không** dùng
singleton `settings`, và **không** dùng tham số `settings` được truyền vào chính
hàm. Sửa một dòng: đọc từ singleton, hoặc dùng tham số. {code}

**Q-15 — luật hạ cấp confidence trong `route_intent` là nhánh chết.**
Điều kiện `decision.confidence < route_min_confidence` với
`route_min_confidence = 0.55`. Liệt kê đủ 11 giá trị confidence mà
`_rule_decision` có thể trả: 0.92, 0.90, 0.86, 0.84, 0.82, 0.80, 0.75, 0.72,
0.70, 0.68, **0.58**. Không giá trị nào dưới 0.55, nên `clarify` vì thiếu tự tin
**chưa bao giờ chạy**. Hai cách sửa: nâng ngưỡng lên 0.60 (khi đó nhánh
`low_signal_default` sẽ hạ cấp), hoặc hạ confidence của nhánh đó xuống dưới 0.55.
Phải chọn có chủ đích — hiện tại là một cơ chế an toàn tồn tại trên giấy. {code}

**Q-16 — `EXTRACTOR_MODE=rule` không đạt được ở chế độ unified.**
`di.py:162-163` ép `settings.extractor_mode = "llm"`. Hai file legacy
(`rule_extractor.py`, `rule_normalizer.py`, tổng **2.381 dòng**) tự khai là
"live fallback when `EXTRACTOR_MODE=rule` or the LLM extractor fails" — vế đầu
không còn đạt được, nên đường sống duy nhất là intaker hỏng. Đây là số dòng lớn
nhất của module và cần một câu trả lời rõ trong báo cáo: nó là fallback thật hay
là di sản. {code}

**Q-17 — `_VOCAB_FUZZY_REVIEW = 0.82` không có tác dụng.**
Nó được truyền làm `review` cho `find_in_text`, nhưng hàm đó vứt mọi hit dưới
`accept` ở dòng return (`src.utils` Q-02). Thứ thật sự lọc là `accept = 0.86`.
Một hằng số được tinh chỉnh và ghi chú hai dòng cho một cổng không tồn tại. Sửa
`find_in_text` thì hằng này sống lại — nên hai việc phải làm cùng nhau. {code}

**Q-18 — `_NEGATION_RE` trong `rule_extractor` có 0 caller.**
`rule_extractor.py:81` định nghĩa nó, comment `:80` xếp nó cùng nhóm "điều chỉnh
ngữ cảnh", nhưng `_context_adjust` chỉ dùng `_QUESTION_RE` và `_PRONOUN_RE`. Nghĩa
là câu phủ định **không** bị trừ confidence. {code}

**Q-19 — hai biểu diễn cho `is_pregnant`, và cả hai đều đặt được `False` từ một
từ khoá.** `rule_extractor._bool_from_patterns` trả ba trạng thái (True/False/
none) với confidence 0.90; `rule_normalizer._contains_positive` trả bool hai
trạng thái. Cả hai kiểm phủ định **không có phạm vi**, nên "chị tôi không mang
thai" cho ra `False`. `chat/session/view.py:68` xếp `is_pregnant` vào
`_UNGATED_FIELDS` (ngưỡng 0.0) nên `False` đó luôn vào `confirmed_profile`, và
`medication_safety_refusal` đọc chính trường đó. Đây là cùng hướng hỏng mà
`fold.py` đã xoá 17 keyword để tránh, với lý do ghi rõ "rule không bao giờ được
tự hạ xuống False". Cần thống nhất một quy tắc cho cả ba file. {code+comment}

**Q-20 — hai định nghĩa `_active_inflammatory_lesions` lệch nhau.**
`rule_normalizer:1832` `_ACTIVE_INFLAMMATORY_LESIONS` = 5 phần tử (có `"other"`);
`rule_normalizer:1730` biến cục bộ cùng ý nghĩa = 4 phần tử (không có `"other"`).
Bản 5 phần tử dùng để **loại lesion khi mụn đã khỏi**, bản 4 phần tử dùng để
**suy inflammation**. Vì `"other"` là nhãn bắt-tất khớp mọi chữ "mụn", chênh lệch
này có hậu quả thật. Ngoài ra `_sequelae_lesions` (`:1731`) được gán và không
dùng. {code}

**Q-21 — xem Q-12** (gộp: cùng nguyên nhân, cùng cách sửa).

**Q-22 — `canonical_ingredients` và `current_products` bất đồng về cùng một chất.**
`_extract_products` đòi ngữ cảnh đang-dùng (`_has_product_use_context`, 12 nhánh);
`_extract_canonical_ingredients._in_use` đường (b) chỉ đòi **không bị phủ định**.
Nên "nghe nói BHA tốt" cho `current_products=[]` nhưng
`canonical_ingredients=['salicylic_acid']`. Hai trường của cùng một
`AcneClinicalInput` nói hai điều khác nhau, và trường thứ hai là trường mà
guardrail hoạt chất đọc. {code}

**Q-23 — `concentrations` không gắn với hoạt chất nào.**
`_extract_concentrations` bắt mọi `<số>%` trong câu và trả list phẳng;
`canonical_ingredients` là list phẳng khác. Không có cặp (chất, nồng độ). Với tư
vấn thuốc bôi thì "tretinoin 0.1%" và "0.025%" là hai lời khuyên khác nhau, còn
schema hiện tại không phân biệt được. Đây là hạn chế thiết kế đáng nêu trong
chương giới hạn của báo cáo. {code}

**Q-24 — `"da"` trong danh sách aspect marker biến câu hỏi thành thuốc đang dùng.**
`_has_medication_use_context:~1424` và `_has_product_use_context:~1224` đều chứa
`da` (dạng không dấu của `đã`), trùng với từ "da" — từ phổ biến nhất trong miền
này. Nhánh xác nhận đó `return True` **trước** nhánh loại trừ câu hỏi. Đo trên
chính hàm: `"da em bị mụn, tretinoin có tốt không?"` → True (sai), trong khi
`"tretinoin có tốt không?"` → False (đúng); `"da mình dầu, isotretinoin là gì vậy
ạ"` → True (sai). Chuỗi hệ quả: `UserContext.medications` sai →
`confirmed_profile` sai → `medication_safety_refusal` (cổng an toàn tất định) chạy
trên dữ liệu sai. **Đây là lỗi nghiêm trọng nhất của module.** Hai cách sửa:
(a) bỏ `da` khỏi danh sách và dựa vào `dang|da\s+(?:dùng|bôi|uống)` có tân ngữ;
(b) đảo thứ tự — chạy nhánh loại trừ câu hỏi **trước** nhánh xác nhận aspect.
Cách (b) rẻ hơn và giữ được `"da bôi tretinoin 3 tuần"`. {code}

**Q-25 — `treatment_goals` bị vứt khi không có tín hiệu lâm sàng nào khác.**
Cổng dựng `clinical` ở `normalize_chat_message:~1958` không liệt kê
`treatment_goals`. Đo được: `"muốn trị dứt điểm"` → `goals=['clear_acne']`,
lesions rỗng → `clinical=None` → mục tiêu mất. Ba câu tôi thử có chữ "mụn" đều
thoát nhờ nhãn bắt-tất `"other"`, nên lỗi hiếm chứ không phải không xảy ra. Sửa:
thêm `treatment_goals` vào điều kiện. {code}

---

## §6 — Tự kiểm (Bước 4)

- Khối khai báo ở Bước 0: **170**.
- Tiêu đề `### [x]` đếm được: **127**. Chênh lệch là do **ba tiêu đề gộp**, mỗi
  cái nói rõ số khối nó phủ ngay trong tiêu đề:
  - `intent_router` — **18 bảng term** dưới 1 tiêu đề → +17
  - `rule_normalizer` — **13 bảng term** dưới 1 tiêu đề → +12
  - `rule_normalizer` — **15 hằng phụ trợ** dưới 1 tiêu đề → +14
  - Kiểm: 127 + 17 + 12 + 14 = **170**. Khớp.
- Mục: 170 × 8 = **1.360**. Trong đó 46 khối thuộc ba nhóm nén có khai báo §1
  (46 × 4 = 184 mục phát biểu một lần ở §1, 46 × 4 = 184 mục khai riêng trong ba
  tiêu đề gộp), 124 khối còn lại viết đủ 8 mục tại chỗ (992 mục).
  Kiểm: 184 + 184 + 992 = **1.360**. Khớp.

**Bốn khẳng định đo bằng chạy thật, không đọc mắt:**
1. `_has_medication_use_context` trên 6 câu — bảng kết quả ở khối tương ứng (Q-24).
2. `_extract_lesions("em bị mụn, muốn tư vấn cách trị")` → `['other']`.
3. `_extract_treatment_goals("muốn trị dứt điểm")` → `['clear_acne']` với
   lesions rỗng → `clinical` bị bỏ (Q-25).
4. Liệt kê đủ 11 giá trị confidence của `_rule_decision` để chứng minh nhánh hạ
   cấp trong `route_intent` là chết (Q-15).

**Một nghi ngờ đã kiểm và BÁC BỎ:** tôi thấy `rule_normalizer:695` hiển thị như
byte hỏng (`b???t\s*mụn`) trên terminal và định ghi là regex hỏng. Đọc lại bằng
`python -c` với `encoding="utf-8"` cho ra `'|bớt\\s*mụn|bot\\s*mun'` — chuỗi
đúng, lỗi nằm ở terminal của tôi. Không có byte hỏng trong file.
