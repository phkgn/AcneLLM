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

PHONG CÁCH assistant_answer — QUAN TRỌNG:
Viết như một người bạn có kiến thức da liễu đang nhắn tin: tự nhiên, gần gũi,
đi thẳng vào ý chính nhưng vẫn giữ an toàn y khoa. Câu đầu tiên phải là câu
trả lời thật, không mở bằng lời chào, không "cảm ơn bạn đã chia sẻ", không
"dựa trên mô tả". Nếu ca nhẹ thì trả lời gọn, có thể hơi đời thường. Nếu ca
nặng thì nghiêm túc hơn, giải thích rõ vì sao cần đi khám, nhưng đừng biến
thành một tờ hướng dẫn thuốc.

Đừng dùng một công thức cho mọi sample. Có câu chỉ cần 2–3 câu là đủ; có câu
cần một đoạn ngắn về routine; chỉ dùng bullet khi thật sự giúp dễ đọc. Lưu ý
an toàn xuất hiện đúng lúc: thuốc kê đơn, thai kỳ/cho con bú, mụn bọc/nang,
sẹo, nhiễm trùng, thất bại điều trị. Những câu low-risk không cần disclaimer
cuối bài.

Ví dụ tone tốt (low-risk):
  "Mụn đầu đen ở mũi thường do lỗ chân lông bị bít — BHA (salicylic acid 1–2%)
   là lựa chọn phù hợp nhất, dùng 2–3 lần/tuần là đủ."

Ví dụ tone tốt (high-risk):
  "Nodule đau và sưng to kiểu này dễ để lại sẹo nếu tự xử lý. Tốt nhất là đi
   khám da liễu sớm — bác sĩ có thể tiêm corticoid nội tổn thương để xẹp nhanh
   hơn và giảm nguy cơ sẹo."

Ví dụ tone tốt (thiếu thông tin):
  "Mình cần biết thêm mụn của bạn là đầu đen, mụn đỏ/mủ hay mụn bọc, nằm ở đâu
   và bị bao lâu rồi. Trước mắt cứ giữ routine thật đơn giản, đừng nặn hay tự
   dùng thuốc kê đơn."

NỘI DUNG:
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


RAW_USER_STYLE_PROFILES: tuple[dict[str, str | int], ...] = (
    {
        "key": "casual_short",
        "weight": 30,
        "description": (
            "casual ngắn, như người dùng chat nhanh. 1–2 câu, có thể thiếu một vài "
            "dữ kiện không quan trọng. Không mở đầu bằng lời chào."
        ),
        "examples": (
            "mụn ẩn ở trán mãi ko hết, da dầu, dùng bha bị rát thì nghỉ luôn hả | "
            "cằm cứ lên mụn đỏ trước kỳ kinh, xử lý sao cho đỡ vậy"
        ),
    },
    {
        "key": "semi_formal",
        "weight": 30,
        "description": (
            "semi-formal tự nhiên kiểu em/mình hỏi tư vấn. Có thể đủ tuổi, loại da "
            "hoặc sản phẩm đang dùng, nhưng không viết như bệnh án."
        ),
        "examples": (
            "em 22 tuổi, da dầu, mụn đầu đen ở mũi nhiều quá, nên thêm gì vào routine ạ | "
            "mình đang dùng sữa rửa mặt với dưỡng ẩm thôi mà mụn cằm cứ lên hoài"
        ),
    },
    {
        "key": "fragment_missing_info",
        "weight": 20,
        "description": (
            "câu cụt / thiếu thông tin, đúng kiểu user chưa biết cần kể gì. "
            "normalized_case phải đánh dấu missing_info tương ứng."
        ),
        "examples": (
            "mặt tự nhiên nổi mụn quá giờ làm sao | "
            "mụn lưng nhiều, có cần bôi gì không"
        ),
    },
    {
        "key": "light_typo_no_diacritics",
        "weight": 10,
        "description": (
            "casual có typo nhẹ hoặc không dấu một phần, vẫn dễ đọc. Không lạm dụng "
            "teen code; chỉ dùng vài từ như ko, dc, mn, bi, mun."
        ),
        "examples": (
            "mun an tren tran hoai ko het, da dau nua, dung gi dc | "
            "bha moi boi da rat voi bong nhẹ, co nen nghi ko"
        ),
    },
    {
        "key": "formal_doctor",
        "weight": 10,
        "description": (
            "formal vừa phải kiểu hỏi bác sĩ. Chỉ dùng style này khi được chỉ định; "
            "ngắn gọn, không lặp nguyên mẫu 'Chào bác sĩ, em năm nay... da em thuộc loại...'."
        ),
        "examples": (
            "Bác sĩ cho em hỏi mụn bọc ở cằm đau nhiều thì có nên đi khám sớm không ạ"
        ),
    },
)


