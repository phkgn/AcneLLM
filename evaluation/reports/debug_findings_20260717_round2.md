# Debug findings vòng 2 — bỏ inline citation, đo grounding thay thế

Ngày chốt: 2026-07-17  
Phạm vi: D1 dev, Ollama local, không gọi paid judge, không tune trên D2, không sửa dataset hay artifact cũ.

## Kết luận điều hành

Phần bỏ inline citation đã hoàn tất và có rollback một dòng bằng `inline_citation: "model"`. Ở mode mặc định `off`, prompt không còn yêu cầu `[N]`, không lộ `chunk_ref`, output model được strip marker số an toàn, còn panel nguồn tiếp tục nhận citation event độc lập. S4 extractive cũng đã đổi tiêu đề từ `[1]` sang `Nguồn 1 — ...`, vì dù không phải model citation thì chuỗi cũ vẫn vi phạm smoke contract theo regex.

Grounding deterministic đã chạy end-to-end, nhưng kết quả không cho phép kết luận RAG hiện đã grounded tốt. Trên smoke D1, S3 chỉ đạt **5/25 = 0,20**, thấp hơn gate provisional **0,50**. Context swap làm answer thay đổi ở mức trung bình **0,267**, nhưng canary adoption là **0/3**. Kết luận đúng là: model có phản ứng phần nào với context, song bằng chứng sử dụng fact cụ thể trong context còn yếu và không nhất quán.

Vì vậy Round 2 đạt mục tiêu kỹ thuật của harness/citation cleanup, nhưng **không đạt gate grounding và chưa sẵn sàng để tuyên bố RAG-grounded**. Ngoài ra, contract của base model vẫn là confound thật: S0/S2 parse được JSON nhưng nội dung chính rỗng; hai prompt instruction nhỏ không sửa được.

## 1. Production citation contract

### Thay đổi

- `hybrid_user.j2`, `stream_user.j2`, `knowledge_user.j2` không còn instruction cite ở mode mặc định.
- Hai partial compatibility chỉ được include ở mode `model`: `_inline_citation_model_prose.j2` và `_inline_citation_model_structured.j2`.
- `PromptBuilder` chỉ render ordinal `[Nguon N]` và `chunk_ref=...` khi `inline_citation == "model"`.
- Config mới là `inline_citation: off | model`, default `off`. `chat_require_citations` được giữ làm legacy setting nhưng không còn điều khiển contract mới.
- POST structured output được clean đệ quy; SSE dùng stateful stripper nên vẫn bắt được marker bị tách qua nhiều token. Regex chỉ xóa `[` + 1–3 chữ số + `]`; không đụng `0.1%`, `15-20 phút`, khoảng liều hay tag có tên.
- `source_chunk_id` được giữ để tương thích schema, không required, không bị validate thành lỗi ở mode `off`, và được đánh dấu deprecated trong schema description.
- Mode `model` khôi phục instruction, `chunk_ref`, citation compliance/repair cũ. Việc model có tự sinh marker hay không vẫn là hành vi model; rollback khôi phục contract chứ không giả định model sẽ tuân thủ.

### UI

Kiểm tra tĩnh xác nhận `useSSE.ts` vẫn xử lý event `citation` riêng, `chatStore.ts` lưu citations tách khỏi answer, và `MessageBubble.tsx` render source cards từ mảng citations chứ không parse `[N]`. `npm run lint` trong `frontend/` pass. Đây là bằng chứng wiring + lint; chưa phải browser visual E2E.

### Regression coverage

- Default-off prompt, model rollback, strip prose/structured, token-split streaming, bảo toàn số/tag.
- SSE default-off vẫn emit citation panel event dù text marker bị strip.
- S4 dùng heading markerless `Nguồn N`.

## 2. Grounding deterministic

### Định nghĩa

Module mới: `evaluation/metrics/grounding.py`.

1. Tách sentence theo `. ! ?`, xuống dòng và bullet; bảo vệ số thập phân và các viết tắt như `BS.`.
2. Loại câu chào, câu hỏi, metadata render (`Mức độ`, `Loại mụn`) và disclaimer chuẩn.
3. Với mỗi sentence còn lại, so với context model thực sự thấy trong `trace.faithfulness_context`; nếu artifact không có exact context thì fallback sang snapshot `trace.context_chunks`.
4. Lexical score là character 3-gram Dice trên tiếng Việt lowercase/bỏ dấu, lấy max theo từng câu context. Semantic score là cosine từ embedder có sẵn `AITeamVN/Vietnamese_Embedding`, không thêm dependency.
5. Score cuối là `max(lexical, semantic)`. Lý do: quote gần nguyên văn và paraphrase là hai kiểu support khác nhau; weighted average sẽ phạt oan khi chỉ một tín hiệu mạnh. Đổi lại, phép max làm metric thiên về recall và cần threshold thủ công.
6. Per-record output gồm `grounded_sentence_rate`, `unsupported_sentences`, số câu eligible/grounded, score từng câu, threshold và context tốt nhất.

