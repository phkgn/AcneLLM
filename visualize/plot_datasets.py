"""Visualize DocumentRaw and LLMData datasets."""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter, defaultdict
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from typing import Any

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)
plt.rcParams["font.size"] = 10


def load_jsonl(path: str) -> list[dict]:
    """Load JSONL file."""
    docs = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    docs.append(json.loads(line))
    except FileNotFoundError:
        print(f"⚠️  {path} not found (crawl hasn't run yet)")
    return docs


def analyze_documents(docs: list[dict]) -> dict:
    """Extract statistics from DocumentRaw list."""
    if not docs:
        return {}

    languages = Counter(d.get("source", {}).get("language", "unknown") for d in docs)
    trust_levels = Counter(d.get("source", {}).get("trust_level", "unknown") for d in docs)
    sources = Counter(d.get("source", {}).get("source_name", "unknown") for d in docs)

    categories = Counter()
    for d in docs:
        for cat in d.get("categories", []):
            categories[cat] += 1

    tags = Counter()
    for d in docs:
        for tag in d.get("tags", []):
            tags[tag] += 1

    text_lengths = [len(d.get("text", "")) for d in docs]
    quality_scores = [d.get("quality_score", 0.5) for d in docs]

    return {
        "count": len(docs),
        "languages": dict(languages),
        "trust_levels": dict(trust_levels),
        "sources": dict(sources),
        "categories": dict(categories),
        "tags": dict(tags),
        "text_lengths": text_lengths,
        "quality_scores": quality_scores,
    }


def plot_language_distribution(docs_stats: dict, llm_stats: dict, out_dir: Path):
    """Plot VI vs EN distribution."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Documents
    if docs_stats and docs_stats.get("languages"):
        langs = docs_stats["languages"]
        axes[0].bar(langs.keys(), langs.values(), color=["#FF6B6B", "#4ECDC4"])
        axes[0].set_title("DocumentRaw: Language Distribution", fontsize=12, fontweight="bold")
        axes[0].set_ylabel("Count")
        for i, (k, v) in enumerate(langs.items()):
            axes[0].text(i, v + 50, str(v), ha="center", fontweight="bold")

    # LLM Data
    if llm_stats and llm_stats.get("languages"):
        langs = llm_stats["languages"]
        axes[1].bar(langs.keys(), langs.values(), color=["#FF6B6B", "#4ECDC4"])
        axes[1].set_title("LLMData: Language Distribution", fontsize=12, fontweight="bold")
        axes[1].set_ylabel("Count")
        for i, (k, v) in enumerate(langs.items()):
            axes[1].text(i, v + 50, str(v), ha="center", fontweight="bold")

    plt.tight_layout()
    plt.savefig(out_dir / "01_language_distribution.png", dpi=150, bbox_inches="tight")
    print("✓ 01_language_distribution.png")
    plt.close()


def plot_trust_level_distribution(docs_stats: dict, llm_stats: dict, out_dir: Path):
    """Plot trust level distribution."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    colors = {"high": "#2ECC71", "medium": "#F39C12", "low": "#E74C3C"}

    if docs_stats and docs_stats.get("trust_levels"):
        trust = docs_stats["trust_levels"]
        bars = axes[0].bar(trust.keys(), trust.values(),
                          color=[colors.get(k, "#95A5A6") for k in trust.keys()])
        axes[0].set_title("DocumentRaw: Trust Level", fontsize=12, fontweight="bold")
        axes[0].set_ylabel("Count")
        for bar in bars:
            height = bar.get_height()
            axes[0].text(bar.get_x() + bar.get_width()/2., height,
                        f"{int(height)}", ha="center", va="bottom", fontweight="bold")

    if llm_stats and llm_stats.get("trust_levels"):
        trust = llm_stats["trust_levels"]
        bars = axes[1].bar(trust.keys(), trust.values(),
                          color=[colors.get(k, "#95A5A6") for k in trust.keys()])
        axes[1].set_title("LLMData: Trust Level", fontsize=12, fontweight="bold")
        axes[1].set_ylabel("Count")
        for bar in bars:
            height = bar.get_height()
            axes[1].text(bar.get_x() + bar.get_width()/2., height,
                        f"{int(height)}", ha="center", va="bottom", fontweight="bold")

    plt.tight_layout()
    plt.savefig(out_dir / "02_trust_level.png", dpi=150, bbox_inches="tight")
    print("✓ 02_trust_level.png")
    plt.close()


