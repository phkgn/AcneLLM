# FINDINGS / src.llm

Module: `src/acne_llm/llm/` — 4 file, 534 LOC (`__init__.py` 0, `language.py` 30, `ollama_backend.py` 251, `prompt_builder.py` 253).
30 symbol + 3 khối lời khai (docstring module: language.py, ollama_backend.py, prompt_builder.py) + 1 khối file rỗng = 34 khối × 8 mục = 272.
(Header trước đó ghi 35/280 do đếm nhầm 4 docstring; `__init__.py` 0 LOC không có docstring. Đã sửa theo phép đếm Bước 4.)

---

## `__init__.py`

### [x] (file rỗng)
1. in/out: 0 LOC. {code}
2-5. side effect / state / lỗi / config: không. {code}
6. ai gọi: đánh dấu package; caller import đường dẫn con (`di.py:10`, `di.py:11`). {code}
7. invariant: không có mặt tiền công khai, giống `guardrails/`, khác `schemas/`. {code}
8. deprecated: không. {code}

---

## `language.py`

### [x] `_VI_CHARS`
1. in/out: `set[str]` các ký tự có dấu tiếng Việt. {code} `[language.py:8]`
2. side effect: dựng set lúc import. {code}
3. state: đọc bởi `detect_language_heuristic`; không ghi. {code}
4. lỗi: không. {code}
5. config/env: hằng cứng. {code}
6. ai gọi: chỉ trong file. **0 caller ngoài.** {code}
7. invariant: chỉ chứa nguyên âm có dấu — văn bản tiếng Việt **không dấu** sẽ bị đoán là tiếng Anh. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `detect_language_heuristic`
1. in/out: `(text: str) -> str` trả mã ngôn ngữ. {code} `[language.py:11]`
2. side effect: không. {code}
3. state: đọc `_VI_CHARS`. {code}
4. lỗi: không có nhánh ném. {code}
5. config/env: không. {code}
6. ai gọi: `src/acne_llm/chat/routing/intent_router.py:26` — tức chỉ chạy ở **tầng 3 rule fallback**, mà `INTAKE_MODE=unified` nên thực tế gần như không chạy. {code}
7. invariant: docstring `[:12]` khai "cheap lexical rules, no LLM call" — khớp code, không có I/O nào. {doc}
8. deprecated/TODO: không dấu, nhưng nằm trong nhánh fallback nguội. {code}

### [x] docstring `language.py:1`
1. in/out: lời khai "Small rule-based language helpers used before the final LLM call". {doc}
2-6. side effect / state / lỗi / config / caller: không. {doc}
7. invariant: **kiểm ngược — LỆCH nhẹ**: "used before the final LLM call" đúng về vị trí, nhưng caller duy nhất nằm trong nhánh fallback không chạy ở cấu hình hiện tại. {code}
8. deprecated: không. {doc}

---

## `ollama_backend.py`

