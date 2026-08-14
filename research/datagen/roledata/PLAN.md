# PLAN CUỐI — `datagen/roledata/` (module sinh data finetune, implement-ready)

> Module build mới, **kế thừa pattern** đã chứng minh của pipeline `v4_role` nhưng **code sạch, không import lại code cũ, không đụng `output/v4_role`**.
> Anchor = canonical v3 (`model/Modelfile` ≡ `model/system_prompt.canonical.txt`).
> Output đích: dataset 3.500 mẫu, chia train/val/holdout, export sẵn sàng train LoRA.

---

## 1. Mục tiêu & phạm vi

Sinh ra **một dataset finetune "ép role" cho AcneLLM** đạt 4 tiêu chí:
1. **Parity tuyệt đối** — `system` mỗi record ≡ anchor v3, không lệch một ký tự.
2. **Coverage đủ** — mỗi luật trong SYSTEM v3 có ≥1 case gánh, mỗi case ≥70 mẫu.
3. **Chống forgetting** — có lớp K1 giữ kiến thức nền (LoRA không ghi đè).
4. **Sẵn sàng train** — có split train/val/holdout + export đúng format trainer + dataset_card + checksum.

Ngoài phạm vi (làm ở bước sau, không thuộc module này): train LoRA, eval model sau train (nằm ở `evaluation/`).

---

## 2. Quyết định đã chốt (default — override được)

| # | Quyết định | Giá trị chốt | Ghi chú |
|---|---|---|---|
| D1 | Nguồn "gold" cho K1 knowledge-anchor | Sinh grounded trên tài liệu mụn trong repo (`LLMData/chunk_qa`, AAD/NICE/textbook), chấm đúng bằng LLM-judge factual | Không lấy base model làm gold (base cũng có thể sai); dùng tài liệu làm chuẩn |
| D2 | Format trainer đích | **LLaMA-Factory** (sharegpt/chatml messages) | Đổi sang Axolotl/Unsloth chỉ cần sửa `export.py`, schema gần giống |
| D3 | Provider gen-LLM | **OpenAI** — `OPENAI_API_KEY` trong `.env`; `OPENAI_BASE_URL` (default `https://api.openai.com/v1`), `OPENAI_MODEL` (default `gpt-4o-mini`) | Không hardcode model; đọc env |
| D4 | Tổng & quota | 3.500, theo bảng §6 | R=2.150 · B=850 · K=500 |
| D5 | Nguồn anchor | `config.anchor_path = model/Modelfile`, verify ≡ `system_prompt.canonical.txt` | Một nguồn duy nhất |

---

## 3. Nguyên tắc kế thừa

| Pattern từ `v4_role` (giữ) | Không kế thừa |
|---|---|
| `config.py` là nơi duy nhất đọc `.env` | import `datagen.main/generator/gates` cũ |
| Budget theo taxonomy (largest-remainder) | thư mục `output/v4_role` |
| Writer append-only, dedup theo `id`, resume | record schema thừa field |
| Inline gates trong generation loop | |
| **Parity injection** (`system` = anchor) | |
| One-command orchestrator + preflight + budget guard | |
| CLI `--smoke / --limit / --no-resume / --max-cost-usd` | |

---

## 4. Cấu trúc thư mục

```
datagen/roledata/
├─ __init__.py
├─ config.py              # single-source config; anchor_path, quota, paths, api
├─ anchor.py              # load SYSTEM + assert ≡ system_prompt.canonical.txt
├─ taxonomy.yaml          # 16 case: quota, context, gate, augmentation
├─ style_guide.md         # giọng/khuôn cho generator LLM
├─ prompts/               # 1 template Jinja mỗi case (prompt điều khiển gen-LLM)
│   ├─ R1_identity.j2 … R10_special_population.j2
│   ├─ B1_grounded_role.j2 … B5_depth_anchor.j2
│   └─ K1_knowledge_anchor.j2
├─ generator.py           # async client; build prompt; nhét canonical system vào record
├─ gates.py               # validators inline
├─ writer.py              # JSONL append-only, dedup id, resume
├─ pipeline.py            # orchestrator (entrypoint: python -m datagen.roledata.pipeline)
├─ finalize/
│   ├─ __init__.py
│   ├─ split.py           # train/val/holdout, seed cố định
│   └─ export.py          # → format trainer + dataset_card.md + checksum + parity verify
├─ output/
│   ├─ roledata.train.jsonl
│   ├─ rejected.audit.jsonl
│   ├─ generation_summary.json
│   ├─ limit_checkpoint.json
│   ├─ splits/{train,val,holdout}.jsonl
│   ├─ export/acnellm_role_lora.jsonl
│   ├─ dataset_card.md
│   └─ logs/roledata.log
└─ tests/
    ├─ test_budget.py       # quota sum = 3500
    ├─ test_anchor.py       # parity byte-identical
    ├─ test_gates.py        # từng gate pass/fail đúng
    ├─ test_split.py        # holdout không rò vào train
    └─ test_export.py       # schema export + parity + checksum
```

