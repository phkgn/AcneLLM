"""Bất biến của vòng 2: biến thể anchor, lịch mở bài, echo dữ kiện, split theo nguồn.

Mỗi test ở đây gắn với một con số đo được trên output vòng 1, ghi ngay trong
docstring — để lần sau ai đọc cũng biết test này sinh ra vì cái gì.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from datagen.roledatav2.config import ANCHOR_VARIANT_PATHS, MODULE_ROOT, Config
from datagen.roledatav2.finalize.split import group_key, split
from datagen.roledatav2.gates import anchor_variants, user_facts_echoed
from datagen.roledatav2.generator import (
    opening_moves,
    planned_anchor_variant,
    planned_opening_move,
)

TAXONOMY = str(MODULE_ROOT / "taxonomy.yaml")


# ── biến thể anchor ────────────────────────────────────────────────────────
def test_three_variants_exist_and_differ() -> None:
    variants = anchor_variants()
    assert len(variants) == 3
    assert len(set(variants)) == 3, "ba biến thể phải khác nhau thật"


def test_variant_a_is_the_served_one() -> None:
    """A phải là bản trong Modelfile — sai chỗ này là tái diễn train/serve mismatch."""
    import re

    modelfile = Config(api_key="offline-test").anchor_path.read_text(encoding="utf-8-sig")
    served = re.search(r'\bSYSTEM\s+"""(.*?)"""', modelfile, re.DOTALL).group(1).strip()
    assert served == ANCHOR_VARIANT_PATHS[0].read_text(encoding="utf-8-sig").strip()
    assert served == anchor_variants()[0]


def test_all_variants_carry_the_same_rules() -> None:
    """Khác hành văn thì được, khác LUẬT thì model học hai bộ luật mâu thuẫn."""
    must_appear = (
        "AcneLLM",
        "isotretinoin",
        "doxycycline",
        "NICE",
        "900",  # band độ dài
        "1.500",
        "gạch đầu dòng",
        "DAN mode",
        "bác sĩ da liễu nhi",
    )
    for index, variant in enumerate(anchor_variants()):
        for token in must_appear:
            assert token in variant, f"biến thể {index} thiếu {token!r}"


def test_variant_schedule_favours_the_served_variant() -> None:
    """A xuất hiện nhiều nhất: đó cũng là dạng model gặp lúc chạy thật."""
    variants = anchor_variants()
    picks = [planned_anchor_variant("K1_knowledge_anchor", i, variants) for i in range(1, 401)]
    counts = [picks.count(item) for item in variants]
    assert counts[0] > counts[1] and counts[0] > counts[2]
    assert min(counts) > 0, "biến thể nào cũng phải được dùng"


def test_variant_schedule_is_deterministic() -> None:
    variants = anchor_variants()
    first = [planned_anchor_variant("R2_depth_adaptation", i, variants) for i in range(1, 60)]
    second = [planned_anchor_variant("R2_depth_adaptation", i, variants) for i in range(1, 60)]
    assert first == second


# ── lịch mở bài ────────────────────────────────────────────────────────────
def test_opening_moves_are_spread_evenly() -> None:
    """Vòng 1: 676/2.763 mẫu mở đầu bằng đúng 5 cụm, "Mình hiểu bạn đang" 219 lần.

    Nguyên nhân là `random.choice(VARIATION_DIRECTIVES)` với toàn chỉ dẫn phủ
    định ("tránh cụm sáo mòn"). Bảo model "hãy khác đi" không có tác dụng.
    """
    moves = opening_moves(TAXONOMY)
    picks = [planned_opening_move("R2_depth_adaptation", i, moves)[0] for i in range(1, 601)]
    counts = {name: picks.count(name) for name, _ in moves}
    assert set(counts) == {name for name, _ in moves}
    assert max(counts.values()) - min(counts.values()) <= 1, counts


def test_r4_is_pinned_to_the_empathy_opening() -> None:
    moves = opening_moves(TAXONOMY)
    picked = {planned_opening_move("R4_measured_empathy", i, moves)[0] for i in range(1, 100)}
    assert picked == {"ghi_nhan_cam_xuc"}


# ── echo dữ kiện người dùng ────────────────────────────────────────────────
def test_echo_ignores_diacritics() -> None:
    """30% mẫu có input bỏ dấu/teencode; so thẳng thì mẫu TỐT trượt oan.

    Đo thật trên data vòng 1: bỏ qua chuyện này thì gate loại 317/1.226 mẫu
    (26%), phần lớn là báo động giả; chuẩn hoá dấu xong còn 60/1.226 (5%).
    """
    user = "Tin nhắn hiện tại:\nem buon qua, mat day mun hoai ma khong het, nhin guong thay tu ti"
    answer = "Mình hiểu cảm giác khi nhìn gương thấy mụn mãi không hết. Mặt em đang buồn vì mụn."
    assert user_facts_echoed(user, answer) is True


def test_echo_rejects_generic_boilerplate() -> None:
    user = "Tin nhắn hiện tại:\nDa mình dầu, mụn ở trán và hai bên má, bị ba tháng rồi"
    generic = "Bạn nên đi khám bác sĩ để được tư vấn phù hợp. Chúc bạn sớm khỏe."
    assert user_facts_echoed(user, generic) is False


def test_echo_measures_the_user_not_the_document() -> None:
    """Lượt user của case grounded chứa cả chunk nguồn; chỉ đo khối cuối."""
    user = (
        "Tài liệu tham khảo:\nNguồn 1 —\n" + ("Topical benzoyl peroxide monotherapy. " * 40)
        + "\n\nTin nhắn hiện tại:\nMình bị mụn ở cằm, da dầu, ba tháng rồi"
    )
    answer = "Với da dầu và mụn ở cằm ba tháng nay, bạn nên rửa mặt dịu nhẹ hai lần mỗi ngày."
    assert user_facts_echoed(user, answer) is True


def test_echo_skips_very_short_user_turns() -> None:
    assert user_facts_echoed("Tin nhắn hiện tại:\nChào bạn", "Mình sẵn sàng hỗ trợ.") is True


# ── split theo nguồn ───────────────────────────────────────────────────────
def test_group_key_prefers_anchor_group() -> None:
    record = {"id": "x", "anchor_group": "pair-1", "synthetic_context_sources": ["s1"]}
    assert group_key(record) == "anchor:pair-1"


def test_group_key_ignores_the_synthetic_distractor() -> None:
    """`synthetic-distractor-weather` dùng chung cho MỌI mẫu B3 (138/138 ở vòng 1).

    Gom theo nó thì cả B3 thành một nhóm và không chia được nữa.
    """
    record = {
        "id": "x",
        "anchor_group": None,
        "synthetic_context_sources": ["pubmed_abc::0", "synthetic-distractor-weather"],
    }
    assert group_key(record) == "src:pubmed_abc::0"


def _fixture_records() -> list[dict]:
    rows = []
    for index in range(40):
        pair = f"pair-{index // 2}"
        rows.append(
            {
                "id": f"r-{index:03d}",
                "sample_kind": "B5_depth_anchor" if index < 20 else "R2_depth_adaptation",
                "anchor_group": pair if index < 20 else None,
                "synthetic_context_sources": [f"chunk-{index // 2}"] if index < 20 else [],
                "messages": [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}],
            }
        )
    return rows


def test_split_never_tears_a_source_group(tmp_path: Path) -> None:
    """Vòng 1: 9/40 cặp B5 bị tách qua train/val, cùng y hệt chunk nguồn.

    Bản beginner ở train, bản advanced ở val => val cho điểm ảo => chọn nhầm
    checkpoint.
    """
    cfg = Config(api_key="offline-test", output_dir=tmp_path)
    cfg.train_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.train_path.open("w", encoding="utf-8") as handle:
        for row in _fixture_records():
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    result = split(cfg, seed=42)
    assert result["group_leakage"] == 0
    assert sum(result["counts"].values()) == 40

    where = {}
    for name in ("train", "val", "holdout"):
        for line in getattr(cfg, f"{name}_split_path").read_text(encoding="utf-8").splitlines():
            where[json.loads(line)["id"]] = name
    for index in range(0, 20, 2):
        assert where[f"r-{index:03d}"] == where[f"r-{index + 1:03d}"], f"cặp {index} bị tách"


@pytest.mark.skipif(
    not (MODULE_ROOT / "output.round1" / "roledata.train.jsonl").is_file(),
    reason="chưa có output vòng 1 để đối chiếu",
)
def test_split_on_round1_output_has_no_group_leakage(tmp_path: Path) -> None:
    cfg = Config(api_key="offline-test", output_dir=tmp_path)
    cfg.train_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(MODULE_ROOT / "output.round1" / "roledata.train.jsonl", cfg.train_path)
    result = split(cfg, seed=42)
    assert result["group_leakage"] == 0
    assert result["counts"]["train"] > result["counts"]["val"] > 0


def test_export_accepts_every_anchor_variant() -> None:
    """Export phải chấp nhận cả ba biến thể, không chỉ biến thể A.

    Bắt được lúc chạy thật trên 3.077 mẫu: `export()` của v1 so system prompt với
    MỘT chuỗi và chết ở bản ghi đầu tiên mang biến thể B — sau khi đã sinh xong
    toàn bộ dataset. Cùng loại lỗi với phép kiểm resume trong `run_pipeline`;
    đây là chỗ thứ hai và cuối cùng còn sót.
    """
    from datagen.roledata.finalize import export as export_module
    from datagen.roledatav2.finalize.__main__ import _system_ok_v2

    assert export_module._system_ok is _system_ok_v2, "phải vá trước khi gọi export()"
    variants = anchor_variants()
    assert len(variants) == 3
    for variant in variants:
        assert _system_ok_v2(variant, variants[0]) is True
    assert _system_ok_v2("một system prompt hoàn toàn khác", variants[0]) is False
