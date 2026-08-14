from pathlib import Path

import pytest

from datagen.roledata.anchor import assert_parity, load_anchor
from datagen.roledata.config import Config


def test_repo_anchor_has_byte_identical_canonical_content() -> None:
    cfg = Config(api_key="offline-test")
    anchor = assert_parity(cfg)
    assert anchor == cfg.canonical_path.read_text(encoding="utf-8-sig").strip()


def test_anchor_mismatch_fails(tmp_path: Path) -> None:
    modelfile = tmp_path / "Modelfile"
    canonical = tmp_path / "canonical.txt"
    modelfile.write_text('FROM x\nSYSTEM """alpha"""\n', encoding="utf-8")
    canonical.write_text("beta\n", encoding="utf-8")
    cfg = Config(
        api_key="offline-test",
        anchor_path=modelfile,
        canonical_path=canonical,
    )
    with pytest.raises(ValueError, match="parity"):
        assert_parity(cfg)


def test_anchor_regex_requires_system_block(tmp_path: Path) -> None:
    modelfile = tmp_path / "Modelfile"
    modelfile.write_text("FROM x\n", encoding="utf-8")
    cfg = Config(api_key="offline-test", anchor_path=modelfile)
    with pytest.raises(ValueError, match="Cannot find SYSTEM"):
        load_anchor(cfg)


def test_validate_reports_missing_openai_key() -> None:
    cfg = Config(api_key="", _env_values={})
    assert any("OPENAI_API_KEY" in problem for problem in cfg.validate())
