# Evaluation refactor — evidence report

Generated: 2026-07-26 (Asia/Saigon)
Branch: `codex/simplify-chat-pipeline`

## Kết luận

Tại refactor baseline `6d2259b`, Phase A–H đã hoàn tất và các đường kiểm chứng
đều xanh: `Settings` còn 70 field, judge pointwise dùng
`openai/gpt-5.4-mini`, dashboard không còn ép provider/model/faithfulness model,
retrieval metrics và answer metrics có contract tách biệt, Unified Intake có
harness riêng. Checkout hiện tại đã có commit hậu kỳ `f51a710`; khác biệt config
của commit đó được ghi riêng trong phần correction v2 bên dưới.

**Kết luận nút thắt từ thí nghiệm 5 câu v1 là vô hiệu về mặt thiết kế thí
nghiệm.** Phần evidence refactor ở tài liệu này vẫn có giá trị, nhưng không được
dùng các số v1 để kết luận generator, intake hay retrieval là nút thắt:

- Arm X chạy trên D8 không có `intent_label`; code đã ép mọi mẫu thành
  `knowledge`, chỉ 2/5 mẫu có bất kỳ `user_context` nào. X chưa từng đo oracle
  intake mà đo tác hại của intent suy đoán và context hầu như rỗng.
- Arm Y v1 sinh ba candidate rồi dùng chính `quality_score` của judge để chọn
  candidate trung vị, trong khi Z/X/W chỉ có một candidate. Y là arm duy nhất
  được giảm phương sai bằng chính thước đo dùng để kết luận.
- W có n=4 do timeout còn các arm khác n=5; paired analysis v1 không dùng cùng
  một tập ID thành công.

Harness v2 đã sửa ba lỗi trên và rerun Z/W/Y trên cùng 5 ID D8. Kết quả mới chỉ
là tín hiệu định hướng: Y tăng answer quality nhưng giảm grounding; W tăng
role/tone nhưng grounding không có hướng tăng nhất quán. D8 không có nhãn intake
nên X fail-fast và mặt refusal fidelity không đo được. Chưa có file chấm tay 40
mẫu, vì vậy các mặt do judge chấm **chưa đủ điều kiện để ra kết luận nút thắt**.
Không chạy full trước khi B3 có nhãn intake và judge agreement đạt ngưỡng.

## Commits và line delta theo phase

| Phase | Commit | Files | Added | Deleted |
|---|---|---:|---:|---:|
| A | `755931e` | 15 | 80 | 471 |
| B | `2078eb6` | 6 | 41 | 31 |
| C | `a5dbe25` | 31 | 51 | 374 |
| D | `a67d823` | 3 | 69 | 7 |
| E | `f091863` | 1 | 126 | 0 |
| F | `984411c` | 5 | 1,292 | 25 |
| F correction | `9bd9dee` | 1 | 22 | 8 |
| G | `94fc99f` | 3 | 130 | 0 |
| H | `bac8a00` | 20 | 298 | 47 |
| H cleanup | `cd339b1` | 4 | 4 | 15 |
| Final docs | `c8f8837` | 4 | 300 | 11 |

Chi tiết file/dòng từ `git show --numstat`:

### Phase A

```text
.env.baseline +24/-100
config/settings.py +0/-4
evaluation/adapters/extractive.py +9/-3
evaluation/probe/semantic_probe.py +1/-4
evaluation/unit/eval_context_sensitivity.py +8/-3
scripts/build_kb.py +1/-1
scripts/eval_rag.py +5/-2
scripts/probe_intent_runtime.py +3/-5
src/acne_llm/chat/_retrieval.py +1/-2
src/acne_llm/chat/session.py +2/-0
src/acne_llm/config.py +9/-42
src/acne_llm/di.py +5/-5
src/acne_llm/di.py.bak.20260529 +0/-296
src/acne_llm/rag/retriever.py +11/-2
src/acne_llm/utils/logging.py +1/-2
```

### Phase B

```text
evaluation/dashboard/scripts/run_preliminary_d2.py +5/-6
evaluation/judges/bias_tests.py +4/-5
evaluation/judges/clients.py +10/-3
evaluation/judges/run_judge.py +5/-6
evaluation/run_all.py +3/-4
evaluation/tests/test_judge_openai.py +14/-7
```

### Phase C

