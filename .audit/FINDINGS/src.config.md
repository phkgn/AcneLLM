# FINDINGS / src.config

Module: `src/acne_llm/config.py` — 1 file, 288 LOC.

**Phép đếm khối (Bước 0):**
- 73 field cấu hình — đếm bằng regex `^    [a-z][a-z0-9_]*\s*:\s*[^=\n]+=` chạy trên chính file, ra 73; danh sách đầy đủ ở §4
- 1 `model_config` (gán không annotation nên không lọt regex trên)
- 1 `class Settings`
- 6 `@field_validator`
- 1 singleton `settings`
- 1 khối lời khai (docstring module `config.py:1-13`)

→ **83 khối × 8 mục = 664 mục.**

---

## §1 — NÉN CÓ KHAI BÁO (bắt buộc đọc trước §4)

73 field đều là field khai báo của một lớp `pydantic_settings.BaseSettings`.
Với **mọi** field trong nhóm này, bốn mục dưới đây là hằng số của **cơ chế**,
không phải của từng field, nên tôi phát biểu một lần ở đây thay vì lặp 73 lần.
Đây là nén **có khai báo**, khác với bỏ sót: phát biểu dưới đây áp cho đúng
73/73 field, và mọi field lệch khỏi nó đều được ghi đè tại chỗ trong §4.

- **Mục 2 — side effect:** không. Field chỉ là khai báo schema; việc đọc `.env`
  và ép kiểu do `BaseSettings.__init__` làm, đúng một lần, tại `config.py:288`
  (`settings = Settings()`). Đọc `settings.<field>` sau đó là đọc thuộc tính
  thuần. {code}
- **Mục 3 — state:** `Settings` **không** đặt `frozen=True`, nên pydantic cho
  phép gán lại. Grep toàn repo (`^\s*settings\.[a-z_]* *=[^=]`) tìm được đúng
  **6 chỗ gán lại**, và một trong số đó nằm trong code chạy thật:
  - `src/acne_llm/di.py:163` — `settings.extractor_mode = "llm"`, ghi đè cấu
    hình của người dùng ngay trong composition root. Xem Q-04.
  - `tests/test_admin_auth.py:29,33,38,44,50` — test tự sửa `admin_api_key` rồi
    khôi phục.
  Ngoài 6 chỗ này, trạng thái = giá trị đóng băng lúc import. {code}
- **Mục 4 — lỗi:** field không tự raise. Lỗi phát sinh ở tầng `Settings()`:
  `ValidationError` nếu ép kiểu thất bại (ví dụ `LLM_NUM_CTX=abc`), hoặc
  `ValueError` từ 6 validator ở §3. Lỗi này xảy ra lúc **import**, không phải
  lúc gọi — nên mọi entry point (`main.py`, runner eval, script) chết ngay ở
  dòng import đầu tiên nếu `.env` sai. {code}
- **Mục 7 — invariant:** `model_config` đặt `extra="ignore"` (`config.py:21`),
  nên biến môi trường **thừa** bị nuốt im lặng, và biến **gõ sai tên** cũng bị
  nuốt im lặng trong khi field giữ default. Đây là invariant có hại đã được xác
  nhận bằng chính lịch sử repo: comment `config.py:190-192` kể lại đúng lỗi đó
  (`chat_min_chunk_score` từng không tồn tại trong khi `_retrieval.py` đọc tên
  này qua `getattr(..., 0.25)` → mọi lần tune đều vô tác dụng). {code+comment}

Mục **1 (in/out), 5 (nguồn cấu hình), 6 (ai gọi), 8 (deprecated)** khai riêng
cho từng field ở §4.

Về **mục 5**: nguồn của mọi field là chuỗi ưu tiên của pydantic-settings — biến
môi trường của tiến trình > `.env` (`env_file=".env"`, `config.py:21`) > default
trong file này. Tên biến môi trường = tên field viết hoa. Mục 5 của từng field
vì vậy ghi **default trong file** và **giá trị `.env` thật** nếu `.env` có đặt.

