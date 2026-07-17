# Debug findings — evaluation pipeline — 2026-07-17

## Kết luận ngắn

Ba triệu chứng không có cùng một nguyên nhân:

1. **Citation S3 là lỗi hỗn hợp.** Validator cũ quá chặt với alias có thể quy về duy
   nhất, nhưng model cũng thật sự trả ID sai/mơ hồ và thường không cite. Sau fix bảo
   thủ, `citation_valid_rate` có điều kiện tăng từ **0.6349 lên 0.8413**, vẫn dưới gate
   0.95. Quan trọng hơn, chỉ **53/140 = 0.3786** record vừa có citation vừa hợp lệ.
2. **Faithfulness cũ chưa đủ tin cậy để dùng làm kết luận model.** Có lỗi provenance
   context, lỗi schema validation, S4 cắt giữa câu, false negative của entailment và
   claim-extract tự thêm/biến đổi claim. Tuy vậy, S2/S3 cũng có nhiều claim thật sự
   không nằm trong context. Sau fix có thể recompute offline, S2 chỉ đổi
   `0.4009 -> 0.4039`; S3/S4 không đổi. Các số này vẫn phải xem là provisional cho
   đến khi calibration trên D1 và rejudge bằng trace context mới.
3. **`vacuous` không bị đảo chiều.** Nó là rate of `True`, bỏ `None` khỏi mẫu số, và
   `True` chỉ có nghĩa `causes=[]` và `recommendations=[]`. Vì vậy S1 đúng là
   **70/140 = 0.5 empty-core-fields**, nhưng không phải 50% answer trắng: literal
   blank answer của S1 là **0/140**. Phần lớn mẫu audit đã nhét nội dung vào
   `disclaimer`, tức lỗi hợp đồng output của system cộng với tên cột dễ gây hiểu sai.

Không regenerate answer, không gọi paid judge, không sửa dataset hay evidence run.
Mọi recompute dưới đây đọc trực tiếp artifact hiện có.

## Phạm vi và evidence

- Run chính n=140: `evaluation/reports/prelim_d2_openai_20260717T073212Z/`.
- Run kiểm tra chéo n=30: `evaluation/reports/prelim_d2_20260717T090819_267Z/`.
- Generation n=140 tái dùng từ `prelim_d2_20260716T190345_330Z`; 30 answer đầu của
  S0-S4 giống byte-for-byte giữa run n=30 và n=140.
- Invariant quan trọng: D2 không dùng để tune prompt/threshold
  (`evaluation/README.md:190-196`). Vì vậy không sửa judge prompt hay ngưỡng dựa trên
  các case này; chỉ sửa lỗi cấu trúc có test xác định.

---

## 1. S3 citation mismatch

### Root cause

`citation_valid()` cũ dùng phép tập con exact-string
(`evaluation/metrics/deterministic.py`, trước fix tại hàm nay ở dòng 43). Trong khi
prompt đồng thời lộ ordinal `[Nguon N]` và `chunk_ref=<canonical-id>`
(`config/prompts/hybrid_user.j2:14`), model trả nhiều biến thể:

- `chunk_ref_2`, `chunk_ref_5`;
- `chunk_ref=<id>` hoặc `chunk_ref_<id>`;
- source+hash nhưng bỏ `::index`, hoặc chỉ hash;
- source name có khác biệt separator (`da lieu hanoi` / `dalieuhanoi`).

Không có bằng chứng cho (c) danh sách prompt khác danh sách validate hay (d)
off-by-one/reorder. Hybrid build prompt từ `top` tại
`src/acne_llm/pipeline/hybrid.py:272`, rồi gán `parsed.used_chunks` từ chính
`top.chunks`, giữ nguyên thứ tự tại dòng 292. Vì vậy ordinal 1-based có thể map an
toàn sang `used_chunks[N-1]`.

### Audit 10 record đầu có mismatch

