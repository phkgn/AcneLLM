# Plan Refactor Evaluation Module — AcneLLM

Mục tiêu: thu gọn evaluation về đúng 4 khối, theo thứ tự:

```
Phase 1: LLM Intaker (JSON gen)  ─┐
Phase 2: LLM Generator (TRỌNG TÂM)├─▶ Phase 4: Bottleneck XYZW
Phase 3: RAG                     ─┘    (so sánh, tìm tầng nghẽn)
```

---

## Phase 0 — Dọn dẹp (refactor scope)

**Giữ:**
- `evaluation/runners/run_experiment` (sinh câu trả lời batch), `judges/`, `analysis/report`, `metrics/` (grounding, scorecard) — Phase 2 dùng.
- `runners/run_retrieval` — Phase 3 dùng.
- `scripts/eval_unified_intake.py` — Phase 1 dùng (nâng cấp).
- `scripts/eval_bottleneck.py` — Phase 4 dùng.
- Dashboard: Runs/Results/Inspect/Review + job/SSE infra giữ nguyên.

**Cắt hoặc hạ cấp thành smoke test (không báo metric trong khóa luận):**
- Các evaluator router/planner rule-based cũ đã được gỡ vì không phải đường runtime chính.
- `probe_semantic` — giữ như dev tool, không phải benchmark.
- Regression smoke cho normalizer/guardrails chạy qua test harness hiện tại, không còn command riêng.
- Trim `command-ids.ts` trong dashboard tương ứng.

---

## Phase 1 — Eval LLM Intaker (structured JSON generation)

Intaker làm 2 việc trong 1 lần gọi LLM: (a) phân loại intent, (b) trích xuất field lâm sàng thành JSON theo schema. Vì vậy đo **3 tầng tách biệt** — format ≠ nội dung:

### Metric

| Tầng | Metric | Ghi chú |
|---|---|---|
| 1. Format | **Schema validity rate**: % output parse được JSON + pass schema (đủ key, đúng type, đúng enum) | Đo cả "parse OK nhưng sai schema" riêng |
| 2. Intent | Accuracy, **macro-F1** (4 lớp advise/knowledge/clarify/reject), **reject recall** riêng (an toàn), confusion matrix | Reject recall là safety metric, không gộp trung bình |
| 3. Extraction | **Per-field precision/recall/F1** (slot-filling style): exact match cho enum/số, fuzzy cho từ vựng thuốc/sản phẩm; micro + macro qua các field; **hallucinated-field rate** (điền field không có trong input) | Đây là chỗ LLM extractor hay "bịa" |

Phụ: latency p50/p95 (intaker chạy mỗi turn), và nếu model xuất confidence → calibration (ECE).

### Cơ sở lý thuyết (paper) cho LLM JSON generation — CÓ, khá nhiều:

- **Struc-Bench** (Tang et al., NAACL 2024) — benchmark sinh văn bản có cấu trúc (JSON/bảng), đề xuất metric format-level vs content-level tách biệt → đúng triết lý 3 tầng ở trên.
- **JSONSchemaBench** (Geng et al., 2025) — benchmark chuyên schema-constrained JSON generation, đo validity trên ~10K schema thật.
- **"Let Me Speak Freely?"** (Tam et al., EMNLP 2024) — chứng minh ép format JSON quá chặt có thể làm giảm chất lượng suy luận → lý do phải báo cáo format validity VÀ content F1 riêng, không chỉ một số.
- **IFEval** (Zhou et al., 2023) — instruction/format following có thể verify tự động.
- **Berkeley Function Calling Leaderboard (BFCL)** (Yan et al., 2024) — chuẩn đo argument accuracy của structured/function-call output, gần nhất với bài toán intake.
- Truyền thống hơn: slot filling F1 từ dialogue state tracking (chuẩn **MultiWOZ**, Joint Goal Accuracy) — intake bản chất là DST một lượt.

### Data
`intake.val.jsonl` (held-out) + gold label; giữ overlap guard với train. Cần bổ sung gold cho hallucination check (field nào KHÔNG được có).

---

## Phase 2 — Eval LLM Generator (trọng tâm khóa luận)

Giữ khung 2×2 năm cấu hình hệ thống (base/finetuned × RAG on/off) — chính thiết kế này là kết quả nghiên cứu. Đo 4 nhóm:

### Metric

| Nhóm | Metric | Paper nền |
|---|---|---|
| Chất lượng tổng thể | **LLM-as-judge pointwise** theo rubric (1–5 hoặc 1–10 per-criterion) + **pairwise win-rate** giữa các system với paired bootstrap CI / Wilcoxon | MT-Bench & Chatbot Arena (Zheng et al., NeurIPS 2023); G-Eval (Liu et al., EMNLP 2023) |
| Đúng ý | **Key-point recall**: % expected_answer_points được cover (judge chấm từng ý) | Rubric-based, kiểu HealthBench (OpenAI 2025) — tiền lệ y khoa dùng rubric per-criterion |
| Grounding | **Faithfulness**: mọi claim y khoa có được chunk retrieve hậu thuẫn không; **citation accuracy** nếu có trích nguồn | RAGAS faithfulness (Es et al., 2023); ALCE (Gao et al., EMNLP 2023) |
| An toàn | **Forbidden-claim rate** (string + judge), hành vi triage trên Bộ an toàn, safety failure **báo riêng, không gộp vào điểm chất lượng** | Đã đúng triết lý trong eval_bottleneck hiện tại |

### Bắt buộc cho tính tin cậy của khóa luận
- **Judge calibration với human labels** trên subset (~50–100 mẫu): Cohen's κ / Spearman giữa judge và người → đã có `judge_bias_tests.json`, làm nốt và báo số này. Zheng et al. 2023 báo GPT-4 judge đạt >80% agreement với người — bạn cần con số tương tự cho tiếng Việt y khoa.
- Kiểm soát **position bias** pairwise (swap A/B, đã chuẩn trong harness).
- Latency + token cost per system.

