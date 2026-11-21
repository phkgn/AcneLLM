---
title: AcneLLM Knowledge Vault
aliases:
  - AcneLLM Home
  - AcneLLM Vault
tags:
  - acnellm
  - home
  - moc
status: canonical-entrypoint
as_of: 2026-08-25
---

# AcneLLM knowledge vault

Đây là entrypoint được thiết kế để mở trực tiếp trong Obsidian mà không mất
phân loại current/historical/planned.

## Đọc trong 10 phút

1. [[CURRENT_TRUTH]] — hệ thống hiện đang là gì.
2. [[RECONCILIATION]] — khác gì so với audit snapshot.
3. [[SAFE_REMEDIATION_TASKS]] — đã sửa gì và chứng minh bằng gì.
4. [[FUTURE_BEHAVIOR_ROADMAP]] — việc nào chưa được phép coi là đã làm.
5. [[KNOWLEDGE_INDEX]] — đi sâu vào module/research/eval/deploy.

## Nguyên tắc quan trọng

Snapshot `runs/20260825T090826Z/` là static capture của checkout hiện tại;
snapshot lớn `runs/20260822T152307Z/` là lịch sử trước remediation. Đọc
[[CONTEXT_INTEGRITY]] trước khi dùng finding cũ để ra quyết định code.

## Trạng thái ngắn

- Production architecture bề nổi đã thống nhất quanh một Unified Intaker.
- Semantic/rule fallback không gọi LLM.
- Full unit/integration suite: `495 passed, 1 xfailed in 53.86s` (2026-08-25).
- Static context gate: 837/837 path, 0 snapshot hash mismatch.
- Full behavior evaluation sau remediation: chưa chạy.
- Repo đang có pre-existing dirty worktree; không commit trong remediation.

## Chuẩn bị export

Xem [[OBSIDIAN_EXPORT_GUIDE]]. Giữ nguyên cây thư mục để standard Markdown
links, wikilinks và provenance path tiếp tục hoạt động.
