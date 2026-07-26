# Codex — Sửa thí nghiệm nút thắt trước khi chạy full run

> Tiếp nối `codex_eval_module_refactor_prompt.md`. Refactor Phase A–H đã xanh và
> được chấp nhận. File này chỉ sửa **thí nghiệm**, không đụng lại refactor.

## Vì sao

Kết quả 5 câu trong `docs/evaluation_refactor_evidence.md` **không dùng được để
kết luận**, vì hai lỗi thiết kế — không phải lỗi code, code chạy đúng như viết.

| # | Lỗi | Hậu quả |
|---|---|---|
| 1 | Arm X chạy trên `d8_qrels_seed.jsonl` — dataset **retrieval**, không có nhãn intake | Arm X chưa từng đo intake. Xem chi tiết ở Task 2. |
| 2 | Arm Y sinh 3 candidate rồi **dùng chính điểm judge** để chọn; Z/X/W chỉ 1 lần | Chỉ Y được giảm phương sai → "generator là nút thắt" tựa vào arm duy nhất được ưu ái |

Kết luận hiện tại trong evidence report phải được đánh dấu **vô hiệu**, không
phải sai — thí nghiệm chưa đo được thứ nó định đo.

---

# Task 1 — Bỏ đặc quyền lấy mẫu của arm Y

`scripts/eval_bottleneck.py:440-462`.

Hiện tại:

```python
if arm == "y":
    candidates, temperature_policy = _api_candidates(...)   # 3 lần khi temp không hỗ trợ
else:
    candidates = [generate_prose(..., temperature=0.0)]     # 1 lần

judged = [(c, _score_candidate(judge, sample, c)) for c in candidates]
selected_answer, selected_judge = sorted(
    judged, key=lambda item: item[1]["quality_score"]
)[len(judged) // 2]                                        # ← chọn bằng chính thước đo
```

**Sửa:** bỏ hoàn toàn bước chọn. Lấy candidate **đầu tiên**, luôn luôn.

```python
selected_answer, selected_judge = judged[0]
```

Vẫn giữ `candidate_scores` trong trace — nó là dữ liệu quý (cho biết phương sai
của arm Y), chỉ không được dùng để chọn.

**Không** sửa `_api_candidates` để ép temperature=0 — nếu model không hỗ trợ thì
đó là sự thật về model, ghi lại `temperature_policy` là đủ. Nhưng phải ghi rõ
trong summary rằng arm Y chạy ở temperature mặc định còn Z/X/W ở 0, và đó là
một bất đối xứng đã biết.

`ponytail:` comment tại chỗ: `# ponytail: chọn candidate[0], KHÔNG chọn theo
judge score — chọn bằng chính thước đo làm hỏng tính độc lập của Y−Z`.

---

# Task 2 — Arm X phải fail to, không được im lặng đoán

## Chuyện gì đã xảy ra

`_OracleIntake._intent()` (dòng 75-84) có nhánh fallback:

```python
label = self.sample.get("intent_label")
if label in {...}: return str(label)
task_type = self.sample.get("task_type")
if task_type == "retrieval_qrels": return "knowledge"    # ← nhánh này
```

5 mẫu đã dùng (`d8-0001,0003,0004,0006,0008`) đều có:

```
intent_label = None
task_type    = "retrieval_qrels"
user_context = {} cho 3/5 mẫu; {"skin_type":"sensitive"} và {"age":15} cho 2 mẫu
```

Nên arm X thực tế đã làm:

1. **Ép intent = "knowledge" cho cả 5 mẫu** — đây không phải nhãn vàng, mà là
   một hằng số suy ra từ loại dataset. Mẫu nào lẽ ra là `advise` thì bị đổi
   template (C6: 5 template theo intent) → prose sai dạng → điểm thấp hơn.
2. **Không bơm thêm thông tin gì** cho 3/5 mẫu (`user_context` rỗng).
3. `classify()` trả `confidence=1.0` nhưng `run()` lại lấy confidence từ
   `extract_with_confidence()` chạy trên raw text → **hai nửa của oracle
   không nhất quán**: field là vàng, confidence là của rule chạy trên text.
