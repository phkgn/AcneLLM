# Eval report — 2026-07-17T13:21:47.531348+00:00

## Per-system

> `empty_core_fields_rate` là rate of True: True = causes và recommendations đều rỗng; None bị loại khỏi mẫu số. Đây không phải pass rate và cũng không khẳng định rendered answer không có chữ.

> Grounding dùng mẫu số câu đủ điều kiện; câu hỏi, lời chào và disclaimer chuẩn được loại. Citation chỉ còn là metric legacy để đọc artifact cũ.

| system | n_judged | n_generated | ok | parse | empty_core_fields_rate | grounded_sentence_rate | grounded/eligible | legacy_cite_valid_all_required | preg_safety | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s4 | 0 | 3 | 1.0 | None | None | 0.9577 | 68/71 | 0.0 | 1.0 | None | None | None | 10518 |

## Pre-registered comparisons


## Error Pareto per system

- **s4**: 