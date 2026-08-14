from datagen.roledata.config import Config
from datagen.roledata.generator import (
    load_taxonomy,
    planned_input_style,
    synthesize_context,
)


def test_input_style_schedule_is_exactly_thirty_percent_per_plan_quota() -> None:
    cfg = Config(api_key="offline-test")
    for case in load_taxonomy(cfg):
        styles = [planned_input_style(case.id, ordinal) for ordinal in range(1, case.count + 1)]
        assert sum(style != "standard" for style in styles) == int(case.count * 0.30)


def test_b5_adjacent_records_share_source_and_have_distinct_depths() -> None:
    cfg = Config(api_key="offline-test")
    case = next(case for case in load_taxonomy(cfg) if case.id == "B5_depth_anchor")
    first_context, first_sources, first_meta = synthesize_context(case, cfg, sequence=0)
    second_context, second_sources, second_meta = synthesize_context(case, cfg, sequence=1)

    assert first_context == second_context
    assert first_sources == second_sources
    assert first_meta["anchor_group"] == second_meta["anchor_group"]
    assert {first_meta["depth"], second_meta["depth"]} == {"beginner", "advanced"}