4. `run()` có `del history` trong khi `classify()` dùng history → bất đối xứng.

Đây là lời giải thích đầy đủ cho "X giảm 2/5". **Arm X không đo intake — nó đo
tác hại của việc ép sai intent.**

## Sửa

### 2a. Xóa nhánh fallback, fail to

```python
def _intent(self) -> str:
    label = self.sample.get("intent_label")
    if label in {"advise", "knowledge", "clarify", "reject"}:
        return str(label)
    raise ValueError(
        f"arm X yêu cầu intent_label vàng; mẫu {self.sample.get('sample_id')} "
        f"chỉ có task_type={self.sample.get('task_type')!r}. "
        f"Dùng dataset có nhãn intake gán tay (B3), không phải d8_qrels."
    )
```

Suy intent từ `task_type` là đoán. Oracle mà đoán thì không còn là oracle.

### 2b. Guard ở đầu run — chặn trước khi tốn tiền judge

Trước khi chạy arm X, quét toàn bộ dataset. Nếu **bất kỳ** mẫu nào thiếu
`intent_label`, dừng ngay với thông báo rõ, không chạy một mẫu nào. Không được
chạy nửa vời rồi báo cáo.

### 2c. Đồng bộ confidence với field đã bơm

Khi oracle bơm field từ `user_context`, confidence của **đúng những field đó**
phải là 1.0, không phải giá trị rule-based tính trên raw text. Field không bơm
thì giữ nguyên confidence rule.

Lý do: `extract_min_field_conf = 0.60` quyết định field có được coi là "đã có"
hay không. Field vàng nhưng confidence thấp = tệ hơn intake thật, vì intake
thật ít nhất cho cặp (giá trị, độ tin) nhất quán với nhau.

### 2d. Bỏ `del history` trong `run()`

`classify()` dùng history, `run()` vứt đi. Cùng một oracle phải thấy cùng một
đầu vào.

### 2e. Ghi rõ trong artifact arm X đã bơm gì

Mỗi mẫu ghi: `oracle_intent`, danh sách field đã bơm, và **số field bơm được**.
Nếu số đó bằng 0 thì arm X ≡ arm Z cho mẫu ấy — phải hiện ra trong summary,
không được để lẫn vào trung bình như một mẫu bình thường.

---

# Task 3 — Bộ dữ liệu: tách đúng dataset cho đúng arm

Đây là gốc của Task 2: một dataset không phục vụ được cả W lẫn X.

| Arm | Cần gì | Dataset |
|---|---|---|
| Z, Y | câu hỏi + judge | dùng chung, bất kỳ |
| **W** | `relevant_chunk_ids` (qrels) | `d8_qrels_seed.jsonl` ✔ đã có |
| **X** | `intent_label` + `user_context` gán tay | **chưa có — chờ B3 (250 mẫu)** |

**Việc cần làm bây giờ:**

- Thêm cờ `--dataset` cho `eval_bottleneck.py`; arm X và arm W được phép dùng
  dataset khác nhau, nhưng **Z phải chạy lại trên đúng dataset của arm đang so**.
  Paired delta chỉ có nghĩa khi cùng bộ câu.
- Nếu chạy X và W trên 2 dataset khác nhau thì artifact phải có **2 baseline Z
  riêng**, và tuyệt đối không so X với W trực tiếp.
- Trong lúc chưa có B3: `--arm x` chạy sẽ dừng ở guard 2b. Đó là hành vi đúng.
  Ba arm Z/W/Y vẫn chạy được trên d8.

---

# Task 4 — Đủ n ở mọi arm

`d8-0006` timeout ở arm W → W có n=4 còn ba arm kia n=5. So paired mà khác n
là hỏng.

Quy tắc: **mẫu nào fail ở bất kỳ arm nào thì loại khỏi paired analysis của
TẤT CẢ các arm.** Báo cáo riêng số mẫu bị loại và lý do.

Thêm vào summary: `paired_n`, `dropped_ids`, `drop_reason`. Retry 1 lần với
backoff trước khi tính là fail.

---

# Task 5 — Chấm theo mặt, không phải một điểm

