# Codex — E0: dọn config trước khi chạy thí nghiệm nút thắt

## Mục tiêu

Repo có 5 chỗ một giá trị nằm ở 2 nơi, và 4 bug khiến mọi con số eval từ trước
tới nay không đáng tin. Task này sửa **chỉ phần config** — không đụng logic
retrieval, intake, generator.

Không làm E0 thì mọi eval sau đó là đo bằng thước gãy.

**Nguồn sự thật:** `docs/config_layout.md` (quy tắc) + `docs/config_reference.md`
(từ điển 85 field). Đọc cả hai trước khi bắt đầu. Nếu file này mâu thuẫn với
2 file kia, file này thắng.

---

## ⚠️ 4 quyết định đã chốt — sửa ở đây nếu người dùng muốn khác

```
JUDGE_PROVIDER  = anthropic          # judge phải KHÁC nhà với generator arm Y
JUDGE_MODEL     = claude-sonnet-5
ARM_Y_MODEL     = gpt-5.4-mini       # dùng ở GĐ2, E0 chỉ cần chừa chỗ
ARM_W           = có                 # thêm arm RAG-oracle
PHẠM VI PROMPT  = chỉ E0             # không làm sang GĐ1/GĐ2
```

---

## Ràng buộc

- **KHÔNG** đổi hành vi runtime. Sau E0, mọi câu trả lời phải giống hệt trước E0
  (trừ đúng 1 ngoại lệ ghi ở Task 6).
- **KHÔNG** đụng `rag/retriever.py` ngoài đúng 1 dòng ở Task 5.
- **KHÔNG** đổi `extra="ignore"` thành `"forbid"` — `.env` cố ý chứa key cho
  `datagen/` và `LLMData/` đọc qua `os.environ`. Dùng test ở Task 7 thay thế.
- **KHÔNG** xóa `extractor_*` / `router_*` trong config.py — chúng là arm legacy
  cho A/B (task B7), xóa sau khi thí nghiệm nút thắt kết thúc.
- **KHÔNG** đánh số lại mã lỗi.
- Mỗi task một commit riêng, message tiếng Việt ngắn.

---

## Task 1 — `.env`: 32 key → 16

### 1a. Xóa 5 key chết (không file .py nào đọc — đã verify)

```
GUARDRAILS_ENABLE_OOD          # OOD thật = semantic_router_oos_distance_threshold
GUARDRAILS_OOD_THRESHOLD
USER_AGENT                     # scripts/crawl_official_guidelines.py:37 hardcode UA riêng
JUDGE_REASONING_EFFORT
MINIMAX_API_KEY
```

### 1b. Xóa 11 key trùng y hệt default config.py

```
CHROMA_DIR  BM25_PATH  DOCS_JSONL  CHUNKS_JSONL
PROMPTS_DIR  GUARDRAILS_YAML  SEED_SOURCES
API_HOST  API_PORT  LLM_FALLBACK_MODEL  GUARDRAILS_SCOPE_MODE
```

### 1c. Xóa 4 key nữa

```
EXTRACTOR_MODE       # di.py:165 ép về "llm" bất kể .env đặt gì (khi unified)
EXTRACTOR_MODEL      # di.py:136 bỏ qua cả nhánh này khi intake_mode=unified
EXTRACTOR_TIMEOUT
OLLAMA_GENERATE_TIMEOUT   # đang đặt 180, che đúng latency mà task D1 sắp đo → về default 30
```

### 1d. Thêm 4 key

```
INTAKE_MODE=unified
INTAKE_MODEL=acne-intake
JUDGE_PROVIDER=anthropic
ANTHROPIC_API_KEY=
```

### 1e. `.env` mục tiêu

```ini
# ============================================================
# .env — CHỈ: secret + giá trị khác theo máy/lần chạy.
# Mọi hằng số tuning ở src/acne_llm/config.py. Đừng copy vào đây.
# Quy tắc 3 tầng: docs/config_layout.md
# ============================================================

# ── Secrets (KHÔNG commit) ───────────────────────────────────
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
DATAGEN_API_KEY=
API_KEY=                              # trống = API không yêu cầu auth

# ── Máy này ──────────────────────────────────────────────────
OLLAMA_URL=http://localhost:11434
DEVICE=cpu                            # cuda nếu VRAM >= 12GB
LOG_LEVEL=DEBUG                       # INFO cho production

# ── Model đang chạy (đổi theo lần build / theo arm X-Y-Z-W) ──
LLM_MODEL=acnellm-role
INTAKE_MODE=unified                   # unified | legacy
INTAKE_MODEL=acne-intake

# ── Judge (eval) — PHẢI khác nhà với generator arm Y ─────────
JUDGE_PROVIDER=anthropic
JUDGE_MODEL=claude-sonnet-5

# ── Datagen (LLMData/chunk_qa đọc riêng qua os.environ) ──────
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# ── Deploy ───────────────────────────────────────────────────
CORS_ORIGINS=["*"]                    # PROD: ["https://domain-cu-the.com"]
```

