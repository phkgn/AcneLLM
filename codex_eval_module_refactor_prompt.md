# Codex — Refactor toàn bộ module evaluation

> Thay thế `codex_config_cleanup_prompt.md` (file đó là Phase A của file này).

## Mục tiêu

`evaluation/` có 17.7k dòng / 16 thư mục con, và đang đo sai hệ ở 4 chỗ. Refactor
để mọi con số eval sau này đáng tin, rồi mới chạy thí nghiệm nút thắt X/Y/Z/W.

**Nguồn sự thật kèm theo:** `docs/config_layout.md`, `docs/config_reference.md`.
Nếu mâu thuẫn, file này thắng.

---

## Cấu hình đã chốt

```
JUDGE_PROVIDER = openai
JUDGE_MODEL    = gpt-5.4-mini        # $0.75/$4.50, không có reasoning token ẩn
ARM_Y_MODEL    = gpt-5.6-terra       # arm Y phải KHÁC model judge — cùng model
                                     # tự chấm mình là dạng thiên vị mạnh nhất
ARM_W          = có
```

---

## 4 bug đang làm sai mọi số đo — sửa hết trong Phase A+B

| # | Bug | Chỗ |
|---|---|---|
| 1 | `JUDGE_MODEL` trong `.env` **chưa bao giờ được đọc** — judge thật là `gpt-5-mini`, hardcode ở **2 nơi** | `judges/clients.py:23` **và** `dashboard/lib/commands.ts:16-17` |
| 2 | Eval retrieve **15** chunk, production retrieve **6** | `adapters/extractive.py:51`, `unit/eval_context_sensitivity.py:173` |
| 3 | Bảng boost trong config bị bỏ qua, `retriever.py` hardcode | `config.py:189` vs `rag/retriever.py:14` |
| 4 | `session_history_char_budget=3000` chết, thật là **2000** | `config.py:257` vs `chat/session.py:39` |

---

## Cách chạy

**Viết code liên tục từ Phase A tới Phase G trong một lượt.** Mỗi Phase một
commit riêng, message tiếng Việt ngắn.

**Chỉ Phase A có cửa kiểm chứng bắt buộc.** Sau khi viết xong Phase A, dừng lại
và chạy:

```
pytest
python -c "from acne_llm.config import settings; print(settings.judge_model)"
# chạy 1 câu hỏi qua pipeline, so output với bản trước Phase A
```

- **Xanh** → viết tiếp B→G không dừng nữa.
- **Đỏ** → **DỪNG HẲN**, không viết B→G. Báo cáo cái gì hỏng và vì sao.

Lý do: Phase A đổi config toàn repo và phải giữ output y hệt. Sai ở đây thì
B→G xây trên nền gãy — sửa sau đắt gấp nhiều lần.

Phase B→G chạy `pytest` một lần ở cuối cùng, không gate từng phase.

## Ràng buộc chung
- **KHÔNG** đổi `extra="ignore"` → `"forbid"`.
- **KHÔNG** xóa `extractor_*` / `router_*` trong `config.py` — arm legacy cho A/B.
- **KHÔNG** đánh số lại mã lỗi. `E13` để thành khoảng trống.
- **KHÔNG** đụng `analysis/figures_*.py` (2.6k dòng vẽ hình) — ngoài phạm vi.
- **KHÔNG** tạo abstraction mới. Tái dùng hàm đã có, chi tiết ở Phase E.

---

# PHASE A — Config (bug #2, #3, #4)

## A1. `.env`: 32 key → 16

**Xóa 5 key chết** (đã verify không file .py nào đọc):
`GUARDRAILS_ENABLE_OOD` · `GUARDRAILS_OOD_THRESHOLD` · `USER_AGENT`
(crawler hardcode UA riêng ở `scripts/crawl_official_guidelines.py:37`) ·
`JUDGE_REASONING_EFFORT` · `MINIMAX_API_KEY`

**Xóa 11 key trùng y hệt default config.py:**
`CHROMA_DIR` `BM25_PATH` `DOCS_JSONL` `CHUNKS_JSONL` `PROMPTS_DIR`
`GUARDRAILS_YAML` `SEED_SOURCES` `API_HOST` `API_PORT` `LLM_FALLBACK_MODEL`
`GUARDRAILS_SCOPE_MODE`

