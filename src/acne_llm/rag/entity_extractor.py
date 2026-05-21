"""Lightweight acne entity extraction for direct KB/entity lookup."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas.kb import EntityRecord


@dataclass(frozen=True)
class EntitySeed:
    entity_id: str
    entity_type: str
    name_vi: str
    name_en: str
    aliases: tuple[str, ...]
    description: str
    contraindications: tuple[str, ...] = ()


_SEEDS = [
    EntitySeed(
        entity_id="ingredient_benzoyl_peroxide",
        entity_type="active_ingredient",
        name_vi="Benzoyl peroxide",
        name_en="Benzoyl peroxide",
        aliases=("benzoyl peroxide", "bpo"),
        description="Hoạt chất bôi hỗ trợ giảm vi khuẩn C. acnes và giảm viêm trong mụn.",
    ),
    EntitySeed(
        entity_id="medication_isotretinoin",
        entity_type="medication",
        name_vi="Isotretinoin",
        name_en="Isotretinoin",
        aliases=("isotretinoin", "accutane"),
        description="Thuốc kê đơn đường uống cho một số trường hợp mụn nặng, cần bác sĩ da liễu theo dõi.",
        contraindications=("pregnancy", "breastfeeding", "self_medication"),
    ),
    EntitySeed(
        entity_id="ingredient_salicylic_acid",
        entity_type="active_ingredient",
        name_vi="Axit salicylic",
        name_en="Salicylic acid",
        aliases=("salicylic acid", "axit salicylic", "bha"),
        description="Hoạt chất hỗ trợ làm sạch lỗ chân lông, thường dùng trong chăm sóc mụn đầu đen/đầu trắng.",
    ),
    EntitySeed(
        entity_id="medication_adapalene",
        entity_type="medication",
        name_vi="Adapalene",
        name_en="Adapalene",
        aliases=("adapalene", "retinoid"),
        description="Retinoid bôi dùng trong điều trị mụn, cần thận trọng ở người mang thai/cho con bú.",
        contraindications=("pregnancy",),
    ),
]


def extract_entities(text: str) -> list[EntityRecord]:
    found: list[EntityRecord] = []
    lowered = text.lower()
    for seed in _SEEDS:
        terms = {seed.name_vi.lower(), seed.name_en.lower(), *seed.aliases}
        if any(re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", lowered) for term in terms):
            found.append(
                EntityRecord(
                    entity_id=seed.entity_id,
                    entity_type=seed.entity_type,  # type: ignore[arg-type]
                    name_vi=seed.name_vi,
                    name_en=seed.name_en,
                    aliases=list(seed.aliases),
                    description=seed.description,
                    contraindications=list(seed.contraindications),
                )
            )
    return found
