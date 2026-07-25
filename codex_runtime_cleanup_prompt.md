# Nhiệm vụ Codex: Dọn runtime — logging rõ ràng, config→.env, gom fallback vào `fallback/`

Bạn là agent thực thi. Ba việc, làm **cẩn thận, không được để lỗi runtime**. Sau mỗi phần phải chạy kiểm.
KHÔNG đổi hành vi pipeline, chỉ tổ chức lại + làm sạch log + di chuyển file fallback.

**Đọc trước:** `src/acne_llm/di.py`, `src/acne_llm/api/app.py`, `src/acne_llm/utils/logging.py`,
`src/acne_llm/config.py`, `src/acne_llm/chat/intake.py`, `src/acne_llm/chat/unified_intake.py`,
`docs/UNIFIED_INTAKE_INTEGRATION_PLAN.md`.

---

## Ràng buộc cứng (vi phạm = fail)

1. **KHÔNG deploy/ollama/train.** Chỉ chạy `pytest -q`, `ruff check` (nếu có), và `python -c "import ..."` để verify import.
2. **KHÔNG đổi logic pipeline** — chỉ log, tổ chức file, và nguồn config. Output hành vi giữ nguyên.
3. **KHÔNG di chuyển safety substrate.** `normalizer.py`, `extraction_confidence.py`, `guardrails/` là **always-on**, KHÔNG phải fallback → giữ nguyên chỗ.
4. **Sau mỗi phần chạy `pytest -q` — phải xanh** trước khi sang phần sau. Cuối cùng verify import toàn app không gãy.
5. **Không xoá field config mà code đang tham chiếu** (sẽ vỡ). Chỉ dời giá trị sang `.env` + gom nhóm; field dead thật sự mới bỏ, kèm grep chứng minh 0 tham chiếu.

---

## PHẦN A — Gom script fallback vào `src/acne_llm/chat/fallback/`

**Tạo package `src/acne_llm/chat/fallback/__init__.py` và MOVE vào đó (chỉ các script fallback-only):**
- `semantic_router.py`   → `fallback/semantic_router.py`
- `intent_router.py`     → `fallback/intent_router.py`  (rule router)
- `llm_router.py`        → `fallback/llm_router.py`      (dùng khi `intake_mode=legacy`)
- `llm_extractor.py`     → `fallback/llm_extractor.py`

**KHÔNG MOVE (always-on, giữ nguyên `chat/`):**
- `normalizer.py`, `extraction_confidence.py`, `guardrails/*`, `preprocess.py`, `orchestrator.py`,
  `intake.py`, `unified_intake.py`, `session.py`, các `_*.py` helper của luồng chính.

**Tách parser dùng chung TRƯỚC khi move** (nếu chưa có): các helper mà `unified_intake.py` cần từ
`llm_extractor.py` (`_scalar_node`, `_list_nodes`, `_enum_fr`, `_int_fr`, `_bool_fr`, `_to_user_input`,
`_to_extraction_confidence`, `_extract_json`, `_validate_contract`, enum set) → chuyển sang
`src/acne_llm/chat/_intake_parse.py` (nằm ở `chat/`, KHÔNG vào fallback). `fallback/llm_extractor.py`
và `unified_intake.py` cùng import từ `_intake_parse`. Tránh import vòng.

**Giữ connection:** cập nhật MỌI import trỏ tới các file đã move:
- `di.py`: import router/extractor fallback từ `acne_llm.chat.fallback.*`.
- `intake.py`: `route_intent`, `RouteDecision`, `RouterFallback`, `ExtractorFallback` → nguồn mới.
- `scripts/` + `evaluation/`: grep `chat.semantic_router|chat.intent_router|chat.llm_router|chat.llm_extractor` → sửa hết sang `chat.fallback.*`.
- Verify: `grep -rn "chat\.\(semantic_router\|intent_router\|llm_router\|llm_extractor\)" src scripts evaluation` = rỗng (trừ trong `fallback/`).

---

## PHẦN B — Chuyển tham số config.py sang `.env` (một nguồn giá trị)

`config.py` là `BaseSettings(env_file=".env")` — `.env` đã override field. Mục tiêu: **`.env` là nguồn giá trị
chính thức**, `config.py` chỉ còn schema + validator + default cấu trúc; gom nhóm gọn.

1. **Phân loại 77 field** thành 2 nhóm (ghi bảng vào `docs/CONFIG_MAP.md`):
   - **OPERATIONAL** (operator chỉnh thường xuyên): model names, timeouts, sampling (temp/top_p/top_k/…),
     keep_alive, thresholds (retrieval, rerank floors, semantic router), top_k, feature flags, device.
     → **Bắt buộc có mặt tường minh trong `.env.baseline`** với đúng giá trị hiện tại, gom nhóm + comment.
   - **STRUCTURAL/INTERNAL** (hiếm đổi, thuộc code): đường dẫn data/index, tên file, prompts_dir, validator.
     → Có thể giữ default trong `config.py` (vẫn cho override qua env nhưng không cần liệt kê trong `.env`).
