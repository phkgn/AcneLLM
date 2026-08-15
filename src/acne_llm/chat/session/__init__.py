"""Bo nho hoi thoai nhieu luot.

Package nay duoc tach tu mot file 714 dong o Phase 7. Bon nhom ben trong thay
doi vi bon ly do khac nhau, nen chung o bon file khac nhau:

    models.py   kieu du lieu + hang so        gan nhu khong doi
    memory.py   SessionStore in-memory        doi khi vong doi phien doi
    view.py     chon + render cho prompt      doi khi prompt doi
    (con lai o day, se tach tiep)             fold du kien qua cac luot

Moi ten cu van export lai o day, nen khong cho goi nao phai sua import.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from ...schemas import AcneClinicalInput, UserContext, UserInput
from .models import (
    HISTORY_CHAR_BUDGET,
    HISTORY_WINDOW_TURNS,
    MAX_HISTORY_TURNS,
    SESSION_SCHEMA_VERSION,
    SESSION_TTL,
    ConversationTurn,
    NormalizedSnapshot,
    Session,
)
from .fold import _mentions_stop
from .memory import SessionStore, get_session_store
from .view import (
    CONTEXT_FIELD_THRESHOLD,
    build_confirmed_profile,
    format_history_block,
    select_relevant_history,
)

__all__ = [
    "HISTORY_CHAR_BUDGET", "HISTORY_WINDOW_TURNS", "MAX_HISTORY_TURNS",
    "SESSION_SCHEMA_VERSION", "SESSION_TTL", "CONTEXT_FIELD_THRESHOLD",
    "ConversationTurn", "NormalizedSnapshot", "Session",
    "SessionStore", "get_session_store",
    "select_relevant_history", "build_confirmed_profile",
    "snapshot_from_user", "fold_history_facts", "format_history_block",
]






# ── Normalized memory helpers ────────────────────────────────────────────────

def _dedupe_values(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def snapshot_from_user(user: UserInput, clean_text: str = "") -> NormalizedSnapshot:
    """Create a compact, serializable-ish snapshot from a normalized UserInput."""
    context = user.context.model_dump(exclude_none=True)
    clinical = user.clinical.model_dump() if user.clinical is not None else {}
    context["current_products"] = [
        value for value in context.get("current_products", [])
        if not _mentions_stop(clean_text, value)
    ]
    context["medications"] = [
        value for value in context.get("medications", [])
        if not _mentions_stop(clean_text, value)
    ]
    if clinical:
        clinical["medication_history"] = [
            value for value in clinical.get("medication_history", [])
            if not _mentions_stop(clean_text, value)
        ]
        clinical["skincare_products"] = [
            value for value in clinical.get("skincare_products", [])
            if not _mentions_stop(clean_text, value)
        ]
    return NormalizedSnapshot(context=context, clinical=clinical, clean_text=clean_text)




_SEVERITY_ORDER = {"unknown": 0, "none": 0, "mild": 1, "moderate": 2, "severe": 3}


def _max_severity(a: str | None, b: str | None) -> str | None:
    """Trả về mức severity cao hơn giữa a và b."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a if _SEVERITY_ORDER.get(a, 0) >= _SEVERITY_ORDER.get(b, 0) else b