`.env` thật hiện đặt 17 khoá; 12 khoá trong đó khớp field của `Settings`
(`OLLAMA_URL`, `DEVICE`, `LOG_LEVEL`, `LLM_MODEL`, `INTAKE_MODE`,
`INTAKE_MODEL`, `JUDGE_PROVIDER`, `JUDGE_MODEL`, `CORS_ORIGINS`,
`OLLAMA_GENERATE_TIMEOUT`, `API_KEY`, `ADMIN_API_KEY`). 5 khoá còn lại
(`OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `DATAGEN_API_KEY`, `DEEPSEEK_BASE_URL`,
`DEEPSEEK_MODEL`) **không** phải field của `Settings` — chúng bị `extra="ignore"`
nuốt ở đây và được đọc bởi hệ config khác (`research/evaluation/judges/clients.py:34`,
`research/datagen/config.py:128`, `research/datagen/roledatav2/config.py:142-150`). {code}

---

## §2 — Khối lời khai và khung lớp

### [x] docstring `config.py:1-13`
1. in/out: 13 dòng lời khai, không phải code. {doc}
2. side effect: không. {doc}
3. state: không. {doc}
4. lỗi: không. {doc}
5. config: tự nó là lời khai về layer config. {doc}
6. ai gọi: không ai; `__doc__` không được đọc ở đâu (grep `config.__doc__` = 0). {code}
7. invariant khai báo: "config.py là single source of truth cho SCHEMA + DEFAULTS";
   "Modelfile CHỈ chứa artifact-level, KHÔNG đặt num_ctx/temperature/top_p";
   ".env chỉ override giá trị khác giữa môi trường". {doc}
8. deprecated: không. **Đối chiếu code:** hai lời khai đầu đúng. Lời khai thứ ba
   (".env chỉ override cái khác giữa môi trường") bị chính `.env` phản chứng:
   `OLLAMA_GENERATE_TIMEOUT=300` không phải khác biệt môi trường mà là đảo ngược
   một quyết định thiết kế được ghi rõ ở `config.py:42`. Xem Q-01. {code+doc}

### [x] `class Settings`
1. in/out: `Settings()` không tham số; trả một instance mang 73 thuộc tính. {code}
2. side effect: đọc file `.env` từ **thư mục làm việc hiện tại** và đọc
   `os.environ`, khi khởi tạo. {code}
3. state: instance immutable trên thực tế (xem §1 mục 3). {code}
4. lỗi: `pydantic.ValidationError` khi ép kiểu hỏng hoặc validator raise. {code}
5. config: `model_config` ở dòng ngay dưới. {code}
6. ai gọi: đúng **1** chỗ khởi tạo — `config.py:288`. Ngoài ra `Settings` được
   import theo tên ở `tests/test_settings.py` để dựng instance riêng cho test. {code}
7. invariant: một lớp phẳng, không kế thừa, không lớp con, không `Field(...)` nào
   dùng alias — nên tên field ↔ tên biến môi trường là ánh xạ 1-1 viết hoa. {code}
8. deprecated: không. {code}

### [x] `model_config` (`config.py:21`)
1. in/out: `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`. {code}
2. side effect: không trực tiếp; nó điều khiển side effect của `Settings.__init__`. {code}
3. state: hằng số lớp. {code}
4. lỗi: không. {code}
5. config: chính nó là config của config. {code}
6. ai gọi: pydantic-settings đọc, không code nào của repo đọc. {code}
7. invariant: `env_file=".env"` là đường dẫn **tương đối** → phụ thuộc cwd. Chạy
   từ repo root thì đúng; chạy từ thư mục con thì `.env` không được đọc và **không
   có cảnh báo nào** — mọi field lặng lẽ về default. Xem Q-02. {code}
8. deprecated: không. {code}

### [x] `settings` (singleton, `config.py:288`)
1. in/out: `settings = Settings()` — module-level. {code}
2. side effect: khởi tạo chạy **lúc import**, nên bất kỳ ai `import acne_llm.config`
   đều kích hoạt đọc `.env` + validate. {code}
3. state: một object dùng chung toàn tiến trình; `di.py:163` sửa nó (xem §1 mục 3). {code}
4. lỗi: `ValidationError` lúc import — không bắt được bằng try/except ở nơi gọi
   trừ khi bọc chính câu import. {code}
5. config: không. {code}
6. ai gọi: được import ở rất nhiều nơi; consumer chính là `src/acne_llm/di.py`
   (composition root, đọc 40+ field) và `src/acne_llm/utils/logging.py`
   (banner khởi động, đọc ~15 field). Chi tiết per-field ở §4. {code}
7. invariant: đây là singleton **duy nhất**; không có hàm `get_settings()` hay
   `lru_cache` factory nào — nên không thể inject Settings khác vào runtime mà
   không monkeypatch. Test khắc phục bằng cách dựng `Settings()` riêng. {code}
8. deprecated: không. {code}

---

## §3 — Validator (6 khối, đủ 8 mục mỗi khối)

### [x] `_check_intake_timeout` (`config.py:69-74`)
1. in/out: `(cls, v: float) -> float`; trả nguyên `v`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `ValueError("intake_timeout must be greater than zero")` khi `v <= 0`. {code}
5. config: gắn với field `intake_timeout`. {code}
6. ai gọi: pydantic gọi lúc `Settings()`. Không code nào gọi trực tiếp. {code}
7. invariant: chỉ chặn `<= 0`, **không** chặn trên. `INTAKE_TIMEOUT=100000` qua được. {code}
8. deprecated: không. {code}

### [x] `_check_num_ctx` (`config.py:76-81`)
1. in/out: `(cls, v: int) -> int`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `ValueError(f"llm_num_ctx={v} ngoài phạm vi hợp lý [512, 32768]")`. {code}
5. config: field `llm_num_ctx`. {code}
6. ai gọi: pydantic. Có test phủ: `tests/test_settings.py` (2 lần chạm `llm_num_ctx`). {code+test}
7. invariant: chặn hai đầu `[512, 32768]`. Đây là **validator duy nhất chặn hai
   đầu cho một field số nguyên**. {code}
8. deprecated: không. {code}

### [x] `_check_keep_alive` (`config.py:83-103`, `mode="before"`)
1. in/out: `(cls, v) -> str | int`; nhận bất kỳ, trả int hoặc string-có-unit. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `ValueError` với thông điệp liệt kê dạng hợp lệ, khi chuỗi không phải số
   và cũng không kết thúc bằng `s`/`m`/`h`. {code}
5. config: field `llm_keep_alive`. {code}
6. ai gọi: pydantic, **trước** khi ép kiểu (`mode="before"`) — bắt buộc, vì
   `str | int` sẽ nhận `"-1"` như string hợp lệ nếu không có bước này. {code}
7. invariant: `"-1"` string bị convert thành int `-1`, đúng như comment
   `config.py:36-39` giải thích (Ollama trả 400 "missing unit in duration" với
   string `"-1"` trần). Đây là khối hiếm hoi mà comment và code khớp nhau và
   comment nêu được lý do bên ngoài repo. {code+comment}
8. deprecated: không. {code}

### [x] `_check_semantic_router_k` (`config.py:122-127`)
1. in/out: `(cls, v: int) -> int`. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `ValueError("semantic_router_k must be in [1,100]")`. {code}
5. config: field `semantic_router_k`. {code}
6. ai gọi: pydantic. {code}
7. invariant: chặn `[1,100]`. Cận trên 100 không neo vào gì — index kNN có bao
   nhiêu điểm thì không biết ở tầng này. {code}
8. deprecated: không. {code}

### [x] `_check_semantic_router_thresholds` (`config.py:129-137`)
1. in/out: `(cls, v: float) -> float`; **dùng chung cho 2 field**
   (`semantic_router_oos_distance_threshold`, `semantic_router_ambiguity_margin`). {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `ValueError("semantic router thresholds must be in [0,1]")`. {code}
5. config: 2 field kể trên. {code}
6. ai gọi: pydantic, 2 lần (mỗi field một lần). {code}
7. invariant: `[0,1]`. Với `oos_distance_threshold` đây là khoảng cách cosine —
   khoảng cosine distance thật là `[0,2]`, nên cận trên 1 là ràng buộc chặt hơn
   toán học cho phép. Không sai (giá trị đang dùng 0.483609), nhưng là giả định
   ngầm không được ghi ở đâu. {code}
8. deprecated: không. {code}

### [x] `_normalize_device` (`config.py:139-151`)
1. in/out: `(cls, v: str) -> str`; chuẩn hoá alias → tên PyTorch. {code}
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `ValueError(f"device={v!r} không hợp lệ (chấp nhận: cpu, cuda, cuda:N, mps, auto)")`. {code}
5. config: field `device`. {code}
6. ai gọi: pydantic. Kết quả được đọc ở `rag/embedder.py` (3 lần),
   `rag/reranker.py` (3 lần), `di.py` (2 lần). {code}
7. invariant: map `{"gpu","nvidia","cuda:0"} → "cuda"`; cho qua
   `{"cpu","cuda","mps","auto"}`; cho qua `cuda:N`. Lưu ý `"cuda:0"` bị map về
   `"cuda"` còn `"cuda:1"` giữ nguyên — không đối xứng, nhưng vô hại vì PyTorch
   coi `cuda` ≡ `cuda:0`. {code}
8. deprecated: không. {code}

---

## §4 — 73 field (mục 1, 5, 6, 8; mục 2/3/4/7 xem §1)

### [x] `ollama_url`
1. in/out: field khai bao `ollama_url: str` tai `config.py:24`; doc ra la `settings.ollama_url` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"http://localhost:11434"` trong file; **`.env` that dang dat `OLLAMA_URL=http://localhost:11434`** nen gia tri chay that la cai nay. {code}
6. ai goi: 8 lan doc trong code — src=4 eval=2 other=2 (test=0, doc=5). Vi tri: src/acne_llm/di.py:4; research/evaluation/runners/run_intake.py:1,research/dashboards/architecture/build_drawio.py:1; docker-compose.yml:1,tasks.sh:1. {code}
8. deprecated: khong. {code}

### [x] `llm_model`
1. in/out: field khai bao `llm_model: str` tai `config.py:25`; doc ra la `settings.llm_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"acne-generator"` trong file; **`.env` that dang dat `LLM_MODEL=acne-generator-v2`** nen gia tri chay that la cai nay. {code}
6. ai goi: 8 lan doc trong code — src=2 eval=5 other=1 (test=0, doc=7). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1; research/evaluation/full_evaluation.py:1,research/evaluation/adapters/_repo.py:1,research/evaluation/runners/run_ablation.py:3; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `llm_fallback_model`
1. in/out: field khai bao `llm_fallback_model: str` tai `config.py:26`; doc ra la `settings.llm_fallback_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"qwen2.5:3b"`; `.env` khong dat khoa `LLM_FALLBACK_MODEL` nen default la gia tri chay that. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=1 other=1 (test=0, doc=3). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `llm_num_ctx`
1. in/out: field khai bao `llm_num_ctx: int` tai `config.py:28`; doc ra la `settings.llm_num_ctx` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `8192`; `.env` khong dat khoa `LLM_NUM_CTX` nen default la gia tri chay that. {code}
6. ai goi: 10 lan doc trong code — src=5 eval=3 other=2 (test=2, doc=1). Vi tri: src/acne_llm/di.py:4,src/acne_llm/utils/logging.py:1; research/evaluation/adapters/_repo.py:1,research/evaluation/runners/run_ablation.py:1,research/evaluation/runners/run_intake.py:1; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `llm_num_predict`
1. in/out: field khai bao `llm_num_predict: int` tai `config.py:29`; doc ra la `settings.llm_num_predict` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `2048`; `.env` khong dat khoa `LLM_NUM_PREDICT` nen default la gia tri chay that. {code}
6. ai goi: 5 lan doc trong code — src=1 eval=2 other=2 (test=6, doc=1). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1,research/evaluation/runners/run_ablation.py:1; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `llm_temperature`
1. in/out: field khai bao `llm_temperature: float` tai `config.py:30`; doc ra la `settings.llm_temperature` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.35`; `.env` khong dat khoa `LLM_TEMPERATURE` nen default la gia tri chay that. {code}
6. ai goi: 4 lan doc trong code — src=2 eval=1 other=1 (test=1, doc=1). Vi tri: src/acne_llm/di.py:1,src/acne_llm/chat/runtime.py:1; research/evaluation/adapters/_repo.py:1; frontend/src/config/chatConfig.ts:1. {code}
8. deprecated: khong. {code}

### [x] `llm_top_p`
1. in/out: field khai bao `llm_top_p: float` tai `config.py:31`; doc ra la `settings.llm_top_p` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.85`; `.env` khong dat khoa `LLM_TOP_P` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=1 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1. {code}
8. deprecated: khong. {code}

### [x] `llm_top_k`
1. in/out: field khai bao `llm_top_k: int` tai `config.py:32`; doc ra la `settings.llm_top_k` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `40`; `.env` khong dat khoa `LLM_TOP_K` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=1 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1. {code}
8. deprecated: khong. {code}

### [x] `llm_repeat_penalty`
1. in/out: field khai bao `llm_repeat_penalty: float` tai `config.py:33`; doc ra la `settings.llm_repeat_penalty` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `1.1`; `.env` khong dat khoa `LLM_REPEAT_PENALTY` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=1 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1. {code}
8. deprecated: khong. {code}

### [x] `llm_repeat_last_n`
1. in/out: field khai bao `llm_repeat_last_n: int` tai `config.py:34`; doc ra la `settings.llm_repeat_last_n` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `128`; `.env` khong dat khoa `LLM_REPEAT_LAST_N` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `llm_keep_alive`
1. in/out: field khai bao `llm_keep_alive: str | int` tai `config.py:40`; doc ra la `settings.llm_keep_alive` kieu `str | int`. Khong nhan tham so. {code}
5. nguon: default `-1`; `.env` khong dat khoa `LLM_KEEP_ALIVE` nen default la gia tri chay that. {code}
6. ai goi: 8 lan doc trong code — src=5 eval=1 other=2 (test=0, doc=0). Vi tri: src/acne_llm/di.py:3,src/acne_llm/utils/logging.py:2; research/evaluation/runners/run_intake.py:1; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `ollama_health_timeout`
1. in/out: field khai bao `ollama_health_timeout: float` tai `config.py:41`; doc ra la `settings.ollama_health_timeout` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `5.0`; `.env` khong dat khoa `OLLAMA_HEALTH_TIMEOUT` nen default la gia tri chay that. {code}
6. ai goi: 7 lan doc trong code — src=4 eval=1 other=2 (test=0, doc=0). Vi tri: src/acne_llm/di.py:4; research/evaluation/runners/run_intake.py:1; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `ollama_generate_timeout`
1. in/out: field khai bao `ollama_generate_timeout: float` tai `config.py:43`; doc ra la `settings.ollama_generate_timeout` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `30.0` trong file; **`.env` that dang dat `OLLAMA_GENERATE_TIMEOUT=300`** nen gia tri chay that la cai nay. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=0 other=2 (test=0, doc=4). Vi tri: src/acne_llm/di.py:1; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `llm_use_modelfile_system`
1. in/out: field khai bao `llm_use_modelfile_system: bool` tai `config.py:47`; doc ra la `settings.llm_use_modelfile_system` kieu `bool`. Khong nhan tham so. {code}
5. nguon: default `True`; `.env` khong dat khoa `LLM_USE_MODELFILE_SYSTEM` nen default la gia tri chay that. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=0 other=2 (test=0, doc=3). Vi tri: src/acne_llm/di.py:1; docker-compose.yml:1,scripts/ab_template_prompt.ps1:1. {code}
8. deprecated: khong. {code}

### [x] `intake_mode`
1. in/out: field khai bao `intake_mode: Literal["unified", "legacy"]` tai `config.py:51`; doc ra la `settings.intake_mode` kieu `Literal["unified", "legacy"]`. Khong nhan tham so. {code}
5. nguon: default `"unified"` trong file; **`.env` that dang dat `INTAKE_MODE=unified`** nen gia tri chay that la cai nay. {code}
6. ai goi: 4 lan doc trong code — src=2 eval=1 other=1 (test=2, doc=20). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1; research/dashboards/architecture/build_drawio.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `intake_model`
1. in/out: field khai bao `intake_model: str` tai `config.py:52`; doc ra la `settings.intake_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"acne-intaker"` trong file; **`.env` that dang dat `INTAKE_MODEL=acne-intaker`** nen gia tri chay that la cai nay. {code}
6. ai goi: 7 lan doc trong code — src=2 eval=4 other=1 (test=0, doc=17). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1; research/evaluation/runners/run_intake.py:4; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `intake_timeout`
1. in/out: field khai bao `intake_timeout: float` tai `config.py:53`; doc ra la `settings.intake_timeout` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `60.0`; `.env` khong dat khoa `INTAKE_TIMEOUT` nen default la gia tri chay that. {code}
6. ai goi: 6 lan doc trong code — src=2 eval=2 other=2 (test=0, doc=8). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1; research/evaluation/runners/run_intake.py:2; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `extractor_mode`
1. in/out: field khai bao `extractor_mode: Literal["llm", "rule"]` tai `config.py:58`; doc ra la `settings.extractor_mode` kieu `Literal["llm", "rule"]`. Khong nhan tham so. {code}
5. nguon: default `"llm"`; `.env` khong dat khoa `EXTRACTOR_MODE` nen default la gia tri chay that. {code}
6. ai goi: 8 lan doc trong code — src=7 eval=0 other=1 (test=0, doc=10). Vi tri: src/acne_llm/di.py:3,src/acne_llm/chat/intake.py:1,src/acne_llm/chat/routing/rule_extractor.py:1,src/acne_llm/chat/routing/rule_normalizer.py:1,src/acne_llm/utils/logging.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `extractor_model`
1. in/out: field khai bao `extractor_model: str` tai `config.py:59`; doc ra la `settings.extractor_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"acne-extractor:1.5b"`; `.env` khong dat khoa `EXTRACTOR_MODEL` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=2 eval=0 other=0 (test=0, doc=5). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1. {code}
8. deprecated: khong. {code}

### [x] `extractor_timeout`
1. in/out: field khai bao `extractor_timeout: float` tai `config.py:60`; doc ra la `settings.extractor_timeout` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `20.0`; `.env` khong dat khoa `EXTRACTOR_TIMEOUT` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=2 eval=0 other=0 (test=0, doc=4). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1. {code}
8. deprecated: khong. {code}

### [x] `router_mode`
1. in/out: field khai bao `router_mode: Literal["llm", "semantic"]` tai `config.py:65`; doc ra la `settings.router_mode` kieu `Literal["llm", "semantic"]`. Khong nhan tham so. {code}
5. nguon: default `"llm"`; `.env` khong dat khoa `ROUTER_MODE` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=2 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1. {code}
8. deprecated: khong. {code}

### [x] `router_model`
1. in/out: field khai bao `router_model: str` tai `config.py:66`; doc ra la `settings.router_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"acnellm-intent"`; `.env` khong dat khoa `ROUTER_MODEL` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=2 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1. {code}
8. deprecated: khong. {code}

### [x] `router_timeout`
1. in/out: field khai bao `router_timeout: float` tai `config.py:67`; doc ra la `settings.router_timeout` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `8.0`; `.env` khong dat khoa `ROUTER_TIMEOUT` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=2 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1. {code}
8. deprecated: khong. {code}

### [x] `embedding_model`
1. in/out: field khai bao `embedding_model: str` tai `config.py:106`; doc ra la `settings.embedding_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"AITeamVN/Vietnamese_Embedding"`; `.env` khong dat khoa `EMBEDDING_MODEL` nen default la gia tri chay that. {code}
6. ai goi: 16 lan doc trong code — src=2 eval=13 other=1 (test=0, doc=1). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1; research/evaluation/reports/full_eval_1/retrieval/results.json:1,research/evaluation/reports/run_full_v3_2/retrieval/results.json:1,research/evaluation/reports/full_eval_part2/retrieval/results.json:1,research/evaluation/runners/run_retrieval.py:1,research/evaluation/datasets/make_eval_set.py:1,research/evaluation/datasets/make_intake_set_v2.py:5,research/datagen/main.py:1,research/dashboards/build/source_snapshot.json:1,research/guideline_docs/reembed_guideline.py:1; scripts/build_kb.py:1. {code}
8. deprecated: khong. {code}

### [x] `reranker_model`
1. in/out: field khai bao `reranker_model: str` tai `config.py:107`; doc ra la `settings.reranker_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"BAAI/bge-reranker-v2-m3"`; `.env` khong dat khoa `RERANKER_MODEL` nen default la gia tri chay that. {code}
6. ai goi: 8 lan doc trong code — src=3 eval=5 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1,src/acne_llm/utils/logging.py:1,src/acne_llm/api/routes/kb.py:1; research/evaluation/reports/full_eval_1/retrieval/results.json:1,research/evaluation/reports/run_full_v3_2/retrieval/results.json:1,research/evaluation/reports/full_eval_part2/retrieval/results.json:1,research/evaluation/runners/run_retrieval.py:1,research/dashboards/build/source_snapshot.json:1. {code}
8. deprecated: khong. {code}

### [x] `device`
1. in/out: field khai bao `device: str` tai `config.py:111`; doc ra la `settings.device` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"cpu"` trong file; **`.env` that dang dat `DEVICE=cpu`** nen gia tri chay that la cai nay. {code}
6. ai goi: 16 lan doc trong code — src=9 eval=4 other=3 (test=0, doc=9). Vi tri: src/acne_llm/di.py:2,src/acne_llm/rag/embedder.py:3,src/acne_llm/rag/reranker.py:3,src/acne_llm/utils/logging.py:1; research/evaluation/datasets/make_eval_set.py:1,research/evaluation/datasets/make_intake_set_v2.py:1,research/dashboards/architecture/build_drawio.py:1,research/guideline_docs/reembed_guideline.py:1; docker-compose.yml:2,scripts/build_kb.py:1. {code}
8. deprecated: khong. {code}

### [x] `semantic_router_train_path`
1. in/out: field khai bao `semantic_router_train_path: str` tai `config.py:116`; doc ra la `settings.semantic_router_train_path` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/intent_classify.train.jsonl"`; `.env` khong dat khoa `SEMANTIC_ROUTER_TRAIN_PATH` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=0 other=1 (test=0, doc=1). Vi tri: src/acne_llm/di.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `semantic_router_cache_path`
1. in/out: field khai bao `semantic_router_cache_path: str` tai `config.py:117`; doc ra la `settings.semantic_router_cache_path` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/intent_router_index.npz"`; `.env` khong dat khoa `SEMANTIC_ROUTER_CACHE_PATH` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=0 other=1 (test=0, doc=1). Vi tri: src/acne_llm/di.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `semantic_router_k`
1. in/out: field khai bao `semantic_router_k: int` tai `config.py:118`; doc ra la `settings.semantic_router_k` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `9`; `.env` khong dat khoa `SEMANTIC_ROUTER_K` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=1). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `semantic_router_oos_distance_threshold`
1. in/out: field khai bao `semantic_router_oos_distance_threshold: float` tai `config.py:119`; doc ra la `settings.semantic_router_oos_distance_threshold` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.483609`; `.env` khong dat khoa `SEMANTIC_ROUTER_OOS_DISTANCE_THRESHOLD` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=1). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `semantic_router_ambiguity_margin`
1. in/out: field khai bao `semantic_router_ambiguity_margin: float` tai `config.py:120`; doc ra la `settings.semantic_router_ambiguity_margin` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.08`; `.env` khong dat khoa `SEMANTIC_ROUTER_AMBIGUITY_MARGIN` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=1). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `chroma_dir`
1. in/out: field khai bao `chroma_dir: str` tai `config.py:154`; doc ra la `settings.chroma_dir` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/chroma_db"`; `.env` khong dat khoa `CHROMA_DIR` nen default la gia tri chay that. {code}
6. ai goi: 12 lan doc trong code — src=1 eval=2 other=9 (test=0, doc=4). Vi tri: src/acne_llm/di.py:1; research/guideline_docs/reembed_guideline.py:2; docker-compose.yml:1,scripts/build_kb.py:8. {code}
8. deprecated: khong. {code}