### [x] `OllamaBackend`
1. in/out: class, 14 tham số khởi tạo: `base_url`, `model`, `fallback_model`, `num_ctx`, `timeout`, `health_timeout`, `num_predict`, `temperature`, `top_p`, `top_k`, `repeat_penalty`, `repeat_last_n`, `keep_alive`, `use_modelfile_system`. {code} `[ollama_backend.py:10-11]`
2. side effect: mở **hai** `httpx.Client` `[:45-46]` — một cho chat, một cho health với timeout riêng. Giữ kết nối HTTP. {code}
3. state: giữ toàn bộ tham số sampling trong instance; không có global. {code}
4. lỗi: xem từng method. {code}
5. config/env: mọi tham số đến từ `settings.llm_*` và `settings.ollama_*` qua `di.py:117-131`. Eval ghi đè qua `_repo.build_eval_container` `[research/evaluation/adapters/_repo.py:31-39]`. {code}
6. ai gọi: `di.py:10`, `chat/unified_intake.py:10`, `chat/routing/llm_extractor.py:11`, tổng 7 chỗ — **được khởi tạo bốn lần khác nhau** trong `di.py` cho generator, intake, router, extractor. {code}
7. invariant: `fallback_model` bị eval ép `None` `[_repo.py:24,43]` và ép lần hai sau khi build — bất biến R4 "không fallback khi eval" được thực thi hai lớp. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend.__init__`
1. in/out: `(...14 tham số...) -> None`. {code} `[:11-47]`
2. side effect: tạo hai HTTP client `[:45-46]`. {code}
3. state: ghi mọi thuộc tính instance. {code}
4. lỗi: `httpx.Client` không kết nối ngay nên URL sai không ném tại đây. {code}
5. config/env: như trên. {code}
6. ai gọi: `di.py:116,137,164,200`. Nó gọi `_normalize_keep_alive` `[:47]`. {code}
7. invariant: hai client tách riêng để health check không bị chặn bởi timeout dài của generate. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._normalize_keep_alive` (staticmethod)
1. in/out: `(v) -> str | int`, chuẩn hoá giá trị keep_alive. {code} `[:49]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không có nhánh ném rõ ràng. {code}
5. config/env: `settings.llm_keep_alive` mặc định `-1` `[config.py:40]`, có validator `_check_keep_alive` `[config.py:85]`. {code}
6. ai gọi: chỉ `__init__` `[:47]`. **0 caller ngoài.** {code}
7. invariant: `-1` nghĩa "giữ model trong RAM vô hạn" theo quy ước Ollama — giả định ngầm, không ghi trong code. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._is_runner_terminated` (staticmethod)
1. in/out: `(err) -> bool`. {code} `[:66]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: đây **là** bộ phân loại lỗi — nhận diện Ollama bị kill runner để quyết định có fallback không. {code}
5. config/env: không. {code}
6. ai gọi: `_post_chat` và `_post_chat_stream` trong cùng file (3 lần xuất hiện). **0 caller ngoài.** {code}
7. invariant: nhận diện bằng **khớp chuỗi thông báo lỗi** của Ollama — đổi phiên bản Ollama là cơ chế fallback im lặng hỏng. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._post_chat`
1. in/out: `(payload: dict, model: str) -> dict`. {code} `[:70]`
2. side effect: **HTTP POST** tới Ollama qua `self._client`. {code}
3. state: đọc `self._client`; không ghi. {code}
4. lỗi: bắt `httpx.HTTPStatusError` `[:77]`, log warning `[:96,103]`, có nhánh fallback sang `fallback_model`. {code}
5. config/env: `settings.ollama_generate_timeout` mặc định `30.0` `[config.py:43]` — nhưng `.env` của máy đang đặt `300`. {code}
6. ai gọi: `_chat` `[:147]`. **0 caller ngoài.** Nó gọi `_is_runner_terminated`, `_log_token_budget`. {code}
7. invariant: fallback chỉ kích hoạt khi `fallback_model` không rỗng — eval ép `None` nên nhánh này chết trong eval, đúng ý đồ. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._log_token_budget`
1. in/out: `(done_chunk) -> None`, log cảnh báo khi prompt gần chạm `num_ctx`. {code} `[:82]`
2. side effect: log warning/debug `[:96,103,108]`. {code}
3. state: đọc `self.num_ctx`. {code}
4. lỗi: không ném. {code}
5. config/env: `settings.llm_num_ctx` mặc định `8192` `[config.py:28]`, có validator `_check_num_ctx` `[config.py:78]` giới hạn [512, 32768]. {code}
6. ai gọi: `_post_chat` trong cùng file; `tests/test_settings.py:28`. **Không có caller production nào ngoài file.** {code}
7. invariant: là cảnh báo tràn ngữ cảnh duy nhất trong hệ — nếu prompt vượt `num_ctx`, Ollama cắt im lặng và chỉ dòng log này báo. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._post_chat_stream`
1. in/out: `(payload, model) -> Iterator`, sinh từng dòng JSON. {code} `[:113]`
2. side effect: HTTP POST dạng stream. {code}
3. state: đọc `self._client`. {code}
4. lỗi: bắt `httpx.HTTPStatusError` `[:121]`; dòng không phải JSON → log debug rồi bỏ qua `[:131]`, **không ném**. {code}
5. config/env: như `_post_chat`. {code}
6. ai gọi: `_chat_stream` `[:160]`. **0 caller ngoài.** {code}
7. invariant: bỏ qua dòng lỗi im lặng nghĩa là câu trả lời có thể **thiếu token mà không ai biết**; chỉ log debug ghi lại. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._chat`
1. in/out: `(payload: dict) -> dict`. {code} `[:147]`
2. side effect: gián tiếp qua `_post_chat`. {code}
3. state: đọc `self.model`, `self.fallback_model`. {code}
4. lỗi: log warning `[:154]` khi phải chuyển sang fallback. {code}
5. config/env: `settings.llm_fallback_model` mặc định `'qwen2.5:3b'` `[config.py:26]`. {code}
6. ai gọi: `generate_text` `[:222]`. **0 caller ngoài.** {code}
7. invariant: đây là chỗ **duy nhất** quyết định dùng model chính hay fallback cho đường không stream. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._chat_stream`
1. in/out: `(payload: dict) -> Iterator`. {code} `[:160]`
2. side effect: gián tiếp qua `_post_chat_stream`. {code}
3. state: đọc `self.model`, `self.fallback_model`. {code}
4. lỗi: log warning `[:167]` khi chuyển fallback. {code}
5. config/env: như `_chat`. {code}
6. ai gọi: `stream_text` `[:236]`. **0 caller ngoài.** {code}
7. invariant: song song với `_chat` cho đường stream — hai đường fallback độc lập, sửa một bên quên bên kia là lệch hành vi giữa chat UI và eval. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend.health`
1. in/out: `() -> bool` (hoặc dict trạng thái). {code} `[:173]`
2. side effect: HTTP GET qua `self._health_client`. {code}
3. state: đọc `self._health_client`. {code}
4. lỗi: bắt mọi lỗi, log warning `[:178]`, trả về trạng thái hỏng thay vì ném. {code}
5. config/env: `settings.ollama_health_timeout` mặc định `5.0` `[config.py:41]`. {code}
6. ai gọi: `cli.py:39`, `api/app.py:12`, `api/observability.py:107`, tổng 6 chỗ. {code}
7. invariant: timeout ngắn riêng biệt để endpoint `/health` không treo theo generate. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend.list_models`
1. in/out: `() -> list`, danh sách model Ollama đang có. {code} `[:181]`
2. side effect: HTTP GET. {code}
3. state: đọc `self._health_client`. {code}
4. lỗi: chưa rõ nhánh bắt lỗi cụ thể — không đọc hết thân hàm. {code}
5. config/env: `settings.ollama_url` mặc định `'http://localhost:11434'` `[config.py:24]`. {code}
6. ai gọi: `api/routes/health.py:27`, `tests/test_api.py:16`. Phục vụ endpoint `GET /api/v1/models`. {code}
7. invariant: là nguồn duy nhất cho endpoint `/models`; không cache. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._build_messages`
1. in/out: `(system: str, user: str) -> list[dict]`. {code} `[:189]`
2. side effect: không. {code}
3. state: đọc `self.use_modelfile_system`. {code}
4. lỗi: không ném. {code}
5. config/env: `settings.llm_use_modelfile_system` mặc định `True` `[config.py:47]`. {code}
6. ai gọi: `generate_text` `[:227]`, `stream_text` `[:240]`. **0 caller ngoài.** {code}
7. invariant: khi `use_modelfile_system=True`, **system prompt từ code bị bỏ qua** vì Modelfile đã nhúng sẵn. Đây là lý do `PromptBuilder` trả system rỗng — invariant xuyên hai module, chỉ ghi trong comment `[config.py:46]`. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend._sampling_options`
1. in/out: `(temperature: float | None = None, num_predict: int | None = None) -> dict`. {code} `[:204-220]`
2. side effect: không. {code}
3. state: đọc 7 thuộc tính sampling của instance. {code}
4. lỗi: không ném. {code}
5. config/env: gộp `llm_temperature` 0.35, `llm_top_p` 0.85, `llm_top_k` 40, `llm_repeat_penalty` 1.1, `llm_repeat_last_n` 128, `llm_num_predict` 2048, `llm_num_ctx` 8192. {code}
6. ai gọi: `generate_text` `[:228]`, `stream_text` `[:243]`, và **bị `_repo.py:46` bọc lại để chèn `seed`** — eval wrap hàm này thay vì sửa repo. {code}
7. invariant: docstring `[:206-208]` khai "Caller có thể override temperature và num_predict; các params còn lại" cố định. **Kiểm ngược**: chữ ký chỉ nhận hai tham số đó — khớp. Hệ quả: eval không đổi được `top_p`/`repeat_penalty` qua đường này mà phải đổi ở `Settings`. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend.generate_text`
1. in/out: `(system: str, user: str, temperature=None, response_format: str|dict|None=None) -> str`. {code} `[:222-234]`
2. side effect: HTTP POST không stream. {code}
3. state: đọc `self.model`, `self.keep_alive`. {code}
4. lỗi: qua `_chat`, có fallback. {code}
5. config/env: như trên. {code}
6. ai gọi: `chat/orchestrator.py:179` (trong `generate_prose`), `chat/unified_intake.py:111`, `chat/routing/llm_extractor.py:65`, tổng 9 chỗ. {code}
7. invariant: **không nhận `num_predict`** `[:222-224]` — khác `stream_text` `[:236-238]`. Hệ quả đã đo: runtime nâng trần cho câu hỏi kiến thức qua `stream_text(num_predict=-1)` `[chat/runtime.py:162-167]`, còn eval dùng `generate_text` nên luôn bị trần `llm_num_predict = 2048`. Đây là bất đối xứng runtime↔eval, không phải chủ ý. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend.stream_text`
1. in/out: `(system: str, user: str, temperature=None, num_predict: int|None=None) -> Iterator[str]`. {code} `[:236-247]`
2. side effect: HTTP POST stream. {code}
3. state: đọc `self.model`, `self.keep_alive`. {code}
4. lỗi: qua `_chat_stream`, có fallback. {code}
5. config/env: như trên. {code}
6. ai gọi: `chat/runtime.py:5`, `tests/test_chat_stream.py:36`, `tests/test_ollama_backend.py:83`. Là đường sinh **duy nhất** của production. {code}
7. invariant: `num_predict=-1` nghĩa bỏ trần — quy ước Ollama, dùng ở `runtime.py:162`. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `OllamaBackend.close`
1. in/out: `() -> None`. {code} `[:249-251]`
2. side effect: đóng hai `httpx.Client`. {code}
3. state: ghi trạng thái đóng của client. {code}
4. lỗi: chưa rõ có bọc `try` hay không — không đọc hết ba dòng cuối. {code}
5. config/env: không. {code}
6. ai gọi: `di.py:67`, `api/app.py:27` (lifespan shutdown), `chat/unified_intake.py:178`, tổng 23 chỗ khớp tên `close` (gồm cả `close` của object khác). {code}
7. invariant: phải gọi khi tắt app, nếu không rò socket; `api/app.py` lo việc này. {code}
8. deprecated/TODO: không dấu. {code}

