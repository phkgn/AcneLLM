# PLAN — module `datagen/intakedata/` (Unified Intake datagen)

> Plan implement-ready cho một module sinh data **độc lập**, tách hẳn khỏi các script
> gen khác trong repo. Sinh dataset finetune cho model **Unified Intake** (Qwen 2.5 3B Q4):
> đọc 1 turn tiếng Việt → 1 JSON `{intent, confidence, description, context, clinical}`.
>
> **Đọc trước, bắt buộc:** `datagen/UNIFIED_INTAKE_DATAGEN_SPEC.md` (spec nội dung/hành vi/quota).
> **Clone kiến trúc từ:** `datagen/roledata/` (pipeline đã trưởng thành: config → generator →
> gates → writer → pipeline one-command, resume, inline gates, parity 3 tầng). Copy *kiến trúc*,
> KHÔNG copy nội dung role.

---

## 0. Nguyên tắc

- **Tách biệt tuyệt đối.** Toàn bộ code mới nằm trong `datagen/intakedata/`. KHÔNG sửa, KHÔNG
  import `datagen/main.py`, `datagen/generator.py`, `datagen/gates.py`, `datagen/roledata/`.
  Chỉ *đọc tham chiếu* roledata để mô phỏng kiến trúc.
- **Clone kiến trúc roledata** vì nó đã hiệu quả (one-command, resume, inline gate, CLI log
  realtime, parity). Giữ nguyên khung: `config/schema/generator/gates/writer/pipeline`.
- **Parity train == serve.** System prompt intake cố định (canonical) phải byte-identical trong
  mọi record — giống cách roledata neo SYSTEM anchor.
- **Constrained output.** Mọi record assistant phải khớp JSON schema intake (§3). Enum lấy nguyên
  từ `src/acne_llm/schemas/core.py` + `src/acne_llm/chat/llm_extractor.py`.

---

## 1. Cấu trúc file (clone roledata)

```
datagen/intakedata/
  __init__.py
  config.py          # Config dataclass + .env loader + CASE_TYPE_TARGETS(Σ=4000) + compute_budget
  anchor.py          # load + parity check system prompt canonical
  schema.py          # enum sets + JSON schema constrained + validate_intake_record()
  generator.py       # CaseSpec, OpenAIGenerator(async), build_gen_prompt, synthesize_seed, to_record
  gates.py           # evaluate_record + CorpusGateState (validators §7)
  writer.py          # DatasetWriter append-only jsonl, dedup theo id, resume
  seed.py            # relabel golden_extraction_gen.jsonl (flat) -> record nested+intent
  pipeline.py        # one-command orchestrator (preflight->probe->generate->gate->top-up->split->summary)
  taxonomy.yaml      # 15 case_type + quota + style hint (từ SPEC §6)
  system_prompt.canonical.txt   # intake system prompt cố định (anchor)
  conftest.py
  tests/
    test_budget.py       # Σ quota == 4000
    test_anchor.py       # parity + fail khi lệch
    test_schema.py       # enum-valid, reject JSON hỏng, clinical null-or-valid
    test_gates.py        # negation-leak, empty->null/[], balance
    test_seed.py         # relabel flat->nested đúng contract
    test_pipeline_contracts.py  # smoke wiring, resume, dedup
  output/
    intake/                     # (gitignore) train/val + audit
```

---

## 2. Config (`config.py`)

- Tiny `.env` loader (không thêm dependency), đọc `OPENAI_API_KEY`, `OPENAI_BASE_URL`
  (default `https://api.openai.com/v1`), `OPENAI_MODEL` (default `gpt-4o-mini`).