### [x] `bm25_path`
1. in/out: field khai bao `bm25_path: str` tai `config.py:155`; doc ra la `settings.bm25_path` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/bm25_index.pkl"`; `.env` khong dat khoa `BM25_PATH` nen default la gia tri chay that. {code}
6. ai goi: 9 lan doc trong code — src=1 eval=0 other=8 (test=0, doc=3). Vi tri: src/acne_llm/di.py:1; docker-compose.yml:1,scripts/build_kb.py:7. {code}
8. deprecated: khong. {code}

### [x] `docs_jsonl`
1. in/out: field khai bao `docs_jsonl: str` tai `config.py:156`; doc ra la `settings.docs_jsonl` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/raw/documents.jsonl"`; `.env` khong dat khoa `DOCS_JSONL` nen default la gia tri chay that. {code}
6. ai goi: **0 lan doc trong code** (src=0, eval=0, other=0). Chi con 3 lan nhac trong .md va 0 lan trong test. {code}
8. deprecated: **field chet.** Khong danh dau deprecated o dau, nhung khong ai doc → doi ten hay xoa deu khong lam vo gi. {code}

### [x] `chunks_jsonl`
1. in/out: field khai bao `chunks_jsonl: str` tai `config.py:157`; doc ra la `settings.chunks_jsonl` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/raw/chunks.jsonl"`; `.env` khong dat khoa `CHUNKS_JSONL` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=0 eval=2 other=0 (test=0, doc=3). Vi tri: research/LLMData/chunk_qa/loader.py:1,research/LLMData/chunk_qa/main.py:1. {code}
8. deprecated: khong. {code}