**Xóa 4 key nữa:**
- `EXTRACTOR_MODE` — `di.py:165` ép về `"llm"` bất kể `.env` đặt gì
- `EXTRACTOR_MODEL`, `EXTRACTOR_TIMEOUT` — `di.py:136` bỏ qua cả nhánh khi `intake_mode=unified`
- `OLLAMA_GENERATE_TIMEOUT` — đang 180, che đúng latency task D1 sắp đo → về default 30

**Thêm 3 key:** `INTAKE_MODE=unified` · `INTAKE_MODEL=acne-intake` · `JUDGE_PROVIDER=openai`

`.env` mục tiêu: xem `docs/config_layout.md` mục "Tầng 1". Giữ nguyên giá trị
secret hiện có, chỉ sắp xếp lại. Đồng bộ `.env.baseline` (file này **có** bị git
track — để trống sau dấu `=`, không đưa secret thật vào).

## A2. `config.py`: xóa 8 field chết 🔴

```
retrieve_top_k  chat_rerank_top_k_clinical  extract_fuzzy_accept
extract_fuzzy_review  extract_safety_accept  bm25_normalize
english_input_notice  embedding_model_multilingual
```

**Trước khi xóa `retrieve_top_k`, sửa 3 caller — đây là bug #2:**

| File:dòng | Sửa thành |
|---|---|
| `evaluation/adapters/extractive.py:51,52,57` | `cfg.get("retrieve_top_k", settings.chat_retrieve_top_k)` |
| `evaluation/unit/eval_context_sensitivity.py:173,174,180` | như trên |
| `scripts/eval_rag.py:1495` | help text: `default = settings.chat_retrieve_top_k (=6)` |

## A3. `config.py`: xóa 5 field đã có bản thật ở tầng module 🔵

```
retrieval_source_boosts       → rag/retriever.py:14   _SOURCE_TYPE_BOOST
retrieval_trust_boosts        → rag/retriever.py:26   _TRUST_LEVEL_BOOST
retrieval_authority_boost     → rag/retriever.py:27   _AUTHORITY_TAG_BOOST
session_history_char_budget   → chat/session.py:39    HISTORY_CHAR_BUDGET = 2000
session_max_history_turns     → chat/session.py:42    HISTORY_WINDOW_TURNS = 6
```

**Không** thêm injection point. Chưa ai tune qua env — thêm 3 param cho 0 người
dùng là đi ngược mục tiêu. Ở mỗi hằng số module, thêm 1 dòng comment ghi rõ nó
là nguồn sự thật duy nhất.

## A4. `_DENSE_MAX_DISTANCE` — chỗ duy nhất config thắng code

`rag/retriever.py:28` đang `= 0.48` kèm comment "tightened (was 0.60)", nhưng
`di.py:307` luôn truyền `settings.dense_max_distance = 0.60` đè lên → việc siết
chưa từng có hiệu lực. **Người dùng đã xác nhận 0.60 đúng, 0.48 sai.**

```python
# Default cho caller trực tiếp/test. Production: di.py truyền settings đè lên.
_DENSE_MAX_DISTANCE: float = 0.60
```

Ghi sự bất đối xứng này (A3 code thắng ↔ A4 config thắng) vào docstring đầu
`retriever.py` để người sau không đoán nhầm.

## A5. Gộp 2 rerank floor

`chat_rerank_ood_floor` + `chat_rerank_keep_floor` cùng `0.58`, cùng tầng →
**`chat_rerank_floor: float = 0.58`**. Giữ nguyên comment giải thích vì sao phải
`> 0.50`. Đây là **ngoại lệ hành vi duy nhất** được phép trong Phase A.

## A6. Dọn rác + 3 comment nói dối

Xóa `src/acne_llm/di.py.bak.20260529` và `config/settings.py` (shim 4 dòng — grep
`config.settings` trước, sửa caller sang `acne_llm.config`).

| File:dòng | Comment sai | Sự thật |
|---|---|---|
| `config.py:50` | "Default **legacy** preserves…" | code là `= "unified"` |
| `config.py:42` | "30s đủ cho mọi request" | `.env` từng đặt 180 |
| `scripts/eval_rag.py:1495` | "default=10 y chang production" | thật ra là 6 |

