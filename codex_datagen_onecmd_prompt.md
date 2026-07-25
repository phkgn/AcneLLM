# Nhiệm vụ: Refactor datagen ROLE theo kiến trúc LLMData + một lệnh chạy full e2e

Bạn là agent tiếp nối smoke run của `datagen/` (đọc trước:
`datagen/output/v4_role/SMOKE_REVIEW.md` — 17/17 pass gate máy nhưng còn lỗi
phải sửa trước khi full).

## Mục tiêu cuối

Người dùng gõ ĐÚNG MỘT LỆNH:

```bash
python -m datagen.main
```

(kèm `datagen/RUN.bat` wrapper cho Windows gọi đúng `.venv`) → chạy full e2e
~3.500 mẫu không lỗi: preflight → generate → gates → stats → summary. Chạy lại
cùng lệnh sau khi đứt = resume tiếp, không sinh trùng, không hỏi gì thêm.

## Phần 1 — Copy kiến trúc từ `LLMData/chunk_qa/` (bắt buộc đọc code trước)

`LLMData/chunk_qa/` là pipeline datagen trưởng thành nhất repo. Refactor
`datagen/` theo ĐÚNG các pattern sau của nó:

1. **`config.py`**: dataclass `Config` + tiny `.env` loader không dependency
   (copy pattern `_load_dotenv_if_present`), mọi module khác không import os/env
   trực tiếp. Ratios taxonomy khai báo như `CASE_TYPE_RATIOS` (dict fraction,
   assert sum==1.0) + `compute_budget(total)` chia quota nguyên.
2. **Budget-aware dispatch** (`main.py::_pick_target_case_type`): route mỗi lần
   sinh vào case đang thiếu nhiều nhất so với ratio → phân phối tự cân bằng dù
   đứt giữa chừng. Bảo vệ budget bằng `asyncio.Lock` như bản gốc.
3. **Async + semaphore concurrency** với batch gather, progress log định kỳ.
4. **Resume 2 tầng**: `load_existing_ids` (dedup theo id khi ghi) +
   đếm existing theo case_type từ output để trừ vào budget (pattern
   `_count_clinical_in_output`).
5. **`writer.py`**: `DatasetWriter` context manager, append + dedup id.
6. **Gates = `rule_filter.apply_rules` pattern**: mọi gate trả
   `{passed, reasons[]}`, counter ghi `rule_reason::<r>` để summary đọc được
   vì sao reject.
7. **Top-up loop** (pattern `_safety_target_topup`): sau phase chính, đếm
   thiếu case nào → sinh bù theo batch đến khi đủ target, max_iters chống
   loop vô hạn, dừng pool khi một iter ghi được 0 mẫu.
8. **Logging** file + stdout (`data/logs/` → `datagen/output/v4_role/logs/`),
   run summary counters in cuối.
9. **CLI flags** giữ tương thích: `--limit`, `--smoke`, `--only-case R3`,
   `--concurrency`, `--no-resume`, `--skip-gates` (debug), `-v`.

Giữ nguyên taxonomy R1–R9 + B1–B5, tỉ lệ nhóm B ≈ 40% nhóm A, augmentation
~30% teencode/no_accent/typo, và toàn bộ gate đã có (knowledge-leak, grounding,
contamination, dedupe, B2/B4 rules).

## Phần 2 — Sửa 6 lỗi từ smoke (điều kiện để "không lỗi")

1. Validator xưng hô nhất quán (bắt lỗi "Cô ơi... mình" trong R2).
2. Validator code-switch: từ tiếng Anh lạc ("mostly") trong mẫu nhãn `standard`
   → reject hoặc regenerate.
3. Naturalness cho augmentation teencode/no_accent: câu phải đọc hiểu được
   ("có cần đc ko", "em da kem tron" là fail) — thêm bước LLM self-check rẻ
   hoặc rule (câu phải có động từ, cụm teencode nằm trong whitelist thực tế).
4. B5 phải sinh theo CẶP anchor: cùng docs, 2 user khác trình độ, cùng
   `anchor_group` — validator kiểm đủ cặp.