- `FULL_TARGET = 4000`.
- `CASE_TYPE_TARGETS` (Σ = 4000) — copy từ SPEC §6:
  ```
  advise_selfreport_simple      500
  advise_selfreport_rich        450
  advise_negation_stopped       350
  advise_duration_convert       200
  advise_noaccent               250
  advise_mixed_vi_en            100
  advise_ambiguous_lowconf      150
  knowledge_product_trap        300
  knowledge_general             300
  knowledge_ingredient_compare  200
  clarify_vague                 300
  clarify_followup_multiturn    200
  reject_jailbreak_meta         150
  reject_ood                    200
  reject_unsafe_rx              150
  glue_greeting_thanks          200
  ```
  Import invariant: `sum == FULL_TARGET` else raise.
- `compute_budget(total)` largest-remainder (copy roledata) để scale khi `--limit`.
- `validate()` báo lỗi rõ nếu thiếu `OPENAI_API_KEY`.

---

## 3. Schema constrained (`schema.py`)

Enum copy nguyên (không tự chế/dịch):
```
LESION = {comedone, whitehead, blackhead, closed_comedone, papule, pustule,
          nodule, cyst, scar, post_inflammatory_hyperpigmentation, other}
SKIN   = {dry, oily, combination, sensitive, normal, unknown}
SEX    = {male, female, other}
INFLAMMATION = {none, mild, moderate, severe, unknown}
DISTRIBUTION = {forehead, cheeks, chin, jawline, nose, around_mouth,
                back, chest, shoulders, neck, t_zone, other}
INTENT = {advise, knowledge, clarify, reject}
```
`build_json_schema()` → JSON schema cho constrained decoding (dùng cả khi gen ép provider trả
đúng, và export cho serve). Node scalar = `{value, confidence}`; list phần tử = `{value, confidence}`.

`validate_intake_record(obj)` kiểm:
- root có `intent∈INTENT`, `confidence∈[0,1]`, `description` 1–4000.
- `context` object; mỗi field đúng kiểu; enum ∈ tập; `duration_weeks≥0`.
- `clinical` = `null` HOẶC object với `lesion_types`/`lesion_distribution` enum-valid,
  `inflammation_level∈INFLAMMATION`.
- Trả `(ok: bool, reasons: list[str])`.

---

## 4. Anchor (`anchor.py`)

- `system_prompt.canonical.txt` = intake system prompt cố định (liệt kê enum + quy tắc, dựa
  `datagen/intake_json_system_prompt.md`, rút gọn cho serve).
- `assert_parity(cfg)`: mọi record `messages[0].content` phải byte-identical file này.
- `anchor_sha256()` để log + gate.

---

## 5. Generator (`generator.py`)

- `CaseSpec`: `case_type`, `quota`, `style_hint`, `intent_hint`, `behavior` (từ taxonomy.yaml).
- `synthesize_seed(case_type, rng)`: sinh thuộc tính gieo (tuổi, giới, lesion, sản phẩm, cue
  phủ định…) để đa dạng hoá — theo hành vi từng case (SPEC §6).
- `build_gen_prompt(spec, seed)`: prompt yêu cầu provider sinh **(user_turn, assistant_json)**
  đúng hành vi case + invariants (SPEC §4) + confidence policy (SPEC §5). Ép provider trả JSON
  khớp schema (§3).
- `OpenAIGenerator` (async, retry/backoff) — copy khung roledata.
- `to_record(...)`: gói vào `messages` SFT với `system` = anchor canonical, `user` = turn
  (+ history nếu follow-up), `assistant` = JSON minified; kèm `meta{case_type, source, judged}`.

---

## 6. Seed relabel (`seed.py`)

- Đọc `data/golden_extraction_gen.jsonl` (985, flat schema, đã có `intent`).
- Map flat → nested node contract (§3): `lesions→clinical.lesion_types`,
  `inflammation→clinical.inflammation_level`, `distribution→clinical.lesion_distribution`,
  context fields tương ứng; bọc `{value, confidence}` (confidence gán theo policy: rõ→0.9+,
  suy luận→0.6–0.85).
- Loại record không map được / enum lạ. Gắn `meta.source="golden_relabel"`.
- Mục tiêu: tái dùng phần lớn 985 cho `advise_*`/`knowledge_*`, giảm chi phí gen mới.

