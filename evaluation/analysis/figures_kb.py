"""Generate KB/corpus (A) and finetune-data (B) figure artifacts."""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from evaluation.analysis.figures_common import (
    ManifestBuilder,
    configure_matplotlib,
    fresh_figure_generation,
    histogram,
    iter_jsonl,
    read_json,
    write_json,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _attempt(
    builder: ManifestBuilder,
    *,
    figure_id: str,
    title: str,
    caption: str,
    source_data: str,
    chart_type: str,
    kind: str,
    function: Callable[[], None],
) -> None:
    try:
        function()
    except Exception as exc:
        builder.skip(
            figure_id=figure_id,
            title=title,
            reason=f"{type(exc).__name__}: {exc}",
            caption=caption,
            source_data=source_data,
            chart_type=chart_type,
            kind=kind,
        )


def _load_chunks(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def _a2_chunk_lengths(
    builder: ManifestBuilder,
    chunks_path: Path,
    chunks: list[dict[str, Any]],
) -> None:
    lengths = [
        float(row.get("text_len") or len(str(row.get("text") or "")))
        for row in chunks
        if row.get("text") or row.get("text_len")
    ]
    if not lengths:
        raise ValueError("No chunk lengths found.")
    builder.add_chart(
        figure_id="a2_chunk_length",
        title="Chunk length distribution",
        chart_type="hist",
        payload={
            "data": histogram(lengths, bins=30),
            "x_key": "bin",
            "x_label": "Characters per chunk",
            "y_label": "Chunks",
            "series": [{"key": "count", "label": "Chunks"}],
            "summary": {
                "n": len(lengths),
                "mean": round(mean(lengths), 2),
                "min": min(lengths),
                "max": max(lengths),
            },
        },
        caption="Character length from chunks.jsonl, using text_len when present.",
        source_data=chunks_path.as_posix(),
    )


def _chroma_sample(
    root: Path,
    sample: int,
) -> tuple[list[str], list[dict[str, Any]], Any]:
    persist_dir = root / "data" / "chroma_db"
    if not persist_dir.exists():
        raise ValueError("data/chroma_db does not exist.")
    print("[figures_kb] opening Chroma collection…", flush=True)
    from acne_llm.rag.vectorstore import ChromaStore
    import numpy as np

    store = ChromaStore(persist_dir=str(persist_dir))
    count = store.count()
    if count < 3:
        raise ValueError(f"Chroma collection has only {count} vectors.")
    print(f"[figures_kb] Chroma count={count:,}; sampling seed=42", flush=True)
    inventory = store.col.get(include=["metadatas"])
    all_ids = [str(value) for value in inventory.get("ids") or []]
    if not all_ids:
        raise ValueError("Chroma returned no ids.")
    rng = random.Random(42)
    chosen = rng.sample(all_ids, min(max(3, sample), len(all_ids)))
    batch = store.col.get(
        ids=chosen,
        include=["embeddings", "metadatas"],
    )
    ids = [str(value) for value in batch.get("ids") or []]
    metadatas = [
        value if isinstance(value, dict) else {}
        for value in batch.get("metadatas") or []
    ]
    vectors = np.asarray(batch.get("embeddings"), dtype=np.float32)
    if vectors.ndim != 2 or len(vectors) != len(ids):
        raise ValueError("Chroma embeddings are missing or malformed.")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.maximum(norms, 1e-12)
    return ids, metadatas, vectors


def _a3_umap(
    builder: ManifestBuilder,
    root: Path,
    sample: int,
    output_dir: Path,
) -> tuple[list[str], list[dict[str, Any]], Any]:
    ids, metadatas, vectors = _chroma_sample(root, sample)
    print(
        f"[figures_kb] UMAP fit-transform on {len(ids):,} × {vectors.shape[1]:,}…",
        flush=True,
    )
    import numpy as np
    import umap

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(15, len(ids) - 1),
        min_dist=0.08,
        metric="cosine",
        random_state=42,
        low_memory=True,
        n_jobs=1,
    )
    projected = reducer.fit_transform(vectors)
    print("[figures_kb] UMAP projection complete; rendering PNG/JSON…", flush=True)
    sources = [
        str(metadata.get("source") or metadata.get("source_type") or "unknown")
        for metadata in metadatas
    ]
    common_sources = {
        source
        for source, _ in Counter(sources).most_common(11)
    }
    display_sources = [
        source if source in common_sources else "other"
        for source in sources
    ]
    plt = configure_matplotlib()
    fig, ax = plt.subplots(figsize=(10.2, 7.2))
    categories = sorted(set(display_sources))
    palette = plt.get_cmap("tab20")
    for index, category in enumerate(categories):
        mask = np.asarray([value == category for value in display_sources])
        ax.scatter(
            projected[mask, 0],
            projected[mask, 1],
            s=7,
            alpha=0.55,
            label=category,
            color=palette(index % 20),
            linewidths=0,
        )
    ax.set_xlabel("UMAP-1")
    ax.set_ylabel("UMAP-2")
    ax.set_title(f"Embedding space — {len(ids):,} sampled chunks")
    ax.legend(markerscale=2, fontsize=7, ncol=2, loc="best")
    ax.grid(alpha=0.12)
    fig.tight_layout()
    builder.add_png(
        figure_id="a3_kb_umap",
        title="Embedding space (UMAP)",
        fig=fig,
        caption="Seed-42 sample from Chroma, colored by source; rare sources are grouped as other.",
        source_data="data/chroma_db",
        chart_type="scatter",
    )

    rng = random.Random(42)
    web_indices = sorted(
        rng.sample(range(len(ids)), min(2_000, len(ids)))
    )
    scatter_payload = {
        "id": "a3_kb_umap_web",
        "title": "Embedding space (UMAP web sample)",
        "chart_type": "scatter",
        "data": [
            {
                "x": round(float(projected[index, 0]), 5),
                "y": round(float(projected[index, 1]), 5),
                "source": display_sources[index],
                "chunk_id": ids[index],
                "size": 12,
            }
            for index in web_indices
        ],
        "x_data_key": "x",
        "y_data_key": "y",
        "group_key": "source",
        "x_label": "UMAP-1",
        "y_label": "UMAP-2",
    }
    data_file = output_dir / "a3_kb_umap.json"
    write_json(data_file, scatter_payload)
    builder.figures[-1]["data_file"] = data_file.name
    return ids, metadatas, vectors


def _a4_near_duplicates(
    builder: ManifestBuilder,
    vectors: Any,
) -> None:
    import numpy as np

    n = int(vectors.shape[0])
    if n < 2:
        raise ValueError("Need at least two embeddings.")
    duplicate_items = np.zeros(n, dtype=bool)
    duplicate_pairs = 0
    total_pairs = n * (n - 1) // 2
    block = 512
    print(
        f"[figures_kb] near-duplicate cosine scan over {n:,} vectors…",
        flush=True,
    )
    for left_start in range(0, n, block):
        left_end = min(n, left_start + block)
        left = vectors[left_start:left_end]
        for right_start in range(left_start, n, block):
            right_end = min(n, right_start + block)
            similarities = left @ vectors[right_start:right_end].T
            if right_start == left_start:
                mask = np.triu(similarities > 0.95, k=1)
            else:
                mask = similarities > 0.95
            rows, cols = np.where(mask)
            duplicate_pairs += len(rows)
            duplicate_items[left_start + rows] = True
            duplicate_items[right_start + cols] = True
    item_rate = float(duplicate_items.mean())
    pair_rate = duplicate_pairs / total_pairs if total_pairs else 0.0
    builder.add_chart(
        figure_id="a4_near_duplicate_rate",
        title="Near-duplicate rate (cosine > 0.95)",
        chart_type="bar",
        payload={
            "data": [
                {
                    "metric": "Chunks with ≥1 near duplicate",
                    "rate": round(item_rate, 8),
                    "count": int(duplicate_items.sum()),
                },
                {
                    "metric": "Near-duplicate vector pairs",
                    "rate": round(pair_rate, 8),
                    "count": int(duplicate_pairs),
                },
            ],
            "x_key": "metric",
            "x_label": "Definition",
            "y_label": "Rate",
            "domain": [0, max(item_rate, pair_rate, 0.01)],
            "series": [{"key": "rate", "label": "Rate"}],
            "threshold": 0.95,
            "sample_size": n,
        },
        caption="Exact blockwise cosine scan on the UMAP sample; diagonal pairs are excluded.",
        source_data="data/chroma_db",
    )


def _taxonomy_terms() -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    from scripts.eval.normalizer import taxonomy

    lesion_space = set(taxonomy._LESION_BUCKET.values())
    treatment_space = {item[0] for item in taxonomy._INGREDIENT_PATTERNS}
    population_space = {
        value
        for value in taxonomy._HORMONAL_CANON.values()
        if value
    }
    lesion_aliases = {
        "comedonal": ("comedone", "mụn đầu đen", "mụn đầu trắng", "blackhead", "whitehead"),
        "inflammatory": ("papule", "pustule", "mụn viêm", "mụn mủ", "sẩn viêm"),
        "nodulocystic": ("nodule", "cyst", "mụn bọc", "mụn nang", "nốt sần"),
        "scar": ("scar", "sẹo", "sẹo rỗ", "sẹo lõm"),
        "pigmentation": ("hyperpigmentation", "thâm mụn", "tăng sắc tố"),
    }
    treatment_aliases = {
        "benzoyl_peroxide": ("benzoyl peroxide", "bpo"),
        "adapalene": ("adapalene", "differin"),
        "tretinoin": ("tretinoin",),
        "isotretinoin": ("isotretinoin", "accutane"),
        "salicylic_acid": ("salicylic acid", "bha"),
        "azelaic_acid": ("azelaic acid", "axit azelaic"),
        "clindamycin": ("clindamycin",),
        "doxycycline": ("doxycycline",),
    }
    population_aliases = {
        "pregnancy": ("pregnancy", "pregnant", "mang thai", "thai kỳ", "có bầu"),
        "postpartum": ("postpartum", "sau sinh", "cho con bú", "breastfeeding"),
        "puberty": ("puberty", "dậy thì", "vị thành niên"),
        "pcos": ("pcos", "buồng trứng đa nang"),
        "menstrual_cycle": ("menstrual", "kinh nguyệt", "chu kỳ kinh"),
    }
    return (
        {key: value for key, value in lesion_aliases.items() if key in lesion_space},
        {key: value for key, value in treatment_aliases.items() if key in treatment_space},
        {key: value for key, value in population_aliases.items() if key in population_space},
    )


def _a5_coverage_matrix(
    builder: ManifestBuilder,
    output_dir: Path,
    chunks: list[dict[str, Any]],
) -> None:
    lesions, treatments, populations = _taxonomy_terms()
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in chunks:
        text = str(row.get("text") or "").lower()
        found_lesions = [
            key for key, aliases in lesions.items() if any(alias in text for alias in aliases)
        ]
        found_treatments = [
            key for key, aliases in treatments.items() if any(alias in text for alias in aliases)
        ]
        found_populations = [
            key for key, aliases in populations.items() if any(alias in text for alias in aliases)
        ]
        for lesion in found_lesions:
            for treatment in found_treatments:
                for population in found_populations:
                    counts[(lesion, treatment, population)] += 1
    rows = list(lesions)
    columns = [
        f"{treatment} · {population}"
        for treatment in treatments
        for population in populations
    ]
    if not rows or not columns:
        raise ValueError("Taxonomy did not expose lesion/treatment/population terms.")
    cells = [
        {
            "row": lesion,
            "column": f"{treatment} · {population}",
            "value": counts[(lesion, treatment, population)],
            "treatment": treatment,
            "population": population,
        }
        for lesion in rows
        for treatment in treatments
        for population in populations
    ]
    matrix = [
        [
            counts[(lesion, treatment, population)]
            for treatment in treatments
            for population in populations
        ]
        for lesion in rows
    ]
    plt = configure_matplotlib()
    fig, ax = plt.subplots(figsize=(max(12, len(columns) * 0.45), 5.8))
    image = ax.imshow(matrix, aspect="auto", cmap="magma")
    ax.set_xticks(range(len(columns)), columns, rotation=60, ha="right", fontsize=7)
    ax.set_yticks(range(len(rows)), rows)
    ax.set_title("Chunk coverage: lesion × treatment × population")
    fig.colorbar(image, ax=ax, fraction=0.02, pad=0.02, label="Chunks")
    fig.tight_layout()
    builder.add_png(
        figure_id="a5_coverage_matrix",
        title="Corpus coverage matrix",
        fig=fig,
        caption="Keyword-matched triples derived from the existing normalizer taxonomy.",
        source_data="data/raw/chunks.jsonl + scripts/eval/normalizer/taxonomy.py",
        chart_type="heatmap",
    )
    data_file = output_dir / "a5_coverage_matrix.json"
    write_json(
        data_file,
        {
            "id": "a5_coverage_matrix_web",
            "title": "Corpus coverage matrix",
            "chart_type": "heatmap",
            "rows": rows,
            "columns": columns,
            "cells": cells,
            "value_label": "Chunks",
        },
    )
    builder.figures[-1]["data_file"] = data_file.name


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        if 1900 <= value <= 2200:
            return datetime(int(value), 1, 1, tzinfo=timezone.utc)
        if value > 1_000_000_000:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if re.fullmatch(r"\d{4}", text):
        return datetime(int(text), 1, 1, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _a6_document_age(
    builder: ManifestBuilder,
    chunks: list[dict[str, Any]],
) -> None:
    dates: list[datetime] = []
    keys = ("published_at", "published_date", "date", "updated_at", "year")
    for row in chunks:
        for key in keys:
            parsed = _parse_date(row.get(key))
            if parsed:
                dates.append(parsed)
                break
    if not dates:
        raise ValueError("Chunk metadata has no parseable publication/update date.")
    now = datetime.now(timezone.utc)
    ages = [max(0.0, (now - date).days / 365.25) for date in dates]
    builder.add_chart(
        figure_id="a6_document_age",
        title="Document age distribution",
        chart_type="hist",
        payload={
            "data": histogram(ages, bins=20),
            "x_key": "bin",
            "x_label": "Age (years)",
            "y_label": "Documents/chunks",
            "series": [{"key": "count", "label": "Records"}],
        },
        caption="Age computed only for chunks with parseable date metadata.",
        source_data="data/raw/chunks.jsonl",
    )


def _query_text(row: dict[str, Any]) -> str:
    for key in ("user_query", "query", "text", "input"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _a7_ood_distance(
    builder: ManifestBuilder,
    root: Path,
) -> None:
    import numpy as np
    from acne_llm.rag.embedder import Embedder

    centroid_path = root / "config" / "ood_centroid.json"
    centroid_payload = read_json(centroid_path, {}) or {}
    centroid = np.asarray(centroid_payload.get("centroid"), dtype=np.float32)
    if centroid.ndim != 1 or not len(centroid):
        raise ValueError("config/ood_centroid.json is missing a centroid vector.")
    queries: list[str] = []
    for path in sorted((root / "evaluation" / "datasets" / "v1").glob("t1_*.jsonl")):
        queries.extend(
            text
            for row in iter_jsonl(path)
            if (text := _query_text(row))
        )
    if not queries:
        raise ValueError("No t1_*.jsonl query text found.")
    print(f"[figures_kb] embedding {len(queries):,} OOD probe queries…", flush=True)
    embedder = Embedder()
    vectors = embedder.embed_passages(queries)
    if vectors.shape[1] != centroid.shape[0]:
        raise ValueError(
            f"Centroid dim={centroid.shape[0]} but embedder dim={vectors.shape[1]}."
        )
    similarities = vectors @ centroid
    distances = [float(1.0 - value) for value in similarities]
    similarity_threshold = 0.25
    distance_threshold = 1.0 - similarity_threshold
    builder.add_chart(
        figure_id="a7_ood_distance",
        title="Query distance to OOD centroid",
        chart_type="hist",
        payload={
            "data": histogram(distances, bins=24),
            "x_key": "bin",
            "x_label": "Cosine distance (1 − similarity)",
            "y_label": "Queries",
            "series": [{"key": "count", "label": "Queries"}],
            "threshold": distance_threshold,
            "threshold_label": f"OOD boundary ({distance_threshold:.2f})",
        },
        caption="T1 queries embedded with the production embedder; the line marks the current similarity threshold converted to distance.",
        source_data="config/ood_centroid.json + evaluation/datasets/v1/t1_*.jsonl",
    )


def _a8_bm25_terms(
    builder: ManifestBuilder,
    root: Path,
) -> None:
    from acne_llm.rag.sparse import BM25Index

    path = root / "data" / "bm25_index.pkl"
    if not path.exists():
        raise ValueError("data/bm25_index.pkl does not exist.")
    index = BM25Index.load(str(path))
    if index.bm25 is None:
        raise ValueError("BM25 index is empty.")
    idf = getattr(index.bm25, "idf", {}) or {}
    doc_freqs = getattr(index.bm25, "doc_freqs", []) or []
    document_frequency: Counter[str] = Counter()
    for row in doc_freqs:
        if isinstance(row, dict):
            document_frequency.update(row.keys())
    scored: list[tuple[str, float, int, float]] = []
    for term, value in idf.items():
        token = str(term)
        if len(token) < 2 or not any(character.isalpha() for character in token):
            continue
        df = document_frequency[token]
        score = float(value) * math.log1p(df)
        scored.append((token, score, df, float(value)))
    top = sorted(scored, key=lambda item: item[1], reverse=True)[:30]
    if not top:
        raise ValueError("No BM25 terms found.")
    builder.add_chart(
        figure_id="a8_bm25_terms",
        title="Top BM25 terms",
        chart_type="bar",
        payload={
            "data": [
                {
                    "term": term,
                    "score": round(score, 6),
                    "document_frequency": df,
                    "idf": round(idf_value, 6),
                }
                for term, score, df, idf_value in top
            ],
            "x_key": "term",
            "x_label": "Term",
            "y_label": "IDF × log(1 + document frequency)",
            "series": [{"key": "score", "label": "Term weight"}],
        },
        caption="Terms ranked by IDF weighted by corpus document frequency.",
        source_data="data/bm25_index.pkl",
    )


def _message_content(row: dict[str, Any], role: str) -> str:
    messages = row.get("messages")
    if not isinstance(messages, list):
        return ""
    return "\n".join(
        str(message.get("content") or "")
        for message in messages
        if isinstance(message, dict) and message.get("role") == role
    )


def _scan_finetune(root: Path) -> dict[str, Any]:
    clean_dir = root / "data" / "finetune" / "clean"
    files = {
        split: clean_dir / f"acne_chat_response.{split}.jsonl"
        for split in ("train", "val", "test")
    }
    stats: dict[str, Any] = {
        "files": files,
        "prompt_lengths": defaultdict(list),
        "response_lengths": defaultdict(list),
        "case_types": defaultdict(Counter),
        "severity": Counter(),
        "safety_flags": Counter(),
        "is_pregnant": Counter(),
        "source_chunk_id": Counter(),
        "rows": Counter(),
    }
    for split, path in files.items():
        if not path.exists():
            continue
        print(f"[figures_kb] scanning finetune {split}: {path.name}", flush=True)
        for row in iter_jsonl(path):
            user = _message_content(row, "user")
            assistant = _message_content(row, "assistant")
            metadata = row.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            stats["prompt_lengths"][split].append(len(user))
            stats["response_lengths"][split].append(len(assistant))
            stats["rows"][split] += 1
            stats["case_types"][split][str(metadata.get("case_type") or "unknown")] += 1
            stats["severity"][str(metadata.get("severity") or "unknown")] += 1
            flags = metadata.get("safety_flags")
            if isinstance(flags, list):
                stats["safety_flags"].update(str(flag) for flag in flags if flag)
            pregnant_match = re.search(
                r'"is_pregnant"\s*:\s*(true|false)',
                user,
                re.IGNORECASE,
            )
            stats["is_pregnant"][
                pregnant_match.group(1).lower() if pregnant_match else "unknown"
            ] += 1
            chunk_id = metadata.get("source_chunk_id")
            if chunk_id:
                stats["source_chunk_id"][str(chunk_id)] += 1
    return stats


def _multi_hist(
    values: dict[str, list[float]],
    *,
    bins: int,
) -> list[dict[str, Any]]:
    all_values = [
        float(value)
        for series in values.values()
        for value in series
        if math.isfinite(float(value))
    ]
    if not all_values:
        return []
    low, high = min(all_values), max(all_values)
    if low == high:
        return [{"bin": f"{low:g}", **{key: len(series) for key, series in values.items()}}]
    width = (high - low) / bins
    counts = {key: [0] * bins for key in values}
    for key, series in values.items():
        for raw in series:
            index = min(bins - 1, int((float(raw) - low) / width))
            counts[key][index] += 1
    return [
        {
            "bin": f"{low + index * width:.0f}–{low + (index + 1) * width:.0f}",
            "bin_start": round(low + index * width, 6),
            "bin_end": round(high if index == bins - 1 else low + (index + 1) * width, 6),
            **{key: values_[index] for key, values_ in counts.items()},
        }
        for index in range(bins)
    ]


def _b1_lengths(builder: ManifestBuilder, stats: dict[str, Any]) -> None:
    values = {
        "train_prompt": stats["prompt_lengths"]["train"],
        "test_prompt": stats["prompt_lengths"]["test"],
        "train_response": stats["response_lengths"]["train"],
        "test_response": stats["response_lengths"]["test"],
    }
    data = _multi_hist(values, bins=32)
    if not data:
        raise ValueError("No train/test prompt-response lengths found.")
    builder.add_chart(
        figure_id="b1_prompt_response_length",
        title="Train vs test prompt/response length",
        chart_type="hist",
        payload={
            "data": data,
            "x_key": "bin",
            "x_label": "Characters",
            "y_label": "Examples",
            "series": [
                {"key": key, "label": key.replace("_", " ").title()}
                for key in values
            ],
        },
        caption="Overlaid character-length histograms for train and test messages.",
        source_data="data/finetune/clean/*.jsonl",
    )


def _b2_composition(builder: ManifestBuilder, stats: dict[str, Any]) -> None:
    totals = Counter()
    for counter in stats["case_types"].values():
        totals.update(counter)
    top = [label for label, _ in totals.most_common(14)]
    if not top:
        raise ValueError("No case_type metadata found.")
    data: list[dict[str, Any]] = []
    for split in ("train", "val", "test"):
        counter = stats["case_types"][split]
        row = {"file": split}
        for label in top:
            row[label] = counter[label]
        row["other"] = sum(counter.values()) - sum(counter[label] for label in top)
        data.append(row)
    builder.add_chart(
        figure_id="b2_dataset_composition",
        title="Dataset composition by split and case type",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "file",
            "x_label": "Split",
            "y_label": "Examples",
            "series": [
                {"key": label, "label": label, "stack": "case_type"}
                for label in [*top, "other"]
                if any(row.get(label) for row in data)
            ],
        },
        caption="Top case types are shown explicitly; the long tail is grouped as other.",
        source_data="data/finetune/clean/*.jsonl",
    )


def _b3_metadata_labels(builder: ManifestBuilder, stats: dict[str, Any]) -> None:
    data: list[dict[str, Any]] = []
    data.extend(
        {"dimension": "severity", "label": label, "count": count}
        for label, count in stats["severity"].most_common()
    )
    data.extend(
        {"dimension": "is_pregnant", "label": label, "count": count}
        for label, count in stats["is_pregnant"].most_common()
    )
    data.extend(
        {"dimension": "safety_flags", "label": label, "count": count}
        for label, count in stats["safety_flags"].most_common(20)
    )
    if not data:
        raise ValueError("No severity, safety_flags or pregnancy labels found.")
    builder.add_chart(
        figure_id="b3_metadata_labels",
        title="Finetune metadata label distribution",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "label",
            "x_label": "Label",
            "y_label": "Examples",
            "group_key": "dimension",
            "series": [{"key": "count", "label": "Examples"}],
        },
        caption="Severity, pregnancy state and the 20 most frequent safety flags.",
        source_data="data/finetune/clean/*.jsonl",
    )


def _contamination_path(root: Path) -> Path | None:
    path = (
        root
        / "evaluation"
        / "datasets"
        / "v1"
        / "d2_test.contamination.json"
    )
    return path if path.exists() else None


def _ensure_contamination(root: Path) -> Path | None:
    test_path = root / "evaluation" / "datasets" / "v1" / "d2_test.jsonl"
    train_path = root / "data" / "finetune" / "clean" / "acne_chat_response.train.jsonl"
    if not test_path.exists() or not train_path.exists():
        return None
    existing = _contamination_path(root)
    newest_input = max(test_path.stat().st_mtime_ns, train_path.stat().st_mtime_ns)
    if existing and existing.stat().st_mtime_ns >= newest_input:
        return existing
    print(
        "[figures_kb] contamination artifact missing/stale; "
        "running check_contamination…",
        flush=True,
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.datasets.check_contamination",
            "--test",
            test_path.relative_to(root).as_posix(),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.stdout:
        print(process.stdout, end="", flush=True)
    if process.stderr:
        print(process.stderr, end="", file=sys.stderr, flush=True)
    return _contamination_path(root)


def _b4_contamination(
    builder: ManifestBuilder,
    root: Path,
) -> None:
    path = _ensure_contamination(root)
    if path is None:
        raise ValueError("No contamination output and required train/test files are missing.")
    report = read_json(path, {}) or {}
    threshold = float(report.get("threshold") or 0.5)
    flagged = report.get("flagged")
    flagged = flagged if isinstance(flagged, list) else []
    overlaps = [
        float(row["overlap"])
        for row in flagged
        if isinstance(row, dict) and isinstance(row.get("overlap"), (int, float))
    ]
    data = histogram(overlaps, bins=12) if overlaps else [
        {
            "bin": f"< {threshold:g}",
            "bin_start": 0,
            "bin_end": threshold,
            "count": int(report.get("n_test") or 0),
        }
    ]
    builder.add_chart(
        figure_id="b4_contamination_overlap",
        title="Train-test contamination overlap",
        chart_type="hist",
        payload={
            "data": data,
            "x_key": "bin",
            "x_label": "Flagged n-gram overlap",
            "y_label": "Test samples",
            "threshold": threshold,
            "threshold_label": f"Flag threshold ({threshold:g})",
            "series": [{"key": "count", "label": "Samples"}],
            "n_test": int(report.get("n_test") or 0),
            "n_flagged": int(report.get("n_flagged") or 0),
        },
        caption="Histogram uses overlap values stored by check_contamination; unflagged samples are aggregated below threshold.",
        source_data=_source(root, path),
    )


def _b5_source_chunks(builder: ManifestBuilder, stats: dict[str, Any]) -> None:
    top = stats["source_chunk_id"].most_common(30)
    if not top:
        raise ValueError("No source_chunk_id metadata found.")
    builder.add_chart(
        figure_id="b5_source_chunk_oversampling",
        title="Top source chunks used for QA generation",
        chart_type="bar",
        payload={
            "data": [
                {"source_chunk_id": chunk_id, "count": count}
                for chunk_id, count in top
            ],
            "x_key": "source_chunk_id",
            "x_label": "Source chunk id",
            "y_label": "Generated examples",
            "series": [{"key": "count", "label": "Examples"}],
        },
        caption="Top 30 source chunks reveal concentrated QA generation and oversampling.",
        source_data="data/finetune/clean/*.jsonl",
    )


def _b6_cleaning(
    builder: ManifestBuilder,
    root: Path,
) -> None:
    reports = list((root / "data" / "finetune" / "clean").glob("*.clean_report.json"))
    if not reports:
        raise ValueError("No *.clean_report.json file found.")
    report_path = max(reports, key=lambda path: path.stat().st_mtime)
    report = read_json(report_path, {}) or {}
    before = report.get("before")
    after = report.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("Clean report has no before/after distributions.")
    before_case = before.get("case_type")
    after_case = after.get("case_type")
    if not isinstance(before_case, dict) or not isinstance(after_case, dict):
        raise ValueError("Clean report has no case_type before/after counts.")
    labels = [
        label
        for label, _ in Counter(
            {str(key): int(value) for key, value in before_case.items()}
        ).most_common(15)
    ]
    data = [
        {
            "case_type": label,
            "before": int(before_case.get(label, 0)),
            "after": int(after_case.get(label, 0)),
        }
        for label in labels
    ]
    builder.add_chart(
        figure_id="b6_cleaning_before_after",
        title="Cleaning before vs after",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "case_type",
            "x_label": "Case type",
            "y_label": "Examples",
            "series": [
                {"key": "before", "label": "Before"},
                {"key": "after", "label": "After"},
            ],
            "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
        },
        caption="Top case-type counts from the existing cleaning report.",
        source_data=_source(root, report_path),
    )


@fresh_figure_generation(("kb", "finetune"))
def generate(
    *,
    root: Path | None = None,
    output_root: Path | None = None,
    sample: int = 8_000,
    pdf: bool = False,
    generation_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Path]:
    root = (root or _repo_root()).resolve()
    output_root = output_root or root / "evaluation" / "reports" / "figures"
    kb = ManifestBuilder(
        "kb",
        output_root / "kb",
        pdf=pdf,
        generation_id=generation_id or "",
        generated_at=generated_at or "",
        generator="evaluation.analysis.figures_kb",
    )
    finetune = ManifestBuilder(
        "finetune",
        output_root / "finetune",
        pdf=pdf,
        generation_id=generation_id or "",
        generated_at=generated_at or "",
        generator="evaluation.analysis.figures_kb",
    )
    chunks_path = root / "data" / "raw" / "chunks.jsonl"
    chunks = _load_chunks(chunks_path)

    _attempt(
        kb,
        figure_id="a2_chunk_length",
        title="Chunk length distribution",
        caption="Corpus chunk lengths.",
        source_data="data/raw/chunks.jsonl",
        chart_type="hist",
        kind="chart",
        function=lambda: _a2_chunk_lengths(kb, Path("data/raw/chunks.jsonl"), chunks),
    )

    chroma_state: dict[str, Any] = {}

    def make_umap() -> None:
        ids, metadatas, vectors = _a3_umap(
            kb,
            root,
            sample,
            kb.output_dir,
        )
        chroma_state.update(
            {"ids": ids, "metadatas": metadatas, "vectors": vectors}
        )

    _attempt(
        kb,
        figure_id="a3_kb_umap",
        title="Embedding space (UMAP)",
        caption="Chroma embedding-space projection.",
        source_data="data/chroma_db",
        chart_type="scatter",
        kind="png",
        function=make_umap,
    )
    _attempt(
        kb,
        figure_id="a4_near_duplicate_rate",
        title="Near-duplicate rate (cosine > 0.95)",
        caption="Near-duplicate rate on the A3 sample.",
        source_data="data/chroma_db",
        chart_type="bar",
        kind="chart",
        function=lambda: _a4_near_duplicates(kb, chroma_state["vectors"]),
    )
    _attempt(
        kb,
        figure_id="a5_coverage_matrix",
        title="Corpus coverage matrix",
        caption="Lesion × treatment × population keyword coverage.",
        source_data="data/raw/chunks.jsonl + scripts/eval/normalizer/taxonomy.py",
        chart_type="heatmap",
        kind="png",
        function=lambda: _a5_coverage_matrix(kb, kb.output_dir, chunks),
    )
    _attempt(
        kb,
        figure_id="a6_document_age",
        title="Document age distribution",
        caption="Document age when metadata contains dates.",
        source_data="data/raw/chunks.jsonl",
        chart_type="hist",
        kind="chart",
        function=lambda: _a6_document_age(kb, chunks),
    )
    _attempt(
        kb,
        figure_id="a7_ood_distance",
        title="Query distance to OOD centroid",
        caption="T1 query distance from the production OOD centroid.",
        source_data="config/ood_centroid.json + evaluation/datasets/v1/t1_*.jsonl",
        chart_type="hist",
        kind="chart",
        function=lambda: _a7_ood_distance(kb, root),
    )
    _attempt(
        kb,
        figure_id="a8_bm25_terms",
        title="Top BM25 terms",
        caption="Weighted terms from the persisted sparse index.",
        source_data="data/bm25_index.pkl",
        chart_type="bar",
        kind="chart",
        function=lambda: _a8_bm25_terms(kb, root),
    )

    try:
        finetune_stats = _scan_finetune(root)
    except Exception as exc:
        print(f"[figures_kb] finetune scan failed: {exc}", flush=True)
        finetune_stats = {
            "prompt_lengths": defaultdict(list),
            "response_lengths": defaultdict(list),
            "case_types": defaultdict(Counter),
            "severity": Counter(),
            "safety_flags": Counter(),
            "is_pregnant": Counter(),
            "source_chunk_id": Counter(),
        }

    for figure_id, title, chart_type, function in [
        (
            "b1_prompt_response_length",
            "Train vs test prompt/response length",
            "hist",
            lambda: _b1_lengths(finetune, finetune_stats),
        ),
        (
            "b2_dataset_composition",
            "Dataset composition by split and case type",
            "bar",
            lambda: _b2_composition(finetune, finetune_stats),
        ),
        (
            "b3_metadata_labels",
            "Finetune metadata label distribution",
            "bar",
            lambda: _b3_metadata_labels(finetune, finetune_stats),
        ),
        (
            "b4_contamination_overlap",
            "Train-test contamination overlap",
            "hist",
            lambda: _b4_contamination(finetune, root),
        ),
        (
            "b5_source_chunk_oversampling",
            "Top source chunks used for QA generation",
            "bar",
            lambda: _b5_source_chunks(finetune, finetune_stats),
        ),
        (
            "b6_cleaning_before_after",
            "Cleaning before vs after",
            "bar",
            lambda: _b6_cleaning(finetune, root),
        ),
    ]:
        _attempt(
            finetune,
            figure_id=figure_id,
            title=title,
            caption="Finetune dataset analysis.",
            source_data="data/finetune/clean",
            chart_type=chart_type,
            kind="chart",
            function=function,
        )

    paths = {"kb": kb.finish(), "finetune": finetune.finish()}
    ok = sum(
        figure["status"] == "ok"
        for builder in (kb, finetune)
        for figure in builder.figures
    )
    skipped = sum(
        figure["status"] == "skipped"
        for builder in (kb, finetune)
        for figure in builder.figures
    )
    print(
        f"[figures_kb] chunks={len(chunks):,} sample={sample:,} "
        f"ok={ok} skipped={skipped} manifests={paths['kb']}, {paths['finetune']}",
        flush=True,
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=8_000)
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    sample = max(3, min(args.sample, 100_000))
    generate(sample=sample, pdf=args.pdf)


if __name__ == "__main__":
    main()