### [x] `finetune_jsonl`
1. in/out: field khai bao `finetune_jsonl: str` tai `config.py:160`; doc ra la `settings.finetune_jsonl` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/finetune/llm_data.jsonl"`; `.env` khong dat khoa `FINETUNE_JSONL` nen default la gia tri chay that. {code}
6. ai goi: **0 lan doc trong code** (src=0, eval=0, other=0). Chi con 0 lan nhac trong .md va 0 lan trong test. {code}
8. deprecated: **field chet.** Khong danh dau deprecated o dau, nhung khong ai doc → doi ten hay xoa deu khong lam vo gi. {code}

### [x] `qa_finetune_jsonl`
1. in/out: field khai bao `qa_finetune_jsonl: str` tai `config.py:161`; doc ra la `settings.qa_finetune_jsonl` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/finetune/qa_finetuning.jsonl"`; `.env` khong dat khoa `QA_FINETUNE_JSONL` nen default la gia tri chay that. {code}
6. ai goi: **0 lan doc trong code** (src=0, eval=0, other=0). Chi con 0 lan nhac trong .md va 0 lan trong test. {code}
8. deprecated: **field chet.** Khong danh dau deprecated o dau, nhung khong ai doc → doi ten hay xoa deu khong lam vo gi. {code}

### [x] `prompts_dir`
1. in/out: field khai bao `prompts_dir: str` tai `config.py:164`; doc ra la `settings.prompts_dir` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./config/prompts"`; `.env` khong dat khoa `PROMPTS_DIR` nen default la gia tri chay that. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=2 other=0 (test=0, doc=3). Vi tri: src/acne_llm/di.py:1; research/datagen/render_context.py:2. {code}
8. deprecated: khong. {code}

