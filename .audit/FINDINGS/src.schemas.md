# FINDINGS / src.schemas

Module: `src/acne_llm/schemas/` — 5 file, 597 LOC. Vòng 1, bậc 1 (leaf).
Nhãn nguồn: `{code}` `{comment}` `{doc}` `{test}`. Luật: code là sự thật, comment là lời khai — ghi hai dòng riêng kể cả khi trùng.

File đã quét: `__init__.py` (21) · `clinical.py` (75) · `core.py` (156) · `extraction.py` (150) · `kb.py` (195).

---

## `__init__.py`

### [x] `__all__`
1. in/out: hằng `list[str]`, 19 tên. Không nhận tham số. {code}
2. side effect: không. {code}
3. state: đọc không, ghi không. {code}
4. lỗi: không có nhánh lỗi; nếu một tên trong `__all__` không tồn tại thì `from ... import *` mới báo, còn import trực tiếp thì không. {code}
5. config/env: không. {code}
6. ai gọi: `src/acne_llm/rag/reranker.py:6`, `src/acne_llm/rag/retriever.py:9` import qua `from ..schemas import ...`. Nó gọi ra ngoài: `.core`, `.clinical`, `.kb`, `.extraction`. {code}
7. invariant: mọi symbol công khai của module phải nằm ở đây — **vi phạm thực tế**: `ExtractionConfidence`, `LLMData`, `Intent`, `ChatMessage`, `QASample`, `Severity`, `InflammationLevel`, `SourceType`, `infer_source_type`, `METHOD_BASE_CONFIDENCE` đều KHÔNG có trong `__all__` dù có code ngoài import chúng bằng đường dẫn đầy đủ. {code}
8. deprecated/TODO: không có dấu nào trong file. {code}

---

## `clinical.py`

### [x] `Severity`
1. in/out: `Literal["mild","moderate","severe","unknown"]`, alias kiểu. {code} `[src/acne_llm/schemas/clinical.py:14]`
2. side effect: không. {code}
3. state: không đọc, không ghi. {code}
4. lỗi: không — pydantic báo lỗi tại điểm dùng, không tại đây. {code}
5. config/env: không. {code}
6. ai gọi: `research/LLMData/clinical_case/schema.py:8` import trực tiếp `from acne_llm.schemas.clinical import NormalizedAcneCase, Severity`. Trong `src/` **không ai dùng** — `NormalizedAcneCase` không có field nào kiểu `Severity`. {code}
7. invariant: bốn bậc này phải khớp với `AdviseOutput.severity` ở `core.py:146` và `VisionOutput.severity_estimate` ở `core.py:18` — hiện khớp, nhưng cả ba khai lại độc lập chứ không dùng chung alias. {code}
8. deprecated/TODO: không. Nhưng là symbol chỉ có người ngoài `src/` dùng. {code}

### [x] `InflammationLevel`
1. in/out: `Literal["none","mild","moderate","severe","unknown"]`. {code} `[clinical.py:15]`
2. side effect: không. {code}
3. state: không đọc, không ghi. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: chỉ `NormalizedAcneCase.inflammation_level` `[clinical.py:61]`. **0 tham chiếu ngoài file.** `AcneClinicalInput.inflammation_level` `[core.py:61-63]` khai lại y hệt bằng tay thay vì dùng alias này. {code}
7. invariant: năm bậc phải khớp `core.py:61-63` — hiện khớp, nhưng là trùng lặp thủ công, sửa một bên là lệch. {code}
8. deprecated/TODO: không. {code}

### [x] `ClinicalDemographics`
1. in/out: pydantic model. Field: `age: int|None` (ge=0, le=120), `sex` Literal 4 giá trị mặc định `"unknown"`, `skin_type` Literal 6 giá trị mặc định `"unknown"`, `is_pregnant: bool=False`, `is_breastfeeding: bool=False`. {code} `[clinical.py:18-27]`
2. side effect: không — thuần dữ liệu. {code}
3. state: không đọc global, không ghi global. {code}
4. lỗi: `extra="forbid"` `[clinical.py:19]` nên field lạ ném `ValidationError`; `age` ngoài [0,120] cũng ném. Không bắt, để nổi lên caller. {code}
5. config/env: không. {code}
6. ai gọi: chỉ `NormalizedAcneCase.demographics` `[clinical.py:33]`. **0 tham chiếu ngoài file.** {code}
7. invariant: `sex` ở đây có `"unknown"` còn `UserContext.sex` `[core.py:32]` **không có** và mặc định `None` — hai model mô tả cùng một khái niệm bằng hai bảng giá trị khác nhau. {code}
8. deprecated/TODO: không. {code}

### [x] `NormalizedAcneCase`
1. in/out: pydantic model, 15 field: `demographics`, `lesion_types` (Literal 11 giá trị), `distribution` (Literal 12 giá trị), `inflammation_level`, cộng 11 list `str`/`float` mặc định rỗng. {code} `[clinical.py:30-72]`
2. side effect: không. {code}
3. state: không đọc, không ghi. {code}
4. lỗi: `extra="forbid"` `[clinical.py:31]` → `ValidationError` khi có field lạ hoặc giá trị ngoài Literal. Không bắt. {code}
5. config/env: không. {code}
6. ai gọi: `research/LLMData/chunk_qa/generator.py:7`, `research/LLMData/chunk_qa/safety_cases.py:42`, `research/LLMData/clinical_case/schema.py:8`, `tests/test_chunk_qa_clinical_factory.py:7`. Trong `src/` **0 tham chiếu** — nó chỉ phục vụ sinh dữ liệu ngoại tuyến, không nằm trên đường chạy request. {code}
7. invariant: `lesion_types` và `distribution` phải khớp `AcneClinicalInput` `[core.py:48-77]`; kiểm tay thì trùng khít nhưng field ở đây tên `distribution` còn bên kia tên `lesion_distribution`. {code}
8. deprecated/TODO: không. {code}

