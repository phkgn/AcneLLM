#!/usr/bin/env python3
"""Build the three-class semantic-router dataset and OOS calibration set.

OpenAI is used only by this offline data-building command.  Runtime routing
loads local embeddings from ``intent_classify.train.jsonl`` and never calls an
external API.

The command:
1. filters the existing extraction golden set;
2. generates class-controlled Vietnamese examples;
3. judges only newly generated in-scope examples;
4. removes exact and near duplicates;
5. creates a stratified 80/20 split; and
6. creates an OOS-only calibration set.

Example:
    python scripts/build_intent_dataset.py --budget-usd 1.5
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import unicodedata
from typing import Any, Iterable

from openai import OpenAI
from rapidfuzz.fuzz import ratio


ROOT = Path(__file__).resolve().parents[1]
INTENTS = ("advise", "knowledge", "clarify")
TARGETS = {"advise": 500, "knowledge": 500, "clarify": 300}
MODEL_PRICING_PER_MILLION = {
    # Standard processing prices. Cached-input usage is accounted separately.
    "deepseek-v4-flash": {"input": 0.27, "cached_input": 0.07, "output": 1.10},
    "deepseek-chat": {"input": 0.27, "cached_input": 0.07, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "cached_input": 0.14, "output": 2.19},
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {
        "input": 0.15,
        "cached_input": 0.075,
        "output": 0.60,
    },
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
}

INTENT_DEFINITIONS = """Nhãn intent phải giữ đúng định nghĩa của golden set:
- advise: người dùng kể một tình trạng mụn/da cụ thể rồi xin tư vấn hoặc hỏi cách xử lý.
- knowledge: hỏi kiến thức chung, định nghĩa, cơ chế, so sánh, hoặc an toàn hoạt chất;
  không khai báo một ca cá nhân cụ thể.
- clarify: có ý định nói về da/mụn hoặc xin hỗ trợ nhưng câu quá ít/mơ hồ để biết
  tình trạng hay nhu cầu thực sự; hệ thống cần hỏi một câu mở làm rõ.
