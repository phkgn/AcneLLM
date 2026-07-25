# Semantic intent router Round 3 — 2026-07-19

## Kết luận

Round 3 đã được hiện thực đủ ba pha DATA → RUNTIME → EVAL trên worktree hiện
tại. Runtime chính dùng embedding local + weighted kNN cho `advise`,
`knowledge`, `clarify`; `reject` chỉ sinh từ ngưỡng khoảng cách OOS. OpenAI
không xuất hiện trong runtime.

Kết quả held-out:

- Semantic 3-class + OOS gate: **230/260 = 0.8846 accuracy**.
- Legacy rule trên cùng test split: **157/260 = 0.6038**.
- Baseline rule được handoff cung cấp: **0.7160**.
- In-scope recall tại ngưỡng đã chọn: **255/260 = 0.9808**.
- OOS: **85/125 = 0.6800 recall**, **0.9444 precision**.
- A/B/C/D qua `prepare_chat_turn`/`run_intake` thật: **4/4 đúng** trước và sau
  calibration.
- Regression cuối: **499 passed, 1 xfailed**.

Đánh giá: router semantic đạt mục tiêu chất lượng và bảo toàn in-scope. OOS
recall chưa cao; đây là trade-off chủ động để không chặn nhầm câu hợp lệ, đúng
ưu tiên của handoff. Không nên quảng bá con số 68% như một OOS detector hoàn
hảo.

## 1. DATA

### Nguồn và lọc

Nguồn duy nhất là `data/golden_extraction_gen.jsonl` (985 dòng).

- Loại `query_subject == "other"`: 136 dòng; còn 849.
- `reject` không đi vào classifier/index.
- Mỗi artifact classifier chỉ có đúng hai key `text`, `intent`.
- Với `advise` và `knowledge`, chỉ seed bằng `reliable=true`.
- Với lớp hiếm `clarify`, dùng 18 reliable + 21 unreliable theo ngoại lệ đã
  duyệt trong handoff.
- Một near-duplicate trong seed advise bị loại trước khi bù quota.

### Phân bố và split

| Artifact | advise | knowledge | clarify | reject | Tổng |
|---|---:|---:|---:|---:|---:|
| `intent_classify.jsonl` | 500 | 500 | 300 | 0 | 1,300 |
| `intent_classify.train.jsonl` | 400 | 400 | 240 | 0 | 1,040 |
| `intent_classify.test.jsonl` | 100 | 100 | 60 | 0 | 260 |
| `subject_oos_eval.jsonl` | 0 | 0 | 0 | 125 | 125 |

Train/test không có exact overlap. Router runtime chỉ nhận đường dẫn train;
test và OOS không nằm trong metadata/cache index.

### Sinh và QC

| Lớp | Seed giữ lại | Gen được nhận | Candidate model | Judge loại | Near-dup trước judge |
|---|---:|---:|---:|---:|---:|
| advise | 490 | 10 | 13 | 0 | 0 |
| knowledge | 199 | 301 | 427 | 121 | 2 |
| clarify | 39 | 261 | 382 | 120 | 0 |

OOS gồm 85 reject gốc + 40 câu OOS rõ ràng được sinh thêm. LLM judge chỉ duyệt
mẫu in-scope mới sinh; reject không được đưa thành lớp train.

Model generate/judge: `gpt-4o-mini`. Cost tracker tính prompt, cached prompt và
completion token theo usage thật của API, chặn trước request có thể vượt budget.

- Attempt đầu dừng đúng tại QC vì một seed duplicate: **$0.0479760**.
- Successful attempt: **$0.0468678**.
- Tổng chi phí thực tế: **$0.0948438 / $1.50 budget**.

Hashes:

| Artifact | SHA-256 |
|---|---|
| full | `3de84cda13a3fd163762576472fd1b26efcbb94e5c0a5416816a763e01bbd771` |
| train | `f7807449c1a9ebb5a0d6fd1a40d522d5893538e765e82135c357901d1b7bda7f` |
| test | `bc863e3fa93608f9509b8cca3b1a8828e9f8f6790faaa9366821ab868e65a70e` |
| OOS | `5b80767045985837b57d21bda586866e49e74414d04ae33d4f43452cc793f5cd` |

Chi tiết machine-readable:
`data/intent_classify.build_metrics.json`.

## 2. Runtime

### Router

Module mới: `src/acne_llm/chat/semantic_router.py`.

- Embedder: `AITeamVN/Vietnamese_Embedding`, local/offline, 1,024 chiều; dùng
  chính wrapper RAG hiện có thay vì thêm model thứ hai.
