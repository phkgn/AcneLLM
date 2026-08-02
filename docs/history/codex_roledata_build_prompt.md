# Nhiệm vụ Codex: Build module `datagen/roledata/` theo PLAN, CHỈ chạy test — KHÔNG chạy gen full

Bạn là agent thực thi. Xây dựng module sinh data finetune mới trong `datagen/roledata/`.
**Đọc trước, bắt buộc:** `datagen/roledata/PLAN.md` (plan cuối, implement-ready) và
`model/system_prompt.canonical.txt` (anchor v3). Làm ĐÚNG theo PLAN, không tự đổi thiết kế.

---

## Ràng buộc cứng (đọc kỹ, vi phạm = fail)

1. **KHÔNG chạy gen full.** Tuyệt đối không chạy sinh 3.500 mẫu. Chỉ được chạy:
   - `pytest -q datagen/roledata`
   - `python -m datagen.roledata.pipeline --smoke --yes -v` (1 record/case)
   - tối đa `python -m datagen.roledata.pipeline --limit 8 --yes -v` để chứng minh wiring.
   Không gọi lệnh full, không bỏ `--limit`, không tăng limit quá 8.
2. **Provider = OpenAI, đọc từ `.env`.** Dùng `OPENAI_API_KEY`. Thêm hỗ trợ
   `OPENAI_BASE_URL` (default `https://api.openai.com/v1`) và `OPENAI_MODEL`
   (default `gpt-4o-mini`). **Không hardcode** key/model trong code — chỉ đọc env
   qua `config.py`. Nếu thiếu `OPENAI_API_KEY` → `config.validate()` báo lỗi rõ ràng
   và preflight dừng, không crash mơ hồ.
3. **Log hiện trên CLI.** Logging phải stream ra stdout (StreamHandler) SONG SONG với
   ghi file `output/logs/roledata.log`. Trong lúc generate phải in progress mỗi
   `progress_every` record: case đang sinh, đã accept / mục tiêu, số reject, thời gian.
   Mục tiêu: khi người dùng chạy gen all sau này, họ **nhìn log chạy realtime trên CLI**.
   Chứng minh điều này ngay ở `--smoke` (log phải thấy trên console, không im lặng).
4. **Không đụng** `datagen/main.py`, `datagen/generator.py`, `datagen/gates.py`,
   `datagen/output/v4_role/`, hay bất kỳ file nào ngoài `datagen/roledata/`.
   Không import lại code cũ — viết mới sạch trong `roledata/`.
5. **Parity là bất biến số 1.** Implement đủ parity 3 tầng (PLAN §8):
   preflight `anchor.assert_parity()`, per-record gate `system_parity`, verify ở export.
   `system` mỗi record phải byte-identical với anchor.

---

## Việc cần làm (theo Phase trong PLAN, dừng trước full run)

### Phase 0 — Scaffold
- `datagen/roledata/__init__.py`, `config.py`, `anchor.py`, `taxonomy.yaml`, `style_guide.md`.
- `config.py`: dataclass `Config` + tiny `.env` loader (không thêm dependency), đọc
  `OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL`, `FULL_TARGET=3500`,
  `CASE_TYPE_TARGETS` (bảng PLAN §6, Σ=3500), `compute_budget()` largest-remainder,
  `validate()`.
- `anchor.py`: `load_anchor(cfg)` (regex `SYSTEM """..."""` từ `model/Modelfile`),
  `assert_parity(cfg)` so byte-identical với `model/system_prompt.canonical.txt`.
- Test: `tests/test_budget.py` (Σ quota == 3500), `tests/test_anchor.py` (parity + fail khi lệch).

### Phase 1 — Core generation
- `writer.py` (append-only JSONL, dedup theo `id`, resume), `generator.py`
  (async OpenAI client, retry/backoff, build prompt từ template + style guide,
  `to_record()` nhét anchor vào `messages[0]`), `gates.py` (validators PLAN §9),
  `pipeline.py` (orchestrator + CLI flags PLAN §12, logging CLI+file).
- `tests/test_gates.py`: mỗi gate pass/fail đúng trên ví dụ dựng sẵn (offline, không gọi API).

### Phase 2 — Case mới
- Template `prompts/*.j2` cho đủ 16 case, đặc biệt `R10_special_population.j2` và
  `K1_knowledge_anchor.j2`. K1 grounded trên tài liệu mụn repo (`LLMData/chunk_qa`);
  gate `knowledge_accuracy` (LLM-judge) + `grounded_rate>=0.8`.

### Phase 3 — Finalize
- `finalize/split.py` (train/val/holdout 85/8/7, seed=42, holdout chứa R8+B2+B4,
  0 leakage), `finalize/export.py` (format LLaMA-Factory + `dataset_card.md` +
  `checksum.sha256`, verify parity).
- `tests/test_split.py` (dedup id chéo 3 tập), `tests/test_export.py` (schema + parity + checksum).
  Cho phép test dùng fixture JSONL nhỏ dựng sẵn — KHÔNG cần gen thật.

---

## Cách nghiệm thu (chạy đúng các lệnh này, không hơn)

```bash
# 1. unit test toàn bộ (không gọi API)
python -m pytest -q datagen/roledata

# 2. smoke — chứng minh wiring + log realtime + parity (gọi OpenAI, 16 record)
python -m datagen.roledata.pipeline --smoke --yes -v

# 3. limit nhỏ — chứng minh resume + budget guard (tối đa 8)
python -m datagen.roledata.pipeline --limit 8 --yes -v
```

Sau đó **DỪNG**. Không chạy full, không chạy split/export trên data thật (test đã phủ bằng fixture).

---

## Definition of Done (báo cáo lại từng mục)

- [ ] `pytest -q datagen/roledata` toàn xanh — dán số passed.
- [ ] `--smoke` sinh 16/16 case, **log hiện realtime trên CLI** (dán ~10 dòng log mẫu).
- [ ] Parity verify: in ra SHA-256 của anchor và xác nhận mọi record smoke `system` khớp.
- [ ] `--limit 8` chạy được, kill/chạy lại resume đúng (không sinh trùng id).
- [ ] `config.validate()` báo lỗi rõ khi thiếu `OPENAI_API_KEY` (thử tạm unset để chứng minh).
- [ ] Xác nhận KHÔNG có lệnh full nào được chạy; KHÔNG file nào ngoài `datagen/roledata/` bị sửa.

---

## Những điều CẤM
- Cấm chạy gen full 3.500 (dù ngầm qua top-up không giới hạn).
- Cấm hardcode API key/model; cấm in giá trị key ra log.
- Cấm sửa/xoá `output/v4_role/` và code `datagen/` cũ.
- Cấm nới `--limit` > 8 hoặc bỏ `--yes` để tránh vòng hỏi.
- Cấm để logging chỉ ghi file mà không hiện CLI.

Khi xong, tóm tắt: file đã tạo, kết quả 3 lệnh nghiệm thu, và mẫu log CLI để người dùng thấy.
