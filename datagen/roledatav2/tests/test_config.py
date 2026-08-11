"""Bất biến của config + taxonomy v2. Sai ở đây thì không được chạy generate."""
from __future__ import annotations

import pytest
import yaml

from datagen.roledata.config import CASE_TYPE_TARGETS as V1_TARGETS
from datagen.roledatav2.config import (
    CASE_TYPE_TARGETS,
    FULL_TARGET,
    Config,
    _v1_default,
    compute_budget,
)
from datagen.roledatav2.generator import load_taxonomy

CONTENT_CASES = {
    "B1_grounded_role",
    "B3_irrelevant_chunk",
    "B4_conflicting_docs",
    "B5_depth_anchor",
    "K1_knowledge_anchor",
    "R2_depth_adaptation",
    "R10_special_population",
}


def test_quota_sums_to_full_target() -> None:
    assert sum(CASE_TYPE_TARGETS.values()) == FULL_TARGET == 3_500


def test_case_set_identical_to_v1() -> None:
    """Đổi quota thì được; thêm/bớt case thì phải là quyết định riêng, không lẻn vào."""
    assert set(CASE_TYPE_TARGETS) == set(V1_TARGETS)


def test_quota_shifted_towards_content_cases() -> None:
    v1_content = sum(V1_TARGETS[case] for case in CONTENT_CASES)
    v2_content = sum(CASE_TYPE_TARGETS[case] for case in CONTENT_CASES)
    assert v2_content > v1_content, "v2 phải dịch quota sang nhóm mang nội dung"
    assert v2_content - v1_content >= 300


def test_compute_budget_is_exact_and_deterministic() -> None:
    for total in (0, 1, 7, 100, 999, 3_500):
        budget = compute_budget(total)
        assert sum(budget.values()) == total
        assert budget == compute_budget(total)
        assert set(budget) == set(CASE_TYPE_TARGETS)


def test_paths_do_not_touch_roledata_v1_output() -> None:
    cfg = Config(api_key="offline-test")
    v1_output = cfg.project_root / "datagen" / "roledata" / "output"
    for path in (cfg.output_dir, cfg.train_path, cfg.export_path, cfg.summary_path):
        assert v1_output not in path.parents and path != v1_output, path
    assert cfg.output_dir.name == "output"
    assert cfg.output_dir.parent.name == "roledatav2"


def test_taxonomy_matches_config_and_declares_bands() -> None:
    cfg = Config(api_key="offline-test")
    cases = load_taxonomy(cfg)
    assert {case.id: case.count for case in cases} == CASE_TYPE_TARGETS
    for case in cases:
        low, high = case.len_chars
        assert 0 < low < high <= 2_000, case.id
        assert case.min_points >= 0
        if case.require_structure:
            assert case.min_points >= 2, case.id


def test_content_cases_target_the_measured_band() -> None:
    """Bậc nhảy chất lượng đo được nằm giữa ~900 và ~1.300 ký tự.

    Mọi case mang nội dung phải có trần >= 1.500 và sàn >= 700, nếu không thì
    band đang nằm dưới vùng mà eval cho thấy độ phủ mới xảy ra.
    """
    cfg = Config(api_key="offline-test")
    for case in load_taxonomy(cfg):
        if case.id in CONTENT_CASES:
            low, high = case.len_chars
            assert high >= 1_500, f"{case.id}: trần {high} thấp hơn vùng đo được"
            assert low >= 700, f"{case.id}: sàn {low} rơi vào vùng chắc chắn thiếu ý"
            assert case.min_points >= 3, case.id


def test_short_cases_were_not_inflated() -> None:
    """Không được nới nhóm vai/giọng: anchor yêu cầu ngắn gọn với ca đơn giản."""
    cfg = Config(api_key="offline-test")
    limits = {
        "R7_conversation_glue": 200,
        "R8_meta_jailbreak": 300,
        "R6_role_boundary": 380,
        "R1_identity": 400,
    }
    for case in load_taxonomy(cfg):
        if case.id in limits:
            assert case.len_chars[1] <= limits[case.id], case.id


def test_r5_behaviour_changed_not_only_length() -> None:
    """R5 v1 có 187/187 mẫu chỉ hỏi ngược. v2 phải bắt trả lời trước, rồi mới hỏi."""
    cfg = Config(api_key="offline-test")
    template = cfg.prompt_path("R5_natural_clarification")
    assert template.parent.name == "prompts"
    assert template.parent.parent.name == "roledatav2", "R5 phải dùng template v2"
    body = template.read_text(encoding="utf-8")
    assert "KHÔNG trả lời chỉ gồm câu hỏi" in body
    case = next(c for c in load_taxonomy(cfg) if c.id == "R5_natural_clarification")
    assert case.min_points >= 1