### [x] `guardrails_yaml`
1. in/out: field khai bao `guardrails_yaml: str` tai `config.py:165`; doc ra la `settings.guardrails_yaml` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./config/guardrails.yaml"`; `.env` khong dat khoa `GUARDRAILS_YAML` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=3). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `seed_sources`
1. in/out: field khai bao `seed_sources: str` tai `config.py:166`; doc ra la `settings.seed_sources` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/seed_sources.yaml"`; `.env` khong dat khoa `SEED_SOURCES` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=0 eval=0 other=1 (test=0, doc=3). Vi tri: scripts/crawl_all.py:1. {code}
8. deprecated: khong. {code}

### [x] `rerank_top_k`
1. in/out: field khai bao `rerank_top_k: int` tai `config.py:174`; doc ra la `settings.rerank_top_k` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `3`; `.env` khong dat khoa `RERANK_TOP_K` nen default la gia tri chay that. {code}
6. ai goi: **0 lan doc trong code** (src=0, eval=0, other=0). Chi con 0 lan nhac trong .md va 0 lan trong test. {code}
8. deprecated: **field chet.** Khong danh dau deprecated o dau, nhung khong ai doc → doi ten hay xoa deu khong lam vo gi. {code}

### [x] `chat_retrieve_top_k`
1. in/out: field khai bao `chat_retrieve_top_k: int` tai `config.py:180`; doc ra la `settings.chat_retrieve_top_k` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `25`; `.env` khong dat khoa `CHAT_RETRIEVE_TOP_K` nen default la gia tri chay that. {code}
6. ai goi: 6 lan doc trong code — src=1 eval=5 other=0 (test=0, doc=6). Vi tri: src/acne_llm/chat/_retrieval.py:1; research/evaluation/reports/full_eval_1/retrieval/results.json:1,research/evaluation/reports/run_full_v3_2/retrieval/results.json:1,research/evaluation/reports/full_eval_part2/retrieval/results.json:1,research/evaluation/runners/run_retrieval.py:2. {code}
8. deprecated: khong. {code}

### [x] `chat_rerank_top_k`
1. in/out: field khai bao `chat_rerank_top_k: int` tai `config.py:181`; doc ra la `settings.chat_rerank_top_k` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `5`; `.env` khong dat khoa `CHAT_RERANK_TOP_K` nen default la gia tri chay that. {code}
6. ai goi: 8 lan doc trong code — src=2 eval=5 other=1 (test=0, doc=1). Vi tri: src/acne_llm/chat/_retrieval.py:2; research/evaluation/reports/full_eval_1/retrieval/results.json:1,research/evaluation/reports/run_full_v3_2/retrieval/results.json:1,research/evaluation/reports/full_eval_part2/retrieval/results.json:1,research/evaluation/runners/run_retrieval.py:2; frontend/src/config/chatConfig.ts:1. {code}
8. deprecated: khong. {code}

### [x] `chat_max_context_chars`
1. in/out: field khai bao `chat_max_context_chars: int` tai `config.py:183`; doc ra la `settings.chat_max_context_chars` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `6000`; `.env` khong dat khoa `CHAT_MAX_CONTEXT_CHARS` nen default la gia tri chay that. {code}
6. ai goi: 6 lan doc trong code — src=1 eval=5 other=0 (test=1, doc=2). Vi tri: src/acne_llm/chat/orchestrator.py:1; research/evaluation/reports/full_eval_1/retrieval/results.json:1,research/evaluation/reports/run_full_v3_2/retrieval/results.json:1,research/evaluation/reports/full_eval_part2/retrieval/results.json:1,research/evaluation/runners/run_ablation.py:1,research/evaluation/runners/run_retrieval.py:1. {code}
8. deprecated: khong. {code}

