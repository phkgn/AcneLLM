# TODO — truth-of-architecture remediation

> Historical backlog generated from the 2026-08-22 snapshot. Several items
> were completed or superseded by `SAFE_REMEDIATION_TASKS.md`; consult
> `RECONCILIATION.md` before implementing any remaining item.

Nguồn duy nhất: FINDINGS đã hoàn tất. File này không apply thay đổi.
⚠ = mặc định audit được dùng vì user không phản đối câu hỏi; phải review trước khi apply.

## RỔ A — sửa `.md` và doc

### `src.chat`

⚠ [A] `src.chat:Q-10` · src.chat
  hiện tại: mọi báo cáo eval sinh trước lần sửa sigmoid đều mang nhãn evidence sai

  `compute_evidence_quality` docstring ghi rõ: ngưỡng cũ 0.65/0.40 được chỉnh khi
  reranker còn sigmoid **hai lần**, dải điểm bị nén vào `[0.500, 0.731]`; trên dải
  đó 0.40 không bao giờ đạt tới nên nhãn `"weak"` là code chết và gần như mọi câu
  trả lời được gắn "bằng chứng tốt". Với khoá luận: bất kỳ số liệu evidence_quality
  nào trong `research/evaluation/reports/` sinh trước commit sửa sigmoid đều không
  dùng được. Cần đối chiếu ngày commit với ngày các report khi duyệt
  `research/evaluation/`. {code}

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `.audit/FINDINGS/src.chat.md:1719`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

### `src.chat.routing`

⚠ [A] `src.chat.routing:Q-01` · src.chat.routing
  hiện tại: `llm_router.py` và `llm_extractor.py` (265 dòng) không chạy ở cấu hình hiện tại

  `di.py:133` rẽ nhánh theo `intake_mode`; hai file này chỉ được
  `import` **bên trong nhánh `else`** (`di.py:165-166`). `.env` đặt
  `INTAKE_MODE=unified`, nên trong production Python còn chưa nạp chúng. Với khoá
  luận: hoặc ghi rõ trong báo cáo rằng đây là đường A/B giữ lại có chủ đích, hoặc
  xoá. Đừng để giám khảo tự phát hiện. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `di.py:133`, `di.py:165`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

⚠ [A] `src.chat.routing:Q-06` · src.chat.routing
  hiện tại: semantic router dùng sai đại lượng làm confidence

  `SemanticPrediction.route_decision:48` lấy `nearest_similarity`, tức độ giống với
  **một** láng giềng gần nhất, chứ không lấy `vote_margin` hay `vote_scores[top]`.
  Truy vấn có 9 láng giềng chia đều ba nhãn vẫn nhận confidence cao nếu láng giềng
  số 1 rất gần. Confidence này chảy thẳng vào `RouteDecision.confidence` và vào
  metadata/audit. Đề xuất: dùng `vote_scores[top]` hoặc tích hai đại lượng, và ghi
  lại lựa chọn trong báo cáo. {code}

  phải thành: dùng `vote_scores[top]` hoặc tích hai đại lượng, và ghi
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1851`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

⚠ [A] `src.chat.routing:Q-09` · src.chat.routing
  hiện tại: `RouteDecision.metadata` báo cáo intent thay cho turn_type

  `intent_router.py:52`: `self.turn_type if self.turn_type != "answer" else
  self.primary_intent`. Chỉ một nhánh (`crisis_signal`) từng đặt `turn_type`. Log
  và audit vì thế không phân biệt được "turn_type là advise" với "turn_type chưa
  bao giờ được đặt". {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `intent_router.py:52`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

⚠ [A] `src.chat.routing:Q-16` · src.chat.routing
  hiện tại: `EXTRACTOR_MODE=rule` không đạt được ở chế độ unified

  `di.py:162-163` ép `settings.extractor_mode = "llm"`. Hai file legacy
  (`rule_extractor.py`, `rule_normalizer.py`, tổng **2.381 dòng**) tự khai là
  "live fallback when `EXTRACTOR_MODE=rule` or the LLM extractor fails" — vế đầu
  không còn đạt được, nên đường sống duy nhất là intaker hỏng. Đây là số dòng lớn
  nhất của module và cần một câu trả lời rõ trong báo cáo: nó là fallback thật hay
  là di sản. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `di.py:162`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

### `src.chat.session`

⚠ [A] `src.chat.session:Q-05` · src.chat.session
  hiện tại: `memory.py` là test double sống trong `src/`

  Docstring của chính nó khai điều đó, và grep xác nhận: `get_session_store` được
  gọi 13 lần, **tất cả** trong `tests/`. 195 dòng code production-shaped mà không
  đường production nào chạy qua. Với khoá luận, đây là thứ giám khảo sẽ hỏi: hoặc
  chuyển vào `tests/`, hoặc ghi rõ trong báo cáo là in-memory reference
  implementation dùng để đối chiếu hành vi với bản SQLite. {code+doc}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `.audit/FINDINGS/src.chat.session.md:627`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

⚠ [A] `src.chat.session:Q-08` · src.chat.session
  hiện tại: ba nơi cùng tự nhận là "cổng tất định duy nhất còn lại"

  `fold.py:3-4` (nói `medication_safety_refusal` là cổng duy nhất),
  `guardrails/runner.py:1` (nói chính nó là cổng duy nhất), và `chat/_safety.py`
  (372 dòng khớp chuỗi tất định, `docs/rulebase_audit.md:161` xếp "Tier 5 — Giữ").
  Ba lời khai không thể cùng đúng. Cần một câu trả lời dứt khoát trước khi viết
  chương kiến trúc của báo cáo. {code+doc}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `fold.py:3`, `guardrails/runner.py:1`, `docs/rulebase_audit.md:161`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

### `src.config`

⚠ [A] `src.config:Q-09` · src.config
  hiện tại: `admin_api_key = ""` fail-closed, nhưng `api_key = ""` thì không rõ

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

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `chat/intake.py:748`, `chat/routing/intent_router.py:652`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

### `src.db`

⚠ [A] `src.db:Q-02` · src.db
  hiện tại: comment `base.py:8-10` là hoá thạch của kiến trúc đã bị thay hai lần

  Nó nói "sessions và turns đã chuyển sang JSONL (data/sessions/<id>.jsonl)".
  Thực tế bây giờ là SQLite (`session_store.py:35-56`), và `session_store.py:1`
  mô tả đúng bước đó ("một file sessions.db thay cho nhiều file JSONL"). Với báo
  cáo khoá luận, comment này sẽ dẫn người đọc sai về tầng lưu trữ. {code+comment}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `base.py:8`, `session_store.py:35`, `session_store.py:1`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

### `src.rag`

⚠ [A] `src.rag:Q-07` · src.rag
  hiện tại: `hnsw:space=cosine` chỉ áp lúc tạo collection

  `vectorstore.py:17-21`. Với collection đã tồn tại, `get_or_create_collection`
  giữ không gian cũ và bỏ qua metadata. Mọi lập luận về "distance = 1 − cosine"
  (`:99-100`, `config.py:239`) phụ thuộc vào việc `data/chroma_db` được tạo bằng
  chính dòng này. Với khoá luận: nên kiểm một lần
  (`col.metadata` / `col.configuration_json`) và ghi kết quả vào báo cáo. {code}

  phải thành: Đo/kiểm bằng artifact được nêu trước; chỉ sửa logic nếu phép đo xác nhận tác động.
  căn cứ: `vectorstore.py:17`, `config.py:239`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

[A] `src.rag:Q-14` · src.rag
  hiện tại: dedup near-duplicate là O(n²) trên mỗi tài liệu, giữ toàn bộ shingle set

  `chunker.py:~150`. Tài liệu 100 chunk → 4.950 phép Jaccard, mỗi phép trên hai set
  ~1.200 phần tử. Chỉ chạy lúc build KB nên chấp nhận được; ghi lại để không ai
  gọi `chunk()` trên đường nóng. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `chunker.py:150`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

### `src.schemas`

[A] `src.schemas:Q-10` · src.schemas
  hiện tại:

  Docstring `extraction.py:8` nói phục vụ "completeness/intent_router" nhưng `check_completeness` đã không còn caller. Sửa docstring?
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

  phải thành: **Sửa**, thuộc RỔ B. Bỏ vế completeness, giữ vế router.
  căn cứ: `extraction.py:8`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.

### `src.utils`

⚠ [A] `src.utils:Q-07` · src.utils
  hiện tại: log của API server nằm trong file tên `crawl_*.log`

  `logging.py:168`. `api/app.py:24` gọi `configure_logging` và nhận tên file đó.
  Tàn dư từ thời module chỉ phục vụ crawler. Sửa một dòng; đáng sửa vì báo cáo
  khoá luận sẽ có ảnh chụp thư mục log. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `logging.py:168`, `api/app.py:24`
  rủi ro nếu sửa sai: Sai tài liệu có thể làm người vận hành/giám khảo dùng nhầm flow; sửa sai không đổi runtime nhưng làm mất provenance lịch sử.


## RỔ B — sửa comment/docstring trong code

### `src.chat`

[B] `src.chat:Q-05` · src.chat
  hiện tại: lệch runtime↔eval: đây là nguyên nhân cơ học, đã truy tới dòng

  `orchestrator` là đường chuẩn bị **duy nhất** (lời khai đúng), nhưng bước **sinh**
  tách đôi:
  - production: `runtime.stream_chat_sse` → `c.llm.stream_text(...)`, và `:162`
    đặt `num_predict=-1` cho intent `knowledge` (không giới hạn độ dài);
  - eval/CLI: `orchestrator.generate_prose` → `c.llm.generate_text(...)`, hàm này
    **không có tham số `num_predict`** (`ollama_backend.py:222-224`), nên bị chặn
    ở `settings.llm_num_predict = 2048`.

  Thêm hai lệch phụ cùng nguồn: (a) `normalize_generated_prose` (cắt ký tự CJK)
  chỉ chạy ở đường non-stream — grep trong `runtime.py` = 0, nên ký tự Hán bị cắt
  khi eval nhưng **lọt tới người dùng thật**; (b) `runtime:228-229` gỡ cờ
  `urgency_red_flag` cho intent `knowledge` trước khi gọi `get_safety_suffix`,
  đường eval không có bước đó. Ba lệch này phải được nêu trong chương đánh giá,
  hoặc sửa trước khi chạy full eval. Cách sửa rẻ nhất cho (a): thêm `num_predict`
  vào `generate_text` (một dòng, `_sampling_options` đã nhận sẵn). {code}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `ollama_backend.py:222`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

[B] `src.chat:Q-11` · src.chat
  hiện tại: hợp đồng JSON chính thức không được ép ở đường production

  `_OLLAMA_JSON_SCHEMA` (schema đầy đủ) chỉ dùng bởi `llm_extractor` — đường
  legacy. `unified_intake._infer:116` gọi `response_format="json"` (JSON mode
  chung), với comment giải thích llama.cpp không parse nổi `anyOf`-null lồng nhau.
  Nên ở production, toàn bộ việc bảo vệ hợp đồng do các parser khoan dung làm, và
  chúng **drop im lặng**: enum bịa → `unknown`, item sai kiểu → biến mất, không log
  nào. Không có cách nào đo được model sai hợp đồng bao nhiêu lần. Đề xuất rẻ:
  đếm số field bị drop mỗi lượt và ghi vào `log_pipeline_stage("EXTRACT", ...)`. {code}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `.audit/FINDINGS/src.chat.md:1728`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

[B] `src.chat:Q-19` · src.chat
  hiện tại: tham số chết, tổng hợp toàn `chat/`

  `_resolve_mode(clean_text, history)` — 2 tham số, được người gọi tính rồi truyền;
  `_intake_parse` `prefix` — 6 hàm (Q-12); `_to_extraction_confidence(clean_text)`;
  `rule_extractor._context_adjust(span_hint)` và `_scalar(fallback_methods)`;
  `intent_router.select_relevant_history(message, route_flags)` — 2/4.
  Tổng **13 tham số chết** trong `chat/`. Không cái nào gây lỗi; cùng nhau chúng
  làm chữ ký hàm nói dối về thứ hàm thực sự dùng, và đó là thứ người đọc code
  (giám khảo) sẽ tin. Ngoại lệ đáng khen: `UnifiedIntake.run` viết
  `del clean_text_no_accent` ngay dòng đầu — tham số chết **có khai báo**. {code}

  ---

  ## §6 — Tự kiểm (Bước 4)

  - Khối khai báo ở Bước 0: **141**.
  - Tiêu đề `### [x]` đếm được: **123**. Chênh lệch do **hai tiêu đề gộp**, mỗi cái
    ghi rõ số khối nó phủ ngay trong tiêu đề:
    - `_safety.py` — **10 bảng term** dưới 1 tiêu đề → +9
    - `_intake_parse.py` — **10 hằng enum** dưới 1 tiêu đề → +9
    - Kiểm: 123 + 9 + 9 = **141**. Khớp.
  - Mục: 141 × 8 = **1.128**. Trong đó 20 khối thuộc hai nhóm nén có khai báo
    (20 × 4 = 80 mục phát biểu chung trong hai tiêu đề gộp, 20 × 4 = 80 mục khai
    riêng ở cùng chỗ), 121 khối còn lại viết đủ 8 mục tại chỗ (968 mục).
    Kiểm: 80 + 80 + 968 = **1.128**. Khớp.

  **Năm khẳng định đo bằng chạy thật, không đọc mắt:**
  1. `preprocess_user_text("em dùng BT-Cortin")` → không đổi;
     `"BT_Cortin"` → `"BT Cortin"` — bác bỏ lời khai trong docstring
     `prepare_user_text` (khối `_WORD_JOINER_RE`).
  2. `strip_accents("da đầu")` = `"da dau"` vs `_no_accent("da đầu")` = `"da đau"`;
     và 8 câu phủ định thử với `_NEG_CUES`, `"đừng dùng BHA"` không khớp cue nào (Q-02).
  3. So sha256 `model/intaker/Modelfile` SYSTEM với
     `unified_intake._RUNTIME_SYSTEM`: **bằng nhau** (`6ee28283b579feb8`) — điều
     này **bác bỏ** cách tôi viết Q-02 ban đầu ở `src.chat.routing.md`, đã sửa lại
     file đó.
  4. Đếm bằng `ast`: `AcneClinicalInput` 12 trường, `_to_user_input` truyền 6,
     liệt kê đủ 6 trường không truyền (Q-15).
  5. `grep normalize_generated_prose runtime.py` = 0 → bộ lọc CJK không chạy ở
     đường SSE (Q-05).

  **Ba lần tôi định ghi một khẳng định rồi tự bác bỏ trước khi chốt:**
  - `get_safety_suffix(recent_turns, current_turn_text)` — tôi định ghi là tham số
    chết; `runtime.py:238-239` có truyền và thân hàm có dùng. Đã sửa tại chỗ.
  - `src.rag` Q-08 — tôi đã ghi là vấn đề lớn nhất; `_retrieval` cho thấy hai cơ
    chế chặn hậu quả. Đã hạ mức và ghi đính chính (Q-09).
  - `src.chat.routing` Q-02 — tôi đã ghi "prompt không tới model" như một lỗi;
    đối chiếu Modelfile cho thấy đó là thiết kế đúng. Đã sửa file đó.

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `runtime.py:238`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

