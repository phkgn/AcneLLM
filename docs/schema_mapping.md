# Schema Mapping: ExtractionConfidence (EC) vs Core Schema

## Tổng quan

Có 3 nguồn schema chính trong codebase:
1. **ExtractionConfidence (EC)** - `src/acne_llm/chat/extraction_confidence.py`
2. **Core Schema** - `src/acne_llm/schemas/core.py` (AcneClinicalInput, UserContext)
3. **Clinical Schema** - `src/acne_llm/schemas/clinical.py` (NormalizedAcneCase)

---

## Canonical Field Names (Source of Truth)

### Scalar Fields

| EC Field | Type | Canonical Values | Notes |
|----------|------|-----------------|-------|
| `skin_type` | `FieldResult[str]` | `"dry"\|"oily"\|"combination"\|"sensitive"\|"normal"\|"unknown"` | ✅ UserContext đã có "unknown" |
| `sex` | `FieldResult[str]` | `"male"\|"female"\|"other"\|null` | |
| `age` | `FieldResult[int]` | `int (0-120)` hoặc `null` | |
| `duration_weeks` | `FieldResult[int]` | `int` hoặc `null` | Số tuần |
| `is_pregnant` | `FieldResult[bool]` | `true\|false\|null` | |
| `is_breastfeeding` | `FieldResult[bool]` | `true\|false\|null` | |
| `inflammation` | `FieldResult[str]` | `"none"\|"mild"\|"moderate"\|"severe"\|"unknown"` | |

### List Fields

| EC Field | Type | Canonical Values | Notes |
|----------|------|-----------------|-------|
| `lesion_types` | `ListFieldResult[str]` | `"comedone"\|"whitehead"\|"blackhead"\|"closed_comedone"\|"papule"\|"pustule"\|"nodule"\|"cyst"\|"scar"\|"post_inflammatory_hyperpigmentation"\|"other"` | ✅ Đã có comedone |
| `distribution` | `ListFieldResult[str]` | `"forehead"\|"cheeks"\|"chin"\|"jawline"\|"nose"\|"around_mouth"\|"back"\|"chest"\|"shoulders"\|"neck"\|"t_zone"\|"other"` | |
| `products` | `ListFieldResult[str]` | Free text (tên sản phẩm/hoạt chất) | Đang dùng |
| `medications` | `ListFieldResult[str]` | Free text (tên thuốc) | Đang dùng |
| `allergies` | `ListFieldResult[str]` | `"retinol"\|"retinoid"\|"tretinoin"\|"adapalene"\|"salicylic_acid"\|"benzoyl_peroxide"\|"niacinamide"\|"bha_irritation"\|"aha_irritation"\|"tea_tree"\|"clindamycin"\|"doxycycline"\|"penicillin"\|"fragrance"\|"preservative"\|"sunscreen_chemical"\|"aloe_vera"\|"centella"` | Chỉ khi CÓ context kích ứng |
| `scarring_signs` | `ListFieldResult[str]` | `"sẹo mụn"\|"thâm sau mụn"` | Free text |
| `hormonal_factors` | `ListFieldResult[str]` | `"menstrual_cycle"\|"pcos"\|"stress"\|"diet"\|"pregnancy"\|"postpartum"\|"puberty"` | |
| `treatment_goals` | `ListFieldResult[str]` | `"clear_acne"\|"treat_scar"\|"fade_hyperpigmentation"\|"reduce_oilyness"\|"hydration"\|"reduce_inflammation"\|"prevent_acne"\|"build_routine"\|"product_recommendation"\|"see_doctor"` | |
| `red_flags` | `ListFieldResult[str]` | `"widespread"\|"painful_lesions"\|"purulent_lesions"\|"scarring_risk"\|"infection_signs"\|"skin_irritation"\|"treatment_failure"\|"no_prior_treatment"\|"chronic"\|"self_treatment_risk"` | |

---

## Mapping: EC ↔ Core Schema

### AcneClinicalInput