Hiện `quality_score` là **một** con số → không biết arm Y thắng nhờ mặt nào.
Mất đúng thứ quan trọng nhất: biết mỗi khâu ảnh hưởng vào đâu.

## 5a. `evaluation/metrics/scorecard.py` — mới

**Không viết judge mới.** Gom 5 mặt, phần lớn đã có sẵn:

| Mặt | Lấy từ đâu |
|---|---|
| Bám tài liệu / không bịa | `metrics/grounding.py` `GroundingScorer` — **đã có** |
| An toàn (cửa chặn) | `refusal_fidelity` + `pregnancy_safety` ở `deterministic.py:154` — **đã có** |
| Từ chối đúng chỗ | cùng nguồn trên — **đã có** |
| Trả lời đúng ý & đủ | judge, 1–5 — **mới** |
| Đúng vai & giọng | judge, 1–5 — **mới** |

Chỉ thêm 2 mặt vào prompt judge. Ba mặt còn lại đọc từ metric đã có.

## 5b. An toàn là cửa chặn, không phải một số hạng

Mẫu nào phạm lỗi an toàn nghiêm trọng → **tách riêng, không đưa vào trung
bình**. Không cho điểm cao ở mặt khác che một ca nguy hiểm. Summary phải có
cột `safety_fail` riêng cho từng arm.

## 5c. Báo cáo từng mặt cho từng arm

Bảng paired delta phải có **một dòng cho mỗi mặt**, không chỉ điểm gộp. Đây là
lý do tồn tại của cả thí nghiệm: biết "sửa generator làm bám-tài-liệu tăng vọt
nhưng an toàn không đổi" thì mới ra quyết định được.

---

# Task 6 — Đo trọng tài

Chưa có số này thì mọi điểm ở trên đều là thước cong.

`scripts/judge_agreement.py`:

- Lấy 40 mẫu đã chấm (trải đều các arm, **bắt buộc gồm cả mẫu của arm Y**).
- Xuất file cho người chấm tay theo đúng 5 mặt của scorecard.
- Nhận file người chấm về, tính độ khớp: Cohen's kappa hoặc Spearman cho mặt
  1–5, exact agreement cho mặt nhị phân.
- Báo cáo **riêng cho arm Y** — arm Y dùng model OpenAI, judge cũng OpenAI, nên
  đây là chỗ duy nhất phát hiện được thiên vị cùng nhà nếu có.

Ngưỡng chấp nhận đề xuất: kappa ≥ 0.6 cho mặt an toàn, ≥ 0.4 cho các mặt còn
lại. Dưới ngưỡng → không được dùng judge này ra kết luận.

---

## Định nghĩa "xong"

```
[ ] eval_bottleneck.py: arm Y lấy candidate[0], không chọn theo judge score
[ ] --arm x trên d8_qrels_seed → DỪNG với thông báo rõ, không chạy mẫu nào
[ ] arm X ghi được số field đã bơm mỗi mẫu; mẫu bơm 0 field hiện riêng trong summary
[ ] cờ --dataset hoạt động; mỗi baseline Z gắn với đúng dataset của nó
[ ] mẫu fail ở 1 arm bị loại khỏi paired analysis của mọi arm; có dropped_ids
[ ] scorecard.py cho ra 5 mặt; safety tách riêng khỏi trung bình
[ ] bảng paired delta có 1 dòng mỗi mặt, mỗi arm
[ ] judge_agreement.py xuất được file chấm tay 40 mẫu
[ ] pytest xanh
[ ] Chạy lại Z/W/Y trên d8 (5 mẫu) → artifact mới, so với artifact cũ
    ec955c00... và ghi rõ con số nào đổi vì sửa Task 1
```

## Cập nhật báo cáo

`docs/evaluation_refactor_evidence.md` phần "Kết luận": đánh dấu kết quả 5 câu
là **vô hiệu về mặt thí nghiệm**, giữ nguyên phần refactor evidence. Ghi rõ
arm X chưa từng đo intake và vì sao. Không xóa số cũ — giữ lại làm đối chứng.

## Ngoài phạm vi

Full run · task A3–A5, B4–B6, C4–C6, D1–D4 · gán tay B3 (250 mẫu) và A1 —
là việc của người dùng, chạy song song.