- Index: 1,040 train rows; cosine-normalized `float32`.
- Cache: `data/intent_router_index.npz`, keyed bởi train SHA-256, model name,
  path và schema version.
- `k=9`; vote có trọng số `max(cosine_similarity, 0)^2`.
- OOS chạy trước vote.
- Top-two vote margin dưới `0.08` ép về `clarify`.
- Output live:
  `source="semantic"`, `reason_code="semantic_router"`, confidence là cosine
  similarity của láng giềng gần nhất.
- Nếu model/index/query embedding lỗi, intake log lỗi và dùng
  `route_intent` legacy; lượt chat không vỡ.

### Tích hợp và OOS cũ

- `intake.py` gọi semantic router trên `clean_text`; rule router chỉ là fallback.
- DI luôn khởi tạo `GuardrailRunner(..., enable_ood=False)`.
- Config `guardrails_enable_ood`/`guardrails_ood_threshold` và bước attach
  `ood_centroid.json` đã khỏi live DI.
- `guardrails/ood_detector.py` vẫn còn cho PII helpers và compatibility/unit
  tests, nhưng centroid không quyết định OOS trên chat runtime.

### Bỏ subject

Active runtime không còn `query_subject`:

- `RouteDecision`/metadata không có subject.
- Memory fold, confirmed profile, snapshot và completeness gate bằng
  `primary_intent == "advise"`.
- Knowledge nhận hint không xem là hồ sơ cá nhân.
- SSE, debug trace và evaluation adapter không đọc/phát telemetry subject.
- Không thêm cờ `other`; rủi ro hỏi hộ làm bẩn profile được giữ đúng quyết định
  đã chốt.

`query_subject` chỉ còn trong nguồn golden/generator offline để thực hiện đúng
bước lọc 136 dòng, cùng các negative assertions xác nhận runtime không phát
field này. Các file `.bak`/tài liệu lịch sử không phải active runtime.

### Extractor

- `model/Modelfile.extractor` chỉ còn `context` + `clinical`; ba few-shot không
  có intent.
- `LLMExtractResult` chỉ có `user` + `confidence`.
- `_OLLAMA_JSON_SCHEMA` và validator reject root key ngoài hai section trên.
- Đã rebuild thật:
  `ollama create acne-extractor:1.5b -f model/Modelfile.extractor`.
- Artifact Ollama sau rebuild: ID `ccae33645582`, 986 MB.
- Probe model thật xác nhận `result_fields=['confidence','user']`,
  `has_route=false`.

Quan sát ngoài router: ở case knowledge B, extractor 1.5B vẫn có thể lặp field
clinical từ few-shot trong object nội bộ. Evidence gate làm
`routing_clinical=null`, semantic router chỉ đọc raw text, knowledge không
fold/snapshot, và prompt knowledge kiểm tra không chứa age/lesion giả. Vì vậy
Round 3 không bị sai route/prompt từ hiện tượng này; đây vẫn là điểm cần theo
dõi riêng nếu tiếp tục cải thiện extractor.

### Clarify và completeness

- Router `clarify`: template `clarify_user.j2`, completeness không chạy.
- Router `advise`: completeness chạy và runtime nối tối đa một
  `followup_question` field-specific.
- Prompt advise được lệnh không tự hỏi thêm khi runtime sẽ nối câu deterministic.
- Test SSE mới xác nhận mỗi nhánh chỉ phát đúng một dấu hỏi trong lượt kiểm thử,
  không double-ask.

### Hard guardrails

Không thay nội dung quyết định hard safety.

- `pre_check` và genital-only refusal dừng trước semantic embedding.
- Current-turn pregnancy/breastfeeding + retinoid/tetracycline và
  isotretinoin+tetracycline dừng trước router.
- Check thuốc thứ hai sau advise-only session fold vẫn giữ để bắt thuốc/thai kỳ
  đã xác nhận từ lịch sử.
- Regression thật dùng `GuardrailRunner` xác nhận semantic router không được gọi
  cho bốn case: pregnancy+tretinoin, breastfeeding+retinol,
  isotretinoin+doxycycline và genital-only.

## 3. Calibration và eval

### Ngưỡng OOS

Quét trên 260 test in-scope + 125 OOS. Điều kiện chọn: in-scope recall tối thiểu
0.98; trong các điểm đạt điều kiện, ưu tiên OOS recall rồi OOS precision.