### `src.chat.routing`

⚠ [B] `src.chat.routing:Q-10` · src.chat.routing
  hiện tại: cờ `product_safety_check` bật trên mọi tin nhắn có dấu `+`

  `_SAFETY_PRODUCT_TERMS` chứa `"+"`, và `_contains_product_safety_term` chỉ dùng
  ranh giới từ cho `{aha, bha, bpo}`, còn lại khớp chuỗi con. Docstring nói ngược
  lại. Cờ này đi vào `chat/_safety` và `prompt_builder`. {code}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1875`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

### `src.chat.session`

⚠ [B] `src.chat.session:Q-07` · src.chat.session
  hiện tại: `select_relevant_history` có 2/4 tham số chết

  `view.py:33`: `del message, route_flags`. `chat/intake.py:572,731` vẫn tính và
  truyền chúng. Chữ ký nói hàm dùng nội dung tin nhắn và route flags để chọn
  history; thực tế nó chỉ nhìn `primary_intent`. Docstring `:28-31` giải thích lý
  do bỏ whitelist tiền tố nhưng không nói hai tham số đã thành vô nghĩa. {code+doc}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `view.py:33`, `chat/intake.py:572`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

⚠ [B] `src.chat.session:Q-09` · src.chat.session
  hiện tại: comment `fold.py:48-51` khai sai về chính dòng ngay dưới nó

  Comment nói nhánh alias "chưa từng khớp dữ liệu thật" vì intaker trả
  `"salicylic acid"` (dấu cách) còn key là `"salicylic_acid"` (gạch dưới). Nhưng
  `:51` làm đúng phép chuyển đó: `alias_key = value_lower.replace(" ", "_")`.
  Nhánh alias **có** khớp. Cần quyết: comment sai (xoá) hay code từng khác (thì
  comment là hoá thạch). Không phải lỗi hành vi, nhưng là lời khai sai trong file
  mà docstring gọi là "nguy hiểm nhất trong package". {code+comment}

  phải thành: comment sai (xoá) hay code từng khác (thì
  căn cứ: `fold.py:48`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

[B] `src.chat.session:Q-10` · src.chat.session
  hiện tại: nhánh chết ở `fold_history_facts`: `clinical` không bao giờ còn là None

  `:305` ép `inflammation_level = inflammation or "unknown"`. `:317-331` rồi tính
  `has_clinical = any((..., merged_clinical.inflammation_level, ...))`. Chuỗi
  `"unknown"` luôn truthy → `has_clinical` **luôn True** → `:333`
  `merged_clinical if has_clinical else None` không bao giờ trả None.
  Hệ quả thật: sau khi fold, `UserInput.clinical` luôn là object đầy đủ, kể cả với
  hai lượt liên tiếp không có một tín hiệu lâm sàng nào — đúng tổ hợp mà comment
  `:296-301` mô tả. Downstream nào phân biệt "có clinical" bằng
  `user.clinical is not None` sẽ luôn thấy True. Bản vá ValidationError đã vô hiệu
  hoá cái gác ngay dưới nó. Cần kiểm ở `src.chat` xem có ai dựa vào
  `clinical is None` không. {code}

  ---

  ## §6 — Tự kiểm (Bước 4)

  - Khối khai báo ở Bước 0: **44** (2 + 11 + 16 + 7 + 8)
  - Khối `### [x]` đếm được: 44 — khớp.
  - Mục: 44 × 8 = **352**.
  - Không dùng nén khai báo trong module này; mọi khối viết đủ 8 mục.

  **Đính chính đã áp trong lượt này:** ba khẳng định "0 caller" của tôi bị chính
  grep bác bỏ (`SESSION_SCHEMA_VERSION`, `increment_followup_count`,
  `active_count`). Đã sửa tại chỗ trước khi chốt, và ghi lại ở Q-02, Q-06.

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `.audit/FINDINGS/src.chat.session.md:661`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

### `src.config`