```text
datagen/render_context.py +2/-4
datagen/test_gates.py +2/-2
evaluation/README.md +1/-1
evaluation/adapters/ollama_batch.py +0/-1
evaluation/analysis/check_gate.py +0/-8
evaluation/analysis/error_attribution.py +2/-4
evaluation/analysis/recompute_grounding.py +1/-2
evaluation/analysis/report.py +3/-31
evaluation/datasets/registry.py +1/-1
evaluation/judges/prompts/error_classify.md +1/-1
evaluation/judges/run_judge.py +2/-6
evaluation/metrics/deterministic.py +1/-124
evaluation/metrics/grounding.py +4/-4
evaluation/tests/test_eval_debug_fixes.py +4/-84
evaluation/tests/test_metrics.py +2/-23
evaluation/tests/test_validation_harness_fixes.py +0/-1
evaluation/unit/eval_context_sensitivity.py +2/-10
evaluation/validate/audits/metric_audit.py +0/-1
evaluation/validate/audits/runtime_vs_eval.py +1/-1
evaluation/validate/checks/invariants.py +2/-2
evaluation/validate/checks/judge.py +1/-5
evaluation/validate/checks/runtime.py +0/-1
evaluation/validate/conflict.py +1/-17
scripts/build_hybrid_finetune_dataset.py +3/-12
scripts/clean_acne_chat_response.py +2/-2
scripts/eval_rag.py +8/-8
src/acne_llm/chat/_prompt.py +1/-1
src/acne_llm/config.py +0/-8
src/acne_llm/llm/prompt_builder.py +1/-5
tests/test_eval_rag_e2e.py +1/-1
tests/test_prompt_builder.py +2/-3
```

### Phase D–G

```text
D  evaluation/analysis/report.py +67/-5
D  evaluation/metrics/deterministic.py +1/-1
D  evaluation/metrics/retrieval.py +1/-1
E  evaluation/metrics/intake.py +126/-0
F  evaluation/configs/experiments/multiturn_e2e.yaml +20/-0
F  scripts/eval_bottleneck.py +644/-0; correction +22/-8
F  scripts/eval_extraction.py +89/-25
F  scripts/eval_semantic_router.py +67/-0
F  scripts/eval_unified_intake.py +472/-0
G  evaluation/tests/test_eval_unified_intake.py +68/-0
G  evaluation/tests/test_intake_metrics.py +29/-0
G  tests/test_env_keys.py +33/-0
```

### Phase H

```text
evaluation/analysis/check_gate.py +4/-1
evaluation/analysis/report.py +25/-2
evaluation/configs/gate.yaml +1/-0
evaluation/dashboard/README.md +1/-1; cleanup +1/-2
evaluation/dashboard/app/api/results/route.ts +5/-1
evaluation/dashboard/app/api/status/route.ts +1/-1; cleanup +1/-1
evaluation/dashboard/app/results/page.tsx +4/-0
evaluation/dashboard/components/DashboardClient.tsx +1/-1
evaluation/dashboard/components/ResultsClient.tsx +129/-0
evaluation/dashboard/components/RunsClient.tsx +36/-3
evaluation/dashboard/lib/command-ids.ts +2/-0
evaluation/dashboard/lib/commands.ts +13/-10; cleanup +1/-8
evaluation/dashboard/lib/inspect.ts +0/-10
evaluation/dashboard/lib/types.ts +2/-0
evaluation/dashboard/scripts/run_preliminary_d2.py +1/-1
evaluation/dashboard/tests/commands.test.ts +29/-12; cleanup +1/-4
evaluation/dashboard/tests/gates.test.ts +14/-2
evaluation/dashboard/tests/judge-calibration.test.ts +2/-2
evaluation/dashboard/tests/paths.test.ts +4/-0
evaluation/tests/test_eval_debug_fixes.py +24/-0
```

## Acceptance evidence

| Check | Kết quả |
|---|---|
| Phase A full pytest gate | `537 passed, 1 xfailed` |
| Phase A judge setting | `gpt-5.4-mini` |
| Phase A behavior probe | Pre/post pipeline response byte-identical; verifier trả equality true. |
| Final full pytest | `539 passed, 1 xfailed in 31.72s` |
| Dashboard tests | `23 passed, 0 failed` |
| Dashboard production build | Next.js 15.5.20 compiled, type-check và 10/10 static pages xanh. |
| Config field count | `len(Settings.model_fields) == 70` |
| Env template secrets | 4/4 secret placeholders rỗng. |
| Judge lineage | Bottleneck artifact: `judge_provider=openai`, `judge_model=gpt-5.4-mini`. |
| Arm Y lineage | `generator_model=gpt-5.6-terra`, khác judge. |
| Dashboard old judge grep | `gpt-5-mini`: 0 active dashboard hits. |
| Dashboard citation grep | 0 hits trong `app/`, `components/`, `lib/`. |
| Metric boundary | `retrieval.py` chỉ nhận retrieved/relevant/grades/texts; `deterministic.py` không nhận qrels. |
| W oracle boundary | Runtime log: `mode=hybrid`, real RAG `status=skipped`; scored rows có `retrieval_source=oracle_qrels`, 3 qrel chunks. |

