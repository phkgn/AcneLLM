from pathlib import Path

from datagen.roledata.writer import DatasetWriter, iter_jsonl


def test_writer_is_append_only_and_deduplicates_for_resume(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    first = {"id": "a", "value": 1}
    second = {"id": "b", "value": 2}
    with DatasetWriter(path) as writer:
        assert writer.append(first)
        assert not writer.append(first)
    with DatasetWriter(path) as writer:
        assert writer.existing_ids == {"a"}
        assert not writer.append(first)
        assert writer.append(second)
    assert list(iter_jsonl(path)) == [first, second]
