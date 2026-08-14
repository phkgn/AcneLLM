# Chạy lại toàn bộ eval với DeepSeek

## 0. Kiểm tra trước (2 phút, tránh mất 1 tiếng)

```powershell
cd E:\project\AcneLLM
.\.venv\Scripts\Activate.ps1

ollama serve            # cửa sổ riêng, để đó
ollama list             # phải thấy acne-intaker + acne-generator

python -m evaluation.full_evaluation --smoke --yes --out evaluation/reports/smoke_ds
```

`--smoke` = 10 mẫu/bước. Nếu smoke ra 404 model hoặc 401 key thì sửa `.env`
trước, đừng chạy tiếp.

## 1. Chạy thật

```powershell
python -m evaluation.full_evaluation --yes --retry 5 --out evaluation/reports/full_eval_ds
```

## 2. Nếu đứt giữa chừng

```powershell
python -m evaluation.full_evaluation --yes --retry 5 --out evaluation/reports/full_eval_ds
```

Đúng command đó. Ablation checkpoint từng dòng vào `rows.jsonl`, chạy lại là tiếp
chỗ dở chứ không chấm lại từ đầu. Intake có `report.json` rồi thì tự skip.

## 3. Xem kết quả

```powershell
type evaluation\reports\full_eval_ds\summary.json
python -m evaluation.runners.run_ablation --summarize --output evaluation/reports/full_eval_ds/ablation/results.json
```
