"""Generate source-backed visualizations for the complete AcneLLM repository.

Every chart is recomputed from the current worktree.  The script deliberately
uses only canonical runtime/training/evaluation artifacts and records their
hashes in ``visualization/manifest.json``.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


# Phase 7: visualization/ -> research/dashboards/ nen sau them mot cap.
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "dashboards"
SECTIONS = (
    "KB",
    "finetune_intaker",
    "finetune_generator",
    "evaluation",
    "architecture",
    "repository",
    "_overview",
)

COLORS = ["#2563EB", "#0F9D78", "#F59E0B", "#7C3AED", "#DB2777", "#0891B2", "#64748B"]
INK = "#172033"
MUTED = "#64748B"
GRID = "#D8E0EA"
BG = "#F8FAFC"
GOOD = "#0F9D78"
BAD = "#D1495B"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10.5,
        "axes.titlesize": 16,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.edgecolor": "#94A3B8",
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "text.color": INK,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    }
)

manifest: dict = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generator": "visualization/generate_all.py",
    "artifact_policy": "fresh_compute_from_current_worktree",
    "figures": [],
    "sources": {},
}
_hash_cache: dict[Path, str] = {}


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def sha256(path: Path) -> str:
    path = path.resolve()
    if path not in _hash_cache:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        _hash_cache[path] = digest.hexdigest()
    return _hash_cache[path]


def register_sources(paths: list[Path]) -> list[str]:
    result: list[str] = []
    for path in paths:
        key = rel(path)
        result.append(key)
        if key not in manifest["sources"]:
            stat = path.stat()
            manifest["sources"][key] = {
                "bytes": stat.st_size,
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "sha256": sha256(path),
            }
    return result


def source_caption(paths: list[Path]) -> str:
    names = [rel(path) for path in paths]
    if len(names) <= 2:
        return "Nguồn: " + " · ".join(names)
    return "Nguồn: " + " · ".join(names[:2]) + f" · +{len(names) - 2} file"


def save_figure(
    fig: plt.Figure,
    section: str,
    filename: str,
    title: str,
    sources: list[Path],
    *,
    caption: str | None = None,
) -> Path:
    target = OUT / section / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    footer = caption or source_caption(sources)
    fig.text(0.01, 0.012, footer, fontsize=7.5, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.045, 1, 0.96))
    fig.savefig(target, dpi=180, bbox_inches="tight")
    plt.close(fig)
    manifest["figures"].append(
        {
            "section": section,
            "path": rel(target),
            "title": title,
            "sources": register_sources(sources),
        }
    )
    return target


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {rel(path)}:{line_no}: {exc}") from exc


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compact_label(value: object, limit: int = 38) -> str:
    text = str(value).replace("_", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def add_bar_labels(ax: plt.Axes, *, fmt: str = ",.0f", horizontal: bool = False) -> None:
    for container in ax.containers:
        labels = []
        for bar in container:
            value = bar.get_width() if horizontal else bar.get_height()
            labels.append(format(value, fmt))
        ax.bar_label(container, labels=labels, padding=3, fontsize=8.5, color=INK)


def bar_chart(
    section: str,
    filename: str,
    title: str,
    values: Counter | dict,
    sources: list[Path],
    *,
    top_n: int | None = None,
    xlabel: str = "Số bản ghi",
    color: str = COLORS[0],
    value_fmt: str = ",.0f",
    caption: str | None = None,
) -> None:
    items = sorted(values.items(), key=lambda item: item[1], reverse=True)
    if top_n:
        items = items[:top_n]
    labels = [compact_label(item[0]) for item in items][::-1]
    nums = [item[1] for item in items][::-1]
    height = max(5.2, 0.36 * len(items) + 1.8)
    fig, ax = plt.subplots(figsize=(11, height))
    ax.barh(labels, nums, color=color, alpha=0.9)
    ax.set_title(title, loc="left")
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    add_bar_labels(ax, fmt=value_fmt, horizontal=True)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, section, filename, title, sources, caption=caption)


def donut_chart(
    section: str,
    filename: str,
    title: str,
    values: Counter | dict,
    sources: list[Path],
    *,
    top_n: int = 8,
    caption: str | None = None,
) -> None:
    items = sorted(values.items(), key=lambda item: item[1], reverse=True)
    if len(items) > top_n:
        kept = items[: top_n - 1]
        kept.append(("Khác", sum(value for _, value in items[top_n - 1 :])))
        items = kept
    labels = [compact_label(key, 30) for key, _ in items]
    nums = [value for _, value in items]
    total = sum(nums)
    fig, ax = plt.subplots(figsize=(10.5, 6.3))
    wedges, _ = ax.pie(
        nums,
        startangle=90,
        colors=[COLORS[i % len(COLORS)] for i in range(len(nums))],
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.5},
    )
    ax.text(0, 0.08, f"{total:,}", ha="center", va="center", fontsize=22, weight="bold")
    ax.text(0, -0.14, "bản ghi", ha="center", va="center", color=MUTED)
    legend = [f"{label}: {value:,} ({value / total:.1%})" for label, value in zip(labels, nums)]
    ax.legend(wedges, legend, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
    ax.set_title(title, loc="left")
    save_figure(fig, section, filename, title, sources, caption=caption)


def histogram(
    section: str,
    filename: str,
    title: str,
    values: list[float],
    sources: list[Path],
    *,
    xlabel: str,
    bins: int = 40,
    color: str = COLORS[0],
    xlim: tuple[float, float] | None = None,
    caption: str | None = None,
) -> None:
    arr = np.asarray([value for value in values if value is not None and math.isfinite(value)], dtype=float)
    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.hist(arr, bins=bins, color=color, alpha=0.86, edgecolor="white", linewidth=0.5)
    median = float(np.median(arr))
    p95 = float(np.percentile(arr, 95))
    ax.axvline(median, color=COLORS[3], linewidth=2, label=f"Median: {median:,.1f}")
    ax.axvline(p95, color=COLORS[2], linewidth=2, label=f"P95: {p95:,.1f}")
    ax.set_title(title, loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Số bản ghi")
    if xlim:
        ax.set_xlim(*xlim)
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, section, filename, title, sources, caption=caption)


def heatmap(
    section: str,
    filename: str,
    title: str,
    matrix: np.ndarray,
    row_labels: list[str],
    col_labels: list[str],
    sources: list[Path],
    *,
    fmt: str = ".0f",
    cmap: str = "Blues",
    caption: str | None = None,
) -> None:
    width = max(8.5, 1.15 * len(col_labels) + 3)
    height = max(5.5, 0.55 * len(row_labels) + 2.5)
    fig, ax = plt.subplots(figsize=(width, height))
    image = ax.imshow(matrix, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(col_labels)), [compact_label(x, 25) for x in col_labels], rotation=35, ha="right")
    ax.set_yticks(range(len(row_labels)), [compact_label(x, 34) for x in row_labels])
    threshold = float(np.nanmax(matrix)) * 0.55 if matrix.size else 0
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            text = format(value, fmt) if math.isfinite(float(value)) else "—"
            ax.text(j, i, text, ha="center", va="center", fontsize=8.5,
                    color="white" if value > threshold else INK)
    ax.set_title(title, loc="left")
    fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02)
    save_figure(fig, section, filename, title, sources, caption=caption)


def grouped_bars(
    section: str,
    filename: str,
    title: str,
    categories: list[str],
    series: dict[str, list[float]],
    sources: list[Path],
    *,
    ylabel: str,
    ylim: tuple[float, float] | None = None,
    caption: str | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(max(10.5, len(categories) * 1.35), 6.2))
    x = np.arange(len(categories))
    width = min(0.78 / max(1, len(series)), 0.28)
    for index, (label, values) in enumerate(series.items()):
        offset = (index - (len(series) - 1) / 2) * width
        ax.bar(x + offset, values, width, label=label, color=COLORS[index % len(COLORS)], alpha=0.9)
    ax.set_xticks(x, [compact_label(c, 26) for c in categories], rotation=20, ha="right")
    ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_title(title, loc="left")
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
    ax.legend(frameon=False, ncol=min(4, len(series)))
    add_bar_labels(ax, fmt=".2f")
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, section, filename, title, sources, caption=caption)


def draw_flow(
    filename: str,
    title: str,
    nodes: dict[str, tuple[float, float, str, int]],
    edges: list[tuple[str, str, str]],
    sources: list[Path],
    *,
    caption: str | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(15, 8.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title(title, loc="left", pad=18)
    width, height = 0.155, 0.105
    for source, target, label in edges:
        sx, sy, _, _ = nodes[source]
        tx, ty, _, _ = nodes[target]
        arrow = FancyArrowPatch(
            (sx + width / 2 * np.sign(tx - sx), sy),
            (tx - width / 2 * np.sign(tx - sx), ty),
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.4,
            color="#718096",
            connectionstyle="arc3,rad=0.04" if abs(sy - ty) > 0.08 else "arc3,rad=0",
            zorder=1,
        )
        ax.add_patch(arrow)
        if label:
            ax.text((sx + tx) / 2, (sy + ty) / 2 + 0.025, label, fontsize=8, color=MUTED,
                    ha="center", va="center", bbox={"facecolor": "white", "edgecolor": "none", "pad": 1})
    for _, (x, y, label, color_index) in nodes.items():
        box = FancyBboxPatch(
            (x - width / 2, y - height / 2),
            width,
            height,
            boxstyle="round,pad=0.012,rounding_size=0.015",
            linewidth=1.2,
            edgecolor=COLORS[color_index % len(COLORS)],
            facecolor=COLORS[color_index % len(COLORS)] + "18",
            zorder=2,
        )
        ax.add_patch(box)
        ax.text(x, y, label, ha="center", va="center", fontsize=9, weight="bold", wrap=True, zorder=3)
    save_figure(fig, "workflow", filename, title, sources, caption=caption)


def generate_kb() -> dict:
    chunks_path = ROOT / "data/raw/chunks.jsonl"
    docs_path = ROOT / "data/raw/documents.jsonl"
    source_counts: Counter = Counter()
    source_types: Counter = Counter()
    trust: Counter = Counter()
    languages: Counter = Counter()
    categories: Counter = Counter()
    doc_chunks: Counter = Counter()
    source_docs: dict[str, set[str]] = defaultdict(set)
    lengths: list[int] = []
    positions: list[int] = []
    source_length_pairs: list[tuple[str, int]] = []
    id_to_source: dict[str, str] = {}
    for row in load_jsonl(chunks_path):
        source = row.get("source_name") or "missing"
        length = int(row.get("text_len") or len(row.get("text") or ""))
        source_counts[source] += 1
        source_types[row.get("source_type") or "missing"] += 1
        trust[row.get("trust_level") or "missing"] += 1
        languages[row.get("language") or "missing"] += 1
        categories.update(row.get("categories") or [])
        doc_id = row.get("doc_id") or "missing"
        doc_chunks[doc_id] += 1
        source_docs[source].add(doc_id)
        lengths.append(length)
        positions.append(int(row.get("position") or 0))
        source_length_pairs.append((source, length))
        id_to_source[row.get("chunk_id") or ""] = source

    document_count = sum(1 for _ in load_jsonl(docs_path))
    donut_chart("KB", "01_chunk_sources_pie.png", "KB chunks theo nguồn", source_counts, [chunks_path], top_n=11)
    bar_chart("KB", "02_top_chunk_sources.png", "Top nguồn đóng góp chunks", source_counts, [chunks_path], top_n=20)
    donut_chart("KB", "03_source_type_distribution.png", "Cơ cấu loại nguồn KB", source_types, [chunks_path], top_n=10)
    donut_chart("KB", "04_trust_level_distribution.png", "Mức độ tin cậy của chunks", trust, [chunks_path])
    donut_chart("KB", "05_language_distribution.png", "Ngôn ngữ của KB", languages, [chunks_path])
    bar_chart("KB", "06_category_distribution.png", "Chủ đề được gắn cho chunks", categories, [chunks_path], top_n=18)
    histogram("KB", "07_chunk_length_histogram.png", "Phân phối độ dài chunk", lengths, [chunks_path],
              xlabel="Độ dài chunk (ký tự)", bins=50, xlim=(0, float(np.percentile(lengths, 99.5))))
    histogram("KB", "08_chunks_per_document_histogram.png", "Số chunks trên mỗi tài liệu", list(doc_chunks.values()),
              [chunks_path, docs_path], xlabel="Chunks / tài liệu", bins=45,
              xlim=(0, float(np.percentile(list(doc_chunks.values()), 99))))
    top_sources = [name for name, _ in source_counts.most_common(6)]
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    for index, source in enumerate(top_sources):
        vals = [length for name, length in source_length_pairs if name == source]
        ax.hist(vals, bins=35, histtype="step", linewidth=2, color=COLORS[index], label=f"{source} (n={len(vals):,})")
    ax.set_title("Độ dài chunk của 6 nguồn lớn nhất", loc="left")
    ax.set_xlabel("Ký tự / chunk")
    ax.set_ylabel("Số chunks")
    ax.set_xlim(0, np.percentile(lengths, 99))
    ax.grid(axis="y", color=GRID, alpha=0.8)
    ax.legend(frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "KB", "09_chunk_length_by_source.png", "Độ dài chunk của 6 nguồn lớn nhất", [chunks_path])

    top = [name for name, _ in source_counts.most_common(15)]
    matrix = np.array([[len(source_docs[name]), source_counts[name]] for name in top], dtype=float)
    normalized = matrix / np.maximum(matrix.max(axis=0, keepdims=True), 1)
    heatmap("KB", "10_document_chunk_coverage.png", "Độ phủ tài liệu và chunk theo nguồn (chuẩn hóa theo cột)",
            normalized, top, ["Số tài liệu", "Số chunks"], [chunks_path, docs_path], fmt=".2f",
            caption=f"Giá trị chuẩn hóa 0–1 · {document_count:,} documents · {len(lengths):,} chunks · nguồn: data/raw")
    histogram("KB", "11_chunk_position_histogram.png", "Vị trí chunk trong tài liệu", positions, [chunks_path],
              xlabel="Chỉ số vị trí chunk", bins=max(10, min(50, max(positions) + 1)),
              xlim=(0, float(np.percentile(positions, 99.5))))
    return {
        "chunk_count": len(lengths),
        "document_count": document_count,
        "source_count": len(source_counts),
        "id_to_source": id_to_source,
        "sources": source_counts,
    }


def _last_message(messages: list[dict], role: str) -> str:
    matches = [str(item.get("content") or "") for item in messages if item.get("role") == role]
    return matches[-1] if matches else ""


def _field_has_value(value: object) -> bool:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    return value not in (None, "", [], {})


def generate_intaker() -> dict:
    records_path = ROOT / "research/datagen/intakedata/output/intake/intake.records.jsonl"
    train_path = ROOT / "research/datagen/intakedata/output/intake/intake.train.jsonl"
    val_path = ROOT / "research/datagen/intakedata/output/intake/intake.val.jsonl"
    summary_path = ROOT / "research/datagen/intakedata/output/intake/summary.json"
    records = list(load_jsonl(records_path))
    case_counts: Counter = Counter()
    intent_counts: Counter = Counter()
    sources: Counter = Counter()
    judged: Counter = Counter()
    case_intent: Counter = Counter()
    user_lengths: list[int] = []
    confidences: list[float] = []
    field_presence: Counter = Counter()
    parse_fail = 0
    for row in records:
        meta = row.get("meta") or {}
        case = meta.get("case_type") or "missing"
        case_counts[case] += 1
        sources[meta.get("source") or "missing"] += 1
        judged[str(bool(meta.get("judged")))] += 1
        user_lengths.append(len(_last_message(row.get("messages") or [], "user")))
        try:
            output = json.loads(_last_message(row.get("messages") or [], "assistant"))
        except json.JSONDecodeError:
            parse_fail += 1
            continue
        intent = output.get("intent") or "missing"
        intent_counts[intent] += 1
        case_intent[(case, intent)] += 1
        if isinstance(output.get("confidence"), (int, float)):
            confidences.append(float(output["confidence"]))
        for group in ("context", "clinical"):
            payload = output.get(group)
            if isinstance(payload, dict):
                for key, value in payload.items():
                    if _field_has_value(value):
                        field_presence[f"{group}.{key}"] += 1

    train_n = sum(1 for _ in load_jsonl(train_path))
    val_n = sum(1 for _ in load_jsonl(val_path))
    summary = load_json(summary_path)
    donut_chart("finetune_intaker", "01_train_val_split.png", "Intaker: train/validation split",
                {"train": train_n, "validation": val_n}, [train_path, val_path])
    donut_chart("finetune_intaker", "02_intent_distribution.png", "Intaker: phân phối intent đích",
                intent_counts, [records_path])
    bar_chart("finetune_intaker", "03_case_type_distribution.png", "Intaker: độ phủ case type",
              case_counts, [records_path], top_n=25)
    case_labels = [name for name, _ in case_counts.most_common()]
    intent_labels = [name for name in ("advise", "knowledge", "clarify", "reject") if name in intent_counts]
    matrix = np.array([[case_intent[(case, intent)] for intent in intent_labels] for case in case_labels], dtype=float)
    heatmap("finetune_intaker", "04_case_intent_matrix.png", "Intaker: ánh xạ case type → intent",
            matrix, case_labels, intent_labels, [records_path])
    histogram("finetune_intaker", "05_user_length_histogram.png", "Intaker: độ dài câu người dùng",
              user_lengths, [records_path], xlabel="Ký tự / user message", bins=45,
              xlim=(0, float(np.percentile(user_lengths, 99.5))))
    histogram("finetune_intaker", "06_confidence_histogram.png", "Intaker: confidence trong output",
              confidences, [records_path], xlabel="Confidence", bins=25, xlim=(0, 1.02), color=COLORS[1])
    bar_chart("finetune_intaker", "07_extracted_field_presence.png", "Intaker: trường có giá trị trong nhãn",
              field_presence, [records_path], top_n=30, xlabel="Số mẫu có giá trị", color=COLORS[3])
    donut_chart("finetune_intaker", "08_generation_sources.png", "Intaker: nguồn tạo dữ liệu",
                sources, [records_path])
    reject_reasons = Counter(summary.get("reject_reasons") or {})
    if reject_reasons:
        bar_chart("finetune_intaker", "09_rejected_attempt_reasons.png", "Intaker: lý do loại attempt khi datagen",
                  reject_reasons, [summary_path], color=BAD)
    target_counts = summary.get("case_targets") or {}
    actual_counts = summary.get("case_counts") or {}
    categories = list(target_counts)
    grouped_bars("finetune_intaker", "10_target_vs_actual.png", "Intaker: quota mục tiêu và số đã nhận",
                 categories, {"Mục tiêu": [target_counts[x] for x in categories], "Đã nhận": [actual_counts.get(x, 0) for x in categories]},
                 [summary_path], ylabel="Số mẫu")
    return {
        "records": len(records),
        "train": train_n,
        "validation": val_n,
        "parse_failures": parse_fail,
        "intents": intent_counts,
    }


def generate_generator() -> dict:
    base = ROOT / "research/datagen/roledata"
    output = base / "output"
    master_path = output / "roledata.train.jsonl"
    split_paths = {split: output / "splits" / f"{split}.jsonl" for split in ("train", "val", "holdout")}
    summary_path = output / "generation_summary.json"
    rejected_path = output / "rejected.audit.jsonl"
    export_path = output / "export/acnellm_role_lora.jsonl"
    checksum_path = output / "checksum.sha256"
    taxonomy_path = base / "taxonomy.yaml"

    rows = list(load_jsonl(master_path))
    summary = load_json(summary_path)
    sample_kinds: Counter = Counter()
    families: Counter = Counter()
    input_styles: Counter = Counter()
    contexts: Counter = Counter()
    context_source_counts: Counter = Counter()
    context_source_names: Counter = Counter()
    audiences: Counter = Counter()
    models: Counter = Counter()
    gate_results: Counter = Counter()
    message_counts: Counter = Counter()
    user_lengths: list[int] = []
    assistant_lengths: list[int] = []
    anchor_groups: Counter = Counter()
    style_kind: Counter = Counter()
    master_ids: set[str] = set()
    for row in rows:
        row_id = str(row.get("id") or "")
        master_ids.add(row_id)
        kind = row.get("sample_kind") or "missing"
        style = row.get("input_style") or "missing"
        sample_kinds[kind] += 1
        families[str(kind)[0] if str(kind)[:1] in {"R", "B", "K"} else "other"] += 1
        input_styles[style] += 1
        style_kind[(kind, style)] += 1
        contexts["Có context" if row.get("context") else "Không context"] += 1
        context_items = row.get("synthetic_context") or []
        context_source_counts[len(row.get("synthetic_context_sources") or [])] += 1
        if isinstance(context_items, list):
            for item in context_items:
                if isinstance(item, dict):
                    context_source_names[item.get("source_name") or "missing"] += 1
        metadata = row.get("generation_meta") or {}
        audiences[metadata.get("audience") or "missing"] += 1
        models[row.get("gen_model") or "missing"] += 1
        gate_results["passed" if (row.get("gate_results") or {}).get("passed") else "failed"] += 1
        messages = row.get("messages") or []
        message_counts[len(messages)] += 1
        user_lengths.append(sum(len(str(message.get("content") or "")) for message in messages if message.get("role") == "user"))
        assistant_lengths.append(sum(len(str(message.get("content") or "")) for message in messages if message.get("role") == "assistant"))
        if row.get("anchor_group"):
            anchor_groups[str(row["anchor_group"])] += 1

    split_rows = {name: list(load_jsonl(path)) for name, path in split_paths.items()}
    split_counts = Counter({name: len(values) for name, values in split_rows.items()})
    split_kind: Counter = Counter()
    split_ids: dict[str, set[str]] = {}
    for split, values in split_rows.items():
        split_ids[split] = {str(row.get("id") or "") for row in values}
        for row in values:
            split_kind[(row.get("sample_kind") or "missing", split)] += 1

    rejected = list(load_jsonl(rejected_path))
    rejection_reasons: Counter = Counter()
    rejection_cases: Counter = Counter()
    rejection_attempts: Counter = Counter()
    rejected_ids: set[str] = set()
    for row in rejected:
        rejected_ids.add(str(row.get("id") or ""))
        rejection_cases[row.get("case") or "missing"] += 1
        rejection_attempts[str(row.get("content_attempt") or "missing")] += 1
        reasons = row.get("reasons") or []
        if reasons:
            rejection_reasons.update(str(reason) for reason in reasons)
            continue
        error = str(row.get("error") or "")
        if "input_style" in error:
            rejection_reasons["input_style_schedule"] += 1
        elif "insufficient_quota" in error:
            rejection_reasons["provider_quota_429"] += 1
        elif "each turn must be an object" in error:
            rejection_reasons["invalid_turn_object"] += 1
        else:
            rejection_reasons[row.get("error_type") or "unclassified"] += 1

    paths = [master_path, *split_paths.values(), summary_path, rejected_path, export_path, checksum_path, taxonomy_path]
    donut_chart("finetune_generator", "01_split_distribution.png", "Roledata Generator: train / validation / holdout", split_counts, list(split_paths.values()))

    target = int(summary.get("target") or 0)
    accepted = int(summary.get("accepted") or len(rows))
    bar_chart("finetune_generator", "02_generation_completion.png", "Roledata Generator: tiến độ full target",
              {"Đã accepted": accepted, "Còn thiếu": max(0, target - accepted)}, [summary_path], color=COLORS[1],
              caption=f"status={summary.get('status')} · target={target:,} · accepted={accepted:,} · deficit={max(0, target-accepted):,}")
    bar_chart("finetune_generator", "03_sample_kind_distribution.png", "Roledata Generator: sample_kind",
              sample_kinds, [master_path, taxonomy_path], top_n=25)
    donut_chart("finetune_generator", "04_sample_family_distribution.png", "Roledata Generator: họ R / B / K", families, [master_path, taxonomy_path])
    donut_chart("finetune_generator", "05_input_style_distribution.png", "Roledata Generator: input_style", input_styles, [master_path])
    donut_chart("finetune_generator", "06_context_coverage.png", "Roledata Generator: record có synthetic context", contexts, [master_path])
    bar_chart("finetune_generator", "07_context_source_count.png", "Roledata Generator: số context sources / record",
              {str(key): value for key, value in context_source_counts.items()}, [master_path], xlabel="Số records")
    bar_chart("finetune_generator", "08_context_source_names.png", "Roledata Generator: nguồn synthetic context",
              context_source_names, [master_path, ROOT / "data/raw/chunks.jsonl"], top_n=20)
    histogram("finetune_generator", "09_user_length_histogram.png", "Roledata Generator: tổng độ dài user turns",
              user_lengths, [master_path], xlabel="Ký tự user / record", bins=50,
              xlim=(0, float(np.percentile(user_lengths, 99.5))))
    histogram("finetune_generator", "10_answer_length_histogram.png", "Roledata Generator: tổng độ dài assistant turns",
              assistant_lengths, [master_path], xlabel="Ký tự assistant / record", bins=50, color=COLORS[1],
              xlim=(0, float(np.percentile(assistant_lengths, 99.5))))
    bar_chart("finetune_generator", "11_message_count_distribution.png", "Roledata Generator: số messages / record",
              {str(key): value for key, value in message_counts.items()}, [master_path])
    bar_chart("finetune_generator", "12_audience_distribution.png", "Roledata Generator: audience metadata",
              audiences, [master_path], top_n=12)
    donut_chart("finetune_generator", "13_generation_model_distribution.png", "Roledata Generator: gen_model", models, [master_path])
    donut_chart("finetune_generator", "14_gate_result_distribution.png", "Roledata Generator: stored gate result", gate_results, [master_path])

    kind_labels = [name for name, _ in sample_kinds.most_common()]
    split_labels = ["train", "val", "holdout"]
    matrix = np.array([[split_kind[(kind, split)] for split in split_labels] for kind in kind_labels], dtype=float)
    heatmap("finetune_generator", "15_sample_kind_by_split.png", "Roledata Generator: sample_kind theo split",
            matrix, kind_labels, split_labels, list(split_paths.values()))
    style_labels = [name for name, _ in input_styles.most_common()]
    matrix = np.array([[style_kind[(kind, style)] for style in style_labels] for kind in kind_labels], dtype=float)
    heatmap("finetune_generator", "16_input_style_by_sample_kind.png", "Roledata Generator: input_style theo sample_kind",
            matrix, kind_labels, style_labels, [master_path])
    bar_chart("finetune_generator", "17_rejection_reasons.png", "Roledata Generator: lý do rejected audit",
              rejection_reasons, [rejected_path], top_n=20, color=BAD,
              caption=f"Append-only audit: {len(rejected):,} attempts / {len(rejected_ids):,} unique IDs; grouped from reasons/error strings.")
    bar_chart("finetune_generator", "18_rejection_cases.png", "Roledata Generator: rejected attempts theo case",
              rejection_cases, [rejected_path], top_n=20, color=BAD)
    bar_chart("finetune_generator", "19_rejection_attempt_number.png", "Roledata Generator: content_attempt trong audit",
              rejection_attempts, [rejected_path], color=COLORS[2])
    retry_outcome = {
        "Rejected rồi accepted": len(master_ids & rejected_ids),
        "Rejected chưa accepted": len(rejected_ids - master_ids),
        "Accepted không có reject trước": len(master_ids - rejected_ids),
    }
    donut_chart("finetune_generator", "20_retry_outcomes.png", "Roledata Generator: kết quả theo ID có retry history",
                retry_outcome, [master_path, rejected_path])
    anchor_sizes = Counter(anchor_groups.values())
    bar_chart("finetune_generator", "21_anchor_group_pair_sizes.png", "Roledata Generator: kích thước B5 anchor groups",
              {f"{size} records/group": groups for size, groups in anchor_sizes.items()}, [master_path], color=COLORS[3])

    union_ids = set().union(*split_ids.values())
    overlap_count = sum(len(split_ids[a] & split_ids[b]) for a, b in (("train", "val"), ("train", "holdout"), ("val", "holdout")))
    checksum_expected = checksum_path.read_text(encoding="utf-8").split()[0]
    checksum_actual = sha256(export_path)
    integrity_rows = [
        ["Master IDs", f"{len(master_ids):,}", "unique" if len(master_ids) == len(rows) else "duplicates"],
        ["Split union", f"{len(union_ids):,}", "matches master" if union_ids == master_ids else "mismatch"],
        ["Cross-split overlap", f"{overlap_count:,}", "pass" if overlap_count == 0 else "fail"],
        ["Stored gates", f"{gate_results['passed']:,}/{len(rows):,}", "pass" if gate_results["failed"] == 0 else "fail"],
        ["Export checksum", checksum_actual[:12] + "…", "match" if checksum_actual == checksum_expected else "mismatch"],
    ]
    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    ax.axis("off")
    table = ax.table(cellText=integrity_rows, colLabels=["Check", "Evidence", "Status"], cellLoc="left", colLoc="left",
                     loc="center", colWidths=[0.32, 0.32, 0.25])
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.8)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor(GRID)
        if row == 0:
            cell.set_facecolor("#E8EEF8")
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor("white" if row % 2 else BG)
    ax.set_title("Roledata Generator: integrity checks", loc="left", pad=16)
    save_figure(fig, "finetune_generator", "22_integrity_checks.png", "Roledata Generator integrity checks", paths)
    return {
        "source_root": "datagen/roledata",
        "status": summary.get("status"),
        "target": target,
        "rows": len(rows),
        "deficit": max(0, target - len(rows)),
        "splits": split_counts,
        "sample_kinds": len(sample_kinds),
        "audit_attempts": len(rejected),
        "audit_unique_ids": len(rejected_ids),
        "split_overlap": overlap_count,
        "export_checksum_match": checksum_actual == checksum_expected,
    }


def generate_evaluation(kb: dict) -> dict:
    eval_dataset_path = ROOT / "research/evaluation/datasets/active/generator_eval.v3_2_145.jsonl"
    run_root = ROOT / "research/evaluation/reports/run_full_v3_2"
    run_summary_path = run_root / "summary.json"
    intake_path = run_root / "intake/report.json"
    retrieval_path = run_root / "retrieval/results.json"
    ablation_results_path = run_root / "ablation/results.json"
    ablation_summary_path = run_root / "ablation/summary.json"

    task_types: Counter = Counter()
    intents: Counter = Counter()
    expected_sources: Counter = Counter()
    relevant_counts: list[int] = []
    dataset_rows = list(load_jsonl(eval_dataset_path))
    for row in dataset_rows:
        task_types[row.get("task_type") or "missing"] += 1
        intents[row.get("intent_label") or "missing"] += 1
        chunks = row.get("relevant_chunk_ids") or []
        relevant_counts.append(len(chunks))
        for chunk_id in chunks:
            expected_sources[kb["id_to_source"].get(chunk_id, "unknown_or_guideline")] += 1
    donut_chart("evaluation", "01_dataset_task_types.png", "Eval v3.2: task type", task_types, [eval_dataset_path])
    donut_chart("evaluation", "02_dataset_intents.png", "Eval v3.2: intent labels", intents, [eval_dataset_path])
    bar_chart("evaluation", "03_expected_kb_sources.png", "Eval v3.2: nguồn chunk được gắn relevant",
              expected_sources, [eval_dataset_path, ROOT / "data/raw/chunks.jsonl"], top_n=18)
    histogram("evaluation", "04_relevant_chunks_per_question.png", "Eval v3.2: số relevant chunks / câu hỏi",
              relevant_counts, [eval_dataset_path], xlabel="Relevant chunks / câu hỏi", bins=range(0, max(relevant_counts) + 2))

    run_summary = load_json(run_summary_path)
    steps = run_summary.get("steps") or []
    fig, ax = plt.subplots(figsize=(12, 5.8))
    labels = [step.get("label") or step.get("id") for step in steps]
    durations = [float(step.get("duration_s") or 0) for step in steps]
    colors = [GOOD if step.get("status") == "ok" else COLORS[2] if step.get("status") == "skipped" else BAD for step in steps]
    bars = ax.barh(labels[::-1], durations[::-1], color=colors[::-1])
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("Thời gian (giây, symlog)")
    ax.set_title("Lần gọi cuối của run_full_v3_2", loc="left")
    ax.grid(axis="x", color=GRID, alpha=0.8)
    for bar, duration, step in zip(bars, durations[::-1], steps[::-1]):
        ax.text(max(bar.get_width(), 0.04), bar.get_y() + bar.get_height() / 2,
                f" {duration:,.1f}s · {step.get('status')}", va="center", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "evaluation", "05_run_timeline.png", "Lần gọi cuối của run_full_v3_2", [run_summary_path],
                caption="summary.json ghi intake/retrieval skipped trong lần resume cuối; artifact của hai bước vẫn được vẽ từ file riêng.")

    intake = load_json(intake_path)
    metrics = intake["metrics"]
    headline = {
        "Schema valid": metrics["format"]["schema_valid_rate"],
        "Intent accuracy": metrics["intent"]["accuracy"],
        "Intent macro-F1": metrics["intent"]["macro_f1"],
        "Reject recall": metrics["intent"]["reject_recall"],
        "Extraction micro-F1": metrics["extraction"]["micro"]["f1"],
        "1 − hallucinated rate": 1 - metrics["extraction"]["hallucinated_field_rate"],
    }
    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    names, vals = list(headline), list(headline.values())
    bars = ax.barh(names[::-1], vals[::-1], color=[COLORS[i % len(COLORS)] for i in range(len(vals))][::-1])
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Tỷ lệ / score 0–1")
    ax.set_title(f"Intaker eval: {intake['rows_evaluated']:,} mẫu", loc="left")
    ax.grid(axis="x", color=GRID, alpha=0.8)
    for bar, value in zip(bars, vals[::-1]):
        ax.text(value + 0.012, bar.get_y() + bar.get_height() / 2, f"{value:.3f}", va="center")
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "evaluation", "06_intake_headline_metrics.png", "Intaker headline metrics", [intake_path])

    confusion = metrics["intent"]["confusion_matrix"]
    classes = list(confusion)
    confusion_matrix = np.array([[confusion[gold].get(pred, 0) for pred in classes] for gold in classes], dtype=float)
    heatmap("evaluation", "07_intake_confusion_matrix.png", "Intaker: confusion matrix (gold × predicted)",
            confusion_matrix, classes, classes, [intake_path])
    per_class = metrics["intent"]["per_class"]
    grouped_bars("evaluation", "08_intake_per_intent_prf.png", "Intaker: precision / recall / F1 theo intent",
                 classes, {metric.upper(): [per_class[c][metric] for c in classes] for metric in ("precision", "recall", "f1")},
                 [intake_path], ylabel="Score", ylim=(0, 1.08))

    per_field = metrics["extraction"]["per_field"]
    field_f1 = {name: values.get("f1", 0) for name, values in per_field.items()}
    bar_chart("evaluation", "09_intake_extraction_field_f1.png", "Intaker: extraction F1 theo field", field_f1,
              [intake_path], xlabel="F1", color=COLORS[3], value_fmt=".3f")
    scalar = metrics.get("scalar_accuracy") or {}
    list_prf = {name: values.get("f1", 0) for name, values in (metrics.get("list_prf") or {}).items()}
    combined = {f"scalar · {name}": value for name, value in scalar.items()}
    combined.update({f"list · {name}": value for name, value in list_prf.items()})
    bar_chart("evaluation", "10_intake_scalar_list_quality.png", "Intaker: scalar accuracy và list F1", combined,
              [intake_path], xlabel="Score", color=COLORS[1], value_fmt=".3f")
    latency = metrics["latency"]
    grouped_bars("evaluation", "11_intake_latency.png", "Intaker: latency percentiles",
                 ["P50", "P95"], {"Latency": [latency["p50_ms"], latency["p95_ms"]]}, [intake_path], ylabel="Milliseconds")

    retrieval = load_json(retrieval_path)
    ret_summary = retrieval["summary"]
    ret_rows = retrieval["rows"]
    faces = ret_summary.get("faces") or {}
    ret_metrics = {key: value for key, value in faces.items() if isinstance(value, (int, float))}
    bar_chart("evaluation", "12_retrieval_headline_metrics.png", "Retrieval: judge metrics", ret_metrics,
              [retrieval_path], xlabel="Mean score", color=COLORS[1], value_fmt=".3f")
    source_types: Counter = Counter()
    retrieval_sources: Counter = Counter()
    n_chunks: list[int] = []
    score_series: dict[str, list[float]] = defaultdict(list)
    for row in ret_rows:
        source_types.update(row.get("source_types") or [])
        retrieval_sources.update(row.get("sources") or [])
        n_chunks.append(int(row.get("n_chunks") or 0))
        for key in ("context_relevance", "context_precision", "context_sufficiency", "ranking_quality", "groundedness"):
            if isinstance(row.get(key), (int, float)):
                score_series[key].append(float(row[key]))
    bar_chart("evaluation", "13_retrieval_source_types.png", "Retrieval: source types xuất hiện trong context",
              source_types, [retrieval_path], top_n=18)
    bar_chart("evaluation", "14_retrieval_sources.png", "Retrieval: top nguồn xuất hiện trong context",
              retrieval_sources, [retrieval_path], top_n=18)
    histogram("evaluation", "15_retrieved_chunk_count.png", "Retrieval: số chunks trả về mỗi câu hỏi", n_chunks,
              [retrieval_path], xlabel="Chunks / câu hỏi", bins=range(0, max(n_chunks) + 2))
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    for ax, (key, values) in zip(axes.flat, score_series.items()):
        ax.hist(values, bins=15, color=COLORS[len(ax.lines) % len(COLORS)], alpha=0.85, edgecolor="white")
        ax.set_title(compact_label(key, 28))
        ax.set_xlabel("Score")
        ax.set_ylabel("Cases")
        ax.grid(axis="y", color=GRID, alpha=0.7)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in axes.flat[len(score_series):]:
        ax.axis("off")
    fig.suptitle("Retrieval: phân phối judge scores", x=0.01, ha="left", fontsize=16, weight="bold")
    save_figure(fig, "evaluation", "16_retrieval_score_distributions.png", "Retrieval score distributions", [retrieval_path])

    ablation = load_json(ablation_results_path)
    arm_order = list(ablation["arms"])
    arm_summary = {arm: ablation["arms"][arm]["summary"] for arm in arm_order}
    arm_design = [
        ["RRR", "Real", "Real", "Local acne-generator"],
        ["ORR", "Oracle", "Real", "Local acne-generator"],
        ["RNO", "Real", "No RAG", "API deepseek-v4-pro"],
        ["RNR", "Real", "No RAG", "Local acne-generator"],
        ["ROR", "Real", "Oracle", "Local acne-generator"],
        ["RRO", "Real", "Real", "API deepseek-v4-pro"],
    ]
    fig, ax = plt.subplots(figsize=(11.5, 5.7))
    ax.axis("off")
    table = ax.table(
        cellText=arm_design,
        colLabels=["Arm", "Intake", "RAG", "Generator"],
        cellLoc="left",
        colLoc="left",
        loc="center",
        colWidths=[0.10, 0.18, 0.18, 0.42],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.8)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor(GRID)
        if row == 0:
            cell.set_facecolor("#E8EEF8")
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor("white" if row % 2 else BG)
    ax.set_title("Ablation: thiết kế sáu arm", loc="left", pad=16)
    save_figure(fig, "evaluation", "17_ablation_arm_design.png", "Thiết kế sáu ablation arms", [ablation_results_path])
    grouped_bars("evaluation", "17_ablation_execution.png", "Ablation: thành công, failed/unavailable và safety failures",
                 arm_order,
                 {
                     "Successful": [arm_summary[a]["successful"] for a in arm_order],
                     "Failed / unavailable": [arm_summary[a]["failed"] for a in arm_order],
                     "Safety failed": [arm_summary[a]["safety_failures"] for a in arm_order],
                 },
                 [ablation_results_path], ylabel="Số câu hỏi")
    grouped_bars("evaluation", "18_ablation_answer_tone.png", "Ablation: answer quality và role tone",
                 arm_order,
                 {
                     "Answer quality": [arm_summary[a]["face_means"]["answer_quality"] for a in arm_order],
                     "Role tone": [arm_summary[a]["face_means"]["role_tone"] for a in arm_order],
                 },
                 [ablation_results_path], ylabel="Mean judge score", ylim=(0, 5.2))
    grouped_bars("evaluation", "19_ablation_content_errors.png", "Ablation: incorrect và missing content (thấp hơn tốt hơn)",
                 arm_order,
                 {
                     "Incorrect": [arm_summary[a]["face_means"]["incorrect_content"] for a in arm_order],
                     "Missing": [arm_summary[a]["face_means"]["missing_content"] for a in arm_order],
                 },
                 [ablation_results_path], ylabel="Mean judge score", ylim=(0, 3.0))
    retrieval_arms = [a for a in arm_order if arm_summary[a]["face_means"].get("context_relevance") is not None]
    grouped_bars("evaluation", "20_ablation_rag_faces.png", "Ablation: RAG judge faces",
                 retrieval_arms,
                 {
                     "Context relevance": [arm_summary[a]["face_means"]["context_relevance"] for a in retrieval_arms],
                     "Context sufficiency": [arm_summary[a]["face_means"]["context_sufficiency"] for a in retrieval_arms],
                     "Groundedness": [arm_summary[a]["face_means"]["groundedness"] for a in retrieval_arms],
                 },
                 [ablation_results_path], ylabel="Mean judge score", ylim=(0, 5.2))
    grouped_bars("evaluation", "21_ablation_precision_ranking.png", "Ablation: context precision và ranking quality",
                 retrieval_arms,
                 {
                     "Context precision": [arm_summary[a]["face_means"]["context_precision"] for a in retrieval_arms],
                     "Ranking quality": [arm_summary[a]["face_means"]["ranking_quality"] for a in retrieval_arms],
                 },
                 [ablation_results_path], ylabel="Mean score", ylim=(0, 1.08))

    paired = load_json(ablation_summary_path)["arms"]
    forest_arms, deltas, lo, hi = [], [], [], [],
    for arm, values in paired.items():
        quality = values["quality"]["answer_quality"]
        if quality.get("mean_delta") is None:
            continue
        forest_arms.append(arm)
        deltas.append(float(quality["mean_delta"]))
        lo.append(float(quality["bootstrap_95_ci_mean"][0]))
        hi.append(float(quality["bootstrap_95_ci_mean"][1]))
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    y = np.arange(len(forest_arms))
    xerr = np.array([np.array(deltas) - np.array(lo), np.array(hi) - np.array(deltas)])
    ax.errorbar(deltas, y, xerr=xerr, fmt="o", color=COLORS[0], ecolor=COLORS[0], capsize=5, markersize=8)
    ax.axvline(0, color=INK, linewidth=1)
    ax.set_yticks(y, forest_arms)
    ax.set_xlabel("Mean delta answer quality so với RRR (95% bootstrap CI)")
    ax.set_title("Ablation: paired answer-quality delta", loc="left")
    ax.grid(axis="x", color=GRID, alpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "evaluation", "22_ablation_paired_delta_forest.png", "Paired answer-quality delta", [ablation_summary_path])

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    for index, arm in enumerate(arm_order):
        score = arm_summary[arm]["face_means"]["answer_quality"]
        cost = arm_summary[arm].get("judge_cost_usd") or 0
        ax.scatter(cost, score, s=120, color=COLORS[index % len(COLORS)], label=arm, edgecolor="white", linewidth=1)
        ax.annotate(arm, (cost, score), xytext=(6, 6), textcoords="offset points")
    ax.set_xlabel("Judge cost ghi trong artifact (USD)")
    ax.set_ylabel("Mean answer quality")
    ax.set_title("Ablation: judge cost và answer quality", loc="left")
    ax.grid(color=GRID, alpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "evaluation", "23_ablation_cost_quality.png", "Judge cost và answer quality", [ablation_results_path],
                caption="Chi phí là judge_cost_usd trong artifact, không phải tổng chi phí generator.")

    distributions = []
    latencies = []
    for arm in arm_order:
        answer_values, latency_values = [], []
        for item in ablation["arms"][arm]["items"]:
            score = (item.get("scorecard") or {}).get("answer_quality")
            if isinstance(score, (int, float)):
                answer_values.append(float(score))
            if isinstance(item.get("latency_ms"), (int, float)):
                latency_values.append(float(item["latency_ms"]) / 1000)
        distributions.append(answer_values)
        latencies.append(latency_values)
    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    box = ax.boxplot(distributions, tick_labels=arm_order, patch_artist=True, showmeans=True)
    for index, patch in enumerate(box["boxes"]):
        patch.set_facecolor(COLORS[index % len(COLORS)] + "80")
    ax.set_ylabel("Answer quality score")
    ax.set_title("Ablation: phân phối answer quality theo arm", loc="left")
    ax.grid(axis="y", color=GRID, alpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "evaluation", "24_ablation_answer_quality_boxplot.png", "Answer quality distributions", [ablation_results_path])
    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    box = ax.boxplot(latencies, tick_labels=arm_order, patch_artist=True, showmeans=True, showfliers=False)
    for index, patch in enumerate(box["boxes"]):
        patch.set_facecolor(COLORS[index % len(COLORS)] + "80")
    ax.set_ylabel("Latency / question (seconds)")
    ax.set_title("Ablation: latency theo arm (không hiển thị outlier)", loc="left")
    ax.grid(axis="y", color=GRID, alpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "evaluation", "25_ablation_latency_boxplot.png", "Ablation latency distributions", [ablation_results_path])
    return {
        "dataset_rows": len(dataset_rows),
        "intake_rows": intake["rows_evaluated"],
        "retrieval_rows": ret_summary["n"],
        "ablation_arms": len(arm_order),
        "ablation_rows": sum(arm_summary[a]["rows"] for a in arm_order),
    }


def generate_workflows() -> None:
    runtime_sources = [
        ROOT / "src/acne_llm/api/routes/chat.py",
        ROOT / "src/acne_llm/chat/runtime.py",
        ROOT / "src/acne_llm/chat/orchestrator.py",
        ROOT / "src/acne_llm/chat/intake.py",
        ROOT / "src/acne_llm/chat/_retrieval.py",
        ROOT / "src/acne_llm/llm/prompt_builder.py",
        ROOT / "src/acne_llm/llm/ollama_backend.py",
        ROOT / "src/acne_llm/db/session_store.py",
        ROOT / "src/acne_llm/db/audit.py",
    ]
    nodes = {
        "input": (0.08, 0.72, "HTTP SSE /\nWebSocket input", 0),
        "route": (0.25, 0.72, "chat route\nstream_chat_sse", 0),
        "intake": (0.42, 0.72, "run_intake\npreprocess + safety + route", 1),
        "stop": (0.42, 0.32, "reject / clarify\nshort-circuit", 4),
        "rag": (0.60, 0.72, "Hybrid retrieval\nBM25 + Chroma + rerank", 2),
        "prompt": (0.76, 0.72, "PromptBuilder\ncontext + history", 3),
        "llm": (0.92, 0.72, "Ollama generator\ntoken stream", 3),
        "suffix": (0.76, 0.32, "Safety suffix +\nnormalize output", 4),
        "persist": (0.58, 0.32, "SSE events + SQLite\nsession / audit", 5),
        "output": (0.25, 0.32, "Browser output\nanswer + sources", 0),
    }
    edges = [
        ("input", "route", "message"), ("route", "intake", "prepare turn"),
        ("intake", "stop", "reject / clarify"), ("intake", "rag", "advise / knowledge"),
        ("rag", "prompt", "chunks"), ("prompt", "llm", "system + user"),
        ("llm", "suffix", "tokens"), ("suffix", "persist", "final answer"),
        ("persist", "output", "stream + metadata"), ("stop", "output", "fixed response"),
    ]
    draw_flow("01_runtime_input_to_output.png", "Runtime workflow: input → output", nodes, edges, runtime_sources)

    rag_sources = [ROOT / "src/acne_llm/chat/_retrieval.py", ROOT / "src/acne_llm/rag/retriever.py",
                   ROOT / "src/acne_llm/rag/sparse.py", ROOT / "src/acne_llm/rag/vectorstore.py",
                   ROOT / "src/acne_llm/rag/reranker.py"]
    nodes = {
        "query": (0.08, 0.65, "Query + profile +\nsafety terms", 0),
        "dense": (0.27, 0.80, "Dense retrieve\nChroma", 1),
        "sparse": (0.27, 0.50, "Sparse retrieve\nBM25", 2),
        "guide": (0.45, 0.32, "Guideline / safety\nextra pass", 4),
        "fusion": (0.47, 0.67, "RRF fusion +\ndeduplicate", 3),
        "rerank": (0.66, 0.67, "BGE reranker +\nsource caps", 3),
        "slot": (0.83, 0.67, "Ensure guideline slot\nquality evidence", 1),
        "context": (0.92, 0.38, "Retrieved context\nfor prompt", 0),
    }
    edges = [("query", "dense", "semantic"), ("query", "sparse", "lexical"), ("query", "guide", "medical terms"),
             ("dense", "fusion", "ranked IDs"), ("sparse", "fusion", "ranked IDs"), ("guide", "fusion", "guideline"),
             ("fusion", "rerank", "candidates"), ("rerank", "slot", "top-N"), ("slot", "context", "chunks + scores")]
    draw_flow("02_rag_retrieval_pipeline.png", "RAG retrieval workflow", nodes, edges, rag_sources)

    intaker_sources = [ROOT / "research/datagen/intakedata/pipeline.py", ROOT / "research/datagen/intakedata/generator.py",
                       ROOT / "research/datagen/intakedata/gates.py", ROOT / "research/datagen/intakedata/writer.py",
                       ROOT / "research/datagen/intakedata/output/intake/summary.json"]
    nodes = {
        "taxonomy": (0.08, 0.68, "Taxonomy +\ncase quotas", 0),
        "seed": (0.25, 0.68, "Seed / anchor +\neval overlap guard", 1),
        "generate": (0.42, 0.68, "LLM generation +\ngolden relabel", 3),
        "gates": (0.59, 0.68, "Schema + semantic +\ndedupe gates", 4),
        "reject": (0.59, 0.32, "Rejected audit +\nbounded top-up", 4),
        "records": (0.76, 0.68, "4,000 canonical\nrecords", 1),
        "split": (0.91, 0.68, "3,600 train\n400 validation", 0),
    }
    edges = [("taxonomy", "seed", "targets"), ("seed", "generate", "grounded cases"), ("generate", "gates", "candidate"),
             ("gates", "reject", "fail"), ("reject", "generate", "retry"), ("gates", "records", "accept"), ("records", "split", "90/10")]
    draw_flow("03_intaker_data_pipeline.png", "Intaker fine-tune data workflow", nodes, edges, intaker_sources)

    generator_sources = [ROOT / "research/datagen/roledata/taxonomy.yaml", ROOT / "research/datagen/roledata/pipeline.py",
                         ROOT / "research/datagen/roledata/gates.py", ROOT / "research/datagen/roledata/output/roledata.train.jsonl",
                         ROOT / "research/datagen/roledata/output/generation_summary.json"]
    nodes = {
        "taxonomy": (0.07, 0.68, "Role taxonomy\nR1–R10, B1–B5, K1", 0),
        "context": (0.23, 0.68, "KB-backed synthetic\ncontext + anchors", 1),
        "generate": (0.40, 0.68, "gpt-4o-mini\nrole response generation", 3),
        "gates": (0.57, 0.68, "Schema + role + safety +\nphrase-frequency gates", 4),
        "reject": (0.57, 0.31, "Append-only rejected audit\nretry up to 4 attempts", 4),
        "records": (0.74, 0.68, "3,465 accepted / 3,500\nstatus: incomplete", 2),
        "split": (0.89, 0.76, "2,945 train\n277 val · 243 holdout", 0),
        "model": (0.89, 0.36, "ShareGPT export\nGenerator LoRA", 3),
    }
    edges = [("taxonomy", "context", "case quotas"), ("context", "generate", "prompt + sources"),
             ("generate", "gates", "candidate"), ("gates", "reject", "fail"), ("reject", "generate", "retry"),
             ("gates", "records", "accept"), ("records", "split", "85/8/7"), ("split", "model", "train export")]
    draw_flow("04_generator_data_pipeline.png", "Generator fine-tune data workflow", nodes, edges, generator_sources)

    eval_sources = [ROOT / "research/evaluation/full_evaluation.py", ROOT / "research/evaluation/runners/run_intake.py",
                    ROOT / "research/evaluation/runners/run_retrieval.py", ROOT / "research/evaluation/runners/run_ablation.py",
                    ROOT / "research/evaluation/reports/run_full_v3_2/ablation/results.json"]
    nodes = {
        "dataset": (0.07, 0.70, "Frozen v3.2\n145 questions", 0),
        "pre": (0.22, 0.70, "Preflight +\nlineage gates", 1),
        "intake": (0.39, 0.82, "Intaker eval\n1,490 rows", 1),
        "retrieval": (0.39, 0.56, "Retrieval eval\n120 rows", 2),
        "arms": (0.58, 0.70, "6 paired arms\n870 executions", 3),
        "judge": (0.75, 0.70, "DeepSeek judge +\ndeterministic safety", 4),
        "paired": (0.89, 0.82, "Paired deltas +\nbootstrap CI", 5),
        "artifacts": (0.89, 0.49, "JSON / JSONL +\nsummary", 0),
    }
    edges = [("dataset", "pre", "manifest"), ("pre", "intake", "intake set"), ("pre", "retrieval", "answer-quality subset"),
             ("intake", "arms", "real/oracle intake"), ("retrieval", "arms", "real/oracle/no RAG"),
             ("arms", "judge", "answers + contexts"), ("judge", "paired", "scorecards"), ("judge", "artifacts", "all rows")]
    draw_flow("05_evaluation_workflow.png", "Evaluation workflow: run_full_v3_2", nodes, edges, eval_sources)

    docker_sources = [ROOT / "docker-compose.yml", ROOT / "docker-compose.gpu.yml", ROOT / "docker/nginx/default.conf.template"]
    nodes = {
        "browser": (0.08, 0.68, "Browser / LAN\n:3000", 0),
        "gateway": (0.28, 0.68, "Nginx gateway\npublic port only", 1),
        "frontend": (0.48, 0.82, "Next.js frontend\ninternal :3000", 0),
        "backend": (0.48, 0.52, "FastAPI backend\ninternal :8000", 2),
        "ollama": (0.69, 0.52, "Ollama\n7B generator + 3B intaker", 3),
        "data": (0.88, 0.72, "Bind-mounted data\nChroma + BM25 + SQLite", 1),
        "models": (0.88, 0.34, "Read-only GGUF +\nOllama volume", 4),
    }
    edges = [("browser", "gateway", "HTTP/SSE"), ("gateway", "frontend", "/"), ("gateway", "backend", "/api"),
             ("backend", "ollama", "generate"), ("backend", "data", "retrieve/persist"), ("ollama", "models", "load")]
    draw_flow("06_docker_deployment.png", "Docker Compose deployment", nodes, edges, docker_sources)


def _code_files(root: Path, excluded: set[str] | None = None):
    excluded = excluded or set()
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        yield path


def _safe_text_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return 0


def generate_repository() -> dict:
    source_root = ROOT / "src/acne_llm"
    package_files: Counter = Counter()
    package_loc: Counter = Counter()
    for path in source_root.rglob("*.py"):
        package = path.relative_to(source_root).parts[0] if len(path.relative_to(source_root).parts) > 1 else "root"
        package_files[package] += 1
        package_loc[package] += _safe_text_lines(path)
    bar_chart("repository", "01_backend_files_by_package.png", "Backend Python files theo package", package_files,
              list(source_root.rglob("*.py")), top_n=30)
    bar_chart("repository", "02_backend_loc_by_package.png", "Backend Python LOC theo package", package_loc,
              list(source_root.rglob("*.py")), top_n=30, xlabel="Dòng mã")

    excluded = {".git", ".venv", "node_modules", ".next", "__pycache__", ".pytest_cache", ".ruff_cache", "visualization"}
    extensions: Counter = Counter()
    top_dirs_files: Counter = Counter()
    top_dirs_bytes: Counter = Counter()
    for path in _code_files(ROOT, excluded):
        relative = path.relative_to(ROOT)
        top = relative.parts[0] if len(relative.parts) > 1 else "root"
        top_dirs_files[top] += 1
        top_dirs_bytes[top] += path.stat().st_size
        suffix = path.suffix.lower() or "[no extension]"
        if suffix in {".py", ".ts", ".tsx", ".js", ".json", ".jsonl", ".md", ".yaml", ".yml", ".j2", ".html", ".css", ".ps1", ".sh"}:
            extensions[suffix] += 1
    bar_chart("repository", "03_file_types.png", "Repository: file types chính", extensions, [ROOT / "pyproject.toml", ROOT / "frontend/package.json"], top_n=25)
    bar_chart("repository", "04_files_by_top_directory.png", "Repository: số file theo thư mục cấp một", top_dirs_files,
              [ROOT / "pyproject.toml", ROOT / "frontend/package.json"], top_n=25)
    bar_chart("repository", "05_source_artifact_size.png", "Repository: dung lượng source/artifact theo thư mục",
              {key: value / (1024 * 1024) for key, value in top_dirs_bytes.items()},
              [ROOT / "pyproject.toml", ROOT / "frontend/package.json"], top_n=20, xlabel="MiB", value_fmt=".1f")

    model_files = sorted(
        [path for path in (ROOT / "model").rglob("*") if path.is_file() and path.stat().st_size > 1024 * 1024],
        key=lambda path: path.stat().st_size,
        reverse=True,
    )[:10]
    model_sizes = {rel(path): path.stat().st_size / (1024**3) for path in model_files}
    if model_sizes:
        bar_chart("repository", "06_model_artifact_sizes.png", "Model artifacts lớn", model_sizes, model_files,
                  top_n=10, xlabel="GiB", color=COLORS[3], value_fmt=".2f")
    test_counts: Counter = Counter()
    for path in (ROOT / "tests").glob("test_*.py"):
        stem = path.stem.removeprefix("test_")
        domain = stem.split("_")[0]
        test_counts[domain] += sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
                                   if re.match(r"\s*(async\s+)?def\s+test_", line))
    bar_chart("repository", "07_tests_by_domain.png", "Test functions theo domain tên file", test_counts,
              list((ROOT / "tests").glob("test_*.py")), top_n=25, xlabel="Số test functions", color=COLORS[1])

    return {"backend_python_files": sum(package_files.values()), "backend_python_loc": sum(package_loc.values())}


def register_architecture_figures() -> None:
    """Register diagrams.net-rendered architecture pages in the shared catalog."""
    build_script = OUT / "architecture" / "build_drawio.py"
    drawio_file = OUT / "architecture" / "AcneLLM_Architecture.drawio"
    pages = [
        (
            "01_system_context.png",
            "System context & runtime boundaries",
            [ROOT / "docker-compose.yml", ROOT / "frontend/src/hooks/useSSE.ts", ROOT / "src/acne_llm/api/app.py", ROOT / "src/acne_llm/di.py"],
        ),
        (
            "02_chat_sse_workflow.png",
            "Online chat request: input to streamed output",
            [ROOT / "frontend/src/hooks/useSSE.ts", ROOT / "src/acne_llm/api/routes/chat.py", ROOT / "src/acne_llm/chat/runtime.py", ROOT / "src/acne_llm/chat/orchestrator.py"],
        ),
        (
            "03_intake_safety_routing.png",
            "Intake, hard safety and router-first control flow",
            [ROOT / "src/acne_llm/chat/intake.py", ROOT / "src/acne_llm/chat/preprocess.py", ROOT / "src/acne_llm/chat/unified_intake.py", ROOT / "src/acne_llm/guardrails/runner.py", ROOT / "src/acne_llm/di.py"],
        ),
        (
            "04_rag_kb_lifecycle.png",
            "Knowledge base lifecycle & hybrid retrieval",
            [ROOT / "scripts/crawl_all.py", ROOT / "scripts/build_kb.py", ROOT / "src/acne_llm/chat/_retrieval.py", ROOT / "data/raw/chunks.jsonl"],
        ),
        (
            "05_finetune_data_factory.png",
            "Finetune data factory: Intaker vs Generator",
            [ROOT / "research/datagen/intakedata/pipeline.py", ROOT / "research/datagen/roledata/pipeline.py", ROOT / "research/datagen/roledata/output/generation_summary.json", ROOT / "data/raw/chunks.jsonl"],
        ),
        (
            "06_evaluation_ablation.png",
            "Evaluation harness, judge scoring and paired ablation",
            [ROOT / "research/evaluation/full_evaluation.py", ROOT / "research/evaluation/runners/run_intake.py", ROOT / "research/evaluation/runners/run_retrieval.py", ROOT / "research/evaluation/runners/run_ablation.py", ROOT / "research/evaluation/reports/run_full_v3_2/summary.json"],
        ),
        (
            "07_docker_deployment.png",
            "Docker Compose deployment and startup order",
            [ROOT / "docker-compose.yml", ROOT / "docker-compose.gpu.yml", ROOT / "Dockerfile", ROOT / "frontend/Dockerfile", ROOT / "docker/nginx/default.conf.template"],
        ),
    ]
    for filename, title, sources in pages:
        target = OUT / "architecture" / filename
        if not target.exists():
            raise FileNotFoundError(
                f"Missing diagrams.net architecture render: {rel(target)}. "
                f"Open {rel(drawio_file)} in app.diagrams.net and export the page."
            )
        manifest["figures"].append(
            {
                "section": "architecture",
                "path": rel(target),
                "title": title,
                "sources": register_sources([*sources, build_script, drawio_file]),
                "rendered_with": "https://app.diagrams.net/",
            }
        )


def generate_overview(stats: dict) -> None:
    labels = ["KB chunks", "KB documents", "Intaker records", "Generator rows", "Eval questions", "Ablation executions"]
    values = [stats["kb"]["chunk_count"], stats["kb"]["document_count"], stats["intaker"]["records"],
              stats["generator"]["rows"], stats["evaluation"]["dataset_rows"], stats["evaluation"]["ablation_rows"]]
    fig, ax = plt.subplots(figsize=(12, 6.5))
    bars = ax.bar(labels, values, color=[COLORS[i % len(COLORS)] for i in range(len(values))])
    ax.set_yscale("log")
    ax.set_ylabel("Số bản ghi (log scale)")
    ax.set_title("AcneLLM: quy mô các artifact chính", loc="left")
    ax.grid(axis="y", color=GRID, alpha=0.8)
    ax.tick_params(axis="x", rotation=18)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value * 1.07, f"{value:,}", ha="center", va="bottom", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    sources = [ROOT / "data/raw/chunks.jsonl", ROOT / "data/raw/documents.jsonl",
               ROOT / "research/datagen/intakedata/output/intake/intake.records.jsonl",
               ROOT / "research/datagen/roledata/output/roledata.train.jsonl",
               ROOT / "research/evaluation/datasets/active/generator_eval.v3_2_145.jsonl",
               ROOT / "research/evaluation/reports/run_full_v3_2/ablation/results.json"]
    save_figure(fig, "_overview", "01_artifact_scale.png", "Quy mô các artifact chính", sources)


def write_gallery(stats: dict) -> None:
    manifest["stats"] = stats
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_section: dict[str, list[dict]] = defaultdict(list)
    for figure in manifest["figures"]:
        by_section[figure["section"]].append(figure)
    cards = []
    for section in SECTIONS:
        figures = by_section.get(section, [])
        if not figures:
            continue
        cards.append(f"<section><h2>{html.escape(section)}</h2><div class='grid'>")
        for figure in figures:
            image_path = Path(figure["path"]).relative_to("visualization").as_posix()
            cards.append(
                "<figure><a href='{}'><img loading='lazy' src='{}' alt='{}'></a><figcaption>{}</figcaption></figure>".format(
                    html.escape(image_path), html.escape(image_path), html.escape(figure["title"]), html.escape(figure["title"])
                )
            )
        cards.append("</div></section>")
    document = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AcneLLM Visualization Catalog</title>
<style>
:root{font-family:Inter,Segoe UI,Arial,sans-serif;color:#172033;background:#eef2f7}body{margin:0}header{padding:32px 4vw;background:#172033;color:white}header h1{margin:0 0 8px}header p{margin:0;color:#cbd5e1}main{padding:24px 4vw 48px}h2{margin-top:32px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}figure{margin:0;background:white;border:1px solid #d8e0ea;border-radius:12px;overflow:hidden}img{display:block;width:100%;height:260px;object-fit:contain;background:white}figcaption{padding:12px 14px;border-top:1px solid #e2e8f0;font-weight:600}a:focus{outline:3px solid #2563eb;outline-offset:2px}
</style></head><body><header><h1>AcneLLM Visualization Catalog</h1><p>Fresh compute từ dữ liệu và source code hiện tại · xem manifest.json để kiểm tra provenance/hash.</p></header><main>""" + "".join(cards) + "</main></body></html>\n"
    (OUT / "index.html").write_text(document, encoding="utf-8")


