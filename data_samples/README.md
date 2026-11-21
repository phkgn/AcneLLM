# Mẫu dữ liệu sạch — AcneLLM (`data_samples/`)

Thư mục này chứa các lát cắt mẫu phân tầng (stratified samples) được trích xuất tự động bằng [scripts/export_data_samples.py](../scripts/export_data_samples.py) với `seed=42`. Mục tiêu là giúp người đọc và giảng viên hướng dẫn kiểm tra trực tiếp cấu trúc, nhãn và phân bố dữ liệu ngay trên GitHub mà không phải tải hàng trăm MB dữ liệu thô hoặc vi phạm bản quyền tài liệu gốc.

## 1. Bảng tổng hợp tập mẫu và quy mô dữ liệu thật

| Tệp mẫu trong thư mục này | Số dòng mẫu | Nguồn gốc đầy đủ | Quy mô toàn bộ tập dữ liệu đã xác minh |
|---|---:|---|---|
| `kb_chunks_sample.jsonl` | 20 | `data/raw/chunks.jsonl` | `6.835` tài liệu thô → `6.796` tài liệu đạt ngưỡng (`quality_score >= 0.3`) → `24.393` chunks (đồng bộ `24.393` vector ChromaDB + `24.393` bản ghi BM25) |
| `intaker_train_sample.jsonl` | 20 | `research/datagen/intakedata/output/intake/intake.records.jsonl` | `4.000` mẫu chấp nhận (`3.600` train / `400` val; `advise: 2.000`, `knowledge: 800`, `clarify: 700`, `reject: 500`; `0` exact overlap với eval) |
| `generator_role_sample.jsonl` | 15 | `research/datagen/roledatav2/output/roledata.train.jsonl` | `3.077` mẫu chấp nhận (`2.616` train / `246` val / `215` holdout; mục tiêu ban đầu `3.500` chưa hoàn tất) |
| `eval_calibration_rrr_sample.jsonl` | 15 | `research/evaluation/reports/calibration_rrr/sheet_rrr145_khang.jsonl` | `145` phiếu chấm tay hiệu chuẩn LLM Judge trên arm `RRR` (thuộc bộ `v2_full`: `1.490` intake, `120` retrieval, `145 × 6 = 870` ablation rows) |

Mã băm kiểm toàn vẹn SHA-256 của 4 tệp mẫu được ghi tại [SHA256SUMS.txt](SHA256SUMS.txt).

## 2. Mô tả schema từng tệp mẫu

- **`kb_chunks_sample.jsonl`**: Đại diện cho các nguồn trong KB (`aad_guideline`, `nice_guideline`, `clinical_textbook`, `pubmed_review`, `vi_medical_site`, `en_medical_site`, `blog` bằng tiếng Việt và tiếng Anh). Các trường gồm `chunk_id`, `doc_id`, `title`, `source_name`, `source_type`, `trust_level`, `language`, `categories`, `position`, `text_len`, `text_truncated`, `text` (đã bỏ vector `embedding` và cắt tối đa 500 ký tự đầu để tránh phân phối lại toàn văn tài liệu).
- **`intaker_train_sample.jsonl`**: Định dạng hội thoại `messages` (`system`, `user`, `assistant`) kèm `meta` (`case_type`, `source`, `gate_checks`). Phân tầng đủ 4 intent (`advise: 8`, `knowledge: 4`, `clarify: 4`, `reject: 4`) và 16 `case_type`, bao gồm các ca phủ định, quy đổi thời gian, câu không dấu, thuốc kê đơn không an toàn và ngoài phạm vi.
- **`generator_role_sample.jsonl`**: Định dạng ShareGPT (`id`, `sample_kind`, `input_style`, `messages`, `gate_results`, `gen_model`), bao phủ 15 nhóm `sample_kind` thuộc quy tắc vai trò (`R1–R10`), tiếp đất/từ chối khi thiếu ngữ cảnh (`B1–B4`) và neo kiến thức (`K1`).
- **`eval_calibration_rrr_sample.jsonl`**: Các dòng đối chiếu đánh giá của người chấm trên 4 trục (`human_answer_quality`, `human_role_tone`, `human_incorrect_content`, `human_missing_content`) và cờ vi phạm (`human_forbidden_violated`), phân tầng đủ thang điểm `1–5` kèm các ca có cảnh báo an toàn.

## 3. Ranh giới bản quyền và cách khôi phục toàn bộ artifact

- **Bản quyền tài liệu gốc**: Các tệp PDF/văn bản hướng dẫn y khoa bản quyền trong `research/guideline_docs/*_docs/` và toàn văn bài báo crawl trong `data/raw/` không được đẩy trực tiếp lên cây Git. Danh mục URL gốc nằm tại [data/seed_sources.yaml](../data/seed_sources.yaml) và [research/guideline_docs/manifest.json](../research/guideline_docs/manifest.json) cùng bộ script tải lại.
- **Khôi phục đầy đủ KB & Model**: Bản snapshot runtime KB (`kb-v2-2026-08-23`), trọng số GGUF/LoRA (`models-v2-2026-08-23`) và kho tri thức kiểm toán (`knowledge-2026-08-23`) được phát hành kèm SHA-256 tại GitHub Releases; xem hướng dẫn chi tiết tại [docs/RELEASE_ARTIFACTS.md](../docs/RELEASE_ARTIFACTS.md).
- **Tái tạo lại tệp mẫu cục bộ** (khi đã có bộ dữ liệu gốc trong máy):

```powershell
py -3.10 scripts/export_data_samples.py
```
