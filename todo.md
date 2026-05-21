# TODO — After Overnight KB Embed

## 0. Finish And Verify KB

After overnight embedding completes, build BM25:

```powershell
python -m scripts.build_kb --step bm25
```

Verify:

```powershell
.\tasks.ps1 stats
```

Expected:

- ChromaDB vectors should be close to `21,907`.
- `data/bm25_index.pkl` should exist.
- `RAG ready` should be `True`.

## 1. Verify Hybrid Runtime

Start server:

```powershell
.\tasks.ps1 serve
```

Test `/api/v1/chat` with `mode: "hybrid"`:

```json
{
  "description": "Em bị mụn viêm ở cằm, da dầu, kéo dài 2 tháng",
  "context": {
    "age": 22,
    "sex": "female",
    "skin_type": "oily",
    "duration_weeks": 8
  },
  "clinical": {
    "lesion_types": ["papule", "pustule"],
    "lesion_distribution": ["chin"],
    "inflammation_level": "moderate"
  },
  "mode": "hybrid"
}
```

Check:

- No `503`.
- `used_chunks` is non-empty.
- Output is Vietnamese.
- English input triggers Vietnamese-only notice.
- `source_chunk_id` values come from retrieved chunks when recommendations cite sources.

## 2. Build `llm_only_chatml.jsonl`

Add script:

```text
scripts/convert_acne_dataset.py
```

Input:

```text
LLMData/acne_dataset.jsonl
```

Output:

```text
data/finetune/llm_only_chatml.jsonl
```

Responsibilities:

- Convert `normalization`, `classification`, `recommendation`, and `full_pipeline`.
- Map input to canonical `UserInput + AcneClinicalInput`.
- Convert target to JSON matching `AdviseOutput`.
- Keep metadata such as original `task_type`.

Purpose: teach the fine-tuned LLM to handle acne cases without RAG context.

## 3. Build `hybrid_chatml.jsonl`

Add script:

```text
scripts/build_hybrid_finetune_dataset.py
```

Inputs:

```text
LLMData/acne_dataset.jsonl
data/chroma_db/
data/bm25_index.pkl
```

Output:

```text
data/finetune/hybrid_chatml.jsonl
```

Pipeline:

```text
AcneDataset case
  -> convert to UserInput + AcneClinicalInput
  -> create query_vi/query_en
  -> retrieve top-k chunks via RAG
  -> render prompt similar to hybrid runtime
  -> assistant target = AdviseOutput JSON with source_chunk_id
```

Purpose: teach the fine-tuned LLM to use RAG context, keep citations, and return valid `AdviseOutput`.

## 4. Build Or Resume Knowledge Q&A Data

Optional but useful:

```powershell
python -m scripts.build_qa_dataset --resume
```

Output:

```text
data/finetune/qa_finetuning.jsonl
```

Purpose: add general acne/dermatology knowledge Q&A from crawled documents.

## 5. Merge Fine-Tune Datasets

Add script:

```text
scripts/merge_finetune_datasets.py
```

Inputs:

```text
data/finetune/llm_only_chatml.jsonl
data/finetune/hybrid_chatml.jsonl
data/finetune/qa_finetuning.jsonl
```

Output:

```text
data/finetune/train_mix_chatml.jsonl
```

Suggested ratios:

```text
50% hybrid_chatml
25% llm_only_chatml
25% qa_finetuning
```

Alternative if prioritizing clinical case reasoning:

```text5
40% hybrid_chatml
40% llm_only_chatml
20% qa_finetuning
```

## 6. Fine-Tune And Deploy

Use one of:

- Unsloth
- LLaMA-Factory
- Axolotl

Train Qwen2.5-7B LoRA/QLoRA using:

```text
data/finetune/train_mix_chatml.jsonl
```

Then:

- Merge LoRA if needed.
- Convert to GGUF if deploying through Ollama.
- Create Ollama model with a `Modelfile`.
- Update `.env`:

```env
LLM_MODEL=acne-qwen2.5-7b-finetuned
```

No API route changes should be required.

## 7. Eval After Fine-Tune

Compare:

- `llm_only`
- `hybrid`

Measure:

- JSON parse rate.
- Safety guardrails.
- Severity accuracy.
- Citation correctness.
- Vietnamese-only output behavior.
- Latency.
- RAG `used_chunks` relevance.

## One-Line Reminder

After KB is ready: verify hybrid runtime -> convert AcneDataset into `llm_only` data -> use RAG to build `hybrid` data -> optionally build QA knowledge data -> merge ChatML -> fine-tune Qwen -> deploy via Ollama -> eval `llm_only` and `hybrid`.