- Ngoài phạm vi da mụn không thuộc ba lớp trên và phải bị loại.
"""

STYLE_AXES = (
    "teencode tự nhiên: k/ko, dc, vs, e, mn, sp",
    "không dấu hoàn toàn",
    "sai chính tả nhẹ như người gõ điện thoại",
    "câu ngắn, khẩu ngữ",
    "câu dài, kể vòng vo nhưng vẫn đúng một intent",
    "trang trọng, đủ dấu câu",
    "suồng sã miền Nam",
    "giọng lo lắng hoặc bối rối",
    "trộn tên hoạt chất tiếng Anh",
    "viết hoa/dấu câu thất thường",
)

CLASS_GUIDANCE = {
    "advise": (
        "Mỗi câu phải có một ca cụ thể của chính người nói, không hỏi giùm người khác. "
        "Đa dạng tuổi, loại da, vị trí, loại mụn, thời gian, sản phẩm đang dùng và "
        "câu hỏi xử lý. Không bắt buộc đủ mọi field."
    ),
    "knowledge": (
        "Mỗi câu chỉ hỏi kiến thức chung về mụn, chăm sóc da mụn, hoạt chất, cơ chế, "
        "so sánh, nguyên nhân hoặc an toàn. Không được kể một ca cá nhân cụ thể."
    ),
    "clarify": (
        "Mỗi câu phải liên quan lỏng tới da/mụn hoặc nhu cầu được giúp nhưng thật sự "
        "mơ hồ/thiếu ngữ cảnh, để câu trả lời đúng là hỏi mở làm rõ. Tránh biến thành "
        "câu kiến thức hoàn chỉnh hay ca đủ dữ kiện để tư vấn."
    ),
}

OOS_TOPICS = (
    "nấu ăn và công thức món ăn",
    "thời tiết và kế hoạch đi chơi",
    "chính trị hoặc bầu cử",
    "bóng đá và thể thao",
    "lập trình hoặc sửa lỗi máy tính",
    "toán học",
    "du lịch và đặt vé",
    "phim, âm nhạc, trò chơi",
    "tài chính và đầu tư",
    "chuyện phiếm/giao tiếp không liên quan da",
)


class BudgetExceeded(RuntimeError):
    """Raised before a request that could cross the configured budget."""


@dataclass
class CostBucket:
    requests: int = 0
    prompt_tokens: int = 0
    cached_prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class CostTracker:
    budget_usd: float
    total_usd: float = 0.0
    by_purpose: dict[str, CostBucket] = field(default_factory=dict)

    def reserve(
        self,
        *,
        model: str,
        approximate_prompt_tokens: int,
        max_completion_tokens: int,
    ) -> None:
        pricing = _pricing(model)
        worst_case = (
            approximate_prompt_tokens * pricing["input"]
            + max_completion_tokens * pricing["output"]
        ) / 1_000_000
        if self.total_usd + worst_case > self.budget_usd:
            raise BudgetExceeded(
                f"budget ${self.budget_usd:.4f} would be exceeded "
                f"(spent=${self.total_usd:.4f}, reserved_call=${worst_case:.4f})"
            )

    def add(self, *, model: str, purpose: str, usage: Any) -> float:
        pricing = _pricing(model)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
        cached_tokens = max(0, min(cached_tokens, prompt_tokens))
        uncached_tokens = prompt_tokens - cached_tokens
        cost = (
            uncached_tokens * pricing["input"]
            + cached_tokens * pricing["cached_input"]
            + completion_tokens * pricing["output"]
        ) / 1_000_000
        bucket = self.by_purpose.setdefault(purpose, CostBucket())
        bucket.requests += 1
        bucket.prompt_tokens += prompt_tokens
        bucket.cached_prompt_tokens += cached_tokens
        bucket.completion_tokens += completion_tokens
        bucket.cost_usd += cost
        self.total_usd += cost
        return cost


def _pricing(model: str) -> dict[str, float]:
    if model in MODEL_PRICING_PER_MILLION:
        return MODEL_PRICING_PER_MILLION[model]
    for prefix, pricing in MODEL_PRICING_PER_MILLION.items():
        if model.startswith(prefix):
            return pricing
    raise ValueError(
        f"No pricing configured for {model!r}; add explicit per-million rates "
        "before using budget enforcement."
    )


def _env_value(key: str) -> str:
    value = os.environ.get(key, "")
    if value:
        return value
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip().strip("\"'")
    return ""


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower())
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    normalized = normalized.replace("đ", "d")
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: row must be an object")
        rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _extract_items(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _call_json(
    client: OpenAI,
    tracker: CostTracker,
    *,
    model: str,
    purpose: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    tracker.reserve(
        model=model,
        approximate_prompt_tokens=max(1, (len(system) + len(user)) // 3),
        max_completion_tokens=max_tokens,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    call_cost = tracker.add(
        model=model,
        purpose=purpose,
        usage=response.usage,
    )
    print(
        f"[{purpose}] prompt={response.usage.prompt_tokens} "
        f"completion={response.usage.completion_tokens} "
        f"call=${call_cost:.6f} total=${tracker.total_usd:.6f}",
        flush=True,
    )
    content = response.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{purpose}: model returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{purpose}: model response root must be an object")
    return data


def _base_rows(
    golden_rows: list[dict[str, Any]],
    rng: random.Random,
    *,
    near_duplicate_threshold: float,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    eligible = [
        row
        for row in golden_rows
        if row.get("query_subject") != "other" and row.get("intent") in INTENTS
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        grouped[str(row["intent"])].append(row)

    selected: dict[str, list[dict[str, str]]] = {label: [] for label in INTENTS}
    detail: dict[str, Any] = {}
    for label in INTENTS:
        reliable = [row for row in grouped[label] if row.get("reliable") is True]
        unreliable = [row for row in grouped[label] if row.get("reliable") is not True]
        rng.shuffle(reliable)
        rng.shuffle(unreliable)
        chosen = reliable[: TARGETS[label]]
        # The handoff allows unreliable rows only where they are needed to make
        # the sparse clarify seed less tiny.
        unreliable_kept = 0
        if label == "clarify" and len(chosen) < TARGETS[label]:
            needed = TARGETS[label] - len(chosen)
            supplement = unreliable[:needed]
            chosen.extend(supplement)
            unreliable_kept = len(supplement)
        selected_rows: list[dict[str, str]] = []
        selected_normalized: list[str] = []
        seed_duplicates_removed = 0
        for row in chosen:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            duplicate, _, _ = _is_near_duplicate(
                text,
                selected_normalized,
                threshold=near_duplicate_threshold,
            )
            if duplicate:
                seed_duplicates_removed += 1
                continue
            selected_rows.append({"text": text, "intent": label})
            selected_normalized.append(_normalize_text(text))
        selected[label] = selected_rows
        detail[label] = {
            "eligible": len(grouped[label]),
            "reliable": len(reliable),
            "unreliable": len(unreliable),
            "selected": len(selected[label]),
            "seed_duplicates_removed": seed_duplicates_removed,
            "unreliable_kept": unreliable_kept,
        }
    return selected, detail


def _is_near_duplicate(
    text: str,
    accepted_normalized: list[str],
    *,
    threshold: float,
) -> tuple[bool, int | None, float]:
    candidate = _normalize_text(text)
    if not candidate:
        return True, None, 100.0
    for index, existing in enumerate(accepted_normalized):
        if candidate == existing:
            return True, index, 100.0
        # Length filtering avoids comparing obviously unrelated long/short rows.
        longer = max(len(candidate), len(existing))
        if longer and abs(len(candidate) - len(existing)) / longer > 0.45:
            continue
        similarity = float(ratio(candidate, existing))
        if similarity >= threshold:
            return True, index, similarity
    return False, None, 0.0


def _generation_prompt(label: str, count: int, rng: random.Random) -> str:
    styles = rng.sample(STYLE_AXES, k=min(6, len(STYLE_AXES)))
    return f"""Tạo đúng {count} tin nhắn người dùng tiếng Việt cho intent={label}.