⚠ [B] `src.config:Q-01` · src.config
  hiện tại: `.env` đảo ngược một quyết định thiết kế được ghi rõ trong code

  `config.py:42-43` viết: "Timeout thấp để phép đo latency lộ request chậm thay
  vì che bằng env override", rồi đặt `ollama_generate_timeout: float = 30.0`.
  `.env` thật đang đặt `OLLAMA_GENERATE_TIMEOUT=300` — gấp 10 lần, tức đúng cái
  "che bằng env override" mà comment nói phải tránh. Mọi số latency đo trong eval
  đều chạy dưới trần 300s này. Cần quyết: sửa comment cho khớp thực tế, hay bỏ
  override trong `.env`. {code+comment}

  phải thành: sửa comment cho khớp thực tế, hay bỏ
  căn cứ: `config.py:42`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

⚠ [B] `src.config:Q-04` · src.config
  hiện tại: `di.py:163` ghi đè cấu hình người dùng

  `if getattr(settings, "extractor_mode", "llm") != "llm": settings.extractor_mode = "llm"`.
  Nghĩa là đặt `EXTRACTOR_MODE=rule` trong `.env` **không có tác dụng** — composition
  root ép về `"llm"`. Comment ngay trên (`di.py:160-161`) nói `intake.py` "cố tình
  không đổi và vẫn dùng `extractor_mode`". Field khai `Literal["llm","rule"]` nên
  schema hứa hai lựa chọn, runtime chỉ cho một. {code+comment}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `di.py:163`, `di.py:160`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

### `src.db`

⚠ [B] `src.db:Q-01` · src.db
  hiện tại: `base.py` docstring và `AuditStore` docstring cùng khai sai một điều

  `base.py:1` nói `DBConnection` "dùng chung cho session store và audit log";
  `audit.py:33` nói `AuditStore` "dùng chung DBConnection với session store". Cả
  hai sai: `session_store.py:77` tự `sqlite3.connect` vào **file DB khác**
  (`sessions.db` vs `audit.db`), và `session_store.py:5` nói thẳng là không phụ
  thuộc `db/base.py`. `DBConnection` có đúng một người dùng. {code+doc}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `base.py:1`, `audit.py:33`, `session_store.py:77`, `session_store.py:5`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

[B] `src.db:Q-06` · src.db
  hiện tại: `schema_version` chỉ được kiểm ở 2 trong 8 đường vào

  `_stale` (nơi duy nhất so `schema_version`) được gọi từ `_ensure` và
  `get_history`. `merge_user_context`, `get_user_context`,
  `increment_followup_count` chỉ gọi `_is_expired`. Nên một session lệch phiên bản
  schema vẫn đọc/ghi được `user_context` cho tới khi có ai gọi `get_history` hoặc
  `append_turn`. Docstring `:9` khai "schema_version lệch → reset session" không
  kèm điều kiện đó. {code+doc}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `.audit/FINDINGS/src.db.md:633`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

### `src.rag`

[B] `src.rag:Q-10` · src.rag
  hiện tại: `retrieve_safety_pass` có cổng khoảng cách lỏng hơn và bật fallback, khác đường chính

  `retrieve` truyền `max_distance=self.dense_max_distance` (0.60) và
  `fallback_to_raw=False`; `retrieve_safety_pass` không truyền cái nào → 0.65 và
  True. Nghĩa là pass an toàn/khuyến cáo — chạy cho **mọi** truy vấn — nhận chunk
  xa hơn và có thể rơi về kết quả **chưa lọc khoảng cách**. Comment
  `vectorstore.py:118-120` nói rõ "Chat retrieval disables this so a bad dense
  match cannot bypass the distance gate", nhưng pass thứ hai của chính chat lại
  không tắt. Xem Q-08 — hai câu hỏi này phải trả lời cùng nhau. {code+comment}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `vectorstore.py:118`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

### `src.utils`

⚠ [B] `src.utils:Q-01` · src.utils
  hiện tại: docstring `chunk_filter.py:1` trỏ vào file không tồn tại

  "used by both pipeline/hybrid.py and chat/runtime.py" — `pipeline/hybrid.py`
  grep = 0. Người dùng thật là `chat/_retrieval.py`. {code+doc}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `chunk_filter.py:1`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