| sample | model trả | context/used_chunks | kết luận |
|---|---|---|---|
| `d2-0003` | `chunk_ref_2`, `chunk_ref_5` | 5 canonical IDs đúng thứ tự prompt | alias ordinal, harness false positive E13 |
| `d2-0019` | `vinmec_0f4892fd51`, `vnexpress-suckhoe_4c2352567b` | cùng doc IDs, lần lượt `::0004`, `::0001` và duy nhất | alias bỏ index, quy về duy nhất |
| `d2-0026` | 4 ID đúng + `hello_bacsi_adapalene_bp::0002` | ID cuối không có trong 5 chunks | model bịa ID thật |
| `d2-0038` | `hellobacsi_87d400241e::0003` | context chỉ có cùng doc `::0004`, `::0005` | model sai chunk index thật |
| `d2-0039` | `chunk_ref_53aeabc0ca` | có cả `::0003` và `::0004` | alias mơ hồ, không được normalize |
| `d2-0040` | 3 ID đúng + `unknown` | không có `unknown` | model defect thật |
| `d2-0044` | `chunk_ref=<canonical-id>` | bỏ wrapper là exact | harness false positive E13 |
| `d2-0049` | doc ID bỏ `::index` | mỗi doc chỉ có một chunk trong context | alias duy nhất |
| `d2-0050` | `happyskin-vn_784f8040e9::0003` | canonical là `vnexpress-suckhoe_784f8040e9::0003` | sai provenance/source; vẫn invalid dù hash trùng |
| `d2-0051` | `d8540d60a4` | chỉ một used ID chứa hash này | alias hash duy nhất |

Raw evidence tương ứng nằm ở `s3.results.jsonl:3,19,26,38,39,40,44,49,50,51`.

### Phân loại toàn bộ 23 record cũ bị E13

- **13/23 harness false positive**: alias/wrapper/ordinal xác định được duy nhất.
- **3/23 mơ hồ**: `d2-0039`, `d2-0076-typo6`, `d2-0068-typo11`; không đủ dữ kiện
  chọn chunk index.
- **7/23 system defect thật**: ID/index/source sai hoặc `unknown` ở `d2-0026`,
  `d2-0038`, `d2-0040`, `d2-0050`, `d2-0010-typo46`, `d2-0059-typo49`,
  `d2-0023-typo57`.

Ở cấp citation value, sau normalization bảo thủ còn 18/255 value invalid: 9 value
mơ hồ và 9 value sai thật. Ở cấp record có citation, system defect chắc chắn là
7/63 = 11.1%; thêm 3/63 chưa thể xác minh do alias mơ hồ.

### Fix

- `evaluation/metrics/deterministic.py:61`: thêm `resolve_citation_id()`:
  exact trước; sau đó wrapper/ordinal; alias chỉ được chấp nhận khi map đúng **một**
  used chunk. Wrong index, wrong source, `unknown`, alias mơ hồ vẫn fail.
- `evaluation/analysis/report.py:35`: thêm ba đại lượng riêng:
  `citation_present_rate`, `citation_valid_rate` có điều kiện trên câu đã cite, và
  `citation_coverage_valid_rate` trên toàn bộ câu bắt buộc cite, kèm counts.
- `evaluation/analysis/check_gate.py:52,94`: gate ưu tiên coverage-valid, không còn
  cho 77 câu thiếu citation biến mất khỏi mẫu số; report legacy chưa có field mới
  vẫn fallback về field cũ.

Unit tests: `evaluation/tests/test_eval_debug_fixes.py:13-81`, gồm ordinal/wrapper,
alias duy nhất, ambiguous alias, wrong index, wrong source và denominator coverage.

### Metric trước/sau

| run/system | metric | trước | sau |
|---|---:|---:|---:|
| n=140 S3 | present / required | bị ẩn | 63/140 = **0.4500** |
| n=140 S3 | valid / present | 40/63 = **0.6349** | 53/63 = **0.8413** |
| n=140 S3 | present-and-valid / required | 40/140 = **0.2857** (không report) | 53/140 = **0.3786** |
| n=140 S3 | invalid record có cite | 23/63 | 10/63 |
| n=30 S3 | valid / present | 9/12 = **0.7500** | 11/12 = **0.9167** |
| n=30 S3 | present-and-valid / required | bị ẩn | 11/30 = **0.3667** |

Kết luận: fix harness không cứu được gate. Production S3 vẫn fail vì coverage thấp
và còn citation sai thật. S2 còn nghiêm trọng hơn: 0/140 record RAG có citation theo
structured output, nên coverage-valid mới là 0.0 dù conditional valid trước đây là
`None`.

---

## 2. Faithfulness thấp bất thường

### Pipeline và lỗi context provenance