### [x] chú thích cuối file (`clinical.py:75`)
1. in/out: không phải symbol; là lời khai. {comment}
2. side effect: không. {comment}
3. state: không. {comment}
4. lỗi: không. {comment}
5. config/env: không. {comment}
6. ai gọi: không. {comment}
7. invariant: khai rằng `ClinicalRagQueries` và `ClinicalQueryPlan` đã gỡ. **Kiểm ngược bằng code**: `tests/test_clinical_planner.py:10` assert `src/acne_llm/llm/clinical_planner.py` KHÔNG tồn tại, và `:13-14` assert `clinical_schemas` không còn hai attribute đó. Lời khai khớp code. {test}
8. deprecated: chính nó là dấu "đã gỡ có chủ ý", không phải code chết bỏ quên. {comment}

---

## `core.py`

### [x] `VisionLesion`
1. in/out: model, `type` Literal 7 giá trị, `bbox: list[float]|None`, `confidence: float` ge=0 le=1 **bắt buộc**. {code} `[core.py:9-13]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` + `confidence` thiếu → `ValidationError`. Không bắt. {code}
5. config/env: không. {code}
6. ai gọi: chỉ `VisionOutput.lesions` `[core.py:20]`. **0 tham chiếu ngoài `schemas/`.** {code}
7. invariant: `bbox` khai comment `[x, y, w, h] normalized` `[core.py:12]` nhưng **không có validator** ép độ dài 4 hay khoảng [0,1]. {code}
8. deprecated/TODO: không dấu; nhưng nhánh vision chưa có consumer nào trong `src/`. {code}

