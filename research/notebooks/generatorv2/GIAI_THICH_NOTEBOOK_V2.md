# Notebook finetune v2 — giải thích từng cell, từng tham số, và phần phản biện

Tài liệu này đọc `finetune_role_v2_qwen25_q4.ipynb` theo ba câu hỏi cho mỗi thứ:
**nó làm gì**, **vì sao chọn giá trị đó**, và **có bằng chứng nào nói ngược lại không**.

Phần phản biện ở cuối là phần đáng đọc nhất — có một chỗ repo đang trích paper
để biện minh cho lựa chọn mà paper đó thực ra kết luận ngược lại.

---

## 1. Bức tranh tổng thể trước khi vào chi tiết

Việc bạn đang làm **không phải dạy model kiến thức mới về mụn**. Kiến thức y khoa
đã có sẵn trong Qwen2.5-7B và trong các đoạn RAG lấy từ guideline. Việc của
finetune là dạy **cách cư xử**: trả lời dài bao nhiêu, có cấu trúc thế nào, khi
nào từ chối, khi nào hỏi lại, giọng điệu ra sao với người đang tự ti.

Hiểu đúng mục tiêu này giải thích gần như mọi lựa chọn tham số phía sau. Nó cũng
giải thích vì sao dùng LoRA chứ không full-finetune, vì sao rank nhỏ là đủ, và vì
sao 2.616 mẫu không phải là ít.

Notebook chia làm ba giai đoạn:

| Giai đoạn | Cell | Làm gì |
|---|---|---|
| **Chuẩn bị** | 0–5 | Cài thư viện, nạp model, nạp dữ liệu, kiểm tra dữ liệu có hợp lệ không |
| **Huấn luyện** | 6–9 | Gắn adapter, cấu hình, che loss, train |
| **Xuất bản** | 10–17 | Lưu, thử, gộp trọng số, chuyển sang GGUF, viết Modelfile |

Ba cell 3, 5, 7 là **chốt chặn** — chúng `assert` và làm nổ notebook nếu dữ liệu
hoặc cấu hình sai. Thiết kế này cố ý: hỏng ở phút thứ 2 rẻ hơn hỏng ở giờ thứ 2.

---

## 2. Giai đoạn chuẩn bị

### CELL 0 — INSTALL

Cài `unsloth`, `peft`, `accelerate`, `bitsandbytes`, `datasets`.

**Unsloth là gì.** Nó viết lại các phép nhân ma trận trong Transformer bằng
Triton kernel tối ưu hơn bản gốc. Kết quả: nhanh hơn ~2× và tốn ít VRAM hơn, mà
kết quả toán học không đổi. Bạn thấy dòng `Unsloth - 2x faster free finetuning`
trong log là nó.

Cell này cố ý **không pin phiên bản** `trl`. Comment trong notebook giải thích:
để unsloth tự chọn bản khớp với nó, vì CELL 7 đã tự dò tên tham số nên không phụ
thuộc phiên bản. Đây là quyết định đánh đổi — pin cứng thì tái lập được nhưng dễ
xung đột, thả lỏng thì linh hoạt nhưng phải có code dò. Notebook chọn vế thứ hai
và trả giá bằng ~30 dòng phòng thủ ở CELL 7.

### CELL 1 — CONFIG

Khai báo mọi hằng số. Không có gì chạy nặng ở đây, nên sửa rồi chạy lại tức thì.

```python
MAX_SEQ_LENGTH = 3072
BATCH_SIZE = 4
GRAD_ACCUM = 4
EPOCHS     = 3
LR         = 2e-4
```

**`MAX_SEQ_LENGTH = 3072`** — độ dài tối đa của một record tính bằng token. Vượt
quá thì bị **cắt cụt**, và phần bị cắt là phần đuôi, tức chính câu trả lời.

Con số này là thay đổi quan trọng nhất so với v1 (2048). Lý do đo được: system
anchor ~1.165 token, record p99 ~2.256 token, record max ~2.609 token. Giữ 2048
thì khoảng 1/4 số record bị cắt giữa câu trả lời — và model học được nửa đầu rồi
học luôn thói quen dừng giữa chừng. Đúng cái bệnh bạn đang muốn chữa.