Luồng hiện tại là claim extraction rồi entail từng claim
(`evaluation/judges/run_judge.py:190`). `_context_text()` cũ đọc
`trace.context_chunks`; Ollama adapter dựng trace từ BM25 text và cắt 1500 ký tự,
không phải exact rendered context mà model đã thấy. Prompt production sanitize,
chia budget 6000 ký tự và truncate theo chunk trước khi gọi model. Đây là harness
bug về **audit provenance**: judge được xem một context gần đúng, thường rộng hơn
context model thấy. Nó có thể làm điểm cao giả, không giải thích được toàn bộ điểm
thấp, nhưng khiến score cũ không audit được chính xác.

S4 không gọi LLM, answer copy tối đa 700 ký tự/chunk, trong khi trace chứa 1500 ký
tự. Context judge có chứa phần đã copy, nhưng adapter cũ dùng raw char cut nên có thể
tạo một “claim” dở dang.

### Audit tay 10 claim S2/S3 bị non-supported

| system/sample | claim/verdict | so với context/answer | phân loại |
|---|---|---|---|
| S2 `d2-0001` | cần bác sĩ da liễu xác nhận / `not_found` | context nói trực tiếp cần khám chuyên khoa da liễu | judge false negative |
| S2 `d2-0002` | severity được gắn `unknown` / `not_found` | là header metadata, không phải medical claim cần grounding | claim-extract/metric design bug |
| S2 `d2-0003` | thêm “chẩn đoán và phác đồ” / `not_found` | answer chỉ nói cần xác nhận; extractor tự làm claim cụ thể hơn | claim-extract expansion; entail đúng khi reject |
| S2 `d2-0004` | điều trị theo loại mụn / `not_found` | claim không xuất hiện trong answer một câu | claim-extract hallucination |
| S2 `d2-0007` | đau dữ dội/sốt phải cấp cứu / `not_found` | claim không xuất hiện trong answer | claim-extract hallucination |
| S3 `d2-0001` | tránh nặn / `not_found` | không có trong 5 chunks | generation unsupported thật |
| S3 `d2-0002` | SA/BP OTC, thuốc bôi, diet / `not_found` | các khuyến nghị cụ thể không có trong chunks đã dùng | generation unsupported thật |
| S3 `d2-0003` | vệ sinh/body soap và nhiều recs / `not_found` | chunks chủ yếu mô tả puberty/types; recs không được support | generation unsupported thật |
| S3 `d2-0004` | da dầu có thể ít mụn / `not_found` | context nói da dầu dễ gặp mụn; verdict đúng chiều non-support nhưng đáng ra `contradicted` | system defect + judge label coarse |
| S3 `d2-0012` | `Kem dưỡng ẩm.` / `not_found` | chỉ là noun fragment, không phải atomic proposition; text cũng có trong context | claim segmentation bug |

Evidence: `s2.judged.jsonl:1-4,7` và `s3.judged.jsonl:1-4,12` trong run n=140.

### Audit tay 5 claim S4

| sample | claim/verdict | kết luận |
|---|---|---|
| `d2-0011` | câu Er:YAG dài xuất hiện nguyên văn / `not_found` | false negative rõ |
| `d2-0016` | “Ở phụ nữ, cằm mọc…” xuất hiện nguyên văn / `not_found` | false negative rõ |
| `d2-0040` | câu kết thúc ở “có thể bôi 2” / `not_found` | raw 700-char truncation tạo claim hỏng |
| `d2-0048` | “Những nốt mụn này không mẩn đỏ…” nguyên văn / `not_found` | false negative rõ |
| `d2-0028-typo43` | “Thiếu vệ sinh là nguyên nhân hàng đầu…” / `contradicted` | judge đúng: context ngay sau đó bác bỏ mệnh đề |

Toàn S4 có 1577 claims: 1319 supported, 245 not_found, 13 contradicted. Có 23
non-supported claim đồng thời là exact substring của cả answer và judge context;
22 là `not_found`, 1 là `contradicted` đúng ở case myth nói trên. Audit tay xác nhận
nhiều false negative, nhưng không được auto-convert toàn bộ exact match thành
supported vì một source có thể trích dẫn rồi bác bỏ chính chuỗi đó.

S2 có 439 claims (150 supported, 288 not_found, 1 invalid); S3 có 1008 claims
(422 supported, 583 not_found, 3 contradicted). Do đó score thấp là hỗn hợp:

- harness/context/claim segmentation bug;
- judge behavior quá khắt hoặc không nhất quán;
- generation thật sự thêm ý ngoài context, đặc biệt ở S3.

### Vì sao S4 chỉ 0.84 thay vì gần 1

