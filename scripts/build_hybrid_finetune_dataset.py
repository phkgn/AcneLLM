"""Build RAG-grounded chat fine-tuning records from AcneDataset cases."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.config import settings  # noqa: E402
from acne_llm.di import build_container  # noqa: E402
from scripts.convert_acne_dataset import SYSTEM_PROMPT, _description, _target_advise  # noqa: E402

app = typer.Typer()


def _context_block(chunks, max_chars: int = 4000) -> str:
    if not chunks:
        return "(Không có ngữ cảnh KB phù hợp.)"
    blocks: list[str] = []
    used = 0
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata or {}
        title = meta.get("title", "")
        source = meta.get("source", chunk.source)
        text = chunk.text.strip()
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining].rsplit(" ", 1)[0].strip() + "..."
        blocks.append(f"Nguồn {i} — {title} | {source}\n{text}")
        used += len(text)
    return "\n\n---\n\n".join(blocks)


def _attach_retrieval_metadata(target: dict, chunk_ids: list[str]) -> dict:
    target = dict(target)
    target["mode"] = "hybrid"
    target["used_chunks"] = chunk_ids
    return target


@app.command()
def main(
    input: str = typer.Option("LLMData/acne_dataset.jsonl", "--input"),
    output: str = typer.Option("data/finetune/hybrid_chatml.jsonl", "--output"),
    top_k: int = typer.Option(5, "--top-k"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    container = build_container(settings)
    if container.retriever is None:
        raise RuntimeError(
            "RAG retriever is not ready. Build Chroma and BM25, including BM25 checksum, first."
        )

    in_path = Path(input)
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with in_path.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as dst:
            for line in src:
                if limit is not None and count >= limit:
                    break
                if not line.strip():
                    continue
                row = json.loads(line)
                description = _description(row)
                retrieval = container.retriever.retrieve(description, top_k=top_k, mode="hybrid")
                chunks = retrieval.chunks[:top_k]
                chunk_ids = [chunk.chunk_id for chunk in chunks]
                target = _attach_retrieval_metadata(_target_advise(row), chunk_ids)
                user_content = (
                    f"<raw_user_message>{description}</raw_user_message>\n"
                    f"<rag_context>\n{_context_block(chunks)}\n</rag_context>"
                )
                record = {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                        {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)},
                    ],
                    "metadata": {
                        "id": row.get("id"),
                        "task_type": row.get("task_type"),
                        "source": row.get("source"),
                        "split": row.get("split", "train"),
                        "sample_type": "hybrid_chatml",
                        "retrieved_chunk_ids": chunk_ids,
                    },
                }
                dst.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
    finally:
        import asyncio

        asyncio.run(container.close())
    typer.echo(f"Wrote {count} records to {out_path}")


if __name__ == "__main__":
    app()
