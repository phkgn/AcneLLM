"""Generate clinical chat-response samples from source chunks using DeepSeek.

Output of `generate_cases_for_chunk` is a list of dict items, each shaped:

    {
        "raw_user_message": "...",
        "normalized_case": {... NormalizedAcneCase ...},
        "guideline_context": "...",
        "assistant_answer": "...",
        "case_type": "...",
        "severity": "mild|moderate|severe|unknown",
        "safety_flags": [...],
        "guideline_refs": ["AAD_2024", "NICE_NG198"],
        "confidence": "high|medium|low"
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from acne_llm.schemas.clinical import NormalizedAcneCase

from .config import Config

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Bạn là chuyên gia tạo dữ liệu fine-tuning cho AcneLLM.

Nhiệm vụ: từ một đoạn tài liệu y khoa / guideline về mụn, tạo dữ liệu huấn luyện
cho FINAL CHATBOT RESPONSE — không phải Q&A theo tài liệu.

Pipeline mỗi sample:
1. Tạo một mô tả bệnh nhân tự nhiên bằng tiếng Việt (raw_user_message).
2. Chuẩn hóa mô tả đó thành normalized_case đúng schema NormalizedAcneCase.
3. Tạo guideline_context ngắn, ưu tiên tinh thần AAD 2024 + NICE NG198.
4. Viết assistant_answer như chatbot AcneLLM đang trả lời người dùng thật.

Nguyên tắc bắt buộc:
- KHÔNG viết kiểu "Tài liệu khuyến cáo..." hoặc "Theo đoạn tài liệu này...".
- KHÔNG kê đơn, KHÔNG đưa liều / nồng độ / tần suất thuốc kê đơn.
- Isotretinoin, kháng sinh uống, retinoid kê đơn, spironolactone: chỉ nói ở mức
  boundary cần bác sĩ da liễu, không tự dùng.
- Kháng sinh không được gợi ý đơn trị; nếu nhắc tới phải gắn với bác sĩ và
  antimicrobial stewardship / guideline boundary.
- Mang thai / cho con bú / dự định mang thai: KHÔNG gợi ý retinoid, isotretinoin,
  tetracycline / doxycycline / minocycline; khuyên hỏi bác sĩ.
- Mụn nặng, nodule / cyst, mụn bọc đau, sẹo / nguy cơ sẹo, lan nhanh, nhiễm trùng,
  thất bại điều trị hoặc distress tâm lý: phải khuyên gặp bác sĩ da liễu.
- Thiếu dữ kiện: severity = unknown, hỏi thêm dữ kiện và chỉ đưa hướng an toàn chung.
- AAD 2024 + NICE NG198 là guideline chính. Chunk nguồn khác chỉ bổ trợ.
"""


USER_TEMPLATE = """Source chunk (nguồn: {source_name}, trust_level: {trust_level}, tags: {tags}):
\"\"\"
{chunk_text}
\"\"\"

Hãy tạo CHÍNH XÁC {n} clinical chat-response samples tiếng Việt.

Case mix nên đa dạng tùy nội dung chunk:
- mild_comedonal
- moderate_inflammatory
- severe_nodular_scarring
- insufficient_info
- pregnancy_breastfeeding_safety
- antibiotic_or_isotretinoin_boundary
- skincare_irritation
- self_procedure_refusal
- when_to_see_doctor

Trả về DUY NHẤT JSON object, không markdown:

{{
  "items": [
    {{
      "raw_user_message": "<mô tả/câu hỏi tự nhiên của bệnh nhân>",
      "normalized_case": {{
        "demographics": {{
          "age": null,
          "sex": "unknown",
          "skin_type": "unknown",
          "is_pregnant": false,
          "is_breastfeeding": false
        }},
        "lesion_types": [],
        "distribution": [],
        "inflammation_level": "unknown",
        "scarring_signs": [],
        "medication_history": [],
        "hormonal_factors": [],
        "skincare_products": [],
        "treatment_goals": [],
        "red_flags": [],
        "missing_info": []
      }},
      "guideline_context": "<ngữ cảnh guideline ngắn, ưu tiên AAD 2024 + NICE NG198>",
      "assistant_answer": "<câu trả lời cuối của chatbot, tự nhiên, an toàn, không kê đơn>",
      "case_type": "<một case type trong danh sách trên>",
      "severity": "mild|moderate|severe|unknown",
      "safety_flags": [],
      "guideline_refs": ["AAD_2024", "NICE_NG198"],
      "confidence": "high|medium|low"
    }}
  ]
}}

Enum bắt buộc:
- lesion_types: comedone, whitehead, blackhead, closed_comedone, papule, pustule,
  nodule, cyst, scar, post_inflammatory_hyperpigmentation, other.
- distribution: forehead, cheeks, chin, jawline, nose, around_mouth, back, chest,
  shoulders, neck, t_zone, other.
- inflammation_level: none, mild, moderate, severe, unknown.

Random seed: {seed}
"""