---

## Phase 3 — Eval RAG

### Metric 2 lớp

**Lớp retrieval thuần (component):** trên `retrieval_test.jsonl` (graded qrels):
- **Recall@k, nDCG@k, MRR, Precision@k** — chuẩn IR cổ điển (TREC).
- Ablation: sparse / dense / hybrid / +rerank / +MMR (harness `run_retrieval` đã có).

**Lớp end-to-end (RAG triad):**
- **Context relevance** (chunk lấy về có liên quan câu hỏi?), **faithfulness** (answer bám context?), **answer relevance** (answer trả lời đúng câu hỏi?) — bộ ba của **RAGAS** (Es et al., 2023); phiên bản có huấn luyện judge: **ARES** (Saad-Falcon et al., NAACL 2024).
- So sánh Model tinh chỉnh vs Model tinh chỉnh + RAG / Model gốc + RAG vs Model tinh chỉnh + RAG trong 2×2 chính là RAG contribution có ý nghĩa thống kê.

---

## Phase 4 — Bottleneck XYZW (module so sánh cuối)

### Cơ sở lý thuyết
Đây chính là **ceiling analysis** (Andrew Ng, ML system design): thay lần lượt từng component bằng oracle/upper-bound rồi đo end-to-end gain — component nào cho gain lớn nhất là bottleneck đáng đầu tư. Gần đây cùng tinh thần: **RAGChecker** (Ru et al., NeurIPS 2024) — error attribution cho pipeline RAG.

### Thiết kế (đã có trong `eval_bottleneck.py`, giữ nguyên triết lý)

| Arm | Cấu hình | Trả lời câu hỏi |
|---|---|---|
| **Z** | real intake + real RAG + local generator | Baseline — chạy đầu tiên |
| **X** | **oracle intake** + real RAG + local | ΔX−Z = intake đang kìm hãm bao nhiêu? |
| **W** | real intake + **oracle RAG** + local | ΔW−Z = retrieval đang kìm hãm bao nhiêu? |
| **Y** | real + real + **API generator** | ΔY−Z = generator local còn cách trần bao xa? (tốn phí) |

### Phương pháp thống kê
- **Cùng một question set bất biến** cho cả 4 arm (script đã fingerprint dataset — giữ).
- Điểm chất lượng: cùng một scorecard judge như Phase 2 → **paired per-question delta** so với Z + bootstrap CI (hoặc Wilcoxon signed-rank).
- Safety failure đếm riêng, không trộn vào quality score (đã đúng trong code).

### Data cần
1 bộ duy nhất, mọi mẫu phải có đủ: `user_query`, **`intent_label` gán tay** (arm X yêu cầu, validate sẵn trong script), `relevant_chunk_ids` + `relevance_grade` (arm W), `expected_answer_points` + `forbidden_claims` (chấm điểm). → Nâng cấp retrieval_test hoặc build bộ B3 riêng ~100–150 mẫu.

---

## Một lệnh chạy tất cả (run-all tối giản)

Refactor `evaluation/full_evaluation.py` (tái dùng pattern `run_preliminary_d2.py`: steps tuần tự + summary.json + run dir cô lập):

```
python -m evaluation.full_evaluation --out evaluation/reports/thesis_<stamp>
  [0] preflight → [1] intake_eval → [2] rag_eval → [3] t3 năm cấu hình hệ thống
  → [4] judge+report ($, confirm) → [5] bottleneck Z→X→W (Y opt-in) → [6] figures
```

Nguyên tắc:
- Fail-soft từng bước (ghi FAIL, chạy tiếp bước độc lập); chỉ preflight fail mới dừng.
- Auto-skip: thiếu intent_label vàng → skip arm X + warning; thiếu judge key → skip judge.
- Cost gate: 1 confirm trước judge/arm Y; `--yes` cho overnight.
- Re-run rẻ nhờ sinh câu trả lời batch `--resume` + judge cache sqlite.
- Flags tối thiểu: `--smoke`, `--skip`, `--limit`, `--with-arm-y`, `--yes`.
- Dashboard: nút Run all trỏ orchestrator mới, giữ nguyên job/log/progress infra.

## Thứ tự thi công đề xuất

1. **Tuần 1**: Phase 0 dọn dẹp + chốt bộ metric & rubric (viết chương phương pháp luận song song).
2. **Tuần 2**: Phase 1 — nâng `eval_unified_intake.py` lên 3 tầng metric; bổ sung gold hallucination.
3. **Tuần 3–4**: Phase 2 — chạy 2×2 sinh câu trả lời batch + judge + human calibration subset (việc nặng nhất, là kết quả chính).
4. **Tuần 4**: Phase 3 — retrieval ablation + RAG triad (harness có sẵn, chủ yếu chạy).
5. **Tuần 5**: Phase 4 — build bộ B3 (label intent tay qua trang Review của dashboard), chạy Z → X → W → Y, phân tích delta.
6. **Cuối**: figures + report, mọi con số kèm CI.

## Rủi ro cần né

- Judge chưa calibrate với người → mọi kết luận Phase 2/4 yếu. Làm calibration sớm.
- Bộ bottleneck thiếu intent_label vàng → arm X từ chối chạy (by design). Label trước khi chạy.
- Bộ chất lượng câu trả lời vẫn synthetic-only → khóa luận phải ghi rõ limitation (notice đã có sẵn trong preliminary run).
- Không gộp safety vào quality score ở bất kỳ đâu — hai trục báo cáo riêng.
