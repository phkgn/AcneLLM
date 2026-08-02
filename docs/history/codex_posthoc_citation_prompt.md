# Nhiệm vụ: Chuyển citation sang post-hoc attribution + làm rõ confound structured-output (AcneLLM, vòng 2)

Bạn là debugging agent tiếp nối vòng 1. BẮT BUỘC đọc trước:
`evaluation/reports/debug_findings_20260717.md` — vòng 1 đã fix citation resolver,
faithfulness context capture, và làm rõ semantic `empty_core_fields_rate`.

## Quyết định kiến trúc đã chốt (bối cảnh — không bàn lại)

Model-emitted citation là ngõ cụt với model hiện tại. Bằng chứng:

- Finetune data `data/finetune/cleanv3/acne_chat_response.train.jsonl`:
  **0/41.849** assistant output chứa marker `[n]` — model chưa bao giờ học cite.
- Prompt production (`config/prompts/hybrid_user.j2:16`, `stream_user.j2:24`,
  `knowledge_user.j2:12`) yêu cầu "Đặt [N] sau mỗi claim" nhưng model chỉ tuân thủ
  tối thiểu: dán đúng một `[1]` cuối toàn bộ answer, thường trỏ vào chunk không
  liên quan (quan sát thực tế trên production chat).
- Vòng 1: S3 chỉ 63/140 câu bắt buộc cite là có cite; 7/63 bịa ID/sai index;
  S2 = 0/140 record có citation.

**Quyết định**: bỏ hoàn toàn cơ chế model tự cite. Citation từ nay do CODE gắn
post-hoc: align từng câu của answer với `used_chunks` bằng similarity, gắn `[N]`
(prose) hoặc `chunk_ref` (structured) một cách deterministic. Model chỉ lo trả lời.

## Việc 1 — Implement module post-hoc attribution (task chính)

### Thiết kế

Module mới `src/acne_llm/attribution.py` (hoặc vị trí hợp lý theo cấu trúc repo):

1. **Tách câu** answer thành sentences (tiếng Việt: tách theo `.`, `!`, `?`, xuống
   dòng; cẩn thận viết tắt kiểu "0.1%", "BS.", số thập phân). Loại khỏi attribution:
   disclaimer chuẩn, câu hỏi ngược lại người dùng, câu chào.
2. **Chấm điểm** mỗi sentence với mỗi chunk trong `used_chunks` bằng hybrid score:
   - lexical: character n-gram overlap hoặc ROUGE-L (bắt trích gần nguyên văn) —
     so trên bản đã normalize (lowercase, bỏ dấu) để chịu được typo/dấu;
   - semantic: cosine embedding — DÙNG LẠI embedder sẵn có trong repo (cái đang
     phục vụ Chroma/OOD centroid, xem `config/` và `src/acne_llm/`), không thêm
     dependency mới;
   - score cuối = max hoặc weighted combination (chọn và ghi rõ lý do).
3. **Gắn citation**: sentence có best score ≥ threshold → gắn chunk đó; dưới
   threshold → KHÔNG gắn, và sentence được ghi vào `trace.unsupported_sentences`.
   Một sentence chỉ gắn tối đa 1 chunk (chunk best); nếu sau này cần multi-cite
   thì để TODO, không làm vội.
4. **Hai đường tích hợp**:
   - **Prose/SSE** (`stream`, chat production): strip mọi marker `[n]` model tự
     sinh ra khỏi answer trước, rồi gắn `[N]` mới sau mỗi sentence được attribute.
     Mapping N → chunk giữ đúng thứ tự chunks đưa vào context (khớp UI hiện tại).
   - **Structured** (AdviseOutput, S3 batch): điền `chunk_ref` của từng
     cause/recommendation từ attribution (align text của item đó với chunks),
     bỏ qua/ghi đè giá trị model tự điền.
5. **Prompt cleanup**: gỡ instruction "Đặt [N]..." khỏi các template j2 (model
   không cần cố cite nữa — instruction chỉ gây nhiễu). Đây là thay đổi có chủ đích
   đã được duyệt.
