# Cơ sở siêu tham số — Unified Intake LoRA (Qwen2.5-3B Q4)

_Cho `notebooks/finetune_intake_qwen25_3b_q4.ipynb`. Mỗi param kèm nguồn + mức độ vững._

> **Nguyên tắc trung thực:** siêu tham số deep learning là **thực nghiệm**, không rút ra từ chứng minh đóng.
> Bảng dưới phân 3 mức: **[Lý thuyết]** có chứng minh toán học · **[Ablation]** có thực nghiệm trong paper ·
> **[Heuristic]** quy ước thực hành uy tín. Không param nào là "tối ưu chứng minh sẵn" cho đúng ca 3B + JSON tiếng Việt.

---

## 1. Bảng tổng hợp

| Param | Giá trị | Mức | Cơ sở |
|---|---|---|---|
| Base model | Qwen2.5-3B-Instruct 4bit | [Yêu cầu] | Chốt sẵn theo spec (3B Q4) |
| Quantization | 4-bit NF4 | [Ablation] | QLoRA: NF4 tối ưu thông tin cho weight phân phối chuẩn, vượt Int4/FP4 |
| LoRA target | mọi lớp linear (q,k,v,o,gate,up,down) | [Ablation] | QLoRA: phủ hết linear là *điều kiện cần* để bằng full-finetune 16-bit |
| r (rank) | 16 | [Ablation]+[Heuristic] | QLoRA: rank ít ảnh hưởng khi r≥8; 16 là biên an toàn |
| α (alpha) | 32 (=2r) | [Heuristic] | Công thức scaling α/r từ LoRA gốc; giá trị 2r là quy ước Raschka |
| lora_dropout | 0.05 | [Heuristic] | QLoRA dùng 0.05–0.1 cho model ≤13B chống overfit |
| Optimizer | paged AdamW 8-bit | [Ablation] | QLoRA: paged 8-bit AdamW giảm VRAM, không mất chất lượng |
| LR | 2e-4 | [Ablation] | QLoRA dùng 2e-4 cho 7B/13B, cosine |
| Scheduler | cosine, warmup 3% | [Heuristic] | Quy ước SFT chuẩn (QLoRA cosine + warmup) |
| Epochs | 3 (+ early stop) | [Heuristic] | Quy ước Alpaca SFT nhỏ; early-stopping là lưới an toàn |
| max_length | 2048 | [Đo thực] | Đo dataset: max ~1750 token → 2048 dư biên, không cắt cụt |
| Effective batch | 16 (8×2) | [Heuristic] | Batch vừa cho ~3.6k record |
| Loss mask | chỉ trên assistant | [Heuristic] | Mask completion-only là default SFT chủ đạo |
| Inference | greedy, temp=0 | [Đúng task] | Extraction xác định cần deterministic, không sampling |

---

## 2. Diễn giải từng nhóm

### 2.1 Quantization + LoRA placement — **[Ablation, QLoRA]**
QLoRA (Dettmers et al., NeurIPS 2023) chứng minh bằng thực nghiệm hai điều dùng trực tiếp ở đây:
- **NF4** (4-bit NormalFloat) tối ưu thông tin cho weight phân phối chuẩn, vượt Int4/FP4 → đây là cơ sở cho "Q4".
- **LoRA phải phủ MỌI lớp linear** (không chỉ q,v) mới bằng được full-finetune 16-bit. Notebook target đủ 7 lớp `q,k,v,o,gate,up,down` đúng theo đó.

### 2.2 rank r=16 — **[Ablation]** cho ngưỡng, **[Heuristic]** cho giá trị
QLoRA quan sát: **khi đã phủ hết linear, rank ảnh hưởng rất ít trên r≥8**. Nghĩa là r=8 đủ, r=16 là biên an toàn (thừa nhẹ). Với task "học khuôn JSON" (nhẹ hơn học kiến thức), r=8 hoàn toàn khả thi — r=16 không sai, chỉ hơi rộng.

