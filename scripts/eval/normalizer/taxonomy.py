"""Taxonomy alignment between the *gold* labels shipped in the finetune data
(``data/finetune/cleanv3_gen.jsonl`` — synthetic labels produced by an LLM) and
the *predicted* labels emitted by the rule-based pipeline normalizer
(``acne_llm.chat.normalizer.normalize_chat_message``).

Why this module exists
----------------------
The two label spaces do NOT match 1:1. Naively comparing them makes a correct
normalizer look broken (e.g. ``treatment_goals`` scored ~0.15 Jaccard purely
because the two sides use different words for the same intent). Before any
metric is computed, both sides must be projected into a shared canonical space,
and labels the normalizer *cannot by design* emit must be tracked separately as
a coverage gap rather than counted as errors.

Everything here is pure data + pure functions so it is trivially unit-testable
and easy to audit / extend.
"""
from __future__ import annotations

from typing import Iterable

# ---------------------------------------------------------------------------
# Labels that carry no signal and must be dropped from BOTH sides before scoring
# ---------------------------------------------------------------------------
NOISE_LABELS: frozenset[str] = frozenset(
    {"", "none", "unknown", "other", "na", "n/a", "not applicable"}
)


def _clean(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    for v in values or []:
        if not isinstance(v, str):
            # gold occasionally stores structured dict items; skip — not comparable
            continue
        s = v.strip().lower()
        if s and s not in NOISE_LABELS:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# LESION TYPES
# Normalizer emits: blackhead, closed_comedone, cyst, nodule, papule, pustule,
#                   whitehead  (+ scar / PIH are routed to scarring_signs)
# Gold adds generic "comedone", "scar", "post_inflammatory_hyperpigmentation".
#
# We expose two views:
#   strict  — exact label (subtype-sensitive)
#   bucket  — clinical family (comedonal / inflammatory / nodulocystic / ...)
# ---------------------------------------------------------------------------
_LESION_BUCKET: dict[str, str] = {
    "comedone": "comedonal",
    "open_comedone": "comedonal",
    "closed_comedone": "comedonal",
    "blackhead": "comedonal",
    "whitehead": "comedonal",
    "papule": "inflammatory",
    "pustule": "inflammatory",
    "inflammatory": "inflammatory",
    "nodule": "nodulocystic",
    "cyst": "nodulocystic",
    # scar / pigmentation are a different clinical axis; keep as their own bucket
    "scar": "scar",
    "atrophic_scar": "scar",
    "hypertrophic_scar": "scar",
    "risk_of_scarring": "scar",
    "post_inflammatory_hyperpigmentation": "pigmentation",
    "enlarged_pores": "pores",
    "vesicle": "other_lesion",
}

# Labels the normalizer routes to a DIFFERENT field (scarring_signs), so they
# must not be penalised as lesion misses.
LESION_CROSS_FIELD: frozenset[str] = frozenset(
    {"scar", "atrophic_scar", "hypertrophic_scar", "risk_of_scarring",
     "post_inflammatory_hyperpigmentation"}
)


# ---------------------------------------------------------------------------
# DISTRIBUTION
# Normalizer cannot emit: t_zone, neck, hairline, face (composite / uncovered).
# Expand composites so a t_zone gold label credits forehead/nose/chin hits.
# ---------------------------------------------------------------------------
_DISTRIBUTION_EXPAND: dict[str, set[str]] = {
    "t_zone": {"forehead", "nose", "chin"},
    "face": set(),          # too vague — drop
    "hairline": {"forehead"},
}
# Regions the normalizer has no pattern for → coverage gap, not error.
DISTRIBUTION_UNCOVERED: frozenset[str] = frozenset(
    {"neck", "around_eyes", "armpits", "buttocks"}
)


# ---------------------------------------------------------------------------
# TREATMENT GOALS
# Normalizer vocab: clear_acne, fade_hyperpigmentation, hydration, prevent_acne,
#                   reduce_inflammation, reduce_oiliness, treat_scar
# Map both sides onto this canonical space. Gold goals with no normalizer
# equivalent (reduce_blackheads/comedones, skin_care_routine, prevent_scarring)
# are recorded as UNCOVERED so we report a coverage gap instead of a false miss.
# ---------------------------------------------------------------------------
_GOAL_CANON: dict[str, str] = {
    # already canonical
    "clear_acne": "clear_acne",
    "acne_control": "clear_acne",
    "reduce_acne": "clear_acne",
    "reduce_inflammation": "reduce_inflammation",
    "prevent_inflammation": "reduce_inflammation",
    "reduce_irritation": "reduce_inflammation",
    "reduce_pih": "fade_hyperpigmentation",
    "fade_hyperpigmentation": "fade_hyperpigmentation",
    "improve_scar": "treat_scar",
    "treat_scar": "treat_scar",
    "reduce_oil": "reduce_oiliness",
    "reduce_sebum": "reduce_oiliness",
    "reduce_oiliness": "reduce_oiliness",
    "hydration": "hydration",
    "relieve_dryness": "hydration",
    "reduce_dryness": "hydration",
    "prevent_acne": "prevent_acne",
    "prevent_relapse": "prevent_acne",
}
GOAL_UNCOVERED: frozenset[str] = frozenset(
    {"prevent_scarring", "reduce_blackheads", "reduce_comedones",
     "skin_care_routine", "skincare_routine", "safe_for_pregnancy",
     "reduce_pustules", "reduce_whiteheads", "treatment_failure"}
)


# ---------------------------------------------------------------------------
# HORMONAL FACTORS — spaces are nearly identical.
# Normalizer captures breastfeeding as context.is_breastfeeding, not here.
# ---------------------------------------------------------------------------
_HORMONAL_CANON: dict[str, str] = {
    "menstrual_cycle": "menstrual_cycle",
    "pregnancy": "pregnancy",
    "postpartum": "postpartum",
    "breastfeeding": "postpartum",   # both map to peripartum hormonal state
    "puberty": "puberty",
    "pcos": "pcos",
    "stress": "stress",
    "diet": "diet",
    "contraceptive_pill": "menstrual_cycle",
    "persistent_acne": "",           # not hormonal → drop
}


# ---------------------------------------------------------------------------
# RED FLAGS
# Normalizer vocab is symptom-oriented (infection_signs, painful_lesions,
# purulent_lesions, scarring_risk, skin_irritation, widespread).
# Gold vocab is escalation-oriented (severe_nodular_cystic_acne,
# treatment_failure, pregnancy...). Only scarring_risk truly overlaps, so this
# field is reported as LOW-ALIGNMENT: we score the intersectable subset and flag
# the rest as coverage gap.
# ---------------------------------------------------------------------------
_REDFLAG_CANON: dict[str, str] = {
    "scarring_risk": "scarring_risk",
    "risk_of_scarring": "scarring_risk",
    "scaring_risk": "scarring_risk",
    "severe_inflammation": "severe_inflammation",
    "infection_risk": "infection_signs",
    "infection_signs": "infection_signs",
    "painful_lesions": "painful_lesions",
    "purulent_lesions": "purulent_lesions",
    "skin_irritation": "skin_irritation",
    "widespread": "widespread",
}
REDFLAG_UNCOVERED: frozenset[str] = frozenset(
    {"severe_nodular_cystic_acne", "treatment_failure", "pregnancy",
     "persistent_acne", "breastfeeding", "postpartum", "hypertension",
     "sensitive_skin"}
)


# ---------------------------------------------------------------------------
# MEDICATIONS — gold has 789 messy free-text variants. Canonicalize both sides
# to a small set of known active ingredients via substring matching.
# ---------------------------------------------------------------------------
_INGREDIENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("benzoyl_peroxide", ("benzoyl", "bpo")),
    ("adapalene", ("adapalene", "differin")),
    ("tretinoin", ("tretinoin",)),
    ("isotretinoin", ("isotretinoin", "accutane", "roaccutane")),
    ("retinol", ("retinol",)),
    ("retinoid", ("retinoid",)),
    ("clindamycin", ("clindamycin",)),
    ("erythromycin", ("erythromycin",)),
    ("doxycycline", ("doxycycline",)),
    ("tetracycline", ("tetracycline",)),
    ("minocycline", ("minocycline",)),
    ("salicylic_acid", ("salicylic", "bha")),
    ("glycolic_acid", ("glycolic",)),
    ("azelaic_acid", ("azelaic",)),
    ("niacinamide", ("niacinamide",)),
    ("oral_contraceptive", ("contracept", "birth control", "tranh thai", "diane")),
    ("spironolactone", ("spironolactone",)),
    ("antibiotic", ("antibiotic", "khang sinh")),
]


