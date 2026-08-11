# Danh sách việc — đã chốt quyết định

Tổng hợp từ `runtime_audit.md` + `DEAD_CODE.md` sau khi duyệt từng mục.

**Kết quả dự kiến: xoá ~1.808 dòng, thêm lại ~36 dòng. `src/` từ 17.440 → ~15.670.**

Mỗi phase là một PR riêng. Không gộp.

---

## PHASE 0 — Bảo mật (làm trước, không liên quan tới dọn dẹp)

Nhóm này khẩn vì hiện `/api/v1/admin/audit` trả toàn văn hội thoại người dùng cho
bất kỳ ai — `API_KEY` rỗng khiến `APIKeyMiddleware` cho qua tất cả, cộng
`CORS_ORIGINS=["*"]`.

- [ ] Đặt `API_KEY` thật trong `.env`
- [ ] `CORS_ORIGINS` từ `["*"]` → domain cụ thể
- [ ] Thêm dependency auth riêng cho `admin.router` — không dựa vào middleware
      toàn cục, vì nó tự tắt khi key rỗng
- [ ] Tắt `/debug/trace` (`api/routes/chat.py:54-202`) khi không phải dev, hoặc
      đặt sau cùng auth với admin
- [ ] Rotate 3 secret đang plaintext trong `.env` (OpenAI + 2 DeepSeek)

Kiểm chứng: `curl` tới `/api/v1/admin/audit` không kèm header phải trả 401.

---

## PHASE 1 — Xoá thẳng, không rủi ro (584 dòng)

Không caller nào kể cả test, không mang luật nghiệp vụ.

- [ ] Xoá cả file `llm/qa_generator.py` (328) — `QAGenerator`, `OllamaQAGenerator`
- [ ] `rag/retriever.py`: xoá `mmr_select` (85-122), `retrieve_with_mmr` (276-289),
      `expand_context` (291-353) — 115 dòng. **Xoá luôn `import numpy as np`
      dòng 8**, numpy chỉ dùng trong `mmr_select`
- [ ] Xoá 5 file Protocol (27): `llm/base.py`, `rag/base.py`, `pipeline/base.py`,
      `pipeline/__init__.py`, `crawler/base.py`. `pipeline/` thành package rỗng → xoá cả thư mục
- [ ] Xoá `vision/` (21) + gỡ dây ở `di.py` dòng 21, 38, 54, 339 (3 dòng)
- [ ] `utils/retrieval_query.py`: xoá `build_retrieval_query` (69-112, 44 dòng)
- [ ] `cache.py`: xoá `invalidate_retrieve_cache` (139-154), `clear_all_caches` (157-166) — 26
- [ ] `llm/ollama_backend.py`: xoá `show_params` (189-206) — 18
- [ ] `rag/reranker.py`: xoá `_sigmoid` (12-16) — 5
- [ ] Xoá test tương ứng của tất cả các mục trên

Kiểm chứng: `pytest -q` — số test pass chỉ giảm đúng bằng số test vừa xoá.
`python -c "import acne_llm"` chạy được.

---

## PHASE 2 — Đã chốt quyết định (337 dòng)

### 2a. Endpoint WebSocket → xoá (89 dòng)

Đã chốt: dùng hoàn toàn SSE.

- [ ] `api/routes/chat.py`: xoá `chat_ws` (220-296) và `_parse_sse_frame` (205-216)
- [ ] Gỡ import không còn dùng: `WebSocket`, `WebSocketDisconnect`, có thể cả `asyncio`
      (kiểm lại — `debug_trace` còn dùng `asyncio.to_thread`)
- [ ] Xoá test WebSocket

### 2b. SessionStore in-memory → xoá (193 dòng)

Đã chốt: một nguồn sự thật là SQLite.

- [ ] `chat/session.py`: xoá class `SessionStore` (103-279) và `get_session_store` (288-295)
- [ ] `runtime.py:87` và `intake.py:265`: đổi
      `getattr(c, "session_store", None) or get_session_store()` → `c.session_store`
