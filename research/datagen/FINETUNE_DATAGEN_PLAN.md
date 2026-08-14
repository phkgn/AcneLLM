# Plan — Module sinh data finetune (`datagen/`)

> Mục tiêu: đưa `datagen/` tới trạng thái xuất ra **một dataset finetune sẵn sàng train LoRA**, dùng đúng anchor canonical v3 (`model/Modelfile`), khớp train/serve, đủ coverage theo `dataset_design_role_acne_llm.md`.

---

## 0. TL;DR

Module **đã tồn tại và trưởng thành** (pipeline `v4_role`: one-command, resume, inline gates, top-up, post-validate, 35 pytest pass). **Không cần viết lại.** Việc còn lại là *hoàn thiện + vá lệch anchor + bổ sung 2 khâu thiếu (knowledge-anchor và export)* rồi chạy full. Đây là plan để review, chưa động code.

---

## 1. Hiện trạng (inventory)

**Kiến trúc đang chạy** (`python -m datagen.main`):

```
config.py (single source config, đọc .env)
   └─ role_taxonomy.yaml   → 14 case type, quota, gate, augmentation 30%
   └─ role_style_guide.md  → hướng dẫn giọng cho generator
   └─ model/V2/Q4/Modelfile → extract_production_system() lấy SYSTEM anchor
main.py  (orchestrator: preflight → probe → generate → gates → top-up → post-validate → summary)
   ├─ generator.py  → build prompt (style guide + SYSTEM production) + gọi API async
   ├─ gates.py      → inline content gates (grounded rate, knowledge-leak, phrase-freq…)
   └─ writer.py     → JSONL append-only, dedup theo id, resume
output/v4_role/v4_role.train.jsonl  (record schema giàu: messages + metadata gate)
```

**Đã kiểm chứng (HANDOFF.md):** smoke 18/18, `--limit 30` chạy đủ, kill/resume OK, post-validate schema/dup/phrase = 0 lỗi.

**Taxonomy hiện tại** (tổng 3.500):

| Nhóm | Case | Quota | Vai trò |
|---|---|---:|---|
| R1 | identity | 250 | Danh tính, năng lực, giới hạn |
| R2 | depth_adaptation | 450 | Điều chỉnh độ sâu theo đối tượng |
| R3 | nonjudgment | 350 | Không phán xét |
| R4 | measured_empathy | 300 | Đồng cảm vừa đủ |
| R5 | natural_clarification | 300 | Hỏi lại khi mơ hồ |
| R6 | role_boundary | 250 | Từ chối kê đơn/chẩn đoán |
| R7 | conversation_glue | 200 | Chào/cảm ơn/lan man |
| R8 | meta_jailbreak | 150 | Giữ vai trước DAN/meta |
| R9 | multiturn | 250 | Hội thoại 4–6 lượt |
| B1 | grounded_role | 500 | Trả lời từ tài liệu + role |
| B2 | missing_answer | 200 | Abstain khi tài liệu thiếu |
| B3 | irrelevant_chunk | 150 | Bỏ nguồn nhiễu |
| B4 | conflicting_docs | 80 | Nêu 2 nguồn mâu thuẫn |
| B5 | depth_anchor | 70 | Cùng tài liệu, đổi độ sâu |

**Parity đã được wire sẵn** (điểm mạnh): `generator.py` nhét chính `production_system` (SYSTEM lấy từ Modelfile) vào field `system` của mỗi record, và `validate_record()` kiểm từng record theo production_system → train == serve là *thiết kế có chủ đích*, không phải may rủi.

---

## 2. Gap phải xử lý (khác biệt so với yêu cầu hiện tại)

### G1 — Lệch anchor (CHẶN, ưu tiên cao nhất)
303 record đã sinh mang **system prompt cũ** (thiếu mục "Ưu tiên hệ thống", "Người dùng", tone đã vá). Sau khi Modelfile đổi sang canonical v3, dataset cũ **không còn khớp anchor serve**.
→ Xử lý: **wipe `output/v4_role/` và sinh lại full bằng anchor v3** (data mới nên regen sạch hơn là vá từng dòng; 303 record là nhỏ, chưa tốn gì).

