# Prompt audit

| Prompt | Contract | Context | Output | Model hint |
|---|---|---|---|---|
| `llm_only_user.j2` | data + no-RAG constraints | current/history/safety facts | `AdviseOutput` JSON | `none` |
| `hybrid_user.j2` | data + grounding/citation contract | retrieved chunks + current/history | `AdviseOutput` JSON | `none` |
| `stream_user.j2` | production data prompt | route/history/retrieved chunks | prose + `[N]` | `none` |

## SYSTEM parity (R1)

- S0 vs S1 SYSTEM semantic text equal: **PASS**
- Evidence sources: Ollama `/api/show` when available; fallback Modelfiles `evaluation/modelfiles/qwen25-base-acnesys/Modelfile` and `model/V2/Q4/Modelfile`.

## Semantic findings

- Safety, scope, language and anti-jailbreak rules live in the Modelfile SYSTEM; the three user templates intentionally do not duplicate them.
- `hybrid_user.j2` alone receives retrieved evidence; this is the registered RAG IV, not a model-specific hint.
- T3 prompts require JSON while production `stream_user.j2` requests prose. This is a real path difference and must remain explicit in reports.
- No template may mention S0-S4 or a model/checkpoint name. The table above records the static scan result.

## Hashes

```json
{
  "templates": {
    "config/prompts/clarify_user.j2": "cb5789e047d522ffd8fcf7b277fa2fe9c555119e3d01ddcf22c1606f6671de61",
    "config/prompts/hybrid_user.j2": "6e234c267146f3f987c169ee7829f06e9a0858da407b42e5c29695d8791b68ff",
    "config/prompts/knowledge_user.j2": "c3fa196f89c3853b9bbb0e6dbe0cf590f9d14ccd239880bd1dc52f2303b67c3a",
    "config/prompts/llm_only_user.j2": "fa591d5c2aa337b582aa25ad29c0052fbe79ccab96ff4c50fdf1088f4fc518b1",
    "config/prompts/stream_user.j2": "dbdaa9a51b598b68b340d0b468e9fcc45641f30403730c9870194532e2722f24"
  },
  "judge_prompts": {
    "evaluation/judges/prompts/claim_extract.md": "8db0e44e433f441f528335197882cec9426e1ece7dd5d40f9fa18f7697fec2ab",
    "evaluation/judges/prompts/entailment.md": "c09ca8a87a74fb2094e850d09c566d3f0ba6d420340fd4e93a487925b86c1064",
    "evaluation/judges/prompts/error_classify.md": "4fc159baccab8a30a790cb5fdb5ffcd325f8e647851d018b82b1db1a601d3bef",
    "evaluation/judges/prompts/pairwise.md": "1ecfee0114a9e1aa1f08ecd04f85a85b7235dbaf47b544ff9f392d6e60fc95fb",
    "evaluation/judges/prompts/pointwise.md": "1541398c866e94fe17ad4b029d764dbbbf1b61de1d02239e14fc278710b8d0e7"
  },
  "system_prompts": {
    "s0": "cbff97d20b09486243fa541380871ecda3123e879686c7dd263d1885a7a691e7",
    "s1": "cbff97d20b09486243fa541380871ecda3123e879686c7dd263d1885a7a691e7",
    "s2": "cbff97d20b09486243fa541380871ecda3123e879686c7dd263d1885a7a691e7",
    "s3": "cbff97d20b09486243fa541380871ecda3123e879686c7dd263d1885a7a691e7"
  }
}
```