- [ ] Xoá 3 trường chết trên `ConversationTurn` (`session.py:69-73`):
      `intent_label`, `intent_confidence`, `turn_type` — **đã verify không dòng nào
      trong `src/` đọc chúng**, chỉ ghi vào
- [ ] Xoá `Session.last_intent` (session.py:89) — chỉ được ghi bởi store in-memory
- [ ] `tests/test_session.py`: chuyển sang `SQLiteSessionStore(":memory:")`

### 2c. asked_fields → xoá phương thức, giữ cột (31 dòng)

- [ ] `db/session_store.py`: xoá `get_asked_fields` (284-295), `mark_fields_asked` (297-315)
- [ ] **Giữ** cột `asked_fields` trong schema (dòng 40) — có `DEFAULT '[]'`, không tốn gì
- [ ] Giữ luôn dòng đọc cột ở `get_or_create` (185) để `Session` dựng đủ field

### 2d. Hai helper chết trong intake (24 dòng)

- [ ] `chat/intake.py`: xoá `_has_clinical_data` (152-165), `_is_intake_reply` (193-202)
- [ ] **Giữ** `_snapshot_has_values` (168-190) — còn được `_has_established_case` gọi,
      xử lý sau khi giải quyết `_intent_patch` ở Phase 6

---

## PHASE 3 — Tầng hậu kiểm: port một luật, xoá phần còn lại (+30 / −251)

Thứ tự bắt buộc: **port trước, test xanh, rồi mới xoá.** Không gộp hai bước
vào một commit.

### 3a. Port luật liều lượng sang `_safety.py` (+~30 dòng)

Đây là luật duy nhất được giữ. Lý do: model fine-tune trên tài liệu y khoa chắc
chắn sẽ sinh ra liều cụ thể, và cổng đầu vào không bắt được vì người dùng chưa
hề nhắc tên thuốc.

- [ ] Copy `dose_re` từ `runner.py:734-740` sang `chat/_safety.py`
- [ ] Copy `self_use_re` từ `runner.py:741-746` (cùng nhóm, cùng chi phí)
- [ ] Thêm một khối trong `get_safety_suffix`: nếu `full_text` khớp một trong hai
      regex và chưa có anchor "thuốc kê đơn"/"cần bác sĩ" → nối cảnh báo
- [ ] Viết test: đưa vào chuỗi `"uống doxycycline 100mg mỗi ngày trong 8 tuần"`,
      assert suffix có cảnh báo. Một test, không cần fixture

### 3b. Xoá `post_check` và 9 hàm `_apply_*` (−251 dòng)

Tất cả đã chốt bỏ:

| Hàm | Dòng | Lý do bỏ |
|---|---|---|
| `post_check` | 573-582 | không còn gì để điều phối |
| `_apply_drug_checker` | 584-610 | cả `DrugChecker` bị xoá ở Phase 5 |
| `_apply_retinoid_blocks` | 612-647 | đã có ở `get_safety_suffix:212-239` |
| `_apply_severe_doctor` | 649-673 | phụ thuộc `severity` không còn tồn tại |
| `_apply_age_restriction` | 675-699 | đã có ở `get_safety_suffix:260-270` |
| `_apply_no_popping` | 701-717 | đã có ở `get_safety_suffix:311-314` |
| `_apply_medication_safety` | 719-794 | phần đáng giữ đã port ở 3a |
| `_apply_medication_allergy_redflag` | 796-818 | trùng disclaimer chung |
| `_ensure_disclaimer` | 820-826 | đã có ở `get_safety_suffix:317-321` |
| `_find_rule_keywords` | 828-832 | chỉ `_apply_retinoid_blocks` dùng |

- [ ] Xoá 10 hàm trên
- [ ] Xoá `tests/test_guardrails.py` phần gọi `post_check` (6 chỗ)
- [ ] Gỡ import không còn dùng ở đầu `runner.py`: `Recommendation`, có thể cả `RedFlag`
      (kiểm lại — `medication_safety_refusal` còn dùng `RedFlag`)