---

# PHASE B — Judge (bug #1)

## B1. Thêm 2 field vào `config.py`

```python
# ── Judge (eval) ─────────────────────────────────────────────────────────
judge_provider: Literal["openai", "anthropic", "deepseek"] = "openai"
judge_model: str = "gpt-5.4-mini"
```

## B2. Bỏ hardcode ở `judges/clients.py:23`

```python
DEFAULT_OPENAI_JUDGE_MODEL = "gpt-5-mini-2025-08-07"   # bỏ qua .env hoàn toàn
```

Sửa để client đọc `settings.judge_provider` + `settings.judge_model`. Giữ hằng số
cũ làm fallback cho caller truyền `model=` tường minh.

**Caller phải cập nhật:** `run_judge.py:34,371` · `bias_tests.py:25,47` ·
`dashboard/scripts/run_preliminary_d2.py:23,97,202` · `run_all.py:28,165` ·
`tests/test_judge_openai.py:12,42,95,143`

## B3. Ghi model thật vào mọi output

Mọi file kết quả judge phải ghi `judge_model` **thật sự đã dùng**, không phải
hằng số. Bug #1 tồn tại được vì không ai kiểm tra chéo được từ file kết quả.

---

# PHASE C — Gỡ citation (E1 + A6 trên bảng)

## C1. Xóa 5 hàm citation khỏi `metrics/deterministic.py`

```
citation_valid:45   resolve_citation_id:63   _normalize_citation_alias:129
citation_present:133   _meaningful_prose_citation_numbers:143
```

Gỡ luôn nhánh gọi chúng trong `evaluate_record:188`.

## C2. GIỮ NGUYÊN `metrics/grounding.py`

`GroundingScorer` đo **source support** (câu trả lời có dựa trên tài liệu không) —
**khác hẳn** citation syntax (có đúng marker `[N]` không). Xóa nhầm là mất mặt
chấm quan trọng nhất. Chỉ gỡ phần đọc `chunk_ref`/`[N]` nếu có, giữ toàn bộ
logic dice + cosine.

## C3. Xóa 3 field citation khỏi `config.py` 🟡

`inline_citation` · `chat_min_citation_score` · `chat_require_citations`

## C4. Quét 11 file còn lại

`grep -rn "citation" evaluation/ scripts/`. Với mỗi chỗ: xóa nếu là citation
syntax, giữ nếu là grounding. **Không** đánh số lại mã lỗi.

---

# PHASE D — Tách metric retrieval khỏi metric câu trả lời (A2 trên bảng)

Hiện hai loại lẫn nhau nên không biết điểm thấp là do tìm sai tài liệu hay do
viết dở.

- `metrics/retrieval.py` — chấm **trên qrels**: `recall_at_k`, `mrr_at_k`,
  `ndcg_at_k_graded`, `precision_at_k`, `hit_at_k`, `average_precision`,
  `irrelevant_rate`, `duplicate_rate`. Không được nhận `answer` làm input.
- `metrics/deterministic.py` + `grounding.py` — chấm **câu trả lời**. Không được
  nhận `qrels` làm input.

Ép bằng chữ ký hàm, không phải bằng quy ước. Nếu có hàm đang nhận cả hai → tách
đôi. Report cũng phải tách 2 bảng riêng.

---

# PHASE E — Metric cho intake (B1 trên bảng)

## ⚠️ 3 trong 6 hàm ĐÃ CÓ SẴN — tái dùng, đừng viết lại

| Cần | Đã có ở đâu |
|---|---|
| `intent_prf` | `metrics/classification.py:12` `per_class_prf` + `:27` `macro_f1` |
| `list_prf` (allergies, red_flags…) | `metrics/classification.py:55` `set_micro_prf` |
| ma trận nhầm lẫn intent | `metrics/classification.py:33` `confusion_matrix` |

Chỉ viết wrapper mỏng gọi vào chúng. Bảng công việc ghi "hiện chỉ có 4 hàm RAG"
là **sai** — `classification.py` có sẵn 7 hàm dùng được.

## Chỉ 4 hàm thật sự mới