> **Giữ nguyên giá trị secret đang có trong `.env` hiện tại** — chỉ sắp xếp lại,
> không xóa giá trị. Người dùng sẽ tự xoay vòng key sau.

### 1f. Cập nhật `.env.baseline`

Đồng bộ theo cấu trúc mới. `.env.baseline` **có** bị git track — tuyệt đối
không đưa giá trị secret thật vào, để trống sau dấu `=`.

---

## Task 2 — `config.py`: xóa 8 field chết 🔴

```
retrieve_top_k                  # không file nào trong src/ đọc; production dùng chat_retrieve_top_k
chat_rerank_top_k_clinical
extract_fuzzy_accept
extract_fuzzy_review
extract_safety_accept
bm25_normalize
english_input_notice
embedding_model_multilingual
```

**Trước khi xóa `retrieve_top_k`:** sửa 3 caller đang dùng key dict cùng tên với
default sai (15, trong khi production là 6):

| File:dòng | Sửa thành |
|---|---|
| `evaluation/adapters/extractive.py:51,52,57` | `cfg.get("retrieve_top_k", settings.chat_retrieve_top_k)` |
| `evaluation/unit/eval_context_sensitivity.py:173,174,180` | như trên |
| `scripts/eval_rag.py:1495` | sửa help text: `default = settings.chat_retrieve_top_k (=6)` |

Đây là bug #2: **eval đang retrieve 15 chunk trong khi production retrieve 6.**

---

## Task 3 — `config.py`: xóa 3 field citation 🟡

```
inline_citation
chat_min_citation_score
chat_require_citations          # comment tự ghi "runtime không đọc field này"
```

Chỉ xóa **field**. Việc gỡ citation khỏi 11 file evaluation là task E1, không
thuộc prompt này. Nếu file nào đang import 3 field trên thì để lại một
`ponytail:` comment tại chỗ thay vì sửa lan sang E1.

---

## Task 4 — `config.py`: xóa 5 field đã có bản thật ở tầng module 🔵

```
retrieval_source_boosts         # bản thật: rag/retriever.py:14  _SOURCE_TYPE_BOOST
retrieval_trust_boosts          # bản thật: rag/retriever.py:26  _TRUST_LEVEL_BOOST
retrieval_authority_boost       # bản thật: rag/retriever.py:27  _AUTHORITY_TAG_BOOST
session_history_char_budget     # bản thật: chat/session.py:39   HISTORY_CHAR_BUDGET = 2000  (config ghi nhầm 3000)
session_max_history_turns       # bản thật: chat/session.py:42   HISTORY_WINDOW_TURNS = 6    (config ghi nhầm 10)
```

**Không** thêm injection point cho chúng. Chưa ai từng tune qua env — thêm
3 param mới cho 0 người dùng là đi ngược mục tiêu của task này.

Ở mỗi hằng số module, thêm 1 dòng comment ghi rõ nó là nguồn sự thật duy nhất.

---

## Task 5 — sửa `_DENSE_MAX_DISTANCE`

`rag/retriever.py:28`:

```python
_DENSE_MAX_DISTANCE: float = 0.48  # tightened: loại chunk xa centroid (was 0.60)
```

Nhưng `di.py:307` luôn truyền `settings.dense_max_distance = 0.60` vào
constructor → việc siết xuống 0.48 **chưa từng có hiệu lực**. Người dùng đã
xác nhận: **0.60 đúng, 0.48 sai.**

Sửa thành:

```python
# Default cho caller trực tiếp/test. Production: di.py truyền settings.dense_max_distance đè lên.
_DENSE_MAX_DISTANCE: float = 0.60
```

Đây là chỗ duy nhất trong repo mà **config thắng code**. Bốn chỗ ở Task 4 thì
ngược lại — code thắng. Ghi rõ sự bất đối xứng này vào docstring đầu
`retriever.py` để người sau không đoán nhầm.

---

## Task 6 — gộp 2 rerank floor

`chat_rerank_ood_floor = 0.58` và `chat_rerank_keep_floor = 0.58` — cùng tầng,
cùng giá trị, hai tên. Gộp thành **`chat_rerank_floor: float = 0.58`**, sửa mọi
caller.

Giữ nguyên comment giải thích vì sao phải `> 0.50` (sigmoid(0)=0.50 là mức
ngẫu nhiên; bản cũ để 0.45 nên guard chưa từng kích hoạt).

> Đây là **ngoại lệ hành vi duy nhất** được phép: nếu 2 floor từng được đặt khác
> nhau qua `.env` thì hành vi sẽ đổi. Hiện `.env` không đặt cả hai → không đổi gì.

---

## Task 7 — thêm 2 field judge 🆕 + bỏ hardcode

### 7a. `config.py`, section mới cuối file