2. **Cập nhật `.env.baseline`** = template đầy đủ mọi param OPERATIONAL, chia section rõ
   (`# ── LLM answer (7B) ──`, `# ── Unified intake (3B) ──`, `# ── Fallback router ──`,
   `# ── RAG / retrieval ──`, `# ── Embedding/rerank ──`…), mỗi dòng có comment ngắn + giá trị hiện tại.
   Đồng bộ `.env` thật của máy (giữ giá trị đang chạy, chỉ thêm cái thiếu — KHÔNG ghi đè giá trị người dùng).
3. **Slim `config.py`:** giữ `class Settings` + validators + field (schema cần field để type/validate),
   nhưng **gom nhóm bằng comment section trùng khớp `.env.baseline`**, bỏ comment rác/số cũ (vd `#4096`),
   và **đánh dấu rõ** khối legacy (`extractor_model`, `router_model` — chỉ dùng ở `intake_mode=legacy`).
   KHÔNG bỏ field còn được tham chiếu (grep chứng minh trước khi bỏ bất kỳ field nào).
4. **Không phá `SettingsConfigDict`** — `.env` vẫn ưu tiên hơn default. Test: đổi 1 biến trong `.env`
   → `Settings().<field>` phản ánh đúng.

---

## PHẦN C — Logging: rõ ràng, thống nhất, đúng runtime hiện tại

Giữ loguru + format PowerShell-friendly ở `utils/logging.py`. Mục tiêu: **banner startup phản ánh đúng
runtime unified hiện tại** và **log per-request dễ đọc theo pipeline**.

1. **Banner startup — gom thành một khối mạch lạc** (hiện đang rải rác + lệch runtime):
   thay các dòng lẻ (`LLM effective`, `Modelfile PARAMETER`, `Unified intake`, `RAG ready`…) bằng một
   block căn cột, phản ánh đúng kiến trúc:
   ```
   ── AcneLLM runtime ─────────────────────────────
   intake_mode : unified   (fallback: semantic → rule → deterministic)
   intake 3B   : acne-intake        keep_alive=… timeout=…
   answer 7B   : acnellm-role        ctx=… keep_alive=…
   embedder    : … (cpu)   reranker : …
   RAG         : Chroma …k vectors | BM25 …
   safety      : substrate always-on | guardrails N drugs
   ────────────────────────────────────────────────
   ```
   Lấy giá trị thật từ settings/di. Nếu `intake_mode=legacy` thì in nhánh legacy tương ứng.
2. **Log per-request — chuẩn hoá tag theo tầng pipeline**, đọc top-down khớp sơ đồ. Định dạng đồng nhất:
   `[{sid}] {STAGE:<10} {key=val ...} ({elapsed}ms)`. Các STAGE thống nhất viết hoa cố định:
   `INPUT, PREPROCESS, SAFETY, INTAKE, ROUTE, EXTRACT, RAG, GENERATE, OUTPUT` (map từ tag hiện tại
   INPUT/PREFLIGHT/GUARDRAILS/ROUTE/EXTRACTOR/NORMALIZE… về bộ này). Mỗi stage log **elapsed** để debug latency.
   Ghi rõ khi rơi fallback: `ROUTE intent=… source=unified_intake|semantic|rule reason=…`.
3. **Không đổi mức log của lỗi/an toàn** — hard block, guardrail refuse vẫn log rõ. Chỉ format lại, không giấu.
4. Đảm bảo file sink (DEBUG) vẫn đầy đủ; console gọn hơn.

---

## Verify cuối (bắt buộc, in ra báo cáo)

- `pytest -q` xanh toàn bộ.
- `python -c "from acne_llm.api.app import app"` — import app không gãy (không boot server).
- `grep -rn "chat\.\(semantic_router\|intent_router\|llm_router\|llm_extractor\)" src scripts evaluation` = rỗng (ngoài `fallback/`).
- `python -c "from acne_llm.config import Settings; Settings()"` OK; đổi thử 1 biến `.env` → phản ánh đúng.
- `ruff check src` (nếu có) sạch import thừa.

## Definition of Done
- [ ] `chat/fallback/` chứa semantic_router, intent_router, llm_router, llm_extractor; `_intake_parse.py` ở `chat/`; import cập nhật; grep sạch.
- [ ] safety substrate (`normalizer`, `extraction_confidence`, `guardrails`) KHÔNG bị move.
- [ ] `.env.baseline` đầy đủ param OPERATIONAL có comment; `config.py` slim + nhóm + validators giữ nguyên; `docs/CONFIG_MAP.md` bảng phân loại.
- [ ] Banner startup một khối, đúng runtime unified; log per-request chuẩn STAGE + elapsed.
- [ ] `pytest -q` xanh; import app OK; hành vi pipeline không đổi.
- [ ] Báo cáo: cây file sau dọn, diff tóm tắt, kết quả các lệnh verify.