`judge_cache.sqlite` đã được restore về HEAD sau paid runs; benchmark không để
cache sinh tự động lẫn vào diff.

## Bottleneck experiment correction v2

- Harness commit: `467136f`; runtime checkout khi rerun: `f51a710`.
- Dataset: `evaluation/datasets/v1/d8_qrels_seed.jsonl`, đúng 5 ID
  `d8-0001,d8-0003,d8-0004,d8-0006,d8-0008`.
- Question fingerprint giữ nguyên:
  `fae85439bbf04b3ac56d1e1d1f9b4828a0d41b216badc571b83756c6d7c8a92b`.
- Dataset fingerprint mới (bao gồm labels/qrels):
  `468783581d5a485a0feb9ede709a6269d5273a1184ef163607292df405c93cdd`.
- Artifact v2 SHA-256:
  `18f35c0b1d21c04f254c5436cdfc10f0c7141ea6710bda357552e6f8a6890f7d`.
- Judge bị khóa và ghi provenance là `openai/gpt-5.4-mini`; generator Y là
  `gpt-5.6-terra`. Y không nhận `temperature=0`, nên sinh ba lần ở temperature
  mặc định nhưng luôn lấy `candidate[0]`; cả 15 candidate-score pairs vẫn được
  giữ trong trace.
- Z/W/Y đều 5/5, không mẫu nào cần retry, `paired_n=5`, `dropped_ids=[]`, và
  không arm nào fail safety. X trên D8 dừng trước model/judge, exit code 1 và
  không tạo artifact.

| Arm | Grounding median | Answer quality median | Role/tone median | Safety fail | Median latency |
|---|---:|---:|---:|---:|---:|
| Z | 0.6000 | 4.0 | 4.0 | 0 | 46,325 ms |
| W | 0.6667 | 4.0 | 5.0 | 0 | 39,423 ms |
| Y | 0.4286 | 5.0 | 5.0 | 0 | 31,773 ms |

Paired delta theo từng mặt:

| Arm−Z | Mặt | Median delta | Tăng/Giảm/= | Paired n |
|---|---|---:|---:|---:|
| W−Z | grounding | 0.0000 | 1/2/2 | 5 |
| W−Z | answer quality | 0.0 | 2/0/3 | 5 |
| W−Z | role/tone | +1.0 | 3/0/2 | 5 |
| W−Z | safety gate | không lấy trung bình | fail 0→0 | 5 |
| Y−Z | grounding | −0.1176 | 2/3/0 | 5 |
| Y−Z | answer quality | +1.0 | 5/0/0 | 5 |
| Y−Z | role/tone | +1.0 | 4/0/1 | 5 |
| Y−Z | safety gate | không lấy trung bình | fail 0→0 | 5 |

Mặt refusal fidelity có `paired_n=0` ở cả ba arm vì D8 không có
`intent_label`; harness không suy đoán nhãn thay thế. `judge_agreement.py` đã
được test với 40 dòng chia đều 10 dòng mỗi arm, xuất blind review + key riêng và
báo cáo overall/Y riêng. Chưa có nhãn người thật, nên agreement thực tế vẫn chờ.

So với artifact v1 `ec955c00…`, các số cũ không cùng scorecard/scale nên không
được trừ trực tiếp. Thay đổi riêng của Task 1 được kiểm bằng trace: mọi row Y có
`selected_candidate_index=0`; trong rerun này cả ba candidate của mỗi câu đều
được judge chấm `(answer_quality=5, role_tone=5)`, nên bỏ median-selection
**không làm đổi điểm Y trong chính cohort v2 này**. Việc old Y chỉ tăng 2/5 trên
`quality_score` còn new Y tăng 5/5 trên `answer_quality` đến từ prompt/scale
scorecard mới và generation mới, không thể quy nhân quả cho Task 1.

Lưu ý checkout: commit `f51a710` được thêm sau harness commit và làm
`Settings.model_fields` từ 70 thành 85, đồng thời bỏ `judge_provider/judge_model`.
Full pytest tại harness commit sạch là `539 passed, 1 xfailed`; full pytest ở
HEAD `f51a710` là `538 passed, 1 xfailed, 1 failed` tại `test_env_keys.py` vì
`JUDGE_PROVIDER` trong `.env` thành key mồ côi. Harness v2 truyền judge lineage
tường minh nên artifact trên không dùng nhầm fallback, nhưng regression config
này cần được xử lý riêng, ngoài phạm vi brief thí nghiệm.

## Bottleneck protocol và artifact v1 — lịch sử, đã vô hiệu

