"""Shared helpers for repository-wide evaluation figures.

The figure generators intentionally do all expensive work in Python and write
small, deterministic artifacts for the dashboard to render.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar
from uuid import uuid4

MAX_JSON_BYTES = 1_050_000
ARTIFACT_POLICY = "fresh_compute_no_figure_reuse"
_GROUP_NAME = re.compile(r"^[a-z0-9_-]+$")
_T = TypeVar("_T")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_generation_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{uuid4().hex[:10]}"


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError(
            f"{path.name} exceeds the artifact limit "
            f"({len(encoded):,} > {MAX_JSON_BYTES:,} bytes)"
        )
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _remove_path(path: Path, expected_parent: Path) -> None:
    resolved = path.resolve()
    parent = expected_parent.resolve()
    if resolved.parent != parent or resolved == parent:
        raise ValueError(f"Refusing to remove unsafe artifact path: {resolved}")
    if resolved.is_dir():
        shutil.rmtree(resolved)
    elif resolved.exists():
        resolved.unlink()


def _publish_group_set(
    staging_root: Path,
    output_root: Path,
    groups: tuple[str, ...],
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root = output_root.resolve()
    staging_root = staging_root.resolve()
    backups: dict[str, Path] = {}
    published: list[str] = []
    token = uuid4().hex

    for group in groups:
        if not _GROUP_NAME.fullmatch(group):
            raise ValueError(f"Invalid figure group name: {group}")
        staged = staging_root / group
        if not staged.is_dir() or not (staged / "manifest.json").is_file():
            raise ValueError(f"Fresh generator did not produce {group}/manifest.json")

    try:
        for group in groups:
            final = output_root / group
            staged = staging_root / group
            backup = output_root / f".{group}.backup-{token}"
            if final.exists():
                os.replace(final, backup)
                backups[group] = backup
            os.replace(staged, final)
            published.append(group)
    except Exception:
        for group in reversed(published):
            final = output_root / group
            if final.exists():
                _remove_path(final, output_root)
        for group, backup in backups.items():
            if backup.exists():
                os.replace(backup, output_root / group)
        raise
    else:
        for backup in backups.values():
            if backup.exists():
                _remove_path(backup, output_root)


def fresh_figure_generation(
    groups: tuple[str, ...],
) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Generate into an empty staging root, then replace complete group folders.

    Existing figure JSON/PNG/PDF files are never visible to the wrapped
    generator and stale files disappear when a group is published.
    """

    if not groups or len(set(groups)) != len(groups):
        raise ValueError("Figure generation groups must be unique and non-empty.")

    def decorate(function: Callable[..., _T]) -> Callable[..., _T]:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> _T:
            root = Path(
                kwargs.get("root")
                or Path(__file__).resolve().parents[2]
            ).resolve()
            output_root = Path(
                kwargs.get("output_root")
                or root / "evaluation" / "reports" / "figures"
            ).resolve()
            output_root.parent.mkdir(parents=True, exist_ok=True)
            generation_id = str(
                kwargs.get("generation_id") or new_generation_id()
            )
            generated_at = str(kwargs.get("generated_at") or utcnow())
            staging_root = Path(
                tempfile.mkdtemp(
                    prefix=f".{output_root.name}.build-",
                    dir=output_root.parent,
                )
            )
            call_kwargs = {
                **kwargs,
                "root": root,
                "output_root": staging_root,
                "generation_id": generation_id,
                "generated_at": generated_at,
            }
            try:
                result = function(*args, **call_kwargs)
                _publish_group_set(staging_root, output_root, groups)
            finally:
                if staging_root.exists():
                    _remove_path(staging_root, staging_root.parent)

            if isinstance(result, dict):
                return {
                    group: output_root / group / "manifest.json"
                    for group in groups
                }  # type: ignore[return-value]
            if len(groups) == 1 and isinstance(result, Path):
                return output_root / groups[0] / "manifest.json"  # type: ignore[return-value]
            return result

        return wrapped

    return decorate


