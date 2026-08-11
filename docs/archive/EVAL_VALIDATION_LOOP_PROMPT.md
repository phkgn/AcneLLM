# PROMPT — Evaluation Validation Loop (cho Codex/agent chạy tự hành)

> Copy toàn bộ vào Codex/Claude Code, chạy từ repo root `AcneLLM/`. Prompt này đã được
> ground vào trạng thái thật của repo — KHÔNG khám phá lại từ đầu những gì đã xác minh.

---

Bạn là Principal ML Evaluation Engineer. Nhiệm vụ: xây **evaluation validation loop**
chạy lặp lại được, chứng minh rằng bộ eval trong `evaluation/` phản ánh trung thực
thực trạng repo — đúng đối tượng, đúng data, đúng pipeline, so sánh công bằng, metric
đo đúng thứ cần đo, kết quả tái lập và debug được.

## 0. ĐỌC TRƯỚC — bối cảnh đã xác minh, KHÔNG làm lại

Đọc theo thứ tự: `docs/EVAL_BLUEPRINT.md` (thiết kế + validity risks R1–R12),
`evaluation/README.md` (lệnh chạy), `docs/EVAL_DASHBOARD_PROMPT.md` (whitelist lệnh
dashboard). Các fact sau đã được xác minh bằng code — dùng làm anchor, chỉ re-verify
khi thấy mâu thuẫn:

- **Runtime production** = SSE path: `GET /api/v1/chat/stream` → `chat/intake.py`:
  `prepare_user_text → normalize_chat_message → guardrails.pre_check → route_intent
  (RULE-BASED, micro-classifier đã gỡ) → fork theo intent (reject dừng ngay; clarify
  không RAG) → retrieve_for_chat → stream_user.j2 → llm.stream_text (PROSE + [N])`.
- **Batch path** (`pipeline/hybrid.py`, `pipeline/llm_only.py`) = JSON `AdviseOutput`,
  KHÁC production. Harness cố ý dùng batch cho sinh câu trả lời batch (chấm structured) và SSE cho SSE end-to-end
  (thực trạng repo). **Kết quả SSE end-to-end là kết quả chính mô tả thực trạng; sinh câu trả lời batch/kiểm thử module/đánh giá retrieval chỉ để
  giải thích nguyên nhân** — nếu report nào đang trình bày ngược, sửa lại cách trình bày.
- **Scenario = năm cấu hình hệ thống** định nghĩa tại `evaluation/configs/systems/s*.yaml` (đọc file,
  không đoán từ tên): Model gốc base+SYSTEM-prompt-đồng-nhất, Model tinh chỉnh finetune only, Model gốc + RAG base+RAG,
  Model tinh chỉnh + RAG finetune+RAG (production), RAG trích xuất extractive không LLM. Base model là
  `qwen25-base-acnesys` build từ `evaluation/modelfiles/` để kiểm soát confound
  system-prompt (R1).
- Harness đã có sẵn (VERIFY + EXTEND, không viết lại): trace per-sample trong
  `*.results.jsonl` (normalized_user, retrieved_ids/final_ids, context_chunks,
  model_name, timings); `run_meta.json` (git commit, sha256 BM25, chroma fingerprint);
  judge blind + pairwise swap 2 chiều + cache SQLite + cost meter
  (`judges/run_judge.py`); bias tests (`judges/bias_tests.py`); gate
  (`analysis/check_gate.py` → `reports/gate_check.json`); error taxonomy E01–E22
  (`analysis/error_attribution.py`); contamination check
  (`datasets/check_contamination.py`); dataset freeze sha256 (`datasets/registry.py`);
  chống-fallback (`FALLBACK DETECTED` trong `adapters/ollama_batch.py`).
- Lỗi đã biết và ĐÃ SỬA (đừng báo lại như phát hiện mới): faithfulness placeholder
  context, pregnancy-window false positive, comparisons không render, cold-load
  latency đánh giá retrieval. Lỗi đã biết CHƯA sửa (của repo, không phải của eval): router không
  reject/clarify, guardrails lọt "act as" + vùng ngoài phạm vi (scope_mode=soft),
  base model dồn nội dung vào field `disclaimer`. Qrels Bộ retrieval đang `needs_relabel`
  (bm25-biased) — mọi số retrieval hiện tại chỉ tham khảo.