def plot_top_sources(docs_stats: dict, llm_stats: dict, out_dir: Path, top_n: int = 15):
    """Plot top N sources."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    if docs_stats and docs_stats.get("sources"):
        sources = dict(sorted(docs_stats["sources"].items(), key=lambda x: x[1], reverse=True)[:top_n])
        axes[0].barh(list(sources.keys()), list(sources.values()), color="#3498DB")
        axes[0].set_title(f"DocumentRaw: Top {top_n} Sources", fontsize=12, fontweight="bold")
        axes[0].set_xlabel("Document Count")
        axes[0].invert_yaxis()

    if llm_stats and llm_stats.get("sources"):
        sources = dict(sorted(llm_stats["sources"].items(), key=lambda x: x[1], reverse=True)[:top_n])
        axes[1].barh(list(sources.keys()), list(sources.values()), color="#E74C3C")
        axes[1].set_title(f"LLMData: Top {top_n} Sources", fontsize=12, fontweight="bold")
        axes[1].set_xlabel("Record Count")
        axes[1].invert_yaxis()

    plt.tight_layout()
    plt.savefig(out_dir / "03_top_sources.png", dpi=150, bbox_inches="tight")
    print("✓ 03_top_sources.png")
    plt.close()


def plot_text_length_distribution(docs_stats: dict, llm_stats: dict, out_dir: Path):
    """Plot text length histograms."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    if docs_stats and docs_stats.get("text_lengths"):
        lengths = [l / 1000 for l in docs_stats["text_lengths"] if l > 0]  # Convert to KB
        axes[0].hist(lengths, bins=50, color="#9B59B6", alpha=0.7, edgecolor="black")
        axes[0].set_title("DocumentRaw: Text Length Distribution", fontsize=12, fontweight="bold")
        axes[0].set_xlabel("Text Length (KB)")
        axes[0].set_ylabel("Frequency")
        axes[0].axvline(np.mean(lengths), color="red", linestyle="--", linewidth=2, label=f"Mean: {np.mean(lengths):.1f}KB")
        axes[0].legend()

    if llm_stats and llm_stats.get("text_lengths"):
        lengths = [l / 1000 for l in llm_stats["text_lengths"] if l > 0]
        axes[1].hist(lengths, bins=50, color="#1ABC9C", alpha=0.7, edgecolor="black")
        axes[1].set_title("LLMData: Text Length Distribution", fontsize=12, fontweight="bold")
        axes[1].set_xlabel("Text Length (KB)")
        axes[1].set_ylabel("Frequency")
        axes[1].axvline(np.mean(lengths), color="red", linestyle="--", linewidth=2, label=f"Mean: {np.mean(lengths):.1f}KB")
        axes[1].legend()

    plt.tight_layout()
    plt.savefig(out_dir / "04_text_length.png", dpi=150, bbox_inches="tight")
    print("✓ 04_text_length.png")
    plt.close()


def plot_quality_scores(docs_stats: dict, out_dir: Path):
    """Plot quality score distribution (DocumentRaw only)."""
    if not docs_stats or not docs_stats.get("quality_scores"):
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    scores = docs_stats["quality_scores"]
    ax.hist(scores, bins=30, color="#F39C12", alpha=0.7, edgecolor="black")
    ax.set_title("DocumentRaw: Quality Score Distribution", fontsize=12, fontweight="bold")
    ax.set_xlabel("Quality Score")
    ax.set_ylabel("Frequency")
    ax.axvline(np.mean(scores), color="red", linestyle="--", linewidth=2, label=f"Mean: {np.mean(scores):.3f}")
    ax.legend()

    plt.tight_layout()
    plt.savefig(out_dir / "05_quality_scores.png", dpi=150, bbox_inches="tight")
    print("✓ 05_quality_scores.png")
    plt.close()


