"""Neo mức độ nặng nhẹ không được trôi khỏi Modelfile.

Bài học từ chính dự án này: `reject` từng được định nghĩa trong Modelfile là ba
thứ, còn bộ đề v2 tự nghĩ ra sáu loại — 15 ca gán sai và mọi kết luận về an toàn
lệch theo. Nhãn và model phải đọc CÙNG một định nghĩa, và cách duy nhất giữ được
điều đó là có test đọc cả hai bên rồi so.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from evaluation import severity

ROOT = Path(__file__).resolve().parents[2]
MODELFILE = ROOT / "model/acne_intake_release/Modelfile"
# datagen ép byte-parity với file này (`anchor.assert_parity`): MỌI record sinh
# ra mang đúng nội dung nó. Sửa Modelfile mà quên file này thì dữ liệu học một
# thang còn model chạy một thang — và không có gì kêu lên.
CANONICAL = ROOT / "datagen/intakedata/system_prompt.canonical.txt"
# Bản thứ BA, hardcode trong Python cho đường chạy không qua ollama. Sửa hai file
# kia mà quên bản này thì `test_runtime_anchor_is_byte_identical_to_training_anchor`
# đỏ — nhưng chỉ đỏ SAU khi đã sửa xong, nên liệt kê ở đây để hỏng là biết ngay.
RUNTIME = ROOT / "src/acne_llm/chat/unified_intake.py"


@pytest.mark.parametrize(
    "path", [MODELFILE, CANONICAL, RUNTIME],
    ids=["modelfile", "canonical", "runtime"],
)
def test_prompt_chua_dung_neo_dang_dung(path: Path):
    if not path.exists():
        pytest.skip(f"chưa có {path.name}")
    text = path.read_text(encoding="utf-8").lstrip("﻿")
    for line in severity.MODELFILE_ANCHOR.splitlines():
        assert line in text, (
            f"{path.name} thiếu dòng neo:\n  {line}\n"
            "Sửa evaluation/severity.py xong phải chép sang CẢ HAI file, "
            "nếu không nhãn và model chấm theo hai thang khác nhau."
        )


def test_hai_file_prompt_khong_lech_nhau():
    """Modelfile phải chứa trọn canonical. Datagen sinh theo canonical, ollama
    chạy theo Modelfile — lệch một dòng là lệch cả thí nghiệm."""
    if not (MODELFILE.exists() and CANONICAL.exists()):
        pytest.skip("thiếu một trong hai file")
    modelfile = MODELFILE.read_text(encoding="utf-8")
    for line in CANONICAL.read_text(encoding="utf-8").lstrip("﻿").splitlines():
        if line.strip():
            assert line in modelfile, f"Modelfile thiếu dòng canonical:\n  {line}"


def test_neo_khong_de_lai_tham_chieu_cut():
    """Neo đi thẳng vào prompt của model. Ký hiệu trích dẫn kiểu '[3]' chỉ có
    nghĩa trong docstring của severity.py — vào prompt là rác model không tra được."""
    assert "[3]" not in severity.MODELFILE_ANCHOR
    assert "xem [" not in severity.MODELFILE_ANCHOR


@pytest.mark.skipif(not MODELFILE.exists(), reason="chưa có bản release intaker")
def test_enum_trong_modelfile_khop_voi_LEVELS():
    line = next(
        l for l in MODELFILE.read_text(encoding="utf-8").splitlines()
        if l.startswith("- inflammation_level chỉ dùng:")
    )
    declared = {v.strip().rstrip(".") for v in line.split(":", 1)[1].split(",")}
    assert declared == set(severity.LEVELS)


def test_severe_bat_theo_BAT_KY_dau_hieu_khong_doi_du_ca():
    """Nốt cục HOẶC đau HOẶC sẹo HOẶC lan thân mình — mỗi cái đủ để lên severe.
    Đòi đủ cả thì mọi ca nặng thật đều tụt xuống moderate."""
    assert "BẤT KỲ" in severity.LEVELS["severe"]
    for dau_hieu in ("nốt cục", "đau", "sẹo", "lưng"):
        assert dau_hieu in severity.LEVELS["severe"]


def test_unknown_la_mac_dinh_chu_khong_phai_du_phong():
    """85,5% tập val là None/unknown. Nếu định nghĩa cho phép đoán bừa thì model
    sẽ lấp đầy chỗ trống đó bằng phỏng đoán và accuracy trông đẹp lên một cách
    giả tạo."""
    text = severity.LEVELS["unknown"]
    assert "MẶC ĐỊNH" in text and "không suy đoán" in text


def test_ha_bac_bi_bat_rieng_vi_no_nguy_hiem_mot_chieu():
    assert severity.is_downgrade("severe", "moderate") is True
    assert severity.is_downgrade("moderate", "severe") is False
    assert severity.is_downgrade("severe", "unknown") is False
    assert severity.CRITICAL_LEVEL == "severe"
    assert severity.ORDER == ("none", "mild", "moderate", "severe")
    assert "unknown" not in severity.ORDER   # unknown không nằm trên thang


def test_khong_dung_thang_dem_so_not():
    """Đầu vào là câu chat tự do, không có số để đếm. Nếu neo lỡ nhắc mốc đếm
    thì người gán nhãn sẽ đi tìm con số không tồn tại trong lời kể."""
    for level, text in severity.LEVELS.items():
        for moc in ("21-50", "19-30", "1-18", "11-20", "0-5 nốt"):
            assert moc not in text, f"{level} lẫn mốc đếm {moc}"