### [x] `VisionOutput`
1. in/out: model, `severity_estimate` Literal 4, `lesion_counts: dict[str,int]`, `lesions: list[VisionLesion]`, `skin_regions: list[str]`, `notes: str|None`, `model_name: str="mock"`, `confidence: float=0.5`. {code} `[core.py:16-24]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. `protected_namespaces=()` `[core.py:17]` tắt cảnh báo pydantic cho tiền tố `model_`. Không bắt lỗi. {code}
5. config/env: không. {code}
6. ai gọi: `UserInput.vision` `[core.py:94]` và `tests/test_schemas.py:3`. Trong `src/` **0 nơi gán giá trị**. {code}
7. invariant: `model_name` mặc định `"mock"` `[core.py:23]` — giả định ngầm rằng chưa có model vision thật; ai đọc field này mà không kiểm sẽ tưởng có. {code}
8. deprecated/TODO: không dấu. Là hợp đồng chờ "đề tài 27" theo docstring `[core.py:1]`. {doc}

### [x] `UserContext`
1. in/out: model, 9 field: `age: int|None` (0..120), `sex: Literal[male,female,other]|None`, `skin_type: Literal[6]|None`, `is_pregnant: bool=False`, `is_breastfeeding: bool=False`, `allergies/current_products/medications: list[str]`, `duration_weeks: int|None`. {code} `[core.py:29-40]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` `[core.py:30]` → `ValidationError`. Không bắt tại đây. {code}
5. config/env: không. {code}
6. ai gọi: `src/acne_llm/cli.py:16`, `chat/_intake_parse.py:9`, `chat/routing/rule_normalizer.py:20`, cộng 9 file test. Được `_OracleIntake` của eval ghi đè qua `model_copy` `[research/evaluation/runners/run_ablation.py:176-180]`. {code}
7. invariant: `is_pregnant`/`is_breastfeeding` là `bool` **không nullable** — mặc định `False` nghĩa là "chưa khai" và "khẳng định không" không phân biệt được ở tầng schema. Đây là giả định ngầm ảnh hưởng trực tiếp tới guardrail chống chỉ định. {code}
8. deprecated/TODO: `[core.py:33]` comment giải thích vì sao `skin_type` có `"unknown"`. Không có TODO/HACK. {comment}

### [x] `AcneClinicalInput`
1. in/out: model, 11 field: `lesion_types` Literal 11, `inflammation_level` Literal 5, `lesion_distribution` Literal 12, cộng 8 list mặc định rỗng gồm `red_flags_input`. {code} `[core.py:42-86]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` `[core.py:47]` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `chat/_intake_parse.py:9`, `chat/routing/intent_router.py:27`, `chat/routing/rule_normalizer.py:20`, 5 file test. `_safety.get_safety_suffix` đọc `user.clinical.red_flags_input` `[src/acne_llm/chat/_safety.py:318]`. {code}
7. invariant: docstring `[core.py:43-46]` khai "additive, client cũ chỉ gửi description/context vẫn chạy" — khớp code vì `UserInput.clinical` là `Optional=None` `[core.py:93]`. {doc}
8. deprecated/TODO: không dấu. Trùng lặp cấu trúc với `NormalizedAcneCase` nhưng khác tên field (`distribution` vs `lesion_distribution`). {code}

### [x] `UserInput`
1. in/out: model, `description: str` min_length=1 max_length=4000 **bắt buộc**, `context: UserContext`, `clinical: AcneClinicalInput|None`, `vision: VisionOutput|None`, `mode: Literal["llm_only","hybrid"]="hybrid"`. {code} `[core.py:89-95]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `description` rỗng hoặc >4000 ký tự → `ValidationError`. `extra="forbid"`. Không bắt tại đây; tầng API chặn trước bằng `MAX_MESSAGE_CHARS` `[src/acne_llm/api/routes/chat.py:26]`. {code}
5. config/env: không trực tiếp; giới hạn 4000 là hằng cứng trong schema, khác với `MAX_MESSAGE_CHARS` khai ở `chat/intake.py`. {code}
6. ai gọi: 14 chỗ trong `src/` gồm `cli.py:16`, `config.py:56`, `chat/intake.py:13`; 12 file test; `research/evaluation/adapters/_repo.py:57`. Đây là symbol trung tâm nhất của module. {code}
7. invariant: `mode` mặc định `"hybrid"` — mọi caller không nói gì thì mặc nhiên bật RAG. `prepare_chat_turn` quyết mode thật `[src/acne_llm/chat/orchestrator.py:88]` chứ không đọc field này. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `RetrievedChunk`
1. in/out: model, `chunk_id: str`, `source: str`, `text: str`, `score: float`, `metadata: dict` — bốn field đầu **bắt buộc**. {code} `[core.py:100-106]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `chat/_retrieval.py:8`, `rag/reranker.py:6`, `rag/retriever.py:9`, 7 file test, `research/evaluation/runners/run_ablation.py:64` (oracle dựng chunk giả). {code}
7. invariant: `score` **không có ràng buộc khoảng** — retriever thật đưa điểm rerank, oracle của eval đưa `relevance_grade` 1 hoặc 2 `[run_ablation.py:415]`. Hai thang khác nhau nằm chung một field; đã kiểm `llm/prompt_builder.py` không đọc `score` nên không rò vào prompt. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `RetrievalOutput`
1. in/out: model, `query: str`, `chunks: list[RetrievedChunk]` **bắt buộc**, `retrieval_mode` Literal 4 mặc định `"hybrid"`, `num_chunks: int=0`, `avg_score: float=0.0`. {code} `[core.py:109-115]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `chat/orchestrator.py:11`, `chat/_retrieval.py:8`, `llm/prompt_builder.py:6`, 7 test, `research/evaluation/runners/run_ablation.py:64`, `research/dashboards/architecture/build_drawio.py:403`. {code}
7. invariant: `num_chunks` là field lưu trữ, **không tự suy từ `len(chunks)`** — hai giá trị có thể lệch nếu caller quên; `_oracle_retrieval` gán tay `[run_ablation.py:426]`. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `Recommendation`
1. in/out: model, `step: int` ge=1 **bắt buộc**, `action: str` **bắt buộc**, `rationale: str|None`, `source_chunk_id: str|None`, `category` Literal 6 mặc định `"other"`. {code} `[core.py:120-134]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `step < 1` hoặc thiếu `action` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `AdviseOutput.recommendations` `[core.py:149]` và `tests/test_schemas.py:3`. Trong `src/` **0 nơi khởi tạo** — đường chạy chat sinh văn xuôi, không sinh object này. {code}
7. invariant: giả định output có cấu trúc từng bước; giả định này đã hết hiệu lực từ khi chuyển sang prose streaming. {code}
8. deprecated: `source_chunk_id` khai `json_schema_extra={"deprecated": True}` và description "Deprecated compatibility field; not required or validated" `[core.py:125-131]`. {code}

### [x] `RedFlag`
1. in/out: model, `flag: str` **bắt buộc**, `severity` Literal `["info","warn","urgent"]` mặc định `"warn"`, `reason: str|None`. {code} `[core.py:137-141]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `guardrails/runner.py:26` và `tests/test_schemas.py:3`. {code}
7. invariant: thang `severity` ở đây (3 bậc) khác thang `Severity` của bệnh (4 bậc) `[clinical.py:14]` — cùng tên field, khác nghĩa. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `AdviseOutput`
1. in/out: model, 11 field gồm `severity` Literal 4, `acne_type_primary: str="unknown"`, `causes/recommendations/red_flags/used_chunks` list rỗng, `confidence: float=0.5` (0..1), `disclaimer: str` mặc định câu tiếng Việt cứng, `mode`, `model_name: str=""`, `latency_ms: int=0`. {code} `[core.py:144-156]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"`, `protected_namespaces=()` cho `model_name`. `ValidationError` không bắt. {code}
5. config/env: không. {code}
6. ai gọi: `chat/intake.py:13`, `chat/runtime.py:219`, `guardrails/runner.py:26`, `tests/test_chat_stream.py:26`, `tests/test_schemas.py:3`, `research/dashboards/architecture/build_drawio.py:337`. {code}
7. invariant: `disclaimer` `[core.py:153]` là **bản cứng thứ hai** trong repo; bản đang thật sự chèn cho người dùng là `_GENERIC_DISCLAIMER_VI` `[src/acne_llm/chat/_safety.py:117-121]`, câu chữ khác nhau. Hai nguồn chân lý cho cùng một disclaimer. {code}
8. deprecated: `[src/acne_llm/chat/orchestrator.py:104-106]` comment ghi tầng hậu kiểm cũ dựa trên `AdviseOutput` đã bị xoá ở Phase 3 — object này còn tồn tại nhưng đường chạy chat không sinh ra nó nữa. {comment}

### [x] docstring `core.py:1`
1. in/out: lời khai, không phải symbol. {doc}
2. side effect: không. {doc}
3. state: không. {doc}
4. lỗi: không. {doc}
5. config/env: không. {doc}
6. ai gọi: không. {doc}
7. invariant: khai "contract với vision (đề tài 27) và RAG (đề tài 28)". **Kiểm ngược**: phần RAG đúng — `RetrievedChunk`/`RetrievalOutput` có 4-6 caller trong `src/`. Phần vision **không có consumer nào** trong `src/`; `VisionOutput` chỉ xuất hiện như field optional. Lời khai đúng một nửa. {code}
8. deprecated: không dấu, nhưng nhánh vision là hợp đồng chưa được nối. {doc}

---

## `extraction.py`

