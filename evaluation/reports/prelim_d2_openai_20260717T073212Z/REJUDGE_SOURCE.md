# OpenAI Rejudge Provenance

- Source generation run: `evaluation/reports/prelim_d2_20260716T190345_330Z`
- Reused artifacts: `s0.results.jsonl` through `s4.results.jsonl`, plus
  generation `run_meta.json`
- Excluded from source: every `*.judged.jsonl`, `pairwise_*.jsonl`, report,
  and DeepSeek judge artifact
- New judge: `openai/gpt-5-nano-2025-08-07`
- Concurrency: started at 8 record workers; resumed at 4 after a Tier-1 TPM 429

This preserves the exact 700 generated answers while preventing mixed
DeepSeek/OpenAI scores in one run directory.