| Hàm | Đo gì |
|---|---|
| `enum_validity` | tỉ lệ field enum model sinh ra nằm trong tập hợp lệ (skin_type, severity…) |
| `expected_calibration_error` | confidence model tự báo có khớp độ đúng thật không. Bin đều, 10 bin |
| `negation_leak` | "em **không** dị ứng BHA" → model có trích nhầm thành `allergies:[BHA]` |
| `canonicalization_hit` | teencode/viết tắt có được chuẩn hóa đúng dạng gốc không |

Đặt trong `metrics/intake.py` mới. Mỗi hàm 1 assert-based self-check trong
`if __name__ == "__main__"` — không tạo suite riêng.

---

# PHASE F — Arm harness

## F1. `scripts/eval_unified_intake.py` (B2)

- single-turn **bắt buộc**, no cache, no fallback
- báo cáo `fallback_rate` — nếu > 0 thì số đo không sạch, phải cảnh báo to
- overlap guard: chặn mẫu eval trùng train (`golden_extraction_gen.jsonl` đã nằm
  trong train — **không được dùng làm gold**)

## F2. Thêm arm `unified` cho 2 script cũ (B7)

`eval_extraction.py` + `eval_semantic_router.py` — giữ để A/B, dùng chung metric
Phase E. Không viết lại, chỉ thêm nhánh.

## F3. Nối `d5_multiturn` vào experiment (C3)

72 mẫu đã có, adapter đã đọc `conversation_history`, nhưng chưa experiment nào
trỏ tới. Chỉ là wiring, không sửa adapter.

## F4. `scripts/eval_bottleneck.py` — 4 arm

```
--arm z    intake thật    + RAG thật    + generator local
--arm x    intake ORACLE  + RAG thật    + generator local
--arm w    intake thật    + RAG ORACLE  + generator local
--arm y    intake thật    + RAG thật    + generator API (gpt-5.6-terra)
```

**Bốn điều bắt buộc:**

1. Cùng một bộ câu hỏi cho cả 4 arm. Chấm **paired từng câu**:
   `delta_i = score(arm, câu i) − score(z, câu i)`. Báo cáo trung vị + **phân
   phối** + đếm câu tăng/giảm/không đổi. Không so trung bình trần trụi.
2. `temperature=0`. Không được thì chạy 3 lần lấy trung vị.
3. Oracle intake phải **đúng format runtime** (`FOLLOWUP_HISTORY_JSON`). Đưa JSON
   gold thô vào là đo nhầm lệch format chứ không đo intake.
4. An toàn **tách riêng**: đếm số câu fail gate mỗi arm, không nhét vào trung
   bình. Arm điểm cao mà thêm 3 ca fail safety là arm tệ hơn.

---

# PHASE G — Test

`tests/test_env_keys.py` — 2 test, ~25 dòng, không framework mới:

```python
from pathlib import Path

ALLOWLIST = {  # đọc qua os.environ, không qua Settings
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL", "DATAGEN_API_KEY",
}


def test_khong_co_env_key_mo_coi():
    """extra='ignore' nuốt im lặng mọi key gõ sai. Đây là cái chốt."""
    from acne_llm.config import Settings
    fields = set(Settings.model_fields)
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=")[0].strip()
        assert key.lower() in fields or key in ALLOWLIST, \
            f"{key} trong .env không khớp field nào và không có trong ALLOWLIST"


def test_settings_thang_hang_so_module():
    """Chặn tái phát bug _DENSE_MAX_DISTANCE=0.48 không có hiệu lực."""
    from acne_llm.config import settings
    from acne_llm.rag import retriever
    assert retriever._DENSE_MAX_DISTANCE == settings.dense_max_distance
```

Thêm: unit test cho 4 hàm mới ở Phase E · fuzz "không crash" cho
`eval_unified_intake.py` với backend mock. **Không** viết test cho code sắp xóa
ở Phase C.

---

# PHASE H — Dashboard (Next.js, ~10.5k dòng)

Dashboard **là một phần của module evaluation**, không phải phụ kiện. Nó tự
dựng câu lệnh CLI và tự hardcode tham số → sửa Python mà bỏ dashboard là hệ
thống nói hai giọng.

