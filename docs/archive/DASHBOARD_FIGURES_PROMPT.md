# PROMPT — Trang Figures: visualize toàn repo (A–F) trong dashboard

> Copy vào Codex, chạy từ repo root `AcneLLM/`. Tiếp nối dashboard hiện có tại
> `evaluation/dashboard/` (port 3100). Đọc `docs/EVAL_DASHBOARD_PROMPT.md` để biết
> whitelist/API hiện tại.

---

Bạn là fullstack engineer. Nhiệm vụ: thêm hệ thống visualize TOÀN REPO vào dashboard
theo kiến trúc **compute-in-Python → artifact → render-in-web**. Next.js KHÔNG được
tính toán nặng (không đọc chroma_db/train jsonl trực tiếp); mọi số liệu do Python
sinh ra thành artifact, dashboard chỉ đọc qua `/api/files` và vẽ bằng recharts
(JSON) hoặc `<img>` (PNG).

## 1. Python figure generators (code mới, đặt trong `evaluation/analysis/`)

Ba module CLI, mỗi cái xuất vào `evaluation/reports/figures/<group>/` gồm các file
`*.json` (data cho recharts) hoặc `*.png` (hình Python vẽ sẵn: UMAP, heatmap lớn)
+ 1 `manifest.json`:

```json
{"generated_at": "...", "group": "kb", "figures": [
  {"id": "kb_umap", "title": "Embedding space (UMAP)", "kind": "png|chart",
   "file": "kb_umap.png", "chart_type": "scatter|bar|line|heatmap|hist",
   "caption": "...", "source_data": "data/chroma_db", "status": "ok|skipped",
   "skip_reason": null}
]}
```

### `figures_kb.py` — nhóm A (KB/corpus) + B (finetune data)
- A2 phân phối độ dài chunk (`data/raw/chunks.jsonl`) → hist JSON.
- A3 **UMAP embedding space**: lấy vectors từ ChromaStore (sample tối đa 8.000,
  seed 42), umap-learn (thêm vào requirements riêng của evaluation nếu chưa có),
  tô màu theo `source`, xuất PNG matplotlib + JSON scatter (giảm còn 2.000 điểm cho
  web). Chạy > vài phút là bình thường — in progress ra stdout để log stream hiển thị.
- A4 near-duplicate rate (cosine >0.95 trên sample A3) → bar JSON.
- A5 coverage matrix: đếm chunk theo (lesion-term × treatment-term × population-term)
  bằng keyword matching từ taxonomy có sẵn (`scripts/eval/normalizer/taxonomy.py`,
  import read-only) → heatmap PNG + JSON.
- A6 tuổi tài liệu nếu metadata có ngày (không có → status=skipped kèm lý do).
- A7 histogram khoảng cách query→OOD centroid (`config/ood_centroid.json`, embedder,
  queries lấy từ `evaluation/datasets/v1/dev_tuning.jsonl`), vẽ đường threshold hiện tại.
- A8 top-30 BM25 terms → bar JSON.
- B1 độ dài prompt/response train vs test (`data/finetune/clean/*.jsonl`) → hist chồng.
- B2 thành phần dataset theo file/case_type → stacked bar.
- B3 phân phối nhãn metadata (severity, safety_flags, is_pregnant) → bar.
- B4 đọc output `check_contamination` (chạy nếu chưa có) → hist overlap + threshold.
- B5 top-30 source_chunk_id được dùng sinh QA → bar (phát hiện oversample).
- B6 đọc `data/finetune/clean/*.clean_report.json` có sẵn → before/after bar.

### `figures_eval.py` — nhóm C (model) + F (eval results)
Input `--run-dir` (mặc định run mới nhất có report.json):
- F1 bar năm cấu hình hệ thống × 6 trục judge + error bar CI (bootstrap từ judged.jsonl, tái dùng
  `analysis/stats.paired_bootstrap`).
- F2 forest plot 4 cặp pre-registered (Δmean + CI, đường 0) → PNG matplotlib
  (forest khó vẽ đẹp bằng recharts).
- F3 retrieval curves hit@k/recall@k theo k per mode (đánh giá retrieval summary mới nhất).
- F4 heatmap task_type × system (correctness mean) → JSON heatmap.
- F5 error Pareto stacked (đã có bar đơn trong /results — nâng thành stacked per system).
- F6 normalizer per-field F1 (reports/unit/normalizer).
- F7 confusion matrix intent (reports/unit/intent_router).
- F8 scatter judge↔human + ρ (annotation/human_labels.jsonl — skipped nếu chưa có).
- F9 scatter correctness vs latency (bubble).
- F10 violin/box điểm judge per system → PNG.
- F11 scatter faithfulness vs correctness per case, tô vùng correct-but-unfaithful.
- C3 latency breakdown stacked (timings_ms trong results.jsonl: retrieval/generation).
- C1 loss curve: parse `notebooks/*.ipynb` outputs tìm log loss (best-effort;
  không có → skipped).

