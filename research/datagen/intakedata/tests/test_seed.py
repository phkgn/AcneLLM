from datagen.intakedata.seed import relabel_row


def _base_row(**overrides):
    row = {
        "text": "Em nữ 22 tuổi da dầu, bị mụn đỏ ở má và đang dùng BHA.",
        "skin_type": "oily",
        "sex": "female",
        "age": 22,
        "duration_weeks": None,
        "is_pregnant": None,
        "is_breastfeeding": None,
        "inflammation": "moderate",
        "lesions": ["papule"],
        "distribution": ["cheeks"],
        "products": ["BHA"],
        "medications": [],
        "allergies": [],
        "intent": "advise",
        "reliable": True,
    }
    row.update(overrides)
    return row


def test_flat_golden_maps_to_nested_contract(anchor) -> None:
    record, reasons = relabel_row(_base_row(), anchor)
    assert reasons == []
    assert record is not None
    import json

    payload = json.loads(record["messages"][-1]["content"])
    assert payload["context"]["age"] == {"value": 22, "confidence": 0.94}
    assert payload["context"]["current_products"][0]["value"] == "salicylic acid"
    assert payload["clinical"]["lesion_types"][0]["value"] == "papule"
    assert payload["clinical"]["lesion_distribution"][0]["value"] == "cheeks"
    assert record["meta"]["source"] == "golden_relabel"


def test_knowledge_relabel_discards_flat_extraction_traps(anchor) -> None:
    row = _base_row(
        text="BHA có tốt hơn AHA cho mụn không?",
        intent="knowledge",
        products=["BHA", "AHA"],
        lesions=["papule"],
    )
    record, reasons = relabel_row(row, anchor)
    assert reasons == []
    assert record is not None
    import json

    payload = json.loads(record["messages"][-1]["content"])
    assert payload["intent"] == "knowledge"
    assert payload["context"] == {}
    assert payload["clinical"] is None


def test_unknown_enum_is_filtered(anchor) -> None:
    record, reasons = relabel_row(_base_row(lesions=["very_bad"]), anchor)
    assert record is None
    assert "enum_lesions" in reasons
