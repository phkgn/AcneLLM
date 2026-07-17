"""Generate anonymized production-usage (D) figure artifacts."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acne_llm.guardrails.ood_detector import mask_pii
from evaluation.analysis.figures_common import (
    ManifestBuilder,
    fresh_figure_generation,
    histogram,
    iter_jsonl,
)

STOPWORDS = {
    "và", "là", "có", "không", "cho", "của", "mình", "tôi", "em", "bạn",
    "bị", "mụn", "da", "thì", "nên", "dùng", "được", "với", "trong", "như",
    "một", "những", "các", "này", "đó", "ở", "làm", "sao", "gì", "cách",
    "nào", "cần", "phải", "để", "khi", "về", "ra", "rất", "hơn", "hay",
    "ạ", "ơi", "theo", "trên", "dưới", "đang", "đã", "sẽ", "còn", "thế",
}
MASK_TOKENS = {
    "id_masked",
    "phone_masked",
    "email_masked",
    "address_masked",
    "account_masked",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_session_turns(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    connection = _connect_readonly(path)
    try:
        if "turns" not in _tables(connection):
            return []
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(turns)")
        }
        metadata_expr = "metadata" if "metadata" in columns else "'{}'"
        query = (
            "SELECT session_id, role, content, timestamp, mode, "
            f"{metadata_expr} FROM turns ORDER BY timestamp"
        )
        return [
            {
                "session_id": str(session_id or ""),
                "role": str(role or ""),
                "content": str(content or ""),
                "timestamp": float(timestamp or 0),
                "mode": str(mode or ""),
                "metadata": _json_dict(metadata),
            }
            for session_id, role, content, timestamp, mode, metadata
            in connection.execute(query)
        ]
    finally:
        connection.close()


def _load_audit_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    connection = _connect_readonly(path)
    try:
        if "audit_log" not in _tables(connection):
            return []
        return [
            {
                "session_id": str(session_id or ""),
                "content": str(user_message or ""),
                "timestamp": float(timestamp or 0),
                "scope_decision": str(scope_decision or ""),
            }
            for timestamp, session_id, user_message, scope_decision
            in connection.execute(
                "SELECT timestamp, session_id, user_message, scope_decision "
                "FROM audit_log ORDER BY timestamp"
            )
        ]
    finally:
        connection.close()


def _eval_intent_counts(root: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in (root / "evaluation" / "datasets" / "v1").glob("t1_*.jsonl"):
        for row in iter_jsonl(path):
            label = row.get("intent_label")
            if label:
                counts[str(label)] += 1
    return counts


def _d1_route_distribution(
    builder: ManifestBuilder,
    root: Path,
    turns: list[dict[str, Any]],
    audit: list[dict[str, Any]],
) -> None:
    production: Counter[str] = Counter()
    for row in turns:
        if row["role"] != "user":
            continue
        metadata = row["metadata"]
        route = metadata.get("primary_intent") or metadata.get("turn_type")
        if route:
            production[str(route)] += 1
    if not production:
        production.update(
            str(row["scope_decision"] or "unknown")
            for row in audit
        )
    if not production:
        raise ValueError("No production route or scope records found.")
    evaluation = _eval_intent_counts(root)
    labels = sorted(set(production) | set(evaluation))
    production_total = sum(production.values())
    evaluation_total = sum(evaluation.values())
    data = [
        {
            "route": label,
            "production_count": production[label],
            "evaluation_count": evaluation[label],
            "production_pct": round(production[label] / production_total, 6),
            "evaluation_pct": round(
                evaluation[label] / evaluation_total, 6
            ) if evaluation_total else 0,
        }
        for label in labels
    ]
    builder.add_chart(
        figure_id="d1_route_distribution",
        title="Production route vs eval composition",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "route",
            "x_label": "Intent / route",
            "y_label": "Share",
            "domain": [0, 1],
            "series": [
                {"key": "production_pct", "label": "Production"},
                {"key": "evaluation_pct", "label": "Eval dataset"},
            ],
        },
        caption="Production route share compared with labeled T1 intent composition.",
        source_data="data/sessions.db + data/audit.db + evaluation/datasets/v1/t1_*.jsonl",
    )


def _week(timestamp: float) -> str:
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _d2_weekly_rates(
    builder: ManifestBuilder,
    turns: list[dict[str, Any]],
    audit: list[dict[str, Any]],
) -> None:
    weekly: dict[str, Counter[str]] = defaultdict(Counter)
    for row in turns:
        if row["role"] != "user" or row["timestamp"] <= 0:
            continue
        metadata = row["metadata"]
        intent = str(
            metadata.get("primary_intent")
            or metadata.get("turn_type")
            or ""
        )
        counter = weekly[_week(row["timestamp"])]
        counter["total"] += 1
        if intent == "clarify":
            counter["clarify"] += 1
        if intent == "reject":
            counter["refusal"] += 1
    for row in audit:
        if row["timestamp"] <= 0:
            continue
        scope = str(row["scope_decision"]).lower()
        counter = weekly[_week(row["timestamp"])]
        counter["total"] += 1
        if scope and scope not in {"in", "in_scope", "allowed", "ok"}:
            counter["refusal"] += 1
    if not weekly:
        raise ValueError("No timestamped production records found.")
    data = [
        {
            "week": week,
            "total": counts["total"],
            "refusal_rate": round(
                counts["refusal"] / counts["total"], 6
            ) if counts["total"] else 0,
            "clarify_rate": round(
                counts["clarify"] / counts["total"], 6
            ) if counts["total"] else 0,
        }
        for week, counts in sorted(weekly.items())
    ]
    builder.add_chart(
        figure_id="d2_weekly_refusal_clarify",
        title="Weekly refusal and clarify rate",
        chart_type="line",
        payload={
            "data": data,
            "x_key": "week",
            "x_label": "ISO week",
            "y_label": "Rate",
            "domain": [0, 1],
            "series": [
                {"key": "refusal_rate", "label": "Refusal"},
                {"key": "clarify_rate", "label": "Clarify"},
            ],
        },
        caption="Weekly rate over available audit and session user turns.",
        source_data="data/audit.db + data/sessions.db",
    )


def _d3_turns_per_session(
    builder: ManifestBuilder,
    turns: list[dict[str, Any]],
) -> None:
    counts: Counter[str] = Counter(
        row["session_id"] for row in turns if row["session_id"]
    )
    if not counts:
        raise ValueError("No session turns found.")
    rows = histogram([float(value) for value in counts.values()], bins=min(20, max(5, len(counts))))
    builder.add_chart(
        figure_id="d3_turns_per_session",
        title="Turns per session",
        chart_type="hist",
        payload={
            "data": rows,
            "x_key": "bin",
            "x_label": "Turns per session",
            "y_label": "Sessions",
            "series": [{"key": "count", "label": "Sessions"}],
        },
        caption=f"Distribution across {len(counts):,} persisted sessions.",
        source_data="data/sessions.db",
    )


def _tokens(text: str) -> list[str]:
    masked = mask_pii(text)
    tokens = re.findall(r"[\wÀ-ỹ]+", masked.lower(), re.UNICODE)
    return [
        token
        for token in tokens
        if len(token) > 1
        and token not in STOPWORDS
        and token not in MASK_TOKENS
        and not token.isdigit()
    ]


def _d4_query_terms(
    builder: ManifestBuilder,
    turns: list[dict[str, Any]],
    audit: list[dict[str, Any]],
) -> None:
    counts: Counter[str] = Counter()
    for row in turns:
        if row["role"] == "user":
            counts.update(_tokens(row["content"]))
    for row in audit:
        counts.update(_tokens(row["content"]))
    top = counts.most_common(30)
    if not top:
        raise ValueError("No anonymized query terms found.")
    data = [
        {"term": term, "count": count}
        for term, count in top
    ]
    artifact_text = json.dumps(data, ensure_ascii=False)
    if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", artifact_text):
        raise ValueError("PII validation failed: email-like token remained.")
    if re.search(r"\b(?:\+84|0)[3-9]\d{8}\b", artifact_text):
        raise ValueError("PII validation failed: phone-like token remained.")
    builder.add_chart(
        figure_id="d4_query_terms",
        title="Top anonymized production query terms",
        chart_type="bar",
        payload={
            "data": data,
            "x_key": "term",
            "x_label": "Masked, stopword-filtered term",
            "y_label": "Occurrences",
            "pii_masked": True,
            "series": [{"key": "count", "label": "Occurrences"}],
        },
        caption="All query text passed through mask_pii before token aggregation.",
        source_data="data/audit.db + data/sessions.db",
    )


@fresh_figure_generation(("usage",))
def generate(
    *,
    root: Path | None = None,
    output_root: Path | None = None,
    pdf: bool = False,
    generation_id: str | None = None,
    generated_at: str | None = None,
) -> Path:
    root = (root or _repo_root()).resolve()
    output_root = output_root or root / "evaluation" / "reports" / "figures"
    builder = ManifestBuilder(
        "usage",
        output_root / "usage",
        pdf=pdf,
        generation_id=generation_id or "",
        generated_at=generated_at or "",
        generator="evaluation.analysis.figures_usage",
    )
    sessions_path = root / "data" / "sessions.db"
    audit_path = root / "data" / "audit.db"

    try:
        turns = _load_session_turns(sessions_path)
    except Exception as exc:
        print(f"[figures_usage] sessions.db read failed: {exc}", flush=True)
        turns = []
    try:
        audit = _load_audit_rows(audit_path)
    except Exception as exc:
        print(f"[figures_usage] audit.db read failed: {exc}", flush=True)
        audit = []

    specs = [
        (
            "d1_route_distribution",
            "Production route vs eval composition",
            "bar",
            lambda: _d1_route_distribution(builder, root, turns, audit),
        ),
        (
            "d2_weekly_refusal_clarify",
            "Weekly refusal and clarify rate",
            "line",
            lambda: _d2_weekly_rates(builder, turns, audit),
        ),
        (
            "d3_turns_per_session",
            "Turns per session",
            "hist",
            lambda: _d3_turns_per_session(builder, turns),
        ),
        (
            "d4_query_terms",
            "Top anonymized production query terms",
            "bar",
            lambda: _d4_query_terms(builder, turns, audit),
        ),
    ]
    for figure_id, title, chart_type, function in specs:
        try:
            function()
        except Exception as exc:
            builder.skip(
                figure_id=figure_id,
                title=title,
                reason=f"{type(exc).__name__}: {exc}",
                caption="Production databases are absent, empty, or lack the required fields.",
                source_data="data/audit.db + data/sessions.db",
                chart_type=chart_type,
            )

    manifest = builder.finish()
    ok = sum(figure["status"] == "ok" for figure in builder.figures)
    skipped = len(builder.figures) - ok
    print(
        f"[figures_usage] turns={len(turns)} audit={len(audit)} "
        f"ok={ok} skipped={skipped} manifest={manifest}",
        flush=True,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    generate(pdf=args.pdf)


if __name__ == "__main__":
    main()