1. Entailment false-negative cả exact quote.
2. Claim extractor paraphrase, gộp hoặc thêm chi tiết; một số claim không còn là
   chuỗi mà S4 đã copy.
3. Raw char truncation biến câu thành fragment (`d2-0040`).
4. Copy nguyên văn không bảo đảm mọi mệnh đề là assertion được nguồn ủng hộ: chunk
   có thể chứa myth rồi bác bỏ nó (`d2-0028-typo43`).

### Fix

- `evaluation/adapters/ollama_batch.py:14-102`: capture exact rendered
  `<retrieved_context>` sau sanitize/budget và lưu `trace.faithfulness_context`.
- `evaluation/judges/run_judge.py:135-143`: ưu tiên exact context trên; trace cũ vẫn
  fallback để không phá artifact legacy.
- `evaluation/adapters/extractive.py:10-28,88`: truncate ở sentence boundary nếu có,
  thay vì raw char cut.
- `evaluation/judges/run_judge.py:190-255`: claim text phải non-empty; sau một lần
  schema repair mà claim/verdict vẫn invalid thì payload có `valid=false`, không
  sinh một score có vẻ hợp lệ.
- `evaluation/analysis/report.py:60`: recompute score từ verdict hợp lệ và loại payload
  invalid; không tin mù trường `faithfulness` lưu sẵn.

Không sửa prompt/threshold trên D2. Đề xuất cho D1 calibration: buộc claim-extract
giữ verbatim answer span, không sinh claim từ header `Mức độ/Loại mụn`, không thêm
chi tiết, và có gold set gồm exact quote, paraphrase, negation/myth, câu fragment.

Tests: `evaluation/tests/test_eval_debug_fixes.py:99-174` tái hiện sentence cut,
context provenance và blank-claim schema failure.

### Metric trước/sau offline trên artifact n=140

| system | trước | sau schema-safe recompute | trạng thái |
|---|---:|---:|---|
| S2 | 0.4009 | **0.4039** (135 payload hợp lệ; loại `d2-0019` invalid) | provisional |
| S3 | 0.4543 | **0.4543** | provisional |
| S4 | 0.8431 | **0.8431** | provisional |

Các fix context-capture và sentence truncation chỉ áp dụng cho generation/evidence
mới; constraint không regenerate khiến chúng không thể sửa ngược raw artifacts.
Không gọi lại judge nên không báo một “faithfulness corrected” giả tạo.

---

## 3. `vacuous` và S1 50%

### Semantic chính xác

`vacuous_answer()` tại `evaluation/metrics/deterministic.py:33`:

- structured `None` -> `None`;
- có ít nhất một `cause` hoặc `recommendation` -> `False`;
- cả hai rỗng -> `True`, bất kể `disclaimer`, `red_flags`, severity hay rendered
  answer có nội dung gì.

Aggregator tại `evaluation/analysis/report.py:141-143` bỏ `None`, rồi tính số
`True / số non-None`. Vì vậy cột cũ là **vacuous rate**, không phải pass rate và
không bị đảo chiều. Bug nằm ở tên/diễn giải: nó thực chất là
`empty_core_fields_rate`, không phải literal empty-answer rate. Markdown report mới
nêu rõ định nghĩa tại `evaluation/analysis/report.py:228-232`.

### Đối chiếu 5 record đầu mỗi system

| system | metric 5 record đầu | causes/recs | rendered answer |
|---|---|---|---|
| S0 | T,T,T,T,T | đều 0/0 | đều có disclaimer, 138 chars |
| S1 | T,T,F,F,T | `d2-0003/0004` có core fields; ba case kia 0/0 | tất cả có text, 247-808 chars |
| S2 | T,T,T,T,T | đều 0/0 | đều có disclaimer, 129-177 chars |
| S3 | F,F,F,F,F | mỗi case có cause hoặc rec | có nội dung đầy đủ hơn |
| S4 | None ×5 | `structured=None` | answer extractive 2408-2460 chars |

Pattern trong report cũ vì vậy hoàn toàn khớp code; mâu thuẫn với judge_correct chỉ
là hai metric nhìn hai đối tượng khác nhau: judge đọc rendered text, còn
`vacuous_answer` chỉ nhìn hai slot JSON.

### S1 sau khi đo lại

- Empty-core-fields theo định nghĩa đã đăng ký: **70/140 = 0.5000** (không đổi).
- Literal blank rendered answer: **0/140 = 0.0000**.
- 10 case đầu bị flag: `d2-0001`, `0002`, `0005`, `0006`, `0010`, `0011`, `0012`,
  `0013`, `0015`, `0017`.