---

## 7. Gates (`gates.py`)

`evaluate_record(record, state)` → accept/reject + reason. Validators:
- `schema_valid` (gọi `validate_intake_record`).
- `system_parity` (byte-identical anchor).
- `enum_valid` (0 hallucination — đã trong schema, double-check).
- `negation_leak`: với case negation, kiểm cue phủ định (`không dùng`, `ngưng`, `bỏ`…) —
  entity sau cue KHÔNG được xuất hiện trong `current_products`/`medications`. Leak → reject.
- `empty_discipline`: knowledge/reject/glue phải `context={}`/rỗng + `clinical=null` (không bịa).
- `confidence_range`: mọi conf ∈ [0,1]; ambiguous case phải có ≥1 field conf < 0.6.
- `dedupe` theo hash(user_turn).
- `CorpusGateState`: đếm theo case_type + intent để enforce balance ở post-validate.

---

## 8. Writer (`writer.py`)

Copy roledata: append-only JSONL, dedup theo `id` (hash), resume (đọc lại output đã có), audit
line mỗi record (accept/reject + reason). Không log secret.

---

## 9. Pipeline (`pipeline.py`) — one-command

Thứ tự: `preflight (validate + assert_parity + anchor sha) → probe (1 call provider kiểm key)
→ seed relabel (nếu bật) → generate (async, theo budget/case) → inline gate → top-up (bù case
thiếu) → post-validate (schema/dup/balance/negation) → split 90/10 train/val → summary`.

- Argparse: `--smoke` (1/case), `--limit N`, `--yes`, `-v`, `--no-seed`, `--full`.
- **CLI log realtime**: StreamHandler stdout song song file `output/logs/intake.log`; in progress
  mỗi `progress_every`: case, accept/target, reject, elapsed.
- Split test KHÔNG sinh ở đây — eval gold gán tay riêng (SPEC §7), pipeline chỉ cảnh báo nếu
  phát hiện trùng với eval.

---

## 10. Output

```
output/intake/intake.train.jsonl   # ~3600
output/intake/intake.val.jsonl     # ~400
output/intake/audit.jsonl
output/intake/summary.json         # counts theo case_type + intent + reject reasons
output/logs/intake.log
```

---

## 11. Phases (dừng TRƯỚC full run — user tự chạy gen cuối)

- **Phase 0 Scaffold**: `__init__`, `config`, `anchor`, `schema`, `taxonomy.yaml`,
  `system_prompt.canonical.txt`. Tests: `test_budget`, `test_anchor`, `test_schema`.
- **Phase 1 Core**: `writer`, `generator`, `gates`, `seed`. Tests: `test_gates`, `test_seed`.
- **Phase 2 Orchestrator**: `pipeline` + argparse + CLI log + split. Test:
  `test_pipeline_contracts` (smoke/resume/dedup).
- **Phase 3 Chứng minh wiring (KHÔNG full)**: chạy `--smoke` và `--limit 8`, xác nhận log
  realtime + record khớp schema + parity. Dừng ở đây, bàn giao cho user chạy `--full`.

---

## 12. Lệnh (chỉ tới bước test/smoke)

```
pytest -q datagen/intakedata
python -m datagen.intakedata.pipeline --smoke --yes -v
python -m datagen.intakedata.pipeline --limit 8 --yes -v
# Bước cuối (USER tự chạy, KHÔNG chạy trong build):
# python -m datagen.intakedata.pipeline --full --yes -v
```

## 13. Definition of Done (build)

- `pytest -q datagen/intakedata` xanh toàn bộ.
- `--smoke` sinh 1 record/case, log realtime trên CLI, mọi record schema-valid + parity.
- `--limit 8` chạy đủ vòng gate/top-up/split không lỗi.
- Không đụng file ngoài `datagen/intakedata/`.
- README ngắn trong module: cách chạy `--full` để user gen data cuối.