## ⚠️ H1. Bug #1 có bản sao thứ hai nằm ở đây — quan trọng nhất Phase H

`dashboard/lib/commands.ts:16-19`:

```ts
const JUDGE_PROVIDER = "openai";
const JUDGE_MODEL = "gpt-5-mini-2025-08-07";   // ← hardcode lần 2
const JUDGE_WORKERS = 4;
```

Dòng 375-394 **truyền thẳng các hằng số này thành cờ CLI** cho
`evaluation.judges.run_judge`. Nghĩa là: **sửa xong Phase B mà không sửa chỗ
này thì mọi lần chạy phóng từ dashboard vẫn ép về `gpt-5-mini`.** Phase B chỉ
sửa được đường chạy tay.

Sửa: bỏ 2 hằng số, đọc từ backend. Thêm route `app/api/meta/route.ts` (đã tồn
tại) trả về `judge_provider` + `judge_model` lấy từ `settings`, dashboard gọi
route đó. Nếu cách này phình to, giải pháp lười hơn được chấp nhận: **không
truyền cờ `--judge-provider/--judge-model` nữa**, để Python tự đọc settings —
xóa code còn tốt hơn sửa code.

`JUDGE_WORKERS = 4` giữ nguyên, nó là tham số vận hành của dashboard.

## H2. `lib/types.ts` + `lib/command-ids.ts` — đăng ký lệnh mới

`CommandId` là union đóng 18 giá trị; `COMMAND_IDS` là mảng phải khớp. Thêm:

```
"intake_unified"    → scripts/eval_unified_intake.py   (Phase F1)
"bottleneck"        → scripts/eval_bottleneck.py       (Phase F4)
```

Sửa **cả hai** file, nếu không TypeScript sẽ đỏ.

## H3. `lib/commands.ts` — dựng argv cho 2 lệnh mới

Theo đúng khuôn `case "judge":` hiện có. Lệnh `bottleneck` phải nhận cờ `--arm`
với 4 giá trị `z|x|y|w`. **Xóa** mọi cờ liên quan citation.

## H4. `lib/gates.ts` — thêm gate cứng refusal_fidelity

`gates.ts` đọc `reports/gate_check.json` theo schema:

```
checks[] = { name: "section.metric", threshold: number, actual: number, pass: boolean }
```

`analysis/check_gate.py` phải xuất `refusal_fidelity` đúng schema này với
ngưỡng **fail 1 mẫu là chặn merge**. Không sửa `gates.ts` — nó đã tổng quát,
chỉ cần producer ghi đúng.

## H5. `lib/judge-calibration.ts` — KHÔNG sửa TS, sửa producer

File này **đã đọc sẵn** `record.judge_provider` và `record.judge_model` từ
artifact. Nghĩa là dashboard đang hiển thị model nào artifact ghi — và artifact
đang ghi hằng số hardcode, tức **dashboard đang hiển thị một con số sai mà
trông rất thuyết phục**.

Nối với Phase B3: producer phải ghi model **thật sự đã gọi**, không phải hằng
số. Sau đó dashboard tự đúng, không cần đụng TypeScript.

Đây cũng là chỗ hiển thị kết quả task "đo trọng tài" (độ khớp với người chấm) —
`failedChecks` và `calibrated` đã có sẵn khuôn.

## H6. Gỡ citation khỏi UI

`grep -rn -i citation` trong `app/ components/ lib/` (bỏ `node_modules`,
`.next`). Xóa cột/thẻ/biểu đồ citation ở `ResultsClient.tsx`, `FiguresClient.tsx`,
`lib/results.ts`, `lib/figures.ts`. **Giữ nguyên** mọi thứ tên `grounding` —
xem lý do ở Phase C2.

## H7. Thêm view 4 arm

`app/results/page.tsx` + `components/ResultsClient.tsx`: bảng so Z/X/Y/W.
Bắt buộc hiển thị **paired delta từng câu**, không chỉ điểm trung bình:

- trung vị `delta` mỗi arm so với Z
- đếm câu tăng / giảm / không đổi
- cột **an toàn tách riêng** — số ca fail gate mỗi arm, không gộp vào điểm

Lười tối đa: tái dùng component bảng đã có, thêm cột. Không dựng trang mới,
không thêm thư viện biểu đồ.