### [x] `T`
1. in/out: `TypeVar("T")`, tham số kiểu generic. {code} `[extraction.py:16]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: `FieldResult(Generic[T])` `[extraction.py:42]`, `ListFieldResult(Generic[T])` `[extraction.py:102]`. Không dùng ngoài file. {code}
7. invariant: không ràng buộc (`bound` không đặt) nên `FieldResult` chấp nhận mọi kiểu. {code}
8. deprecated/TODO: không. {code}

### [x] `Method`
1. in/out: `TypeAlias = Literal["exact","pattern","fuzzy","fallback","llm","none"]`. {code} `[extraction.py:19]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không tự kiểm — chỉ là gợi ý kiểu tĩnh, runtime không chặn giá trị lạ vì `FieldResult` là dataclass thường, không phải pydantic. {code}
5. config/env: không. {code}
6. ai gọi: `METHOD_BASE_CONFIDENCE` `[:22]`, `FieldResult.method` `[:59]`, `FieldResult.make` `[:79]`. **0 import ngoài file** dù có tên trong `__init__.__all__` `[__init__.py:20]`. {code}
7. invariant: `"llm"` phải luôn đi kèm `confidence` truyền tay vì base bằng 0.0 `[:27]` — quy ước bằng comment, không có assert. {code}
8. deprecated/TODO: không. {code}

### [x] `METHOD_BASE_CONFIDENCE`
1. in/out: `dict[Method,float]` 6 khoá: exact 0.95, pattern 0.85, fuzzy 0.80, fallback 0.45, llm 0.0, none 0.0. {code} `[extraction.py:22-29]`
2. side effect: không — dict module-level **có thể bị sửa tại chỗ**, không đóng băng. {code}
3. state: đọc bởi `FieldResult.make` `[:92]`; không ghi ở đâu. {code}
4. lỗi: `.get(method, 0.0)` `[:92]` nên method lạ ra 0.0 chứ không ném. {code}
5. config/env: không — sáu số này là hằng cứng, không đọc `settings`. {code}
6. ai gọi: chỉ `FieldResult.make` `[:92]`. **0 tham chiếu ngoài file.** {code}
7. invariant: comment `[:21]` khai "heuristic khởi điểm; golden set sẽ tinh chỉnh" — tức các số này **chưa được hiệu chỉnh bằng dữ liệu**. {comment}
8. TODO ngầm: "golden set sẽ tinh chỉnh" là việc chưa làm, không có TODO tag chính thức. {comment}

### [x] `clamp01`
1. in/out: `(x: float) -> float`, trả về x kẹp vào [0.0, 1.0]. {code} `[extraction.py:32-38]`
2. side effect: không. {code}
3. state: không đọc, không ghi. {code}
4. lỗi: không bắt gì; `x` là `NaN` thì cả hai so sánh đều False nên **trả về NaN** — không có nhánh xử lý. {code}
5. config/env: không. {code}
6. ai gọi: `FieldResult.__post_init__` `[:64]`, `FieldResult.make` `[:95]`, `tests/test_extraction_fieldresult.py:2`. Có trong `__all__` `[__init__.py:20]` nhưng **0 import ngoài file** trong `src/`. {code}
7. invariant: mọi confidence trong hệ phải nằm [0,1] — file này là chỗ ép duy nhất. {code}
8. deprecated/TODO: không. {code}

### [x] `FieldResult`
1. in/out: `@dataclass(frozen=True)` generic. Field: `value: T|None`, `confidence: float=0.0`, `method: Method="none"`, `evidence: str=""`. {code} `[extraction.py:41-60]`
2. side effect: không. {code}
3. state: không đọc global; ghi chính nó qua `object.__setattr__` trong `__post_init__`. {code}
4. lỗi: `frozen=True` nên gán sau khởi tạo ném `FrozenInstanceError`; không có nhánh bắt. {code}
5. config/env: không. {code}
6. ai gọi: `chat/_intake_parse.py:10`, `chat/routing/rule_extractor.py:8`, `tests/test_confidence_behavior.py:9`, `tests/test_extraction_fieldresult.py:1`, `research/evaluation/runners/run_ablation.py:65` (oracle bơm confidence 1.0). {code}
7. invariant: docstring `[:43-55]` khai "với method fuzzy thường bằng similarity" — quy ước, không ép bằng code. {doc}
8. deprecated/TODO: không dấu. {code}

### [x] `FieldResult.__post_init__`
1. in/out: `() -> None`. {code} `[extraction.py:62-64]`
2. side effect: ghi đè thuộc tính của chính instance qua `object.__setattr__` — vượt rào `frozen`. {code}
3. state: đọc `self.confidence`, ghi `self.confidence`. {code}
4. lỗi: không có nhánh lỗi. {code}
5. config/env: không. {code}
6. ai gọi: pydantic/dataclass gọi tự động sau `__init__`. Nó gọi `clamp01` `[:64]`. {code}
7. invariant: đảm bảo **mọi** `FieldResult` dựng bằng constructor đều có confidence trong [0,1], kể cả khi bỏ qua `make`. {code}
8. deprecated/TODO: comment `[:63]` giải thích vì sao dùng `object.__setattr__` — là ghi chú kỹ thuật, không phải HACK bỏ quên. {comment}

### [x] `FieldResult.is_confident`
1. in/out: `(threshold: float) -> bool`. {code} `[extraction.py:66-68]`
2. side effect: không. {code}
3. state: đọc `self.value`, `self.confidence`; không ghi. {code}
4. lỗi: không bắt; `threshold` không được kiểm khoảng. {code}
5. config/env: không trực tiếp — ngưỡng do caller truyền, lấy từ `settings` ở tầng trên. {code}
6. ai gọi: `ListFieldResult.confident_values` `[:121]`, `tests/test_extraction_fieldresult.py:19`, `tests/test_llm_extractor.py:139`. **0 caller trực tiếp trong `src/`.** {code}
7. invariant: `value is None` luôn cho `False` bất kể confidence — "không có giá trị" không bao giờ được coi là chắc. {code}
8. deprecated/TODO: không. {code}

