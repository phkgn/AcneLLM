# Đánh giá `run_full_v3_2` — báo cáo eval mới nhất

**Run:** `evaluation/reports/run_full_v3_2` · chạy 2026-08-08 20:18 → 2026-08-09 08:17 UTC (11h58m)
**Dataset:** `generated_v3_2/eval_set.v3.jsonl` — 145 dòng (100 sinh + 45 chính sách), loại 18
**Judge:** `deepseek-v4-pro` · **Generator baseline:** `acne-generator` (local) · **Oracle gen:** `gpt-5.6-terra`
**Bootstrap:** 2000 mẫu, seed 42 · baseline = `RRR`

> Chỉ **Khâu 3 (ablation)** chạy trong run này. Khâu 1 (intake) và Khâu 2 (retrieval) đều `skipped`.
> Artifact `intake/` và `retrieval/` trong thư mục là **tồn dư từ 08-08**, không thuộc run này.

---

## 1. Điểm tuyệt đối theo arm

| Arm | ok/n | answer_q (1-5) | role_tone (1-5) | incorrect ↓ (0-3) | missing ↓ (0-3) | ctx_suff (0-5) | ground (0-5) | safety% | refusal% | p50 latency |
|---|---|---|---|---|---|---|---|---|---|---|
| **RRR** (sản phẩm) | 145/145 | **2.43** | 3.34 | 0.30 | 2.24 | 3.20 | 3.40 | **87.6** | 89.7 | **119 s** |
| RNR (tắt RAG) | 145/145 | 2.45 | 3.38 | 0.26 | 2.26 | — | — | 90.3 | 89.7 | 44 s |
| ROR (RAG oracle) | 100/145 | 2.48 | 3.33 | 0.29 | 2.27 | **4.47** | 2.87 | 96.0* | 95.0* | 108 s |
| ORR (intake oracle) | 145/145 | 2.46 | 3.33 | 0.27 | 2.19 | 3.15 | 3.51 | **95.9** | **96.6** | 75 s |
| RRO (gen mạnh) | 141/145 | **3.54** | **4.34** | 0.16 | 1.44 | 3.11 | 3.54 | 91.5 | 89.4 | 110 s |
| RNO (gen mạnh, tắt RAG) | 142/145 | **3.70** | 4.34 | **0.10** | **1.27** | — | — | 90.8 | 89.4 | 46 s |

\* ROR rớt 53 mẫu (ca `reject`/`clarify` không có oracle context — đúng thiết kế), nên safety%/refusal% của ROR **không so được** với arm khác: mẫu đã bị lọc mất đúng phần nguy hiểm.

## 2. Sáu số quyết định (paired delta vs RRR, `answer_quality`)

| Câu hỏi | Công thức | Kết quả | 95% CI | Kết luận |
|---|---|---|---|---|
| RAG có đóng góp gì không | `RRR − RNR` | **0.000** | [−0.098, 0.089] | **Không.** Bằng 0 gần như tuyệt đối |
| Retriever còn dư địa bao nhiêu | `ROR − RRR` | **+0.25** | [0.087, 0.413] ✔ | Có, nhưng **rất nhỏ** |
| Tỉ lệ khai thác của retriever | `(RRR−RNR)/(ROR−RNR)` | **0 %** | — | Không khai thác gì |
| Intaker đáng sửa không (về chất lượng) | `ORR − RRR` | +0.04 | [−0.056, 0.144] | Không — nhưng xem §4 |
| Generator có phải nút thắt | `RRO − RRR` | **+1.04** | [0.836, 1.230] ✔ | **Đúng, áp đảo** |
| Model có biết dùng RAG không | `RRO − RNO` | **−0.16** | — | Ngay cả frontier model cũng **không** hưởng lợi từ RAG |

✔ = CI không chứa 0.

---

## 3. Ba phát hiện chính

### a. RAG hiện tại đóng góp bằng 0 — và tốn 75 giây/câu

`RRR − RNR = 0.000`. Tắt hoàn toàn retrieval không làm câu trả lời tệ đi ở **bất kỳ mặt nào**
(incorrect −0.008, missing +0.008, role_tone +0.008 — tất cả CI chứa 0), trong khi latency p50
giảm từ **119 s → 44 s**. Toàn bộ pipeline Dense + BM25 + RRF + cross-encoder đang trả về
75 giây và không có gì.

Theo đúng logic đọc arm trong `eval_context.md` §3, nếu `RRR−RNR ≈ 0` mà `RRO−RNO > 0` thì kết
luận là "RAG có giá trị, `acne-generator` không biết khai thác". **Không phải trường hợp này**:
`RRO−RNO = −0.16`, tức `gpt-5.6-terra` **cũng** không khá hơn khi có tài liệu — thậm chí RNO là
arm điểm cao nhất toàn bảng (3.70). Vậy vấn đề **không** nằm ở chỗ generator dốt, mà ở chỗ
**tài liệu đưa vào không mang thông tin mà câu trả lời cần**.

### b. Ngay cả tài liệu hoàn hảo cũng gần như không giúp

`ROR` bơm thẳng chunk vàng vào: `context_sufficiency` nhảy **3.20 → 4.47** (paired +1.33, SIG) —
tài liệu rõ ràng tốt hơn hẳn. Nhưng `answer_quality` chỉ nhích **+0.25**, và `groundedness`
lại **tụt −0.45 (SIG)**. Tài liệu tốt hơn nhiều mà câu trả lời gần như không đổi, độ bám tài
liệu còn giảm.