Cái giá: seq dài gấp 1,5 lần thì activation cũng gấp ~1,5 lần, nên tốn VRAM hơn
và chậm hơn mỗi step.

**`BATCH_SIZE × GRAD_ACCUM = 16`** — đây là **effective batch**, con số thực sự
quan trọng. Nó có nghĩa: model xem 16 mẫu rồi mới cập nhật trọng số một lần.

Vì sao tách làm hai số? Vì GPU không nhét nổi 16 mẫu dài 3072 token cùng lúc.
Nên ta chạy 4 mẫu, giữ gradient lại, chạy 4 mẫu nữa, cộng dồn... đủ 4 lần thì
mới cập nhật. Kết quả toán học **giống hệt** như chạy 16 mẫu một lúc, chỉ chậm
hơn. Đây là lý do bảng GPU trong notebook đổi hai số này theo VRAM nhưng luôn
giữ tích = 16: **để mọi cấu hình cho ra cùng một model.**

Trên A100 40GB bạn để 4×4. Trên T4 16GB phải là 1×16.

**`EPOCHS = 3`** — số vòng model đọc hết dữ liệu. 2.616 ÷ 16 ≈ 164 step mỗi
epoch, ×3 = 492 step tổng.

**`LR = 2e-4`** — learning rate, độ lớn mỗi bước điều chỉnh trọng số. Quá cao thì
model nhảy qua điểm tối ưu và loss dao động loạn; quá thấp thì học chậm và có thể
kẹt. `2e-4` là mặc định thực dụng của Unsloth cho LoRA 7B.

### CELL 2 — LOAD MODEL

```python
BASE_MODEL = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
load_in_4bit = True
```

Nạp Qwen2.5-7B đã được nén xuống **4-bit**. Bình thường một model 7B ở 16-bit tốn
~15 GB VRAM chỉ để chứa trọng số. Nén 4-bit còn ~4 GB.