| EC Field | Core Field | Mapping |
|----------|------------|---------|
| `inflammation` | `inflammation_level` | Direct map |
| `lesion_types` | `lesion_types` | Direct map |
| `distribution` | `lesion_distribution` | Rename |
| `products` | `skincare_products` | Rename |
| `medications` | `medication_history` | Rename |
| `scarring_signs` | `scarring_signs` | Direct map |
| `hormonal_factors` | `hormonal_factors` | Direct map |
| `treatment_goals` | `treatment_goals` | Direct map |
| `red_flags` | `red_flags_input` | Rename |
| - | `canonical_ingredients` | EC không extract (suy từ products) |
| - | `usage_frequencies` | EC không extract |
| - | `concentrations` | EC không extract |

### UserContext

| EC Field | Core Field | Mapping |
|----------|------------|---------|
| `skin_type` | `skin_type` | Direct map (đã có "unknown") |
| `sex` | `sex` | Direct map |
| `age` | `age` | Direct map |
| `duration_weeks` | `duration_weeks` | Direct map |
| `is_pregnant` | `is_pregnant` | Direct map |
| `is_breastfeeding` | `is_breastfeeding` | Direct map |
| `allergies` | `allergies` | Direct map |
| `products` | `current_products` | Rename |

---

## Field Name Inconsistencies (Legacy)

| Legacy Name | EC Name (Canonical) | Status |
|------------|---------------------|--------|
| `red_flags_input` | `red_flags` | Legacy - cần rename |
| `medication_history` | `medications` | Legacy - cần rename |
| `skincare_products` | `products` | Legacy - cần rename |
| `current_products` | `products` | Legacy - cần rename |

---

## Validation Rules

### Lesion Types
```python
VALID_LESIONS = {
    "comedone", "whitehead", "blackhead", "closed_comedone",
    "papule", "pustule", "nodule", "cyst", "scar",
    "post_inflammatory_hyperpigmentation", "other"
}
```

### Allergies (phải có context kích ứng)
```python
VALID_ALLERGIES = {
    "retinol", "retinoid", "tretinoin", "adapalene",
    "salicylic_acid", "benzoyl_peroxide", "niacinamide",
    "bha_irritation", "aha_irritation", "tea_tree",
    "clindamycin", "doxycycline", "penicillin",
    "fragrance", "preservative", "sunscreen_chemical",
    "aloe_vera", "centella"
}
```

### Red Flags
```python
VALID_RED_FLAGS = {
    "widespread", "painful_lesions", "purulent_lesions",
    "scarring_risk", "infection_signs", "skin_irritation",
    "treatment_failure", "no_prior_treatment",
    "chronic", "self_treatment_risk"
}
```

---

## Completeness Fields (theo priority)

```python
_CORE_FIELDS = ["lesion_types", "distribution", "inflammation"]
_SAFETY_FIELDS = ["is_pregnant", "is_breastfeeding", "allergies"]
_ALL_FIELDS = _CORE_FIELDS + _SAFETY_FIELDS + [
    "skin_type", "age", "duration_weeks", "hormonal_factors",
    "scarring_signs", "treatment_goals"
]
```

---

## Scripts liên quan

- `scripts/gen_golden_set.py` - Generate golden set với đầy đủ fields
- `scripts/eval_extraction.py` - Eval extraction với golden set

---

## Recent Changes

### 2026-05-31
- ✅ Thêm `"comedone"` vào LESIONS (core.py + clinical.py + normalizer.py)
- ✅ Thêm `"unknown"` vào INFLAMMATION (core.py)
- ✅ Thêm `"unknown"` vào UserContext.skin_type (core.py)
- ✅ Fix `_has_medication_use_context` - loại bỏ `ngưng/dừng` khỏi confirmation verbs
- ✅ Fix `find_in_text` - accept parameter được sử dụng đúng
- ✅ Fix `_inflammation_confidence` regex - word boundary cho "nặng"
- ✅ Fix IntakeResult.extraction_confidence type annotation
- ✅ Remove dead code trong `_extract_inflammation`
- ✅ Fix `best_match` division by zero
- ✅ Add TypeAlias cho Method
- ✅ Mở rộng completeness check cho tất cả fields
- ✅ Thêm `low_confidence_fields` vào CompletenessResult
- ✅ Add field questions cho tất cả fields
