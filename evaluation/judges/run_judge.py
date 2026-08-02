"""Chấm điểm results bằng LLM judge (blind, cached, cost-tracked).

Pointwise + faithfulness (claim extract → entailment với context) cho mọi record;
pairwise 2 chiều (swap) cho các cặp pre-registered trong experiment config.

Usage:
    python -m evaluation.judges.run_judge --run-dir evaluation/reports/main_2x2_t3 \
        --dataset evaluation/datasets/v1/answer_quality_test.jsonl \
        [--provider openai] [--pairs s0:s1,s2:s3] [--limit 50]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from acne_llm.config import settings  # noqa: E402
from evaluation.common import (  # noqa: E402
    ROOT,
    append_jsonl,
    read_jsonl,
    sha256_file,
    utcnow,
    write_jsonl,
)
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.judges.clients import (  # noqa: E402
    DEFAULT_JUDGE_WORKERS,
    DEFAULT_OPENAI_FAITHFULNESS_MODEL,
    JudgeClient,
    load_prompt,
)

POINTWISE_AXES = ["correctness", "completeness", "safety", "relevance",
                  "fluency", "instruction_following"]
PAIRWISE_CHOICES = {"A", "B", "tie"}


def is_valid_pointwise_payload(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for axis in POINTWISE_AXES:
        score = value.get(axis)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return False
        if float(score) not in {1.0, 2.0, 3.0, 4.0, 5.0}:
            return False
    confidence = value.get("confidence")
    return (
        confidence is None
        or (
            not isinstance(confidence, bool)
            and isinstance(confidence, (int, float))
            and 0.0 <= float(confidence) <= 1.0
        )
    )


def is_valid_pairwise_row(row: dict) -> bool:
    return (
        row.get("forward") in PAIRWISE_CHOICES
        and row.get("backward") in PAIRWISE_CHOICES
        and row.get("verdict") in PAIRWISE_CHOICES
    )


def _inferred_provider(row: dict) -> str | None:
    provider = row.get("judge_provider")
    if isinstance(provider, str) and provider:
        return provider
    model = str(row.get("judge_model") or "")
    if model.startswith("gpt-"):
        return "openai"
    if model.startswith("deepseek"):
        return "deepseek"
    return None


def _matches_client(row: dict, client: JudgeClient) -> bool:
    return (
        _inferred_provider(row) == client.provider
        and row.get("judge_model") == client.model
    )


def _prepare_resume(path: Path, client: JudgeClient, *, pairwise: bool,
                    faithfulness_client: JudgeClient | None = None) -> set[str]:
    """Keep only valid rows for the active judge and return completed IDs.

    Invalid rows are deliberately removed so a resumed run retries them. Mixing
    providers/models in one artifact is rejected because report readers expect
    one canonical judge row per sample.
    """
    if not path.exists():
        return set()
    rows = read_jsonl(path)
    foreign = [row for row in rows if not _matches_client(row, client)]
    if not pairwise and faithfulness_client is not None:
        foreign.extend(
            row for row in rows
            if row.get("faithfulness") is not None
            and (
                row.get("faithfulness_judge_provider") != faithfulness_client.provider
                or row.get("faithfulness_judge_model") != faithfulness_client.model
            )
            and row not in foreign
        )
    if foreign:
        found = sorted({
            f"{_inferred_provider(row) or 'unknown'}/{row.get('judge_model') or 'unknown'}"
            for row in foreign
        })
        raise RuntimeError(
            f"{path} chứa artifact judge khác ({', '.join(found)}). "
            "Hãy dùng run directory mới để không trộn provider/model."
        )
    latest = {str(row["sample_id"]): row for row in rows if row.get("sample_id")}
    if pairwise:
        valid = [row for row in latest.values() if is_valid_pairwise_row(row)]
    else:
        valid = [
            row for row in latest.values()
            if row.get("judge_status") == "valid"
            and is_valid_pointwise_payload(row.get("pointwise"))
        ]
    write_jsonl(path, valid)
    return {str(row["sample_id"]) for row in valid}


def _context_text(record: dict) -> str:
    """Ghép context THẬT từ trace: ưu tiên context_chunks (adapter lưu text đầy đủ),
    Nếu chỉ có id không text thì trả '(không có)' để judge KHÔNG chấm
    faithfulness trên placeholder (tránh not_found giả)."""
    trace = record.get("trace") or {}
    exact_context = trace.get("faithfulness_context")
    if isinstance(exact_context, str) and exact_context.strip():
        return exact_context.strip()
    parts = [f"[{c['chunk_id']}] {c['text']}"
             for c in trace.get("context_chunks") or [] if c.get("text")]
    return "\n\n".join(parts) or "(không có tài liệu)"


def build_pointwise_prompt(record: dict, sample: dict) -> str:
    return load_prompt(
        "pointwise",
        question=sample["user_query"],
        user_context=json.dumps(sample.get("user_context") or {}, ensure_ascii=False),
        context=_context_text(record),
        expected_points="\n".join(f"- {p}" for p in sample.get("expected_answer_points") or []) or "(không có)",
        forbidden_claims="\n".join(f"- {c}" for c in sample.get("forbidden_claims") or []) or "(không có)",
        answer=record.get("answer") or "(rỗng)",
    )


def judge_pointwise(client: JudgeClient, record: dict, sample: dict, *,
                    use_cache: bool = True) -> dict | None:
    prompt = build_pointwise_prompt(record, sample)
    result = client.judge(prompt, use_cache=use_cache)
    if is_valid_pointwise_payload(result):
        return result
    return client.judge(
        prompt
        + "\n\nSCHEMA REPAIR: Mỗi điểm bắt buộc là SỐ NGUYÊN từ 1 đến 5. "
          "Không bao giờ dùng 0 hoặc số ngoài khoảng. Trả lại toàn bộ JSON đúng schema.",
        use_cache=False,
    )


def judge_error_class(client: JudgeClient, record: dict, sample: dict) -> dict | None:
    """Error classifier (§10) — chỉ gọi cho record bị điểm kém."""
    prompt = load_prompt(
        "error_classify",
        question=sample["user_query"],
        expected_behavior=sample.get("expected_behavior") or "(không có)",
        context=_context_text(record),
        answer=record.get("answer") or "(rỗng)",
    )
    return client.judge(prompt)


def judge_faithfulness(client: JudgeClient, record: dict) -> dict | None:
    """Faithfulness = supported / total claims (RAGAS-style). Chỉ cho hệ có context."""
    context = _context_text(record)
    if context.startswith("(không"):
        return None
    extract_prompt = load_prompt("claim_extract", answer=record.get("answer") or "")
    extraction = client.judge(extract_prompt)
    claims = (extraction or {}).get("claims")
    if not _valid_claim_list(claims):
        extraction = client.judge(
            extract_prompt
            + "\n\nSCHEMA REPAIR: claims phải là mảng object, mỗi object có text "
              "là string KHÔNG RỖNG.",
            use_cache=False,
        )
        claims = (extraction or {}).get("claims")
    if not _valid_claim_list(claims):
        return {
            "n_claims": 0,
            "faithfulness": None,
            "contradiction_rate": None,
            "claims": [],
            "valid": False,
            "error": "claim_schema_failure",
        }
    if not claims:
        return None
    claims = [{**claim, "text": claim["text"].strip()} for claim in claims]
    verdicts = []
    for claim in claims:
        entailment_prompt = load_prompt(
            "entailment", context=context, claim=claim["text"]
        )
        v = client.judge(entailment_prompt)
        if (v or {}).get("verdict") not in {
            "supported", "contradicted", "not_found"
        }:
            v = client.judge(
                entailment_prompt
                + "\n\nSCHEMA REPAIR: verdict chỉ được là supported, contradicted, "
                  "hoặc not_found.",
                use_cache=False,
            )
        verdicts.append({**claim, "verdict": (v or {}).get("verdict", "invalid")})
    if any(verdict["verdict"] not in {"supported", "contradicted", "not_found"}
           for verdict in verdicts):
        return {
            "n_claims": len(verdicts),
            "faithfulness": None,
            "contradiction_rate": None,
            "claims": verdicts,
            "valid": False,
            "error": "entailment_schema_failure",
        }
    supported = sum(1 for v in verdicts if v["verdict"] == "supported")
    contradicted = sum(1 for v in verdicts if v["verdict"] == "contradicted")
    return {
        "n_claims": len(verdicts),
        "faithfulness": round(supported / len(verdicts), 4),
        "contradiction_rate": round(contradicted / len(verdicts), 4),
        "claims": verdicts,
        "valid": True,
    }


def _valid_claim_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(claim, dict)
        and isinstance(claim.get("text"), str)
        and bool(claim["text"].strip())
        for claim in value
    )


def judge_pair(client: JudgeClient, rec_a: dict, rec_b: dict, sample: dict,
               rng: random.Random) -> dict:
    """Pairwise 2 chiều swap (Wang et al. 2024): mâu thuẫn → tie."""
    def one(a: dict, b: dict) -> str:
        prompt = load_prompt(
            "pairwise",
            question=sample["user_query"],
            user_context=json.dumps(sample.get("user_context") or {}, ensure_ascii=False),
            expected_points="\n".join(sample.get("expected_answer_points") or []) or "(không có)",
            answer_a=a.get("answer") or "(rỗng)",
            answer_b=b.get("answer") or "(rỗng)",
        )
        res = client.judge(prompt)
        if (res or {}).get("winner") not in PAIRWISE_CHOICES:
            res = client.judge(
                prompt
                + "\n\nSCHEMA REPAIR: winner chỉ được là A, B hoặc tie.",
                use_cache=False,
            )
        return (res or {}).get("winner", "invalid")
    w1 = one(rec_a, rec_b)                       # A=hệ 1, B=hệ 2
    w2 = one(rec_b, rec_a)                       # swap
    w2_mapped = {"A": "B", "B": "A"}.get(w2, w2)
    verdict = w1 if w1 == w2_mapped and w1 in ("A", "B") else "tie"
    return {"forward": w1, "backward": w2, "verdict": verdict}


def _judge_pointwise_row(client: JudgeClient, system_id: str, record: dict,
                         sample: dict, *, skip_faithfulness: bool,
                         faithfulness_client: JudgeClient | None = None,
                         ) -> tuple[dict, bool]:
    pointwise = judge_pointwise(client, record, sample)
    pointwise_valid = is_valid_pointwise_payload(pointwise)
    row = {
        "sample_id": record["sample_id"],
        "system_id": system_id,
        "judge_provider": client.provider,
        "judge_model": client.model,
        "pointwise": pointwise,
        "judge_status": "valid" if pointwise_valid else "invalid",
    }
    if not pointwise_valid:
        row["judge_error"] = (
            "pointwise_parse_failure"
            if pointwise is None else "pointwise_schema_failure"
        )
    if pointwise_valid and not skip_faithfulness and record.get("used_chunks"):
        faith_client = faithfulness_client or client
        row["faithfulness"] = judge_faithfulness(faith_client, record)
        row["faithfulness_judge_provider"] = faith_client.provider
        row["faithfulness_judge_model"] = faith_client.model
        claims = (row.get("faithfulness") or {}).get("claims") or []
        if ((row.get("faithfulness") or {}).get("valid") is False
                or any(claim.get("verdict") == "invalid" for claim in claims)):
            row["judge_status"] = "invalid"
            row["judge_error"] = "faithfulness_schema_failure"
    pw = row["pointwise"] or {}
    if any(
        isinstance(pw.get(axis), (int, float)) and pw[axis] <= 2
        for axis in ("correctness", "safety")
    ):
        row["error_class"] = judge_error_class(client, record, sample)
    return row, row["judge_status"] == "invalid"


def _judge_pairwise_row(client: JudgeClient, a: str, b: str, sid: str,
                        rec_a: dict, rec_b: dict, sample: dict,
                        rng: random.Random) -> tuple[dict, bool]:
    verdict = judge_pair(client, rec_a, rec_b, sample, rng)
    row = {
        "sample_id": sid,
        "pair": [a, b],
        "judge_provider": client.provider,
        "judge_model": client.model,
        **verdict,
    }
    valid = is_valid_pairwise_row(row)
    row["judge_status"] = "valid" if valid else "invalid"
    if not valid:
        row["judge_error"] = "pairwise_parse_or_schema_failure"
    return row, not valid


def _total_cost(primary: JudgeClient, faithfulness: JudgeClient) -> float:
    return primary.total_cost_usd + (
        faithfulness.total_cost_usd if faithfulness is not primary else 0.0
    )


def _total_calls(primary: JudgeClient, faithfulness: JudgeClient) -> int:
    return primary.calls + (faithfulness.calls if faithfulness is not primary else 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument(
        "--provider",
        default=settings.judge_provider,
        choices=["openai"],
    )
    ap.add_argument(
        "--model",
        default=settings.judge_model,
        help=(
            "Judge model; mặc định đọc từ Settings/.env "
            f"({settings.judge_model})."
        ),
    )
    ap.add_argument(
        "--faithfulness-model",
        default=None,
        help=(
            "OpenAI model cho claim extraction/entailment; mặc định "
            f"{DEFAULT_OPENAI_FAITHFULNESS_MODEL}."
        ),
    )
    ap.add_argument("--pairs", default=None, help="vd: s0:s1,s1:s3")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_JUDGE_WORKERS,
        help=(
            "Số OpenAI requests đồng thời theo record "
            f"(mặc định {DEFAULT_JUDGE_WORKERS})."
        ),
    )
    ap.add_argument("--skip-faithfulness", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.workers <= 32:
        ap.error("--workers phải từ 1 đến 32")

    run_dir = Path(args.run_dir)
    samples = {s["sample_id"]: s for s in load_dataset(ROOT / args.dataset)}
    client = JudgeClient(args.provider, args.model)
    faithfulness_client = client
    if not args.skip_faithfulness:
        faithfulness_model = args.faithfulness_model
        if faithfulness_model is None and args.provider == "openai":
            faithfulness_model = DEFAULT_OPENAI_FAITHFULNESS_MODEL
        if faithfulness_model and faithfulness_model != client.model:
            faithfulness_client = JudgeClient(args.provider, faithfulness_model)
    rng = random.Random(42)
    invalid_rows = 0
    started_at = utcnow()

    results = {p.stem.replace(".results", ""): read_jsonl(p)
               for p in sorted(run_dir.glob("*.results.jsonl"))}

    # Pointwise + faithfulness
    for system_id, records in results.items():
        out_path = run_dir / f"{system_id}.judged.jsonl"
        done = _prepare_resume(
            out_path,
            client,
            pairwise=False,
            faithfulness_client=faithfulness_client,
        )
        pending = [
            (rec, samples[rec["sample_id"]])
            for rec in records[: args.limit]
            if rec.get("ok")
            and rec["sample_id"] not in done
            and rec["sample_id"] in samples
        ]
        def pointwise_task(item: tuple[dict, dict]) -> tuple[dict, bool]:
            rec, sample = item
            return _judge_pointwise_row(
                client,
                system_id,
                rec,
                sample,
                skip_faithfulness=args.skip_faithfulness,
                faithfulness_client=faithfulness_client,
            )

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for index, (row, invalid) in enumerate(
                pool.map(pointwise_task, pending), 1
            ):
                invalid_rows += int(invalid)
                append_jsonl(out_path, row)
                if index % 10 == 0 or index == len(pending):
                    print(
                        f"[{system_id}] {len(done) + index}/"
                        f"{len(done) + len(pending)} | cost=${_total_cost(client, faithfulness_client):.3f}",
                        flush=True,
                    )
        print(
            f"[{system_id}] judged -> {out_path} "
            f"| cost=${_total_cost(client, faithfulness_client):.3f}"
        )

    # Pairwise pre-registered
    if args.pairs:
        for pair in args.pairs.split(","):
            a, b = pair.split(":")
            out_path = run_dir / f"pairwise_{a}_vs_{b}.jsonl"
            done = _prepare_resume(out_path, client, pairwise=True)
            recs_a = {r["sample_id"]: r for r in results.get(a, []) if r.get("ok")}
            recs_b = {r["sample_id"]: r for r in results.get(b, []) if r.get("ok")}
            pending_ids = [
                sid
                for sid in sorted(recs_a.keys() & recs_b.keys())[: args.limit]
                if sid not in done and sid in samples
            ]
            def pairwise_task(sid: str) -> tuple[dict, bool]:
                return _judge_pairwise_row(
                    client,
                    a,
                    b,
                    sid,
                    recs_a[sid],
                    recs_b[sid],
                    samples[sid],
                    rng,
                )

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for index, (row, invalid) in enumerate(
                    pool.map(pairwise_task, pending_ids), 1
                ):
                    invalid_rows += int(invalid)
                    append_jsonl(out_path, row)
                    if index % 10 == 0 or index == len(pending_ids):
                        print(
                            f"[{a} vs {b}] {len(done) + index}/"
                            f"{len(done) + len(pending_ids)} "
                            f"| cost=${_total_cost(client, faithfulness_client):.3f}",
                            flush=True,
                        )
            print(f"[{a} vs {b}] -> {out_path}")

    print(
        f"\nJudge: {client.provider}/{client.model} | calls: "
        f"{_total_calls(client, faithfulness_client)} | cost ước tính: "
        f"${_total_cost(client, faithfulness_client):.2f} | invalid: {invalid_rows}"
    )
    judge_run = {
        "started": started_at,
        "finished": utcnow(),
        "status": "failed" if invalid_rows else "succeeded",
        "provider": client.provider,
        "model": client.model,
        "faithfulness_provider": faithfulness_client.provider,
        "faithfulness_model": faithfulness_client.model,
        "workers": args.workers,
        "calls": _total_calls(client, faithfulness_client),
        "calls_by_model": {
            client.model: client.calls,
            **(
                {faithfulness_client.model: faithfulness_client.calls}
                if faithfulness_client is not client else {}
            ),
        },
        "estimated_cost_usd": round(_total_cost(client, faithfulness_client), 6),
        "estimated_cost_by_model_usd": {
            client.model: round(client.total_cost_usd, 6),
            **(
                {faithfulness_client.model: round(faithfulness_client.total_cost_usd, 6)}
                if faithfulness_client is not client else {}
            ),
        },
        "invalid_rows": invalid_rows,
        "dataset": args.dataset,
        "limit": args.limit,
        "skip_faithfulness": args.skip_faithfulness,
        "pairs": args.pairs.split(",") if args.pairs else [],
        "prompt_hashes": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha256_file(path)
            for path in sorted((Path(__file__).parent / "prompts").glob("*.md"))
        },
    }
    (run_dir / "judge_run.json").write_text(
        json.dumps(judge_run, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    run_meta_path = run_dir / "run_meta.json"
    if run_meta_path.exists():
        run_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
        run_meta.update({
            "judge_provider": client.provider,
            "judge_model": client.model,
            "faithfulness_judge_provider": faithfulness_client.provider,
            "faithfulness_judge_model": faithfulness_client.model,
            "judge_workers": args.workers,
        })
        run_meta.setdefault("prompt_hashes", {})["judge_prompts"] = (
            judge_run["prompt_hashes"]
        )
        run_meta_path.write_text(
            json.dumps(run_meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if invalid_rows:
        raise SystemExit(
            f"Judge tạo {invalid_rows} row invalid; run bị đánh dấu FAIL và các row này "
            "sẽ được retry khi chạy lại."
        )


if __name__ == "__main__":
    main()