Report aggregation dùng mẫu số câu: `sum(grounded_sentences) / sum(eligible_sentences)`, không lấy trung bình mù theo record. Deterministic metrics được tổng hợp từ generation-valid records kể cả khi không chạy judge; report đồng thời hiện `n_generation_valid` để tránh cột `n=0` của judge bị hiểu nhầm là không có generation.

### Tune threshold chỉ trên D1

Đọc tay 15 câu D1 theo whole-claim entailment: 12 supported, 3 unsupported. Sweep cuối sau khi sửa lexical scorer từ whole-chunk sang từng câu context:

| Threshold | Predicted grounded rate | Precision ước lượng | Recall ước lượng | F1 | TP/FP/FN/TN |
|---:|---:|---:|---:|---:|---:|
| 0,50 | 0,47 | 1,00 | 0,58 | 0,74 | 7/0/5/3 |
| 0,55 | 0,40 | 1,00 | 0,50 | 0,67 | 6/0/6/3 |
| 0,60 | 0,27 | 1,00 | 0,33 | 0,50 | 4/0/8/3 |
| 0,65 | 0,27 | 1,00 | 0,33 | 0,50 | 4/0/8/3 |
| 0,70–0,90 | 0,07 | 1,00 | 0,08 | 0,15 | 1/0/11/3 |

Chọn **0,50** vì F1 cao nhất trong sweep và không tạo false positive trên 15 nhãn. Precision `1,00` chỉ là ước lượng trên mẫu rất nhỏ, không phải độ chính xác đã tổng quát hóa. Recall `0,5833` cho thấy proxy đang bảo thủ và có thể đánh rớt paraphrase/ngữ cảnh ngắn.

Artifact calibration cuối: `evaluation/reports/unit/grounding_threshold/20260717T122004Z/report.json`. Run `20260717T121736Z` là chẩn đoán bị loại: whole-chunk overlap làm cả 3 negative thành false positive; nó được giữ để audit, không dùng làm threshold cuối.

### Tests và giới hạn đã biết

Tests bao phủ exact quote, paraphrase, hallucination, số/thập phân/khoảng, disclaimer/metadata, cùng case myth-rồi-bác-bỏ. Giới hạn được ghi thẳng trong output là `negation_or_refutation`: similarity có thể align đúng từ nhưng sai chiều khẳng định. Các câu hành động rất ngắn như “Cần tránh hoàn toàn” cũng có thể false-negative do thiếu lexical surface. Đây là proxy miễn phí bổ sung, không thay thế faithfulness LLM-judge hay human review.

## 3. Context sensitivity D1

Runner: `evaluation/unit/eval_context_sensitivity.py`; model `acnellm-v2-q4`; seed cố định; 3 case D1. Canary `EVALCANARY-L42` chỉ được chèn vào bản copy in-memory của retrieval output, đứng đầu context, không gọi API ghi KB; `persistent_kb_write_calls = 0`.

| Case | Canary adopted | Embedding distance | Char-3gram distance | Swap sensitivity |
|---|---:|---:|---:|---:|
| d1-0000 | 0 | 0,2401 | 0,4266 | 0,3334 |
| d1-0001 | 0 | 0,1995 | 0,2989 | 0,2492 |
| d1-0002 | 0 | 0,0917 | 0,3450 | 0,2184 |
| **Mean/rate** | **0/3 = 0,0000** | **0,1771** | **0,3568** | **0,2670** |

Gate provisional: canary adoption `>= 0,50` **fail**; swap sensitivity `>= 0,15` **pass**. Chín prompt trace (canary/correct/swapped × 3) đều không chứa citation instruction hoặc `chunk_ref`.

Diễn giải: answer không hoàn toàn bất biến khi đổi context, nên chưa có red flag “bỏ context hoàn toàn”. Tuy nhiên model bỏ qua một fact vô hại được yêu cầu nhắc lại ở cả 3 case. Canary fail không tự nó chứng minh model không dùng bất kỳ context nào—schema/prompt priority cũng có thể chặn canary—nhưng kết hợp với grounding S3 thấp thì là tín hiệu cần điều tra, không phải pass chất lượng.

Artifact: `evaluation/reports/unit/context_sensitivity/20260717T122510Z/report.json`.