Đây là kết luận nghiêm khắc nhất của run: **trần trên của việc sửa retriever là ~+0.25/5 điểm.**
Có tối ưu retrieval đến hoàn hảo cũng không cứu được sản phẩm.

### c. Generator là nút thắt duy nhất có ý nghĩa

Đổi mỗi generator: `answer_quality +1.04`, `role_tone +1.02`, `missing_content −0.75`
(tất cả SIG, CI xa 0). Riêng `RNO` — model mạnh, không RAG — đạt 3.70/5 với latency 46 s,
gấp rưỡi điểm và bằng 40 % thời gian của sản phẩm hiện tại.

`missing_content` baseline = **2.24/3** (càng thấp càng tốt): `acne-generator` bỏ sót phần lớn
ý bắt buộc trong rubric. Đó là lỗi sinh, không phải lỗi tìm — vì `ORR`, `ROR` đều không sửa được nó,
chỉ đổi generator mới sửa (−0.75, −0.91).

---

## 4. Điểm dễ đọc sai — intaker

Nhìn `answer_quality` thì `ORR − RRR = +0.04` (ns) → "intaker không đáng sửa". **Sai nếu dừng ở đó.**
Nhìn cột an toàn:

| | safety fail | refusal fidelity |
|---|---|---|
| RRR | **18 / 145** (87.6 %) | 89.7 % |
| ORR | **6 / 145** (95.9 %) | **96.6 %** |

Bơm slot đúng vào intake **cắt 2/3 số ca fail an toàn** và giảm ~7 điểm lỗi quyết định
từ chối/trả lời. Cơ chế hợp lý: `is_pregnant`, `medications`, `allergies` trích sai → guard
thai kỳ và guard tương tác thuốc không kích hoạt. Intaker không phải nút thắt **chất lượng**,
nhưng đang là nút thắt **an toàn**.

87.6 % safety pass ở cấu hình sản phẩm là con số không chấp nhận được với hệ tư vấn y tế.

---

## 5. Độ tin cậy của chính con số này

| Vấn đề | Ảnh hưởng |
|---|---|
| **Đổi judge sang `deepseek-v4-pro`** (preflight đã cảnh báo) | Không được gộp/so với artifact cũ (`full_eval_1`, `run_full`, `full_eval_part2`) — khác thang |
| **Không có calibration người–judge trong run** | `calibrate.py` tồn tại nhưng không có artifact κ/Spearman. Điểm tuyệt đối 2.43/5 chưa biết là model dở hay judge khắt |
| **n nhỏ**: paired n = 92–125 | CI rộng; các delta nhỏ (ORR, ROR ở mặt context) chỉ đọc được là "không phát hiện được khác biệt", không phải "bằng nhau" |
| **Dataset synthetic**, `annotation_status: synthetic_pending_review` | Chưa qua review người. Guard trùng lặp có chạy (cosine p99 = 0.549) |
| **ROR rớt 53/145 mẫu** | Mọi số của ROR chỉ nói về câu hỏi kiến thức, không nói gì về ca chính sách |
| **Khâu 1 & 2 bị skip** | Không có số retrieval độc lập trong run này để đối chiếu §3.b |
| Lỗi `ConvertFrom-Json` (duplicate key `BHA`/`bha`) ở bước intake eval | Bước intake của e2e hỏng ở cả 2 lượt — cần sửa normalize key trước khi chạy lại Khâu 1 |

---

## 6. Kết luận

**Xếp hạng nút thắt: generator ≫ intaker (an toàn) ≫ retriever ≈ 0.**

1. **Không tối ưu retriever nữa.** Trần đo được là +0.25/5. Công sức bỏ vào Dense+BM25+RRF+
   reranker đang không đổi ra chất lượng. Nếu buộc phải chạm vào RAG, việc đáng làm là kiểm tra
   **KB có nội dung không** — vì ngay cả chunk vàng cũng chỉ đẩy `context_sufficiency` lên 4.47
   mà không đẩy được câu trả lời.
2. **Đầu tư vào generator.** Đây là biến duy nhất có delta lớn và chắc chắn (+1.04, CI [0.84, 1.23]).
   Fine-tune lại `acne-generator` nhắm thẳng vào `missing_content` (2.24/3 → mục tiêu < 1.5) sẽ
   thu về nhiều hơn mọi thứ khác cộng lại.
3. **Sửa intaker vì an toàn, không vì điểm.** 18 → 6 ca fail. Bắt đầu từ độ chính xác trích
   `is_pregnant` / `medications` / `allergies`.
4. **Cân nhắc tắt RAG trong lúc chờ.** RNR bằng điểm RRR ở mọi mặt, safety cao hơn (90.3 % vs 87.6 %),
   latency 44 s thay vì 119 s. Nếu chưa chứng minh được RAG mang lại gì, nó đang là 75 giây thuần lỗ.
   *(Cần chốt: nhóm có yêu cầu bắt buộc phải trích nguồn không — nếu có thì đây là ràng buộc sản
   phẩm, không phải quyết định đo lường.)*
5. **Trước khi tin số tuyệt đối, chạy calibration.** `python -m evaluation.judges.calibrate` để có
   Cohen's κ. Các delta trong báo cáo này là paired nên bền với judge bias; các mức tuyệt đối
   (2.43/5, 87.6 %) thì không.

**Việc cần làm ngay, theo thứ tự:** (1) sửa lỗi duplicate key `BHA`/`bha` rồi chạy lại Khâu 1;
(2) calibration người–judge; (3) chạy 8 arm (`+OOR ORO ROO OOO`) để có Shapley — hiện các delta
đơn lẻ không cộng thành tổng nên chưa định lượng được "generator chịu trách nhiệm bao nhiêu %".