⚠ [B] `src.utils:Q-02` · src.utils
  hiện tại: `find_in_text` không có tầng "review" như docstring khai

  `fuzzy_match.py:98-105`: hit giữa `review` và `accept` được tính rồi bị vứt ở
  dòng return. "Two-tier" trong docstring không tồn tại trong hành vi. Cần quyết:
  sửa docstring, hay trả về hai danh sách như đã hứa (nếu `rule_extractor.py` cần
  tầng review). {code+doc}

  phải thành: sửa docstring, hay trả về hai danh sách như đã hứa (nếu `rule_extractor.py` cần
  căn cứ: `fuzzy_match.py:98`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.

⚠ [B] `src.utils:Q-06` · src.utils
  hiện tại: thêm một lời khai nữa về "cổng tất định"

  Banner khởi động `logging.py:150` in `"cong tat dinh: injection, genital, thuoc"`
  — **ba** cổng. `chat/session/fold.py:3-4` nói `medication_safety_refusal` là cổng
  **duy nhất**; `guardrails/runner.py:1` nói chính nó là cổng **duy nhất**. Ba lời
  khai, ba nội dung. Đây là câu hỏi lặp lại từ `src.chat.session` Q-08 và
  `src.guardrails`; cần một câu trả lời dứt khoát trước khi viết chương kiến trúc. {code+comment}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `logging.py:150`, `chat/session/fold.py:3`, `guardrails/runner.py:1`
  rủi ro nếu sửa sai: Comment/docstring sai tiếp tục gây hiểu nhầm; sửa quá tay có thể biến claim thành điều code không bảo đảm.


## RỔ C — sửa code

### `src.chat`

⚠ [C] `src.chat:Q-01` · src.chat
  hiện tại: `teencode_replaced` luôn rỗng và vẫn được ghi vào audit DB

  `preprocess.prepare_user_text:70` gán cứng `[]`; giá trị đi qua
  `IntakeResult.teencode_replaced` vào `AuditEntry` và xuống cột
  `audit_log.teencode_replaced` dưới dạng `"[]"` cho mọi bản ghi. Comment `:53-56`
  giải thích vì sao bảng teencode bị xoá (train/serve skew) nhưng không dọn trường.
  Xoá được cả trường lẫn cột. {code}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `.audit/FINDINGS/src.chat.md:1637`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat:Q-02` · src.chat
  hiện tại: repo có hai hàm bỏ dấu, và một trong hai bỏ sót chữ `đ`

  `preprocess.strip_accents` NFD-tách dấu **rồi** `replace("đ","d")`;
  `utils/retrieval_query._no_accent` **thiếu** bước sau. Đo:
  `strip_accents("da đầu")` → `"da dau"`, `_no_accent("da đầu")` → `"da đau"`.
  Hệ quả đo được: `retrieval_query._NEG_CUES` viết bằng ASCII nên cue `"đừng dùng"`
  không khớp nổi văn bản đã qua `_no_accent`. Thử 8 câu phủ định — 7 khớp,
  `"đừng dùng BHA"` **không khớp cue nào**. Sửa một dòng: dùng chung
  `preprocess.strip_accents`. (Đây là bổ sung cho `src.utils`; tôi đã ghi chú
  chéo vào file đó.) {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1644`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-03` · src.chat
  hiện tại: `_intent_patch._demo` không nằm trong suite test

  8 assert bảo vệ đúng ranh giới an toàn quan trọng nhất của module (chỉ `clarify`
  được sửa), nhưng chúng chỉ chạy khi `python -m ...` trực tiếp. `pytest` không
  thấy. Đổi tên file thành `tests/test_intent_patch.py` hoặc thêm một wrapper là
  xong. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1654`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-04` · src.chat
  hiện tại: hai field an toàn nhất bị bỏ khỏi cơ chế hedging confidence

  `confidence_hint._OVERALL_WEIGHTS` có 10 field và **không** có `products`/
  `medications`; vòng lặp `build_confidence_hint:86-90` cũng duyệt đúng 10 tên đó.
  Nhưng `_FIELD_LABELS_VI` **có** nhãn cho cả hai (`"sản phẩm đang dùng"`,
  `"thuốc đang dùng"`) — hai nhãn không bao giờ in được. Đó là bằng chứng việc bỏ
  sót chứ không phải quyết định. Hậu quả: extractor trích sai tên thuốc với
  confidence thấp mà prompt **không** được cảnh báo, trong khi chính hai trường đó
  nuôi `medication_safety_refusal`. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1660`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-06` · src.chat
  hiện tại: `_DOSE_RE` dùng `[^\n]{0,90}` trong khi output có xuống dòng

  Model trả lời dạng Markdown bullet, tên thuốc và liều thường nằm hai dòng. Đo ở
  phiên trước: chỉ **3/38** câu bị đánh dấu sai an toàn khớp được regex này. Sửa:
  đổi `[^\n]` thành `[\s\S]` và giảm cửa sổ, hoặc chuẩn hoá xuống dòng trước khi
  hậu kiểm. {code}

  phải thành: đổi `[^\n]` thành `[\s\S]` và giảm cửa sổ, hoặc chuẩn hoá xuống dòng trước khi
  căn cứ: `.audit/FINDINGS/src.chat.md:1686`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-07` · src.chat
  hiện tại: cảnh báo khẩn cấp sống được nhờ một mệnh đề `or not _rf`

  `_safety:~320`: `"urgency_red_flag" in route_flags and ((_rf & _EMERGENCY_FLAGS)
  or not _rf)`. Vì `red_flags_input` **luôn rỗng** trên đường unified (Q-15),
  `_rf & _EMERGENCY_FLAGS` luôn rỗng, và chỉ `not _rf` giữ cho nhánh này chạy. Nếu
  ai đó "dọn" mệnh đề trông thừa ấy, cảnh báo khẩn cấp chết hoàn toàn ở production
  mà mọi test dùng dữ liệu rule vẫn xanh. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1692`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-08` · src.chat
  hiện tại: ba bản sao `_extract_json` và hai bản `rrf_fusion`

  `_intake_parse._extract_json` ≡ `llm_router._extract_json` (khác kiểu ngoại lệ);
  `_retrieval.rrf_fusion` ≡ `rag/retriever.rrf_fusion` (giống từng dòng). Sửa công
  thức RRF ở một chỗ thì chỗ kia lệch im lặng. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1699`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-12` · src.chat
  hiện tại: tham số `prefix` chết xuyên 6 hàm của `_intake_parse`

  `_scalar_node`, `_list_nodes`, `_enum_fr`, `_int_fr`, `_bool_fr`, `_lfr` đều nhận
  `prefix` và không hàm nào đọc. Dấu vết của cơ chế báo lỗi theo đường dẫn field đã
  gỡ. Cùng với Q-11 thì đây là gợi ý: `prefix` từng phục vụ đúng việc mà Q-11 đang
  thiếu. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1737`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-13` · src.chat
  hiện tại: `is_pregnant` mất trạng thái thứ ba ngay tại `_to_user_input`

  `_bool_fr` giữ được ba trạng thái (True/False/không rõ), nhưng `:~324`
  `is_pregnant = bool(pregnant.value)` ép về hai, vì `UserContext.is_pregnant` khai
  `bool` chứ không `bool | None`. Nên "không nhắc tới" và "nói rõ là không" không
  phân biệt được ở tầng schema. Đây là **cùng một khiếm khuyết** với đường rule
  (`src.chat.routing` Q-19) nhưng nguyên nhân khác: ở kia là regex phủ định không
  phạm vi, ở đây là kiểu dữ liệu. Sửa triệt để phải đổi schema. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1743`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-14` · src.chat
  hiện tại: `_lfr` không hạ chữ ở đúng những field dễ trùng nhất

  Khi `allowed` là None (allergies, products, medications, scarring_signs,
  hormonal_factors, treatment_goals) thì dedupe phân biệt hoa-thường, nên `"BHA"`
  và `"bha"` thành hai mục. Ba trong sáu field đó đi thẳng vào
  `confirmed_profile` và vào cổng thuốc. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1751`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat:Q-15` · src.chat
  hiện tại: đường production chỉ điền 3/12 trường lâm sàng

  Đếm bằng `ast`: `AcneClinicalInput` có **12** trường; `_to_user_input` truyền
  **6**; và system prompt của intaker quy định `clinical` chỉ gồm **3**
  (`lesion_types`, `inflammation_level`, `lesion_distribution`). Sáu trường không
  được truyền: `medication_history`, `skincare_products`, `canonical_ingredients`,
  `usage_frequencies`, `concentrations`, `red_flags_input`.

  Hậu quả dây chuyền, tất cả đều đo được bằng grep:
  - `red_flags_input` rỗng → nhánh `urgent_personal_case` (confidence 0.92) của
    `_rule_decision` không bao giờ chạy; bản vá "BUG FIX" ở `intake.py:~676` vô
    tác dụng; cảnh báo khẩn ở `_safety` chỉ sống nhờ `or not _rf` (Q-07).
  - `canonical_ingredients` và `medication_history` rỗng → hai vòng lặp cuối của
    `_extract_safety_terms` chết.
  - `usage_frequencies`, `concentrations` rỗng → `extracted_entities_from_user`
    ghi khoá rỗng vào audit log mọi bản ghi.
  - `fold_history_facts` gộp 12 trường, trong đó 6 luôn rỗng.

  Đây là **phát hiện cấu trúc lớn nhất** của module. Cần một quyết định rõ trong
  báo cáo: hoặc thu `AcneClinicalInput` về đúng 3 trường mà hệ thật dùng, hoặc mở
  rộng prompt intaker để sinh đủ. Trạng thái hiện tại — schema hứa 12, hệ dùng 3 —
  là thứ giám khảo sẽ hỏi. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `intake.py:676`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-16` · src.chat
  hiện tại: hai bản system prompt của intaker phải đồng bộ bằng tay

  `unified_intake._RUNTIME_SYSTEM` và `model/intaker/Modelfile` SYSTEM hiện **giống
  hệt** (3.322 ký tự, sha256 `6ee28283b579feb8`), nhưng không có gì canh. Vì
  `use_modelfile_system=True`, bản Python **không** được gửi — nên nếu ai sửa nó,
  hành vi không đổi và không ai biết là đã lệch. Một test 3 dòng so sha256 là đủ. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1779`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat:Q-17` · src.chat
  hiện tại: prompt nói 3 lượt lịch sử, code gửi 6

  `_RUNTIME_SYSTEM` mở đầu: "Đọc turn hiện tại và tối đa **3** turn lịch sử gần
  nhất". `_MAX_HISTORY_TURNS = HISTORY_WINDOW_TURNS = 6`. Hai adapter legacy thì
  đúng 3 (`[-3:]`). Nếu tập fine-tune chỉ có mẫu ≤ 3 lượt thì đây là train/serve
  skew. Ngoài ra `_build_user_prompt` dùng **hai định dạng** (nguyên văn khi không
  có lịch sử, bọc `FOLLOWUP_HISTORY_JSON` khi có) — cần kiểm tập train có cả hai
  không. Cả hai câu hỏi thuộc phần kiểm kê `research/datagen/intakedata`. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1785`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat:Q-18` · src.chat
  hiện tại: snapshot chỉ được lưu cho lượt `advise`, và `_intent_patch` phụ thuộc điều đó

  `runtime._snapshot_for_persistence` trả None trừ khi
  `primary_intent == "advise"`. `_has_established_case` chỉ thấy lượt có snapshot.
  `_intent_patch` nâng `clarify` → `advise` **dựa trên** `_has_established_case`.
  Nên một phiên mở đầu bằng `clarify` không bao giờ tích được ca bệnh để tự thoát
  khỏi `clarify` — trừ khi có một lượt `advise` xen vào. Vòng phụ thuộc này không
  được ghi ở đâu và đáng kiểm bằng một test hội thoại nhiều lượt. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.md:1793`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

### `src.chat.routing`

[C] `src.chat.routing:Q-02` · src.chat.routing
  hiện tại: (ĐÃ SỬA — nhẹ hơn tôi viết ban đầu) — hằng `_RUNTIME_SYSTEM` trong hai adapter không được gửi, nhưng đó là thiết kế đúng

  Cả hai truyền
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

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `di.py:186`, `di.py:220`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-03` · src.chat.routing
  hiện tại: `_timeout` là bản sao chết ở cả ba adapter

  `LLMExtractor:45`, `LLMRouter:54`, `UnifiedIntake:80` đều gán `self._timeout` và
  không dùng. Timeout thật đã áp ở tầng HTTP khi `di.py` dựng
  `OllamaBackend(timeout=...)`. `LLMRouter` còn phơi property `timeout` mà 0 caller
  đọc. {code}

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1835`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-05` · src.chat.routing
  hiện tại: `_short_history` có hai bản

  `llm_router.py:94-108` (hàm riêng) và
  `llm_extractor.py:90-102` (nội tuyến trong `_build_prompt`). Cùng logic, cùng
  hằng số 3 lượt / 300 ký tự. Hai file cạnh nhau. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `llm_router.py:94`, `llm_extractor.py:90`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-07` · src.chat.routing
  hiện tại: hai miền hợp lệ cho `oos_distance_threshold`

  `SemanticRouter.__init__:85` chấp nhận `[0, 2]` (đúng toán học cho cosine
  distance); `config.py:129-137` chỉ cho `[0, 1]`. Lớp chấp nhận giá trị mà
  `Settings` từ chối. Đã ghi ở `src.config`, nay xác nhận từ phía tiêu thụ. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `config.py:129`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat.routing:Q-08` · src.chat.routing
  hiện tại: cache semantic router gắn với đường dẫn tuyệt đối

  `_cache_metadata:343` đưa `str(self.train_path.resolve())` vào metadata so sánh.
  Đổi thư mục repo → cache bị coi là khác → encode lại toàn tập lúc khởi động.
  Không được ghi ở đâu. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1864`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-11` · src.chat.routing
  hiện tại: `_has_any_clinical_fact` mang khiếm khuyết đã biết và chưa sửa

  Nó `any()` trên `clinical.inflammation_level`, trường luôn truthy sau
  `fold_history_facts` (`src.chat.session` Q-10). Comment tại call site
  (`intent_router:~618`) đã biết và **né** bằng cách không dùng hàm này ở nhánh
  cuối. Nhưng nhánh `contextual_personal_advice` (`:~600`) **vẫn** dùng nó. Ở đó nó
  đi kèm `is_advice_question` nên hậu quả hẹp hơn, không phải không có. {code}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1880`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat.routing:Q-12` · src.chat.routing
  hiện tại: bảng regex của `rule_normalizer` không compile sẵn

  13 bảng ~950 dòng
  lưu regex ở dạng **chuỗi**, `_has` compile qua cache nội bộ của module `re`
  (512 entry). Số pattern riêng biệt vượt xa 512 → đuổi cache và compile lại nhiều
  lần mỗi request. Lỗi cú pháp regex cũng chỉ nổ lúc chạy, không lúc import. Sửa
  rẻ: compile sẵn khi dựng bảng, như `_FOOTER_PATTERNS` của `rag/chunker.py` đã làm. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1887`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat.routing:Q-13` · src.chat.routing
  hiện tại: `crisis_signal` xếp sau bốn nhánh knowledge trong `_rule_decision`

  Thứ tự nhánh: short_followup → urgent_personal_case → knowledge_ranking →
  product/food/mechanism → general_comparison → **crisis_signal** → … Một câu vừa
  mang tín hiệu khủng hoảng vừa chứa `"là gì"`/`"tại sao"` sẽ ra `knowledge` và
  **không** vào `safety_clarify`. Đây là tầng 3, chỉ chạy khi Ollama chết — tức
  đúng lúc hệ đang yếu nhất. Cần quyết: đẩy `crisis_signal` lên ngay sau
  `urgent_personal_case`. {code}

  phải thành: đẩy `crisis_signal` lên ngay sau
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1893`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-14` · src.chat.routing
  hiện tại: `route_intent` dựng một `Settings()` mới mỗi lần gọi

  `intent_router.py:~651`: `from ...config import Settings as _S; _S().route_min_confidence`.
  Mỗi lời gọi đọc lại `.env` từ đĩa và chạy lại 6 validator. Nó **không** dùng
  singleton `settings`, và **không** dùng tham số `settings` được truyền vào chính
  hàm. Sửa một dòng: đọc từ singleton, hoặc dùng tham số. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `intent_router.py:651`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-15` · src.chat.routing
  hiện tại: luật hạ cấp confidence trong `route_intent` là nhánh chết

  Điều kiện `decision.confidence < route_min_confidence` với
  `route_min_confidence = 0.55`. Liệt kê đủ 11 giá trị confidence mà
  `_rule_decision` có thể trả: 0.92, 0.90, 0.86, 0.84, 0.82, 0.80, 0.75, 0.72,
  0.70, 0.68, **0.58**. Không giá trị nào dưới 0.55, nên `clarify` vì thiếu tự tin
  **chưa bao giờ chạy**. Hai cách sửa: nâng ngưỡng lên 0.60 (khi đó nhánh
  `low_signal_default` sẽ hạ cấp), hoặc hạ confidence của nhánh đó xuống dưới 0.55.
  Phải chọn có chủ đích — hiện tại là một cơ chế an toàn tồn tại trên giấy. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1907`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-17` · src.chat.routing
  hiện tại: `_VOCAB_FUZZY_REVIEW = 0.82` không có tác dụng

  Nó được truyền làm `review` cho `find_in_text`, nhưng hàm đó vứt mọi hit dưới
  `accept` ở dòng return (`src.utils` Q-02). Thứ thật sự lọc là `accept = 0.86`.
  Một hằng số được tinh chỉnh và ghi chú hai dòng cho một cổng không tồn tại. Sửa
  `find_in_text` thì hằng này sống lại — nên hai việc phải làm cùng nhau. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1924`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-18` · src.chat.routing
  hiện tại: `_NEGATION_RE` trong `rule_extractor` có 0 caller

  `rule_extractor.py:81` định nghĩa nó, comment `:80` xếp nó cùng nhóm "điều chỉnh
  ngữ cảnh", nhưng `_context_adjust` chỉ dùng `_QUESTION_RE` và `_PRONOUN_RE`. Nghĩa
  là câu phủ định **không** bị trừ confidence. {code}

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `rule_extractor.py:81`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-19` · src.chat.routing
  hiện tại: hai biểu diễn cho `is_pregnant`, và cả hai đều đặt được `False` từ một từ khoá

  `rule_extractor._bool_from_patterns` trả ba trạng thái (True/False/
  none) với confidence 0.90; `rule_normalizer._contains_positive` trả bool hai
  trạng thái. Cả hai kiểm phủ định **không có phạm vi**, nên "chị tôi không mang
  thai" cho ra `False`. `chat/session/view.py:68` xếp `is_pregnant` vào
  `_UNGATED_FIELDS` (ngưỡng 0.0) nên `False` đó luôn vào `confirmed_profile`, và
  `medication_safety_refusal` đọc chính trường đó. Đây là cùng hướng hỏng mà
  `fold.py` đã xoá 17 keyword để tránh, với lý do ghi rõ "rule không bao giờ được
  tự hạ xuống False". Cần thống nhất một quy tắc cho cả ba file. {code+comment}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `chat/session/view.py:68`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-20` · src.chat.routing
  hiện tại: hai định nghĩa `_active_inflammatory_lesions` lệch nhau

  `rule_normalizer:1832` `_ACTIVE_INFLAMMATORY_LESIONS` = 5 phần tử (có `"other"`);
  `rule_normalizer:1730` biến cục bộ cùng ý nghĩa = 4 phần tử (không có `"other"`).
  Bản 5 phần tử dùng để **loại lesion khi mụn đã khỏi**, bản 4 phần tử dùng để
  **suy inflammation**. Vì `"other"` là nhãn bắt-tất khớp mọi chữ "mụn", chênh lệch
  này có hậu quả thật. Ngoài ra `_sequelae_lesions` (`:1731`) được gán và không
  dùng. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1945`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-21` · src.chat.routing
  hiện tại: xem Q-12

  (gộp: cùng nguyên nhân, cùng cách sửa).

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1953`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-22` · src.chat.routing
  hiện tại: `canonical_ingredients` và `current_products` bất đồng về cùng một chất

  `_extract_products` đòi ngữ cảnh đang-dùng (`_has_product_use_context`, 12 nhánh);
  `_extract_canonical_ingredients._in_use` đường (b) chỉ đòi **không bị phủ định**.
  Nên "nghe nói BHA tốt" cho `current_products=[]` nhưng
  `canonical_ingredients=['salicylic_acid']`. Hai trường của cùng một
  `AcneClinicalInput` nói hai điều khác nhau, và trường thứ hai là trường mà
  guardrail hoạt chất đọc. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1955`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.routing:Q-23` · src.chat.routing
  hiện tại: `concentrations` không gắn với hoạt chất nào

  `_extract_concentrations` bắt mọi `<số>%` trong câu và trả list phẳng;
  `canonical_ingredients` là list phẳng khác. Không có cặp (chất, nồng độ). Với tư
  vấn thuốc bôi thì "tretinoin 0.1%" và "0.025%" là hai lời khuyên khác nhau, còn
  schema hiện tại không phân biệt được. Đây là hạn chế thiết kế đáng nêu trong
  chương giới hạn của báo cáo. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1963`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat.routing:Q-24` · src.chat.routing
  hiện tại: `"da"` trong danh sách aspect marker biến câu hỏi thành thuốc đang dùng

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

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1970`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.chat.routing:Q-25` · src.chat.routing
  hiện tại: `treatment_goals` bị vứt khi không có tín hiệu lâm sàng nào khác

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

  phải thành: thêm `treatment_goals` vào điều kiện. {code}
  căn cứ: `.audit/FINDINGS/src.chat.routing.md:1983`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

### `src.chat.session`

⚠ [C] `src.chat.session:Q-01` · src.chat.session
  hiện tại: `SESSION_TTL` có hai nguồn sự thật, và nguồn `.env` không tới được store

  `models.py:61` đặt `SESSION_TTL = 1800.0`; `config.py:250` đặt
  `session_ttl: float = 1800.0`. Cả `SessionStore()` (`memory.py:194`) lẫn
  `Session.is_expired` (`models.py:117`) đều lấy hằng module. Đặt `SESSION_TTL=60`
  trong `.env` chỉ đổi `settings.session_ttl` — cần kiểm ở `src.db` xem
  `SQLiteSessionStore` có đọc `settings` không, vì đó mới là store chạy thật. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `models.py:61`, `config.py:250`, `memory.py:194`, `models.py:117`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.session:Q-02` · src.chat.session
  hiện tại: `SESSION_SCHEMA_VERSION` có người đọc, nhưng chỉ ở một trong hai store

  `db/session_store.py:127` dùng nó để reset row lệch phiên bản; bản in-memory
  không kiểm. Đây là điểm lệch thứ ba giữa hai store (hai điểm kia: các field
  intent đã xoá, và `asked_fields`). Kiểm đủ ở `src.db`. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `db/session_store.py:127`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.session:Q-03` · src.chat.session
  hiện tại: `format_history_block` có hai hành vi mặc định khác nhau

  Production truyền `max_turns=HISTORY_WINDOW_TURNS` (6) từ
  `llm/prompt_builder.py:228`; default của hàm là 2 (`view.py:149`). Test gọi
  không tham số nên đo hành vi 2-turn, production chạy 6-turn. Bất kỳ test nào
  khẳng định về nội dung history block đều **không** đo cái production làm. {code+test}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `llm/prompt_builder.py:228`, `view.py:149`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.session:Q-04` · src.chat.session
  hiện tại: bốn method không `touch()`, nên session bị hết hạn oan

  `merge_user_context`, `get_user_context`, `increment_followup_count`, `delete`
  đều không gọi `Session.touch()`. Một phiên chỉ cập nhật profile mà không append
  turn sẽ già đi như thể không ai dùng. Cần kiểm bản SQLite có cùng lỗ không. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.chat.session.md:622`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.chat.session:Q-06` · src.chat.session
  hiện tại: (rút lại)

  Ghi chú ban đầu của tôi nói `increment_followup_count` và
  `active_count` không có caller nào. Sai: `chat/runtime.py:95-96` và
  `api/routes/admin.py:41` **có** gọi hai tên đó, chỉ là gọi trên
  `SQLiteSessionStore` chứ không phải lớp trong file này. Đã sửa tại chỗ ở hai
  khối tương ứng. Không còn là câu hỏi.

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `chat/runtime.py:95`, `api/routes/admin.py:41`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

### `src.config`

[C] `src.config:Q-02` · src.config
  hiện tại: `env_file=".env"` phụ thuộc cwd và hỏng im lặng

  `config.py:21`. Chạy từ thư mục con → không đọc được `.env` → 12 khoá đang đặt
  biến mất, `llm_model` về `"acne-generator"` (bản cũ, không phải `-v2`),
  `judge_provider` về `"deepseek"` (hết credit). Không có log, không có exception.
  Đây là cùng một hạng lỗi với bug preflight đã sửa hôm trước. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `config.py:21`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.config:Q-03` · src.config
  hiện tại: 8 field không có consumer nào trong code

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

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `research/LLMData/chunk_qa/loader.py:103`, `research/LLMData/chunk_qa/config.py:88`, `src/acne_llm/cache.py:102`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.config:Q-05` · src.config
  hiện tại: 3 default đã mục so với thực tế đang chạy

  - `llm_model = "acne-generator"` (`:25`) — model thật là `acne-generator-v2`,
    chỉ đúng nhờ `.env`.
  - `judge_provider = "deepseek"` (`:279`), `judge_model = "deepseek-v4-pro"` (`:280`)
    — DeepSeek đã hết credit; `.env` đang trỏ `openai` / `gpt-5.6-luna`.
  Cả ba chỉ đúng khi `.env` đọc được — nối thẳng vào Q-02. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.config.md:685`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.config:Q-06` · src.config
  hiện tại: hai model được đặt default trong code nhưng có thể không còn tồn tại

  `extractor_model = "acne-extractor:1.5b"` (`:59`) và `router_model = "acnellm-intent"`
  (`:66`), cả hai được `di.py:170,196-202` dùng làm default cứng. Cần đối chiếu
  với `ollama list` sau đợt dọn model. Nếu đã xoá, đường LLM-first của router và
  extractor rơi thẳng xuống fallback trong mọi request mà không ai biết —
  `extractor_mode`/`router_mode` vẫn báo `"llm"`. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `di.py:170`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.config:Q-07` · src.config
  hiện tại: độ phủ validator lệch hẳn

  6 validator phủ 8/73 field. Không field số nào trong nhóm quan trọng nhất được
  chặn: `llm_temperature` (`:30`), `llm_top_p` (`:31`), `chat_rerank_floor` (`:217`),
  `reranker_min_sigmoid` (`:236`), `dense_max_distance` (`:240`), `chat_min_chunk_score`
  (`:200`) — tất cả đều là số trong `[0,1]` theo ngữ nghĩa, không có gì chặn. Đặt
  `CHAT_RERANK_FLOOR=5.0` sẽ khiến RAG trả rỗng cho **mọi** truy vấn và không báo lỗi. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.config.md:699`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.config:Q-08` · src.config
  hiện tại: comment dài hơn code và mang lịch sử chưa được kiểm

  `config.py:194-217` và `:227-236` chứa hai đoạn kể lại lịch sử tune ngưỡng
  sigmoid ("code còn sigmoid lần hai nên mọi thứ bị nén vào [0.500, 0.731]"). Đây
  là {comment}, hạng lời khai. Tôi **chưa** đối chiếu với `rag/reranker.py` trong
  module này — việc đó thuộc `src.rag`. Ghi lại để module đó phải kiểm.

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `config.py:194`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

### `src.db`

⚠ [C] `src.db:Q-03` · src.db
  hiện tại: 3 method 0 caller trong `src/`: `DBConnection.executemany`, `DBConnection.close`, `SQLiteSessionStore.delete`, `SQLiteSessionStore.close`

  (Bốn, tính cả hai `close`.) `close` đáng chú ý hơn hai cái kia: cả hai chỉ đóng
  được connection của thread gọi, nên với server nhiều thread, mỗi thread giữ một
  sqlite connection cho tới khi tiến trình chết. Không ai gọi, và kể cả có gọi
  cũng không dọn hết. {code}

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `.audit/FINDINGS/src.db.md:611`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.db:Q-04` · src.db
  hiện tại: audit log cho "trách nhiệm pháp lý" mất bản ghi im lặng

  `audit.py:39-67`: `except Exception` → `logger.warning`. `runtime.py:287` gọi
  không kiểm kết quả. Nếu `audit.db` đầy đĩa, khoá, hoặc rơi về DB tạm
  (`di.py:104-110` có nhánh fallback vào `tempfile.gettempdir()`), hệ vẫn trả lời
  người dùng bình thường và không ai biết bản ghi tư vấn y tế đã mất. Cần quyết:
  giữ nguyên và ghi rõ giới hạn này trong báo cáo, hay nâng thành lỗi thấy được. {code}

  phải thành: giữ nguyên và ghi rõ giới hạn này trong báo cáo, hay nâng thành lỗi thấy được. {code}
  căn cứ: `audit.py:39`, `runtime.py:287`, `di.py:104`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.db:Q-05` · src.db
  hiện tại: "TTL xoá lazy" không đồng đều giữa 8 method, và hai store lệch nhau

  Trong `SQLiteSessionStore`: `get_or_create`, `get_history`, `merge_user_context`,
  `get_user_context`, `increment_followup_count` có kiểm hết hạn; `append_turn`
  (qua `_ensure`) có; `delete` và `active_count` không cần. Nhưng bản in-memory
  `memory.py:141-148` `get_user_context` **không** kiểm hết hạn. Cùng một lời gọi,
  hai store trả hai kết quả khác nhau cho session quá TTL. Test chạy bản in-memory
  không phát hiện được. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `memory.py:141`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.db:Q-07` · src.db
  hiện tại: `RLock` là bắt buộc chứ không phải phòng xa, và không ai ghi lại

  `get_or_create:175-181` giữ `self._lock` rồi gọi `self.get_history`, hàm này
  cũng `with self._lock`. Đổi `RLock` → `Lock` là deadlock ngay request đầu tiên.
  Ràng buộc này không có comment nào bảo vệ. (Ngược lại, `RLock` ở
  `memory.py:44` thì **không** cần — kiểm tay: không method nào ở đó gọi method
  khác cùng lớp trong lúc giữ lock.) {code}

  ---

  ## §6 — Tự kiểm (Bước 4)

  - Khối khai báo ở Bước 0: **46** (2 + 11 + 10 + 23)
  - Khối `### [x]` đếm được: xem `grep -c '^### \[x\]'`
  - Mục: 46 × 8 = **368**. Không dùng nén khai báo; mọi khối viết đủ 8 mục.

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `memory.py:44`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

### `src.rag`

⚠ [C] `src.rag:Q-01` · src.rag
  hiện tại: `clean_for_finetuning` (`cleaning.py:84`) không có caller trong `src/`, `scripts/`, `tests/`

  Phải kiểm `research/LLMData` (chưa duyệt) xem bộ
  dữ liệu fine-tune của `acne-generator-v2` có đi qua hàm này không. Quan trọng vì
  bản song sinh chết ở `utils/text_cleaning.py` **thiếu** `PDF_ARTIFACTS`
  (`src.utils` Q-09) — nếu dataset fine-tune từng sinh bằng bản kia thì nó mang lỗi
  ƣ/Ƣ. {code}

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `cleaning.py:84`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.rag:Q-02` · src.rag
  hiện tại: ba nơi chuẩn hoá `device`, ba hành vi

  `config.py:139-151` (validator: map alias, chấp nhận `cuda:N/mps/auto`),
  `rag/embedder.py:7-20` (map `gpu → cuda`, **kiểm CUDA thật** và hạ về CPU),
  `rag/reranker.py:18` (`self.device = device`, không chuẩn hoá gì). Hệ quả thật:
  đặt `DEVICE=cuda` trên máy không có GPU thì embedder tự hạ về CPU còn reranker
  vẫn đưa `"cuda"` cho `CrossEncoder` → lỗi lúc nạp model. Đường production hiện
  đặt `DEVICE=cpu` nên chưa nổ. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `config.py:139`, `rag/embedder.py:7`, `rag/reranker.py:18`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.rag:Q-03` · src.rag
  hiện tại: `underthesea` là phụ thuộc tuỳ chọn nhưng quyết định chất lượng BM25, và không có bản ghi nào nói lúc build đã dùng chế độ nào

  `sparse.py:8-11` + `chunker.py:7-10`. Thiếu gói → tách theo khoảng trắng. Index
  xây bằng một chế độ và truy vấn bằng chế độ kia sẽ lệch. File `.sha256` bảo vệ
  nội dung pickle, không bảo vệ điều này. Đề xuất rẻ nhất: ghi cờ
  `tokenizer="underthesea"|"whitespace"` vào chính pickle và kiểm lúc `load`. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `sparse.py:8`, `chunker.py:7`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-04` · src.rag
  hiện tại: `"không"` nằm trong `_VI_STOPWORDS`

  `sparse.py:19`. BM25 không phân biệt "dùng được" và "không dùng được". Với câu
  hỏi y khoa dạng phủ định ("bà bầu **không** được dùng gì") đây là mất tín hiệu
  thật. 5/8 mục cuối của danh sách (`i, v, a, b, c`) còn thừa vì đã bị
  `len(t) > 1` loại. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `sparse.py:19`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-05` · src.rag
  hiện tại: `BM25Index.texts` được lưu vào pickle nhưng không bao giờ đọc lại

  `sparse.py:65,69,93,110`. Grep `\.texts` chỉ ra `build`/`save`/`load`. Nó chứa
  toàn văn 24.393 chunk — phần lớn kích thước file `bm25_index.pkl` là dữ liệu
  chết. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `sparse.py:65`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-06` · src.rag
  hiện tại: `BM25Index.build` không kiểm `len(chunk_ids) == len(texts)`

  `sparse.py:67-71`. `ChromaStore.upsert:31-32` **có** kiểm ràng buộc tương ứng và
  raise `ValueError`. Nếu hai list lệch, `query:153` trả **sai chunk_id** — không
  lỗi, chỉ sai kết quả. Một dòng `if` là đủ. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `sparse.py:67`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-09` · src.rag
  hiện tại: `ChromaStore.query` gọi `count()` trên mọi truy vấn

  `vectorstore.py:76`. Một round-trip DB thừa trên đường nóng, cho một giá trị
  gần như bất biến giữa các request. Cache trong instance là đủ. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `vectorstore.py:76`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-11` · src.rag
  hiện tại: `Reranker._score_cache` dùng chung giữa request đồng thời, không lock

  `reranker.py:23`. Hậu quả xấu nhất là mất/đè một entry, không sai kết quả (giá
  trị được tính lại). Ghi lại để không ai "sửa" thành cấu trúc phức tạp hơn mà
  không có lý do đo được. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `reranker.py:23`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-12` · src.rag
  hiện tại: khoá cache reranker là `(query_đầy_đủ, chunk_id)`, gần như không bao giờ trúng

  `reranker.py:64`. Trong hội thoại thật, query đổi mỗi lượt (nó gồm cả
  `recent context:` từ `build_current_turn_query`), nên cache 2048 entry chỉ trúng
  khi người dùng gửi lại **đúng cùng một chuỗi**. Nơi nó thật sự trúng là **eval**:
  cùng 145 câu chạy qua nhiều arm. Đáng đo tỉ lệ trúng trước khi giữ hay bỏ. {code}

  phải thành: Đo/kiểm bằng artifact được nêu trước; chỉ sửa logic nếu phép đo xác nhận tác động.
  căn cứ: `reranker.py:64`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-13` · src.rag
  hiện tại: `_HEADING_RE` thiếu phần lớn nguyên âm hoa tiếng Việt

  `chunker.py:13`. Lớp `[A-ZÀÁẢÃẠĂẶÂẦẤĐÊÔƠƯ]` không có `Ứ Ổ Ộ Ệ È É Ò Ó Ù Ú Ì Í`…
  Tiêu đề bắt đầu bằng những chữ đó không được nhận diện, nên không được gắn vào
  đoạn kế tiếp. Ảnh hưởng chất lượng chunk của KB đã build. Sửa bằng
  `re.match(r"[^\W\d_]", s)` + `s[0].isupper()` thay cho lớp liệt kê tay. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `chunker.py:13`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.rag:Q-15` · src.rag
  hiện tại: `chunk_with_stats` rò rỉ state và không có caller

  `chunker.py:220-224`: `self.dedup = before` bị ghi đè ngay bởi `self.dedup = True`,
  nên object dựng với `dedup=False` bị bật dedup vĩnh viễn sau một lần gọi. Hàm
  này 0 caller toàn repo. Xoá được; nếu giữ thì phải sửa hai dòng. {code}

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `chunker.py:220`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.rag:Q-16` · src.rag
  hiện tại: trần boost 1.67 bị chính code vượt qua

  Comment `retriever.py:19-22` chứng minh trần ~1.67 cho `_SOURCE_TYPE_BOOST`
  (tôi đã kiểm lại số và nó đúng). Nhưng `retrieve:~163` **nhân thêm**
  `_AUTHORITY_TAG_BOOST = 1.15` → chunk NICE có tag "guidelines" đạt
  1.60 × 1.15 = **1.84 > 1.67**. Theo chính lập luận của comment, khi pool có
  chunk như vậy thì mọi chunk chỉ-một-list bị cắt sạch, tức hybrid retrieval bị vô
  hiệu hoá cho truy vấn đó. Cần đo tần suất tag "guidelines" trên KB trước khi
  quyết định hạ `_AUTHORITY_TAG_BOOST` hay hạ `_MIN_FUSION_SCORE_RELATIVE`. {code+comment}

  phải thành: Sửa lời khai để mô tả đúng code đang chạy; không đổi logic trong cùng patch.
  căn cứ: `retriever.py:19`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

### `src.schemas`

[C] `src.schemas:Q-01` · src.schemas
  hiện tại:

  `EntityRecord` có trong `__all__` nhưng 0 caller. Xoá hay giữ?
  → Đáp án tôi chọn: **giữ, đánh dấu "hợp đồng chưa nối"**. Lý do: `contraindications` trùng vai `config/drugs_acne.yaml` đang chạy; xoá thì mất dấu ý định, mà giữ thì phải ghi rõ chưa dùng.

  phải thành: Đáp án tôi chọn: **giữ, đánh dấu "hợp đồng chưa nối"**. Lý do: `contraindications` trùng vai `config/drugs_acne.yaml` đang chạy; xoá thì mất dấu ý định, mà giữ thì phải ghi rõ chưa dùng.
  căn cứ: `.audit/FINDINGS/src.schemas.md:494`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-02` · src.schemas
  hiện tại:

  `kb.Intent` (9 giá trị ask_*) đối lập `PrimaryIntent` (4 giá trị) đang chạy. Giữ cái nào?
  → **Xoá `kb.Intent`**. `git log` cho thấy `routing/intent_router.py` là nhánh được sửa liên tục tới `024739b` (2026-08), còn `kb.Intent` không đổi từ lúc tạo.

  phải thành: **Xoá `kb.Intent`**. `git log` cho thấy `routing/intent_router.py` là nhánh được sửa liên tục tới `024739b` (2026-08), còn `kb.Intent` không đổi từ lúc tạo.
  căn cứ: `.audit/FINDINGS/src.schemas.md:497`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-03` · src.schemas
  hiện tại:

  `LLMData`, `QASample`, `ChatMessage` — chết hoàn toàn. Xoá?
  → **Xoá cả ba**. Pipeline sinh dữ liệu thật ghi JSONL thô, không qua pydantic.

  phải thành: **Xoá cả ba**. Pipeline sinh dữ liệu thật ghi JSONL thô, không qua pydantic.
  căn cứ: `.audit/FINDINGS/src.schemas.md:500`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-04` · src.schemas
  hiện tại:

  `VisionLesion`/`VisionOutput` chưa có consumer. Giữ?
  → **Giữ**. Docstring `core.py:1` khai đây là hợp đồng với "đề tài 27"; đó là ranh giới liên đề tài, không phải code chết.

  phải thành: **Giữ**. Docstring `core.py:1` khai đây là hợp đồng với "đề tài 27"; đó là ranh giới liên đề tài, không phải code chết.
  căn cứ: `core.py:1`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-05` · src.schemas
  hiện tại:

  `Recommendation`/`AdviseOutput` không còn được sinh trên đường chat. Giữ?
  → **Giữ `AdviseOutput`** (còn 3 caller trong `src/`), **đánh dấu `Recommendation` là legacy** (0 caller `src/`).

  phải thành: **Giữ `AdviseOutput`** (còn 3 caller trong `src/`), **đánh dấu `Recommendation` là legacy** (0 caller `src/`).
  căn cứ: `.audit/FINDINGS/src.schemas.md:506`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-06` · src.schemas
  hiện tại:

  `UserContext.sex` không có `"unknown"`, `ClinicalDemographics.sex` có. Thống nhất?
  → **Không đụng lúc này**. `UserContext` nằm trên đường chạy request và đang được eval ghi đè; đổi Literal là rủi ro `ValidationError` giữa lần chạy full eval. Ghi vào RỔ C để làm sau.

  phải thành: **Không đụng lúc này**. `UserContext` nằm trên đường chạy request và đang được eval ghi đè; đổi Literal là rủi ro `ValidationError` giữa lần chạy full eval. Ghi vào RỔ C để làm sau.
  căn cứ: `.audit/FINDINGS/src.schemas.md:509`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-07` · src.schemas
  hiện tại:

  `InflammationLevel` khai ở `clinical.py:15` nhưng `core.py:61-63` khai lại bằng tay. Gom?
  → **Gom về một alias**, nhưng thuộc RỔ C và làm sau lần chạy eval.

  phải thành: **Gom về một alias**, nhưng thuộc RỔ C và làm sau lần chạy eval.
  căn cứ: `clinical.py:15`, `core.py:61`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-08` · src.schemas
  hiện tại:

  `AdviseOutput.disclaimer` `[core.py:153]` khác câu chữ với `_GENERIC_DISCLAIMER_VI` `[_safety.py:117-121]`. Bản nào là chuẩn?
  → **`_safety.py` là bản đang thật sự tới người dùng**; `core.py:153` là bản chết. Lý do: chỉ `_safety` được `runtime.stream_chat_sse` gọi.

  phải thành: **`_safety.py` là bản đang thật sự tới người dùng**; `core.py:153` là bản chết. Lý do: chỉ `_safety` được `runtime.stream_chat_sse` gọi.
  căn cứ: `core.py:153`, `_safety.py:117`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.schemas:Q-09` · src.schemas
  hiện tại:

  `ExtractionConfidence.field()` không tìm thấy caller. Chết hay gọi động?
  → **Chưa rõ, cần bạn xác nhận**. Tôi không tìm được lời gọi nào; nhưng vì nó là `getattr` theo tên chuỗi nên grep có thể sót.

  phải thành: **Chưa rõ, cần bạn xác nhận**. Tôi không tìm được lời gọi nào; nhưng vì nó là `getattr` theo tên chuỗi nên grep có thể sót.
  căn cứ: `.audit/FINDINGS/src.schemas.md:518`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

### `src.utils`

⚠ [C] `src.utils:Q-03` · src.utils
  hiện tại: `classify` + `_as_tuple` không phục vụ production

  Chỉ test import. Đường production (`rule_extractor.py`) gọi `find_in_text`, vốn
  gọi `best_match` **không** qua `_as_tuple` — nên canonical không được chuẩn hoá
  (`strip().lower()`) và không được cache. Nếu lexicon canonical có mục thừa
  khoảng trắng hoặc viết hoa, `best_match` so nó nguyên trạng với query đã
  `.lower()`. Đáng kiểm ở `src.chat` khi duyệt `rule_extractor.py`. {code}

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `.audit/FINDINGS/src.utils.md:653`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.utils:Q-04` · src.utils
  hiện tại: `timer.py` (12 dòng) 0 caller

  `timed` không được gọi ở đâu; `label` còn không được dùng trong thân hàm. Đo
  thời gian thật do `log_pipeline_stage` làm. Xoá được. {code}

  phải thành: Xác minh dynamic/reflection; nếu vẫn 0 caller thì xóa hoặc đánh dấu legacy rõ ràng.
  căn cứ: `.audit/FINDINGS/src.utils.md:660`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.utils:Q-05` · src.utils
  hiện tại: `log_pipeline_stage` raise trên tên giai đoạn sai

  `logging.py:66-67`. Một hàm ghi log có quyền làm hỏng request. 36 chỗ gọi.
  Hiện tại cả 36 đều dùng tên hợp lệ (đã đếm literal: 9/9 giai đoạn có người dùng,
  không có tên lạ), nên đây là rủi ro chứ chưa phải lỗi. Cần quyết: giữ (fail
  fast, bắt lỗi lúc test) hay hạ xuống `logger.warning`. {code}

  phải thành: giữ (fail
  căn cứ: `logging.py:66`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.utils:Q-08` · src.utils
  hiện tại: `_NEG_RE` bắt nhầm "bơ", "bò", "bố" thành phủ định

  `retrieval_query.py:27`, chạy trên chuỗi đã bỏ dấu. Đo thật:
  `"toi an bo dau phong"` → True, `"me toi nau thit bo"` → True,
  `"toi thich qua bo"` → True. Hệ quả: mô tả có nhắc bơ/thịt bò làm alias sản phẩm
  trong cùng mệnh đề bị loại khỏi query RAG. Chủ đề ăn uống (sữa, đường, đồ cay,
  whey) xuất hiện thường xuyên trong mô tả ca mụn — chính `chunk_filter.py:34-35`
  liệt kê chúng làm "marker cụ thể". Cách vá rẻ nhất: giữ dấu cho riêng phép kiểm
  này, hoặc đổi `\bbo\b` thành khớp trên bản có dấu `\bbỏ\b`. {code}

  phải thành: giữ dấu cho riêng phép kiểm
  căn cứ: `retrieval_query.py:27`, `chunk_filter.py:34`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

⚠ [C] `src.utils:Q-09` · src.utils
  hiện tại: `text_cleaning.py` (89 dòng) là bản sao chết và lỗi thời của `rag/cleaning.py`

  Grep `text_cleaning` toàn repo = 0 người dùng. `diff` cho thấy bản này thiếu
  `PDF_ARTIFACTS` và hai lời gọi `translate` — tức thiếu đúng bản vá cho PDF tiếng
  Việt đời cũ mà `rag/cleaning.py:6-9` giải thích. Đây là bẫy: ai import nhầm
  `utils.text_cleaning` thay vì `rag.cleaning` sẽ mất bản vá đó mà không có lỗi
  nào. Đề xuất: xoá file. Trước khi xoá, cần kiểm ở `research/LLMData` xem bộ
  fine-tune có từng sinh bằng `clean_for_finetuning` của bản này không. {code}

  phải thành: xoá file. Trước khi xoá, cần kiểm ở `research/LLMData` xem bộ
  căn cứ: `rag/cleaning.py:6`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

[C] `src.utils:Q-10` · src.utils
  hiện tại: ba bản sao chức năng trùng nhau trong `utils/` và láng giềng

  `_dedupe` (`retrieval_query.py:50`) ≡ `_dedupe_values` (`chat/session/fold.py:65`);
  `_QUERY_STOP_TERMS` (`chunk_filter.py:23`) chồng lên `_VI_STOPWORDS`
  (`rag/sparse.py:14`) và được áp **sau** nó; `text_cleaning.py` ≡ `rag/cleaning.py`.
  Ba cặp, ba nơi phải sửa cùng lúc khi đổi một quy tắc. {code}

  ---

  ## §6 — Tự kiểm (Bước 4)

  - Khối khai báo ở Bước 0: **47** (1 + 10 + 8 + 2 + 8 + 11 + 6 + 1)
  - Khối `### [x]` đếm được: xem `grep -c '^### \[x\]'`
  - Mục: 47 × 8 = **376**. Không dùng nén khai báo; mọi khối viết đủ 8 mục.
  - Ba khẳng định đo bằng chạy thật chứ không đọc mắt: `_NEG_RE` (Q-08),
    độ dài `_no_accent` NFC vs NFD, và `diff text_cleaning.py rag/cleaning.py` (Q-09).

  ---

  ## §7 — BỔ SUNG (thêm sau khi duyệt `src.chat/preprocess.py`)

  **Thêm một hệ quả đo được cho Q-08 (`_NEG_RE`) và một lỗi mới của `_no_accent`.**

  `chat/preprocess.strip_accents` và `utils/retrieval_query._no_accent` cùng làm
  một việc — bỏ dấu tiếng Việt — nhưng bản ở `preprocess` có thêm
  `.replace("đ","d").replace("Đ","D")`, còn bản ở đây **không**. Lý do kỹ thuật:
  `đ` (U+0111) không phân rã được bằng NFD, nên chỉ NFD-tách-dấu là chưa đủ.

  Đo thật:

  | đầu vào | `preprocess.strip_accents` | `retrieval_query._no_accent` |
  |---|---|---|
  | `"da đầu"` | `"da dau"` | `"da đau"` |
  | `"đang dùng adapalene"` | `"dang dung adapalene"` | `"đang dung adapalene"` |

  Hệ quả đo được ngay trong module này: `_NEG_CUES` được viết bằng ASCII
  (`"khong dung"`, `"ngung dung"`, `"dung lai"`…), nên cue nào tương ứng một từ
  tiếng Việt bắt đầu bằng `đ` sẽ **không bao giờ khớp**. Thử 8 câu phủ định:

  - khớp cue: `"không dùng BHA nữa"`, `"ngừng dùng BHA"`, `"đã ngưng BHA"`,
    `"thôi dùng BHA"`, `"hết dùng BHA"`, `"không xài BHA nữa"` (6/8)
  - `"bỏ BHA"` — không cue nào khớp, nhưng `_NEG_RE` bắt được (đó là lý do
    `_NEG_RE` tồn tại riêng)
  - **`"đừng dùng BHA"` — không cue nào khớp và `_NEG_RE` cũng không** → alias sản
    phẩm vẫn vào query RAG dù người dùng đã phủ định.

  Sửa một dòng: `retrieval_query` dùng chung `chat.preprocess.strip_accents` thay
  vì tự định nghĩa `_no_accent`. Lưu ý khi sửa: điều này **thay đổi độ dài chuỗi ở
  những chuỗi có `đ`**, và `_alias_is_negated` lấy chỉ số `match.start()` từ chuỗi
  **có dấu** rồi cắt trên chuỗi **không dấu** — hiện an toàn vì cả hai cùng độ dài
  (xem khối `_no_accent`, mục 7). Thay `đ`→`d` giữ nguyên độ dài 1:1 nên bất biến
  đó vẫn đúng; nhưng phải kiểm lại chứ đừng tin.

  phải thành: Review theo bằng chứng Q này; ưu tiên thay đổi nhỏ nhất khôi phục invariant được nêu.
  căn cứ: `retrieval_query.py:50`, `chat/session/fold.py:65`, `chunk_filter.py:23`, `rag/sparse.py:14`
  rủi ro nếu sửa sai: Có thể đổi routing, safety, retrieval, schema, persistence hoặc reproducibility; bắt buộc test/review riêng.

## Q đã đóng/đính chính — không đưa vào patch

- `src.chat:Q-09` — ĐÍNH CHÍNH `src.rag` Q-08: hậu quả tôi lo KHÔNG xảy ra
- `src.chat.routing:Q-04` — (ĐÃ TRẢ LỜI — không phải lỗi)
- `src.rag:Q-08` — `RetrievedChunk.score` có bốn thang, và thang của đường chính nằm dưới mọi ngưỡng hạ nguồn
- `src.rag:Q-17` — `_source_type_from_meta` sửa dict metadata tại chỗ
- `src.rag:Q-08` — ở trên đã được hạ mức

## Doc mồ côi

- `src/acne_llm/utils/text_cleaning.py` tự mô tả cleaning nhưng 0 caller và cũ hơn `src/acne_llm/rag/cleaning.py`: đề xuất xóa code ở Rổ C và xóa/sửa mọi doc trỏ tới nó.
- Các report/evaluation `.md` mô tả schema/run cũ phải đối chiếu fingerprint hiện tại; report không có dataset/question fingerprint nên được gắn historical, không dùng làm runtime truth.
- `src/acne_llm/schemas/kb.py` tự mô tả toàn file là KB trong khi chứa cả schema fine-tune: viết lại module docstring hoặc tách miền.

## Hành vi quan trọng chưa được mô tả

- Audit DB fallback sang temp directory khi path chính không mở được.
- Rebuild KB không tự invalidate retrieval cache.
- Unified intake production chỉ populate một phần clinical schema; nhiều field legacy luôn rỗng.
- SSE runtime có CJK normalization/safety suffix/persistence mà non-streaming eval path không có.
- `RetrievedChunk.score` có nhiều scale theo provenance; metadata `source_type` có thể được suy ra và mutate lúc chạy.
- Semantic-router/RAG/reranker degrade độc lập; `rag_ready` không đồng nghĩa reranker hoặc semantic router ready.

## Patch artifacts

- `patches/A-docs.patch`
- `patches/B-comments.patch`
- `patches/C-code.patch`

Ba patch độc lập và chưa apply. Rổ C không được commit chung A/B.
