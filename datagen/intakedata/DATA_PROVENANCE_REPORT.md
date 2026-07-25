# Báo cáo nguồn dữ liệu — Unified Intake finetune

_Chốt ngày 2026-07-24. Bộ dữ liệu: `datagen/intakedata/output/intake/`._

## 1. Dữ liệu lấy từ đâu

Bộ finetune gồm **4.000 record** (chat SFT, format `messages`), đến từ **hai nguồn**:

| Nguồn | Số record | Mô tả |
|---|---:|---|
| `golden_relabel` | 836 | Tái sử dụng `data/golden_extraction_gen.jsonl` (985 dòng có sẵn), relabel từ schema flat → format intake nested + `{value, confidence}` + intent. Miễn phí, không gọi API. |
| `openai:gpt-4o-mini` | 3.164 | Sinh mới bằng provider, ép constrained JSON schema, qua gate chất lượng. |
| **Tổng** | **4.000** | |

Vì sao golden chỉ còn 836/985: **149 dòng golden bị loại** do trùng nguyên văn với eval set (`data/intent_classify.test.jsonl`) — hai file cùng nguồn gốc sinh ra nên overlap. Toàn bộ contamination đến từ chỗ này và đã được purge sạch (985 − 149 = 836).

## 2. Phân bố (đạt đúng thiết kế SPEC §6)

16/16 case_type đạt target. Phân bố intent:

| intent | số record |
|---|---:|
| advise | 2.000 |
| clarify | 700 |
| knowledge | 800 |
| reject | 500 |

Split: **train 3.600 / val 400** (90/10).

## 3. Kiểm định chất lượng (đã verify)

| Chỉ tiêu | Kết quả |
|---|---|
| status | complete (4.000/4.000) |
| schema hợp lệ | 4.000/4.000 (invalid = 0) |
| enum hallucination | 0 (constrained decoding) |
| rò rỉ eval (train+val ∩ eval) | **0** |
| parity system prompt (train==serve) | OK, byte-identical |
| trùng id | 0 |

## 4. Eval — TÁCH RIÊNG, chưa nằm trong bộ này

- Intent test: `data/intent_classify.test.jsonl` (260) — giữ nguyên, đã loại khỏi train.
- Extraction gold: **~250, cần gán tay mới** (nhồi negation / duration / knowledge-trap / no-accent).
- ⚠️ Không được lấy extraction gold từ `golden_extraction_gen.jsonl` vì file đó đã đóng góp vào train.

## 5. Sẵn sàng finetune chưa?

**Có — train/val đã sạch và sẵn sàng train.** Bộ eval gold (extraction) là để *đo* sau khi train, không chặn việc bắt đầu; nên build song song.

Cấu hình đề xuất:
- QLoRA trên Qwen 2.5 3B, quantize 4-bit; LoRA rank 16–32; 2–3 epoch.
- Train = `intake.train.jsonl`, val = `intake.val.jsonl`.
- Serve: bật constrained decoding (JSON schema từ `schema.py`) + giữ rule-based (`normalizer.py`, `intent_router.py`) làm fallback đường cùng.

**Chốt: tiến hành finetune được.** Việc còn lại song song là dựng eval gold extraction để đánh giá sau train.