def fold_history_facts(
    current: UserInput,
    history: list[ConversationTurn],
) -> UserInput:
    """Fold prior normalized snapshots into the current user.

    Strategy:
    - stable identity facts: first write wins (age, sex, skin_type);
    - pregnancy/breastfeeding: current turn wins; history only fills in khi
      current turn không mention (tránh contaminate từ turn khác session);
    - inflammation: lấy max severity giữa current và history (không downgrade);
    - products/medications: union, with simple stop-word removal on later turns;
    - allergies and clinical descriptors: union.
    """
    # Chỉ lấy snapshot từ user turns (assistant turns không có normalized_snapshot).
    snapshots = [
        turn.normalized_snapshot for turn in history
        if turn.role == "user" and turn.normalized_snapshot is not None
    ]
    if not snapshots:
        return current

    age = current.context.age
    sex = current.context.sex
    skin_type = current.context.skin_type
    duration_weeks = current.context.duration_weeks
    # Ghi nhận xem turn HIỆN TẠI có explicitly set pregnancy/breastfeeding không.
    # Nếu current turn đã True → không cần fold từ history (giữ nguyên).
    # Nếu current turn là False → chỉ fold từ history khi current turn không
    #   mention pregnancy/breastfeeding gì cả (tức là không negation, không positive).
    _current_text_lower = current.description.lower()
    _current_mentions_pregnant = any(
        t in _current_text_lower
        for t in ("mang thai", "có thai", "bầu", "pregnant", "pregnancy")
    )
    _current_mentions_breastfeed = any(
        t in _current_text_lower
        for t in ("cho con bú", "cho con bu", "đang bú", "breastfeed", "lactating")
    )
    is_pregnant = current.context.is_pregnant
    is_breastfeeding = current.context.is_breastfeeding
    allergies = list(current.context.allergies)
    # Current-turn corrections are tombstones. Normalization may still extract
    # the corrected-away name (for example "không phải doxycycline"), so drop
    # it before replaying prior facts and again after replay.
    products = [
        value for value in current.context.current_products
        if not _mentions_stop(current.description, value)
    ]
    medications = [
        value for value in current.context.medications
        if not _mentions_stop(current.description, value)
    ]

    lesion_types = list(current.clinical.lesion_types) if current.clinical else []
    distribution = list(current.clinical.lesion_distribution) if current.clinical else []
    inflammation = current.clinical.inflammation_level if current.clinical else None
    scarring = list(current.clinical.scarring_signs) if current.clinical else []
    med_history = list(current.clinical.medication_history) if current.clinical else []
    hormonal = list(current.clinical.hormonal_factors) if current.clinical else []
    skincare = list(current.clinical.skincare_products) if current.clinical else []
    canonical_ingredients = list(current.clinical.canonical_ingredients) if current.clinical else []
    usage_frequencies = list(current.clinical.usage_frequencies) if current.clinical else []
    concentrations = list(current.clinical.concentrations) if current.clinical else []
    goals = list(current.clinical.treatment_goals) if current.clinical else []
    red_flags = list(current.clinical.red_flags_input) if current.clinical else []

    current_has_age = current.context.age is not None
    current_has_sex = bool(current.context.sex)
    current_has_skin_type = bool(current.context.skin_type)
    current_has_duration = current.context.duration_weeks is not None

    # Replay oldest -> newest so later corrections/tombstones dominate earlier
    # facts. Reversed replay was the source of corrected medication resurrection.
    for snap in snapshots:
        ctx = snap.context or {}
        clean = (snap.clean_text or "").lower()

        if not current_has_age and ctx.get("age") is not None:
            age = ctx.get("age")
        if not current_has_sex and ctx.get("sex"):
            sex = ctx.get("sex")
        if not current_has_skin_type and ctx.get("skin_type"):
            skin_type = ctx.get("skin_type")
        if not current_has_duration and ctx.get("duration_weeks") is not None:
            duration_weeks = ctx.get("duration_weeks")

        # Pregnancy: chỉ fold từ history khi current turn KHÔNG mention pregnancy.
        # Tránh inject "mang thai" từ turn cũ vào session của người dùng mới hoặc
        # người dùng đã hỏi về chủ đề khác không liên quan đến thai kỳ.
        # ponytail: hai nhanh phu dinh bang keyword da bi xoa o Phase 7.
        # 17 chuoi tung co quyen set is_pregnant = False -- tuc la TAT cong
        # chong chi dinh thai ky, cong tat dinh duy nhat con lai. Chung khong
        # kiem chu ngu va khong kiem pham vi phu dinh:
        #   "chi toi khong mang thai, con em thi co" -> is_pregnant = False
        # Trang thai thai ky gio chi den tu intaker. Fail-safe la GIU True:
        # rule khong bao gio duoc tu ha xuong False.
        if not _current_mentions_pregnant:
            if ctx.get("is_pregnant") and not is_pregnant:
                is_pregnant = True

        if not _current_mentions_breastfeed:
            if ctx.get("is_breastfeeding") and not is_breastfeeding:
                is_breastfeeding = True

        allergies.extend(ctx.get("allergies") or [])
        products = [value for value in products if not _mentions_stop(clean, value)]
        medications = [value for value in medications if not _mentions_stop(clean, value)]
        med_history = [value for value in med_history if not _mentions_stop(clean, value)]
        for value in ctx.get("current_products") or []:
            if _mentions_stop(clean, value):
                products = [p for p in products if p.lower() != value.lower()]
            else:
                products.append(value)
        for value in ctx.get("medications") or []:
            if _mentions_stop(clean, value):
                medications = [m for m in medications if m.lower() != value.lower()]
            else:
                medications.append(value)

        clinical = snap.clinical or {}
        snapshot_topic_shift = any(marker in clean for marker in (
            "không phải ở", "khong phai o", "câu này tôi hỏi về",
            "cau nay toi hoi ve", "chuyển sang", "chuyen sang",
            "nói nhầm", "noi nham",
        ))
        if snapshot_topic_shift:
            if clinical.get("lesion_distribution"):
                distribution = []
            if clinical.get("lesion_types"):
                lesion_types = []
        lesion_types.extend(clinical.get("lesion_types") or [])
        distribution.extend(clinical.get("lesion_distribution") or [])
        # Inflammation: lấy max severity, không downgrade (moderate → mild là sai).
        history_infl = clinical.get("inflammation_level")
        inflammation = _max_severity(inflammation, history_infl)
        scarring.extend(clinical.get("scarring_signs") or [])
        med_history.extend(clinical.get("medication_history") or [])
        hormonal.extend(clinical.get("hormonal_factors") or [])
        skincare.extend(clinical.get("skincare_products") or [])
        canonical_ingredients.extend(clinical.get("canonical_ingredients") or [])
        usage_frequencies.extend(clinical.get("usage_frequencies") or [])
        concentrations.extend(clinical.get("concentrations") or [])
        goals.extend(clinical.get("treatment_goals") or [])
        red_flags.extend(clinical.get("red_flags_input") or [])

    # Apply current-turn tombstones last so an older snapshot cannot resurrect
    # a product/medication that the user explicitly removed or corrected.
    products = [value for value in products if not _mentions_stop(current.description, value)]
    medications = [value for value in medications if not _mentions_stop(current.description, value)]
    med_history = [value for value in med_history if not _mentions_stop(current.description, value)]

    # Explicit topic shifts replace location-dependent clinical facts instead
    # of unioning face/back or old/new lesions into one synthetic case.
    current_lower = current.description.lower()
    topic_shift = any(marker in current_lower for marker in (
        "không phải ở", "khong phai o", "câu này tôi hỏi về",
        "cau nay toi hoi ve", "chuyển sang", "chuyen sang",
        "nói nhầm", "noi nham",
    ))
    if topic_shift and current.clinical is not None:
        if current.clinical.lesion_distribution:
            distribution = list(current.clinical.lesion_distribution)
        if current.clinical.lesion_types:
            lesion_types = list(current.clinical.lesion_types)

    merged_context = UserContext(
        age=age,
        sex=sex,
        skin_type=skin_type,
        is_pregnant=bool(is_pregnant),
        is_breastfeeding=bool(is_breastfeeding),
        allergies=_dedupe_values(allergies),
        current_products=_dedupe_values(products),
        medications=_dedupe_values(medications),
        duration_weeks=duration_weeks,
    )
    merged_clinical = AcneClinicalInput(
        lesion_types=_dedupe_values(lesion_types),  # type: ignore[arg-type]
        lesion_distribution=_dedupe_values(distribution),  # type: ignore[arg-type]
        # `inflammation` la None khi current.clinical is None VA khong snapshot
        # nao co inflammation_level. Truong nay la Literal khong nhan None ->
        # ValidationError -> 500 giua stream.
        #
        # To hop do co that: intaker khai bao ro "khong co bat ky tin hieu lam
        # sang nao thi clinical=null", va UserInput.clinical default cung la
        # None. Hai luot personal-case lien tiep deu khong co tin hieu lam sang
        # la du. Xem tests/test_session_fold_branches.py.
        #
        # None van la sentinel dung TRONG luc fold (_max_severity dua vao no de
        # khong ha cap severity), nen va o cho dung: luc dung object.
        inflammation_level=inflammation or "unknown",
        scarring_signs=_dedupe_values(scarring),
        medication_history=_dedupe_values(med_history),
        hormonal_factors=_dedupe_values(hormonal),
        skincare_products=_dedupe_values(skincare),
        canonical_ingredients=_dedupe_values(canonical_ingredients),
        usage_frequencies=_dedupe_values(usage_frequencies),
        concentrations=list(dict.fromkeys(float(x) for x in concentrations)),
        treatment_goals=_dedupe_values(goals),
        red_flags_input=_dedupe_values(red_flags),
    )
    has_clinical = any(
        (
            merged_clinical.lesion_types,
            merged_clinical.lesion_distribution,
            merged_clinical.inflammation_level,
            merged_clinical.scarring_signs,
            merged_clinical.medication_history,
            merged_clinical.hormonal_factors,
            merged_clinical.skincare_products,
            merged_clinical.canonical_ingredients,
            merged_clinical.usage_frequencies,
            merged_clinical.concentrations,
            merged_clinical.treatment_goals,
            merged_clinical.red_flags_input,
        )
    )
    return current.model_copy(update={
        "context": merged_context,
        "clinical": merged_clinical if has_clinical else None,
    })