---

## 5. Đặc tả từng file

### `config.py`
- Dataclass `Config`, chỉ module này đọc `os.environ` (mirror `.env` loader nhẹ).
- Keys: `anchor_path=model/Modelfile`, `canonical_path=model/system_prompt.canonical.txt`, `taxonomy_path`, `style_guide_path`, `output_dir`, `knowledge_source_dir=LLMData/chunk_qa`, `api_key/base_url/model` (từ `.env`), `thinking="disabled"`, `concurrency=3`, `batch_size=6`, `max_cost_usd=25`, `phrase_ngram_size=8`, `phrase_max_occurrences=5`, `seed=42`.
- `FULL_TARGET=3500`, `CASE_TYPE_TARGETS` (bảng §6), `compute_budget(total)` largest-remainder.
- `validate() -> list[str]`: thiếu API key, thiếu file anchor/taxonomy/style/knowledge, `thinking≠disabled`, `max_cost_usd<=0`.

### `anchor.py`
- `load_anchor(cfg) -> str`: regex `SYSTEM\s+"""(.*?)"""` từ `anchor_path`.
- `assert_parity(cfg)`: so `load_anchor` với `canonical_path` (đã strip) **byte-identical**; lệch → raise. Gọi ở preflight.

### `taxonomy.yaml`
- `version: roledata-v1`, `role_definition`, `augmentation{ratio:0.30, styles, answer_must_use_standard_vietnamese:true}`.
- 16 `groups` với `sample_kind, count, context(bool), behavior, gate, (user_turns / anchor_pair_size khi cần)`.

### `generator.py`
- `build_gen_prompt(case, cfg, anchor, style_guide) -> messages`: prompt điều khiển gen-LLM (yêu cầu sinh cặp user/assistant theo behavior của case).
- `synthesize_context(case, cfg)`: với case `context:true`, lấy chunk từ `knowledge_source_dir` (+ chèn nguồn nhiễu cho B3, mâu thuẫn cho B4, thiếu đáp án cho B2).
- `to_record(case, user, assistant, anchor, meta) -> dict`: **`messages[0]={"role":"system","content":anchor}`** (parity), + `id`, `sample_kind`, `input_style`, `synthetic_context`, `gate_results`.
- Async gọi API (retry/backoff, tôn trọng `concurrency`, `max_output_tokens`).

### `gates.py` — xem §9. Trả `GateResult{passed:bool, reasons:list}`.

### `writer.py`
- `DatasetWriter` (context manager, thread-safe): append-only, dedup theo `id`, `load_existing_ids()` để resume.

### `pipeline.py` (orchestrator, một lệnh)
Thứ tự: preflight (config.validate + anchor.assert_parity) → probe model + assert `thinking=disabled` → embedding sanity → contamination index (n-gram vs `evaluation/datasets`) → throughput/cost estimate + budget guard → resume/re-audit → async generate + inline gates → top-up phần thiếu theo relative deficit → post-validate (schema/dup/phrase/parity) → `generation_summary.json`.
CLI: `--smoke`, `--limit N`, `--only-case X`, `--concurrency N`, `--no-resume`, `--skip-gates` (debug), `--max-cost-usd N`, `--yes`, `-v`.

### `finalize/split.py`
- `split(cfg, seed=42)`: stratified theo `sample_kind`. Tỉ lệ mặc định **train 85% / val 8% / holdout 7%**.
- **Holdout bắt buộc gồm toàn bộ phần test của R8, B2, B4** (tách trước, không rò vào train). Dedup id chéo 3 tập.

### `finalize/export.py`
- `export(cfg)`: đọc `splits/train.jsonl` → format LLaMA-Factory (giữ `messages[system,user,assistant]`, thêm `id` để trace; bỏ metadata gate).
- Verify lại `system ≡ anchor` cho mọi dòng; sinh `dataset_card.md` (phân bổ case, coverage matrix, anchor SHA-256, tổng token) + `checksum.sha256`.

---

## 6. Taxonomy chi tiết (3.500)

**Role (R1–R10) = 2.150 · context=false**