### 2.3 α=32 (α/r=2) — **[Heuristic]**, và lưu ý phản biện lý thuyết
- Công thức scaling `ΔW = (α/r)·BA` đến từ **LoRA gốc (Hu et al., 2021)** — đây là phần "công thức" thật.
- **Nhưng giá trị α=2r chỉ là heuristic thực hành** (phổ biến qua các hướng dẫn của Sebastian Raschka), không có chứng minh 2 là tối ưu.
- **Phản biện lý thuyết:** **rsLoRA (Kalajdzievski, 2023, arXiv:2312.03732)** *chứng minh* scaling α/r làm norm gradient sụp khi rank tăng, và đề xuất **α/√r** để ổn định. Ở r=16 chênh lệch nhỏ nên α/r=2 chấp nhận được; nếu sau này tăng rank, nên bật `use_rslora=True`.
- Một hướng lý thuyết khác: **LoRA+ (Hayou et al., 2024, arXiv:2402.12354)** chứng minh ma trận A và B nên có LR khác nhau để hội tụ hiệu quả hơn — không dùng ở đây, ghi để biết default này không phải "đã tối ưu".

### 2.4 LR 2e-4 + cosine + warmup — **[Ablation]**
QLoRA dùng chính LR **2×10⁻⁴** với cosine schedule cho model 7B/13B. 3B nhỏ hơn nên 2e-4 an toàn; nếu thấy loss dao động hoặc overfit sớm, hạ 1e-4 (QLoRA dùng 1e-4 cho model lớn hơn — cho thấy dải hợp lệ 1e-4…2e-4).

### 2.5 Epochs 3 — **[Heuristic]**, điểm rủi ro nhất
Không paper nào "chứng minh" 3 epoch; đây là quy ước từ **Alpaca (Stanford, 2023)** cho SFT dữ liệu nhỏ. Với task JSON templated, 3 epoch **có nguy cơ overfit khuôn** (học thuộc giá trị field). Giảm thiểu bằng:
- `EarlyStoppingCallback(patience=3)` + `load_best_model_at_end` + eval mỗi 100 step.
- Theo dõi đường val-loss: nếu chạm đáy trước cuối epoch 1–2 → early stop cắt; cân nhắc hạ 2 epoch.

### 2.6 max_length 2048 — **[Đo thực, cơ sở vững nhất]**
Không phải copy: đã đo trực tiếp trên 4000 record — system anchor ~2132 ký tự, record dài nhất ~3850 ký tự ≈ ~1750 token. 2048 phủ hết với biên an toàn, không cắt cụt anchor/marker (điều kiện để `train_on_responses_only` mask đúng).

### 2.7 Mask loss completion-only — **[Heuristic chủ đạo]**, có tranh luận
`train_on_responses_only` (chỉ tính loss trên token assistant) là default SFT phổ biến, hợp lý vì system anchor cố định chiếm phần lớn token/record. Lưu ý không phải chuyện đã đóng: **Shi et al. (2024), "Instruction Tuning With Loss Over Instructions"** cho thấy đôi khi tính loss cả instruction lại tốt hơn. Với ca này (anchor cực dài, cố định) thì mask completion-only vẫn là lựa chọn đúng.

### 2.8 Inference greedy temp=0 — **[Đúng bản chất task]**
Khác role (dùng sampling temp=0.3 cho văn xuôi đa dạng), extraction/route cần **xác định và lặp lại được** → greedy `do_sample=False, temperature=0`. Lúc serve nên thêm **constrained decoding** (JSON schema) — đưa lỗi format ≈ 0, phần này thuộc serve chứ không phải train.

---

## 3. Kết luận

Cấu hình = tổng hợp default **có kiểm chứng thực nghiệm (QLoRA)** + **công thức LoRA gốc** + **quy ước SFT (Alpaca/Raschka)**, cộng hai param được tune thẳng cho task (`max_length` đo thực, inference greedy). **Không có "chứng minh trước" cho đúng ca 3B/JSON/tiếng Việt** — hai điểm cần validate thực nghiệm là **epochs (overfit)** và **LR**, đều đã có early-stopping + đường loss + eval gold để kiểm. Muốn "vững lý thuyết" hơn nữa: bật `use_rslora=True` (scaling α/√r) và/hoặc chọn checkpoint theo intent-accuracy trên eval gold thay vì eval_loss.

---

## Nguồn

- LoRA: Hu et al., 2021 — arXiv:2106.09685
- QLoRA: Dettmers et al., NeurIPS 2023 — arXiv:2305.14314
- rsLoRA: Kalajdzievski, 2023 — arXiv:2312.03732
- LoRA+: Hayou et al., 2024 — arXiv:2402.12354
- Loss over instructions: Shi et al., 2024 — arXiv:2405.14394
- Alpaca (3-epoch SFT convention): Taori et al., 2023 (Stanford CRFM)
- α=2r heuristic: Sebastian Raschka, "Practical Tips for Finetuning LLMs Using LoRA (and QLoRA)"
