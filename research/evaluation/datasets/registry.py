"""Dataset registry: validate schema (§5.2 blueprint), freeze bằng sha256 MANIFEST.

Usage:
    python -m evaluation.datasets.registry validate \
        evaluation/datasets/active/generator_eval.v3_2_145.jsonl
    python -m evaluation.datasets.registry freeze evaluation/datasets/active
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import read_jsonl, sha256_file, utcnow  # noqa: E402

REQUIRED = ["sample_id", "user_query", "task_type", "split", "dataset_version",
            "source_provenance"]
OPTIONAL_DEFAULTS = {
    # ĐÃ GỠ khỏi schema — đừng thêm lại mà không có consumer:
    #   expected_behavior     — trùng vai với expected_answer_points (văn xuôi vs
    #                           danh sách, cùng mô tả "trả lời đúng trông ra sao").
    #                           Hai bản mô tả cùng một thứ là chỗ sinh mâu thuẫn.
    #   conversation_history  — null 197/197, chưa từng có dữ liệu. Móc đa lượt
    #                           vẫn còn ở run_ablation._populate_history: thêm
    #                           field này lại vào file là nó chạy, không phải sửa
    #                           code. Cần khi muốn đo `clarify` (vốn là đa lượt).
    "session_id": None, "intent_label": None,
    "subject_label": None, "clinical_risk_level": None,
    "expected_answer_points": [], "forbidden_claims": [], "relevant_chunk_ids": [],
    "relevance_grade": {}, "reference_answer": None,
    "difficulty": None, "annotation_status": "draft", "human_notes": "",
    # v3: nhãn suy ra từ system prompt trong Modelfile, không tự nghĩ ra.
    # `spec_category` = loại theo spec; `generator_constraints` = luật generator
    # phải giữ khi trả lời ca này (không chẩn đoán, không hướng dẫn thủ thuật…).
    "intent_label_source": None, "spec_category": None,
    "generator_constraints": [],
}
VALID_PROVENANCE = {
    "human_written", "real_user", "synthetic_deepseek", "synthetic_openai",
    "paraphrase", "legacy_approved", "legacy_sample",
}
VALID_RISK = {None, "low", "medium", "high", "critical"}


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for i, row in enumerate(read_jsonl(path), 1):
        for field in REQUIRED:
            if field not in row or row[field] in (None, ""):
                errors.append(f"{path.name}:{i} thiếu trường bắt buộc '{field}'")
        sid = row.get("sample_id")
        if sid in seen_ids:
            errors.append(f"{path.name}:{i} sample_id trùng: {sid}")
        seen_ids.add(sid)
        if row.get("source_provenance") not in VALID_PROVENANCE:
            errors.append(f"{path.name}:{i} source_provenance không hợp lệ: "
                          f"{row.get('source_provenance')}")
        if row.get("clinical_risk_level") not in VALID_RISK:
            errors.append(f"{path.name}:{i} clinical_risk_level không hợp lệ")
        grades = row.get("relevance_grade") or {}
        for cid, g in grades.items():
            if g not in (0, 1, 2):
                errors.append(f"{path.name}:{i} relevance_grade[{cid}]={g} ∉ {{0,1,2}}")
    return errors


def load_dataset(path: Path) -> list[dict]:
    """Load + validate + fill defaults. Nếu MANIFEST tồn tại → verify sha256 (freeze)."""
    path = Path(path)
    errors = validate_file(path)
    if errors:
        raise ValueError("Dataset không hợp lệ:\n" + "\n".join(errors[:20]))
    manifest = path.parent / "MANIFEST.json"
    if manifest.exists():
        entries = json.loads(manifest.read_text(encoding="utf-8")).get("files", {})
        expected = entries.get(path.name)
        if expected and expected != sha256_file(path):
            raise ValueError(
                f"{path.name} đã bị SỬA sau khi freeze (sha256 mismatch với MANIFEST). "
                "Dataset test là bất biến — tạo version mới thay vì sửa."
            )
    rows = read_jsonl(path)
    return [{**OPTIONAL_DEFAULTS, **row} for row in rows]


def freeze_dir(dirpath: Path) -> None:
    files = sorted(p for p in Path(dirpath).glob("*.jsonl"))
    manifest = {
        "frozen_at": utcnow(),
        "files": {p.name: sha256_file(p) for p in files},
    }
    out = Path(dirpath) / "MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Frozen {len(files)} files -> {out}")


if __name__ == "__main__":
    cmd, target = sys.argv[1], Path(sys.argv[2])
    if cmd == "validate":
        errs = validate_file(target)
        print("\n".join(errs) if errs else "OK")
        sys.exit(1 if errs else 0)
    elif cmd == "freeze":
        freeze_dir(target)