def _pick_raw_user_style() -> dict[str, str | int]:
    total = sum(int(profile["weight"]) for profile in RAW_USER_STYLE_PROFILES)
    roll = random.randint(1, total)
    upto = 0
    for profile in RAW_USER_STYLE_PROFILES:
        upto += int(profile["weight"])
        if roll <= upto:
            return profile
    return RAW_USER_STYLE_PROFILES[0]


def _raw_user_message_too_formal(text: str) -> bool:
    normalized = " ".join((text or "").lower().split())
    formal_openers = (
        "chào bác sĩ",
        "em chào bác sĩ",
        "xin chào bác sĩ",
        "kính chào bác sĩ",
    )
    if normalized.startswith(formal_openers):
        return True
    textbook_markers = (
        "em năm nay",
        "da em thuộc loại",
        "em muốn hỏi",
        "em xin hỏi",
    )
    return sum(1 for marker in textbook_markers if marker in normalized) >= 2


# Mô tả từng case_type để guide DeepSeek khi được chỉ định target
CASE_TYPE_DESCRIPTIONS: dict[str, str] = {
    "mild_comedonal": (
        "Người dùng bị mụn nhẹ: mụn đầu đen, đầu trắng, mụn cám, mụn ẩn. "
        "Chưa hoặc ít viêm. Gợi ý OTC phù hợp (BHA, niacinamide, benzoyl peroxide thấp), "
        "routine đơn giản, không kê đơn."
    ),
    "moderate_inflammatory": (
        "Người dùng bị mụn viêm mức độ vừa: papule, pustule, một số nodule nhỏ. "
        "Đã thử OTC nhưng chưa đủ. Hướng dẫn thêm options OTC/non-Rx, "
        "đặt boundary với kháng sinh/retinoid kê đơn, gợi ý đi khám nếu không cải thiện."
    ),
    "severe_nodular_scarring": (
        "Người dùng bị mụn nặng: nodule, cyst, mụn bọc sâu đau, nguy cơ sẹo rõ. "
        "Phải khuyên đi khám bác sĩ da liễu sớm, không tự điều trị thuốc mạnh, "
        "không hướng dẫn liều Rx."
    ),
    "skincare_routine": (
        "Người dùng hỏi về routine chăm sóc da, thứ tự bước, cách layer sản phẩm, "
        "chọn sản phẩm OTC (cleanser, moisturizer, sunscreen, serum actives nhẹ). "
        "Tư vấn routine phù hợp loại da, không kê đơn thuốc."
    ),
    "product_qna": (
        "Người dùng hỏi về một sản phẩm/hoạt chất cụ thể: công dụng, cách dùng, "
        "kết hợp với sản phẩm khác, tần suất, nồng độ OTC an toàn. "
        "Ví dụ: retinol OTC, niacinamide, azelaic acid, BHA, vitamin C, SPF."
    ),
    "when_to_see_doctor": (
        "Người dùng mô tả triệu chứng cần đánh giá y khoa: mụn kéo dài không đỡ, "
        "sẹo lan rộng, nhiễm trùng, distress tâm lý, mụn liên quan nội tiết. "
        "Khuyên đi khám rõ ràng, giải thích lý do."
    ),
    "insufficient_info": (
        "Người dùng mô tả quá mơ hồ, thiếu thông tin về loại mụn, vị trí, thời gian. "
        "Model hỏi thêm thông tin cụ thể, chỉ đưa hướng an toàn chung, không đoán."
    ),
    "antibiotic_or_isotretinoin_boundary": (
        "Người dùng hỏi về kháng sinh uống, isotretinoin, retinoid kê đơn. "
        "Đặt boundary rõ ràng: không kê đơn, không liều, giải thích cần bác sĩ, "
        "antimicrobial stewardship."
    ),
    "pregnancy_breastfeeding_safety": (
        "Người dùng đang mang thai hoặc cho con bú, hỏi về thuốc/sản phẩm trị mụn. "
        "Không gợi ý retinoid, isotretinoin, tetracycline; khuyên hỏi bác sĩ."
    ),
    "skincare_irritation": (
        "Người dùng có kích ứng da do dùng quá nhiều actives, peel tại nhà, kem trộn. "
        "Hướng dẫn đơn giản hoá routine, phục hồi hàng rào da, đi khám nếu nặng."
    ),
    "teen_acne": (
        "Người dùng là thanh thiếu niên (12–19 tuổi) bị mụn tuổi dậy thì. "
        "Tư vấn phù hợp lứa tuổi: gentle routine, OTC an toàn, không kê đơn Rx mạnh, "
        "đề cập yếu tố hormone, diet, stress tuổi teen."
    ),
    "diet_lifestyle": (
        "Người dùng hỏi về ảnh hưởng của chế độ ăn, thói quen sinh hoạt đến mụn: "
        "dairy, đường, high-glycemic, stress, ngủ đủ giấc, tập thể dục. "
        "Cung cấp bằng chứng dựa trên guideline, không phóng đại, không chẩn đoán."
    ),
    "post_acne_care": (
        "Người dùng đã qua giai đoạn mụn nặng, đang lo về sẹo rỗ, thâm PIH, "
        "phục hồi da sau điều trị. Gợi ý OTC cho PIH (niacinamide, azelaic acid, SPF), "
        "giải thích sẹo rỗ cần can thiệp y khoa, không hứa hẹn quá."
    ),
}