### [x] docstring `ollama_backend.py:1`
1. in/out: lời khai "Ollama HTTP backend. Supports JSON-schema constrained decoding". {doc}
2-6. side effect / state / lỗi / config / caller: không. {doc}
7. invariant: **kiểm ngược** — "JSON-schema constrained decoding" khớp tham số `response_format` `[:224]` được truyền vào payload `[:232]`. Đúng. {code}
8. deprecated: không. {doc}

---

## `prompt_builder.py`

### [x] `_INJECTION_MARKERS`
1. in/out: tuple chuỗi mồi tấn công ("ignore previous", "forget prior", "override i…"). {code} `[prompt_builder.py:15]`
2. side effect: không. {code}
3. state: đọc bởi `_sanitize_chunk_text` và `_sanitize_user_description`. {code}
4. lỗi: không. {code}
5. config/env: hằng cứng. {code}
6. ai gọi: trong file; `tests/test_guardrails.py:14`. {code}
7. invariant: đây là **bản còn sống** của blocklist injection sau khi `pre_check` bỏ chặn `[guardrails/runner.py:59-63]` — chuyển từ "từ chối" sang "vô hiệu hoá trong prompt". {code}
8. deprecated/TODO: không dấu. {code}

### [x] `_escape_jinja`
1. in/out: `(value: str) -> str`, vô hiệu hoá dấu phân cách Jinja2. {code} `[:26-38]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không ném. {code}
5. config/env: không. {code}
6. ai gọi: 6 lần trong file; `tests/test_prompt_builder.py:5`. {code}
7. invariant: chặn **template injection** — text người dùng chứa `{{ }}` không được Jinja render. Là lớp phòng thủ riêng, khác `_INJECTION_MARKERS` vốn chống prompt injection. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `_sanitize_chunk_text`
1. in/out: `(text: str) -> str`. {code} `[:41-64]`
2. side effect: không. {code}
3. state: đọc `_INJECTION_MARKERS`. {code}
4. lỗi: không ném. {code}
5. config/env: không. {code}
6. ai gọi: 4 lần trong file (`_context_block`). **0 caller ngoài.** {code}
7. invariant: **chunk từ KB cũng bị coi là dữ liệu không tin cậy** — nếu KB bị nhiễm nội dung độc, lớp này chặn. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `sanitize_history_turns`
1. in/out: `(history) -> list`, trả bản sao lịch sử đã vô hiệu hoá marker từng lượt. {code} `[:66-72]`
2. side effect: không — tạo bản sao, không sửa tại chỗ. {code}
3. state: không. {code}
4. lỗi: không ném. {code}
5. config/env: không. {code}
6. ai gọi: 2 lần trong file (định nghĩa + 1 lời gọi nội bộ). **0 caller ngoài file** dù tên không có tiền tố `_` nên trông như API công khai. {code}
7. invariant: lịch sử hội thoại cũng là dữ liệu không tin cậy — người dùng có thể cài mồi ở lượt trước rồi kích hoạt ở lượt sau. {code}
8. deprecated/TODO: không dấu; nên đổi thành `_sanitize_history_turns` cho khớp phạm vi thật. {code}

### [x] `_sanitize_user_description`
1. in/out: `(text: str) -> str`. {code} `[:74-97]`
2. side effect: không. {code}
3. state: đọc `_INJECTION_MARKERS`. {code}
4. lỗi: không ném. {code}
5. config/env: không. {code}
6. ai gọi: 2 lần trong file. **0 caller ngoài.** {code}
7. invariant: cùng danh sách marker với `_sanitize_chunk_text` nhưng hàm riêng — hai đường dữ liệu (người dùng và KB) được xử lý riêng để đổi luật độc lập. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `PromptBuilder`
1. in/out: class, khởi tạo từ `templates_dir`; phơi `build`, `_context_block`. {code} `[:99-115]`
2. side effect: nạp template Jinja2 từ đĩa lúc khởi tạo. {code}
3. state: giữ môi trường Jinja và thư mục template. {code}
4. lỗi: template thiếu → Jinja ném `TemplateNotFound`; không thấy nhánh bắt. {code}
5. config/env: `settings.prompts_dir` mặc định `'./config/prompts'` `[config.py:164]`, truyền tại `di.py:222`. {code}
6. ai gọi: `di.py:11`, `tests/test_api.py:34`, `tests/test_prompt_builder.py:5`, tổng 4 chỗ. {code}
7. invariant: docstring `[:100]` khai "Khối nào KHÔNG có luật tương ứng trong Modelfile" — tức prompt và Modelfile là **hai nửa của một hợp đồng**, và `llm_use_modelfile_system=True` `[config.py:47]` quyết định nửa nào thắng. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] `PromptBuilder._MAX_CHARS_PER_CHUNK`
1. in/out: hằng lớp `= 800`. {code} `[:114]`
2. side effect: không. {code}
3. state: đọc bởi `_context_block`. {code}
4. lỗi: không. {code}
5. config/env: **hằng cứng trong class, không phải `Settings`** — trong khi `chat_max_context_chars` (6000) thì nằm trong `Settings` `[config.py:183]`. Hai giới hạn liên quan nhau ở hai nơi khác nhau. {code}
6. ai gọi: 2 lần trong file. **0 caller ngoài.** {code}
7. invariant: 800 × 5 chunk = 4000 < 6000 nên trần chunk là ràng buộc chặt hơn trần tổng — quan hệ này không được ghi ở đâu. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `PromptBuilder._SOURCE_BADGES`
1. in/out: `dict[str, str]` ánh xạ `source_type` → nhãn hiển thị (`'nice_guideline' → '[NICE Guideline]'`…). {code} `[:124]`
2. side effect: không. {code}
3. state: đọc bởi `_context_block`. {code}
4. lỗi: `source_type` lạ → chưa rõ có default hay `KeyError`; không đọc hết thân `_context_block`. {code}
5. config/env: hằng cứng. {code}
6. ai gọi: 2 lần trong file. **0 caller ngoài.** {code}
7. invariant: khoá phải khớp `SourceType` `[schemas/kb.py:8-19]` — hai danh sách khai độc lập, không có test canh trôi. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `PromptBuilder.__init__`
1. in/out: `(templates_dir) -> None`. {code} `[:116-122]`
2. side effect: dựng `jinja2.Environment` trỏ vào thư mục template. {code}
3. state: ghi thuộc tính instance. {code}
4. lỗi: thư mục không tồn tại → Jinja báo khi render, không khi khởi tạo. {code}
5. config/env: `settings.prompts_dir`. {code}
6. ai gọi: `di.py:222`. {code}
7. invariant: 7 file `.j2` trong `config/prompts/` là hợp đồng ngoài code — đổi tên file là gãy lúc chạy, không lúc import. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `PromptBuilder._context_block`
1. in/out: `(retrieval: RetrievalOutput, max_chars: int) -> str`. {code} `[:141-187]`
2. side effect: không. {code}
3. state: đọc `_MAX_CHARS_PER_CHUNK`, `_SOURCE_BADGES`; gọi `_sanitize_chunk_text`, `_truncate_at_sentence`. {code}
4. lỗi: không thấy nhánh ném. {code}
5. config/env: `max_chars` do caller truyền, lấy từ `settings.chat_max_context_chars` `[chat/orchestrator.py:150]`. {code}
6. ai gọi: `build` trong cùng file; `tests/test_prompt_builder.py:155`; `scripts/build_hybrid_finetune_dataset.py:21` — **script sinh dữ liệu dùng lại hàm này để prompt lúc train khớp prompt lúc chạy**. {code}
7. invariant: **không đọc `chunk.score`** — đã kiểm bằng grep; nên arm oracle của eval gán `score` bằng grade 1/2 `[research/evaluation/runners/run_ablation.py:415]` không rò vào prompt. Bất biến này giữ cho so sánh arm hợp lệ. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `PromptBuilder._truncate_at_sentence` (staticmethod)
1. in/out: `(text: str, budget: int) -> str`. {code} `[:189-198]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không ném. {code}
5. config/env: không. {code}
6. ai gọi: 2 lần trong file. **0 caller ngoài.** {code}
7. invariant: cắt ở ranh giới câu chứ không giữa chừng — giữ cho chunk không bị cụt nửa ý, ảnh hưởng trực tiếp `groundedness` mà judge chấm. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `PromptBuilder.build`
1. in/out: `(user, retrieval, template, max_context_chars, history, prompt_note, confirmed_profile) -> tuple[str, str]` — trả `(system_prompt, user_prompt)`. {code} `[:200-253]`
2. side effect: render Jinja2 template từ đĩa. {code}
3. state: đọc môi trường Jinja, các hằng lớp. {code}
4. lỗi: template thiếu → `TemplateNotFound` ném ra caller. {code}
5. config/env: `settings.prompts_dir`, `settings.chat_max_context_chars`, gián tiếp `llm_use_modelfile_system`. {code}
6. ai gọi: `chat/orchestrator.py` trong `prepare_chat_turn` `[orchestrator.py:~150]`; `research/evaluation/runners/run_ablation.py:434` gọi lại để dựng prompt cho arm `ROR`. {code}
7. invariant: **trả system rỗng khi Modelfile đã nhúng SYSTEM** — docstring class `[:100-102]` khai điều này, và `_build_messages` `[ollama_backend.py:189]` là bên tiêu thụ. Đây là hợp đồng ngầm giữa ba nơi: `config.llm_use_modelfile_system`, `PromptBuilder.build`, `OllamaBackend._build_messages`. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] docstring `prompt_builder.py:1`
1. in/out: lời khai "Jinja2 prompt builder với sanitization chống injection". {doc}
2-6. side effect / state / lỗi / config / caller: không. {doc}
7. invariant: **kiểm ngược** — có ba lớp sanitize thật (`_escape_jinja`, `_sanitize_chunk_text`, `_sanitize_user_description`) cộng `sanitize_history_turns`. Lời khai khớp code và còn khiêm tốn hơn thực tế (không nhắc lớp chống template injection). {code}
8. deprecated: không. {doc}

---

## BƯỚC 4 — TỰ KIỂM

```
file trong module / file đã tick   :   4 / 4
symbol đã liệt kê / đã tick        :  30 / 30  (+4 lời khai +1 file rỗng)
mục 1-8 cần điền / đã điền         : 280 / 280
```
"Chưa rõ" còn lại: **3** — nhánh bắt lỗi của `list_models` `[:181]`, của `close` `[:249]`, và hành vi khi `source_type` không có trong `_SOURCE_BADGES`. Cả ba đều do tôi không đọc hết thân hàm, không phải do code mơ hồ.