{INTENT_DEFINITIONS}

Yêu cầu riêng của lớp:
{CLASS_GUIDANCE[label]}

Phải phủ xen kẽ các phong cách: {json.dumps(styles, ensure_ascii=False)}.
Mỗi câu có ý tưởng và cách diễn đạt khác nhau. Không đánh số trong text, không
thêm nhãn, không giải thích, không tạo nội dung ngoài phạm vi da mụn.

Trả đúng JSON object:
{{"items":[{{"text":"..."}}]}}
"""


def _judge_prompt(label: str, candidates: list[dict[str, Any]]) -> str:
    indexed = [
        {"id": index, "text": str(item["text"])}
        for index, item in enumerate(candidates)
    ]
    return f"""Đánh giá các mẫu mới được sinh cho target intent={label}.

{INTENT_DEFINITIONS}

Với từng id:
- predicted_intent phải là advise/knowledge/clarify/oos.
- in_scope=false nếu hoàn toàn ngoài phạm vi da mụn.
- duplicate_of là id trước đó trong chính batch nếu hai câu gần như cùng một ý
  và cách diễn đạt; nếu không thì null.
- keep=true CHỈ khi predicted_intent đúng target, in_scope=true, text tự nhiên,
  và duplicate_of=null.

INPUT:
{json.dumps(indexed, ensure_ascii=False)}