def plot_categories(docs_stats: dict, llm_stats: dict, out_dir: Path):
    """Plot category distribution."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    if docs_stats and docs_stats.get("categories"):
        cats = dict(sorted(docs_stats["categories"].items(), key=lambda x: x[1], reverse=True))
        axes[0].bar(cats.keys(), cats.values(), color="#3498DB", alpha=0.8)
        axes[0].set_title("DocumentRaw: Category Distribution", fontsize=12, fontweight="bold")
        axes[0].set_ylabel("Count")
        axes[0].tick_params(axis="x", rotation=45)

    if llm_stats and llm_stats.get("categories"):
        cats = dict(sorted(llm_stats["categories"].items(), key=lambda x: x[1], reverse=True))
        axes[1].bar(cats.keys(), cats.values(), color="#E74C3C", alpha=0.8)
        axes[1].set_title("LLMData: Category Distribution", fontsize=12, fontweight="bold")
        axes[1].set_ylabel("Count")
        axes[1].tick_params(axis="x", rotation=45)

    plt.tight_layout()
    plt.savefig(out_dir / "06_categories.png", dpi=150, bbox_inches="tight")
    print("✓ 06_categories.png")
    plt.close()


def generate_summary(docs: list[dict], llm_data: list[dict], out_dir: Path):
    """Generate text summary."""
    docs_stats = analyze_documents(docs)
    llm_stats = analyze_documents(llm_data)

    summary = f"""# Dataset Visualization Summary

## DocumentRaw (RAG Knowledge Base)
- **Total Documents**: {docs_stats.get("count", 0):,}
- **Languages**: {docs_stats.get("languages", {})}
- **Trust Levels**: {docs_stats.get("trust_levels", {})}
- **Avg Text Length**: {np.mean(docs_stats.get("text_lengths", [0])) / 1000:.1f} KB
- **Avg Quality Score**: {np.mean(docs_stats.get("quality_scores", [0.5])):.3f}
- **Top 5 Sources**:
{chr(10).join(f"  - {k}: {v}" for k, v in sorted(docs_stats.get("sources", {}).items(), key=lambda x: x[1], reverse=True)[:5])}

## LLMData (Fine-tuning Dataset)
- **Total Records**: {llm_stats.get("count", 0):,}
- **Languages**: {llm_stats.get("languages", {})}
- **Trust Levels**: {llm_stats.get("trust_levels", {})}
- **Avg Text Length**: {np.mean(llm_stats.get("text_lengths", [0])) / 1000:.1f} KB
- **Top 5 Sources**:
{chr(10).join(f"  - {k}: {v}" for k, v in sorted(llm_stats.get("sources", {}).items(), key=lambda x: x[1], reverse=True)[:5])}

## Data Format Differences
| Aspect | DocumentRaw | LLMData |
|--------|-------------|---------|
| **Purpose** | RAG retrieval & chunking | Fine-tuning LLM |
| **Fields** | url, title, text, html_len, quality_score, source, categories, tags | instruction, input, output, metadata |
| **Key Field** | `text` (extracted HTML content) | `output` (same as text) |
| **Instruction** | None | Generated from title (VI/EN templates) |
| **Use Case** | Semantic search, RAG context | LLM instruction-following training |
"""

    with open(out_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(summary)
    print("✓ README.md")


def main():
    root = Path(__file__).parent.parent
    docs_path = root / "data" / "processed" / "documents.jsonl"
    llm_path = root / "data" / "processed" / "llm_data.jsonl"
    out_dir = Path(__file__).parent

    print(f"📊 Visualizing datasets from {root}")
    print(f"  - DocumentRaw: {docs_path}")
    print(f"  - LLMData: {llm_path}")
    print()

    docs = load_jsonl(str(docs_path))
    llm_data = load_jsonl(str(llm_path))

    docs_stats = analyze_documents(docs)
    llm_stats = analyze_documents(llm_data)

    print(f"📈 Loaded {len(docs)} DocumentRaw, {len(llm_data)} LLMData records\n")

    # Generate plots
    plot_language_distribution(docs_stats, llm_stats, out_dir)
    plot_trust_level_distribution(docs_stats, llm_stats, out_dir)
    plot_top_sources(docs_stats, llm_stats, out_dir)
    plot_text_length_distribution(docs_stats, llm_stats, out_dir)
    plot_quality_scores(docs_stats, out_dir)
    plot_categories(docs_stats, llm_stats, out_dir)

    # Summary
    generate_summary(docs, llm_data, out_dir)

    print(f"\n✅ Visualization saved to {out_dir}")


if __name__ == "__main__":
    main()