def remove_previous_generated_figures() -> None:
    """Remove only PNGs recorded by the previous generator manifest."""
    previous_manifest = OUT / "manifest.json"
    if not previous_manifest.exists():
        return
    try:
        previous = load_json(previous_manifest)
    except (OSError, json.JSONDecodeError):
        return
    out_root = OUT.resolve()
    for item in previous.get("figures") or []:
        if item.get("section") == "architecture":
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            continue
        candidate = (ROOT / raw_path).resolve()
        if candidate.suffix.lower() == ".png" and candidate.is_relative_to(out_root) and candidate.exists():
            candidate.unlink()


def main() -> None:
    remove_previous_generated_figures()
    for section in SECTIONS:
        (OUT / section).mkdir(parents=True, exist_ok=True)
    kb = generate_kb()
    intaker = generate_intaker()
    generator = generate_generator()
    evaluation = generate_evaluation(kb)
    register_architecture_figures()
    repository = generate_repository()
    stats = {"kb": {k: v for k, v in kb.items() if k not in {"id_to_source", "sources"}},
             "intaker": {k: v for k, v in intaker.items() if k != "intents"},
             "generator": generator, "evaluation": evaluation, "repository": repository}
    generate_overview({"kb": kb, "intaker": intaker, "generator": generator, "evaluation": evaluation})
    write_gallery(stats)
    print(f"Generated {len(manifest['figures'])} figures in {OUT}")


if __name__ == "__main__":
    main()