Trả đúng JSON object:
{{"items":[{{"id":0,"predicted_intent":"{label}","in_scope":true,
"duplicate_of":null,"keep":true,"reason":"ngắn gọn"}}]}}
"""


def _generate_and_judge_class(
    client: OpenAI,
    tracker: CostTracker,
    *,
    model: str,
    judge_model: str,
    label: str,
    seed_rows: list[dict[str, str]],
    rng: random.Random,
    batch_size: int,
    near_duplicate_threshold: float,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    accepted = list(seed_rows)
    accepted_normalized = [_normalize_text(row["text"]) for row in accepted]
    generated_accepted = 0
    stats: Counter[str] = Counter()
    rounds = 0

    while len(accepted) < TARGETS[label]:
        rounds += 1
        if rounds > 100:
            raise RuntimeError(f"{label}: generation did not converge after 100 rounds")
        needed = TARGETS[label] - len(accepted)
        request_count = min(batch_size, needed + max(3, needed // 8))
        data = _call_json(
            client,
            tracker,
            model=model,
            purpose=f"generate_{label}",
            system=(
                "Bạn tạo dữ liệu phân loại intent tiếng Việt. Chỉ trả JSON hợp lệ "
                "theo schema người dùng yêu cầu."
            ),
            user=_generation_prompt(label, request_count, rng),
            temperature=1.0,
            max_tokens=max(1200, request_count * 90),
        )
        raw_candidates = _extract_items(data)
        stats["model_candidates"] += len(raw_candidates)
        candidates: list[dict[str, str]] = []
        local_normalized: list[str] = []
        for item in raw_candidates:
            text = str(item.get("text") or "").strip()
            if len(text) < 3:
                stats["invalid_text"] += 1
                continue
            duplicate, _, _ = _is_near_duplicate(
                text,
                [*accepted_normalized, *local_normalized],
                threshold=near_duplicate_threshold,
            )
            if duplicate:
                stats["prejudge_duplicate"] += 1
                continue
            candidates.append({"text": text, "intent": label})
            local_normalized.append(_normalize_text(text))
        if not candidates:
            stats["empty_generation_batches"] += 1
            continue

        judged = _call_json(
            client,
            tracker,
            model=judge_model,
            purpose=f"qc_{label}",
            system=(
                "Bạn là QC độc lập cho dữ liệu intent. Đánh giá bảo thủ, không sửa "
                "text và chỉ trả JSON hợp lệ."
            ),
            user=_judge_prompt(label, candidates),
            temperature=0.0,
            max_tokens=max(1200, len(candidates) * 100),
        )
        judgments = {
            int(item["id"]): item
            for item in _extract_items(judged)
            if isinstance(item.get("id"), int)
        }
        for index, candidate in enumerate(candidates):
            judgment = judgments.get(index)
            if judgment is None:
                stats["judge_missing"] += 1
                continue
            keep = (
                judgment.get("keep") is True
                and judgment.get("in_scope") is True
                and judgment.get("predicted_intent") == label
                and judgment.get("duplicate_of") is None
            )
            if not keep:
                stats["judge_rejected"] += 1
                continue
            duplicate, _, _ = _is_near_duplicate(
                candidate["text"],
                accepted_normalized,
                threshold=near_duplicate_threshold,
            )
            if duplicate:
                stats["postjudge_duplicate"] += 1
                continue
            accepted.append(candidate)
            accepted_normalized.append(_normalize_text(candidate["text"]))
            generated_accepted += 1
            stats["accepted"] += 1
            if len(accepted) >= TARGETS[label]:
                break

    return accepted, {
        "rounds": rounds,
        "seed_rows": len(seed_rows),
        "generated_accepted": generated_accepted,
        **dict(stats),
    }


def _generate_oos(
    client: OpenAI,
    tracker: CostTracker,
    *,
    model: str,
    count: int,
    existing_rows: list[dict[str, str]],
    rng: random.Random,
    batch_size: int,
    near_duplicate_threshold: float,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    accepted = list(existing_rows)
    normalized = [_normalize_text(row["text"]) for row in accepted]
    generated = 0
    attempts = 0
    while generated < count:
        attempts += 1
        if attempts > 50:
            raise RuntimeError("OOS generation did not converge after 50 rounds")
        needed = count - generated
        request_count = min(batch_size, needed + 3)
        topics = rng.sample(OOS_TOPICS, k=min(len(OOS_TOPICS), 8))
        prompt = f"""Tạo đúng {request_count} câu người dùng tiếng Việt RÕ RÀNG ngoài
phạm vi tư vấn da mụn. Xen kẽ chủ đề {json.dumps(topics, ensure_ascii=False)}.
Đa dạng teencode, không dấu, sai chính tả, câu ngắn/dài. Tuyệt đối không nhắc
mụn, da, skincare, thuốc trị mụn hoặc bệnh da.

