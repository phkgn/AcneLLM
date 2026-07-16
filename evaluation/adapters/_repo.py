"""Cầu nối với code repo: build container theo config eval, KHÔNG đụng dữ liệu production.

- fallback_model bị tắt (R4)
- audit.db / sessions.db trỏ vào thư mục tạm của eval (không ghi vào data/ production)
- seed inject vào Ollama sampling options (repo không hỗ trợ seed → wrap tối thiểu)
- preprocessing dùng ĐÚNG production path: prepare_user_text → normalize_chat_message
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from evaluation.common import ensure_repo_importable

ensure_repo_importable()


def build_eval_container(model: str | None, sampling: dict | None):
    from acne_llm.config import settings as base_settings
    from acne_llm.di import build_container

    tmp = Path(tempfile.mkdtemp(prefix="acnellm_eval_"))
    overrides = {
        "llm_fallback_model": "",                      # R4: không fallback khi eval
        "audit_db_path": str(tmp / "audit.db"),        # không ghi audit production
        "session_db_path": str(tmp / "sessions.db"),
        "cache_size_gb": 0.0,                          # R5: tắt response cache
    }
    if model:
        overrides["llm_model"] = model
    if sampling:
        overrides.update({
            "llm_temperature": sampling.get("temperature", 0.35),
            "llm_top_p": sampling.get("top_p", 0.85),
            "llm_top_k": sampling.get("top_k", 40),
            "llm_repeat_penalty": sampling.get("repeat_penalty", 1.1),
            "llm_num_ctx": sampling.get("num_ctx", 3072),
            "llm_num_predict": sampling.get("num_predict", 1200),
        })
    settings = base_settings.model_copy(update=overrides)
    container = build_container(settings)

    # Chống fallback tuyệt đối, kể cả khi build_container thay đổi sau này
    container.llm.fallback_model = None

    # Inject seed (Ollama options) — wrap _sampling_options, không sửa repo
    seed = (sampling or {}).get("seed")
    if seed is not None:
        orig = container.llm._sampling_options
        container.llm._sampling_options = (
            lambda *a, **k: {**orig(*a, **k), "seed": int(seed)}
        )
    return container


def normalize_query(container, sample: dict):
    """Production preprocessing: raw text → UserInput (đúng path chat)."""
    from acne_llm.chat.preprocess import prepare_user_text
    from acne_llm.chat.normalizer import normalize_chat_message

    raw = sample["user_query"]
    prepared = prepare_user_text(raw)
    user = normalize_chat_message(
        raw,
        mode="auto",
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )
    # user_context bổ sung từ dataset (age, skin_type, is_pregnant, ...)
    ctx = sample.get("user_context") or {}
    if ctx and getattr(user, "user_context", None) is not None:
        try:
            merged = user.user_context.model_copy(update={
                k: v for k, v in ctx.items()
                if hasattr(user.user_context, k) and v is not None
            })
            user = user.model_copy(update={"user_context": merged})
        except Exception:
            pass  # giữ user gốc nếu schema không khớp — ghi vào trace ở caller
    return user, prepared
