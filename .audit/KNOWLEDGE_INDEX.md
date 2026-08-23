---
title: AcneLLM Knowledge Index
aliases:
  - Knowledge Index
tags:
  - acnellm
  - moc
  - knowledge-base
status: canonical-index
as_of: 2026-08-23
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
