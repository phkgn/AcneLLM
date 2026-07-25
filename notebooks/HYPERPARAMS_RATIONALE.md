# Cơ sở khoa học cho siêu tham số — `finetune_role_qwen25_q4.ipynb`

Tài liệu này giải thích **vì sao** mỗi siêu tham số trong notebook được chọn, dựa trên các paper/nguồn uy tín, và ánh xạ với đặc thù dataset ROLE của AcneLLM (2.945 train / 277 val / 243 holdout, mỗi record có system anchor v3 ~1.240 token cố định).

## Bảng tổng hợp

| Tham số | Giá trị | Căn cứ chính |
|---|---|---|
| Base + lượng tử hóa | Qwen2.5-7B-Instruct, **4-bit NF4** | QLoRA (Dettmers 2023) |
| LoRA rank `r` | **16** | Raschka; LoRA-Learns-Less |
| LoRA `alpha` | **32 (= 2r)** | Raschka; Unsloth guide |
| LoRA `dropout` | **0.05** | QLoRA (0.05–0.1 cho ≤13B) |
| Target modules | **tất cả lớp linear** (q,k,v,o,gate,up,down) | QLoRA; Raschka |
| Learning rate | **2e-4** (nên sweep 1e-4…3e-4) | Unsloth; LR-matters papers |
| Scheduler / warmup | **cosine, warmup 0.03** | cấu hình Qwen2.5 phổ biến |
| Epochs | **≤3 + giữ checkpoint tốt nhất theo val-loss + early stopping** | Raschka; LIMA |
| Effective batch | **16** (`4 × 4`) | LIMA (32/64); thực tiễn LoRA |
| Optimizer | **adamw_8bit** | QLoRA (paged/8-bit optimizers) |
| `max_seq_length` | **2048** | đo thực tế + LIMA (trim 2048) |
| Mask loss | **chỉ trên assistant** (`train_on_responses_only`) | Prompt-loss-matters (2401.13586) |
| weight_decay | **0.01** | thực tiễn chuẩn |

---

## Giải thích từng lựa chọn

### 1. 4-bit NF4 (QLoRA)
QLoRA chứng minh finetune với trọng số lượng tử hóa **4-bit NormalFloat (NF4)** + tính toán bf16 **giữ nguyên chất lượng của finetune 16-bit**, đồng thời đủ nhẹ để train model lớn trên 1 GPU. Đây là lý do dùng `unsloth/Qwen2.5-7B-Instruct-bnb-4bit`. (Dettmers et al., *QLoRA*, NeurIPS 2023.)

### 2. Rank `r = 16`
Raschka (thực nghiệm trên nhiều dataset) và các hướng dẫn LoRA khuyên bắt đầu `r` nhỏ (8–16) cho **thích nghi phong cách/giọng** và dữ liệu gần với pretraining — đúng bản chất task "ép role" của ta (không dạy kiến thức mới, chỉ định hình hành vi/giọng). `r=16` nằm ở "elbow" hiệu năng/chi phí. Tăng `r` chỉ cần khi task phức tạp/đa dạng lớn. (Raschka, *Practical Tips for Finetuning LLMs Using LoRA*.)

### 3. Alpha `= 32 = 2r`  ⟵ **đã sửa so với notebook v2**
Vì thư viện scale ma trận LoRA theo `α/r`, quy tắc heuristic được khuyến nghị rộng rãi là **α = 2r**. Notebook v2 để `α = r = 16` (scaling 1×) — hợp lệ nhưng bảo thủ; chuyển sang `α = 32` (scaling 2×) cho tín hiệu thích nghi mạnh và ổn định hơn theo Raschka và Unsloth guide. (Raschka; *Unsloth LoRA Hyperparameters Guide*.)

### 4. Dropout `= 0.05`  ⟵ **đã sửa so với notebook v2**
QLoRA dùng LoRA dropout **0.1 cho model ≤13B** như một regularizer. Với dataset nhỏ (~3k) nguy cơ overfit cao, nên bật dropout thay vì để 0 như v2. Chọn 0.05 (giữa 0 và giá trị 0.1 của paper) để cân bằng regularization và tốc độ hội tụ. (Dettmers et al., *QLoRA*.)

### 5. LoRA trên tất cả lớp linear
Cả QLoRA lẫn Raschka đều kết luận nên gắn LoRA vào **toàn bộ lớp linear** (không chỉ q,v) để tối đa hiệu năng — notebook giữ đủ 7 module. (Dettmers et al.; Raschka.)

### 6. Learning rate `2e-4` (khuyến nghị sweep 1e-4 → 3e-4)
Các nghiên cứu gần đây nhấn mạnh **learning rate là đòn bẩy quan trọng nhất của LoRA và nên tinh chỉnh trước tiên**, quét trong khoảng ~[1e-5, 5e-4] và chọn giá trị cao nhất mà vẫn ổn định. `2e-4` là mặc định thực dụng của Unsloth cho LoRA 7B và nằm giữa dải khuyến nghị. Nếu có thời gian, quét {1e-4, 2e-4, 3e-4} chọn theo val-loss. (*Learning Rate Matters: Vanilla LoRA May Suffice*; *LR Scaling across LoRA Ranks*; Unsloth guide.)

### 7. Cosine scheduler + warmup 0.03
Cấu hình được dùng phổ biến khi finetune Qwen2.5 (cosine annealing, warmup ratio 0.03) giúp ổn định giai đoạn đầu và giảm LR mượt về cuối. (Tổng hợp cấu hình Qwen2.5 LoRA.)

