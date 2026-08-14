# AcneLLM ROLE datagen — handoff

## Kết luận

Pipeline ROLE đã chạy end-to-end bằng một entrypoint, resume append-only theo ID, chạy gate ngay trong generation loop, top-up phần thiếu, rồi đọc lại toàn output để post-validate. Smoke và hai lượt `--limit 30` đã được chạy thật; full 3.500 record **chưa được chạy** theo yêu cầu.

## Lệnh vận hành

Từ repository root:

```powershell
python -m datagen.main
```

Trên Windows có thể dùng đúng Python trong `.venv`:

```powershell
datagen\RUN.bat
```

Lệnh mặc định làm lần lượt: config/key preflight, model/completion probe, assert `thinking=disabled`, real embedding sanity, production template/SYSTEM validation, contamination index, throughput/cost estimate, resume/re-audit, async generation + inline gates, top-up, post-validation và summary.

Các flag vận hành chính:

```text
--limit N             cohort kiểm thử tối đa N record mới
--smoke               1 record/case, thêm cặp B5 và augmentation regressions
--only-case R3        chỉ một case
--concurrency N       số API call đồng thời
--no-resume           debug: sinh thêm sau ID hiện có, bỏ progress quota hiện tại
--skip-gates          debug nguy hiểm: bỏ inline content gates
--max-cost-usd N      budget guard, mặc định 25 USD
--yes                 không hỏi xác nhận khi estimate vượt ngưỡng cảnh báo
-v                    log chi tiết
```

Với `--limit N`, `limit_checkpoint.json` cố định `target_total = start_total + N`. Nếu process chết, chạy lại đúng lệnh sẽ chỉ bù tới target cũ. Khi checkpoint đã `complete`, một lần gọi `--limit N` mới mới mở cohort kế tiếp.

## Output và audit

- Train append/resume: `datagen/output/v4_role/v4_role.train.jsonl`
- Candidate bị loại: `datagen/output/v4_role/rejected.audit.jsonl`
- Summary của lượt gần nhất: `datagen/output/v4_role/generation_summary.json`
- Checkpoint bounded run: `datagen/output/v4_role/limit_checkpoint.json`
- Bằng chứng tổng hợp các lượt kiểm chứng: `datagen/output/v4_role/verification_summary.json`
- Smoke machine + human review: `datagen/output/v4_role/SMOKE_REVIEW_V2.md`
- Log: `datagen/output/v4_role/logs/datagen.log`

`datagen/output/v4_role/v4_role.smoke.jsonl` và `SMOKE_REVIEW.md` cũ không bị sửa.

## Kết quả đã kiểm chứng

1. `python -m pytest -q datagen`: **35 passed**.
2. `python -m datagen.main --smoke --yes`: **18/18** inline gate; đọc tay **18/18** chấp nhận được. Real embedder sanity **0.6643 > 0.5**.
3. `python -m datagen.main --limit 30`: từ 46 lên 76, sinh đủ 30, complete trong 211.2 giây.
4. Kill/resume cùng `--limit 30`: checkpoint cố định 76 -> 106; kill ở 82; lần chạy lại log `remaining=24`, sinh đúng 24 và kết thúc ở **106/106 unique ID**.
5. Post-validation cuối: schema errors 0, duplicate IDs 0, phrase-frequency violations 0, B5 pair pass.
6. `datagen\RUN.bat --smoke --dry-run`: wrapper tìm đúng `.venv` và in đủ 18 smoke slot.

## Throughput, chi phí và giới hạn còn lại

- Probe thực tế dao động mạnh theo provider, khoảng **1.75–14.80 giây/candidate**; probe smoke cuối là 2.33 giây/candidate. Suy tuyến tính riêng probe cho 3.500 record là khoảng **1.7–14.4 giờ**.
- Lượt `--limit 30` không ngắt đo được 211.2 giây, tương đương **7.04 giây/record được accept**, hay khoảng **6.8 giờ** nếu full giữ cùng tốc độ/reject rate. Đây là estimate thực tế hơn nhưng vẫn chưa phải benchmark full.
- Model hiện cấu hình rate 0 và các lượt kiểm chứng ghi nhận **0 USD**; đây không phải bằng chứng billing của provider. Nếu endpoint/model có giá, phải đặt `DATAGEN_INPUT_PRICE_PER_MILLION` và `DATAGEN_OUTPUT_PRICE_PER_MILLION` đúng trong `.env` để budget guard 25 USD phản ánh chi phí thật.
- Dataset 106 record còn warning R1 27.4% so với target 7.1% vì kế thừa partial R1 cũ. Dispatcher chọn case theo relative deficit nên khi chạy full sẽ ưu tiên các case thiếu; warning này không làm bounded smoke/limit fail.
- Provider từng dao động throughput và có thể trả 503; client có retry/backoff, nhưng full 3.500 vẫn cần theo dõi log và checkpoint.
