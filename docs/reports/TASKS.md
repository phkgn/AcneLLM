# Danh sách việc — đưa project về 100%

Cập nhật 2026-08-19. Đánh dấu `[x]` khi xong.

Xếp theo **phụ thuộc**: việc sau cần việc trước. Trong mỗi nhóm xếp theo chi phí.

---

## NHÓM 1 — Dữ liệu cho báo cáo

Đây là nhóm duy nhất **chặn khoá luận**. Ba nhóm còn lại chỉ chặn bàn giao.

- [ ] **1.1. Người thứ hai chấm 60 câu** ⭐ *việc quan trọng nhất còn lại*

  Gói đã sẵn: `research/evaluation/reports/calibration/cham_60cau.zip` (35 KB).
  Gửi → họ chấm → trả về `calibration_<tên>.jsonl`.

- [ ] **1.2. Bạn cũng chấm lại bộ mới** (bản CÓ checklist)

  Mở `calibration/cham.html`. Lần đầu chấm thiếu `expected_answer_points` nên κ
  chỉ 0,10 — phép đo chưa hợp lệ, không phải judge tệ. Bộ cũ đã lưu ở
  `*.v1_nochecklist.jsonl`.

  Có cả hai người thì được **hai** con số: κ người–judge, và κ người–người.
  Cái sau trả lời câu phản biện *"vừa là tác giả vừa là người chấm"*.

- [ ] **1.3. Tính κ**

  ```powershell
  $env:PYTHONPATH = "research;src"
  python -m evaluation.judges.calibrate --import <file đã chấm>
  ```

  Ngưỡng: κ trọng số bậc hai ≥ 0,61 thì mặt đó dùng được. Dưới thì phải ghi rõ
  là không đủ tin cậy.

- [ ] **1.4. Cập nhật `METRIC_EVIDENCE.md`** thêm bảng ba judge (§4 của
  `FINALIZE.md`) và kết quả κ.

- [ ] **1.5. Sửa cách mô tả n = 114 trong mọi tài liệu**

  Không phải *"114/145 thành công"* mà là *"114 câu chung giữa hai bộ đề"*.
  v1 chạy trên `generated_v3_2/eval_set.v3.jsonl` (145 dòng), v2 chạy `--limit 145`
  trên `datasets/eval_set.v3.jsonl` (195 dòng). Hai bộ chỉ giao 117 id.

---

## NHÓM 2 — Repo bàn giao được

- [ ] **2.1. Sửa `model/generator/Modelfile`** ⭐

  Vẫn `FROM ./Qwen2.5-7B-Instruct.Q4_K_M.gguf` = GGUF **vòng 1**. Ai clone repo
  rồi dựng lại sẽ được v1. Header của chính file đó đã dặn phải đổi.

  Bản đúng đã có tại `model/generator/qwen25_acne_role_v2_gguf_q4_k_m/Modelfile`.

- [ ] **2.2. Đổi tên một trong hai `eval_set.v3.jsonl`**

  Hai file cùng tên khác nội dung là nguyên nhân của nhầm lẫn ở 1.5. Đề xuất:
  `generated_v3_2/eval_set.v3.jsonl` → `eval_set.v3_145.jsonl`, sửa 4 chỗ tham chiếu.

- [ ] **2.3. Chạy bộ test** — `pytest`, 502 test, ~7 giây.

- [ ] **2.4. Commit 67 file đang dirty**

  35 sửa · 23 mới · 9 xoá. Gồm sửa của phiên này: `run_intake.py` (`--model`,
  `--verbose`), `rescore.py` (`--verbose`), `calibrate.py` (checklist),
  `clients.py` (giá GPT-5.6), dataset `_unused/`.

  Nên tách ≥ 2 commit: một cho công cụ eval, một cho dữ liệu `roledatav2`.

- [ ] **2.5. Dọn ~25 GB**

  | Mục | Cỡ |
  |---|---|
  | `model/legacy/` | 20 GB |
  | zip lạc trong `model/generator/` | 5,6 GB |
  | `research/datagen/roledatav2/output.round1/` | 62 MB |
  | `research/notebooks/colab/` | 2 MB |
  | `config/{cache,custom-covers,logs,secret_key}` — rác Komga | nhỏ |
  | `data/.fuse_hidden*` | nhỏ |
  | `scripts/ab_template_prompt.ps1` + `Modelfile.simplify` | nhỏ |

  `.git` đang **65 GB**, trong đó 64 GB là LFS. Cân nhắc `git lfs prune`.

---

## NHÓM 3 — Sửa lỗi đã tìm ra

Không chặn báo cáo, nhưng nên có mặt trong chương "hướng phát triển".

- [ ] **3.1. Vô hiệu hoá `inflammation_level`** trong đường chạy

  Lift **−0,415** — tệ hơn luôn trả `unknown`. Kiểm xem nó có chảy vào prompt
  generator không; nếu có thì cắt.

- [ ] **3.2. Thêm trần cho gate `len_chars`**

  `roledatav2/taxonomy.yaml` hiện chỉ ép **sàn**. Trong nội bộ v2, câu càng dài
  càng nhiều lỗi (ρ = +0,351, dải 116–7.732 ký tự).

- [ ] **3.3. Lưu bộ hồi quy an toàn**

  25 ca vi phạm thật → `research/evaluation/datasets/safety_regression.jsonl`.
  Chạy trước mỗi lần train, rẻ hơn 145 câu.

- [ ] **3.4. Thống nhất định nghĩa `reject` 6 nhóm** giữa
  `datagen/intakedata/taxonomy.yaml` và `evaluation/datasets/`.

  Gốc của vụ `reject` 93% trên bộ này nhưng 40% trên bộ kia.

- [ ] **3.5. Gom enum về `src/acne_llm/schemas/enums.py`** + test canh trôi cho
  cả 6 enum. Hiện chỉ `inflammation_level` có test.

---

## NHÓM 4 — Hoãn có chủ ý

- [ ] **4.1. Docker** — `ollama-init.sh` tạo `acne-generator` từ `Modelfile.full`
  (anchor cũ 3.719 ký tự, không `TEMPLATE`, 1 stop token) nên **Docker phục vụ
  model khác local**. Làm sau khi repo xong.

- [ ] **4.2. Finetune lại intaker** — chỉ khi cần. Phải sinh lại data trước, và
  sửa luôn lỗi *200 dòng multi-turn đều nhãn `clarify`* mà `_intent_patch.py` đã ghi.

- [ ] **4.3. Generator v3** — sau khi có 3.2 và đắp mẫu `R6`/`R8`.

---

## Đường tới hạn

```
1.1 gửi gói đi  ──┐
                  ├──> 1.3 tính κ ──> 1.4 cập nhật tài liệu ──> VIẾT BÁO CÁO
1.2 bạn chấm  ────┘

2.1 + 2.3 + 2.4  ──────────────────────────────────────────>  BÀN GIAO
```

**Việc chặn duy nhất là 1.1** — và nó đang chờ người khác, nên gửi gói đi trước,
rồi làm nhóm 2 trong lúc chờ.

Nhóm 2 mất khoảng một buổi. Nhóm 3 tuỳ thời gian còn lại.