### `figures_usage.py` — nhóm D (production usage, audit.db/sessions.db)
- **BẮT BUỘC ẩn danh**: mọi text query phải qua `mask_pii` (import từ
  `acne_llm.guardrails.ood_detector`, read-only) trước khi ghi ra artifact.
- Bộ dev intent/route distribution từ audit.db → bar (so cạnh composition dataset eval).
- Bộ chất lượng câu trả lời refusal/clarify rate theo tuần → line.
- Bộ ca khó phân phối số turn/session → hist.
- Bộ an toàn top-30 từ khóa query thật (sau mask, bỏ stopword) → bar (không word-cloud lib).
- DB không tồn tại/rỗng → mọi figure status=skipped, KHÔNG crash.

## 2. Dashboard — trang `/figures`

- Tab theo nhóm: `KB & Corpus (A)` / `Finetune Data (B)` / `Model & Latency (C)` /
  `Usage (D)` / `Diagrams (E)` / `Eval Results (F)`.
- Mỗi tab đọc `manifest.json` nhóm tương ứng → render grid card: chart recharts
  (theo `chart_type`) hoặc `<img>`; caption + `generated_at` + nút "Regenerate"
  (spawn command tương ứng qua job API có sẵn, disable khi đang chạy).
- Figure `status=skipped` → card xám hiện `skip_reason`.
- Tab Diagrams (E): render 2 sơ đồ mermaid client-side (import mermaid): E2 pipeline
  8-task trước RAG/LLM + fork intent (vẽ theo `docs/EVAL_BLUEPRINT.md` §2.2), E3 eval
  4 tầng + ma trận năm cấu hình hệ thống; kèm link mở `acnellm_pipeline.html`, `pipeline_simulator.html`
  có sẵn (serve qua /api/files với content-type html — chỉ 2 file này, whitelist path).
- Nút "Export all PNG+PDF" → chạy generators với flag `--pdf` (matplotlib xuất kèm
  .pdf cho LaTeX).

## 3. Whitelist & tích hợp

Thêm 3 commandId vào whitelist dashboard + cập nhật bảng trong
`docs/EVAL_DASHBOARD_PROMPT.md`:

| id | Lệnh |
|---|---|
| `figures_kb` | `python -m evaluation.analysis.figures_kb [--sample 8000] [--pdf]` |
| `figures_eval` | `python -m evaluation.analysis.figures_eval [--run-dir <dir>] [--pdf]` |
| `figures_usage` | `python -m evaluation.analysis.figures_usage [--pdf]` |

Watch: `evaluation/reports/figures/**/manifest.json`.

## 4. Ràng buộc

- KHÔNG sửa `src/acne_llm/**` (import read-only được phép). KHÔNG đọc `.env` ra artifact.
- Artifact JSON ≤ ~1MB/file (sample/aggregate trước khi ghi); PNG dpi 150, PDF vector.
- Mọi generator chạy được độc lập, idempotent, exit 0 kể cả khi nhiều figure skipped.
- Deps Python mới (umap-learn, matplotlib) thêm vào `evaluation/requirements.txt`
  (tạo mới nếu chưa có, KHÔNG đụng requirements.txt gốc).
- Unit tests: mỗi generator có test với data giả nhỏ (tmp_path) kiểm tra manifest
  schema + skipped-graceful; test render page bằng test suite dashboard hiện có.
- Windows-safe; tiếng Việt trong figure dùng font mặc định matplotlib có fallback
  (DejaVu Sans — kiểm tra không vỡ dấu).

## 5. Acceptance

1. `figures_eval` chạy trên run smoke có sẵn → tab F hiện ≥ 8 figures thật.
2. `figures_kb` chạy xong (UMAP có thể lâu — log tiến độ stream được trên /runs)
   → tab A/B hiện figures; A3 PNG mở được.
3. `figures_usage` với audit.db thật → tab D render, mọi query text đã mask PII
   (kiểm tra thủ công 5 mẫu trong artifact JSON không chứa số điện thoại/email).
4. Tab E render 2 mermaid diagram không lỗi console.
5. Regenerate từ UI hoạt động, card cập nhật sau khi job xong.
6. `pytest evaluation/tests -q` + build dashboard xanh; báo cáo ngắn liệt kê figure
   nào ok/skipped và vì sao.

Thứ tự: `figures_eval` (data sẵn có, thấy kết quả ngay) → trang `/figures` + tab F
→ `figures_kb` → `figures_usage` → Diagrams → QA acceptance.
