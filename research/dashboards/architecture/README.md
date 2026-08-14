# AcneLLM architecture diagrams

This directory is the canonical architecture visualization set for the current
`codex/simplify-chat-pipeline` worktree. The seven pages were built from the
runtime/data/evaluation source files, opened and visually checked in
<https://app.diagrams.net/>, then rendered at 1920×1080.

## Pages

1. `01_system_context.png` — client, gateway, API, application core, models and stores.
2. `02_chat_sse_workflow.png` — production HTTP SSE/WebSocket request path.
3. `03_intake_safety_routing.png` — preprocessing, hard safety, routing, extraction and effective mode.
4. `04_rag_kb_lifecycle.png` — offline KB build plus online hybrid retrieval/reranking.
5. `05_finetune_data_factory.png` — independent `datagen/intakedata` and `datagen/roledata` provenance paths.
6. `06_evaluation_ablation.png` — deterministic intake metrics, retrieval judge and paired ablation.
7. `07_docker_deployment.png` — Compose startup order, internal network and persistent mounts.

## Editable source

- `AcneLLM_Architecture.drawio` is the editable, uncompressed, seven-page diagrams.net file.
- `build_drawio.py` deterministically rebuilds the `.drawio` XML from the verified architecture definition.
- Each page includes a yellow `SOURCE-VERIFIED` note naming its primary code/config inputs.

Rebuild the editable document:

```powershell
.\.venv\Scripts\python.exe visualization\architecture\build_drawio.py
```

Open `AcneLLM_Architecture.drawio` in diagrams.net and export each page as PNG
when source changes affect the architecture.
