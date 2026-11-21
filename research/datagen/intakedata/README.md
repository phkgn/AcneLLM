# Unified Intake datagen

Module độc lập sinh SFT chat records cho model **Unified Intake** (extract + intent route trong
1 call). Mọi record dùng `system_prompt.canonical.txt` byte-identical, assistant trả JSON
`{intent, confidence, description, context, clinical}`, được gate (schema + enum + negation-leak +
empty-discipline) trước khi ghi append-only.

Thiết kế & hành vi: xem `PLAN.md` và `../UNIFIED_INTAKE_DATAGEN_SPEC.md`.

## Cấu hình

Đặt trong `.env` ở root repo (không ghi key vào code hoặc log):

```dotenv
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
# tùy chọn:
INTAKEDATA_CONCURRENCY=6            # số call song song (mặc định 6)
INTAKEDATA_MAX_OUTPUT_TOKENS=1600   # trần token/record (mặc định 1600)
```

## Lệnh & các mode

Phải chọn đúng một mode; **không truyền mode thì không sinh gì**.

```powershell
pytest -q datagen/intakedata                                  # offline, không tốn phí
python -m datagen.intakedata.pipeline --smoke --yes -v        # 1 record/case (16 call provider)
python -m datagen.intakedata.pipeline --limit 8 --yes -v      # corpus giới hạn 8 record
python -m datagen.intakedata.pipeline --full --yes -v         # gen đủ 4.000 (bước cuối, tốn phí)
```

Cờ bổ sung:
- `--yes` — xác nhận cho phép gọi provider (bắt buộc với mọi mode có sinh).
- `--no-seed` — bỏ bước relabel golden, sinh mới hoàn toàn.
- `--concurrency N` — ghi đè số call song song.
- `-v` — log DEBUG realtime.

Ghi chú chi phí: `--smoke` gọi provider **16 lần** (mỗi case_type 1 record) — vẫn tốn phí. `--full`
tốn nhất. Chỉ chạy `--full` sau khi đã xem smoke đạt. `--limit N` relabel golden trước rồi chỉ
top-up phần thiếu nên rẻ hơn gen mới cùng số lượng.

## Output

Tất cả nằm trong `datagen/intakedata/output/`:

| Mode | File dữ liệu |
|---|---|
| `--smoke` | `output/intake/intake.smoke.jsonl` |
| `--limit N` | `output/intake/intake.limit-N.jsonl` |
| `--full` | `output/intake/intake.records.jsonl` → split thành `intake.train.jsonl` (~90%) + `intake.val.jsonl` (~10%) |

Kèm theo mỗi lần chạy:
- `output/intake/summary.json` — đếm theo case_type + intent + lý do reject, đường dẫn train/val.
- `output/intake/audit.jsonl` — accept/reject từng record.
- `output/logs/intake.log` — log realtime (song song stdout).

Pipeline có **resume + dedup**: chạy lại cùng mode sau gián đoạn sẽ tiếp tục, không sinh trùng.
Split tự loại record trùng với eval `data/intent_classify.test.jsonl` (chống rò eval → train).

## Sau khi gen (next steps)

1. Kiểm `summary.json`: mỗi case_type đạt ≥90% quota, reject reasons hợp lý, `negation_leak = 0`.
2. Build **eval gold gán tay ~500** (SPEC §7) — tách hoàn toàn, KHÔNG judge-only.
3. Finetune LoRA Qwen 2.5 3B Q4 trên `intake.train.jsonl` (rank 16–32, 2–3 epoch), val = `intake.val.jsonl`.
4. Bật constrained decoding lúc serve (JSON schema từ `schema.py`) + giữ rule-based làm fallback.