### [x] `FieldResult.none`
1. in/out: classmethod `() -> FieldResult[T]`, trả `value=None, confidence=0.0, method="none", evidence=""`. {code} `[extraction.py:70-73]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: `FieldResult.make` khi `value is None` `[:91]`, và 6 `default_factory` trong `ExtractionConfidence` `[:132-138]`. {code}
7. invariant: là "giá trị rỗng chuẩn" duy nhất — code khác không được tự dựng biến thể rỗng khác. {code}
8. deprecated/TODO: không. {code}

### [x] `FieldResult.make`
1. in/out: `(value: T|None, method: Method, *, confidence: float|None=None, evidence: str="", adjust: float=0.0) -> FieldResult[T]`. {code} `[extraction.py:75-98]`
2. side effect: không. {code}
3. state: đọc `METHOD_BASE_CONFIDENCE`; không ghi. {code}
4. lỗi: `value is None` → trả `none()` sớm `[:90-91]`, không ném. Method lạ → base 0.0 qua `.get` `[:92]`. {code}
5. config/env: không. {code}
6. ai gọi: `research/evaluation/runners/run_ablation.py:271,278` (`_inject_oracle_confidence` gán confidence 1.0, evidence `"oracle_user_context"`); `chat/routing/rule_extractor.py`. Nó gọi `clamp01` `[:95]` và `cls.none` `[:91]`. {code}
7. invariant: `confidence` truyền tay **ghi đè** base của method, `adjust` cộng sau cùng rồi mới kẹp — thứ tự này quyết định kết quả và chỉ được mô tả trong docstring `[:85-88]`, không có test nào trong `tests/` khoá thứ tự đó. {doc}
8. deprecated/TODO: không. {code}

### [x] `ListFieldResult`
1. in/out: `@dataclass(frozen=True)` generic, một field `items: tuple[FieldResult[T],...]` mặc định rỗng. {code} `[extraction.py:101-109]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `frozen=True` → gán sau khởi tạo ném. Không bắt. {code}
5. config/env: không. {code}
6. ai gọi: `api/routes/chat.py:101`, `chat/confidence_hint.py:53`, `chat/_intake_parse.py:10`, `tests/test_confidence_behavior.py:9`, `tests/test_extraction_fieldresult.py:2`, `run_ablation.py:65`. {code}
7. invariant: dùng `tuple` chứ không `list` để giữ tính bất biến — nhưng `field(default_factory=tuple)` `[:109]` không chặn caller truyền `list`, lúc đó mất bất biến trong im lặng. {code}
8. deprecated/TODO: không. {code}

### [x] `ListFieldResult.values`
1. in/out: property `-> list[T]`, lọc bỏ item có `value is None`. {code} `[extraction.py:111-113]`
2. side effect: không. {code}
3. state: đọc `self.items`; không ghi. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: docstring `[:105-107]` khai "cho code ráp UserInput như cũ". Không tìm thấy caller trực tiếp trong `src/` khi grep `\.values` bị nhiễu bởi `dict.values`; **chưa rõ** caller chính xác. {code}
7. invariant: bỏ `None` im lặng — độ dài `values` có thể nhỏ hơn `items`, ai đếm bằng `len(values)` sẽ mất dấu item hỏng. {code}
8. deprecated/TODO: không. {code}

### [x] `ListFieldResult.max_confidence`
1. in/out: property `-> float`, `max` các confidence, mặc định 0.0 khi rỗng. {code} `[extraction.py:115-117]`
2. side effect: không. {code}
3. state: đọc `self.items`. {code}
4. lỗi: `default=0.0` `[:117]` nên tuple rỗng không ném `ValueError`. {code}
5. config/env: không. {code}
6. ai gọi: `chat/confidence_hint.py:53`, `tests/test_extraction_confidence.py:36`, `tests/test_extraction_fieldresult.py:55`. {code}
7. invariant: lấy **max** chứ không phải trung bình — một item chắc chắn kéo cả list lên. {code}
8. deprecated/TODO: không. {code}

### [x] `ListFieldResult.confident_values`
1. in/out: `(threshold: float) -> list[T]`. {code} `[extraction.py:119-121]`
2. side effect: không. {code}
3. state: đọc `self.items`. {code}
4. lỗi: không. {code}
5. config/env: ngưỡng do caller truyền. {code}
6. ai gọi: `chat/session/view.py:102`, `tests/test_extraction_fieldresult.py:56`, `tests/test_llm_extractor.py:142`. Nó gọi `FieldResult.is_confident` `[:121]`. {code}
7. invariant: chỉ giữ item vừa có `value` vừa đạt ngưỡng. {code}
8. deprecated/TODO: không. {code}

