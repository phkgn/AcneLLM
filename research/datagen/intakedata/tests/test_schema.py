import json

from datagen.intakedata.schema import (
    DISTRIBUTION,
    INFLAMMATION,
    INTENT,
    LESION,
    SEX,
    SKIN,
    build_json_schema,
    validate_intake_record,
)


def test_schema_contains_source_of_truth_enums() -> None:
    schema = build_json_schema()
    assert schema["properties"]["intent"]["enum"] == sorted(INTENT)
    populated = schema["properties"]["context"]["anyOf"][1]
    assert populated["properties"]["sex"]["anyOf"][0]["properties"]["value"]["enum"] == sorted(SEX)
    assert populated["properties"]["skin_type"]["anyOf"][0]["properties"]["value"]["enum"] == sorted(SKIN)
    clinical = schema["properties"]["clinical"]["anyOf"][1]
    assert clinical["properties"]["lesion_types"]["items"]["properties"]["value"]["enum"] == sorted(LESION)
    assert clinical["properties"]["inflammation_level"]["properties"]["value"]["enum"] == sorted(INFLAMMATION)
    assert clinical["properties"]["lesion_distribution"]["items"]["properties"]["value"]["enum"] == sorted(DISTRIBUTION)


def test_valid_node_record_and_minified_json(make_record) -> None:
    record = make_record()
    content = record["messages"][-1]["content"]
    assert content.startswith("{") and content.endswith("}")
    assert "\n" not in content
    ok, reasons = validate_intake_record(content)
    assert ok, reasons


def test_rejects_broken_json_and_invalid_enum(make_record) -> None:
    assert validate_intake_record("{broken") == (False, ["json_parse"])
    payload = json.loads(make_record()["messages"][-1]["content"])
    payload["clinical"]["lesion_types"][0]["value"] = "mụn_viêm"
    ok, reasons = validate_intake_record(payload)
    assert not ok
    assert "clinical.lesion_types" in reasons


def test_clinical_must_be_null_or_nonempty_valid_object(make_record) -> None:
    payload = json.loads(make_record()["messages"][-1]["content"])
    payload["clinical"] = None
    assert validate_intake_record(payload)[0]
    payload["clinical"] = {
        "lesion_types": [],
        "inflammation_level": {"value": "unknown", "confidence": 0.5},
        "lesion_distribution": [],
    }
    ok, reasons = validate_intake_record(payload)
    assert not ok
    assert "clinical_empty" in reasons