def test_output_budget_fits_the_longest_band() -> None:
    """v1 để 1.200 token ra cho target ~400 ký tự. Band v2 lên tới 1.800 ký tự
    tiếng Việt + câu hỏi + 3 points + cú pháp JSON. Thiếu token là JSON bị cắt
    giữa chừng -> parse hỏng -> reject vòng lặp (đúng lỗi đã thấy khi thử kimi)."""
    cfg = Config(api_key="offline-test")
    longest = max(case.len_chars[1] for case in load_taxonomy(cfg))
    # Tiếng Việt tốn token: ước lượng thận trọng ~2 ký tự/token cho phần sinh ra.
    assert cfg.max_output_tokens >= longest / 2 * 1.8, (cfg.max_output_tokens, longest)
    assert cfg.max_output_tokens > _v1_default("max_output_tokens")
    assert cfg.request_timeout_s > _v1_default("request_timeout_s")


def test_v1_defaults_are_read_from_dataclass_fields() -> None:
    """Chốt lại cái bẫy: `ConfigV1.<field>` trên dataclass slots là descriptor,
    không phải giá trị mặc định. So sánh với nó thì override chết im lặng."""
    from datagen.roledata.config import Config as ConfigV1

    assert _v1_default("max_output_tokens") == 1_200
    assert not isinstance(ConfigV1.max_output_tokens, int)


def test_explicit_override_is_respected() -> None:
    assert Config(api_key="x", max_output_tokens=999).max_output_tokens == 999
    assert Config(api_key="x", request_timeout_s=5.0).request_timeout_s == 5.0


ENV_DEEPSEEK = {
    "ROLEDATA_PROVIDER": "deepseek",
    "DEEPSEEK_API_KEY": "sk-deepseek-test",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-v4-flash",
    "OPENAI_API_KEY": "sk-proj-openai-thật",
}


def test_default_provider_is_deepseek_v4_flash() -> None:
    """Mặc định của v2. v1 mặc định gpt-4o-mini và đó là trần của dataset cũ."""
    cfg = Config(_env_values={"DEEPSEEK_API_KEY": "sk-ds"})
    assert cfg.provider == "deepseek"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.model == "deepseek-v4-flash"
    assert cfg.api_key == "sk-ds"
    assert (cfg.input_price_per_million, cfg.output_price_per_million) == (0.14, 0.28)


def test_default_does_not_reach_for_the_openai_key() -> None:
    """Mặc định DeepSeek mà không có DEEPSEEK_API_KEY thì phải BÁO THIẾU,
    không được lặng lẽ dùng OPENAI_API_KEY của ablation/judge."""
    cfg = Config(_env_values={"OPENAI_API_KEY": "sk-proj-openai-thật"})
    assert cfg.api_key != "sk-proj-openai-thật"
    assert any("API_KEY" in problem for problem in cfg.validate())


def test_openai_provider_still_available() -> None:
    cfg = Config(_env_values={"ROLEDATA_PROVIDER": "openai", "OPENAI_API_KEY": "sk-openai"})
    assert cfg.provider == "openai"
    assert cfg.base_url == "https://api.openai.com/v1"
    assert cfg.model == "gpt-4o-mini"
    assert cfg.api_key == "sk-openai"


def test_constructor_args_beat_the_provider_table() -> None:
    cfg = Config(api_key="k", base_url="https://x/v1", model="m", _env_values=dict(ENV_DEEPSEEK))
    assert (cfg.api_key, cfg.base_url, cfg.model) == ("k", "https://x/v1", "m")


def test_deepseek_provider_reads_its_own_env() -> None:
    cfg = Config(_env_values=dict(ENV_DEEPSEEK))
    assert cfg.provider == "deepseek"
    assert cfg.api_key == "sk-deepseek-test"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.model == "deepseek-v4-flash"
    assert (cfg.input_price_per_million, cfg.output_price_per_million) == (0.14, 0.28)


def test_deepseek_provider_does_not_hijack_openai_key() -> None:
    """`OPENAI_API_KEY` còn được `ablation/frontier.py` và judge provider `openai`
    dùng. Đổi provider cho datagen KHÔNG được đụng vào nó."""
    cfg = Config(_env_values=dict(ENV_DEEPSEEK))
    assert cfg.api_key != ENV_DEEPSEEK["OPENAI_API_KEY"]
    assert cfg._env_values["OPENAI_API_KEY"] == ENV_DEEPSEEK["OPENAI_API_KEY"]


def test_explicit_price_env_wins_over_provider_table() -> None:
    env = dict(ENV_DEEPSEEK) | {"OPENAI_INPUT_PRICE_PER_MILLION": "0.9"}
    assert Config(_env_values=env).input_price_per_million == 0.9


def test_unknown_provider_fails_loudly() -> None:
    with pytest.raises(ValueError, match="ROLEDATA_PROVIDER"):
        Config(_env_values={"ROLEDATA_PROVIDER": "anthropic", "OPENAI_API_KEY": "x"})


def test_taxonomy_version_is_v2() -> None:
    cfg = Config(api_key="offline-test")
    payload = yaml.safe_load(cfg.taxonomy_path.read_text(encoding="utf-8"))
    assert payload["version"] == "roledata-v2"
