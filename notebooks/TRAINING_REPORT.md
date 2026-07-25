# Báo cáo train — AcneLLM ROLE LoRA → Qwen2.5-7B (GGUF Q4)

**Notebook:** `finetune_role_qwen25_q4.ipynb`
**Ngày:** 2026-07-23
**Trạng thái:** ✅ Training hoàn tất đủ 3 epoch, đường học lành mạnh, model được lưu.

## Môi trường & cấu hình thực tế

| Mục | Giá trị |
|---|---|
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition (local runtime) |
| Base model | `unsloth/Qwen2.5-7B-Instruct-bnb-4bit` (4-bit NF4) |
| Train / Val | 2.945 / 277 mẫu |
| Epochs / Total steps | 3 / 555 |
| Effective batch | 16 (per-device 4 × grad-accum 4) |
| max_length | 2048 |
| Trainable params | 40,370,176 / 7,655,986,688 = **0.53%** (LoRA r=16, α=32, dropout=0.05) |
| Mask loss | chỉ trên assistant (`train_on_responses_only`) |
| Tốc độ | ~0.24 it/s (~4s/step) — full run ~39 phút |

## Đường học (train/val loss)

| Step | Train Loss | Val Loss |
|---|---|---|
| 100 | 0.8938 | 0.8660 |
| 200 | 0.7658 | 0.8375 |
| 300 | 0.7184 | **0.8119** ← thấp nhất |
| 400 | 0.5709 | 0.8204 |
| 500 | 0.5973 | 0.8124 |
| **Final (555)** | train_loss TB = **0.7611**, epoch 3.0, runtime 2356s | — |

**Nhận xét:**
- Val loss giảm đều tới step 300 (0.866 → 0.812) → model học thật, đúng hướng.
- Từ step 400 train loss lao xuống (0.57) trong khi val loss chững/nhích lên (0.812–0.820) → **bắt đầu overfit nhẹ sau ~epoch 1.6**.
- `load_best_model_at_end=True` (theo `eval_loss`) → **model cuối được khôi phục về checkpoint step 300** (val 0.8119), không phải bản cuối epoch 3. Cơ chế chống overfit hoạt động đúng.
- Không có lỗi. Cảnh báo `num_items_in_batch` của Unsloth là vô hại (grad-accum kém chính xác một chút).

## Kết luận
Training **ổn và đã xong**. Chất lượng hội tụ tốt, đã tự lấy checkpoint tối ưu. LoRA adapter đã lưu (`qwen25_acne_role_lora` + `.zip`). Các bước sau (merge 16bit → **GGUF Q4_K_M** → Modelfile) chạy tự động theo hàng đợi Run-all.

## Khuyến nghị cho lần sau
1. **Giảm còn 2 epoch** (~step 370): val chạm đáy quanh epoch 1.6, epoch 3 chỉ thêm overfit và tốn thời gian. Khớp phát hiện của Raschka (multi-epoch instruction tuning dễ tụt điểm).
2. Nếu muốn ép val thấp hơn nữa: thử LR 1e-4 (thay 2e-4) hoặc tăng dropout 0.05 → 0.1.
3. Giữ nguyên phần còn lại — cấu hình đã đúng khoa học (xem `HYPERPARAMS_RATIONALE.md`).

## Việc còn lại cần xác nhận
- [ ] Merge 16-bit xong (CELL 14)
- [ ] **Export GGUF Q4_K_M xong** (CELL 15) — bước phụ thuộc build llama.cpp, cần theo dõi
- [ ] Modelfile (SYSTEM = anchor v3) + zip (CELL 16)
- [ ] Nạp Ollama: `ollama create acnellm-qwen25-role -f Modelfile`