def canon_ingredients(values: Iterable[str] | None) -> set[str]:
    """Collapse arbitrary medication strings into known ingredient tokens."""
    out: set[str] = set()
    for v in values or []:
        if not isinstance(v, str):
            continue
        low = v.lower()
        for canon, needles in _INGREDIENT_PATTERNS:
            if any(n in low for n in needles):
                out.add(canon)
    return out


# ---------------------------------------------------------------------------
# Public canonicalization helpers — each returns (canonical_set, uncovered_set)
# uncovered = gold labels the normalizer cannot emit by design (coverage gap).
# ---------------------------------------------------------------------------
def canon_lesions(values, *, bucket: bool) -> tuple[set[str], set[str]]:
    cleaned = _clean(values)
    uncovered = {v for v in cleaned if v in LESION_CROSS_FIELD}
    core = [v for v in cleaned if v not in LESION_CROSS_FIELD]
    if bucket:
        return {_LESION_BUCKET.get(v, v) for v in core}, uncovered
    return set(core), uncovered


def canon_distribution(values, *, expand: bool) -> tuple[set[str], set[str]]:
    cleaned = _clean(values)
    uncovered = {v for v in cleaned if v in DISTRIBUTION_UNCOVERED}
    out: set[str] = set()
    for v in cleaned:
        if v in DISTRIBUTION_UNCOVERED:
            continue
        if expand and v in _DISTRIBUTION_EXPAND:
            out |= _DISTRIBUTION_EXPAND[v]
        else:
            out.add(v)
    return out, uncovered


