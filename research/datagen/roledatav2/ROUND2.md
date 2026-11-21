# ⚠ ĐỌC TRƯỚC — model đang phục vụ có thể chưa từng nhận system prompt

`ollama show acne-generator --modelfile` (16/08/2026) cho ra:

```
TEMPLATE {{ .Prompt }}
```

Template này **không tham chiếu `.System`** và **không phát tag `<|im_start|>` nào**.
Cộng với `AppConfig.llm_use_modelfile_system = True` (mặc định) — tức app CỐ Ý
không gửi system message qua API mà trông cậy vào Modelfile — thì chuỗi thành:

> app không gửi system → template không render system → **model chưa bao giờ nhận
> system prompt**, và nhận prompt ở dạng thô, không có chat format mà nó được
> finetune trên đó.

Model được tạo từ `model/generator/Modelfile.full` (đối chiếu từng dòng SYSTEM đã
khớp; file này **không có** khối `TEMPLATE`, khác `model/legacy/Modelfile` vốn có
template Qwen đầy đủ). Ghi chú `GENERATOR_ROOT_CAUSE.md` §A1 nói bản phục vụ là
`722281f0` — sai: bản thật là `36b70b7a`, lệch đúng một dòng ("bằng ngôn ngữ khác"
thay cho "bằng tiếng Anh hay tiếng Trung").

Nếu đúng vậy thì **mọi số trong `run_full_v3_2` đều bị nhiễu**: arm RRO dùng
`gpt-5.6-terra` qua API và CÓ nhận system prompt, còn arm RRR thì không. `+1.04`
không phải "model mạnh hơn" mà là "model mạnh hơn VÀ có system prompt".

## Kiểm dứt điểm trước khi làm bất cứ gì khác (~10 phút, không tốn API)

```powershell
cd model\legacy
ollama create acne-generator-templated -f Modelfile   # bản CÓ TEMPLATE Qwen
ollama show acne-generator-templated --modelfile | Select-String "TEMPLATE" -Context 0,6

# so cùng một câu hỏi trên hai model
$q = "Da em dầu, mụn ở trán và hai bên má, bị ba tháng rồi, em nên làm gì?"
ollama run acne-generator            $q > old.txt
ollama run acne-generator-templated  $q > new.txt
(Get-Content old.txt -Raw).Length; (Get-Content new.txt -Raw).Length
```

Nếu bản có template dài hơn hẳn và có gạch đầu dòng, thì nút thắt là **serving
config**, không phải data — và sửa nó rẻ hơn toàn bộ vòng 2 này cộng lại. Vòng 2
vẫn đáng làm, nhưng thứ tự ưu tiên đảo ngược.

---

# roledatav2 — vòng 2

Vòng 1 sinh 2.763/3.500 mẫu bằng anchor `722281f0` (`model/legacy/Modelfile`).
Vòng 2 đổi anchor, đổi quota, bỏ judge, thêm hai gate. Mọi thay đổi đều truy
ngược được về một con số trong `research/evaluation/reports/run_full_v3_2/`.

## Đổi những gì, vì sao

| # | Thay đổi | Căn cứ |
|---|---|---|
| 1 | Anchor v4 (`model/generator/Modelfile`, sha `5421f207`) | `GENERATOR_ROOT_CAUSE.md`: anchor cũ gây 28% mở bằng câu đồng cảm, 22% đóng bằng disclaimer, 29% kết bằng câu hỏi — trên ngân sách chỉ 377 ký tự. Không có một chữ nào về độ dài/cấu trúc ⇒ 0/145 câu có gạch đầu dòng. |
| 2 | 3 biến thể anchor, rải theo lịch | Cả 48.705 dòng SFT cũ **và** 2.763 mẫu vòng 1 đều chỉ có 1 system prompt. Model học chuỗi, không học luật (nghi phạm A1). |
| 3 | Quota nhóm cần tài liệu 1.570 → 660 | `RRR−RNR = 0.000`, `RRO−RNO = −0.16`, `ROR−RRR = +0.25` với groundedness tụt −0.45. Vấn đề ở nội dung KB, không ở chỗ model biết đọc tài liệu. |
| 4 | Xoá `judge_knowledge` | 1043 điểm 5 / 2 điểm 4 / 0 điểm ≤3 trên 1.045 mẫu; `knowledge_accuracy` 491/491 đều 5. Judge dùng chính model vừa sinh câu trả lời để chấm nó. |
| 5 | Gate `entities_grounded` | Bắt 192/1.264 mẫu bịa tên thuốc/số mà judge cho 5/5. |
| 6 | Gate `user_facts_echoed` | Không gate nào kiểm câu trả lời có dùng dữ kiện người dùng hay không — đó chính là `missing_content` 2.24/3. |
| 7 | Lịch mở bài 6 kiểu | 676/2.763 mẫu mở đầu bằng đúng 5 cụm. `random.choice` + chỉ dẫn phủ định không có tác dụng. |
| 8 | Split theo nguồn | 9/40 cặp B5 bị tách qua train/val, cùng chunk nguồn ⇒ val cho điểm ảo. |

