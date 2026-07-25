# Intent from extracted fields — round 2 (2026-07-19)

## Kết luận

Live routing không còn dùng `intent` do `acne-extractor:1.5b` dự đoán. Model vẫn
sản xuất intent trong JSON để debug/đánh giá contract, nhưng `run_intake` luôn gọi
`route_intent` trên text hiện tại và một bản clinical routing-only đã gate. Ba ca
runtime bắt buộc đều đi đúng intent, subject, reason code và template.

## Thay đổi runtime

- Bỏ `route_override_from_llm` khỏi live routing; `extracted.route` là advisory only.
- Dùng `settings.extract_min_field_conf` (0.60) để gate clinical của current turn.
- Router nhận một bản sao `UserInput` chứa clinical đã gate; `base_user` đầy đủ vẫn
  đi qua guardrail, fold, retrieval và prompt như trước.
- Vì model 1.5B gán confidence 0.8–0.9 cho few-shot leakage, current turn còn phải
  có case evidence độc lập từ extractor deterministic. Gate này chỉ là boolean;
  clinical truyền router vẫn chỉ chứa field model đủ confidence, không nhập nhãn
  rule và không đọc clinical đã fold từ history.
- Sửa hai lỗi text-rule được runtime test chứng minh: `con em` là `non_self`, và
  `mụn sữa` không phải food query chỉ vì chứa từ `sữa`.
- Giữ nguyên thứ tự pre-check, scope, complaint, reject, fold, medication refusal,
  clarify override và completeness.

## A/B/C runtime thật

Model được rebuild bằng:

```text
ollama create acne-extractor:1.5b -f model/Modelfile.extractor
```

| Case | Trước round 2 | Sau round 2 | Reason / template | Clinical dùng cho routing |
|---|---|---|---|---|
| A | `advise+self`, nhưng reason `llm_extractor` | `advise+self` | `personal_acne_case` / `stream_user.j2` | distribution=`cheeks`, inflammation=`moderate` |
| B | `knowledge+non_self`, nhưng reason `llm_extractor` | `knowledge+non_self` | `general_comparison_question` / `knowledge_user.j2` | `null` (hallucination bị lọc) |
| C | **sai:** `knowledge+non_self` | `advise+non_self` | `personal_acne_case` / `stream_user.j2` | model fields đủ confidence được giữ sau boolean case-evidence; subject vẫn do text rule |

Ở lần chạy cuối, cả ba lượt có `[sid] EXTRACTOR=llm ok`; route source là `rule`,
không có reason `llm_extractor`. A build clinical plan + snapshot và chạy
completeness. B/C không fold self profile; B dùng knowledge template.

Artifacts:

- Before: `reports/intent_from_fields_round2_before_20260719.json`
- Final: `reports/intent_from_fields_round2_final_20260719.json`

## Nguyên nhân và quá trình sửa

1. Vòng 1 gán thẳng `extracted.route`, nên sai lệch định nghĩa intent của model đi
   thẳng vào template/planner/session behavior. Đây là nguyên nhân C bị knowledge.
2. Gate confidence 0.60 đơn thuần chưa đủ. Ở B, model vẫn bịa
   `papule/pustule/chin/moderate` với confidence 0.8–0.9. Tăng threshold không thể
   tách B khỏi A vì khoảng confidence chồng lấn.
3. Few-shot knowledge được đổi cho khớp đúng câu B và model được rebuild, nhưng
   clinical leakage vẫn còn. Gate exact-label intersection ở lần thử đầu lọc B
   nhưng quá nghiêm: model và rule có thể gọi khác enum dù text là ca thật. Fix
   cuối là evidence gate boolean: current turn phải có case evidence, sau đó chỉ
   field model đạt confidence mới được truyền vào router.
4. Ở exact-label attempt, khi clinical model của C bị lọc sạch, router lộ lỗi
   `sữa` trong `mụn sữa` bị coi là food query và `con em` chưa được nhận là
   other-subject. Hai rule được sửa hẹp, có regression test riêng.

## Evaluation

### Baseline vòng 1 (985 rows)

| Pipeline | Primary intent | Query subject | Joint |
|---|---:|---:|---:|
| Raw model intent | 0.2558 | 0.4599 | 0.2305 |
| Rule fields/router | 0.7157 | 0.7117 | 0.6142 |

### Quick round 2 (50 rows)

| Pipeline | Primary intent | Query subject | Joint | Failures |
|---|---:|---:|---:|---:|
| Current rule | 0.8800 | 0.6800 | 0.6600 | 0 |
| Rule on gated LLM fields | 0.8800 | 0.6800 | 0.6400 | 0 |

### Full round 2 (985 rows)

| Pipeline | Primary intent | Query subject | Joint | Failures |
|---|---:|---:|---:|---:|
| Current rule | 0.7157 | 0.7330 | 0.6315 | 0 |
| Exact-label evidence attempt | 0.6640 | 0.7076 | 0.5817 | 0 |
| **Final: rule on boolean-evidence-gated LLM fields** | **0.7025** | **0.7249** | **0.6183** | **0** |

So với raw model intent vòng 1, pipeline cuối tăng **+0.4467 primary**,
**+0.2650 subject** và **+0.3878 joint**. So với rule vòng 1, primary thấp
0.0132 nhưng subject cao 0.0132 và joint cao 0.0041. So với current rule trên
revision cuối, cả ba chênh lần lượt -0.0132 / -0.0081 / -0.0132: đạt mục tiêu
"rất sát" mà không dùng lại intent model.

Full metric artifact cuối:
`reports/intent_from_fields_round2_full_final_985_20260719.json`. JSON ghi
`intent_pipeline=rule_on_confidence_gated_llm_fields`, threshold 0.60,
`rows=985`, đủ 985 nhãn intent/subject và `failures=0`, nên không thể nhầm với
raw model intent hoặc một run có fallback bị che.

## Verification

- Focused routing/extractor tests: 46 passed.
- Full regression cuối: **492 passed, 1 xfailed** in 31.83s.
- Real model/runtime A/B/C: all expected outputs matched.
- Full 985-row final model evaluation: 0 failures; **0.7025 / 0.7249 / 0.6183**.