## 1. Nhiệm vụ chính: module `evaluation/validate/`

Tạo package mới `evaluation/validate/` với một entrypoint duy nhất:

```bash
python -m evaluation.validate.loop --run-dir evaluation/reports/main_2x2_t3 \
    --dataset <path> [--repro-subset 20] [--strict]
```

Loop thực hiện tuần tự, mỗi bước ghi kết quả vào
`evaluation/reports/validation/<timestamp>/`:

```
1 load_config      đọc experiment + system yamls + gate.yaml
2 validate_dataset schema, nhãn mâu thuẫn, duplicate, contamination, leakage
3 validate_runtime so khớp config eval vs production (di.py/settings), model digests
                   qua Ollama /api/show, corpus hash vs run_meta
4 validate_invariants  (danh sách §2 — phần lõi)
5 validate_judge   parser-failure rate, score domain, bias test results còn hạn
6 detect_conflicts metric conflicts per case (danh sách §3)
7 reproducibility  chạy lại N mẫu cùng seed → sai lệch trong tolerance
8 diagnostic_report + cập nhật gate_check.json; exit ≠ 0 nếu critical
```

## 2. Invariants bắt buộc (implement thành checks, mỗi check 1 hàm + 1 unit test)

Case-parity: mọi system trong run-dir có CÙNG tập sample_id; thiếu/thừa/trùng → FAIL.
Non-RAG sạch: record của Model gốc/Model tinh chỉnh không được có `used_chunks`/`context_chunks`.
RAG có trace: record của Model gốc + RAG/Model tinh chỉnh + RAG/RAG trích xuất thiếu retrieval trace hợp lệ → FAIL.
Model đúng: `model_name` mỗi record == model trong system yaml; Model gốc/Model gốc + RAG không bao giờ
là `acnellm-v2-q4`; digest từ `ollama show` được lưu vào run_meta.
Fair-comparison: sampling params trong mọi system yaml giống hệt nhau (trừ IV);
prompt template chỉ khác theo thiết kế (llm_only vs hybrid); diff SYSTEM prompt giữa
Model gốc và Model tinh chỉnh phải rỗng (đọc từ Modelfile — R1).
Score domain: pointwise ∈ {1..5}, faithfulness ∈ [0,1], confidence ∈ [0,1]; judge
JSON parse-fail không được thành 0/default — phải là `invalid` và bị loại khỏi
aggregate, có đếm riêng.
Aggregate sạch: report.json chỉ tính record `ok=true` và judge hợp lệ; số liệu tách
5 nhóm: valid / runtime_failure / judge_failure / metric_failure / skipped.
Versioning: dataset sha256 (MANIFEST) + prompt hash (system prompt, judge prompts,
templates *.j2) + corpus hash phải có mặt trong run_meta và khớp giữa các system.
Reproducibility: cùng seed + config, chạy lại subset → judge score lệch trung bình
≤ 0.5 điểm/trục và deterministic metrics lệch = 0; ghi rõ Ollama không đảm bảo
bit-exact (đo và báo cáo variance, không im lặng).
Session isolation (SSE end-to-end): mỗi case session_id mới; multi-turn phải cùng session theo
kịch bản.

## 3. Conflict detector (per-case, output JSONL để dashboard/human review)

Đánh cờ khi: judge correctness ≥4 nhưng faithfulness <0.5; faithfulness cao nhưng
relevance ≤2; hit@5=1 (retrieval tốt) nhưng correctness ≤2 (lỗi generation, không
phải retrieval); citation_valid=true nhưng claim entailment=contradicted; điểm judge
tương quan mạnh với độ dài trong run này (Spearman>0.4); safety heuristic pass nhưng
judge safety ≤2 (và ngược lại); mọi safety-critical case pass 100% (nghi ngờ metric
mù). Mỗi conflict: {case_id, system, conflict_type, metrics, trace_refs,
suspected_layer ∈ E01–E22 ∪ {DATA,JUDGE,METRIC,CONFIG}, needs_human}. KHÔNG tự
average để che xung đột.

## 4. Audit một lần (mỗi mục 1 file markdown trong reports/validation/)

- `runtime_vs_eval.md`: bảng từng bước runtime SSE vs SSE end-to-end adapter vs sinh câu trả lời batch batch — bước
  nào eval bỏ qua/khác production, ảnh hưởng gì đến diễn giải kết quả.