Audit tay 10 case:

- 7/10 có nội dung thực dụng nhưng nhét sai field `disclaimer`: hỏi lại chi tiết,
  routine sáng/tối, lưu ý BHA, chăm thâm/sẹo, tránh nặn/thuốc kê đơn.
- 3/10 gần như generic disclaimer/referral (`d2-0010`, `d2-0012`, `d2-0017`).

Không ngoại suy 7/10 thành một rate toàn bộ vì đó sẽ là metric chủ quan và vi phạm
invariant không tune D2. Kết luận chắc chắn là S1 **không trắng 50%**; nó vi phạm
hợp đồng structured output 50%.

### Giả thuyết có bằng chứng về S1 no-RAG

Scan toàn bộ `data/finetune/cleanv3/acne_chat_response.train.jsonl`:

- 41,849/41,849 user prompts có `<guideline_context>`;
- 41,849/41,849 assistant outputs là prose;
- 0/41,849 assistant outputs là JSON object, 0 có key `causes`.

Trong S1 eval, `llm_only_user.j2` không có context và runtime ép schema AdviseOutput.
Đây là hai distribution shifts cùng lúc: **context luôn có -> không context**, và
**prose -> structured JSON**. Pattern “nội dung prose bị dồn vào disclaimer, core
arrays rỗng” phù hợp trực tiếp với mismatch này. Đây là giả thuyết nhân quả mạnh,
nhưng chưa là proof ablation; cần kiểm chứng trên D1 bằng training/format probe, không
dùng D2 để tune.

### Phân loại và fix

- Không có inversion bug trong metric hoặc aggregate.
- Có analysis/label bug: cột `vacuous` dễ bị đọc như pass rate hay answer trắng.
- Có system contract defect thật ở S0/S1/S2: nội dung không đi vào `causes` /
  `recommendations`; riêng S1 là 70/140.
- Fix report label/definition; không đổi metric definition/threshold trên D2.

Metric trước/sau vì vậy giữ nguyên: S0 0.9857, S1 0.5000, S2 1.0000, S3 0.0000,
S4 `None`. Từ nay phải đọc tên này là `empty_core_fields_rate`.

---

## Test và kiểm chứng

- Red tests trước fix: 5 failure + 1 pass cho batch đầu; sau đó thêm regression
  riêng cho report direction, invalid faithfulness, wrong-source citation và gate
  coverage, mỗi test đều fail trước phần fix tương ứng.
- Targeted suite cuối: **35 passed**.
- Full `pytest evaluation/tests -q`: **87 passed, 2 warnings**. Figure tests có side
  effect ghi artifact; các side effect đó đã được dọn, chỉ giữ source/test của task.
- Không có Ollama generation và không có API judge call.

## Con số nào được phép tin

| Nhóm số | Kết luận |
|---|---|
| parse/ok/latency và deterministic safety trên raw records | dùng được trong phạm vi T3 |
| S3 citation conditional 0.8413 | dùng được sau resolver bảo thủ, nhưng không đại diện coverage |
| S3 citation coverage-valid 0.3786 | số chính nên dùng cho readiness/gate |
| S1 empty-core-fields 0.5000 | dùng được; không gọi nó là “50% answer rỗng” |
| literal blank S1 0.0000 | dùng được |
| faithfulness S2/S3/S4 hiện tại | chỉ diagnostic/provisional; chờ trace mới + D1 judge calibration/rejudge |
| pointwise/pairwise OpenAI prelim | provisional theo notice của run; không nâng thành production verdict |

## Kết luận readiness

Sau khi loại lỗi harness, kết luận không đẹp hơn về production:

- S3 **vẫn fail citation gate**: 0.8413 nếu chỉ xét câu đã cite, và chỉ 0.3786 nếu
  xét toàn bộ câu bắt buộc cite.
- Faithfulness chưa được phép dùng để xếp hạng S2/S3 cho đến khi judge calibration
  và exact-context trace được chạy lại; audit tay vẫn xác nhận có unsupported
  generation thật ở S3.
- S1 no-RAG không “im lặng” 50%, nhưng vi phạm structured output contract 50% và có
  distribution mismatch rõ với finetune data.

Vì đây là T3 batch diagnostic, chưa đủ để tuyên bố production-ready; verdict cuối
vẫn cần T4 SSE theo invariant của `evaluation/README.md`.