### 8. Epochs ≤3 + giữ checkpoint tốt nhất + early stopping  ⟵ **cải tiến so với v2**
Raschka thấy **train nhiều epoch cho instruction tuning thường làm tụt điểm do overfit** (tăng gấp đôi số vòng trên Alpaca 50k làm giảm chất lượng). LIMA thì cho thấy chỉ cần rất ít dữ liệu chất lượng cao là học được format/giọng. Do đó thay vì "cứng" 3 epoch như v2, notebook mới:
- eval + save mỗi 100 step,
- `load_best_model_at_end=True` theo `eval_loss`,
- `EarlyStoppingCallback(patience=3)`.

Tức train tối đa 3 epoch nhưng **lấy checkpoint có val-loss thấp nhất**, tự dừng nếu val-loss không cải thiện. (Raschka; Zhou et al., *LIMA*.)

### 9. Effective batch = 16
LIMA dùng batch 32 (64 cho model nhỏ). Với data ~3k, effective batch **16** (`per_device 4 × grad_accum 4`) cho nhiều bước cập nhật/epoch hơn (~184 step/epoch) trong khi vẫn đủ ổn định gradient. Có ghi chú chỉnh `BATCH_SIZE/GRAD_ACCUM` theo VRAM (T4/L4/A100/H100) ở CELL 1. (Zhou et al., *LIMA*.)

### 10. Optimizer `adamw_8bit`
QLoRA giới thiệu **paged/8-bit optimizers** để quản lý đỉnh bộ nhớ mà không hại chất lượng — `adamw_8bit` giảm VRAM optimizer state, phù hợp GPU 16GB. (Dettmers et al., *QLoRA*.)

### 11. `max_seq_length = 2048`  ⟵ **đã sửa so với notebook v2 (1024)**
Đo thực tế trên data: system anchor v3 ~1.240 token, record max ~1.670 token, p95 ~1.490. Để `1024` (như v2) sẽ **cắt cụt** cả anchor lẫn câu trả lời → hỏng parity và mất nhãn. `2048` phủ trọn p100 với dư địa. LIMA cũng trim ở 2048. (Đo trong repo; Zhou et al., *LIMA*.)

### 12. Mask loss chỉ trên assistant (`train_on_responses_only`)  ⟵ **cải tiến so với v2**
Paper *Instruction Fine-Tuning: Does Prompt Loss Matter?* (2401.13586) cho thấy với **dữ liệu "completion ngắn" (tỉ lệ completion/prompt < 1)**, việc xử lý loss trên phần prompt **có ảnh hưởng lớn**, và mask prompt (PLW=0) là chuẩn phổ biến. Data của ta có prompt (anchor ~1.240 token) **lớn hơn nhiều** phần assistant → thuộc chế độ completion-ngắn → **bắt buộc mask** phần system+user, chỉ tính loss trên assistant. Nếu không, ~86% tín hiệu loss đổ vào anchor cố định (học vẹt, phí capacity). (Huerta-Enochian & Ko, 2401.13586.)

---

## Ánh xạ đặc thù dataset → bằng chứng

- **Data nhỏ (~3k) vẫn đủ để ép role**: LIMA cho thấy 1.000 mẫu chất lượng cao đủ định hình hành vi/format — ta có 2.945 mẫu qua gate sạch, dư sức cho mục tiêu "giọng + ranh giới vai".
- **Lo forgetting kiến thức (lớp K1)**: *LoRA Learns Less and Forgets Less* (2405.09673) chứng minh **LoRA quên ít hơn full-finetune, và mức quên do rank kiểm soát** — dùng LoRA `r=16` (thay vì full-FT) chính là lựa chọn bảo toàn kiến thức nền tốt nhất, cộng hưởng với 500 mẫu K1 preservation trong dataset.
- **Anchor cố định khổng lồ**: đẩy ta vào chế độ completion-ngắn → mask prompt là bắt buộc (mục 12).

---

## Khuyến nghị vận hành (nếu muốn tối ưu thêm)
1. **Sweep LR** {1e-4, 2e-4, 3e-4}, chọn theo `eval_loss` — đây là đòn bẩy lớn nhất.
2. Nếu vẫn overfit (val-loss quay đầu sớm): giảm còn 2 epoch hoặc tăng dropout lên 0.1 (giá trị QLoRA gốc).
3. Sau train: đo **retention** (base vs finetuned trên holdout, đặc biệt K1) làm cổng release — cần thêm cell so sánh (có thể bổ sung).

---

## Nguồn

- [QLoRA: Efficient Finetuning of Quantized LLMs (Dettmers et al., 2023)](https://arxiv.org/abs/2305.14314)
- [LoRA Learns Less and Forgets Less (Biderman et al., TMLR 2024)](https://arxiv.org/abs/2405.09673)
- [LIMA: Less Is More for Alignment (Zhou et al., 2023)](https://arxiv.org/abs/2305.11206)
- [Instruction Fine-Tuning: Does Prompt Loss Matter? (2401.13586)](https://arxiv.org/abs/2401.13586)
- [Practical Tips for Finetuning LLMs Using LoRA — Sebastian Raschka](https://magazine.sebastianraschka.com/p/practical-tips-for-finetuning-llms)
- [LoRA Fine-tuning Hyperparameters Guide — Unsloth](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide)
- [Learning Rate Matters: Vanilla LoRA May Suffice for LLM Fine-tuning](https://arxiv.org/pdf/2602.04998)
- [Learning Rate Scaling across LoRA Ranks and Transfer to Full Finetuning](https://arxiv.org/html/2602.06204v1)