**Không port:** kháng sinh đơn trị liệu, tương tác chéo trên text. Đã chốt bỏ.

---

## PHASE 4 — Tầng scope và OOD (−266 dòng)

### Xoá

- [ ] `runner.py`: `scope_check` (436-472), `_scope_refusal_if_out_of_scope` (357-434) — 115
- [ ] `guardrails/ood_detector.py`: class `OodDetector` (106-234) — 129.
      **Giữ nguyên file**, `contains_pii`/`mask_pii` đang chạy mỗi request
- [ ] `runner.py`: `_normalize_scope_mode` (333-340), `self.scope_mode`,
      tham số ctor `enable_ood`/`ood_threshold`/`centroid_path`, và khối init OOD (307-322)
- [ ] `config.py:171`: setting `guardrails_scope_mode`
- [ ] `di.py:229-231`: hai tham số truyền vào `GuardrailRunner`
- [ ] File `config/ood_centroid.json`
- [ ] `tests/test_guardrails.py`: 9 chỗ gọi `scope_check`

### Giữ — đây là các cổng cứng, cố ý không phụ thuộc model

- `is_prompt_injection` + `_PROMPT_INJECTION_PHRASES` (203-279)
- `is_genital_out_of_scope` / `is_genital_scope` + `_GENITAL_BODY_TERMS` (128-138)
- `contains_pii`, `mask_pii`
- `medication_safety_refusal` (474-558)
- `_contains_any` (267-274) — cả ba cổng trên đều dùng
- `_ACNE_SCOPE_TERMS`, `_OUT_OF_SCOPE_INTENT_TERMS`, `is_acne_scope_text` — vẫn sống
  qua `_is_acne_scope` trong intake. Xem Phase 6 để sửa

### Đổi tên

- [ ] `guardrails/ood_detector.py` → `guardrails/pii.py`. Sau khi xoá class, cả file
      chỉ còn làm việc phát hiện/che PII; để tên cũ thì người sau sẽ không tìm
      `mask_pii` ở đó
- [ ] Sửa import ở `runner.py:9`, `intake.py:34`, `runtime.py:23`

---

## PHASE 5 — DrugChecker (−69 dòng code, + sửa dữ liệu)

Lưu ý: `DrugChecker.check()` **đang chạy thật** qua `medication_safety_refusal`.
Đây là cải thiện hệ thống sống, không phải dọn code chết.

### Bối cảnh — đọc trước khi làm

Ba phát hiện khi đọc kỹ, xếp theo mức quan trọng:

**Hai luật giá trị nhất KHÔNG dùng DrugChecker.** `medication_safety_refusal`
(runner.py:474-558) hardcode một tập `drug_terms` 13 thuốc ngay trong hàm, tự
tính `preg_block`, tự kiểm cặp isotretinoin+tetracycline bằng tuple literal.
Kết quả `check()` chỉ dùng ở đúng một dòng:
`blocking = [w for w in warnings if w.is_critical or w.interactions_triggered]`.
Nghĩa là DrugChecker chỉ đóng góp khi `preg_block` đã False → thông điệp chung
chung thứ ba. **Đang có hai cơ sở dữ liệu thuốc song song: một trong YAML, một
inline trong hàm gọi YAML.**

**13/18 giá trị `contraindications` trong YAML không bao giờ khớp được.**
`_context_flags` chỉ sinh 5 cờ: `pregnant`, `breastfeeding`, `age_under_8`,
`age_under_12`, `male_patient_acne_use`. YAML còn có `history_thrombosis`,
`smoker_over_35`, `potassium_supplements`, `iron_supplements`,
`pregnant_first_trimester`, `pregnant_third_trimester`,
`pregnant_high_concentration` — không trường nào trong `UserContext` sinh ra
chúng. Và sáu giá trị là **tên thuốc đặt nhầm ô**: `benzoyl_peroxide`,
`clindamycin_topical`, `doxycycline`, `tetracycline`, `tretinoin_topical`,
`erythromycin_topical` — chúng thuộc `interactions`, nằm ở `contraindications`
thì vĩnh viễn im.