6. **Flag config**: `citation_mode: posthoc | model | off` (default `posthoc`),
   để A/B và rollback được. `model` = hành vi cũ nguyên vẹn.
7. **Trace đầy đủ**: mỗi record ghi lại per-sentence: text, best chunk, score,
   cited hay không — để eval và debug đọc được.

### Threshold — tune đúng luật

- Threshold và mọi lựa chọn scoring CHỈ được tune trên **D1 dev**
  (`evaluation/datasets/v1/d1_dev_seed.jsonl`), TUYỆT ĐỐI không đụng D2/D4/D8
  (invariant `evaluation/README.md` mục 4).
- Viết script sweep nhỏ: chạy attribution trên answers sẵn có của D1 smoke
  (hoặc generate mới ≤ 10 case Ollama local), in bảng threshold vs
  (coverage, precision ước lượng bằng đọc tay 10-15 sentence). Chọn threshold,
  ghi số liệu vào report.

### Unit tests (bắt buộc, viết test fail trước khi code)

- Exact quote từ chunk → cite đúng chunk đó.
- Paraphrase gần → cite đúng chunk (dùng fixture embedder hoặc mock).
- Sentence không liên quan chunk nào → không cite + vào `unsupported_sentences`.
- Strip đúng marker `[n]` cũ của model, không phá số/phần trăm ("0.1%", "15-20 phút").
- Structured path: `chunk_ref` chỉ chứa canonical id có thật trong `used_chunks`.
- Case biết-là-giới-hạn: chunk trích myth rồi bác bỏ (xem `d2-0028-typo43` vòng 1)
  — similarity sẽ align sai. Viết test document hành vi này (xfail hoặc assert
  hành vi hiện tại + comment), ghi vào report là known limitation cần NLI/LLM
  ở vòng sau.

## Việc 2 — Cập nhật eval harness theo hợp đồng citation mới

1. `evaluation/metrics/deterministic.py`: với record `citation_mode=posthoc`,
   `citation_valid` luôn true by construction — metric có nghĩa giờ là:
   - `attribution_coverage_rate`: % sentence (đủ điều kiện) được gắn citation;
   - `unsupported_sentence_rate`: % sentence không align được — đây chính là
     proxy faithfulness deterministic, miễn phí;
   Thêm 2 metric này vào `evaluate_record` + report + gate (ngưỡng đặt tạm,
   đánh dấu provisional, KHÔNG tune trên D2).
2. Artifact CŨ (model-emitted): giữ nguyên metric cũ để đọc lại được, nhưng thêm
   rule: answer prose mà toàn bộ citation chỉ là một `[1]` duy nhất ở cuối →
   đếm là `citation_present=false` (nó là decorative, đã có bằng chứng).
3. Không sửa/ghi đè bất kỳ file nào trong `evaluation/reports/` cũ.

## Việc 3 — Chẩn đoán nhanh S2 zero-citation (rút gọn, ≤ 1 giờ)

Post-hoc thay thế tương lai, nhưng vẫn cần biết vì sao S2 = 0/140 để loại trừ
parser bug ảnh hưởng field khác:

1. Diff `evaluation/configs/systems/s2.yaml` vs `s3.yaml` (prompt, schema, options).
2. Đọc 5 raw response S2 trong `s2.results.jsonl`: model có nhắc nguồn dạng text
   mà parser drop không?
3. Kết luận 1 đoạn: (a) prompt thiếu instruction, (b) parser drop, (c) model lờ.
   Nếu (b) → fix vì có thể ảnh hưởng field khác; (a)/(c) → chỉ ghi nhận, không fix
   (đường model-cite sắp bỏ).

## Việc 4 — Chứng cứ cho quyết định "hợp đồng eval" (KHÔNG tự quyết)

