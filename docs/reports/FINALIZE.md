# Chốt sổ — số liệu và việc còn lại

Một chỗ duy nhất chứa mọi con số đã đo, để dán thẳng vào báo cáo, cộng danh sách
việc còn thiếu.

Cập nhật: 2026-08-19.

---

## PHẦN I — SỐ LIỆU ĐÃ CÓ

### 1. Dữ liệu huấn luyện

| | v1 `roledata` | v2 `roledatav2` |
|---|---|---|
| Mẫu được duyệt | 3.465 | 3.077 |
| Train / val / holdout | 2.945 / 277 / 243 | 2.616 / 246 / 215 |
| Ký tự assistant, trung vị | 311 | **1.062** |
| Token assistant được học | ~0,92 triệu | **~2,78 triệu** |
| Biến thể anchor | 1 | **3** (`v4.a/b/c`) |
| Gate cấu trúc | không | `len_chars` + `min_points` + ≥2 bullet |

### 2. Huấn luyện

Cấu hình LoRA **giống hệt nhau** — đây là cơ sở của thiết kế một biến.

| | v1 | v2 |
|---|---|---|
| Base | Qwen2.5-7B-Instruct 4-bit NF4 | như v1 |
| LoRA | r=16, α=32, dropout 0,05, 7 lớp linear | **như v1** |
| Tham số train | 40.370.176 / 7.655.986.688 = 0,53% | **như v1** |
| Effective batch | 16 | 16 |
| `MAX_SEQ_LENGTH` | 2048 | **3072** |
| Step | 555 (3 epoch trọn) | **dừng 450/492**, epoch 2,75 |
| Best val loss | 0,8119 @ step 300 | 0,7477 @ step 300 |
| Runtime | ~39 phút (RTX PRO 6000) | 76 phút (A100) |
| Early stopping | không kích hoạt | **kích hoạt** |

### 3. Eval generator — 145 câu, judge `deepseek-v4-pro`

| | v1 `RRR` | v2 `RRR` | Trần `RRO` |
|---|---|---|---|
| Độ dài p50 | 377 | **1.204** | 1.509 |
| `answer_quality` | 2,43 | 2,81 | 3,54 |
| — câu ≤2 | 89/145 | 46/145 | 24/141 |
| `missing_content` | 2,24 | 1,88 | 1,44 |
| `role_tone` | 3,34 | 3,89 | 4,34 |
| `groundedness` | 3,40 | **3,61** | 3,54 |
| Có bullet/số | **0/145** | **111/145** | 102/141 |
| Kết bằng `?` | 43/145 | 18/145 | 18/141 |
| `incorrect_content` | 0,30 | **0,72** | 0,16 |
| `safety_fail` | 18/145 | **38/145** | 12/141 |

### 4. Kiểm định bắt cặp — 114 câu, bootstrap 10.000

**Ba judge độc lập.** `*` = CI 95% không chứa 0.

| Mặt | DeepSeek-v4-pro | GPT-5.4-nano | GPT-5.6-luna | Vững? |
|---|---|---|---|---|
| `missing_content` | −0,482 * | −0,360 * | −0,237 * | ✅ **cả ba: tốt lên** |
| `incorrect_content` | +0,447 * | +0,711 * | +0,939 * | ✅ **cả ba: xấu đi** |
| `answer_quality` | +0,526 * | +0,360 * | +0,114 | ❌ Luna không xác nhận |
| `role_tone` | +0,623 * | *(hằng số)* | −0,211 * | ❌ **đảo dấu** |

CI đầy đủ:

```
DeepSeek : answer_quality +0,526 [+0,298,+0,763] · missing −0,482 [−0,667,−0,298]
           incorrect     +0,447 [+0,237,+0,658] · role_tone +0,623 [+0,439,+0,807]
nano     : answer_quality +0,360 [+0,193,+0,526] · missing −0,360 [−0,509,−0,202]
           incorrect     +0,711 [+0,544,+0,877] · role_tone  0,000 [ 0,000, 0,000]
luna     : answer_quality +0,114 [−0,070,+0,300] · missing −0,237 [−0,390,−0,090]
           incorrect     +0,939 [+0,730,+1,150] · role_tone −0,211 [−0,360,−0,070]
```

`safety_fail` 10 → 28 trên 114 câu bắt cặp. **McNemar exact p = 0,00091**
(23 câu hỏng thêm, 5 câu được cứu).