### [x] `chat_safety_top_k`
1. in/out: field khai bao `chat_safety_top_k: int` tai `config.py:185`; doc ra la `settings.chat_safety_top_k` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `5`; `.env` khong dat khoa `CHAT_SAFETY_TOP_K` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=2). Vi tri: src/acne_llm/chat/_retrieval.py:1. {code}
8. deprecated: khong. {code}

### [x] `chat_guideline_top_k`
1. in/out: field khai bao `chat_guideline_top_k: int` tai `config.py:189`; doc ra la `settings.chat_guideline_top_k` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `5`; `.env` khong dat khoa `CHAT_GUIDELINE_TOP_K` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/chat/_retrieval.py:1. {code}
8. deprecated: khong. {code}

### [x] `chat_min_chunk_score`
1. in/out: field khai bao `chat_min_chunk_score: float` tai `config.py:200`; doc ra la `settings.chat_min_chunk_score` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.25`; `.env` khong dat khoa `CHAT_MIN_CHUNK_SCORE` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/chat/_retrieval.py:1. {code}
8. deprecated: khong. {code}

### [x] `chat_max_chunks_per_source`
1. in/out: field khai bao `chat_max_chunks_per_source: int` tai `config.py:204`; doc ra la `settings.chat_max_chunks_per_source` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `1`; `.env` khong dat khoa `CHAT_MAX_CHUNKS_PER_SOURCE` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/chat/_retrieval.py:1. {code}
8. deprecated: khong. {code}

### [x] `chat_rerank_floor`
1. in/out: field khai bao `chat_rerank_floor: float` tai `config.py:217`; doc ra la `settings.chat_rerank_floor` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.50`; `.env` khong dat khoa `CHAT_RERANK_FLOOR` nen default la gia tri chay that. {code}
6. ai goi: 5 lan doc trong code — src=1 eval=4 other=0 (test=0, doc=0). Vi tri: src/acne_llm/chat/_retrieval.py:1; research/evaluation/reports/full_eval_1/retrieval/results.json:1,research/evaluation/reports/run_full_v3_2/retrieval/results.json:1,research/evaluation/reports/full_eval_part2/retrieval/results.json:1,research/evaluation/runners/run_retrieval.py:1. {code}
8. deprecated: khong. {code}

### [x] `extract_min_field_conf`
1. in/out: field khai bao `extract_min_field_conf: float` tai `config.py:225`; doc ra la `settings.extract_min_field_conf` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.60`; `.env` khong dat khoa `EXTRACT_MIN_FIELD_CONF` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=2). Vi tri: src/acne_llm/chat/intake.py:1. {code}
8. deprecated: khong. {code}

### [x] `route_min_confidence`
1. in/out: field khai bao `route_min_confidence: float` tai `config.py:226`; doc ra la `settings.route_min_confidence` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.55`; `.env` khong dat khoa `ROUTE_MIN_CONFIDENCE` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=2, doc=1). Vi tri: src/acne_llm/chat/routing/intent_router.py:1. {code}
8. deprecated: khong. {code}

### [x] `reranker_batch_size`
1. in/out: field khai bao `reranker_batch_size: int` tai `config.py:228`; doc ra la `settings.reranker_batch_size` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `16`; `.env` khong dat khoa `RERANKER_BATCH_SIZE` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=4, doc=0). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `reranker_cache_size`
1. in/out: field khai bao `reranker_cache_size: int` tai `config.py:229`; doc ra la `settings.reranker_cache_size` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `2048`; `.env` khong dat khoa `RERANKER_CACHE_SIZE` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=4, doc=0). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `reranker_min_sigmoid`
1. in/out: field khai bao `reranker_min_sigmoid: float` tai `config.py:236`; doc ra la `settings.reranker_min_sigmoid` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.30`; `.env` khong dat khoa `RERANKER_MIN_SIGMOID` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=1 eval=0 other=0 (test=0, doc=1). Vi tri: src/acne_llm/di.py:1. {code}
8. deprecated: khong. {code}

### [x] `dense_max_distance`
1. in/out: field khai bao `dense_max_distance: float` tai `config.py:240`; doc ra la `settings.dense_max_distance` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `0.60`; `.env` khong dat khoa `DENSE_MAX_DISTANCE` nen default la gia tri chay that. {code}
6. ai goi: 4 lan doc trong code — src=4 eval=0 other=0 (test=1, doc=10). Vi tri: src/acne_llm/di.py:1,src/acne_llm/rag/retriever.py:3. {code}
8. deprecated: khong. {code}

### [x] `cache_dir`
1. in/out: field khai bao `cache_dir: str` tai `config.py:244`; doc ra la `settings.cache_dir` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/cache"`; `.env` khong dat khoa `CACHE_DIR` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=0 other=1 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `cache_size_gb`
1. in/out: field khai bao `cache_size_gb: float` tai `config.py:246`; doc ra la `settings.cache_size_gb` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `2.0`; `.env` khong dat khoa `CACHE_SIZE_GB` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=1 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1. {code}
8. deprecated: khong. {code}

### [x] `session_ttl`
1. in/out: field khai bao `session_ttl: float` tai `config.py:250`; doc ra la `settings.session_ttl` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `1800.0`; `.env` khong dat khoa `SESSION_TTL` nen default la gia tri chay that. {code}
6. ai goi: 9 lan doc trong code — src=9 eval=0 other=0 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1,src/acne_llm/chat/session/memory.py:2,src/acne_llm/chat/session/models.py:2,src/acne_llm/chat/session/__init__.py:2,src/acne_llm/db/session_store.py:2. {code}
8. deprecated: khong. {code}