# Mapping từng case_type sang nhóm để chọn prompt phù hợp
_CLINICAL_CASE_TYPES = frozenset(CASE_TYPE_DESCRIPTIONS.keys())

_CASE_TYPE_ALIASES = {
    "skincare_routine_product": "skincare_routine",
    "product_recommendation": "product_qna",
    "new_domain_teen": "teen_acne",
    "new_domain_diet": "diet_lifestyle",
    "new_domain_post_acne": "post_acne_care",
    "post_acne": "post_acne_care",
    "diet": "diet_lifestyle",
    "teen": "teen_acne",
}


def normalize_case_type(case_type: Any) -> str:
    """Normalize case_type aliases produced by older prompts or models."""
    raw = str(case_type or "general").strip() or "general"
    return _CASE_TYPE_ALIASES.get(raw, raw)


USER_TEMPLATE = """Source chunk (nguồn: {source_name}, trust_level: {trust_level}, tags: {tags}):
\"\"\"
{chunk_text}
\"\"\"

Hãy tạo CHÍNH XÁC {n} clinical chat-response sample tiếng Việt.{target_instruction}

RAW_USER_MESSAGE STYLE TARGET:
- Style bắt buộc cho lần generate này: {raw_user_style_key}
- Mô tả: {raw_user_style_description}
- Ví dụ cùng style: {raw_user_style_examples}

Luật riêng cho raw_user_message:
- Viết như user thật đang chat với app, không phải bệnh án phòng khám.
- Tối đa khoảng 10% sample mới được formal kiểu "Chào bác sĩ"; nếu style không
  phải formal_doctor thì KHÔNG dùng opener "Chào bác sĩ", "Em chào bác sĩ",
  "Em năm nay...", "Da em thuộc loại...", "Em muốn hỏi..." theo khuôn.
- Không phải sample nào cũng cần đủ tuổi, loại da, thời gian bị mụn, treatment
  history. Nếu user nói thiếu, normalized_case.missing_info phải phản ánh đúng.
- Được dùng câu ngắn, hỏi dồn, lo lắng, thiếu dấu/typo nhẹ khi style yêu cầu.
- Với thai kỳ/cho con bú, thuốc kê đơn, isotretinoin/kháng sinh, mụn bọc/nang,
  sẹo hoặc nhiễm trùng: raw_user_message vẫn phải chứa đủ tín hiệu an toàn quan
  trọng để assistant_answer xử lý đúng.

Ví dụ raw_user_message tốt:
- "mụn ẩn ở trán mãi ko hết, da dầu, dùng bha bị rát thì nghỉ luôn hả"
- "mình đang bầu 3 tháng, nổi mụn đỏ ở cằm, có bôi được gì an toàn không"
- "mụn lưng nhiều sau khi tập gym, áo bó với ra mồ hôi suốt, làm sao đỡ"

Ví dụ raw_user_message KHÔNG tốt vì quá formal/lặp:
- "Chào bác sĩ, em năm nay 23 tuổi, da em thuộc loại da dầu..."
- "Em muốn hỏi là với tình trạng của em thì em nên dùng sản phẩm gì ạ?"

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

Danh sách case_type hợp lệ:
{valid_case_types}

Random seed: {seed}
"""