### G2 — Nguồn anchor chưa trỏ về "prompt chính"
`config.model_file_path` đang trỏ `model/V2/Q4/Modelfile`, nhưng bạn vừa chốt **`model/Modelfile`** là prompt chính. Hai file hiện đều là v3, nhưng để tránh drift về sau phải **một nguồn duy nhất**.
→ Xử lý: trỏ `config.model_file_path` về `model/Modelfile` (hoặc để cả hai Modelfile đọc chung `model/system_prompt.canonical.txt`), thêm test khẳng định SYSTEM ≡ canonical.

### G3 — Thiếu lớp Knowledge-Anchor (chống forgetting)
Taxonomy hiện chỉ có role (R*) + grounded (B*). Không có lớp "trả lời kiến thức mụn ĐÚNG như base model" — chính là lá chắn chống quên trong `dataset_design`. Rủi ro cao khi finetune trên Q4.
→ Xử lý (chọn 1, xem §5 Quyết định):
  - (a) Thêm case type `K1_knowledge_anchor` (~15–22% tổng, chiếm chỗ bằng cách giảm bớt B-series), HOẶC
  - (b) Không đưa vào train, chỉ đo retention ở eval sau train (rẻ hơn nhưng không "phòng" được).

### G4 — Thiếu khâu split + export sang định dạng trainer
Pipeline dừng ở `v4_role.train.jsonl` (một file gộp). Chưa thấy: chia train/val/holdout, và convert sang format LoRA trainer (Axolotl/LLaMA-Factory/Unsloth).
→ Xử lý: thêm module `finalize/` (xem §3).

### G5 — Full 3.500 chưa chạy
Mới verify tới `--limit 30`. Cần một lần chạy full có giám sát (throughput 1.7–14 giờ, budget guard 25 USD).

---

## 3. Kiến trúc module mục tiêu (sau khi vá)

Giữ nguyên lõi, **thêm 2 khối** (in đậm):

```
config.py ──────────────► đọc .env, anchor = model/Modelfile (canonical v3)
   │
role_taxonomy.yaml ─────► + K1_knowledge_anchor (nếu chọn 3a)
role_style_guide.md
   │
main.py (orchestrator, không đổi luồng)
   ├─ generator.py   sinh candidate, system = anchor v3 (parity)
   ├─ gates.py       inline gates: schema, VN-only, grounded_rate, knowledge-leak,
   │                 phrase-freq, refusal-present (R6/R8), abstain-rule (B2), conflict (B4)
   ├─ writer.py      append-only, dedup, resume
   │
   ├─ **finalize/split.py**    ← MỚI: chia train/val/holdout theo case, seed cố định,
   │                             holdout R8+B2+B4 (đối kháng/safety) KHÔNG vào train
   └─ **finalize/export.py**   ← MỚI: convert JSONL → format trainer (chatml/sharegpt),
                                 verify system ≡ canonical, sinh dataset_card.md + checksum
   │
output/v4_role/
   ├─ v4_role.train.jsonl        (raw accepted)
   ├─ **splits/{train,val,holdout}.jsonl**
   ├─ **export/acnellm_lora.{jsonl|parquet}**
   ├─ **dataset_card.md**        (thống kê phân bổ, anchor hash, coverage matrix)
   └─ rejected.audit.jsonl / generation_summary.json / logs/
```

**Record schema** (đã có, giữ): `id, sample_kind, input_style, synthetic_context, knowledge_leak_check, grounded_sentence_rate, anchor_group, messages[system,user,assistant], gate_results`. Export chỉ giữ `messages` (+ `id` để trace), bỏ metadata gate.

---

## 4. Prompt-coverage matrix (cầu nối anchor ↔ data)

Mỗi luật trong anchor v3 phải có case type gánh + số mẫu tối thiểu. Đây là thứ đảm bảo "prompt được nội hoá", không chỉ đọc suông:

| Luật trong SYSTEM v3 | Case gánh | Đủ chưa? |
|---|---|---|
| Ưu tiên hệ thống / chống jailbreak | R8 (150) | ✅ |
| Phạm vi + từ chối out-of-scope | R6, R7 | ✅ |
| Người dùng (điều chỉnh độ khó) | R2, B5 | ✅ |
| An toàn: không kê đơn/chẩn đoán | R6 | ✅ |
| Special population (thai kỳ, sơ sinh, <12) | **— chưa có case riêng** | ⚠️ thiếu |
| Grounding / không bịa nguồn | B1, B3 | ✅ |
| Abstain khi thiếu tài liệu | B2 | ✅ |
| Mâu thuẫn nguồn | B4 | ✅ |
| Hỏi lại khi thiếu dữ kiện | R5 | ✅ |
| Tone đồng cảm không phán xét | R3, R4 | ✅ |
| Kiến thức mụn đúng (anti-forgetting) | **— chưa có (G3)** | ⚠️ thiếu |

→ **Hai ô ⚠️**: special-population và knowledge-anchor. Cân nhắc thêm case `R10_special_population` (~120) và `K1_knowledge_anchor` (~500), bù bằng cách hạ nhẹ quota B1/R2.

---

## 5. Quyết định cần bạn chốt trước khi làm

1. **Knowledge-anchor (G3):** thêm hẳn case `K1` vào train (phòng forgetting, khuyến nghị) hay chỉ đo ở eval?
2. **Special-population (§4):** thêm case `R10` riêng hay để rải trong R2/R6?
3. **Nguồn anchor (G2):** trỏ config về `model/Modelfile`, hay để cả hai Modelfile đọc chung `system_prompt.canonical.txt`?
4. **Format trainer đích (G4):** Axolotl / LLaMA-Factory / Unsloth — cái nào? (quyết định schema export).
5. **Regen (G1):** đồng ý wipe `output/v4_role/` sinh lại full bằng v3?

---

## 6. Lộ trình thực thi (sau khi chốt §5)

**Phase 1 — Vá anchor & config (nhanh, chặn mọi thứ sau)**
- Trỏ `config.model_file_path` về nguồn canonical đã chốt.
- Thêm test: `extract_production_system(cfg)` ≡ `system_prompt.canonical.txt` (byte-identical).
- Wipe `output/v4_role/`.

**Phase 2 — Cập nhật taxonomy (nếu chọn 5.1/5.2)**
- Thêm `K1_knowledge_anchor`, `R10_special_population` vào `role_taxonomy.yaml` + `config.CASE_TYPE_TARGETS`, cân lại quota về tổng 3.500.
- Viết template sinh cho case mới; thêm gate tương ứng (K1: đối chiếu độ chính xác; R10: có khuyến nghị khám đúng).

**Phase 3 — Bổ sung finalize/ (G4)**
- `split.py`: train/val/holdout, seed cố định, holdout R8+B2+B4.
- `export.py`: convert sang format trainer + `dataset_card.md` + checksum + verify system≡anchor.
- Unit test cho cả hai.

**Phase 4 — Chạy full có giám sát (G5)**
- `python -m datagen.main` full 3.500, theo dõi log/checkpoint, budget guard.
- Post-validate: schema 0 lỗi, dup 0, phrase-freq 0, coverage khớp §4.

**Phase 5 — Bàn giao dataset**
- Xuất `export/` + `dataset_card.md`; chạy `datagen` pytest xanh; sẵn sàng đưa sang bước train LoRA (config đã có trong `dataset_design_role_acne_llm.md`).

---

## 7. Rủi ro & chốt chặn

- **Parity là bất biến số 1:** mọi record `system` phải ≡ anchor; thêm test tự động, không tin tay.
- **Q4 + forgetting:** nếu bỏ K1, bắt buộc phải có eval retention (base vs finetuned) làm cổng release.
- **Augmentation (teencode/typo 30%):** chỉ biến đổi phía *user*; câu trả lời phải giữ tiếng Việt chuẩn (taxonomy đã quy định — giữ nguyên).
- **Holdout không rò vào train:** R8/B2/B4 holdout tách trước khi export.

---

*Plan để review — chưa sửa code. Chốt §5 xong mình bắt đầu Phase 1.*
