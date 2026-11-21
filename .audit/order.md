# Thu tu audit — leaf truoc, entrypoint sau

## Vong 1 — src/ (code chay production)
 1  src.schemas          leaf
 2  src.cache            leaf
 3  src.config           leaf
 4  src.chat.session     leaf dung chung (db va llm deu phu thuoc)
 5  src.rag              -> cache, schemas
 6  src.utils            -> rag, schemas
 7  src.guardrails       -> schemas
 8  src.llm              -> chat.session, schemas
 9  src.db               -> chat.session
10  src.chat (con lai)   -> cache, config, db, guardrails, llm, schemas, utils
11  src.di               -> tat ca (composition root)
12  src.api              -> chat, config, di, utils   (entrypoint HTTP)
13  src.cli              -> chat, config, di, schemas (entrypoint CLI)

## Vong 2 — hop dong ben ngoai
14  config               prompt .j2, guardrails.yaml, drugs_acne.yaml
15  deploy               Dockerfile, compose, nginx, ollama-init
16  tests                kiem chung lai vong 1
17  frontend             hop dong SSE voi src.api

## Vong 3 — research/ (ngoai tuyen)
18  eval.metrics · eval.adapters · eval.common   leaf
19  eval.judges
20  eval.datasets
21  eval.runners
22  eval.core            full_evaluation, trace, severity, e2e.ps1
23  eval.tests
24  datagen.core         gates/main v1 — nghi la legacy
25  datagen.roledata     v1
26  datagen.intakedata
27  datagen.roledatav2   v2, bo dang dung
28  dashboards · dataset_viz
29  LLMData · guideline_docs
30  scripts
31  root                 tasks.sh, pyproject, .env.baseline, README

## Vong 4 — loi khai, kiem nguoc lai code
32  docs                 59 file .md
33  notebooks            15 .ipynb — xem de xuat skip
