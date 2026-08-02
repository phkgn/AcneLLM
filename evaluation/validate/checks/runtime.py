from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

from evaluation.common import ROOT, corpus_versions, sha256_file, sha256_text
from evaluation.validate.types import CheckResult, ValidationContext


def _model_key(name: str) -> str:
    return name.split(":", 1)[0]


def normalize_model_name(name: str | None) -> str:
    """Treat Ollama's implicit :latest tag as equivalent to an untagged name."""
    value = str(name or "").strip()
    if value.casefold().endswith(":latest"):
        return value[:-7]
    return value


def model_names_equal(left: str | None, right: str | None) -> bool:
    return normalize_model_name(left) == normalize_model_name(right)


def normalize_system_prompt(text: str | None) -> str:
    """Remove transport/platform-only differences without changing prompt meaning."""
    value = unicodedata.normalize("NFC", str(text or ""))
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in value.split("\n")).strip()


def extract_system_prompt(modelfile: str) -> str:
    match = re.search(r'\bSYSTEM\s+"""(.*?)"""', modelfile, re.DOTALL)
    return normalize_system_prompt(match.group(1)) if match else ""


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body if isinstance(body, dict) else {}


def capture_ollama_models(
    model_names: Sequence[str],
    base_url: str = "http://localhost:11434",
) -> tuple[dict[str, dict[str, Any]], str | None]:
    try:
        tags = _request_json(base_url.rstrip("/") + "/api/tags")
    except Exception as exc:  # noqa: BLE001 - validation must degrade gracefully
        return {}, f"{type(exc).__name__}: {exc}"
    by_name: dict[str, dict[str, Any]] = {}
    for item in tags.get("models") or []:
        if not isinstance(item, dict):
            continue
        for key in {
            str(item.get("name") or ""),
            str(item.get("model") or ""),
            _model_key(str(item.get("name") or "")),
            _model_key(str(item.get("model") or "")),
        }:
            if key:
                by_name[key] = item
    snapshots: dict[str, dict[str, Any]] = {}
    for model in sorted(set(model_names)):
        tag = by_name.get(model) or by_name.get(_model_key(model))
        if not tag:
            snapshots[model] = {"available": False, "digest": None}
            continue
        show: dict[str, Any] = {}
        try:
            show = _request_json(
                base_url.rstrip("/") + "/api/show",
                payload={"name": model},
            )
        except Exception as exc:  # noqa: BLE001
            show = {"show_error": f"{type(exc).__name__}: {exc}"}
        modelfile = str(show.get("modelfile") or "")
        snapshots[model] = {
            "available": True,
            "digest": tag.get("digest"),
            "name": tag.get("name") or tag.get("model"),
            "details": tag.get("details") or show.get("details") or {},
            "parameters": show.get("parameters"),
            "template": show.get("template"),
            "system_prompt": extract_system_prompt(modelfile),
            "modelfile_sha256": sha256_text(modelfile) if modelfile else None,
            "show_error": show.get("show_error"),
        }
    return snapshots, None


def fallback_system_prompts(
    system_configs: Mapping[str, dict[str, Any]],
) -> dict[str, str]:
    paths = {
        "qwen25-base-acnesys": ROOT
        / "evaluation"
        / "modelfiles"
        / "qwen25-base-acnesys"
        / "Modelfile",
        "acnellm-v2-q4": (
            ROOT / "model" / "V2" / "Q4" / "Modelfile"
            if (ROOT / "model" / "V2" / "Q4" / "Modelfile").exists()
            else ROOT / "model" / "Modelfile"
        ),
    }
    prompts: dict[str, str] = {}
    for sid, cfg in system_configs.items():
        model = cfg.get("model")
        path = paths.get(str(model))
        if path and path.exists():
            prompts[sid] = extract_system_prompt(path.read_text(encoding="utf-8"))
    return prompts


