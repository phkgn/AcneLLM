# Nhiệm vụ Codex: Build module `datagen/intakedata/` theo PLAN — CHỈ chạy test/smoke, KHÔNG gen full

Bạn là agent thực thi. Xây dựng một module sinh data finetune **độc lập, tách hẳn** trong
`datagen/intakedata/`, cho model **Unified Intake** (Qwen 2.5 3B Q4): đọc 1 turn tiếng Việt →
1 JSON `{intent, confidence, description, context, clinical}` (gộp extract + intent route).

**Đọc trước, bắt buộc:**
1. `datagen/intakedata/PLAN.md` — plan implement-ready (làm ĐÚNG theo, không tự đổi thiết kế).
2. `datagen/UNIFIED_INTAKE_DATAGEN_SPEC.md` — spec nội dung, hành vi, quota, confidence policy.
3. `src/acne_llm/schemas/core.py` + `src/acne_llm/chat/llm_extractor.py` — nguồn enum + wire key (copy nguyên).
4. `datagen/roledata/` — **kiến trúc tham chiếu để clone** (config/generator/gates/writer/pipeline). Đọc để mô phỏng khung, KHÔNG copy nội dung role, KHÔNG import.

---

## Ràng buộc cứng (vi phạm = fail)

1. **KHÔNG chạy gen full.** Tuyệt đối không sinh 4.000 mẫu. Chỉ được chạy:
   - `pytest -q datagen/intakedata`
   - `python -m datagen.intakedata.pipeline --smoke --yes -v` (1 record/case)
   - tối đa `python -m datagen.intakedata.pipeline --limit 8 --yes -v` để chứng minh wiring.
   Không bỏ `--limit`, không dùng `--full`. Bước gen cuối do **người dùng** tự chạy.

2. **Tách biệt tuyệt đối.** Chỉ tạo/sửa file trong `datagen/intakedata/`. KHÔNG đụng
   `datagen/main.py`, `datagen/generator.py`, `datagen/gates.py`, `datagen/roledata/`, hay bất kỳ
   file nào khác. Viết mới sạch, không import code cũ.

3. **Provider = OpenAI, đọc từ `.env`.** Dùng `OPENAI_API_KEY`, hỗ trợ `OPENAI_BASE_URL`
   (default `https://api.openai.com/v1`) và `OPENAI_MODEL` (default `gpt-4o-mini`). KHÔNG hardcode
   key/model — chỉ đọc env qua `config.py`. Thiếu `OPENAI_API_KEY` → `config.validate()` báo lỗi rõ,
   preflight dừng sạch, không crash mơ hồ.

4. **Parity là bất biến số 1.** `system_prompt.canonical.txt` cố định; mọi record `messages[0].content`
   phải byte-identical. Implement 3 tầng: preflight `anchor.assert_parity()`, per-record gate
   `system_parity`, verify ở post-validate.

5. **Constrained + enum tuyệt đối.** Enum copy nguyên từ code (PLAN §3). Record có enum ngoài tập,
   `intent` ngoài 4 giá trị, `confidence` ngoài [0,1], hay `clinical` là object rỗng (thay vì `null`)
   → gate REJECT. `validate_intake_record()` là cổng chặn cứng.

6. **Log realtime trên CLI.** StreamHandler stdout SONG SONG file `output/logs/intake.log`. Trong
   generate in progress mỗi `progress_every`: case đang sinh, accept/target, reject, elapsed. Chứng
   minh ngay ở `--smoke` (không im lặng).

---

## Việc cần làm (theo Phase trong PLAN, DỪNG trước full run)

### Phase 0 — Scaffold
- `__init__.py`, `config.py`, `anchor.py`, `schema.py`, `taxonomy.yaml`, `system_prompt.canonical.txt`.
- `config.py`: `Config` dataclass + tiny `.env` loader (không thêm dependency), `FULL_TARGET=4000`,
  `CASE_TYPE_TARGETS` (PLAN §2, Σ=4000, import invariant), `compute_budget()` largest-remainder,
  `validate()`.
- `schema.py`: enum sets (PLAN §3), `build_json_schema()`, `validate_intake_record()` trả `(ok, reasons)`.
- `anchor.py`: `assert_parity()`, `anchor_sha256()`.
- Tests: `test_budget.py` (Σ==4000), `test_anchor.py` (parity + fail khi lệch),
  `test_schema.py` (enum-valid pass, JSON hỏng/enum lạ/clinical rỗng → fail).

### Phase 1 — Core generation + seed
- `writer.py`: append-only JSONL, dedup theo `id`, resume, audit line (không log secret).
- `generator.py`: `CaseSpec`, `synthesize_seed()`, `build_gen_prompt()` (ép JSON khớp schema +
  hành vi case + invariants SPEC §4 + confidence policy SPEC §5), `OpenAIGenerator` async retry/backoff,
  `to_record()` (bọc `messages` SFT, system=anchor, assistant=JSON minified, `meta`).
- `seed.py`: relabel `data/golden_extraction_gen.jsonl` (flat→nested node+intent, PLAN §6); loại record
  không map / enum lạ; `meta.source="golden_relabel"`.
- `gates.py`: `evaluate_record` + `CorpusGateState` với validators PLAN §7 — đặc biệt `negation_leak`
  (entity sau cue phủ định KHÔNG vào list) và `empty_discipline` (knowledge/reject/glue → context rỗng,
  clinical null).
- Tests: `test_gates.py` (negation-leak reject, empty-discipline, balance counter),
  `test_seed.py` (flat→nested đúng contract, enum-valid).

### Phase 2 — Orchestrator
- `pipeline.py`: one-command (preflight→probe→seed→generate→gate→top-up→post-validate→split 90/10→summary),
  argparse (`--smoke/--limit/--yes/-v/--no-seed/--full`), CLI log realtime, `summary.json`.
- Test: `test_pipeline_contracts.py` (smoke wiring, resume idempotent, dedup, split không rò eval).

### Phase 3 — Chứng minh wiring (KHÔNG full)
- Chạy `pytest -q datagen/intakedata` → xanh.
- Chạy `--smoke --yes -v` → 1 record/case, log realtime, mọi record schema-valid + parity.
- Chạy `--limit 8 --yes -v` → đủ vòng gate/top-up/split, không lỗi.
- Viết `datagen/intakedata/README.md` ngắn: cách user chạy `--full` để gen data cuối.
- **DỪNG.** Báo cáo: cây file, kết quả test, mẫu 2–3 record smoke, lệnh `--full` để user tự chạy.

---

## Definition of Done
- `pytest -q datagen/intakedata` xanh toàn bộ.
- `--smoke` + `--limit 8` chạy sạch, log realtime, record schema-valid + parity byte-identical.
- Không có file nào ngoài `datagen/intakedata/` bị tạo/sửa (trừ `codex_intakedata_build_prompt.md`
  này và output/log do chạy sinh).
- KHÔNG chạy `--full`. Bàn giao lệnh full cho người dùng.

---

## Sau khi Codex xong (người dùng tự làm)
```
# Gen dataset cuối để finetune:
python -m datagen.intakedata.pipeline --full --yes -v
# Output: datagen/intakedata/output/intake/intake.train.jsonl (+ .val.jsonl, summary.json)
```
Sau đó build eval gold gán tay (~500, SPEC §7) tách riêng trước khi train LoRA.
