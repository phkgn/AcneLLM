# Kế hoạch — từ việc nhỏ nhất đến finetune

Bản này thay thế các bản trước. Xếp theo **chi phí tăng dần**: đo trước, sửa
miễn phí, dọn nền, rồi mới sinh data và finetune.

---

## Những gì đã biết (cơ sở của kế hoạch)

**1. `reject` không dốt như tưởng — hai bộ đề đo hai thang khác nhau.**

| Bộ đề | `reject` đúng |
|---|---|
| `intake_eval.v2` (họ hàng với tập train) | **28/30 = 93,3%** |
| `eval_set.v3` (bộ đề eval viết riêng) | **6/15 = 40%** |

`datagen/intakedata/taxonomy.yaml` coi `reject` là 3 nhóm hẹp. Bộ đề eval coi
`reject` gồm cả mụn vùng kín, hỏi cấu hình hệ thống, nhập vai. **Đây là lỗi định
nghĩa, không phải lỗi model.**

**2. Intaker đang train/serve mismatch.**

```
TRAIN : 2.132 ký tự | sha 1b08d960450af4d4
SERVE : 3.337 ký tự | sha 86b4b999a4beff14
```

Phần chênh đúng bằng khối IGA (`inflammation_level`) — thêm vào Modelfile sau khi
finetune, không sinh lại data. `anchor.py::assert_parity` canh giữa
`canonical_path` ↔ dataset, **nhưng không ai canh dataset ↔ Modelfile**.

**3. Không cần constrained decoding.** `fallback_rate = 0.0`, `failures = 0` trên
1.490 mẫu. Việc "truyền JSON Schema vào đường unified" đã **loại khỏi kế hoạch** —
`unified_intake.py:107` ghi rõ llama.cpp trả 400 với nested `anyOf-null`, và
`_OLLAMA_JSON_SCHEMA` là dạng phẳng dành cho đường legacy, sai hình dạng.

**4. Enum gần như đã khớp.** 5/6 khớp cả ba nơi. Chỉ `sex` lệch (3 vs 4), ở chỗ
không nằm trên đường chạy. Nhưng khớp là do may, không có test canh (trừ
`inflammation_level`).

**5. Ràng buộc chỗ.** SYSTEM ≈ 1.192 token / `num_ctx` 2048 → còn ~856 token cho
user + 3 turn lịch sử + JSON ra. Một enum định nghĩa đầy đủ tốn 430 token.

**6. Generator v2 đã sửa được độ dài, nhưng hỏng chỗ khác.**

| | v1 | v2 | Trần |
|---|---|---|---|
| Độ dài p50 | 377 | **1.204** | 1.509 |
| Có bullet | 0/145 | **111/145** | 102/141 |
| `answer_quality` | 2,43 | **2,81** | 3,54 |
| `incorrect_content` | 0,30 | **0,72** | 0,16 |
| `safety_fail` | 18/145 | **38/145** | 12/141 |

---

## TẦNG 0 — Đo, chưa sửa gì

Miễn phí. Vài phút. Quyết định mọi thứ phía sau.

**0.1. Chạy `run_intake` trên bộ đề eval** (hiện chỉ mới chạy trên bộ họ hàng train).

```powershell
$env:PYTHONPATH = "research;src"
python -m evaluation.runners.run_intake --eval research/evaluation/datasets/eval_set.v3.jsonl
```

Trả lời: 40% là thật, hay là artifact của cách ablation gán nhãn.

**0.2. A/B system prompt.** Chạy `run_intake` hai lần — một với Modelfile hiện tại
(3.337 ký tự), một với bản khớp train (2.132 ký tự, bỏ khối IGA).

Trả lời câu quan trọng nhất: **prompt còn kéo được model không, hay trọng số đã
đóng cứng.** Nếu bản ngắn tốt hơn → mismatch đang hại, revert là fix miễn phí.
Nếu bản dài tốt hơn → prompt vẫn có lực, Tầng 1 sẽ hiệu quả.

---

## TẦNG 1 — Sửa không đụng trọng số

Miễn phí.

**1.1. Chốt định nghĩa `reject` = 6 nhóm**, sửa **cả hai bên**:
`research/datagen/intakedata/taxonomy.yaml` và `research/evaluation/datasets/`.

| Nhóm | Nội dung |
|---|---|
| a | Ngoài chủ đề hoàn toàn |
| b | Y tế ngoài phạm vi da mụn — vùng sinh dục/hậu môn, mắt, niêm mạc, bệnh da khác, bệnh toàn thân |
| c | Xin kê đơn / chỉnh liều |
| d | Nhập vai, mượn danh chuyên môn |
| e | Hỏi nội bộ hệ thống |
| f | Nhờ chẩn đoán thay bác sĩ |

**Luật chống từ chối nhầm:** chỉ `reject` khi **toàn bộ** tin nhắn ngoài phạm vi;
có cả trong lẫn ngoài thì chọn intent theo phần trong. Luật này đã có ở
`system_prompt.v4.a.txt:8` của generator — thiếu ở intaker, nơi thực sự quyết định.

**1.2. Sửa `reject_user.j2`** — một template, hai nhánh bằng `{% if %}`:

- Nhóm a, e: chuyển hướng thẳng, không cần đồng cảm.
- Nhóm b, c, f: thừa nhận ngắn điều người hỏi lo, **chỉ đúng chuyên khoa**
  (phụ khoa/nam khoa cho vùng kín — judge đã phạt vì chỉ nói "da liễu"), mời quay lại.

**Không ép số câu.** Dùng "ngắn gọn, đi thẳng vào việc". Lý do: `orchestrator.py`
đã ghi bài học — mệnh lệnh cứng về hình thức bị model phá và không bắt được.

**1.3. Revert Modelfile về bản khớp train** — nếu 0.2 cho thấy nên.

---

## TẦNG 2 — Dọn nền, không đổi hành vi

Miễn phí. Làm để lần sau không trôi lại.

**2.1. `src/acne_llm/schemas/enums.py`** — nguồn sự thật duy nhất cho 6 enum.
Sinh ra 3 dạng: `Literal` (pydantic), `frozenset` (validate), khối text (Modelfile).
Nguyên mẫu đã có: `severity.py::MODELFILE_ANCHOR`.

Phân tầng độ chi tiết theo ngân sách token:

| Enum | Mức |
|---|---|
| `intent`, `inflammation_level` | định nghĩa đầy đủ + ví dụ |
| `lesion_types`, `skin_type`, `lesion_distribution` | 1–2 dòng luật phân biệt giá trị dễ lẫn |
| `sex` | chỉ liệt kê |

**2.2. Test canh trôi cho cả 6**, hai chiều:
`enums.py` ↔ Modelfile, và `enums.py` ↔ `datagen/intakedata/schema.py`.
Đây là lỗ hổng đã gây ra mismatch hiện tại.

**2.3. Dọn schema:**

| Việc | Lý do |
|---|---|
| `sex` → 3 giá trị | bỏ `unknown` khỏi `ClinicalDemographics` |
| Xoá `Severity` (`clinical.py:14`) | 0 caller, thiếu bậc `none` — bẫy import nhầm |
| Xoá `VisionOutput`, `VisionLesion` | `vision/` đã xoá; `VisionLesion.type` là thang 7 đối chọi thang 11 |
| Gộp `NormalizedAcneCase` → `AcneClinicalInput` | sửa 5 file `research/LLMData/`; `distribution`→`lesion_distribution`, `red_flags`→`red_flags_input` |

**2.4. `num_ctx` 2048 → 4096** nếu Tầng 2.1 cần thêm chỗ.

---

## TẦNG 3 — Sinh lại dữ liệu

Tốn ít credit. Chỉ khi Tầng 0–1 chưa đủ.

**3.1. Sinh lại `intake` data từ `enums.py`.** Sửa luôn lỗi cấu trúc mà
`_intent_patch.py` đã ghi: **200 dòng multi-turn thì cả 200 đều nhãn `clarify`**,
vì `taxonomy.yaml` chỉ có một case type sinh lịch sử. Cho multi-turn mang đủ 4 nhãn.

**3.2. Đắp mẫu cho generator** — `R6_role_boundary` (173) và `R8_meta_jailbreak`
(126) đang mỏng so với `R2` (429). Nhắm ~150–200 mẫu, không cần đủ 3.500.

Đây là gốc của `safety_fail` 38/145: dataset dạy *giúp* nhiều hơn dạy *dừng*.

---

## TẦNG 4 — Finetune

**4.1. Intaker (3B)** — rẻ, data 4.000 dòng. Sau khi làm 3.1 thì train/serve khớp
byte trở lại, và **xoá được `_intent_patch.py`** (điều kiện xoá đã ghi trong
docstring của nó).

**4.2. Generator v3 (7B)** — chỉ sau khi có 3.2. Mục tiêu: giữ độ dài và cấu trúc
của v2, kéo `incorrect_content` từ 0,72 về gần 0,30 và `safety_fail` từ 26% xuống.

---

## TẦNG 5 — Đo lại

**5.1. `run_intake`** — miễn phí, sau mỗi lần đụng intaker.

**5.2. `run_ablation --arms RRR --limit 145`** — ~$0,5, so trực tiếp với bảng v1/v2.

**5.3. Bộ hồi quy an toàn** — 25 câu vi phạm thật đã có sẵn trong
`v2_round2/rows.jsonl`. Lưu thành `safety_regression.jsonl`, chạy trước mỗi lần
train. Rẻ hơn 145 câu, bắt đúng thứ cần bắt.

---

## Tóm tắt một dòng mỗi tầng

| Tầng | Việc | Chi phí | Trả lời câu gì |
|---|---|---|---|
| 0 | Đo intake trên bộ eval + A/B prompt | 0 | Prompt còn kéo được model không? |
| 1 | Thống nhất định nghĩa `reject`, sửa template | 0 | Sửa định nghĩa có đủ không? |
| 2 | `enums.py` + test canh trôi + dọn schema | 0 | — (phòng ngừa) |
| 3 | Sinh lại intake data + đắp R6/R8 | thấp | — |
| 4 | Finetune intaker, rồi generator v3 | cao | — |
| 5 | Đo lại | ~$0,5 | Có tốt lên thật không? |
