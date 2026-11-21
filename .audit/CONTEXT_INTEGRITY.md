---
title: AcneLLM Context Integrity Protocol
tags:
  - acnellm
  - provenance
  - context-integrity
status: canonical-policy
as_of: 2026-08-25
---

# Context integrity protocol

Protocol này giúp một người hoặc AI đọc vault mà không trộn code truth, report
cũ, kế hoạch và giả định thành cùng một loại fact.

## Thứ tự nguồn thắng

1. Live source/config/runtime artifact tại đúng thời điểm câu hỏi.
2. Test/probe/hash được chạy trên cùng source state.
3. [[CURRENT_TRUTH]] và [[SAFE_REMEDIATION_TASKS]].
4. Current immutable snapshot `runs/20260825T090826Z/**`, then the historical
   pre-remediation snapshot `runs/20260822T152307Z/**`.
5. Comment/doc/report/notebook lịch sử.
6. Roadmap hoặc proposal chưa triển khai.

Nguồn hạng thấp không được ghi đè nguồn hạng cao. Một report pass không chứng
minh runtime SSE nếu report chỉ chạy batch/T3.

## Bốn nhãn bắt buộc

- `verified-current`: đã đối chiếu current source/evidence.
- `historical`: đúng ở snapshot ghi rõ ngày/run id.
- `planned`: ý định, chưa phải behavior.
- `unknown`: chưa đủ bằng chứng; không được lấp bằng suy đoán.

## Quy tắc bảo toàn thời gian

- Không sửa nội dung trong immutable run để làm nó có vẻ current.
- Mỗi remediation tạo delta note và trỏ `supersedes` tới claim cũ.
- Mỗi evaluation ghi source state/model/config/artifact hash.
- Nếu working tree dirty, commit SHA không đủ; phải giữ status/diff fingerprint.
- Binary/cache/database chỉ là evidence khi có provenance và thời điểm rõ.

## Quy tắc cập nhật vault

Khi code thay đổi:

1. Ghi file/symbol/contract bị tác động.
2. Ghi behavior impact: none, metadata-only, fallback-only hoặc answer-changing.
3. Chạy test phù hợp và ghi kết quả thật.
4. Xác định eval nào còn giá trị và eval nào cần rerun.
5. Cập nhật [[CURRENT_TRUTH]], [[RECONCILIATION]] và [[KNOWLEDGE_INDEX]].
6. Không rewrite historical notes; thêm liên kết superseded.

## Quy tắc đọc nhanh

Một phiên mới phải đọc theo thứ tự:

1. [[OBSIDIAN_HOME]].
2. [[CURRENT_TRUTH]].
3. [[SAFE_REMEDIATION_TASKS]].
4. [[FUTURE_BEHAVIOR_ROADMAP]].
5. Chỉ mở findings/snapshot theo module đang làm.

Thứ tự này giữ context đầy đủ nhưng tránh nạp hàng trăm finding cũ trước khi
biết kiến trúc hiện hành.