| Case | SL | Behavior | Gate chính |
|---|--:|---|---|
| R1 identity | 200 | Danh tính, năng lực, giới hạn; không nhận là bác sĩ | `identity_rule` |
| R2 depth_adaptation | 340 | Đổi register/độ sâu theo teen/phụ huynh/SV y | `depth_marker` |
| R3 nonjudgment | 270 | Không phán xét (nặn mụn, kem trộn, bỏ skincare) | `nonjudgment_rule` |
| R4 measured_empathy | 220 | Công nhận cảm xúc vừa đủ, không therapist | `empathy_rule` |
| R5 natural_clarification | 220 | Hỏi lại 1–2 ý khi mơ hồ | `clarify_present` |
| R6 role_boundary | 250 | Từ chối kê đơn/chẩn đoán/kết luận từ ảnh | `refusal_present` |
| R7 conversation_glue | 150 | Chào/cảm ơn/lan man → kéo về chủ đề | `onscope_redirect` |
| R8 meta_jailbreak | 150 | Giữ vai trước DAN/meta/đòi làm bác sĩ | `refusal_present` + `no_prompt_leak` |
| R9 multiturn | 200 | 4–6 lượt, nhất quán giọng/xưng hô | `turn_count` + `consistency` |
| R10 special_population | 150 | Thai kỳ/cho bú, <12, sơ sinh | `referral_present` + `no_rx` |

**Grounded (B1–B5) = 850 · context=true**

| Case | SL | Behavior | Gate chính |
|---|--:|---|---|
| B1 grounded_role | 380 | Bám tài liệu + lồng role | `grounded_rate>=0.8` |
| B2 missing_answer | 200 | Abstain khi thiếu đáp án | `abstain_rule` |
| B3 irrelevant_chunk | 130 | Bỏ nguồn nhiễu, dùng nguồn đúng | `grounded_rate>=0.8` |
| B4 conflicting_docs | 70 | Nêu 2 nguồn mâu thuẫn, khuyên hỏi bác sĩ | `conflict_rule` |
| B5 depth_anchor | 70 | Cùng tài liệu, đổi độ sâu (cặp 2) | `grounded_rate>=0.8` + `anchor_pair` |

**Preservation (K1) = 500 · context=true (grounded trên tài liệu mụn)**

| Case | SL | Behavior | Gate chính |
|---|--:|---|---|
| K1 knowledge_anchor | 500 | Trả lời kiến thức mụn đúng (BHA/AHA, retinoid, cơ chế…) theo persona | `knowledge_accuracy` (LLM-judge factual) + `grounded_rate>=0.8` |

Augmentation 30% (teencode/no_accent/typo/mixed) **chỉ ở phía user**, assistant luôn tiếng Việt chuẩn.

---

## 7. Record schema

**Raw (`roledata.train.jsonl`)**
```json
{
  "id": "roledata-R6-000123",
  "sample_kind": "R6_role_boundary",
  "input_style": "standard|teencode|no_accent|typo|mixed",
  "context": false,
  "synthetic_context": null,
  "synthetic_context_sources": [],
  "anchor_group": null,
  "messages": [
    {"role": "system",    "content": "<ANCHOR v3 — byte-identical>"},
    {"role": "user",      "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "gate_results": {"passed": true, "checks": {"refusal_present": true, "...": true}},
  "gen_model": "z-ai/glm-5.2-free"
}
```

**Export (`export/acnellm_role_lora.jsonl`)** — chỉ giữ phần train cần: `{"id", "messages":[system,user,assistant]}`. Bỏ metadata gate.

---

## 8. Parity — 3 tầng chặn

1. **Preflight:** `anchor.assert_parity()` — SYSTEM(Modelfile) ≡ canonical.txt, lệch → dừng ngay.
2. **Per-record gate:** `system_parity` — record nào `messages[0].content` ≠ anchor → reject vào `rejected.audit.jsonl`.
3. **Export:** `export.py` verify lại toàn bộ + ghi anchor SHA-256 vào `dataset_card.md`.

---

## 9. Gates (inline validators)

**Chung mọi record:** `schema_valid`, `vietnamese_only` (assistant ≥98% VN), `phrase_frequency` (8-gram ≤5 lần toàn corpus), `knowledge_leak` (không lộ system), `system_parity`.

**Theo case:**

| Gate | Áp dụng | Luật |
|---|---|---|
| `refusal_present` | R6, R8 | Có nhịp từ chối lịch sự |
| `no_prompt_leak` | R8 | Không in/nhắc lại nội dung system |
| `clarify_present` | R5 | Có 1–2 câu hỏi lại trọng tâm |
| `referral_present` + `no_rx` | R10 | Khuyên khám đúng ca; tuyệt đối không liều/tên thuốc kê toa |
| `grounded_rate>=0.8` | B1, B3, B5, K1 | ≥80% câu khẳng định bám nguồn |
| `abstain_rule` | B2 | Thừa nhận thiếu dữ kiện, không bịa |
| `conflict_rule` | B4 | Nêu cả hai nguồn + khuyên bác sĩ |
| `knowledge_accuracy` | K1 | LLM-judge chấm đúng sự thật so tài liệu (≥4/5) |
| `turn_count` + `consistency` | R9 | 4–6 lượt, xưng hô/giọng nhất quán |
| `anchor_pair` | B5 | Đủ cặp 2 mẫu cùng tài liệu khác độ sâu |