def prompt_hashes(system_prompts: Mapping[str, str] | None = None) -> dict[str, Any]:
    template_dir = ROOT / "config" / "prompts"
    judge_dir = ROOT / "evaluation" / "judges" / "prompts"
    templates = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha256_file(path)
        for path in sorted(template_dir.glob("*.j2"))
    }
    judges = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha256_file(path)
        for path in sorted(judge_dir.glob("*.md"))
    }
    systems = {
        sid: sha256_text(normalize_system_prompt(text))
        for sid, text in sorted((system_prompts or {}).items())
        if text
    }
    return {
        "templates": templates,
        "judge_prompts": judges,
        "system_prompts": systems,
    }


def system_config_hashes(paths: Mapping[str, Path]) -> dict[str, str]:
    return {
        sid: sha256_file(path)
        for sid, path in sorted(paths.items())
        if path.exists()
    }


def capture_versioning_snapshot(
    dataset_path: Path,
    experiment_path: Path,
    system_paths: Mapping[str, Path],
    system_configs: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    model_names = [
        str(cfg["model"])
        for cfg in system_configs.values()
        if cfg.get("model")
    ]
    snapshots, ollama_error = capture_ollama_models(model_names)
    prompts = {
        sid: str((snapshots.get(str(cfg.get("model"))) or {}).get("system_prompt") or "")
        for sid, cfg in system_configs.items()
        if cfg.get("model")
    }
    fallback = fallback_system_prompts(system_configs)
    prompts = {sid: text or fallback.get(sid, "") for sid, text in prompts.items()}
    manifest = dataset_path.parent / "MANIFEST.json"
    return {
        "dataset_sha256": sha256_file(dataset_path),
        "dataset_manifest_sha256": sha256_file(manifest) if manifest.exists() else None,
        "experiment_config_sha256": (
            sha256_file(experiment_path) if experiment_path.exists() else None
        ),
        "system_config_hashes": system_config_hashes(system_paths),
        "prompt_hashes": prompt_hashes(prompts),
        "model_digests": {
            model: snapshot.get("digest")
            for model, snapshot in snapshots.items()
            if snapshot.get("digest")
        },
        "model_metadata_status": "SKIPPED" if ollama_error else "CAPTURED",
        "model_metadata_note": ollama_error,
    }


def validate_runtime(
    context: ValidationContext,
) -> tuple[CheckResult, dict[str, Any]]:
    model_names = [
        str(cfg["model"])
        for cfg in context.system_configs.values()
        if cfg.get("model")
    ]
    try:
        from evaluation.common import ensure_repo_importable

        ensure_repo_importable()
        from acne_llm.config import settings

        ollama_url = settings.ollama_url
        production = {
            "model": settings.llm_model,
            "sampling": {
                "temperature": settings.llm_temperature,
                "top_p": settings.llm_top_p,
                "top_k": settings.llm_top_k,
                "repeat_penalty": settings.llm_repeat_penalty,
                "num_ctx": settings.llm_num_ctx,
                "num_predict": settings.llm_num_predict,
            },
            "retrieval": {
                "retrieve_top_k": settings.chat_retrieve_top_k,
                "rerank_top_k": settings.chat_rerank_top_k,
                "max_context_chars": settings.chat_max_context_chars,
            },
        }
    except Exception as exc:  # noqa: BLE001
        ollama_url = "http://localhost:11434"
        production = {"error": f"{type(exc).__name__}: {exc}"}

    snapshots, ollama_error = capture_ollama_models(model_names, ollama_url)
    live_prompts = {
        sid: str((snapshots.get(str(cfg.get("model"))) or {}).get("system_prompt") or "")
        for sid, cfg in context.system_configs.items()
        if cfg.get("model")
    }
    fallback_prompts = fallback_system_prompts(context.system_configs)
    system_prompts = {
        sid: prompt or fallback_prompts.get(sid, "")
        for sid, prompt in live_prompts.items()
    }
    current_corpus = corpus_versions()
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if production.get("error"):
        warnings.append({
            "message": "Production settings could not be imported.",
            "detail": production["error"],
            "file": "src/acne_llm/config.py",
        })
    else:
        s3 = context.system_configs.get("s3") or {}
        if s3 and not model_names_equal(production["model"], s3.get("model")):
            violations.append({
                "message": "S3 model differs from the effective production model.",
                "production": production["model"],
                "s3": s3.get("model"),
                "files": ["src/acne_llm/config.py", "evaluation/configs/systems/s3.yaml"],
            })
        eval_sampling = s3.get("sampling") or {}
        sampling_diff = {
            key: {"production": value, "eval": eval_sampling.get(key)}
            for key, value in production["sampling"].items()
            if eval_sampling.get(key) != value
        }
        if sampling_diff:
            violations.append({
                "message": "S3 sampling differs from production settings.",
                "diff": sampling_diff,
                "files": ["src/acne_llm/config.py", "evaluation/configs/systems/s3.yaml"],
            })
        retrieval_diff = {
            "production": production["retrieval"],
            "generation_production_config": {
                "retrieve_top_k": s3.get("retrieve_top_k"),
                "rerank_top_k": s3.get("rerank_top_k"),
            },
        }
        if (
            s3.get("retrieve_top_k") != production["retrieval"]["retrieve_top_k"]
            or s3.get("rerank_top_k") != production["retrieval"]["rerank_top_k"]
        ):
            warnings.append({
                "message": (
                    "T3 batch retrieval depth differs from production SSE; "
                    "T3 cannot be presented as production behavior."
                ),
                "diff": retrieval_diff,
                "files": [
                    "src/acne_llm/config.py",
                    "evaluation/configs/systems/s3.yaml",
                    "evaluation/adapters/ollama_batch.py",
                    "evaluation/adapters/sse_api.py",
                ],
            })

    for key in ("bm25_sha256", "chroma_fingerprint"):
        old = context.run_meta.get(key)
        current = current_corpus.get(key)
        if old and current and old != current:
            violations.append({
                "message": f"Corpus artifact {key} changed since the run.",
                "run_meta": old,
                "current": current,
                "file": "run_meta.json",
            })
        elif not old:
            violations.append({
                "message": f"run_meta.json does not pin {key}.",
                "file": "run_meta.json",
            })

    if ollama_error:
        warnings.append({
            "message": "Ollama model metadata check was skipped.",
            "detail": ollama_error,
            "url": ollama_url,
        })
    else:
        missing_models = sorted(
            model for model, snapshot in snapshots.items()
            if not snapshot.get("available")
        )
        if missing_models:
            violations.append({
                "message": "Configured models are missing from Ollama.",
                "models": missing_models,
                "url": ollama_url,
            })
        recorded = context.run_meta.get("model_digests") or {}
        digest_drift = {
            model: {
                "run_meta": recorded.get(model),
                "current": snapshot.get("digest"),
            }
            for model, snapshot in snapshots.items()
            if recorded.get(model) and recorded.get(model) != snapshot.get("digest")
        }
        if digest_drift:
            violations.append({
                "message": "Live Ollama digest differs from the run metadata.",
                "models": digest_drift,
                "file": "run_meta.json",
            })

    snapshot = {
        "production": production,
        "ollama_url": ollama_url,
        "ollama_models": snapshots,
        "system_prompts": system_prompts,
        "prompt_hashes": prompt_hashes(system_prompts),
        "system_config_hashes": system_config_hashes(context.system_config_paths),
        "corpus": current_corpus,
        "warnings": warnings,
        "violations": violations,
    }
    if violations:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"
    evidence = violations + warnings
    if not evidence:
        evidence = [{
            "message": "Eval model, sampling and corpus artifacts match production/run metadata.",
            "models": {
                model: snapshot.get("digest")
                for model, snapshot in snapshots.items()
            },
        }]
    return CheckResult(
        "runtime_alignment",
        status,
        evidence,
        critical=bool(violations),
    ), snapshot