def _build_target_instruction(target_case_type: str | None) -> str:
    """Tạo đoạn hướng dẫn case_type chèn vào USER_TEMPLATE."""
    if not target_case_type or target_case_type not in CASE_TYPE_DESCRIPTIONS:
        # Không có target → để DeepSeek tự chọn, liệt kê toàn bộ case types
        return (
            "\n\nCase mix nên đa dạng, chọn case_type phù hợp với nội dung chunk từ danh sách sau."
        )
    desc = CASE_TYPE_DESCRIPTIONS[target_case_type]
    return (
        f"\n\nYÊU CẦU BẮT BUỘC: sample PHẢI có case_type = \"{target_case_type}\".\n"
        f"Mô tả case_type này: {desc}\n"
        f"Tạo tình huống phù hợp với nội dung chunk nhưng bắt buộc thuộc case_type trên."
    )


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

    case_type = normalize_case_type(item.get("case_type"))

    return {
        "raw_user_message": raw_user_message,
        "normalized_case": normalized_case.model_dump(),
        "guideline_context": guideline_context,
        "assistant_answer": answer,
        "case_type": case_type,
        "severity": severity,
        "safety_flags": safety_flags,
        "guideline_refs": _coerce_refs(item.get("guideline_refs")),
        "confidence": confidence,
    }


async def generate_cases_for_chunk(
    client: AsyncOpenAI,
    cfg: Config,
    chunk: dict,
    target_case_type: str | None = None,
    n_cases: int | None = None,
) -> list[dict]:
    """Call DeepSeek và trả về validated clinical chat-response items.

    Args:
        target_case_type: Nếu set, guide DeepSeek generate sample thuộc
            đúng case_type này (dùng bởi budget-aware dispatcher trong main.py).
            Nếu None, DeepSeek tự chọn case_type đa dạng.
    """
    chunk_text = _truncate(chunk.get("text") or "")
    target_case_type = normalize_case_type(target_case_type) if target_case_type else None
    target_instruction = _build_target_instruction(target_case_type)
    requested_n = max(1, n_cases or cfg.cases_per_chunk)
    raw_user_style = _pick_raw_user_style()
    user_prompt = USER_TEMPLATE.format(
        source_name=chunk.get("source_name", "unknown"),
        trust_level=chunk.get("trust_level", "unknown"),
        tags=", ".join(chunk.get("tags") or []),
        chunk_text=chunk_text,
        n=requested_n,
        target_instruction=target_instruction,
        raw_user_style_key=raw_user_style["key"],
        raw_user_style_description=raw_user_style["description"],
        raw_user_style_examples=raw_user_style["examples"],
        valid_case_types=", ".join(sorted(_CLINICAL_CASE_TYPES)),
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
                    if target_case_type and validated["case_type"] != target_case_type:
                        logger.debug(
                            "Dropped generated item with case_type=%s; expected=%s",
                            validated["case_type"], target_case_type,
                        )
                        continue
                    if (
                        raw_user_style["key"] != "formal_doctor"
                        and _raw_user_message_too_formal(validated["raw_user_message"])
                    ):
                        logger.debug(
                            "Dropped over-formal raw_user_message for style=%s: %s",
                            raw_user_style["key"], validated["raw_user_message"],
                        )
                        continue
                    cleaned.append(validated)
                    if len(cleaned) >= requested_n:
                        break
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