5. **Embedder hỏng**: mọi `semantic_score = 0.0` trong smoke → grounding gate
   đang chạy mù bằng lexical. Sửa để embedding cosine hoạt động thật (load đúng
   `AITeamVN/Vietnamese_Embedding` như `evaluation/metrics/grounding.py`);
   thêm assert trong preflight: một cặp câu paraphrase mẫu phải cho
   semantic_score > 0.5, không thì abort với thông báo rõ.
6. **Phrase-frequency gate toàn dataset**: cụm ≥ 8 từ xuất hiện > 5 lần trong
   toàn bộ output → reject mẫu mới (câu clarify "mụn đầu trắng, mụn mủ hay mụn
   sưng" đã lặp 3 lần ngay trong 17 mẫu smoke). Kèm diversity injection khi
   sinh: seed phrasing xoay vòng, cấm reuse nguyên văn câu hỏi lại.

## Phần 3 — Một lệnh e2e: `python -m datagen.main`

Chạy không tham số = full pipeline theo thứ tự, mỗi bước fail thì DỪNG với
thông báo tiếng Việt rõ ràng phải sửa gì (không stacktrace trần):

1. **Preflight** (fail-fast, in bảng ✓/✗):
   - `.env` có `DATAGEN_API_KEY`; gọi thử 1 completion ngắn (retry 3 lần
     backoff — TokenRouter hay 503);
   - model khả dụng, `thinking=disabled` được tôn trọng;
   - embedder load + assert semantic sanity (mục 2.5);
   - `stream_user.j2`, SYSTEM Modelfile, index contamination đọc được;
   - throughput probe: sinh thử 3 mẫu, đo giây/mẫu → in ước tính tổng thời
     gian + cost cho phần còn thiếu; nếu > 12h hoặc > budget $25 → in cảnh báo
     và câu hỏi y/n (flag `--yes` để bỏ qua hỏi).
2. **Generate** đến đủ target mọi case (budget dispatch + top-up loop).
   Retry/backoff 503 và timeout theo pattern LLMData (`max_retries`, sleep);
   record fail sau N retry → ghi `rejected.audit.jsonl`, KHÔNG crash cả run.
3. **Gates** chạy inline khi ghi (như LLMData) — reject có lý do, top-up bù
   cho đủ quota.
4. **Post-run validate**: đọc lại toàn bộ output, kiểm schema từng record,
   phân phối theo sample_kind/input_style so với taxonomy (lệch > 10% → warning),
   phrase-frequency toàn cục, đếm cặp B5.
5. **Stats + summary**: `generation_summary.json` + bảng in cuối
   (counts, cost, thời gian, reject theo lý do) + đường dẫn
   `v4_role.train.jsonl`.

`datagen/RUN.bat`: kích hoạt `.venv` rồi gọi `python -m datagen.main %*`.

## Kiểm chứng trước khi bàn giao (bạn phải tự chạy)

1. `pytest` cho gates + validators mới (viết fail trước).
2. `python -m datagen.main --smoke` (1 mẫu/case, thêm cặp B5): 100% pass gate,
   không còn 6 lỗi ở Phần 2 — đính kèm SMOKE_REVIEW mới.
3. Chạy thật `python -m datagen.main --limit 30`: xong không lỗi, giết process
   giữa chừng rồi chạy lại → resume đúng, không trùng id.
4. KHÔNG tự chạy full 3.500 — đó là lệnh của người dùng. Bàn giao khi 3 bước
   trên xanh.

## Ràng buộc

- Chỉ sửa trong `datagen/`; đọc-only với `evaluation/`, `config/`, `model/`,
  `LLMData/`.
- Key chỉ từ `.env`. Budget guard $25 mặc định (`--max-cost-usd` override).
- Không thêm dependency ngoài những gì repo/`.venv` đã có.
- Không đụng output smoke cũ; run mới ghi tiếp cùng `v4_role.train.jsonl`
  (dedup id lo phần trùng).

## Deliverable

`datagen/HANDOFF.md`: cách chạy (1 lệnh), các flag, kết quả 3 bước kiểm chứng,
ước tính thời gian + cost full theo throughput đo được, và known limitations.