Confound: empty_core_fields_rate S0=0.99, S2=1.0, S1=0.5, S3=0.0 — so sánh 2×2
đang đo lẫn "tuân JSON schema" với "chất lượng nội dung". Hai hướng:
(a) judge mọi condition trên rendered prose, structured metrics chỉ áp cho S3;
(b) sửa prompt để base model cũng điền được structure.

Nhiệm vụ: THU THẬP CHỨNG CỨ, người dùng quyết:

1. Đọc 15 record S0 + 15 record S2 (cả empty lẫn non-empty nếu có): nội dung thật
   nằm ở đâu (disclaimer? rendered text?), chất lượng khi đọc như prose?
2. Xác định rendered answer judge đang chấm build từ field nào
   (`evaluation/adapters/ollama_batch.py` / render code). Rendered text đủ nội dung
   bất kể core fields rỗng → hướng (a) rẻ và sạch. Rendered text cũng nghèo →
   điểm judge S0/S2 đang bị kéo theo, nêu rõ.
3. Probe hướng (b): thử 1-2 biến thể instruction (few-shot JSON, field description
   rõ hơn) CHỈ trên D1 dev, ≤ 10 case Ollama local. Báo empty-core-fields rate
   trước/sau.
4. Memo ≤ 1 trang: trade-off (a)/(b), khuyến nghị + lý do, những gì phải chạy lại
   theo mỗi hướng.

## Việc 5 — Smoke test tổng hợp

Chạy smoke generation mới (run dir MỚI, không ghi đè):
`python -m evaluation.runners.run_experiment --experiment
evaluation/configs/experiments/main_2x2.yaml --systems s2,s3,s4 --limit 3
--dataset evaluation/datasets/v1/d1_dev_seed.jsonl` (hoặc tương đương). Xác nhận:

- fix vòng 1 hoạt động: record có `trace.faithfulness_context` đúng; S4 không cắt
  giữa câu;
- attribution mới chạy end-to-end: prose có `[N]` do code gắn, structured có
  `chunk_ref` hợp lệ 100%, trace có per-sentence scores;
- `citation_mode: model` vẫn tái tạo hành vi cũ (flag hoạt động);
- metric mới (`attribution_coverage_rate`, `unsupported_sentence_rate`) xuất hiện
  trong report của smoke run.

## Ràng buộc

- Ollama local: chỉ smoke ≤ 10 case/hệ và probe D1. KHÔNG chạy full 140.
- KHÔNG gọi paid API judge.
- KHÔNG sửa `evaluation/datasets/v1/`, KHÔNG sửa/ghi đè `evaluation/reports/` cũ.
- KHÔNG tune threshold/prompt trên D2 — mọi tuning trên D1 dev.
- Không thêm dependency mới (embedder dùng lại của repo; ROUGE/n-gram tự viết
  hoặc stdlib).
- Mỗi fix/feature kèm unit test viết-fail-trước. Chạy full
  `pytest evaluation/tests -q` (và test suite của `src/` nếu có) trước khi kết thúc.
- Production code (`src/acne_llm/`) thay đổi tối thiểu, mọi hành vi mới sau flag
  `citation_mode`, default có thể đổi lại `model` bằng 1 dòng config.

## Deliverable

`evaluation/reports/debug_findings_20260717_round2.md`:

1. Việc 1: thiết kế attribution (scoring, threshold + số liệu sweep D1, sentence
   segmentation), diff tóm tắt, danh sách test, known limitations (myth/negation case).
2. Việc 2: metric mới + rule trailing-[1], số recompute được trên artifact cũ nếu có.
3. Việc 3: kết luận S2 zero-citation (1 đoạn, phân loại a/b/c).
4. Việc 4: memo trade-off (a)/(b) + số liệu probe D1.
5. Việc 5: kết quả smoke — bằng chứng từng mục pass/fail.
6. Việc còn lại cho vòng 3 (dự kiến: regenerate full T3 với posthoc citation,
   judge self-consistency + bias tests, human calibration, audit boilerplate
   finetune data — 74 mẫu "mặt nạ nghệ" đã phát hiện model regurgitate off-topic).