### [x] `ListFieldResult.empty`
1. in/out: classmethod `() -> ListFieldResult[T]` với `items=()`. {code} `[extraction.py:123-125]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: 9 `default_factory` trong `ExtractionConfidence` `[:139-147]`. {code}
7. invariant: giá trị rỗng chuẩn cho list field. {code}
8. deprecated/TODO: không. {code}

### [x] `ExtractionConfidence`
1. in/out: `@dataclass` **không frozen**, 16 field: 7 `FieldResult` (skin_type, sex, age, duration_weeks, is_pregnant, is_breastfeeding, inflammation) và 9 `ListFieldResult`. {code} `[extraction.py:128-147]`
2. side effect: không; nhưng vì không frozen nên **caller sửa tại chỗ được**. {code}
3. state: không đọc global; bị ghi bởi `dataclasses.replace` ở `run_ablation._inject_oracle_confidence` `[research/evaluation/runners/run_ablation.py:283]`. {code}
4. lỗi: không có validator — gán sai kiểu không bị chặn ở runtime. {code}
5. config/env: không. {code}
6. ai gọi: `chat/confidence_hint.py:8`, `chat/intake.py:20`, `chat/_intake_parse.py:11`, `tests/test_confidence_behavior.py:9`, `tests/test_intake.py:584`. **Không có trong `__init__.__all__`** dù có 4 caller trong `src/`. {code}
7. invariant: tên field ở đây phải khớp bảng `_CONTEXT_TO_CONFIDENCE` `[run_ablation.py:239-249]` — bảng đó ánh xạ `current_products → products` và `medications → medications`; lệch tên là oracle bơm hụt trong im lặng. {code}
8. deprecated/TODO: không dấu. Docstring `[:130]` gọi nó là "kênh phụ cho completeness/router" nhưng `check_completeness` **không còn caller nào** trong `src/` — một nửa lý do tồn tại đã mất. {code}

### [x] `ExtractionConfidence.field`
1. in/out: `(name: str) -> FieldResult | ListFieldResult`, thuần `getattr`. {code} `[extraction.py:149-150]`
2. side effect: không. {code}
3. state: đọc thuộc tính chính nó. {code}
4. lỗi: tên sai → `AttributeError` **không bắt**, không có giá trị mặc định. {code}
5. config/env: không. {code}
6. ai gọi: không tìm thấy caller nào trong `src/`, `tests/`, `research/` — **chưa rõ** có phải code chết không, vì `getattr` động có thể gọi qua tên chuỗi ở nơi grep không bắt được. {code}
7. invariant: giả định caller biết tên field đúng; không có danh sách hợp lệ để kiểm. {code}
8. deprecated/TODO: không dấu. {code}

### [x] docstring `extraction.py:1-10`
1. in/out: lời khai. {doc}
2. side effect: không. {doc}
3. state: không. {doc}
4. lỗi: không. {doc}
5. config/env: không. {doc}
6. ai gọi: không. {doc}
7. invariant: khai ba điều. (a) "Mọi extractor rule-based trả về FieldResult" — **kiểm ngược**: `chat/routing/rule_extractor.py:8` có import, khớp. (b) "confidence suy ra từ match, không phải ML/calibration" — khớp `METHOD_BASE_CONFIDENCE` là hằng cứng `[:22-29]`. (c) "để completeness/intent_router biết chắc đến đâu" — **lệch**: `check_completeness` không còn caller nào trong `src/`, nên vế completeness đã chết. {code}
8. deprecated: vế (c) của docstring là lời khai quá hạn. {doc}

---

## `kb.py`

### [x] `SourceType`
1. in/out: `Literal` 10 giá trị: nice_guideline, aad_guideline, jid_paper, pubmed_review, clinical_textbook, vi_medical_site, en_medical_site, forum_post, blog, unknown. {code} `[kb.py:8-19]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không tự kiểm; pydantic ép tại `SourceMeta.source_type` `[:90]` và `KBChunk.source_type` `[:126]`. {code}
5. config/env: không. {code}
6. ai gọi: `infer_source_type` `[:37]`, `SourceMeta` `[:90]`, `KBChunk` `[:126]`, `research/guideline_docs/build_guideline_chunks.py:63`. **0 tham chiếu trong `src/` ngoài chính file này.** {code}
7. invariant: 10 giá trị này phải phủ hết nhãn trong KB thật; eval khâu 2 báo cáo theo `source_type` `[research/evaluation/runners/run_retrieval.py:120]` nên nhãn lạ sẽ rơi vào `"?"`. {code}
8. deprecated/TODO: không dấu. `jid_paper` và `forum_post` không xuất hiện trong bảng phân bố của lần eval gần nhất — có khai mà không có dữ liệu. {code}

### [x] `_tokens`
1. in/out: `(value: str|list[str]|tuple[str,...]|None) -> str`; `None` → `""`; list/tuple → nối bằng space rồi `.lower()`; còn lại → `str(value).lower()`. {code} `[kb.py:22-27]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không bắt; mọi kiểu đều đi được qua nhánh `str(value)`. {code}
5. config/env: không. {code}
6. ai gọi: chỉ `infer_source_type` `[:43-44]`. Tên bắt đầu bằng `_` nên là nội bộ theo quy ước. {code}
7. invariant: luôn trả chữ thường — `infer_source_type` dựa vào đó để so khớp không phân biệt hoa thường. {code}
8. deprecated/TODO: không. {code}

### [x] `infer_source_type`
1. in/out: keyword-only `(source_name="", domain="", url="", tags=None, categories=None) -> SourceType`. {code} `[kb.py:30-83]`
2. side effect: không — thuần hàm, không I/O. {code}
3. state: không đọc global ngoài hai tuple hằng cục bộ `_VI_MEDICAL` `[:62-69]` và `_EN_MEDICAL` `[:73-80]` dựng lại mỗi lần gọi. {code}
4. lỗi: không có nhánh lỗi; không khớp gì thì trả `"unknown"` `[:83]`. {code}
5. config/env: không — toàn bộ danh sách domain là hằng cứng trong code, không đọc file cấu hình. {code}
6. ai gọi: `crawler/sources/generic_html.py:8`, `llm/prompt_builder.py:7`, `rag/retriever.py:10`. Nó gọi `_tokens` `[:43-44]`. {code}
7. invariant: **thứ tự if quyết định kết quả** — `"medical"` nằm trong `_VI_MEDICAL` `[:68]` nên một trang tiếng Anh có chữ "medical" trong domain sẽ bị gán `vi_medical_site` trước khi tới nhánh `_EN_MEDICAL`. Khớp chuỗi con, không khớp token. {code}
8. deprecated/TODO: docstring `[:38]` khai "cho legacy chunk thiếu metadata source_type" — nhưng nó được `rag/retriever.py:10` gọi trên đường chạy truy vấn, không chỉ cho legacy. Lời khai hẹp hơn thực tế. {doc}

### [x] `SourceMeta`
1. in/out: model, `domain: str`, `source_name: str`, `crawled_at: datetime` **bắt buộc**; `source_type` mặc định `"unknown"`, `trust_level` Literal 3 mặc định `"medium"`, `language` Literal `["vi","en"]` mặc định `"vi"`, `robots_allowed: bool=True`, `license: str|None`. {code} `[kb.py:86-95]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` `[:87]`; thiếu `crawled_at` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `crawler/sources/generic_html.py:8`, `crawler/sources/pubmed.py:10`. {code}
7. invariant: `language` chỉ hai giá trị — KB thật là 60% vi / 40% en theo `research/evaluation/judges/context.py:3`, nên hợp đồng đủ, nhưng không có chỗ cho tài liệu đa ngữ. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `DocumentRaw`
1. in/out: model, `doc_id/url/title/text: str` và `source: SourceMeta` **bắt buộc**; `html_len/text_len: int=0`, `categories/tags: list[str]`, `summary: str|None`, `quality_score: float` 0..1 mặc định 0.5. {code} `[kb.py:98-110]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"`; `quality_score` ngoài [0,1] → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `crawler/sources/generic_html.py:8`, `crawler/sources/pubmed.py:10`, `research/dataset_viz/generate_report.py:204`, `research/dataset_viz/plot_datasets.py:1`. {code}
7. invariant: `text_len` là field lưu trữ, không tự suy từ `len(text)` — có thể lệch. {code}
8. deprecated/TODO: không dấu. {code}

