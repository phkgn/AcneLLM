from acne_llm.rag.cleaning import clean_vi_text
from acne_llm.crawler.normalizer import normalize_vi_text


def test_clean_vi_collapse_whitespace():
    s = "Mụn  viêm   ở  cằm\n\n\n\nnguyên nhân"
    out = clean_vi_text(s)
    assert "  " not in out
    assert "\n\n\n" not in out


def test_clean_vi_remove_boilerplate():
    s = "Mô tả mụn viêm. Đọc thêm: https://example.com\ntiếp tục."
    out = clean_vi_text(s)
    assert "Đọc thêm" not in out
    assert "tiếp tục" in out


def test_normalize_nfc():
    s = "mụn"  # already NFC, just ensure no exception
    assert normalize_vi_text(s) == "mụn"


def test_normalize_empty():
    assert normalize_vi_text("") == ""
    assert normalize_vi_text(None) == ""