**Đồng thuận giữa judge** (Spearman, 145 câu v2):

| Mặt | DS↔nano | DS↔luna | nano↔luna |
|---|---|---|---|
| `answer_quality` | +0,589 | +0,699 | +0,635 |
| `missing_content` | +0,601 | +0,647 | +0,633 |
| `incorrect_content` | +0,466 | +0,672 | +0,666 |
| `role_tone` | n/a | **+0,421** | n/a |

Chi phí toàn bộ phần kiểm chứng chéo: **$0,29**.

### 5. Kiểm thiên lệch độ dài — Spearman trong nội bộ từng arm

| Arm | `answer_quality` | `incorrect_content` |
|---|---|---|
| v1 | **−0,255** | +0,233 |
| v2 | **−0,053** | **+0,351** |

→ **Không có thiên lệch độ dài.** Cải thiện không giải thích được bằng độ dài.

→ Phát hiện phụ: trong nội bộ v2, **câu càng dài càng nhiều lỗi** (ρ = +0,351,
dải 116–7.732 ký tự).

### 6. Phân loại 38 ca `safety_fail` của v2

| Loại | Số ca |
|---|---|
| Vi phạm thật | **25 (66%)** |
| Chỉ thiếu yếu tố hình thức | 12 (32%) |
| Khác | 1 |

Theo intent: `advise` 22/82 · `reject` 9/15 · `knowledge` 7/45.

Ba kiểu vi phạm thật: chỉ định lịch dùng thuốc khi chưa khám · khuyên chấm tinh
dầu tràm trà nguyên chất không pha loãng · khẳng định sai rằng thuốc trị mụn
không ảnh hưởng kinh nguyệt (isotretinoin gây rối loạn ~18%).

Nguyên nhân phân bố: `R2` 429 mẫu dạy *giúp*, `R6` 173 + `R8` 126 dạy *dừng*.

### 7. Eval intaker — 1.490 dòng

**Kỹ thuật:**

```
parse_fail_rate  0,000      fallback_rate 0,000
schema_valid     0,979      enum_validity 0,993–1,000
latency p50      2,04s      p95 2,41s
intent_ece       0,036      field_ece 0,307
```

**Intent:** 95,8% tổng · macro-F1 0,747 · `reject_recall` 0,933

| Nhãn | Đúng | Tỉ lệ |
|---|---|---|
| `knowledge` | 30/30 | 100% |
| `advise` | 1.359/1.410 | 96,4% |
| `reject` | 28/30 | 93,3% |
| `clarify` | 10/20 | **50%** (10 ca `__failure__`) |

**Trích xuất — dùng `lift` chứ đừng dùng accuracy thô:**

| Field | Accuracy | Baseline | Lift |
|---|---|---|---|
| `lesion_distribution` | 0,910 | 0,650 | **+0,260** |
| `lesion_types` | 0,798 | 0,646 | **+0,152** |
| `skin_type` | 0,978 | 0,892 | +0,086 |
| `age` | 0,992 | 0,952 | +0,040 |
| `is_breastfeeding` | 0,989 | 0,960 | +0,030 |
| `duration_weeks` | 0,986 | 0,957 | +0,029 |
| `is_pregnant` | 0,951 | 0,960 | **−0,009** |
| `sex` | 0,906 | 0,940 | **−0,034** |
| `inflammation_level` | 0,245 | 0,660 | **−0,415** |

Trung bình 12 field: acc thô **0,894**, baseline **0,882**, lift **+0,012**.
Accuracy chỉ trên dòng CÓ khai: **0,784**. Bỏ `inflammation_level` ra: acc 0,953,
lift +0,051.

`inflammation_level` chi tiết: 506 dòng có nhãn bậc, accuracy 0,362, hạ bậc 26
(5,1%), `unknown` recall chỉ **0,106** (bỏ sót 798/893).

### 8. A/B system prompt trên intaker — 290 dòng

Bản serve (3.337 ký tự) so với bản khớp train (2.132 ký tự):

```
pred_intent khác nhau : 0 / 290
per_field khác nhau   : 0 / 12
mọi chỉ số            : trùng khít
```

→ **System prompt không tác động lên model đã finetune.** Trọng số đóng cứng.

---

## PHẦN II — CÒN THIẾU

### A. Chặn báo cáo