def _truncate(text: str, max_chars: int = 3500) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " ..."


def _coerce_refs(refs: Any) -> list[str]:
    values = refs if isinstance(refs, list) else []
    out: list[str] = []
    for ref in values:
        value = str(ref).strip()
        if value:
            out.append(value)
    if "AAD_2024" not in out:
        out.append("AAD_2024")
    if "NICE_NG198" not in out:
        out.append("NICE_NG198")
    return list(dict.fromkeys(out))


def _validate_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a single DeepSeek-generated item. Returns None if invalid."""
    raw_user_message = str(item.get("raw_user_message") or "").strip()
    answer = str(item.get("assistant_answer") or "").strip()
    guideline_context = str(item.get("guideline_context") or "").strip()
    if not raw_user_message or not answer or not guideline_context:
        return None

    try:
        normalized_case = NormalizedAcneCase.model_validate(
            item.get("normalized_case") or {}
        )
    except ValidationError as exc:
        logger.debug("Generated item has invalid normalized_case: %s", exc)
        return None

    severity = str(item.get("severity") or "unknown").strip().lower()
    if severity not in ("mild", "moderate", "severe", "unknown"):
        severity = "unknown"

    confidence = str(item.get("confidence") or "medium").strip().lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    safety_flags_raw = item.get("safety_flags")
    safety_flags = [
        str(x).strip()
        for x in (safety_flags_raw if isinstance(safety_flags_raw, list) else [])
        if str(x).strip()
    ]

    return {
        "raw_user_message": raw_user_message,
        "normalized_case": normalized_case.model_dump(),
        "guideline_context": guideline_context,
        "assistant_answer": answer,
        "case_type": str(item.get("case_type") or "general").strip() or "general",
        "severity": severity,
        "safety_flags": safety_flags,
        "guideline_refs": _coerce_refs(item.get("guideline_refs")),
        "confidence": confidence,
    }


async def generate_cases_for_chunk(
    client: AsyncOpenAI,
    cfg: Config,
    chunk: dict,
) -> list[dict]:
    """Call DeepSeek and return validated clinical chat-response items."""
    chunk_text = _truncate(chunk.get("text") or "")
    user_prompt = USER_TEMPLATE.format(
        source_name=chunk.get("source_name", "unknown"),
        trust_level=chunk.get("trust_level", "unknown"),
        tags=", ".join(chunk.get("tags") or []),
        chunk_text=chunk_text,
        n=cfg.cases_per_chunk,
        seed=random.randint(1, 10**9),
    )

    last_err: Exception | None = None
    for attempt in range(1, cfg.deepseek_max_retries + 1):
        try:
            resp = await client.chat.completions.create(
                model=cfg.deepseek_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=cfg.deepseek_temperature,
                response_format={"type": "json_object"},
                timeout=cfg.deepseek_timeout_s,
            )
            content = resp.choices[0].message.content or ""
            data = json.loads(content)
            items = data.get("items")
            if not isinstance(items, list):
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
            if not isinstance(items, list) or not items:
                raise ValueError("No 'items' list in DeepSeek response.")

            cleaned: list[dict] = []
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                validated = _validate_item(raw)
                if validated is not None:
                    cleaned.append(validated)
            if not cleaned:
                raise ValueError("No items survived validation.")
            return cleaned

        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "429" in msg or "rate limit" in msg or "too many" in msg:
                sleep_s = 20.0 + 5.0 * attempt + random.uniform(0, 5.0)
            else:
                sleep_s = min(2.0 ** attempt, 30.0) + random.uniform(0, 1.0)
            logger.warning(
                "DeepSeek attempt %d/%d failed for chunk %s: %s — sleeping %.1fs",
                attempt, cfg.deepseek_max_retries, chunk.get("chunk_id"),
                type(e).__name__, sleep_s,
            )
            await asyncio.sleep(sleep_s)

    logger.error(
        "DeepSeek gave up on chunk %s after %d attempts: %r",
        chunk.get("chunk_id"), cfg.deepseek_max_retries, last_err,
    )
    return []


def make_deepseek_client(cfg: Config) -> AsyncOpenAI:
    if not cfg.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")
    return AsyncOpenAI(api_key=cfg.deepseek_api_key, base_url=cfg.deepseek_base_url)