def canon_goals(values) -> tuple[set[str], set[str]]:
    cleaned = _clean(values)
    uncovered = {v for v in cleaned if v in GOAL_UNCOVERED}
    out = {_GOAL_CANON[v] for v in cleaned if v in _GOAL_CANON and _GOAL_CANON[v]}
    return out, uncovered


def canon_hormonal(values) -> tuple[set[str], set[str]]:
    cleaned = _clean(values)
    out = {_HORMONAL_CANON[v] for v in cleaned
           if v in _HORMONAL_CANON and _HORMONAL_CANON[v]}
    uncovered = {v for v in cleaned if v not in _HORMONAL_CANON}
    return out, uncovered


def canon_redflags(values) -> tuple[set[str], set[str]]:
    cleaned = _clean(values)
    uncovered = {v for v in cleaned if v in REDFLAG_UNCOVERED}
    out = {_REDFLAG_CANON[v] for v in cleaned if v in _REDFLAG_CANON}
    return out, uncovered


def canon_inflammation(value: str | None) -> str:
    v = (value or "unknown")
    v = v.strip().lower() if isinstance(v, str) else "unknown"
    return v if v in {"mild", "moderate", "severe", "none"} else "unknown"


def canon_scalar(value: str | None) -> str:
    v = (value or "unknown")
    return v.strip().lower() if isinstance(v, str) else "unknown"