Candidate fail → retry tối đa `max_content_attempts=4`, vẫn fail → ghi `rejected.audit.jsonl`.

---

## 10. Split & holdout

- Stratified theo `sample_kind`, seed=42. **train 85% / val 8% / holdout 7%**.
- Holdout **bắt buộc** chứa phần test của **R8 (jailbreak), B2 (abstain), B4 (conflict)** — 3 hành vi an toàn cần đo tổng quát hoá; các case này KHÔNG được để lọt hết vào train.
- Kiểm chéo id: không mẫu nào ở >1 tập (chống leakage). `test_split.py` khẳng định điều này.

---

## 11. Export (LLaMA-Factory)

- `dataset_info` entry: `formatting: sharegpt`, cột `messages`, mapping role `system/user/assistant`.
- File: `export/acnellm_role_lora.jsonl` + `dataset_card.md` + `checksum.sha256`.
- `dataset_card.md` gồm: tổng mẫu, phân bổ 16 case, coverage matrix (luật↔case), anchor SHA-256, tổng token in/out, seed, ngày sinh.

---

## 12. Vận hành

```powershell
# nghiệm thu nhanh
python -m datagen.roledata.pipeline --smoke --yes
python -m datagen.roledata.pipeline --limit 50

# full
python -m datagen.roledata.pipeline --max-cost-usd 25
python -m datagen.roledata.finalize.split
python -m datagen.roledata.finalize.export
python -m pytest -q datagen/roledata
```

---

## 13. Lộ trình & acceptance criteria

| Phase | Việc | Xong khi (acceptance) |
|---|---|---|
| **0. Scaffold** | `__init__`, `config.py`, `anchor.py`, `taxonomy.yaml`, `style_guide.md` | `test_budget` (Σ=3500) & `test_anchor` (parity) xanh |
| **1. Core gen** | `writer.py`, `generator.py`, `gates.py`, `pipeline.py` | `--smoke` sinh 16/16 case, đọc tay ổn; inline gate chạy |
| **2. Case mới** | template + gate R10, K1 (+ nguồn tài liệu cho K1) | `--only-case R10` và `--only-case K1` pass gate; K1 judge ≥4/5 |
| **3. Finalize** | `split.py`, `export.py` + tests | `test_split` (0 leakage) & `test_export` (parity+schema) xanh |
| **4. Full + bàn giao** | full 3.500 có giám sát → split → export | post-validate 0 lỗi schema/dup/phrase; coverage khớp §6; `export/` + `dataset_card.md` sẵn sàng |

---

## 14. Chi phí & throughput (ước tính từ `v4_role`)

- ~7 giây/record accept (đo thực lượt limit-30) → full 3.500 ≈ **6–7 giờ** một lần chạy liền mạch; có checkpoint nên kill/resume an toàn.
- Budget guard mặc định 25 USD; model hiện free-tier (rate 0) — nếu đổi provider có phí, set `DATAGEN_INPUT/OUTPUT_PRICE_PER_MILLION` trong `.env`.

---

## 15. Rủi ro & mitigation

| Rủi ro | Mitigation |
|---|---|
| Lệch anchor (như bản cũ) | Parity 3 tầng (§8) + `test_anchor` |
| Forgetting sau train Q4 | Lớp K1 500 mẫu + eval retention (base vs finetuned) làm cổng release ở `evaluation/` |
| Holdout rò vào train | Tách holdout trước export + `test_split` dedup id chéo |
| Lặp mẫu/học vẹt | `phrase_frequency` 8-gram ≤5; augmentation đa dạng phía user |
| K1 sai kiến thức | Gate `knowledge_accuracy` LLM-judge ≥4/5, grounded trên tài liệu repo |
| Provider 503/dao động | retry/backoff + resume theo id |

---

## 16. Definition of Done

- [ ] `datagen/roledata/` chạy `python -m datagen.roledata.pipeline` full → 3.500 record, post-validate 0 lỗi.
- [ ] Mọi record `system` ≡ anchor v3 (parity 3 tầng xanh).
- [ ] Coverage matrix không ô trống; mỗi case ≥ quota §6 (±3%).
- [ ] `splits/` 85/8/7, holdout chứa R8+B2+B4, 0 leakage.
- [ ] `export/acnellm_role_lora.jsonl` + `dataset_card.md` + `checksum.sha256`.
- [ ] `pytest -q datagen/roledata` toàn xanh.

---

*Plan cuối — implement-ready. Bắt đầu Phase 0 khi bạn duyệt.*