```python
# ── Judge (eval) ─────────────────────────────────────────────────────────
# Judge PHẢI khác nhà với generator của arm Y. Thiên vị tự-ưu-ái cùng cỡ
# với delta đang đo (vài điểm) → nếu cùng nhà sẽ thổi phồng đúng con số
# quyết định kết luận "generator có phải nút thắt không".
judge_provider: Literal["anthropic", "openai", "deepseek"] = "anthropic"
judge_model: str = "claude-sonnet-5"
```

### 7b. `evaluation/judges/clients.py:23`

```python
DEFAULT_OPENAI_JUDGE_MODEL = "gpt-5-mini-2025-08-07"   # hardcode, bỏ qua .env
```

Đây là bug #1: `JUDGE_MODEL=o4-mini` trong `.env` **chưa bao giờ được đọc** —
mọi điểm chấm từ trước tới nay chạy bằng `gpt-5-mini`.

Sửa để client đọc `settings.judge_provider` + `settings.judge_model`. Giữ hằng
số cũ làm fallback cho caller truyền `model=` tường minh. Cập nhật các caller:
`run_judge.py:34,371` · `bias_tests.py:25,47` · `run_preliminary_d2.py:23,97,202` ·
`run_all.py:28,165` · `tests/test_judge_openai.py`.

Nếu chưa có client Anthropic trong `clients.py`, thêm một class tối thiểu theo
đúng interface class OpenAI hiện có — không refactor sang abstraction mới.

---

## Task 8 — test chốt chặn

`tests/test_env_keys.py`, ~25 dòng, không framework mới:

```python
from pathlib import Path

# Key đọc qua os.environ, không qua Settings — hợp lệ nhưng không có field
ALLOWLIST = {
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "DATAGEN_API_KEY",
}


def test_khong_co_env_key_mo_coi():
    """extra='ignore' nuốt im lặng mọi key gõ sai. Test này là cái chốt."""
    from acne_llm.config import Settings
    fields = set(Settings.model_fields)
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=")[0].strip()
        assert key.lower() in fields or key in ALLOWLIST, (
            f"{key} trong .env không khớp field nào và không có trong ALLOWLIST"
        )


def test_settings_thang_hang_so_module():
    """Chặn tái phát bug _DENSE_MAX_DISTANCE=0.48 không có hiệu lực."""
    from acne_llm.config import settings
    from acne_llm.di import build_container
    c = build_container(settings)
    assert c.retriever.dense_max_distance == settings.dense_max_distance
```

Nếu `build_container` quá nặng cho unit test, thay test thứ hai bằng cách so
trực tiếp `retriever._DENSE_MAX_DISTANCE == settings.dense_max_distance`.

---

## Task 9 — dọn rác + sửa comment nói dối

### 9a. Xóa

```
src/acne_llm/di.py.bak.20260529      # file .bak nằm trong src/
config/settings.py                    # shim 4 dòng — sửa import ở caller sang acne_llm.config
```

Grep `from config.settings` / `config.settings` trước khi xóa.

### 9b. Sửa 3 comment mâu thuẫn với code

| File:dòng | Comment sai | Sự thật |
|---|---|---|
| `config.py:50` | "Default **legacy** preserves the current two-model runtime" | code là `= "unified"` |
| `config.py:42` | "30s đủ cho mọi request" | `.env` từng đặt 180 (Task 1c đã bỏ) |
| `scripts/eval_rag.py:1495` | "default=10 y chang `settings.chat_retrieve_top_k` production" | thật ra là 6 |

---

## Định nghĩa "xong"

```
[ ] .env đúng 16 key, .env.baseline đồng bộ và không chứa secret
[ ] config.py còn 70 field  (85 − 8🔴 − 5🔵 − 3🟡 − 1 gộp + 2🆕)
[ ] grep toàn repo: 0 tham chiếu tới 16 field đã xóa
[ ] pytest xanh, gồm 2 test mới ở Task 8
[ ] `python -c "from acne_llm.config import settings; print(settings.judge_model)"`
    in ra claude-sonnet-5
[ ] API khởi động được, 1 câu hỏi chat trả lời bình thường
[ ] Chạy 1 câu qua pipeline trước/sau E0 → output giống hệt nhau
```

Cuối cùng cập nhật `docs/config_reference.md` và `docs/config_layout.md` cho
khớp trạng thái thật (đổi ✅/🔴/🔵 thành "đã xong"), rồi báo cáo:

- danh sách file đã sửa + số dòng
- field/key nào **không xóa được** và vì sao (nếu có)
- bất kỳ chỗ nào phát hiện thêm một giá trị nằm ở 2 nơi

## Không làm gì trong prompt này

Gỡ citation khỏi 11 file (E1) · `metrics.py` (B1) · `scorecard.py` ·
`eval_unified_intake.py` (B2) · `eval_bottleneck.py` · mọi task nhóm A/B/C/D.