## 4. Gate/report và artifact cũ

- `evaluation/configs/gate.yaml` dùng `generation.grounded_sentence_rate >= 0,50`; citation không còn là release gate.
- `citation_present_rate`, `citation_valid_rate`, `citation_coverage_valid_rate` vẫn được đọc/hiển thị với nhãn legacy để artifact cũ không vỡ.
- Prose artifact cũ chỉ có đúng một `[1]` decorative ở cuối answer được coi là không cite. Rule chỉ tác động citation legacy, không xóa dữ liệu gốc.
- `check_gate.py` có `--out` để gate result nằm trong run mới, tránh ghi đè `evaluation/reports/gate_check.json`.

Recompute read-only trên D1 artifact cũ tạo artifact mới `evaluation/reports/round2_legacy_grounding_d1_20260717T125908Z/report.json`. Việc reconstruct context chỉ được phép vì SHA-256 BM25 nguồn khớp current index; source artifact và hash đều được ghi lại.

| Metric trên 10 record cũ | Kết quả |
|---|---:|
| Grounded sentence rate | 24/52 = 0,4615 |
| Unsupported sentences | 28/52 |
| Legacy citation present | 2/10 = 0,20 |
| Legacy citation valid, conditional on present | 2/2 = 1,00 |
| Legacy citation coverage-valid | 2/10 = 0,20 |

Hai metric không cùng ý nghĩa; số liệu chỉ cho thấy citation presence thấp không đủ đại diện cho support. Không có file cũ nào bị sửa.

Gate run-local từ smoke sạch ban đầu: `evaluation/reports/round2_smoke_20260717T124200Z/gate_check_round2.json`: tổng 5/15 check pass. Với các check trực tiếp liên quan smoke/context: parse pass, safety pass, swap pass; S3 grounding fail và canary fail. Các retrieval/unit failure còn lại dùng nguồn unit hiện có và không được “sửa ké” trong vòng này.

## 5. Memo quyết định eval contract — người dùng quyết

### Chứng cứ

Đọc 15 S0 + 15 S2 đầu tiên từ artifact immutable `prelim_d2_20260716T190345_330Z`:

- **S0:** 15/15 parse JSON, 15/15 có `causes=[]` và `recommendations=[]`; rendered answer trung bình 131,9 ký tự. Cả 15 chỉ gồm `unknown/unknown` và disclaimer boilerplate, không có câu trả lời y khoa thực chất.
- **S2:** 15/15 parse JSON, 15/15 core rỗng; rendered answer trung bình 145,9 ký tự. Nội dung nằm trong `disclaimer`, thường chỉ một câu mơ hồ. Có dangling reference `[N3]/[N4]` và câu “tuân theo hướng dẫn dưới đây” nhưng không có hướng dẫn.
- `_flatten_advise` render `severity`, `acne_type`, `causes`, `recommendations`, `red_flags`, rồi `disclaimer`. Vì vậy answer nonempty không chứng minh core fields đã có nội dung; trong mẫu đọc tay, rendered prose cũng nghèo chứ không chỉ sai vị trí field.

Probe hướng (b), 3 case D1, base+RAG S2, không sửa production prompt:

| Variant | Parse success | Empty core fields |
|---|---:|---:|
| Baseline | 3/3 | 3/3 = 1,00 |
| “causes/recommendations không đồng thời rỗng” | 3/3 | 3/3 = 1,00 |
| “disclaimer chỉ cho giới hạn/an toàn” | 3/3 | 3/3 = 1,00 |

Model vẫn dồn content vào disclaimer. Artifact: `evaluation/reports/unit/structure_prompt_probe/20260717T122041Z/report.json`.

### Trade-off và khuyến nghị

**(a) Chấm semantic trên prose, structured metrics chỉ áp cho S3.** Rẻ và tách được chất lượng nội dung khỏi schema compliance, nhưng không nên tiếp tục dùng `_flatten_advise` hiện tại cho base: bằng chứng cho thấy prose render từ JSON vẫn rỗng/nghèo. Biến thể sạch hơn là cho S0/S2 dùng raw-prose answer path riêng, judge cùng semantic rubric, còn S3 giữ structured production contract. Đổi lại, điều kiện không còn cùng output format; report phải tách “semantic comparator” và “production contract compliance”.

**(b) Làm base model điền structure.** Giữ cùng contract, nhưng hai instruction nhỏ đã không cải thiện 3/3 case. Bước tiếp theo phải là few-shot đầy đủ, schema nhỏ hơn hoặc parser/adapter khác; đây là thay đổi hệ thống chứ không còn comparator thuần, có thể ưu ái base condition và phải rebaseline.

