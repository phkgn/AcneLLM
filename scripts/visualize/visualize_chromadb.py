"""Visualize the AcneLLM ChromaDB knowledge base.

Loads the persisted Chroma collection (embeddings + metadata + documents),
projects the high-dimensional embeddings down to 2D, and writes an interactive
HTML scatter plot where each point is a chunk — hover to see title / source /
text snippet, colour by any metadata field (source, trust, lang, source_type).
Also prints a quick summary of the collection.

Dependency-graceful:
  - dim reduction: tries UMAP -> t-SNE (sklearn) -> PCA (numpy, always works)
  - plotting:      tries Plotly (interactive HTML) -> matplotlib (static PNG)

Usage (from repo root, inside the venv):
    python scripts/visualize/visualize_chromadb.py
    python scripts/visualize/visualize_chromadb.py --color trust --method umap
    python scripts/visualize/visualize_chromadb.py --limit 3000 --method tsne
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO / "data" / "chroma_db"
OUT_DIR = Path(__file__).resolve().parent / "output"


# --------------------------------------------------------------------------- #
# load
# --------------------------------------------------------------------------- #
def load_collection(persist_dir: Path, collection: str, limit: int | None):
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(persist_dir), settings=Settings(anonymized_telemetry=False)
    )
    col = client.get_collection(collection)
    total = col.count()
    got = col.get(
        include=["embeddings", "metadatas", "documents"],
        limit=limit or total,
    )
    embs = np.asarray(got["embeddings"], dtype=float)
    metas = got["metadatas"] or []
    docs = got["documents"] or []
    return embs, metas, docs, total


# --------------------------------------------------------------------------- #
# dimensionality reduction (graceful fallback)
# --------------------------------------------------------------------------- #
def reduce_2d(embs: np.ndarray, method: str) -> tuple[np.ndarray, str]:
    order = {"umap": ["umap", "tsne", "pca"],
             "tsne": ["tsne", "pca"],
             "pca": ["pca"]}.get(method, ["umap", "tsne", "pca"])
    for m in order:
        try:
            if m == "umap":
                import umap  # type: ignore
                xy = umap.UMAP(n_components=2, metric="cosine",
                               random_state=42).fit_transform(embs)
                return np.asarray(xy), "UMAP"
            if m == "tsne":
                from sklearn.manifold import TSNE
                perp = min(30, max(5, len(embs) // 100))
                xy = TSNE(n_components=2, metric="cosine", init="pca",
                          perplexity=perp, random_state=42).fit_transform(embs)
                return np.asarray(xy), "t-SNE"
            if m == "pca":
                return _pca_numpy(embs), "PCA"
        except Exception as e:  # noqa: BLE001
            print(f"  [{m}] unavailable ({e.__class__.__name__}), trying next…")
    return _pca_numpy(embs), "PCA"


def _pca_numpy(embs: np.ndarray) -> np.ndarray:
    x = embs - embs.mean(axis=0, keepdims=True)
    # SVD-based PCA — no sklearn needed
    _, _, vt = np.linalg.svd(x, full_matrices=False)
    return x @ vt[:2].T


# --------------------------------------------------------------------------- #
# plotting
# --------------------------------------------------------------------------- #
def _snippet(doc: str, n: int = 140) -> str:
    doc = (doc or "").replace("\n", " ").strip()
    return (doc[:n] + "…") if len(doc) > n else doc


def plot(xy, metas, docs, color_field: str, algo: str, out_html: Path) -> Path:
    colors = [str((m or {}).get(color_field, "unknown")) or "unknown" for m in metas]
    titles = [str((m or {}).get("title", "")) for m in metas]
    sources = [str((m or {}).get("source", "")) for m in metas]
    try:
        import plotly.graph_objects as go

        cats = sorted(set(colors))
        palette = _palette(len(cats))
        cmap = {c: palette[i] for i, c in enumerate(cats)}
        fig = go.Figure()
        for c in cats:
            idx = [i for i, v in enumerate(colors) if v == c]
            fig.add_trace(go.Scattergl(
                x=xy[idx, 0], y=xy[idx, 1], mode="markers", name=f"{c} ({len(idx)})",
                marker=dict(size=5, color=cmap[c], opacity=0.7,
                            line=dict(width=0)),
                text=[f"<b>{titles[i]}</b><br>source: {sources[i]}"
                      f"<br>{color_field}: {colors[i]}<br>{_snippet(docs[i])}"
                      for i in idx],
                hoverinfo="text",
            ))
        fig.update_layout(
            title=f"AcneLLM ChromaDB — {len(colors)} chunks ({algo}, colour = {color_field})",
            template="plotly_white", legend_title=color_field,
            width=1100, height=750,
            xaxis=dict(showticklabels=False), yaxis=dict(showticklabels=False),
        )
        out_html.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(out_html))
        return out_html
    except Exception as e:  # noqa: BLE001
        print(f"  Plotly unavailable ({e.__class__.__name__}); falling back to PNG")
        return _plot_matplotlib(xy, colors, color_field, algo,
                                out_html.with_suffix(".png"))


def _plot_matplotlib(xy, colors, color_field, algo, out_png: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cats = sorted(set(colors))
    cmap = {c: i for i, c in enumerate(cats)}
    fig, ax = plt.subplots(figsize=(11, 7.5))
    sc = ax.scatter(xy[:, 0], xy[:, 1], c=[cmap[c] for c in colors],
                    cmap="tab20", s=6, alpha=0.7)
    ax.set_title(f"AcneLLM ChromaDB — {len(colors)} chunks ({algo}, colour = {color_field})")
    ax.set_xticks([]); ax.set_yticks([])
    handles = [plt.Line2D([0], [0], marker="o", ls="", markersize=6,
                          color=sc.cmap(sc.norm(cmap[c]))) for c in cats]
    ax.legend(handles, cats, title=color_field, fontsize=8,
              loc="center left", bbox_to_anchor=(1, 0.5))
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=130, bbox_inches="tight")
    return out_png


def _palette(n: int) -> list[str]:
    base = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860",
            "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD", "#E377C2", "#7F7F7F",
            "#2CA02C", "#D62728", "#9467BD", "#1F77B4", "#FF7F0E", "#17BECF"]
    return [base[i % len(base)] for i in range(max(n, 1))]


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def print_summary(embs, metas, total, shown):
    print("\n" + "=" * 60)
    print(f"collection total chunks : {total}")
    print(f"loaded for plot         : {shown}")
    print(f"embedding dimension     : {embs.shape[1] if embs.ndim == 2 else '?'}")
    for field in ("source", "trust", "lang", "source_type"):
        c = Counter(str((m or {}).get(field, "?")) for m in metas)
        if len(c) > 1 or "?" not in c:
            top = ", ".join(f"{k}={v}" for k, v in c.most_common(8))
            print(f"by {field:12}: {top}")
    print("=" * 60)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--collection", default="acne_kb_vi")
    ap.add_argument("--color", default="source",
                    help="metadata field to colour by (source/trust/lang/source_type)")
    ap.add_argument("--method", default="umap", choices=["umap", "tsne", "pca"])
    ap.add_argument("--limit", type=int, default=5000,
                    help="max chunks to load (subsample for speed); 0 = all")
    ap.add_argument("--out", type=Path, default=OUT_DIR / "chromadb_map.html")
    args = ap.parse_args()

    print(f"loading '{args.collection}' from {args.db} …")
    embs, metas, docs, total = load_collection(
        args.db, args.collection, args.limit or None
    )
    if len(embs) == 0:
        print("collection is empty — nothing to visualize.")
        return
    print_summary(embs, metas, total, len(embs))

    print(f"\nreducing {embs.shape} -> 2D via {args.method} …")
    xy, algo = reduce_2d(embs, args.method)

    print(f"plotting (colour = {args.color}) …")
    out = plot(xy, metas, docs, args.color, algo, args.out)
    print(f"\n✓ wrote {out}")
    print("  open it in a browser (interactive) — hover a point for title/source/text.")


if __name__ == "__main__":
    main()
