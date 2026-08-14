"""Convert LLMData acne tasks into chat-style fine-tuning records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

app = typer.Typer()

SYSTEM_PROMPT = (
    "Bạn là AcneLLM, trợ lý tư vấn da mụn tiếng Việt. Trả lời an toàn y tế, "
    "không chẩn đoán chắc chắn, không kê đơn thuốc, và khuyên khám da liễu khi có dấu hiệu nặng."
)


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v).strip()]
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if isinstance(item, list):
                out.extend(str(v) for v in item if v is not None and str(v).strip())
            elif item is not None:
                out.append(f"{key}: {item}")
        return out
    text = str(value).strip()
    return [text] if text else []


def _description(row: dict) -> str:
    inp = row.get("input") or {}
    for key in ("raw_patient_text", "patient_statement", "context"):
        if inp.get(key):
            return str(inp[key])
    if inp.get("structured_features"):
        return "Thông tin ca mụn: " + json.dumps(
            inp["structured_features"], ensure_ascii=False, sort_keys=True
        )
    if inp.get("classification_result"):
        return "Kết quả phân loại ban đầu: " + json.dumps(
            inp["classification_result"], ensure_ascii=False, sort_keys=True
        )
    return json.dumps(inp, ensure_ascii=False, sort_keys=True)


def _severity_from(value: str | None) -> str:
    value = (value or "unknown").lower()
    return value if value in {"mild", "moderate", "severe", "unknown"} else "unknown"


def _recommendations(raw: Any) -> list[dict]:
    actions: list[str] = []
    if isinstance(raw, dict):
        actions.extend(_items(raw.get("first_line")))
        actions.extend(_items(raw.get("second_line")))
        actions.extend(_items(raw.get("recommendations")))
        actions.extend(_items(raw.get("lifestyle_advice")))
        if raw.get("monitoring"):
            actions.append(str(raw["monitoring"]))
    else:
        actions.extend(_items(raw))

    if not actions:
        actions = ["Theo dõi tình trạng và đi khám bác sĩ da liễu nếu mụn nặng, đau, lan rộng hoặc để lại sẹo."]

    return [
        {
            "step": i,
            "action": action,
            "rationale": None,
            "source_chunk_id": None,
            "category": "other",
        }
        for i, action in enumerate(actions[:6], 1)
    ]


def _target_advise(row: dict) -> dict:
    out = row.get("output") or {}
    task_type = row.get("task_type", "unknown")
    structured = out.get("structured_result") if isinstance(out, dict) else None
    classification = {}
    rec_source: Any = None

    if isinstance(structured, dict):
        classification = structured.get("classification") or {}
        rec_source = structured.get("recommendations")
    elif task_type == "classification":
        classification = out
    elif task_type == "recommendation":
        classification = (row.get("input") or {}).get("classification_result") or {}
        rec_source = out.get("recommendations") if isinstance(out, dict) else out
    else:
        rec_source = out.get("recommendations") if isinstance(out, dict) else out

    severity = _severity_from(classification.get("severity") if isinstance(classification, dict) else None)
    acne_type = (
        classification.get("acne_type")
        if isinstance(classification, dict) and classification.get("acne_type")
        else task_type
    )
    causes = []
    if isinstance(classification, dict):
        causes.extend(_items(classification.get("contributing_factors")))
    if isinstance(out, dict):
        causes.extend(_items(out.get("extracted_features")))
        if out.get("reasoning"):
            causes.append(str(out["reasoning"]))
        if structured and structured.get("reasoning"):
            causes.append(str(structured["reasoning"]))

    unsafe_flags = []
    if isinstance(out, dict):
        unsafe_flags.extend(_items(out.get("unsafe_flags")))
    if isinstance(structured, dict):
        unsafe_flags.extend(_items(structured.get("unsafe_flags")))

    return {
        "severity": severity,
        "acne_type_primary": str(acne_type or "unknown"),
        "causes": causes[:6] or ["Chưa đủ thông tin để xác định nguyên nhân."],
        "recommendations": _recommendations(rec_source),
        "red_flags": [
            {"flag": flag, "severity": "warn", "reason": "unsafe_flag"}
            for flag in unsafe_flags[:5]
        ],
        "used_chunks": [],
        "confidence": 0.7,
        "disclaimer": "Thông tin mang tính tham khảo, không thay thế chẩn đoán từ bác sĩ.",
        "mode": "llm_only",
        "model_name": "",
        "latency_ms": 0,
    }


def convert_row(row: dict) -> dict:
    description = _description(row)
    target = _target_advise(row)
    user_content = (
        f"<raw_user_message>{description}</raw_user_message>\n"
        f"<task_type>{row.get('task_type', 'unknown')}</task_type>"
    )
    return {
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
            "sample_type": "llm_only_chatml",
        },
    }


@app.command()
def main(
    input: str = typer.Option("research/LLMData/acne_dataset.jsonl", "--input"),
    output: str = typer.Option("data/finetune/llm_only_chatml.jsonl", "--output"),
) -> None:
    in_path = Path(input)
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with in_path.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            record = convert_row(json.loads(line))
            dst.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    typer.echo(f"Wrote {count} records to {out_path}")


if __name__ == "__main__":
    app()
