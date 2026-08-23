# Audit status — RECONCILED CURRENT + HISTORICAL COMPLETE

Current entrypoint: `CURRENT_TRUTH.md`.

The one-pass run below remains immutable historical evidence. Safe remediation
was applied afterward and is recorded in `SAFE_REMEDIATION_TASKS.md`; the bridge
between both states is `RECONCILIATION.md`. Do not read the old patch/todo claims
as current runtime truth without that reconciliation.

## Current state (2026-08-23)

- Production architecture: one Unified Intaker; semantic then rule fallback.
- Safe remediation: complete.
- Full test: 495 passed, 1 xfailed.
- Full behavior evaluation after remediation: not run.
- Obsidian-ready entrypoint and knowledge index: present.

## Historical one-pass state (2026-08-22)

Canonical run: `runs/20260822T152307Z/`

## Bước 0 / Bước 4 — toàn repo

```text
file semantic trong scope / file đã tick : 581 / 581
symbol/block đã liệt kê / đã tick         : 10.403 / 10.403
mục 1-8 cần điền / mục đã điền            : 83.224 / 83.224
```

Ngoài 581 file semantic, 202/202 binary/data/runtime artifact được `[skip]` với
lý do; tổng mẫu số là 783/783 path (773 tracked + 10 untracked ngoài `.audit`).
Coverage còn `[ ]`: **0**.

## Bằng chứng chống sót/drift

- `manifest.jsonl`: 783 path unique.
- `snapshot/`: 581 file, 581 hash đúng, 0 thiếu.
- Semantic pass hoàn chỉnh mở mỗi snapshot file đúng một lần trong một process.
- `FINDINGS_COMPLETE/`: 581 file section, 10.403 block, mỗi block đủ mục 1–8.
- So initial public-surface inventory với final FINDINGS: 0 symbol/route/env/config
  key bị thiếu.
- Parse error ngoài notebook: 0. Notebook có Jupyter magic được ghi `chưa rõ`,
  không bị bỏ qua im lặng.
- Product/research file có mtime sau capture: 0/581.
- Git status ngoài `.audit` so với lúc capture: 0 dòng drift.

## Historical deliverables

- `ARCHITECTURE.md`: kiến trúc thật, dependency/data flows/contracts/invariants,
  unknowns, snapshot id và baseline commit.
- `todo.md`: 103 action + 5 Q đã đóng = 108/108 Q; đúng ba rổ A/B/C, có doc mồ
  côi và hành vi chưa được mô tả.
- `patches/A-docs.patch`, `B-comments.patch`, `C-code.patch`: proposal artifacts
  của snapshot; hiện superseded, không apply wholesale.
- `runs/20260822T152307Z/COMPLETION_GATE.md`: gate máy cuối cùng.

## Những gì historical audit không làm

- Không sửa product code, không apply patch, không commit.
- Không restart/kill service và không biến architecture audit thành runtime
  quality/readiness test.
- Không coi report, notebook hay doc là code truth.
- Patch chỉ materialize các đề xuất đủ chắc; các mục cần đo/quyết định vẫn ở
  `todo.md`, không được biến thành logic đoán mò.

## Di sản trước one-pass run

`FINDINGS/` là 11 module deep-audit cũ (57 file) đã được preserve và validate
vào run mới. `coverage.legacy.pre-one-pass.md`, `modules.txt`, `order.md` là
checkpoint cũ, không phải trạng thái hoàn tất. `coverage.md` hiện là ledger cuối.
