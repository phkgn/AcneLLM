"""Convert crawled documents → conversational Q&A fine-tuning dataset.

Pipeline:
  documents.jsonl  →  clean_for_finetuning()  →  QAGenerator (LLM)  →  qa_finetuning.jsonl

Output format: ChatML (system / user / assistant) — compatible with
Axolotl (sharegpt), LLaMA-Factory, Unsloth out-of-the-box.

Usage:
    # Via DeepSeek API (default):
    export DEEPSEEK_API_KEY=sk-...
    python -m scripts.build_qa_dataset

    # Via local Ollama (no API key required):
    python -m scripts.build_qa_dataset --use-ollama

    # Resume from checkpoint (skips already-processed doc_ids):
    python -m scripts.build_qa_dataset --resume

    # Dry-run (first 20 docs, no API calls):
    python -m scripts.build_qa_dataset --dry-run --limit 20

    # Use different API provider (e.g. local vLLM):
    python -m scripts.build_qa_dataset --base-url http://localhost:8000/v1 --model mistral
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path

import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.utils.text_cleaning import clean_for_finetuning
from acne_llm.llm.qa_generator import QAGenerator, OllamaQAGenerator
from acne_llm.utils.logging import configure_logging

LOG_DIR = ROOT / "data" / "logs"
DOCS_PATH = ROOT / "data" / "raw" / "documents.jsonl"
OUT_PATH = ROOT / "data" / "finetune" / "qa_finetuning.jsonl"
CKPT_PATH = ROOT / "data" / "finetune" / ".qa_checkpoint.json"

app = typer.Typer(add_completion=False)


def _load_checkpoint() -> set[str]:
    if CKPT_PATH.exists():
        return set(json.loads(CKPT_PATH.read_text(encoding="utf-8")))
    return set()


def _save_checkpoint(done: set[str]) -> None:
    CKPT_PATH.write_text(json.dumps(sorted(done)), encoding="utf-8")


def _load_docs(limit: int | None) -> list[dict]:
    docs: list[dict] = []
    with open(DOCS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
            if limit and len(docs) >= limit:
                break
    return docs


@app.command()
def run(
    docs: str = typer.Option(str(DOCS_PATH), help="Input documents.jsonl"),
    out: str = typer.Option(str(OUT_PATH), help="Output qa_finetuning.jsonl"),
    resume: bool = typer.Option(False, help="Skip already-processed doc_ids"),
    dry_run: bool = typer.Option(False, help="Print stats only, no API calls"),
    limit: int = typer.Option(0, help="Process only first N docs (0 = all)"),
    concurrency: int = typer.Option(5, help="Concurrent LLM requests"),
    base_url: str = typer.Option("https://api.deepseek.com", help="OpenAI-compatible API base URL"),
    model: str = typer.Option("deepseek-chat", help="Model name"),
    log_level: str = typer.Option("INFO"),
    use_ollama: bool = typer.Option(False, "--use-ollama", help="Use local Ollama instead of API (no API key required)"),
    ollama_url: str = typer.Option("http://localhost:11434", help="Ollama server URL (--use-ollama only)"),
    ollama_model: str = typer.Option("qwen2.5:7b", help="Ollama model name (--use-ollama only)"),
):
    configure_logging(level=log_level, log_dir=LOG_DIR)
    asyncio.run(_run(docs, out, resume, dry_run, limit or None, concurrency,
                     base_url, model, use_ollama, ollama_url, ollama_model))


async def _run(
    docs_path: str,
    out_path: str,
    resume: bool,
    dry_run: bool,
    limit: int | None,
    concurrency: int,
    base_url: str,
    model: str,
    use_ollama: bool = False,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "qwen2.5:7b",
):
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key and not use_ollama and not dry_run:
        logger.error(
            "Set DEEPSEEK_API_KEY (or OPENAI_API_KEY), or use --use-ollama for local generation."
        )
        raise SystemExit(1)

    all_docs = _load_docs(limit)
    logger.info(f"Loaded {len(all_docs)} documents from {docs_path}")

    done_ids: set[str] = _load_checkpoint() if resume else set()
    if done_ids:
        logger.info(f"Resuming — {len(done_ids)} docs already processed, skipping")

    pending = [d for d in all_docs if d["doc_id"] not in done_ids]
    logger.info(f"Pending: {len(pending)} docs | dry_run={dry_run}")

    if dry_run:
        _print_stats(all_docs, pending)
        return

    if use_ollama:
        logger.info(f"Using local Ollama: {ollama_model} @ {ollama_url}")
        generator = OllamaQAGenerator(
            ollama_url=ollama_url,
            model=ollama_model,
            num_ctx=8192,
            temperature=0.6,
        )
    else:
        logger.info(f"Using API: {model} @ {base_url}")
        generator = QAGenerator(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_concurrency=concurrency,
        )

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if resume else "w"

    total_samples = 0
    write_lock = asyncio.Lock()

    async def process_doc(doc: dict) -> None:
        nonlocal total_samples

        doc_id = doc["doc_id"]
        lang = doc.get("source", {}).get("language", "vi")
        raw_text = doc.get("text", "")
        title = doc.get("title", "")

        text = clean_for_finetuning(raw_text)
        if len(text) < 300:
            logger.debug(f"[skip] {doc_id} — text too short after cleaning ({len(text)} chars)")
            async with write_lock:
                done_ids.add(doc_id)
            return

        source_meta = {
            "source_url": doc.get("url", ""),
            "source_name": doc.get("source", {}).get("source_name", ""),
            "trust_level": doc.get("source", {}).get("trust_level", "medium"),
            "categories": doc.get("categories", []),
            "title": title,
        }

        # Prepend title to give the LLM context without repeating it in answers
        context_text = f"{title}\n\n{text}" if title else text
        samples = await generator.generate(doc_id, context_text, lang, source_meta)

        if not samples:
            logger.warning(f"[QAGen] 0 samples for doc={doc_id}")
        else:
            async with write_lock:
                with open(out_p, mode, encoding="utf-8") as f:
                    for s in samples:
                        f.write(json.dumps(s.model_dump(), ensure_ascii=False) + "\n")
                total_samples += len(samples)
                done_ids.add(doc_id)
                _save_checkpoint(done_ids)
                logger.info(
                    f"[{len(done_ids)}/{len(pending)}] {doc_id[:12]}… "
                    f"+{len(samples)} pairs | total={total_samples}"
                )

    await asyncio.gather(*(process_doc(d) for d in pending))
    await generator.close()

    logger.success(
        f"Done. {total_samples} Q&A pairs from {len(done_ids)} docs → {out_path}"
    )
    _print_final_stats(out_p)


def _print_stats(all_docs: list[dict], pending: list[dict]) -> None:
    vi = sum(1 for d in all_docs if d.get("source", {}).get("language") == "vi")
    en = len(all_docs) - vi
    short = sum(1 for d in all_docs if len(d.get("text", "")) < 300)
    logger.info(
        f"\n{'─'*50}\n"
        f"  Total docs : {len(all_docs)}\n"
        f"  VI         : {vi} ({vi/len(all_docs)*100:.0f}%)\n"
        f"  EN         : {en} ({en/len(all_docs)*100:.0f}%)\n"
        f"  Too short  : {short} (will be skipped)\n"
        f"  Pending    : {len(pending)}\n"
        f"  Est. pairs : {len(pending)*8} – {len(pending)*12} "
        f"(avg 8–12 per doc)\n"
        f"{'─'*50}"
    )


def _print_final_stats(out_p: Path) -> None:
    if not out_p.exists():
        return
    intent_counts: dict[str, int] = {}
    lang_counts: dict[str, int] = {}
    total = 0
    with open(out_p, encoding="utf-8") as f:
        for line in f:
            try:
                s = json.loads(line)
                meta = s.get("metadata", {})
                intent_counts[meta.get("intent", "?")]  = intent_counts.get(meta.get("intent", "?"), 0) + 1
                lang_counts[meta.get("language", "?")] = lang_counts.get(meta.get("language", "?"), 0) + 1
                total += 1
            except Exception:
                pass

    rows = "\n".join(
        f"  {k:<20} {v:>6}  ({v/total*100:.1f}%)" for k, v in sorted(intent_counts.items(), key=lambda x: -x[1])
    )
    lang_rows = "  " + "  |  ".join(f"{k}: {v}" for k, v in sorted(lang_counts.items()))
    logger.success(
        f"\n{'═'*50}\n"
        f"  QA DATASET SUMMARY\n"
        f"{'─'*50}\n"
        f"  Total samples : {total:,}\n"
        f"  Language      : {lang_rows}\n"
        f"{'─'*50}\n"
        f"  Intent breakdown:\n{rows}\n"
        f"{'═'*50}"
    )


if __name__ == "__main__":
    app()