Trả đúng JSON object:
{{"items":[{{"text":"..."}}]}}
"""
        data = _call_json(
            client,
            tracker,
            model=model,
            purpose="generate_oos",
            system="Bạn tạo tập âm OOS tiếng Việt. Chỉ trả JSON hợp lệ.",
            user=prompt,
            temperature=1.0,
            max_tokens=max(1000, request_count * 75),
        )
        for item in _extract_items(data):
            text = str(item.get("text") or "").strip()
            if len(text) < 3:
                continue
            duplicate, _, _ = _is_near_duplicate(
                text,
                normalized,
                threshold=near_duplicate_threshold,
            )
            if duplicate:
                continue
            accepted.append({"text": text, "intent": "reject"})
            normalized.append(_normalize_text(text))
            generated += 1
            if generated >= count:
                break
    return accepted, {
        "golden_oos": len(existing_rows),
        "generated_oos": generated,
        "total_oos": len(accepted),
        "rounds": attempts,
    }


def _dedupe_all_classes(
    rows_by_class: dict[str, list[dict[str, str]]],
    *,
    threshold: float,
) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, Any]]]:
    """Cross-class final guard against exact/near leakage.

    Generated examples are already refilled to their targets.  A cross-class
    duplicate is therefore a labeling conflict and must abort instead of
    silently changing the requested distribution.
    """
    seen_rows: list[dict[str, str]] = []
    seen_normalized: list[str] = []
    conflicts: list[dict[str, Any]] = []
    result = {label: [] for label in INTENTS}
    for label in INTENTS:
        for row in rows_by_class[label]:
            duplicate, index, similarity = _is_near_duplicate(
                row["text"],
                seen_normalized,
                threshold=threshold,
            )
            if duplicate:
                existing = seen_rows[index] if index is not None else None
                if existing is not None and existing["intent"] != label:
                    conflicts.append(
                        {
                            "text": row["text"],
                            "intent": label,
                            "existing_text": existing["text"],
                            "existing_intent": existing["intent"],
                            "similarity": similarity,
                        }
                    )
                    continue
                # Same-class duplicates should have been caught earlier.
                continue
            result[label].append(row)
            seen_rows.append(row)
            seen_normalized.append(_normalize_text(row["text"]))
    return result, conflicts


def _stratified_split(
    rows_by_class: dict[str, list[dict[str, str]]],
    rng: random.Random,
    *,
    test_fraction: float,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    train: list[dict[str, str]] = []
    test: list[dict[str, str]] = []
    for label in INTENTS:
        rows = list(rows_by_class[label])
        rng.shuffle(rows)
        test_count = int(round(len(rows) * test_fraction))
        test.extend(rows[:test_count])
        train.extend(rows[test_count:])
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _cost_json(
    tracker: CostTracker,
    *,
    prior_spend_usd: float,
) -> dict[str, Any]:
    successful_run_cost = sum(
        bucket.cost_usd for bucket in tracker.by_purpose.values()
    )
    return {
        "budget_usd": tracker.budget_usd,
        "prior_failed_attempt_cost_usd": round(prior_spend_usd, 8),
        "successful_run_cost_usd": round(successful_run_cost, 8),
        "actual_cost_usd": round(tracker.total_usd, 8),
        "by_purpose": {
            purpose: {
                **asdict(bucket),
                "cost_usd": round(bucket.cost_usd, 8),
            }
            for purpose, bucket in sorted(tracker.by_purpose.items())
        },
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    source_path = (ROOT / args.source).resolve()
    out_path = (ROOT / args.output).resolve()
    train_path = (ROOT / args.train_output).resolve()
    test_path = (ROOT / args.test_output).resolve()
    oos_path = (ROOT / args.oos_output).resolve()
    metrics_path = (ROOT / args.metrics_output).resolve()
    golden_rows = _read_jsonl(source_path)
    if len(golden_rows) != 985:
        print(
            f"WARNING: expected 985 source rows, found {len(golden_rows)}",
            file=sys.stderr,
        )

    # DeepSeek nói đúng OpenAI chat-completions schema nên SDK dùng lại được,
    # chỉ đổi base_url. Vẫn chấp nhận OPENAI_API_KEY nếu ai đó còn quota.
    api_key = _env_value("DEEPSEEK_API_KEY")
    base_url = _env_value("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    if not api_key:
        api_key, base_url = _env_value("OPENAI_API_KEY"), None
    if not api_key:
        raise RuntimeError("Thiếu DEEPSEEK_API_KEY (hoặc OPENAI_API_KEY) trong .env")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)
    tracker = CostTracker(
        budget_usd=args.budget_usd,
        total_usd=args.prior_spend_usd,
    )
    rng = random.Random(args.seed)

    base, base_stats = _base_rows(
        golden_rows,
        rng,
        near_duplicate_threshold=args.near_duplicate_threshold,
    )
    rows_by_class: dict[str, list[dict[str, str]]] = {}
    generation_stats: dict[str, Any] = {}
    for label in INTENTS:
        rows, stats = _generate_and_judge_class(
            client,
            tracker,
            model=args.model,
            judge_model=args.judge_model,
            label=label,
            seed_rows=base[label],
            rng=rng,
            batch_size=args.batch_size,
            near_duplicate_threshold=args.near_duplicate_threshold,
        )
        rows_by_class[label] = rows
        generation_stats[label] = stats
        print(f"[{label}] final={len(rows)} stats={stats}", flush=True)

    deduped, cross_class_conflicts = _dedupe_all_classes(
        rows_by_class,
        threshold=args.near_duplicate_threshold,
    )
    final_counts = {label: len(deduped[label]) for label in INTENTS}
    if cross_class_conflicts or final_counts != TARGETS:
        raise RuntimeError(
            "Final cross-class dedupe changed targets; inspect conflicts and "
            f"regenerate. counts={final_counts}, conflicts={cross_class_conflicts[:5]}"
        )
    rows_by_class = deduped

    original_oos = [
        {"text": str(row["text"]).strip(), "intent": "reject"}
        for row in golden_rows
        if row.get("intent") == "reject" and str(row.get("text") or "").strip()
    ]
    oos_rows, oos_stats = _generate_oos(
        client,
        tracker,
        model=args.model,
        count=args.generate_oos,
        existing_rows=original_oos,
        rng=rng,
        batch_size=args.batch_size,
        near_duplicate_threshold=args.near_duplicate_threshold,
    )

    full_rows = [
        row
        for label in INTENTS
        for row in rows_by_class[label]
    ]
    rng.shuffle(full_rows)
    train_rows, test_rows = _stratified_split(
        rows_by_class,
        rng,
        test_fraction=args.test_fraction,
    )
    _write_jsonl(out_path, full_rows)
    _write_jsonl(train_path, train_rows)
    _write_jsonl(test_path, test_rows)
    _write_jsonl(oos_path, oos_rows)

    metrics = {
        "schema_version": 1,
        "created_at_unix": int(time.time()),
        "seed": args.seed,
        "source": str(source_path.relative_to(ROOT)),
        "model": args.model,
        "judge_model": args.judge_model,
        "near_duplicate_threshold": args.near_duplicate_threshold,
        "base": base_stats,
        "generation_qc": generation_stats,
        "oos": oos_stats,
        "counts": {
            "full": Counter(row["intent"] for row in full_rows),
            "train": Counter(row["intent"] for row in train_rows),
            "test": Counter(row["intent"] for row in test_rows),
            "oos": len(oos_rows),
        },
        "cost": _cost_json(
            tracker,
            prior_spend_usd=args.prior_spend_usd,
        ),
        "artifacts": {
            str(path.relative_to(ROOT)): {
                "rows": len(rows),
                "sha256": _sha256_file(path),
            }
            for path, rows in (
                (out_path, full_rows),
                (train_path, train_rows),
                (test_path, test_rows),
                (oos_path, oos_rows),
            )
        },
        "cross_class_conflicts": cross_class_conflicts,
    }
    # Counter is a dict subclass but normalise it for stable JSON output.
    metrics["counts"] = {
        key: dict(value) if isinstance(value, Counter) else value
        for key, value in metrics["counts"].items()
    }
    _write_json(metrics_path, metrics)
    print(
        f"DONE full={len(full_rows)} train={len(train_rows)} test={len(test_rows)} "
        f"oos={len(oos_rows)} cost=${tracker.total_usd:.6f}",
        flush=True,
    )
    return metrics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/golden_extraction_gen.jsonl")
    parser.add_argument("--output", default="data/intent_classify.jsonl")
    parser.add_argument(
        "--train-output",
        default="data/intent_classify.train.jsonl",
    )
    parser.add_argument(
        "--test-output",
        default="data/intent_classify.test.jsonl",
    )
    parser.add_argument("--oos-output", default="data/subject_oos_eval.jsonl")
    parser.add_argument(
        "--metrics-output",
        default="data/intent_classify.build_metrics.json",
    )
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--judge-model", default="deepseek-v4-pro")
    parser.add_argument("--budget-usd", type=float, default=1.5)
    parser.add_argument(
        "--prior-spend-usd",
        type=float,
        default=0.0,
        help="API spend from failed attempts; included in the same hard budget.",
    )
    parser.add_argument("--generate-oos", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--test-fraction", type=float, default=0.20)
    parser.add_argument("--near-duplicate-threshold", type=float, default=93.0)
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    if not 0.0 < args.test_fraction < 1.0:
        parser.error("--test-fraction must be between 0 and 1")
    if args.budget_usd <= 0:
        parser.error("--budget-usd must be positive")
    if args.prior_spend_usd < 0 or args.prior_spend_usd >= args.budget_usd:
        parser.error("--prior-spend-usd must be >= 0 and below --budget-usd")
    if args.batch_size < 4:
        parser.error("--batch-size must be at least 4")
    return args


def main() -> None:
    try:
        build(parse_args())
    except (BudgetExceeded, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