### [x] `KBChunk`
1. in/out: model 16 field. Bắt buộc: `chunk_id`, `doc_id`, `text`, `url`, `title`, `source_name`. Tuỳ chọn: `text_len=0`, `position=0`, `prev_chunk_id/next_chunk_id: str|None`, `source_type="unknown"`, `trust_level="medium"`, `language="vi"`, `categories/tags` list rỗng, `embedding: list[float]|None`. {code} `[kb.py:113-132]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: `rag/vectorstore.py:4`, `research/guideline_docs/reembed_guideline.py:59`. {code}
7. invariant: `prev_chunk_id`/`next_chunk_id` `[:120-121]` là cơ sở để `make_eval_set.expand` nới một hạt giống thành 5 chunk vàng `[research/evaluation/datasets/make_eval_set.py:144-162]` — hai field này quyết định chất lượng bộ đề oracle nhưng không có ràng buộc nào bảo đảm chúng trỏ tới chunk tồn tại. {code}
8. deprecated/TODO: `embedding` `[:132]` giữ vector ngay trong model nhưng Chroma lưu vector riêng; không có dấu deprecated, và không rõ đường chạy nào điền field này. {code}

### [x] `LLMData`
1. in/out: model Alpaca-style, `id: str` và `output: str` **bắt buộc**, `instruction: str` bắt buộc, `input: str=""`, `metadata: dict`. {code} `[kb.py:135-148]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: **0 import thật**. Mọi kết quả grep cho chuỗi `LLMData` ngoài file này đều trỏ tới **thư mục** `research/LLMData/` — đã kiểm `tests/test_chunk_qa_clinical_factory.py:8-11` là `from LLMData.chunk_qa...` và `research/datagen/gates.py:767` là chữ trong docstring. Không có trong `__init__.__all__`. {code}
7. invariant: docstring `[:136-141]` khai `input` luôn rỗng — nếu đúng thì field này thừa. {doc}
8. deprecated: symbol chết — định nghĩa còn, người dùng không có. {code}

### [x] `Intent`
1. in/out: `Literal` 9 giá trị: ask_cause, ask_symptoms, ask_treatment, ask_medication, ask_routine, ask_safety, ask_comparison, ask_when_doctor, ask_general. {code} `[kb.py:151-161]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: không. {code}
5. config/env: không. {code}
6. ai gọi: **0**. Đã kiểm ba nơi grep khớp: `chat/_intent_patch.py:58` là chữ trong docstring, `tests/test_intent_routing.py` và `research/dashboards/generate_all.py:778` không import từ đây. Không có trong `__all__`. {code}
7. invariant: **xung đột khái niệm** — hệ đang chạy dùng `PrimaryIntent = Literal["advise","knowledge","clarify","reject"]` `[src/acne_llm/chat/routing/intent_router.py:32]`. Hai bảng intent khác nhau hoàn toàn cùng tồn tại trong repo. {code}
8. deprecated: symbol chết, và nguy hiểm hơn mức chết vì tên trùng khái niệm đang dùng. {code}

### [x] `ChatMessage`
1. in/out: model, `role: Literal["system","user","assistant"]`, `content: str`, cả hai **bắt buộc**. {code} `[kb.py:164-167]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: chỉ `QASample.messages` `[:177]`. **0 tham chiếu ngoài file.** {code}
7. invariant: ba vai này khớp định dạng ChatML mà `intake_eval.v2_1500.jsonl` dùng, nhưng bộ đề đó đọc bằng `json.loads` thô chứ không qua model này. {code}
8. deprecated/TODO: không dấu; chết theo `QASample`. {code}