class FreshSnapshot:
    """Build a complete figures tree in isolation and publish it as one snapshot."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()
        self.output_root.parent.mkdir(parents=True, exist_ok=True)
        self.staging_root = Path(
            tempfile.mkdtemp(
                prefix=f".{self.output_root.name}.snapshot-",
                dir=self.output_root.parent,
            )
        )

    def __enter__(self) -> Path:
        return self.staging_root

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if exc_type is not None:
            if self.staging_root.exists():
                _remove_path(self.staging_root, self.staging_root.parent)
            return False

        parent = self.output_root.parent
        backup = parent / f".{self.output_root.name}.backup-{uuid4().hex}"
        try:
            if self.output_root.exists():
                os.replace(self.output_root, backup)
            os.replace(self.staging_root, self.output_root)
        except Exception:
            if self.output_root.exists():
                _remove_path(self.output_root, parent)
            if backup.exists():
                os.replace(backup, self.output_root)
            raise
        else:
            if backup.exists():
                _remove_path(backup, parent)
        finally:
            if self.staging_root.exists():
                _remove_path(self.staging_root, self.staging_root.parent)
        return False


def histogram(values: list[float], bins: int = 24) -> list[dict[str, Any]]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return []
    low, high = min(finite), max(finite)
    if low == high:
        return [{"bin": f"{low:g}", "bin_start": low, "bin_end": high, "count": len(finite)}]
    width = (high - low) / max(1, bins)
    counts = [0] * bins
    for value in finite:
        index = min(bins - 1, int((value - low) / width))
        counts[index] += 1
    rows: list[dict[str, Any]] = []
    for index, count in enumerate(counts):
        start = low + index * width
        end = high if index == bins - 1 else start + width
        rows.append(
            {
                "bin": f"{start:.1f}–{end:.1f}",
                "bin_start": round(start, 6),
                "bin_end": round(end, 6),
                "count": count,
            }
        )
    return rows


def configure_matplotlib() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.unicode_minus": False,
            "figure.dpi": 100,
            "savefig.dpi": 150,
        }
    )
    return plt


def save_matplotlib(
    fig: Any,
    png_path: Path,
    *,
    pdf: bool,
) -> str | None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    pdf_file: str | None = None
    if pdf:
        pdf_path = png_path.with_suffix(".pdf")
        fig.savefig(pdf_path, bbox_inches="tight")
        pdf_file = pdf_path.name
    configure_matplotlib().close(fig)
    return pdf_file


def chart_to_pdf(payload: dict[str, Any], pdf_path: Path) -> None:
    """Render a compact vector fallback for JSON chart artifacts."""
    plt = configure_matplotlib()
    chart_type = str(payload.get("chart_type") or "bar")
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    title = str(payload.get("title") or "")
    if title:
        ax.set_title(title)

    if chart_type == "heatmap":
        rows = [str(value) for value in payload.get("rows") or []]
        columns = [str(value) for value in payload.get("columns") or []]
        cells = payload.get("cells") or []
        lookup = {
            (str(cell.get("row")), str(cell.get("column"))): float(cell.get("value") or 0)
            for cell in cells
            if isinstance(cell, dict)
        }
        matrix = [[lookup.get((row, column), 0.0) for column in columns] for row in rows]
        image = ax.imshow(matrix, aspect="auto", cmap="viridis")
        ax.set_xticks(range(len(columns)), columns, rotation=45, ha="right")
        ax.set_yticks(range(len(rows)), rows)
        fig.colorbar(image, ax=ax, fraction=0.03, pad=0.03)
    else:
        data = [row for row in payload.get("data") or [] if isinstance(row, dict)]
        x_key = str(payload.get("x_key") or "label")
        series = [item for item in payload.get("series") or [] if isinstance(item, dict)]
        if chart_type == "scatter":
            x_data_key = str(payload.get("x_data_key") or "x")
            y_data_key = str(payload.get("y_data_key") or "y")
            group_key = str(payload.get("group_key") or "")
            groups: dict[str, list[dict[str, Any]]] = {}
            for row in data:
                group = str(row.get(group_key) or "data") if group_key else "data"
                groups.setdefault(group, []).append(row)
            for group, points in list(groups.items())[:12]:
                ax.scatter(
                    [float(point.get(x_data_key) or 0) for point in points],
                    [float(point.get(y_data_key) or 0) for point in points],
                    s=[max(8.0, float(point.get("size") or 18)) for point in points],
                    alpha=0.65,
                    label=group,
                )
            if len(groups) > 1:
                ax.legend(fontsize=7, loc="best")
        elif chart_type == "line":
            xs = [row.get(x_key) for row in data]
            for item in series:
                key = str(item.get("key"))
                ax.plot(xs, [float(row.get(key) or 0) for row in data], marker="o", label=item.get("label") or key)
            if len(series) > 1:
                ax.legend(fontsize=8)
        else:
            labels = [str(row.get(x_key) or "") for row in data]
            positions = list(range(len(labels)))
            stacked = any(item.get("stack") for item in series)
            width = 0.8 if stacked else 0.8 / max(1, len(series))
            bottom = [0.0] * len(data)
            for index, item in enumerate(series):
                key = str(item.get("key"))
                values = [float(row.get(key) or 0) for row in data]
                xs = positions if stacked else [
                    value - 0.4 + width / 2 + index * width for value in positions
                ]
                kwargs: dict[str, Any] = {}
                error_key = item.get("error_key")
                if error_key:
                    raw_errors = [row.get(str(error_key)) for row in data]
                    if all(isinstance(error, list) and len(error) == 2 for error in raw_errors):
                        kwargs["yerr"] = [
                            [float(error[0]) for error in raw_errors],
                            [float(error[1]) for error in raw_errors],
                        ]
                        kwargs["capsize"] = 2
                ax.bar(
                    xs,
                    values,
                    width=width,
                    bottom=bottom if stacked else None,
                    label=item.get("label") or key,
                    **kwargs,
                )
                if stacked:
                    bottom = [current + value for current, value in zip(bottom, values)]
            ax.set_xticks(positions, labels, rotation=45, ha="right")
            if len(series) > 1:
                ax.legend(fontsize=8)

    ax.set_xlabel(str(payload.get("x_label") or ""))
    ax.set_ylabel(str(payload.get("y_label") or ""))
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)


@dataclass
class ManifestBuilder:
    group: str
    output_dir: Path
    pdf: bool = False
    generated_at: str = field(default_factory=utcnow)
    generation_id: str = field(default_factory=new_generation_id)
    generator: str = ""
    figures: list[dict[str, Any]] = field(default_factory=list)

    def add_chart(
        self,
        *,
        figure_id: str,
        title: str,
        chart_type: str,
        payload: dict[str, Any],
        caption: str,
        source_data: str,
    ) -> None:
        file_name = f"{figure_id}.json"
        payload = {
            "id": figure_id,
            "title": title,
            "chart_type": chart_type,
            **payload,
        }
        write_json(self.output_dir / file_name, payload)
        pdf_file = None
        if self.pdf:
            pdf_file = f"{figure_id}.pdf"
            chart_to_pdf(payload, self.output_dir / pdf_file)
        self.figures.append(
            {
                "id": figure_id,
                "title": title,
                "kind": "chart",
                "file": file_name,
                "pdf_file": pdf_file,
                "chart_type": chart_type,
                "caption": caption,
                "source_data": source_data,
                "status": "ok",
                "skip_reason": None,
            }
        )

    def add_png(
        self,
        *,
        figure_id: str,
        title: str,
        fig: Any,
        caption: str,
        source_data: str,
        chart_type: str = "scatter",
    ) -> None:
        file_name = f"{figure_id}.png"
        pdf_file = save_matplotlib(
            fig,
            self.output_dir / file_name,
            pdf=self.pdf,
        )
        self.figures.append(
            {
                "id": figure_id,
                "title": title,
                "kind": "png",
                "file": file_name,
                "pdf_file": pdf_file,
                "chart_type": chart_type,
                "caption": caption,
                "source_data": source_data,
                "status": "ok",
                "skip_reason": None,
            }
        )

    def skip(
        self,
        *,
        figure_id: str,
        title: str,
        reason: str,
        caption: str,
        source_data: str,
        chart_type: str,
        kind: str = "chart",
    ) -> None:
        self.figures.append(
            {
                "id": figure_id,
                "title": title,
                "kind": kind,
                "file": None,
                "pdf_file": None,
                "chart_type": chart_type,
                "caption": caption,
                "source_data": source_data,
                "status": "skipped",
                "skip_reason": reason,
            }
        )

    def finish(self) -> Path:
        manifest = {
            "generated_at": self.generated_at,
            "generation_id": self.generation_id,
            "generator": self.generator,
            "artifact_policy": ARTIFACT_POLICY,
            "group": self.group,
            "figures": self.figures,
        }
        path = self.output_dir / "manifest.json"
        write_json(path, manifest)
        return path