### [x] `audit_db_path`
1. in/out: field khai bao `audit_db_path: str` tai `config.py:254`; doc ra la `settings.audit_db_path` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/audit.db"`; `.env` khong dat khoa `AUDIT_DB_PATH` nen default la gia tri chay that. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=1 other=1 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `session_db_path`
1. in/out: field khai bao `session_db_path: str` tai `config.py:256`; doc ra la `settings.session_db_path` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"./data/sessions.db"`; `.env` khong dat khoa `SESSION_DB_PATH` nen default la gia tri chay that. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=1 other=1 (test=0, doc=0). Vi tri: src/acne_llm/di.py:1; research/evaluation/adapters/_repo.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `log_level`
1. in/out: field khai bao `log_level: str` tai `config.py:260`; doc ra la `settings.log_level` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"INFO"` trong file; **`.env` that dang dat `LOG_LEVEL=DEBUG`** nen gia tri chay that la cai nay. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=0 other=2 (test=0, doc=4). Vi tri: src/acne_llm/api/app.py:1; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `api_host`
1. in/out: field khai bao `api_host: str` tai `config.py:263`; doc ra la `settings.api_host` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"0.0.0.0"`; `.env` khong dat khoa `API_HOST` nen default la gia tri chay that. {code}
6. ai goi: **0 lan doc trong code** (src=0, eval=0, other=0). Chi con 4 lan nhac trong .md va 0 lan trong test. {code}
8. deprecated: **field chet.** Khong danh dau deprecated o dau, nhung khong ai doc → doi ten hay xoa deu khong lam vo gi. {code}

### [x] `api_port`
1. in/out: field khai bao `api_port: int` tai `config.py:264`; doc ra la `settings.api_port` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `8000`; `.env` khong dat khoa `API_PORT` nen default la gia tri chay that. {code}
6. ai goi: **0 lan doc trong code** (src=0, eval=0, other=0). Chi con 4 lan nhac trong .md va 0 lan trong test. {code}
8. deprecated: **field chet.** Khong danh dau deprecated o dau, nhung khong ai doc → doi ten hay xoa deu khong lam vo gi. {code}

### [x] `frontend_url`
1. in/out: field khai bao `frontend_url: str` tai `config.py:265`; doc ra la `settings.frontend_url` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"http://localhost:3000"`; `.env` khong dat khoa `FRONTEND_URL` nen default la gia tri chay that. {code}
6. ai goi: 4 lan doc trong code — src=3 eval=0 other=1 (test=0, doc=0). Vi tri: src/acne_llm/api/app.py:3; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `cors_origins`
1. in/out: field khai bao `cors_origins: list[str]` tai `config.py:268`; doc ra la `settings.cors_origins` kieu `list[str]`. Khong nhan tham so. {code}
5. nguon: default `["http://localhost:3000", "http://localhost:8000"]` trong file; **`.env` that dang dat `CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]`** nen gia tri chay that la cai nay. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=0 other=1 (test=0, doc=8). Vi tri: src/acne_llm/api/app.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `api_key`
1. in/out: field khai bao `api_key: str` tai `config.py:269`; doc ra la `settings.api_key` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `""` trong file; **`.env` that dang dat `API_KEY=<co dat>`** nen gia tri chay that la cai nay. {code}
6. ai goi: 28 lan doc trong code — src=7 eval=15 other=6 (test=7, doc=13). Vi tri: src/acne_llm/api/observability.py:4,src/acne_llm/api/app.py:1,src/acne_llm/api/deps.py:2; research/evaluation/judges/clients.py:3,research/evaluation/datasets/make_eval_set.py:1,research/evaluation/datasets/make_intake_set.py:1,research/datagen/generator.py:2,research/datagen/intakedata/generator.py:1,research/datagen/roledatav2/probe_provider.py:6,research/datagen/roledata/generator.py:1; docker-compose.yml:5,scripts/prepare_docker_bundle.ps1:1. {code}
8. deprecated: khong. {code}

### [x] `admin_api_key`
1. in/out: field khai bao `admin_api_key: str` tai `config.py:274`; doc ra la `settings.admin_api_key` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `""` trong file; **`.env` that dang dat `ADMIN_API_KEY=<co dat>`** nen gia tri chay that la cai nay. {code}
6. ai goi: 2 lan doc trong code — src=2 eval=0 other=0 (test=9, doc=3). Vi tri: src/acne_llm/api/deps.py:2. {code}
8. deprecated: khong. {code}

### [x] `rate_limit_per_minute`
1. in/out: field khai bao `rate_limit_per_minute: int` tai `config.py:275`; doc ra la `settings.rate_limit_per_minute` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `60`; `.env` khong dat khoa `RATE_LIMIT_PER_MINUTE` nen default la gia tri chay that. {code}
6. ai goi: 3 lan doc trong code — src=1 eval=0 other=2 (test=0, doc=0). Vi tri: src/acne_llm/api/app.py:1; docker-compose.yml:2. {code}
8. deprecated: khong. {code}

### [x] `metrics_enabled`
1. in/out: field khai bao `metrics_enabled: bool` tai `config.py:276`; doc ra la `settings.metrics_enabled` kieu `bool`. Khong nhan tham so. {code}
5. nguon: default `True`; `.env` khong dat khoa `METRICS_ENABLED` nen default la gia tri chay that. {code}
6. ai goi: 2 lan doc trong code — src=1 eval=0 other=1 (test=0, doc=0). Vi tri: src/acne_llm/api/routes/metrics.py:1; docker-compose.yml:1. {code}
8. deprecated: khong. {code}

### [x] `judge_provider`
1. in/out: field khai bao `judge_provider: Literal["openai", "anthropic", "deepseek"]` tai `config.py:279`; doc ra la `settings.judge_provider` kieu `Literal["openai", "anthropic", "deepseek"]`. Khong nhan tham so. {code}
5. nguon: default `"deepseek"` trong file; **`.env` that dang dat `JUDGE_PROVIDER=openai`** nen gia tri chay that la cai nay. {code}
6. ai goi: 22 lan doc trong code — src=0 eval=22 other=0 (test=0, doc=14). Vi tri: research/evaluation/full_evaluation.py:2,research/evaluation/reports/full_eval_1/ablation/results.json:7,research/evaluation/reports/run_full_v3_2/ablation/results.json:7,research/evaluation/judges/clients.py:3,research/evaluation/runners/run_ablation.py:3. {code}
8. deprecated: khong. {code}

### [x] `judge_model`
1. in/out: field khai bao `judge_model: str` tai `config.py:280`; doc ra la `settings.judge_model` kieu `str`. Khong nhan tham so. {code}
5. nguon: default `"deepseek-v4-pro"` trong file; **`.env` that dang dat `JUDGE_MODEL=gpt-5.6-luna`** nen gia tri chay that la cai nay. {code}
6. ai goi: 40 lan doc trong code — src=0 eval=37 other=3 (test=0, doc=16). Vi tri: research/evaluation/full_evaluation.py:1,research/evaluation/reports/rescore_gpt/v1/summary.json:1,research/evaluation/reports/rescore_gpt/v2/summary.json:1,research/evaluation/reports/rescore_luna/v1/summary.json:1,research/evaluation/reports/rescore_luna/v2/summary.json:1,research/evaluation/reports/full_eval_1/ablation/results.json:7,research/evaluation/reports/full_eval_1/retrieval/results.json:1,research/evaluation/reports/run_full_v3_2/ablation/results.json:7,research/evaluation/reports/run_full_v3_2/retrieval/results.json:1,research/evaluation/reports/full_eval_part2/retrieval/results.json:1,research/evaluation/judges/clients.py:2,research/evaluation/runners/rescore.py:4,research/evaluation/runners/run_ablation.py:5,research/evaluation/runners/run_retrieval.py:4; scripts/build_intent_dataset.py:3. {code}
8. deprecated: khong. {code}

### [x] `crawl_concurrency`
1. in/out: field khai bao `crawl_concurrency: int` tai `config.py:283`; doc ra la `settings.crawl_concurrency` kieu `int`. Khong nhan tham so. {code}
5. nguon: default `8`; `.env` khong dat khoa `CRAWL_CONCURRENCY` nen default la gia tri chay that. {code}
6. ai goi: **0 lan doc trong code** (src=0, eval=0, other=0). Chi con 0 lan nhac trong .md va 0 lan trong test. {code}
8. deprecated: **field chet.** Khong danh dau deprecated o dau, nhung khong ai doc → doi ten hay xoa deu khong lam vo gi. {code}