- Dataset: `evaluation/datasets/v1/d8_qrels_seed.jsonl`.
- Stable IDs: `d8-0001,d8-0003,d8-0004,d8-0006,d8-0008`.
- Lý do chọn: cả ba qrel chunk của từng mẫu còn tồn tại trong KB hiện tại.
  D8 tổng thể có nhãn cũ/stale; chỉ 24/100 mẫu có toàn bộ qrel IDs trong Chroma,
  nên không được chọn 5 dòng đầu một cách mù quáng.
- Question fingerprint:
  `fae85439bbf04b3ac56d1e1d1f9b4828a0d41b216badc571b83756c6d7c8a92b`.
- Artifact SHA-256:
  `ec955c0005a6db6402ecd1bc6d4958cf3d9bd77add28df7cf8508196d84d1d43`.
- Z/X/W local: `temperature=0`; Y: temperature unsupported, ba candidates/mẫu,
  chọn candidate có judge score trung vị. Đây là lỗi thiết kế đã vô hiệu kết quả.

| Arm | Success | Median quality | Median delta vs Z | Tăng/Giảm/= | Paired n | Safety fail | Median latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| Z | 5/5 | 4.0 | 0.0 | 0/0/5 | 5 | 0 | 37,815 ms |
| X | 5/5 | 3.0 | 0.0 | 0/2/3 | 5 | 0 | 26,406 ms |
| Y | 5/5 | 4.0 | 0.0 | 2/0/3 | 5 | 0 | 27,924 ms |
| W | 4/5 | 3.0 | 0.0 | 1/1/2 | 4 | 0 | 26,231 ms |

Paired delta từng câu:

| Sample | X−Z | Y−Z | W−Z |
|---|---:|---:|---:|
| `d8-0001` | 0 | +1 | 0 |
| `d8-0003` | −1 | 0 | −1 |
| `d8-0004` | 0 | +2 | +1 |
| `d8-0006` | 0 | 0 | infra timeout |
| `d8-0008` | −1 | 0 | 0 |

Arm Y cải thiện rõ nhất ở câu về benzoyl peroxide cho da nhạy cảm và câu về
nguy cơ sẹo do mụn nặng. Arm X không giúp quality dù nhanh hơn. W không có hướng
tăng nhất quán và còn một generator timeout, nên oracle RAG chưa chứng minh được
retrieval là nút thắt.

Một cold Z run trước bản artifact cuối chỉ thành công 1/5; log ghi reranker load
fail do Windows paging file error 1455 và bốn local generation timeout. Warm Z
rerun thành công 5/5 và đã ghi đè baseline cuối. Đây là bằng chứng reproducibility
vận hành còn nhạy với memory/model warm state; không được bỏ qua khi mở full run.

Chi phí judge được ghi trong các summary hiện tại tổng cộng `$0.018402`; đây là
cost của rows hiện còn trong artifact và có thể thấp do cache hit, không phải hóa
đơn tổng của mọi smoke/rerun đã thực hiện.

## Mâu thuẫn và phần cố ý giữ lại

1. Brief ghi `.env` mục tiêu 16 key nhưng danh sách tường minh chỉ có 15. `.env`
   và `.env.baseline` giữ đúng 15 key được liệt kê; không thêm key giả.
2. Không có field trong nhóm 8 đỏ + 5 xanh + 3 citation bị giữ lại. Hai floor cũ
   cũng đã gộp thành `chat_rerank_floor`.
3. `extractor_*` và `router_*` được giữ đúng ràng buộc để chạy legacy A/B.
4. Tên `retrieve_top_k` còn xuất hiện như **experiment-local override** trong
   YAML/adapter, đúng yêu cầu A2; không còn là `Settings` field. Không có tham
   chiếu `settings.<deleted_field>` trong active code.
5. Literal citation không còn trong active metric/dashboard path. `gold_citations`
   vẫn tồn tại trong frozen/draft dataset artifacts và `datasets/generate_drafts.py`
   (file ngoài phạm vi), còn report cũ giữ lịch sử provenance. Không rewrite
   frozen data hoặc historical reports chỉ để làm grep đẹp.
6. Hai giá trị còn có hai biểu diễn có chủ ý:
   `_DENSE_MAX_DISTANCE=0.60` là default caller trực tiếp/test nhưng production
   nhận `settings.dense_max_distance`; test khóa equality. `JUDGE_WORKERS=4` ở
   dashboard được giữ theo yêu cầu H1 dù Python cũng có default worker riêng.
   Literal faithfulness model trùng trong TypeScript đã được xóa; Python hiện là
   nguồn duy nhất cho default đó.

## Artifacts để review

- `evaluation/reports/bottleneck/results.json`: raw rows, answers, trace,
  per-arm summary và paired distribution.
- `docs/config_layout.md`: quy tắc ownership + 15 env keys + 70 fields.
- `docs/config_reference.md`: reference hiện hành của toàn bộ 70 fields.
