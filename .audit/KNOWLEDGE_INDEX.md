---
title: AcneLLM Knowledge Index
aliases:
  - Knowledge Index
tags:
  - acnellm
  - moc
  - knowledge-base
status: canonical-index
as_of: 2026-08-25
---

# Knowledge index

## Bắt đầu

- [[OBSIDIAN_HOME]] — trang chủ khi mở vault.
- [[CURRENT_TRUTH]] — kiến trúc và contract hiện hành.
- [[CONTEXT_INTEGRITY]] — cách giải quyết mâu thuẫn/provenance.
- [[RECONCILIATION]] — delta từ audit snapshot sang source hiện tại.

## Triển khai đã hoàn tất

- [[SAFE_REMEDIATION_TASKS]] — scope, file, test và hash evidence.
- `../docs/ARCHITECTURE_TRUTH.md` — runtime architecture canonical.
- `../docs/config_reference.md` — active Settings reference.
- `../docs/config_layout.md` — ownership giữa env/config/module constants.

## Bằng chứng người

- `../research/evaluation/reports/calibration_rrr/README.md` — phiếu chấm tay
  toàn bộ 145 hàng arm `RRR`, cách đọc κ trên arm đơn, giới hạn.
- `../research/evaluation/reports/calibration_rrr/ket_qua_rrr145.json` — κ,
  κ_quad, Gwet AC1, khớp ±1 bậc, và kiểm định hai cờ safety do judge suy luận.
- `../research/evaluation/reports/calibration_rrr/judge_calibration_rrr145.json`
  — artifact κ theo đúng định dạng `judges/calibrate.py`.
- `../research/evaluation/reports/calibration/` — bộ 60 mẫu cũ; `historical`,
  đo trên lần sinh khác và judge khác, **không** carry-forward sang `v2_full`.

## Bảo vệ khóa luận

- [[SLIDE_FACT_CHECK_2026-08-25]] — fact boundary mới nhất cho claim trên slide.
- `../docs/presentations/AcneLLM_Defense_E2E_Context_2026-08-25.md` — cấu trúc
  22 slide chính + appendix, evidence map và timing 20 phút.
- `../docs/presentations/AcneLLM_KhoaLuan_20min_DaDuyet.pptx` — deck đã duyệt
  hiện có; context refresh này chưa sửa binary deck.

## Snapshot current 2026-08-25

- `runs/20260825T090826Z/SNAPSHOT_GATE.md` — gate động PASS.
- `runs/20260825T090826Z/scope.json` — HEAD, branch và denominator 837 path.
- `runs/20260825T090826Z/manifest.jsonl` — disposition và hash từng path.
- `runs/20260825T090826Z/FINDINGS_AUTO/` — 590 file section và 10.335 block.

## Hướng phát triển

- [[FUTURE_BEHAVIOR_ROADMAP]] — T4/SSE, medication, intake/schema, RAG,
  generation/safety và session/data contracts.
- [[todo]] — 108 mục audit cũ; historical backlog, phải reconcile trước khi làm.

## Kiến trúc snapshot 2026-08-22

Snapshot mở rộng được đóng thành release asset
[`audit-run-20260822T152307Z.zip`](https://github.com/phkgn/AcneLLM/releases/download/knowledge-2026-08-23/audit-run-20260822T152307Z.zip)
để tránh nhân bản 581 source files trong lịch sử Git. Sau khi giải nén vào
`.audit/runs/`, các đường dẫn dưới đây hoạt động nguyên trạng.

- [[ARCHITECTURE]] — synthesis của immutable snapshot.
- [[coverage]] — coverage ledger 581 semantic + 202 skipped.
- `runs/20260822T152307Z/SUMMARY.md` — run summary.
- `runs/20260822T152307Z/COMPLETION_GATE.md` — machine gate.
- `runs/20260822T152307Z/FINDINGS_COMPLETE/INDEX.md` — per-file findings.
- `runs/20260822T152307Z/manifest.jsonl` — physical manifest.
- `runs/20260822T152307Z/snapshot/` — source snapshot at capture time.

## Deep audit theo production module

- `FINDINGS/src.chat.md` — orchestration/runtime.
- `FINDINGS/src.chat.routing.md` — intent/semantic/rules; một phần superseded.
- `FINDINGS/src.chat.session.md` — session/fold; một phần superseded.
- `FINDINGS/src.config.md` — settings; legacy intake config đã superseded.
- `FINDINGS/src.guardrails.md` — hard safety and medication policy.
- `FINDINGS/src.rag.md` — retrieval/reranker/cache.
- `FINDINGS/src.llm.md` — prompt/backend/generator.
- `FINDINGS/src.db.md` — SQLite audit/session persistence.
- `FINDINGS/src.schemas.md` — data contracts.
- `FINDINGS/src.utils.md` và `FINDINGS/src.cache.md` — utilities/cache.

## Research, data, evaluation và deploy

Per-file knowledge nằm trong
`runs/20260822T152307Z/FINDINGS_COMPLETE/` với các nhóm:

- `eval.*`, `evaluation.md`: evaluation harness/artifacts.
- `datagen.*`, `LLMData.md`: dataset generation/training data.
- `research.md`, `dashboards.md`, `dataset_viz.md`: research tooling/visuals.
- `data.md`, `guideline_docs.md`: KB inputs and runtime data artifacts.
- `docker.md`, `docker-compose.md`, `Dockerfile.md`: deployment.
- `frontend.md`: Next.js/SSE client.
- `scripts.md`, `tasks.md`: operational entrypoints.

## Provenance và trạng thái

- [[STATUS]] — trạng thái audit/reconciliation hiện hành.
- [[CURRENT_COMPLETION_GATE]] — gate knowledge reconciliation.
- [[COMPLETION_GATE]] — historical one-pass machine gate.
- `patches/A-docs.patch`, `B-comments.patch`, `C-code.patch` — superseded
  provenance; không apply wholesale.
- `coverage.legacy.pre-one-pass.md`, `modules.txt`, `order.md` — legacy audit
  checkpoints, không phải current truth.