**Khuyến nghị để người dùng chọn:** chọn (a) theo dạng raw-prose comparator cho S0/S2, và chỉ áp structured metrics cho S3. Lý do là dữ liệu hiện tại bác bỏ giả định “rendered answer đủ nội dung”, còn prompt patch nhỏ của (b) không hiệu quả. Nếu mục tiêu ưu tiên tuyệt đối là cùng deployment contract, chọn (b), nhưng phải coi đó là một experiment mới và rerun D1 trước khi đụng D2. Chưa thay đổi contract trong code ở vòng này.

Sau khi quyết định: khóa adapter/rubric, chạy D1 regression nhỏ, rồi regenerate full T3 và judge/human calibration theo cùng contract; không tái sử dụng score D2 cũ để so trực tiếp nếu output path thay đổi.

## 6. Smoke tổng hợp

Run sạch model-backed: `evaluation/reports/round2_smoke_20260717T124200Z/`. S4 markerless được rerun riêng sau regression test tại `evaluation/reports/round2_smoke_s4_markerless_20260717T131952Z/`.

| System | OK | Exact faithfulness context | Cite instruction | `chunk_ref` prompt | Answer `[n]` | Grounding |
|---|---:|---:|---:|---:|---:|---:|
| S2 off | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 | 7/14 = 0,5000 |
| S3 off | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 | 5/25 = 0,2000 |
| S3 rollback `model` | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 8/18 = 0,4444 |
| S4 markerless | 3/3 | N/A | N/A | N/A | 0/3 | 68/71 = 0,9577 |

Rollback đã khôi phục chính xác prompt contract; trong ba sample cụ thể model không tự sinh `[N]`. Unit test SSE chứng minh old deterministic repair vẫn thêm marker khi mode `model` và model bỏ sót. Không được diễn giải 0/3 output marker là rollback hỏng.

S4 có 9/9 snippet dài 513–689 ký tự, không quá budget 700, đều kết thúc bằng `.`, không cắt giữa câu. Grounding cao của S4 là kỳ vọng vì answer là trích xuất; không dùng số đó để kết luận generative S3 tốt.

`grounded_sentence_rate` và `unsupported_sentences` có mặt trong mọi record applicable và report. Smoke config đầu `round2_smoke_20260717T123500Z` được giữ làm failure evidence: YAML bare `off` bị parser thành boolean `False`; sau khi quote thành `"off"`, run sạch pass 12/12 generation. Run `round2_smoke_20260717T130655Z` không được dùng vì hai shell timeout để lại concurrent writers, gây duplicate sample; số liệu ở report này không được trích dẫn.

## 7. Verification và việc còn lại vòng 3

Verification cuối:

- `pytest evaluation/tests -q`: **105 passed**.
- Citation/prompt/stream targeted tests: **27 passed**.
- `frontend npm run lint`: **pass**.
- `git diff --check`: không có whitespace error; chỉ có cảnh báo LF/CRLF của checkout Windows.

Vòng 3 nên làm theo thứ tự:

1. Người dùng chốt contract (a) raw-prose comparator hay (b) structured base experiment.
2. Điều tra S3 grounding 0,20 và canary 0/3 bằng prompt/context ablation D1; không thêm heuristic preprocessing trước khi xác định model hay retrieval/prompt là bottleneck.
3. Mở rộng human calibration D1 cho grounding, ưu tiên negation/refutation, số/liều và câu hành động ngắn; chỉ sau đó mới khóa provisional gate.
4. Regenerate full T3 theo contract đã khóa; chạy self-consistency, judge-bias tests và human calibration. Không gọi paid judge trước khi contract ổn định.
5. Audit 74 mẫu finetune chứa boilerplate “mặt nạ nghệ” và kiểm tra regurgitation/off-topic trước khi kết luận chất lượng model.

## Artifact index

- Threshold labels: `evaluation/configs/grounding_d1_manual_labels.json`
- Threshold report: `evaluation/reports/unit/grounding_threshold/20260717T122004Z/report.json`
- Context sensitivity: `evaluation/reports/unit/context_sensitivity/20260717T122510Z/report.json`
- Structure probe: `evaluation/reports/unit/structure_prompt_probe/20260717T122041Z/report.json`
- Legacy recompute: `evaluation/reports/round2_legacy_grounding_d1_20260717T125908Z/report.json`
- Clean model smoke/report/gate: `evaluation/reports/round2_smoke_20260717T124200Z/`
- Markerless S4 smoke/report: `evaluation/reports/round2_smoke_s4_markerless_20260717T131952Z/`