**A1. κ người–judge.** Việc duy nhất còn thiếu về mặt dữ liệu, và giờ **quan
trọng hơn trước**: ba judge bất đồng ở `answer_quality` và `role_tone`, nên người
chấm mù là trọng tài duy nhất còn lại.

```powershell
$env:PYTHONPATH = "research;src"
python -m evaluation.judges.calibrate --export `
  --results research/evaluation/reports/calibration/merged_v1v2.json --size 60
# chấm calibration_sheet.jsonl, ĐỪNG mở calibration_key.jsonl
python -m evaluation.judges.calibrate --import calibration_sheet.jsonl
```

File `merged_v1v2.json` đã dựng sẵn: `SYS_A` = v1, `SYS_B` = v2, tên trung tính
để chấm mù. Trộn hai bản vào một phiếu nên còn đo được thêm: **người chấm mù có
xếp v2 trên v1 giống judge không.**

**A2. Cập nhật `METRIC_EVIDENCE.md`** với bảng ba judge ở §4 trên.

### B. Chặn bàn giao

**B1. `model/generator/Modelfile` vẫn `FROM ./Qwen2.5-7B-Instruct.Q4_K_M.gguf`** —
GGUF vòng 1. Production chạy đúng v2 vì `.env` gọi `acne-generator-v2`, nhưng ai
clone repo rồi dựng lại theo Modelfile gốc sẽ được **v1**. Header của chính file
đó đã dặn phải đổi.

**B2. 55 file chưa commit**, gồm cả sửa của phiên này: `run_intake.py`
(`--model`, `--verbose`), `rescore.py` (`--verbose`), `clients.py` (giá GPT-5.6).

**B3. Chạy bộ test một lượt** trước khi chốt — 502 test, ~7 giây. Phiên này chỉ
sửa trong `research/`, không đụng `src/`, nhưng nên xác nhận.

**B4. Dọn ~25 GB**: `model/legacy/` (20 GB), zip lạc trong `model/generator/`
(5,6 GB), `config/{cache,custom-covers,logs,secret_key}` (rác Komga),
`data/.fuse_hidden*`, `research/notebooks/colab/`, `output.round1/` (62 MB).

### C. Không chặn

**C1. `RRO` của v2** dừng ở 72/145 — không cần chạy nốt, trần đã có từ v1 cùng
model cùng bộ đề.

**C2. Bộ hồi quy an toàn** — 25 ca vi phạm thật, lưu thành
`research/evaluation/datasets/safety_regression.jsonl` để lần train sau chạy trước.

**C3. Docker** — hoãn theo yêu cầu. Nhắc lại vấn đề đã ghi: `ollama-init.sh` tạo
`acne-generator` từ `Modelfile.full` (anchor cũ 3.719 ký tự, không `TEMPLATE`,
1 stop token) nên **Docker phục vụ model khác local**.

---

## PHẦN III — PHÁT BIỂU KẾT LUẬN ĐỀ XUẤT

Dựa trên đúng những gì ba judge đồng thuận:

> Thiết kế lại dữ liệu huấn luyện với ràng buộc độ dài và cấu trúc đã đạt mục
> tiêu đề ra: độ dài trung vị tăng từ 377 lên 1.204 ký tự, tỉ lệ câu trả lời có
> cấu trúc danh sách tăng từ 0/145 lên 111/145, và mức bỏ sót nội dung giảm có ý
> nghĩa thống kê — nhất quán qua ba mô hình chấm điểm độc lập.
>
> Tuy nhiên can thiệp gây hồi quy ở hai mặt: nội dung sai tăng có ý nghĩa ở cả ba
> judge (mức tăng lớn dần theo năng lực judge: +0,447 → +0,711 → +0,939), và tỉ
> lệ trượt kiểm tra an toàn tăng từ 12% lên 26% (McNemar p < 0,001).
>
> Tác động lên chất lượng tổng thể **không kết luận được**: hai trong ba judge ghi
> nhận cải thiện có ý nghĩa ở `answer_quality`, judge thứ ba không xác nhận. Mức
> đồng thuận giữa các judge chỉ ở khoảng ρ = 0,42–0,70.
>
> Cơ chế của hồi quy được truy ra: trong nội bộ v2, độ dài câu trả lời tương quan
> dương với số lỗi nội dung (ρ = +0,351), trong khi tương quan với chất lượng gần
> như bằng không (ρ = −0,053). Ràng buộc độ dài buộc mô hình nói thêm, và phần
> nói thêm là nơi lỗi phát sinh.