| `tau_oos` | In-scope recall | False reject | OOS recall | OOS precision |
|---:|---:|---:|---:|---:|
| 0.398978 | 0.8385 | 42 | 0.9200 | 0.7325 |
| 0.420136 | 0.8885 | 29 | 0.9040 | 0.7958 |
| 0.441293 | 0.9269 | 19 | 0.8720 | 0.8516 |
| 0.459429 | 0.9538 | 12 | 0.8080 | 0.8938 |
| 0.480587 | 0.9769 | 6 | 0.6880 | 0.9348 |
| **0.483609** | **0.9808** | **5** | **0.6800** | **0.9444** |
| 0.498722 | 0.9846 | 4 | 0.5760 | 0.9474 |
| 0.519880 | 0.9885 | 3 | 0.5040 | 0.9545 |
| 0.541038 | 0.9923 | 2 | 0.3760 | 0.9592 |

Ngưỡng production chọn: **`tau_oos=0.483609`**.

Theo nguồn OOS tại ngưỡng này:

- 85 reject golden gốc: 54 reject đúng, recall 0.6353.
- 40 OOS rõ ràng sinh thêm: 31 reject đúng, recall 0.7750.

### Accuracy

| Hệ | Accuracy | Correct/total |
|---|---:|---:|
| Semantic kNN + selected OOS gate | **0.8846** | 230/260 |
| Legacy rule trên cùng split | 0.6038 | 157/260 |
| Rule baseline từ handoff | 0.7160 | — |

Semantic cao hơn stated baseline **+0.1686** và cao hơn rule hiện tại trên cùng
split **+0.2808**.

Per-class recall:

| Gold class | Recall | Correct/support |
|---|---:|---:|
| advise | 0.8400 | 84/100 |
| knowledge | 0.9400 | 94/100 |
| clarify | 0.8667 | 52/60 |

Confusion:

| Gold \ Pred | advise | knowledge | clarify | reject |
|---|---:|---:|---:|---:|
| advise | 84 | 13 | 0 | 3 |
| knowledge | 3 | 94 | 1 | 2 |
| clarify | 4 | 4 | 52 | 0 |

Margin `0.00` đến `0.08` cùng đạt accuracy trước OOS gate là 0.9000. Chọn
**0.08**, là margin dương lớn nhất không làm giảm held-out accuracy, để giữ
đúng contract “lưỡng lự → clarify”.

### Latency

Đo 385 query bằng local CPU, model/index đã load, cố ý bypass disk query cache để
đo embedding+kNN thật:

| Metric | ms |
|---|---:|
| Mean | 244.02 |
| Median | 233.65 |
| p95 | 338.44 |
| Max | 708.86 |

Cold build index lần đầu trên CPU mất khoảng 118 giây sau khi model load. Sau đó
NPZ cache hit; bước đọc/validate index quan sát khoảng 50 ms, còn load model
process mới khoảng 10–11 giây. Đây là startup cost, không phải per-turn cost.

Machine-readable curve/metrics:
`reports/semantic_router_eval_20260719.json`.

## 4. Runtime A/B/C/D trước và sau calibration

Trước: `k=9`, `tau=0.42`, margin `0.08`.
Sau: `k=9`, `tau=0.483609`, margin `0.08`.

| Case | Kết quả trước | Kết quả sau | Template sau | Completeness sau |
|---|---|---|---|---|
| A | advise, semantic | advise, semantic | `stream_user.j2` | chạy, level sufficient |
| B | knowledge, semantic | knowledge, semantic | `knowledge_user.j2` | skip |
| C | clarify, semantic | clarify, semantic | `clarify_user.j2` | skip |
| D | reject, semantic | reject, semantic | none | skip |

Case D có nearest distance `0.525348`, vượt cả ngưỡng cũ và mới. Calibration
không đổi A/B/C/D, nhưng giảm false reject toàn test split từ khoảng 29 tại
`tau≈0.42` xuống 5 tại ngưỡng chọn.

Artifacts:

- `reports/semantic_router_runtime_before_20260719.json`
- `reports/semantic_router_runtime_after_20260719.json`

## 5. Validation cuối

- `ollama create acne-extractor:1.5b -f model/Modelfile.extractor`: success.
- Extractor live output contract: chỉ `user`, `confidence`; không route/intent.
- Train index cache hit và hash khớp train artifact.
- `build_container` thật: semantic ready, 1,040 rows, cache hit,
  `k=9/tau=0.483609/margin=0.08`.
- A/B/C/D final với `--assert-expected`: 4/4.
- `python -m pytest -q` trong `.venv`: **499 passed, 1 xfailed in 28.36s**.
- `git diff --check`: pass.

Lưu ý môi trường: Python global có `torch 2.7.1+cu118` nhưng
`torchvision 0.20.1+cu121`, gây lỗi `torchvision::nms`. Không sửa dependency
global. Runtime/eval dùng đúng repo `.venv`, nơi `torch 2.5.1+cu121` và
`sentence-transformers 5.4.1` load model thành công.