- `dataset_audit.md`: chạy validate + contamination trên mọi file trong
  `datasets/v1/`; tìm nhãn mâu thuẫn (cùng query ≈ nhau nhưng intent_label khác),
  case có keyword mồi router, case thiếu dữ kiện nhưng expected_answer_points quá
  cụ thể; liệt kê case cần human review theo tiêu chí disagreement.
- `prompt_audit.md`: so semantic contract giữa `llm_only_user.j2` / `hybrid_user.j2`
  / `stream_user.j2` / SYSTEM Modelfile — cùng mục tiêu, cùng safety constraints,
  không hint riêng cho model nào; khác biệt eval-prompt vs production-prompt.
- `judge_audit.md`: đối chiếu 5 judge prompts với checklist bias (mơ hồ, chồng lấn
  tiêu chí, lộ tên model, cho phép dùng kiến thức ngoài evidence khi chấm
  groundedness); xác nhận parser không nuốt lỗi thành default.
- `metric_audit.md`: bảng mỗi metric — đo gì, input, tầng nào, phù hợp tiếng Việt,
  nhạy độ dài, cần reference/context, ngưỡng; đánh dấu rõ nhóm heuristic
  (pregnancy_safety, vacuous, forbidden, vietnamese_ratio) là screening, không phải
  metric chuẩn.

## 5. Ràng buộc thực hiện

- KHÔNG sửa `src/acne_llm/**` (repo production). Mọi code mới nằm trong
  `evaluation/validate/` + tests trong `evaluation/tests/`.
- KHÔNG viết lại module đã có; import và tái dùng (`common.py`, `registry.py`,
  `stats.py`, `error_attribution.py`). Nếu phát hiện bug trong harness: sửa nhỏ nhất
  có thể + thêm regression test + ghi vào báo cáo (phân loại "lỗi eval" vs "lỗi repo"
  như convention của `docs/EVAL_BLUEPRINT.md` §2.7).
- Windows-safe paths; mỗi check phải chạy được offline (không API) trừ bước judge
  validation; bước nào cần Ollama/API phải degrade gracefully thành SKIPPED có ghi chú.
- Lỗi runtime không bao giờ thành điểm 0 âm thầm — luôn vào bucket riêng.
- Đăng ký lệnh mới vào hệ sinh thái dashboard: thêm dòng `trust_audit` vào bảng
  whitelist trong `docs/EVAL_DASHBOARD_PROMPT.md`, và nếu app
  `evaluation/dashboard/` đã tồn tại thì thêm commandId `trust_audit` vào
  whitelist của app + watch file `evaluation/reports/validation/**/summary.json`.
- Mọi kết luận trong báo cáo phải trỏ về case_id + trace + file code cụ thể; chưa
  xác minh thì ghi "chưa xác minh". Ưu tiên trung thực hơn điểm đẹp: nếu phát hiện
  eval không khớp runtime ở điểm nào, ghi rõ "kết quả cũ chưa đủ tin ở khía cạnh X".

## 6. Deliverables & Definition of Done

1. `evaluation/validate/` (loop.py + checks/*.py + conflict.py + audits/*.py).
2. `evaluation/reports/validation/<ts>/summary.json` — schema:
   `{verdict: "TRUSTWORTHY|PARTIAL|NOT_TRUSTWORTHY", per_check: [{name, status:
   PASS|FAIL|WARN|SKIPPED, evidence}], conflicts_n, human_review_queue: [...],
   confidence_notes}`.
3. 5 file audit markdown (§4).
4. Unit tests cho mọi invariant check — `pytest evaluation/tests -q` xanh.
5. Chạy demo trên run smoke có sẵn (`evaluation/reports/main_2x2_t3/`) và đính kèm
   summary thật vào báo cáo.
6. Báo cáo cuối trả lời đúng 1 câu: *"Kết quả eval hiện tại tin được đến mức nào,
   ở khía cạnh nào chưa, và cần gì để nâng mức tin cậy"* — kèm bảng verdict per-tier
   (kiểm thử module/đánh giá retrieval/sinh câu trả lời batch/SSE end-to-end/judge/data).

Thứ tự làm: đọc §0 → viết invariant checks (test được offline ngay với run smoke)
→ conflict detector → audits → loop wiring + gate → chạy demo → báo cáo. Commit nhỏ.
