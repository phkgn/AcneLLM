from pathlib import Path

import pytest

from datagen.intakedata.anchor import anchor_sha256, assert_parity, load_anchor
from datagen.intakedata.config import Config


def test_canonical_anchor_loads_and_hashes() -> None:
    cfg = Config()
    anchor = assert_parity(cfg)
    assert anchor == load_anchor(cfg)
    assert len(anchor_sha256(anchor)) == 64
    assert anchor.endswith("\n")


def test_record_parity_is_byte_exact(make_record) -> None:
    record = make_record()
    cfg = Config()
    assert assert_parity(cfg, [record]) == record["messages"][0]["content"]
    record["messages"][0]["content"] += " "
    with pytest.raises(ValueError, match="parity"):
        assert_parity(cfg, [record])


def test_alternate_canonical_path_is_not_trimmed(tmp_path: Path) -> None:
    path = tmp_path / "canonical.txt"
    path.write_text("anchor with trailing newline\n", encoding="utf-8")
    cfg = Config(canonical_path=path)
    assert load_anchor(cfg).encode("utf-8") == path.read_bytes()