## H8. `dashboard/scripts/run_preliminary_d2.py`

249 dòng, đang import `DEFAULT_OPENAI_JUDGE_MODEL` ở dòng 23, 97, 202. Sửa
theo Phase B2.

## H9. Cập nhật test TS đã có

`tests/commands.test.ts` (196 dòng) · `gates.test.ts` · `judge-calibration.test.ts`
· `paths.test.ts`. Thêm ca cho 2 CommandId mới. Chạy được bằng
`npm test` trong `dashboard/`.

---

## Bản đồ phủ — mọi thư mục con của `evaluation/`

| Thư mục | Phase đụng tới | Ghi chú |
|---|---|---|
| `metrics/` | C, D, E | trọng tâm |
| `judges/` | B | bỏ hardcode |
| `adapters/` | A2, F | sửa `retrieve_top_k` |
| `unit/` | A2, F2 | sửa `retrieve_top_k`, thêm arm unified |
| `analysis/check_gate.py` | H4 | xuất gate refusal_fidelity |
| `analysis/tune_grounding.py`, `recompute_grounding.py` | C2 | **giữ**, chỉ gỡ phần citation nếu có |
| `analysis/figures_*.py` | — | **ngoài phạm vi** (2.6k dòng vẽ hình) |
| `validate/` | C4 | quét citation; không refactor logic |
| `runners/` | F3, F4 | wiring d5_multiturn + arm |
| `datasets/registry.py` | F1 | overlap guard chống leak |
| `datasets/generate_drafts.py` | — | **ngoài phạm vi** (2.2k dòng) |
| `annotations/`, `probe/`, `configs/` | — | không đụng |
| `dashboard/` | H | toàn bộ Phase H |
| `tests/` | G, H9 | cập nhật theo thay đổi |

Thư mục nào **không** có trong bảng này mà bị sửa → phải giải thích trong
báo cáo cuối.

## Định nghĩa "xong"

```
[ ] .env đúng 16 key; .env.baseline đồng bộ, không chứa secret
[ ] config.py còn 70 field  (85 − 8🔴 − 5🔵 − 3🟡 − 1 gộp + 2🆕)
[ ] grep toàn repo: 0 tham chiếu tới 16 field đã xóa
[ ] python -c "from acne_llm.config import settings; print(settings.judge_model)"
    → gpt-5.4-mini
[ ] file kết quả judge ghi đúng model thật đã dùng
[ ] grep "citation" evaluation/ → chỉ còn chỗ thuộc grounding
[ ] metrics/retrieval.py không nhận answer; deterministic.py không nhận qrels
[ ] eval_bottleneck.py chạy được cả 4 arm trên 5 câu mẫu
[ ] pytest xanh
[ ] Phase A: chạy 1 câu trước/sau → output giống hệt

DASHBOARD
[ ] grep -rn "gpt-5-mini" dashboard/ (bỏ node_modules, .next) → 0 kết quả
[ ] grep -rn -i "citation" dashboard/app dashboard/components dashboard/lib → 0
[ ] npm run build trong dashboard/ không lỗi TypeScript
[ ] npm test xanh
[ ] Mở dashboard: chạy được lệnh bottleneck với --arm z, thẻ judge hiển thị
    đúng gpt-5.4-mini (không phải gpt-5-mini)
```

Cuối cùng cập nhật `docs/config_reference.md` + `docs/config_layout.md` cho khớp
trạng thái thật, rồi báo cáo:

- file đã sửa + số dòng, theo Phase
- field/key nào **không xóa được** và vì sao
- bất kỳ chỗ nào phát hiện thêm một giá trị nằm ở 2 nơi

## Ngoài phạm vi

`analysis/figures_*.py` (2.6k dòng vẽ hình) · `datasets/generate_drafts.py`
(2.2k dòng) · `annotations/` · `probe/` · `dashboard/node_modules` và
`dashboard/.next` (build artifact, đã gitignore) · mọi task nhóm A3–A5, B4–B6,
C4–C6, D1–D4 trên bảng công việc — chúng chỉ mở sau khi `eval_bottleneck.py`
chỉ ra nhánh nào là nút thắt.