### [x] `crawl_rate_per_sec`
1. in/out: field khai bao `crawl_rate_per_sec: float` tai `config.py:284`; doc ra la `settings.crawl_rate_per_sec` kieu `float`. Khong nhan tham so. {code}
5. nguon: default `1.0`; `.env` khong dat khoa `CRAWL_RATE_PER_SEC` nen default la gia tri chay that. {code}
6. ai goi: 1 lan doc trong code — src=0 eval=0 other=1 (test=0, doc=0). Vi tri: scripts/crawl_all.py:1. {code}
8. deprecated: khong. {code}

---

## §5 — Điều tìm được (câu hỏi)

**Q-01 — `.env` đảo ngược một quyết định thiết kế được ghi rõ trong code.**
`config.py:42-43` viết: "Timeout thấp để phép đo latency lộ request chậm thay
vì che bằng env override", rồi đặt `ollama_generate_timeout: float = 30.0`.
`.env` thật đang đặt `OLLAMA_GENERATE_TIMEOUT=300` — gấp 10 lần, tức đúng cái
"che bằng env override" mà comment nói phải tránh. Mọi số latency đo trong eval
đều chạy dưới trần 300s này. Cần quyết: sửa comment cho khớp thực tế, hay bỏ
override trong `.env`. {code+comment}

**Q-02 — `env_file=".env"` phụ thuộc cwd và hỏng im lặng.**
`config.py:21`. Chạy từ thư mục con → không đọc được `.env` → 12 khoá đang đặt
biến mất, `llm_model` về `"acne-generator"` (bản cũ, không phải `-v2`),
`judge_provider` về `"deepseek"` (hết credit). Không có log, không có exception.
Đây là cùng một hạng lỗi với bug preflight đã sửa hôm trước. {code}

**Q-03 — 8 field không có consumer nào trong code.**
`docs_jsonl`, `chunks_jsonl`, `finetune_jsonl`, `qa_finetune_jsonl`,
`rerank_top_k`, `api_host`, `api_port`, `crawl_concurrency`.
Ghi chú hai trường hợp dễ nhầm:
- `chunks_jsonl` **có** vẻ được dùng ở `research/LLMData/chunk_qa/loader.py:103`
  (`cfg.chunks_jsonl`), nhưng `cfg` ở đó là `research/LLMData/chunk_qa/config.py:88
  class Config` — một dataclass khác hoàn toàn, có field `chunks_jsonl` riêng
  (`:91`). `Settings.chunks_jsonl` vẫn là 0 consumer.
- `rerank_top_k` **có** vẻ được dùng ở `src/acne_llm/cache.py:102`, nhưng đó là
  biến cục bộ trong `cached_retrieve`, không phải `settings.rerank_top_k`.
  Field này là bản song sinh chết của `chat_rerank_top_k` (field sống, 7 lần đọc).
{code}

**Q-04 — `di.py:163` ghi đè cấu hình người dùng.**
`if getattr(settings, "extractor_mode", "llm") != "llm": settings.extractor_mode = "llm"`.
Nghĩa là đặt `EXTRACTOR_MODE=rule` trong `.env` **không có tác dụng** — composition
root ép về `"llm"`. Comment ngay trên (`di.py:160-161`) nói `intake.py` "cố tình
không đổi và vẫn dùng `extractor_mode`". Field khai `Literal["llm","rule"]` nên
schema hứa hai lựa chọn, runtime chỉ cho một. {code+comment}

**Q-05 — 3 default đã mục so với thực tế đang chạy.**
- `llm_model = "acne-generator"` (`:25`) — model thật là `acne-generator-v2`,
  chỉ đúng nhờ `.env`.
- `judge_provider = "deepseek"` (`:279`), `judge_model = "deepseek-v4-pro"` (`:280`)
  — DeepSeek đã hết credit; `.env` đang trỏ `openai` / `gpt-5.6-luna`.
Cả ba chỉ đúng khi `.env` đọc được — nối thẳng vào Q-02. {code}

**Q-06 — hai model được đặt default trong code nhưng có thể không còn tồn tại.**
`extractor_model = "acne-extractor:1.5b"` (`:59`) và `router_model = "acnellm-intent"`
(`:66`), cả hai được `di.py:170,196-202` dùng làm default cứng. Cần đối chiếu
với `ollama list` sau đợt dọn model. Nếu đã xoá, đường LLM-first của router và
extractor rơi thẳng xuống fallback trong mọi request mà không ai biết —
`extractor_mode`/`router_mode` vẫn báo `"llm"`. {code}

**Q-07 — độ phủ validator lệch hẳn.**
6 validator phủ 8/73 field. Không field số nào trong nhóm quan trọng nhất được
chặn: `llm_temperature` (`:30`), `llm_top_p` (`:31`), `chat_rerank_floor` (`:217`),
`reranker_min_sigmoid` (`:236`), `dense_max_distance` (`:240`), `chat_min_chunk_score`
(`:200`) — tất cả đều là số trong `[0,1]` theo ngữ nghĩa, không có gì chặn. Đặt
`CHAT_RERANK_FLOOR=5.0` sẽ khiến RAG trả rỗng cho **mọi** truy vấn và không báo lỗi. {code}

**Q-08 — comment dài hơn code và mang lịch sử chưa được kiểm.**
`config.py:194-217` và `:227-236` chứa hai đoạn kể lại lịch sử tune ngưỡng
sigmoid ("code còn sigmoid lần hai nên mọi thứ bị nén vào [0.500, 0.731]"). Đây
là {comment}, hạng lời khai. Tôi **chưa** đối chiếu với `rag/reranker.py` trong
module này — việc đó thuộc `src.rag`. Ghi lại để module đó phải kiểm.

**Q-09 — `admin_api_key = ""` fail-closed, nhưng `api_key = ""` thì không rõ.**
Comment `:273` nói rõ rỗng = từ chối truy cập với `admin_api_key`. `api_key`
(`:269`) không có comment tương ứng; hành vi khi rỗng do `api/deps.py` quyết
định, sẽ kiểm ở `src.api`. Ghi lại để module đó phải trả lời. {code+comment}

---

## §6 — Tự kiểm (Bước 4)

- Khối khai báo ở Bước 0: **83**
- Khối `### [x]` đếm được trong file này: xem lệnh `grep -c '^### \[x\]'`
- Mục: 83 × 8 = **664**, trong đó 73 × 4 = 292 mục thuộc nhóm nén có khai báo ở
  §1 (mục 2/3/4/7 của các field), 73 × 4 = 292 mục khai riêng ở §4, và
  10 × 8 = 80 mục khai đầy đủ ở §2–§3.
- Kiểm tổng: 292 + 292 + 80 = **664**. Khớp.

**Đính chính so với báo cáo miệng trước đó:** tôi từng nói module này có
**10** field không consumer. Đếm lại bằng script phân loại theo thư mục cho
**8**. Hai field tôi kể nhầm là `extract_min_field_conf` (thật ra có consumer:
`chat/intake.py:748-755`, đọc qua `getattr(getattr(c,"settings",None), ...)`)
và `route_min_confidence` (có consumer: `chat/routing/intent_router.py:652`,
`_S().route_min_confidence`). Số đúng là 8, danh sách ở Q-03.