**Vì sao nén không làm hỏng chất lượng.** Đây là kết quả chính của
[QLoRA (Dettmers et al., 2023)](https://arxiv.org/abs/2305.14314). Họ dùng kiểu
số gọi là **NF4** (NormalFloat 4-bit), thiết kế riêng cho việc trọng số neural
network phân bố gần chuẩn — nên 16 mức lượng tử được đặt ở nơi có nhiều trọng số
nhất thay vì rải đều. Paper chứng minh finetune trên nền 4-bit NF4 **đạt ngang
finetune 16-bit** trên các benchmark của họ.

Quan trọng: trọng số gốc bị đóng băng ở 4-bit và **không được train**. Chỉ có
adapter (CELL 6) được train, và nó ở độ chính xác cao hơn.

### CELL 3 — LOAD DATASET + BẮT ANCHOR

Nạp 3 file jsonl, rồi kiểm tra **anchor**.

**Anchor là gì.** Là system prompt đứng đầu mỗi record. Nó quan trọng vì lúc chạy
thật, Ollama sẽ nhét system prompt từ `Modelfile` vào cùng vị trí đó. Nếu chuỗi
lúc train và lúc chạy **khác nhau dù một ký tự**, model gặp một ngữ cảnh nó chưa
từng thấy — hành vi lệch đi mà không có lỗi nào báo.

Dataset v2 có **ba biến thể** anchor (`system_prompt.v4.a/b/c`, phân bố
1.584/807/686). Đây là **cố ý** — train với nhiều cách diễn đạt để model bám vào
*ý nghĩa* của system prompt thay vì học thuộc một chuỗi ký tự. Kỹ thuật này gọi
là prompt-variant training, và nó làm model bền hơn khi bạn chỉnh sửa system
prompt sau này.

Cell ghim `ANCHOR_SYSTEM` vào biến thể **v4.a** bằng SHA-256, vì đó là bản sẽ
được ghi vào Modelfile ở CELL 16.

### CELL 4 — FORMAT SANG CHATML

Chuyển danh sách `messages` thành một chuỗi text phẳng theo định dạng ChatML:

```
<|im_start|>system
...anchor...<|im_end|>
<|im_start|>user
...câu hỏi...<|im_end|>
<|im_start|>assistant
...câu trả lời...<|im_end|>
```

Model không hiểu khái niệm "vai trò" — nó chỉ thấy chuỗi token. Các thẻ
`<|im_start|>` chính là cách đánh dấu ai đang nói. Qwen2.5-Instruct đã được
pretrain với đúng định dạng này nên ta phải dùng đúng nó.

Cell cũng **xoá mọi cột phụ** (`id`, `sample_kind`, `context`...), chỉ giữ `text`.
Nếu để lại, trainer có thể hiểu nhầm chúng là đầu vào.

### CELL 5 — KIỂM TRA ĐỘ DÀI TOKEN

Đếm token thật của từng record và **dừng notebook nếu >2% vượt `MAX_SEQ_LENGTH`**.

Đây là chốt chặn có giá trị nhất trong cả notebook. Cắt cụt là loại lỗi **im
lặng** — không có exception, không có cảnh báo, chỉ có một model học sai mà bạn
phát hiện sau 3 tiếng train.

Ngưỡng 2% không thiêng liêng, nhưng lý lẽ đằng sau thì có: những record dài nhất
chính là các case `K1` (kiến thức), `B1` (grounding), `R2` (điều chỉnh độ sâu) —
tức những hành vi cốt lõi nhất. Cắt 2% ở đuôi phân bố nghĩa là hy sinh đúng phần
khó nhất.

---

## 3. Giai đoạn huấn luyện

### CELL 6 — GẮN LORA ADAPTER

```python
r=16, lora_alpha=32, lora_dropout=0.05,
target_modules=[q,k,v,o,gate,up,down], use_rslora=False
```

**LoRA là gì, giải thích không dùng toán.** Model có những ma trận trọng số
khổng lồ. Full-finetune nghĩa là sửa toàn bộ 7,6 tỉ số đó — tốn bộ nhớ khủng
khiếp và dễ làm model quên kiến thức cũ.

LoRA thay vào đó **đóng băng ma trận gốc** và gắn thêm bên cạnh một cặp ma trận
rất nhỏ. Khi chạy, kết quả = (ma trận gốc) + (tích của hai ma trận nhỏ). Chỉ hai
ma trận nhỏ được train. Ở đây: **40.370.176 trên 7.655.986.688 tham số = 0,53%**.

Ẩn dụ: thay vì viết lại cả cuốn sách, bạn dán giấy nhớ vào lề. Sách gốc còn
nguyên, và bạn có thể gỡ giấy nhớ ra bất cứ lúc nào.

**`r = 16`** — "độ dày" của giấy nhớ. `r` càng lớn, adapter càng nhiều tham số,
càng học được thứ phức tạp, nhưng càng dễ overfit và tốn hơn.

Căn cứ: [Raschka](https://magazine.sebastianraschka.com/p/practical-tips-for-finetuning-llms)
thực nghiệm trên nhiều dataset và thấy `r` nhỏ (8–16) là đủ cho việc **thích nghi
phong cách và giọng** — đúng bản chất task này. `r=16` nằm ở "elbow", tức điểm mà
tăng thêm không còn đổi lại được nhiều.

**`lora_alpha = 32`** — hệ số khuếch đại. Thư viện nhân đóng góp của adapter với
`α/r`. Ở đây `32/16 = 2`, tức adapter được nhân đôi ảnh hưởng. Quy tắc `α = 2r`
là heuristic được khuyến nghị rộng rãi.

**`lora_dropout = 0.05`** — trong lúc train, ngẫu nhiên "tắt" 5% kết nối trong
adapter mỗi bước. Nghe phá hoại nhưng đây là kỹ thuật chống học vẹt kinh điển:
model không thể dựa vào một đường dẫn cố định nào nên buộc phải học biểu diễn
tổng quát hơn. QLoRA dùng 0.1 cho model ≤13B; đây chọn 0.05, nhẹ hơn.

**`target_modules` — cả 7 lớp linear.** Bản LoRA gốc chỉ gắn vào `q` và `v`.
QLoRA và Raschka đều kết luận gắn vào **toàn bộ** lớp linear cho kết quả tốt hơn
rõ rệt, và đó là lý do dùng đủ 7.

**`use_rslora = False`** — xem phần phản biện §5.2.

**`random_state = 3407`** — hạt giống ngẫu nhiên, để chạy lại ra kết quả giống
nhau. Con số này là một trò đùa trong giới ML, từ paper *"Torch.manual_seed(3407)
is all you need"*.

### CELL 7 — SFTConfig

Cell dài nhất, và phần lớn độ dài là **code phòng thủ chống trôi API**.

Vấn đề: `unsloth`, `trl`, `transformers` đổi tên tham số theo ba lịch khác nhau.
`max_length` ↔ `max_seq_length`, `tokenizer=` ↔ `processing_class=`. Truyền sai
tên thì **không nổ** — bị bỏ qua im lặng, giá trị rơi về mặc định, và bạn chỉ
biết sau khi train xong. Nên cell tự dò tên bằng `inspect.signature` rồi
`assert` lại giá trị đã vào được config.

Các tham số đáng chú ý:

**`warmup_ratio = 0.03`** — 3% số step đầu, learning rate tăng dần từ 0 lên
`2e-4` thay vì nhảy thẳng. Lúc mới bắt đầu, adapter khởi tạo ngẫu nhiên nên
gradient rất nhiễu; đi bước lớn ngay dễ làm hỏng. Warmup là khởi động trước khi
chạy.

**`lr_scheduler_type = "cosine"`** — sau warmup, learning rate giảm dần theo
đường cong cosine về gần 0. Ý tưởng: đầu train đi bước lớn để tìm vùng tốt, cuối
train đi bước nhỏ để tinh chỉnh.

**`optim = "adamw_8bit"`** — optimizer lưu trạng thái ở 8-bit thay vì 32-bit,
tiết kiệm VRAM. Cũng từ QLoRA.

**`weight_decay = 0.01`** — phạt nhẹ các trọng số lớn, chống overfit.

**`eval_steps=50`, `save_steps=50`, `load_best_model_at_end=True`,
`EarlyStoppingCallback(patience=3)`** — bộ tứ chống overfit, và là phần thiết kế
tốt nhất của notebook.

Cứ 50 step thì chấm điểm trên tập val và lưu checkpoint. Nếu 3 lần chấm liên tiếp
không cải thiện (= 150 step) thì dừng. Và bất kể dừng ở đâu, **model cuối cùng
được khôi phục về checkpoint có val loss thấp nhất**, không phải bản cuối.

Cơ chế này đã cứu lần train v1: báo cáo ghi rõ model cuối được lấy về step 300
(val 0.8119) chứ không phải bản cuối epoch 3.

### CELL 8 — CHE LOSS, CHỈ TÍNH TRÊN ASSISTANT

```python
trainer = train_on_responses_only(trainer,
    instruction_part="<|im_start|>user\n",
    response_part="<|im_start|>assistant\n")
```

**Vấn đề nó giải quyết.** Mặc định, model được huấn luyện để dự đoán **mọi**
token, kể cả token trong system prompt và câu hỏi của người dùng. Nhưng anchor là
một chuỗi **cố định** lặp lại ở cả 2.616 record. Nếu tính loss trên nó, model
dành phần lớn công sức học thuộc lòng một chuỗi mà lúc chạy thật nó **luôn được
cho sẵn** — hoàn toàn lãng phí.

`train_on_responses_only` đặt nhãn của mọi token không thuộc phần assistant thành
`-100`, giá trị quy ước nghĩa là "bỏ qua khi tính loss".

Cell in ra tỉ lệ token được tính loss để bạn kiểm chứng bằng mắt.

Với dataset v2 (multi-turn ở case R9), hàm này bắt **mọi** lượt assistant chứ
không chỉ lượt cuối.

**Đây là cell gây tranh cãi nhất — xem §5.1.**

### CELL 9 — TRAIN

Chạy. Đọc log:

```
Num examples = 2,616 | Num Epochs = 3 | Total steps = 492
Batch size per device = 4 | Gradient accumulation steps = 4
Total batch size (4 x 4 x 1) = 16
Trainable parameters = 40,370,176 of 7,655,986,688 (0.53% trained)
```

`resume_from_checkpoint=False` — chạy mới hoàn toàn. Đổi thành `True` nếu phiên
bị đứt và muốn đi tiếp.

---

## 4. Giai đoạn xuất bản

| Cell | Làm gì | Ghi chú |
|---|---|---|
| **10** | Lưu LoRA adapter (~200 MB) | Chỉ giấy nhớ, chưa gộp vào sách |
| **11** | Thử 6 câu chạm 6 hành vi | R10 an toàn, R4 đồng cảm, R8 jailbreak, R1 danh tính, R7 xã giao |
| **12** | In val loss cuối | |
| **13** | Nén adapter | |
| **14** | **Gộp** LoRA vào trọng số gốc ở 16-bit | Cần ~15 GB RAM — đây là chỗ T4 chết |
| **15** | Chuyển sang GGUF Q4_K_M | Định dạng Ollama đọc được |
| **16** | Viết Modelfile | |
| **17** | Tải về | |

**Vì sao phải gộp rồi mới quantize.** LoRA lúc train là hai ma trận riêng. Ollama
không hiểu khái niệm adapter — nó cần một file trọng số duy nhất. Nên phải cộng
adapter vào ma trận gốc (CELL 14), rồi nén kết quả xuống 4-bit (CELL 15).

**Q4_K_M là gì.** Một sơ đồ lượng tử của llama.cpp. `Q4` = 4 bit, `K` = dùng
k-quant (chia nhóm nhỏ, mỗi nhóm có hệ số scale riêng, chính xác hơn nén đều),
`M` = medium, tức cân bằng giữa `S` (nhỏ) và `L` (lớn). Đây là lựa chọn mặc định
phổ biến nhất cho model 7B chạy local.

**CELL 16 có một quyết định đáng chú ý.** Modelfile v2 **cố ý không** đặt
`temperature`, `top_p`, `num_ctx`:

```python
# "PARAMETER temperature 0.3"   ← bị comment
"PARAMETER repeat_penalty 1.05"
'PARAMETER stop "<|im_end|>"'
```

Lý do nằm trong chính repo: `PARAMETER` trong Modelfile **đè** mọi giá trị gửi
qua API, nên Python mất quyền chỉnh theo từng request. Notebook v1 có ghi chúng
vào — nghĩa là `llm_temperature` trong `config.py` hiện **không có tác dụng gì**
với model đang chạy. Đây là một bug thầm lặng mà v2 sửa.

---

## 5. Phản biện — bằng chứng nói ngược lại

Đây là phần bạn hỏi, và nó có thật. Bốn điểm, xếp theo mức độ đáng lo.

### 5.1. Che loss hoàn toàn — paper được trích đang bị đọc ngược

`HYPERPARAMS_RATIONALE.md` §12 trích paper
[*Instruction Fine-Tuning: Does Prompt Loss Matter?* (Huerta-Enochian & Ko, EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.1267/)
để biện minh cho việc mask toàn bộ prompt.

**Nhưng kết luận của paper là ngược lại.** Với dữ liệu completion-ngắn, họ tìm
thấy quan hệ **bậc hai âm** giữa hiệu năng và prompt loss weight (PLW), và:

> Model finetune trên dữ liệu completion-ngắn với prompt loss masking (PLW = 0)
> **gần như luôn cho kết quả tệ nhất** trên nhiều benchmark.

Giá trị tối ưu họ tìm được là **PLW nhỏ nhưng khác 0** (0,01–0,1) cho tác vụ
sinh ngắn, và **PLW ≈ 1,0** cho tác vụ **sinh dài**.

**Dataset của bạn nằm ở đâu.** Tôi đo trên `train.jsonl`:

| | tỉ lệ completion/prompt |
|---|---|
| v1 (`roledata`) | 0,082 |
| **v2 (`roledatav2`)** | **0,200** |

Không record nào đạt tỉ lệ ≥ 1. Vậy **cả hai đều nằm trong vùng completion-ngắn**
mà paper nói masking là lựa chọn tệ nhất. v2 có khá hơn v1 2,4 lần nhưng vẫn còn
xa ngưỡng.

Và AcneLLM là tác vụ **sinh dài** — viết đoạn tư vấn nhiều ý. Theo paper, vùng đó
tối ưu ở PLW ≈ 1,0, tức **gần như không mask gì cả**.

**Nói công bằng cho phía masking:**

- Paper đo trên benchmark tổng quát (trắc nghiệm, sinh văn bản chung), không đo
  *tuân thủ vai trò trong miền hẹp* — đúng cái bạn cần.
- Lý lẽ "anchor cố định lặp 2.616 lần" vẫn có sức nặng riêng: học thuộc một chuỗi
  bất biến thì đúng là phí thật.
- `train_on_responses_only` là thực hành mặc định của Unsloth/TRL và có nền tảng
  kinh nghiệm rộng.
- Cơ chế paper đề xuất là **cân bằng hai lực**: PLW nhỏ giúp giữ trọng số
  pretrain, PLW lớn giảm overfit và **làm output dài ra**. Chữ "output dài ra"
  đáng chú ý — đó chính xác là thứ bạn đang thiếu.

**Đề xuất:** đây là **ablation đáng giá nhất** để chạy sau lần train này. Train
lại một bản với PLW ≈ 0,1 (không mask hoàn toàn) và so trên holdout. Nếu paper
đúng trong miền của bạn, bạn được cả chất lượng lẫn độ dài — đúng hai thứ đang
là bottleneck.

### 5.2. `use_rslora = False` — an toàn ở đây, nhưng đừng mang sang rank cao

Notebook tắt rsLoRA. Trong khi đó
[*A Rank Stabilization Scaling Factor for Fine-Tuning with LoRA* (Kalajdzievski, 2023)](https://arxiv.org/abs/2312.03732)
chứng minh rằng hệ số `α/r` chuẩn khiến **độ lớn gradient sụp đổ khi rank tăng**
— rank càng cao, cập nhật càng bị bóp nghẹt. Định lý 3.2 của paper nói adapter
chỉ ổn định khi hệ số scale thuộc `Θ(1/√r)`.

**Nhưng ở `r = 16` thì hiệu ứng này còn nhỏ.** Vấn đề rõ rệt ở rank cao (64, 128,
256+). Nên `use_rslora=False` với `r=16` là **hợp lý**.

Cảnh báo: nếu sau này bạn thử tăng `r` lên 64 hay 128 vì nghĩ "nhiều tham số hơn
chắc tốt hơn", mà vẫn để `use_rslora=False`, bạn sẽ thấy kết quả **không cải
thiện hoặc tệ đi** — và dễ kết luận nhầm rằng rank cao vô dụng. Đổi rank thì phải
bật rsLoRA cùng lúc.

### 5.3. `EPOCHS = 3` — bằng chứng nghiêng về ít hơn

Raschka thấy **train nhiều epoch cho instruction tuning thường làm tụt điểm**
(tăng gấp đôi số vòng trên Alpaca 50k làm giảm chất lượng).
[LIMA (Zhou et al., 2023)](https://arxiv.org/abs/2305.11206) cho thấy 1.000 mẫu
chất lượng cao là đủ để định hình format và giọng.

Chính `TRAINING_REPORT.md` của v1 khuyến nghị giảm còn 2 epoch: val loss chạm đáy
ở step 300/555, tức ~epoch 1,6.

**Vì sao vẫn nên giữ 3 ở lần này.** "Epoch 1,6" là quan sát trên **data v1**. Data
v2 có gấp ~3 lần token assistant mỗi record, tín hiệu học mỗi step khác hẳn, nên
điểm chạm đáy gần như chắc chắn dịch chỗ. Ghim cứng 2 epoch là đem số của bộ cũ
áp lên bộ mới.

Và quan trọng hơn: `EarlyStopping` + `load_best_model_at_end` **đã làm đúng việc
mà "giảm epoch" muốn làm**, nhưng làm một cách thích ứng. Cái giá của việc để 3
epoch chỉ là thời gian GPU thừa, không phải chất lượng.

### 5.4. `LR = 2e-4` — chưa từng được quét

Các nghiên cứu gần đây nhấn mạnh **learning rate là đòn bẩy lớn nhất của LoRA và
nên tinh chỉnh trước tiên**, quét trong khoảng ~[1e-5, 5e-4] và chọn giá trị cao
nhất mà vẫn ổn định.

`2e-4` là mặc định của Unsloth, không phải kết quả đo trên dữ liệu của bạn. Chính
`HYPERPARAMS_RATIONALE.md` §6 cũng đã ghi "nên sweep 1e-4…3e-4" — nhưng chưa ai
làm.

Đây là món nợ rẻ: ba lần train, chọn theo val loss.

### 5.5. Một điểm cộng ít ai nhắc

[*LoRA Learns Less and Forgets Less* (Biderman et al., TMLR 2024)](https://arxiv.org/abs/2405.09673)
thường bị trích như lời chê LoRA — vế "learns less" là thật, LoRA kém
full-finetune khi cần **nạp kiến thức mới**.

Nhưng vế sau mới hợp với bạn: **LoRA quên ít hơn full-finetune, và mức quên được
kiểm soát bởi rank.** Bạn *không* dạy kiến thức mới (kiến thức đến từ RAG), bạn
chỉ ép hành vi — nên "learns less" không phải cái giá bạn phải trả, còn "forgets
less" là thứ bạn được. Dataset còn có riêng lớp `K1_knowledge_anchor` (231 mẫu)
để giữ kiến thức nền.

Nói cách khác: với task này, LoRA `r=16` không phải là lựa chọn tiết kiệm — nó là
lựa chọn **đúng**.

---

## 6. Tóm tắt bảng tham số

| Tham số | Giá trị | Căn cứ | Mức chắc chắn |
|---|---|---|---|
| 4-bit NF4 | bật | QLoRA | Cao |
| `r` | 16 | Raschka elbow; LoRA-forgets-less | Cao |
| `lora_alpha` | 32 (=2r) | heuristic α=2r | Trung bình |
| `lora_dropout` | 0.05 | QLoRA (0.05–0.1) | Trung bình |
| target modules | cả 7 linear | QLoRA; Raschka | Cao |
| `use_rslora` | False | ổn ở r=16 | Cao *(chỉ ở rank thấp)* |
| `LR` | 2e-4 | mặc định Unsloth | **Thấp — chưa quét** |
| scheduler | cosine + warmup 0.03 | cấu hình Qwen2.5 phổ biến | Trung bình |
| `EPOCHS` | 3 + early stop | Raschka; LIMA | Cao *(nhờ early stop)* |
| effective batch | 16 | LIMA; thực tiễn | Trung bình |
| `optim` | adamw_8bit | QLoRA | Cao |
| `MAX_SEQ_LENGTH` | 3072 | đo trên data thật | Cao |
| mask loss | toàn bộ prompt | Unsloth mặc định | **Thấp — paper nói ngược** |

---

## 7. Nếu chỉ làm được một việc tiếp theo

Chạy ablation **PLW = 0,1 so với PLW = 0**, giữ nguyên mọi thứ khác.

Đó là chỗ duy nhất trong toàn bộ cấu hình mà bằng chứng học thuật **mâu thuẫn
trực tiếp** với lựa chọn hiện tại, và cũng là chỗ mà nếu paper đúng thì bạn được
đúng thứ đang thiếu: câu trả lời dài hơn và đầy đủ hơn.

Việc thứ hai, rẻ hơn: sweep LR {1e-4, 2e-4, 3e-4}.

---

## Nguồn

- [QLoRA: Efficient Finetuning of Quantized LLMs (Dettmers et al., 2023)](https://arxiv.org/abs/2305.14314)
- [A Rank Stabilization Scaling Factor for Fine-Tuning with LoRA (Kalajdzievski, 2023)](https://arxiv.org/abs/2312.03732)
- [Instruction Fine-Tuning: Does Prompt Loss Matter? (Huerta-Enochian & Ko, EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.1267/)
- [LoRA Learns Less and Forgets Less (Biderman et al., TMLR 2024)](https://arxiv.org/abs/2405.09673)
- [LIMA: Less Is More for Alignment (Zhou et al., 2023)](https://arxiv.org/abs/2305.11206)
- [Practical Tips for Finetuning LLMs Using LoRA — Raschka](https://magazine.sebastianraschka.com/p/practical-tips-for-finetuning-llms)
- [LoRA Hyperparameters Guide — Unsloth](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide)
