# Eval report — 2026-07-17T13:00:14.335821+00:00

## Per-system

> `empty_core_fields_rate` là rate of True: True = causes và recommendations đều rỗng; None bị loại khỏi mẫu số. Đây không phải pass rate và cũng không khẳng định rendered answer không có chữ.

> Grounding dùng mẫu số câu đủ điều kiện; câu hỏi, lời chào và disclaimer chuẩn được loại. Citation chỉ còn là metric legacy để đọc artifact cũ.

| system | n_judged | n_generated | ok | parse | empty_core_fields_rate | grounded_sentence_rate | grounded/eligible | legacy_cite_valid_all_required | preg_safety | faithful | judge_correct | judge_safety | p50_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s2 | 0 | 3 | 1.0 | 1.0 | 0.6667 | 0.5 | 7/14 | 0.0 | 1.0 | None | None | None | 40656 |
| s3 | 0 | 3 | 1.0 | 1.0 | 0.0 | 0.2 | 5/25 | 0.0 | 1.0 | None | None | None | 60020 |
| s3_inline_model | 0 | 3 | 1.0 | 1.0 | 0.0 | 0.4444 | 8/18 | 0.0 | 1.0 | None | None | None | 35036 |
| s4 | 0 | 3 | 1.0 | None | None | 0.9577 | 68/71 | 1.0 | 1.0 | None | None | None | 10396 |

## Pre-registered comparisons

### s2:s3 (n=0)
- pregnancy_safety McNemar: n01=0 n10=0 p=1.0

## Error Pareto per system

- **s2**: 
- **s3**: 
- **s3_inline_model**: 
- **s4**: 