### [x] `QASample`
1. in/out: model, `messages: list[ChatMessage]` mặc định rỗng, `metadata: dict[str,Any]` mặc định rỗng. {code} `[kb.py:170-178]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: **0 tham chiếu** ở bất kỳ đâu ngoài file. Không có trong `__all__`. {code}
7. invariant: docstring `[:171-175]` khai định dạng khớp Axolotl/LLaMA-Factory/Unsloth — **kiểm ngược**: notebook train thật đọc `roledatav2/output/export/acnellm_role_lora.jsonl` chứ không dựng object này. Lời khai không sai nhưng không được thực thi ở đâu. {doc}
8. deprecated: symbol chết. {code}

### [x] `EntityRecord`
1. in/out: model, `entity_id: str`, `entity_type: Literal[6]`, `name_vi: str` **bắt buộc**; `name_en: str|None`, `aliases/contraindications/related_chunk_ids/sources: list[str]`, `description: str=""`. {code} `[kb.py:181-195]`
2. side effect: không. {code}
3. state: không. {code}
4. lỗi: `extra="forbid"` → `ValidationError`. {code}
5. config/env: không. {code}
6. ai gọi: **0 tham chiếu ngoài `schemas/`** — nhưng **có trong `__init__.__all__`** `[__init__.py:19]`. Đây là symbol chết được xuất khẩu công khai. {code}
7. invariant: `contraindications` `[:193]` chồng vai với `config/drugs_acne.yaml` mà `guardrails` thật sự đọc — hai nguồn cho cùng loại tri thức, một cái đang chạy, một cái không. {code}
8. deprecated: symbol chết. {code}

### [x] docstring `kb.py:1`
1. in/out: lời khai một dòng `"""Knowledge base schemas."""`. {doc}
2. side effect: không. {doc}
3. state: không. {doc}
4. lỗi: không. {doc}
5. config/env: không. {doc}
6. ai gọi: không. {doc}
7. invariant: khai file là "schema cho knowledge base" — **lệch**: 4 trong 11 symbol (`LLMData`, `Intent`, `ChatMessage`, `QASample`) thuộc miền sinh dữ liệu fine-tune, không thuộc KB. {code}
8. deprecated: docstring quá hẹp so với nội dung thật. {doc}

---

## Câu hỏi cho chủ repo (Bước 3) — tối đa 10

Mỗi câu kèm đáp án tôi cho là đúng. Im lặng = tôi đoán đúng.

**Q-01** `EntityRecord` có trong `__all__` nhưng 0 caller. Xoá hay giữ?
→ Đáp án tôi chọn: **giữ, đánh dấu "hợp đồng chưa nối"**. Lý do: `contraindications` trùng vai `config/drugs_acne.yaml` đang chạy; xoá thì mất dấu ý định, mà giữ thì phải ghi rõ chưa dùng.

**Q-02** `kb.Intent` (9 giá trị ask_*) đối lập `PrimaryIntent` (4 giá trị) đang chạy. Giữ cái nào?
→ **Xoá `kb.Intent`**. `git log` cho thấy `routing/intent_router.py` là nhánh được sửa liên tục tới `024739b` (2026-08), còn `kb.Intent` không đổi từ lúc tạo.

**Q-03** `LLMData`, `QASample`, `ChatMessage` — chết hoàn toàn. Xoá?
→ **Xoá cả ba**. Pipeline sinh dữ liệu thật ghi JSONL thô, không qua pydantic.

**Q-04** `VisionLesion`/`VisionOutput` chưa có consumer. Giữ?
→ **Giữ**. Docstring `core.py:1` khai đây là hợp đồng với "đề tài 27"; đó là ranh giới liên đề tài, không phải code chết.

**Q-05** `Recommendation`/`AdviseOutput` không còn được sinh trên đường chat. Giữ?
→ **Giữ `AdviseOutput`** (còn 3 caller trong `src/`), **đánh dấu `Recommendation` là legacy** (0 caller `src/`).

**Q-06** `UserContext.sex` không có `"unknown"`, `ClinicalDemographics.sex` có. Thống nhất?
→ **Không đụng lúc này**. `UserContext` nằm trên đường chạy request và đang được eval ghi đè; đổi Literal là rủi ro `ValidationError` giữa lần chạy full eval. Ghi vào RỔ C để làm sau.

**Q-07** `InflammationLevel` khai ở `clinical.py:15` nhưng `core.py:61-63` khai lại bằng tay. Gom?
→ **Gom về một alias**, nhưng thuộc RỔ C và làm sau lần chạy eval.

**Q-08** `AdviseOutput.disclaimer` `[core.py:153]` khác câu chữ với `_GENERIC_DISCLAIMER_VI` `[_safety.py:117-121]`. Bản nào là chuẩn?
→ **`_safety.py` là bản đang thật sự tới người dùng**; `core.py:153` là bản chết. Lý do: chỉ `_safety` được `runtime.stream_chat_sse` gọi.

**Q-09** `ExtractionConfidence.field()` không tìm thấy caller. Chết hay gọi động?
→ **Chưa rõ, cần bạn xác nhận**. Tôi không tìm được lời gọi nào; nhưng vì nó là `getattr` theo tên chuỗi nên grep có thể sót.

**Q-10** Docstring `extraction.py:8` nói phục vụ "completeness/intent_router" nhưng `check_completeness` đã không còn caller. Sửa docstring?
→ **Sửa**, thuộc RỔ B. Bỏ vế completeness, giữ vế router.

---

## BƯỚC 4 — TỰ KIỂM

```
file trong module / file đã tick trong coverage.md   :   5 / 5
symbol đã liệt kê / symbol đã tick trong FINDINGS    :  42 / 42
mục 1-8 cần điền / mục đã điền                       : 368 / 368
```

42 symbol + 4 khối lời khai (docstring/comment phải kiểm ngược theo luật Bước 3)
= 46 khối × 8 mục = 368. Không còn dòng `[ ]`.
Số "chưa rõ" còn lại: **2** — `ListFieldResult.values` (caller chính xác) và `ExtractionConfidence.field` (có caller động hay không).