## Hệ quả đo được (chưa tốn API)

- Nguồn cho case B*/K1: **100% tầng guideline** (NICE 142 + AAD 173 + textbook 345).
  Vòng 1 có 53% là `pubmed_review` vì 776 chunk guideline không đủ cho 1.320 mẫu.
- Chạy gate mới trên data vòng 1: `entities_grounded` loại 192/1.264 (15%),
  `user_facts_echoed` loại 60/1.226 (5%).
- Split lại data vòng 1: cặp B5 bị tách 9/40 → **0/40**, source rò rỉ 11 → **0**.
- Tiết kiệm ~1.755 lời gọi judge mỗi lần chạy full.

## Chạy — hai phase

Phase 1 sinh SƯỜN (lời người dùng + ý mong đợi), phase 2 sinh CÂU TRẢ LỜI. Phải
chạy phase 1 trước; phase 2 thiếu sườn thì dừng ngay kèm lệnh cần chạy.

Lý do tách: ở bản một-phase, `points` và `assistant` do CÙNG một lời gọi sinh ra
nên `points_covered` chỉ chứng minh model tự nhất quán với chính nó — đúng lỗi
self-preference đã giết `judge_knowledge` (1043 điểm 5 trên 1.045 mẫu). Tách đôi
thì `points` là ràng buộc từ bên ngoài. Kèm theo: khử trùng lặp làm trên câu hỏi
TRƯỚC khi tiêu tiền sinh đáp án, câu trả lời hỏng chỉ sinh lại câu trả lời, và bộ
sườn đông lạnh cho phép so hai teacher theo cặp trên cùng đề bài.

```bash
cd research

# 1. smoke: 16 sườn + 16 đáp án, một mẫu mỗi case
python -m datagen.roledatav2.phase1   --smoke --yes
python -m datagen.roledatav2.pipeline --smoke --yes

# 2. thử có giới hạn, cả hai phase đều resume được
python -m datagen.roledatav2.phase1   --limit 200 --yes
python -m datagen.roledatav2.pipeline --limit 200 --yes

# 3. full 3.500
python -m datagen.roledatav2.phase1   --yes
python -m datagen.roledatav2.pipeline --yes

# 4. split + export
python -m datagen.roledatav2.finalize
```

`output/skeletons.jsonl` là artifact giữa hai phase — giữ lại, đừng xoá cùng
`roledata.train.jsonl` khi muốn sinh lại đáp án bằng teacher khác.

Xoá output vòng 1 trước khi chạy, hoặc `--no-resume`: dữ liệu cũ mang anchor
`722281f0`, trộn với anchor mới là quay lại đúng lỗi train/serve mismatch.

## ⚠ Trước khi phục vụ model mới

Anchor đổi thì **phải** `ollama create` lại, nếu không thì train một đằng serve
một nẻo — đúng lỗi đã giết bản cũ:

```bash
ollama create acne-generator -f model/generator/Modelfile
```

Hai chỗ trong repo còn trỏ vào đường cũ, cần sửa khi chốt vòng 2:

- `research/evaluation/runners/run_ablation.py:86` → `model/system_prompt.canonical.txt`
  (đường này không tồn tại; bản dùng thật nằm ở `model/generator/prompts/system_prompt.v4.a.txt`)
- `datagen/roledata/tests/test_anchor.py` đang đỏ vì tìm `model/Modelfile` — lỗi
  có từ trước vòng 2, không phải do thay đổi này.

## Còn nợ

- **B3 vẫn dùng một đoạn nhiễu duy nhất** (`synthetic-distractor-weather`, 138/138
  mẫu vòng 1). Nhiễu về thời tiết thì model nào cũng bỏ qua được. Nên đổi sang
  bốc ngẫu nhiên một chunk khác chủ đề — nhiễu gần chủ đề mới khó.
- **Chưa kiểm KB có nội dung không.** `ROR−RNO` nói ngay cả chunk vàng cũng không
  đẩy được `answer_quality`. Đọc tay 30 chunk vàng của arm ROR trước khi quyết
  định có nên tăng lại quota B*/K1.
- **Chưa có calibration người–judge.** Mọi mức tuyệt đối (2.43/5, 87.6% safety)
  chưa biết là model dở hay judge khắt.