**Toàn bộ `warnings_vi` chưa từng đến mắt người dùng.** 20 đoạn cảnh báo tiếng
Việt chỉ được đọc bởi `_apply_drug_checker` (chết, xoá ở Phase 3b) và
`format_warnings_for_prompt` (0 caller). Caller thật tự viết ba câu cứng của
riêng nó.

**Quyết định: phương án A — xoá hẳn `DrugChecker`, giữ 3 luật bằng ~6 dòng.**

Sau khi dò hết dữ liệu YAML, đây là những gì thật sự mất và không mất.

*Mất đúng ba luật*, và cả ba đều là một dòng `if`:

| Luật | Thuốc | Bảo toàn bằng |
|---|---|---|
| dưới 8 tuổi | doxycycline, minocycline, tetracycline | `has_tetracycline` **đã tính sẵn** ở runner.py:521 |
| dưới 12 tuổi | isotretinoin, lymecycline | `has_isotretinoin` đã tính sẵn ở runner.py:520 |
| nam giới | spironolactone | `user.context.sex` |

*Không mất gì ở `interactions`.* Cặp duy nhất đáng giá — isotretinoin +
tetracycline — **đã nằm inline** trong caller (runner.py:520-524, 531-536).
Phần còn lại chia hai:

- Vế kia là thuốc ngoài da liễu (`warfarin`, `oral_contraceptives`, `antacids`,
  `iron_supplements`, `ace_inhibitors`, `nsaids`, `rifampicin`) — intaker không
  bao giờ trích ra vì schema chỉ canonical hoá hoạt chất trị mụn. Không bao giờ khớp.
- **Đang gây hại:** `benzoyl peroxide ↔ tretinoin_topical`, `dapsone ↔ benzoyl_peroxide`,
  `zinc ↔ tetracycline`. Code coi `interactions_triggered` là **điều kiện chặn**,
  nên người khai dùng BPO sáng + tretinoin tối — phác đồ chuẩn — bị từ chối tư vấn.
  Xoá DrugChecker **sửa một lỗi over-block**, không chỉ xoá code.

*Sửa thêm một bug tiềm ẩn:* `medication_safety_refusal:512` gọi
`self._drug_checker.check(...)` **không guard `None`**, trong khi `_drug_checker`
được phép là `None` khi thiếu YAML (runner.py:326-330). Hàm chết
`_apply_drug_checker` thì có guard. Đường sống đang có `AttributeError` chờ sẵn.

### 5a. Xoá `DrugChecker`, giữ 3 luật (−367 dòng)

- [ ] Xoá cả file `guardrails/drug_checker.py` (358)
- [ ] `runner.py:10` — xoá import
- [ ] `runner.py:324-330` — xoá khối init `_drug_checker` (7)
- [ ] `runner.py:512-518` — xoá `warnings` / `blocking`, đổi điều kiện thoát
      thành `if not preg_block and not age_block and not male_block: return None`
- [ ] Thêm ~6 dòng ba luật trên, đặt ngay sau khối `has_isotretinoin` /
      `has_tetracycline` đã có
- [ ] Xoá test của `drug_checker`

### 5b. Hai chỗ phải sửa theo, nếu quên sẽ vỡ

- [ ] **`config/drugs_acne.yaml`: GIỮ LẠI.** `datagen/gates.py:519-520` đang đọc
      nó để lấy danh sách hoạt chất và alias cho cổng kiểm dữ liệu. File đổi vai
      từ "database runtime" sang "từ điển thuốc cho datagen" — sửa comment dòng
      2-3 ở đầu file cho khớp, đừng để người sau tưởng nó còn phục vụ request
- [ ] **`utils/logging.py:148-149`** đọc `guardrails._drug_checker._db` để in số
      thuốc trong banner boot. Xoá hai dòng đó, hoặc banner sẽ crash

### 5c. Không làm

Ba việc trong bản kế hoạch trước, nay không còn lý do tồn tại vì bảng không còn
phục vụ runtime:

- ~~Sửa `_normalize` dùng `strip_accents`~~ — hàm đi theo file
- ~~Sửa `_find_in_db` khớp chính xác~~ — như trên
- ~~Gộp `drug_terms` inline vào YAML~~ — giờ inline **là** nguồn sự thật duy nhất,
  đúng như mong muốn, chỉ khác là đạt được bằng cách xoá bảng thay vì gộp vào bảng

Nếu sau này cần mở rộng vốn thuốc (corticoid bôi / "kem trộn", kháng nấm, tên
thương mại VN), chỗ để thêm là tập `drug_terms` trong `medication_safety_refusal`
— một `frozenset` ở module level, không phải một class 358 dòng.

### 5d. Mở rộng vốn thuốc — việc dữ liệu, làm dần

Sau 5a, chỗ để thêm là `frozenset` `drug_terms` ở module level, không phải YAML.
Nhóm đáng thêm nhất, hiện hoàn toàn không có:

- [ ] **Corticoid bôi** — dexamethasone, betamethasone, clobetasol, hydrocortisone,
      và **"kem trộn"**. Nguyên nhân số một gây viêm da corticoid ở người tự trị
      mụn tại VN
- [ ] Kháng nấm — ketoconazole, fluconazole, itraconazole (fungal acne;
      `_ACNE_SCOPE_TERMS` đã có từ "mụn nấm")
- [ ] Tên thương mại VN — Acnotin, Isotrex, Klenzit, Megaduo
- [ ] Hydroquinone, tranexamic acid

Cảnh báo về giới hạn: cổng này chỉ chạy khi **người dùng tự khai tên thuốc**.
Nó không bảo vệ trước việc model tự bịa ra thuốc — đó là lỗ hổng phía output,
Phase 3a vá.

---

## PHASE 6 — Ba bug thật (từ `runtime_audit.md`)

Không phải dọn dẹp, là sửa hành vi sai.

- [ ] **`compute_route_flags` gọi thiếu tham số** — `intake.py:616` truyền
      `(clean_text, history=history)`, bỏ trống `user`, nên
      `has_red_flags` (`intent_router.py:292`) **luôn False**. Mọi red flag
      intaker trích được đều không bật cảnh báo khẩn ở `_safety`.
      Sửa: tính lại cờ sau bước extract, hoặc merge thêm phần phụ thuộc clinical
- [ ] **`_contains_any` khớp chuỗi con** — `runner.py:267`. Đã đo:
      `is_acne_scope_text("con chó nhà tôi bị ốm")` → True vì term `"co"`.
      Ảnh hưởng thật: `_has_established_case` gần như luôn True → bản vá
      `_intent_patch` (clarify→advise) kích hoạt rộng hơn docstring của nó tuyên bố.
      Sửa: ranh giới từ cho mọi term, gộp thành một regex `|`-join compile ở
      module level (vừa đúng vừa nhanh hơn 420 lần `in`)
- [ ] **Cache một-ô của `UnifiedIntake`** — `unified_intake.py:69`. Một ô duy nhất
      trên instance dùng chung; hai request song song ghi đè nhau → intaker chạy
      gấp đôi. Sửa: bỏ cache, cho `run_intake` gọi `_infer()` một lần rồi dùng
      chung cho cả routing lẫn extraction
- [ ] Sau khi sửa `_contains_any`: xem lại có xoá được `_snapshot_has_values` không

---

## PHASE 7 — Hiệu năng (đo trước, sửa sau)

- [ ] **Đo trước.** Chạy 30 request thật, gom p50 từng stage từ `log_pipeline_stage`
      (INPUT / PREPROCESS / SAFETY / ROUTE / EXTRACT / RAG / GENERATE). Mọi con số
      dưới đây là suy luận từ kiến trúc, chưa đo
- [ ] `chat_retrieve_top_k` 25 → 12: cross-encoder đang chấm ~30-35 cặp rồi giữ 5
- [ ] `chat_guideline_top_k` 5 → 1: `ensure_guideline_slot` đằng nào cũng ép đúng
      một đoạn vào ô cuối, retrieve 5 rồi vứt 4 là thừa
- [ ] Cân nhắc trả lời cứng cho intent `reject` thay vì sinh 2048 token
- [ ] **Không** bật `DEVICE=cuda` mù — `llm_keep_alive=-1` giữ cả hai model Ollama
      thường trú VRAM; nhét thêm reranker 2.2GB có thể đẩy Ollama offload xuống RAM
      và làm chậm đi. Đo VRAM headroom trước; nếu chật thì chỉ đưa embedder lên GPU
- [ ] Bỏ `getattr(settings, x, default)` — 5 chỗ có default khác `config.py`
      (`chat_retrieve_top_k` 8≠25, `chat_rerank_top_k` 3≠5,
      `chat_max_context_chars` 4500≠6000, `chat_rerank_floor` 0.58≠0.50,
      `llm_temperature` 0.3≠0.35). Test đang chạy một hệ thống khác production
- [ ] `RateLimitMiddleware._hits` không bao giờ xoá key → rò rỉ chậm
- [ ] `RequestLoggingMiddleware` đo latency tới header đầu tiên, với SSE là ~0 →
      metric p95 trong `/metrics` đang nói dối

---

## PHASE 8 — Dọn thư mục (đã chốt: bỏ phần rủi ro)

Chốt: **không** di chuyển package Python (`datagen`, `evaluation`, `ablation`,
`LLMData`, `guideline_docs`). Lý do ở `CLEANUP_PLAN.md` mục 3 — chúng import
vòng tròn nhau, và mẹo `PYTHONPATH` đổi 20 thư mục lộn xộn lấy một chỗ lệch giữa
đường dẫn và tên module.

- [ ] Xoá `__pycache__` rải rác, xác nhận `.gitignore` đã cover
- [ ] `mkdir docs/archive`, chuyển ~25 file `CODEX_TASK_*`, `*_PROMPT`, `*_PLAN`
      đã hoàn thành vào. **Duyệt từng file**, đừng dùng wildcard mù — `CONFIG_MAP.md`,
      `config_reference.md`, `DOCKER_QUICKSTART.md` vẫn còn giá trị
- [ ] `mkdir docs/reports`, chuyển `context.md`, `report.md`, `smoke_review.md`,
      `runtime_audit.md`, `AcneLLM_config_audit.xlsx` vào
- [ ] Làm rõ `visualization/` vs `visualize/` vs `scripts/visualize/` — ba tên gần
      giống nhau cho ba thứ khác nhau. Đổi tên hoặc thêm một dòng README mỗi cái
- [ ] **Thêm cây thư mục 12 dòng vào `README.md`.** Đây là thứ giải quyết đúng
      vấn đề "nhìn vào là hiểu", và nó không thể làm hỏng import nào

---

## Thứ tự đề xuất

```
Phase 0  (bảo mật)        ── làm ngay, nửa giờ
Phase 1  (xoá vô hại)     ── một buổi sáng
Phase 8  (docs + README)  ── 40 phút, xen kẽ được
Phase 2  (đã chốt)        ── nửa buổi
Phase 6  (ba bug)         ── nửa buổi, diff nhỏ nhưng đang sai hành vi
Phase 3  (port + xoá)     ── nửa buổi, thứ tự bắt buộc
Phase 4  (scope + OOD)    ── nửa buổi
Phase 5  (DrugChecker)    ── 5a+5b nửa buổi; 5d là dữ liệu, làm dần
Phase 7  (hiệu năng)      ── sau cùng, và chỉ sau khi đã đo
```

Phase 6 xếp sớm hơn Phase 3-5 vì đó là hành vi sai đang chạy trong production,
còn 3-5 chỉ là code thừa. Code thừa không làm ai đau; `has_red_flags` luôn False
thì có.
