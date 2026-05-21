from acne_llm.crawler.quality_filter import (
    passes_quality, score_quality, STRONG_KEYWORDS, MEDIUM_KEYWORDS, _REMOVED_BROAD
)


# ── Basic checks ──────────────────────────────────────────────────────────────

def test_passes_strong_keyword():
    """1 STRONG keyword là đủ pass."""
    title = "Mụn trứng cá: nguyên nhân và cách điều trị hiệu quả"
    text = "Mụn trứng cá là tình trạng da liễu phổ biến ở tuổi dậy thì. " * 30
    ok, reason = passes_quality(text, title)
    assert ok, reason
    assert "strong" in reason


def test_passes_via_isotretinoin():
    """Từ thuốc đặc thù (STRONG) trong body là đủ."""
    title = "Hướng dẫn sử dụng thuốc điều trị da liễu cho bệnh nhân"
    text = ("Isotretinoin là thuốc điều trị mụn trứng cá nặng được bác sĩ kê đơn. "
            "Cần tuân thủ đúng liều lượng theo hướng dẫn. ") * 20
    ok, reason = passes_quality(text, title)
    assert ok, reason


def test_passes_via_medium_keywords():
    """Không có STRONG nhưng có ≥ 3 MEDIUM."""
    title = "Chăm sóc da mụn toàn diện cho người trẻ"
    # chứa: "mụn", "da dầu", "skincare", "rửa mặt" → 4 medium hits
    text = ("Da dầu dễ bị nổi mụn hơn da thường. "
            "Skincare đúng cách giúp giảm mụn hiệu quả. "
            "Hãy rửa mặt 2 lần mỗi ngày để làm sạch bụi bẩn. ") * 30
    ok, reason = passes_quality(text, title)
    assert ok, reason
    assert "medium" in reason


def test_rejects_broad_single_keyword():
    """Từ generic không đủ để pass dù lặp nhiều lần."""
    title = "Hướng dẫn kiểm tra và review sản phẩm công nghệ mới nhất"
    text = ("Bài review này sẽ giúp bạn kiểm tra và đánh giá sản phẩm. "
            "Test thử ngay hôm nay để có kết quả tốt nhất. "
            "Routine hàng ngày rất quan trọng cho công việc hiệu quả. ") * 30
    ok, reason = passes_quality(text, title)
    assert not ok, f"should reject, got: {reason}"
    assert "keyword" in reason


def test_rejects_too_short():
    ok, reason = passes_quality("ngắn quá", "Mụn trứng cá điều trị", "vi")
    assert not ok
    assert "short" in reason


def test_rejects_unrelated_article():
    """Bài lập trình không liên quan — phải reject."""
    title = "Python cho người mới bắt đầu lập trình web toàn tập"
    text = "Học lập trình Python cơ bản cho người mới bắt đầu. " * 30
    ok, reason = passes_quality(text, title)
    assert not ok
    assert "keyword" in reason


def test_passes_english_acne():
    """Bài tiếng Anh về acne pass qua STRONG."""
    title = "How to treat acne vulgaris with benzoyl peroxide"
    text = ("Acne vulgaris is a common skin condition affecting teenagers. "
            "Benzoyl peroxide works by killing bacteria on the skin surface. "
            "Consult a dermatologist for severe acne cases. ") * 20
    ok, reason = passes_quality(text, title)
    assert ok, reason


def test_passes_pubmed_abstract():
    """PubMed abstract ngắn về acne treatment."""
    title = "Efficacy of isotretinoin in severe acne treatment"
    text = ("Isotretinoin is a retinoid used for severe acne vulgaris. "
            "This study evaluates the efficacy and safety of isotretinoin "
            "in patients with cystic acne. Results showed significant reduction "
            "in acne lesion counts after 6 months of treatment. ") * 5
    ok, reason = passes_quality(text, title)
    assert ok, reason


# ── Keyword sanity checks ─────────────────────────────────────────────────────

def test_broad_words_not_in_strong():
    """Các từ broad không được nằm trong STRONG."""
    bad = {"test", "help", "clear", "review", "routine", "gel", "cream",
           "mask", "toner", "serum", "healing", "trigger", "advice"}
    leaked = bad & {k.lower() for k in STRONG_KEYWORDS}
    assert not leaked, f"Broad words leaked into STRONG: {leaked}"


def test_broad_words_not_in_medium():
    """Các từ generic không được nằm trong MEDIUM."""
    bad = {"test", "help", "clear", "review", "tips", "hack",
           "routine", "healing", "trigger", "advice", "recommendation"}
    leaked = bad & {k.lower() for k in MEDIUM_KEYWORDS}
    assert not leaked, f"Broad words leaked into MEDIUM: {leaked}"


def test_removed_broad_documented():
    """_REMOVED_BROAD phải có ít nhất các từ nguy hiểm nhất."""
    must_have = {"test", "help", "clear", "review", "routine",
                 "gel", "cream", "mask", "toner"}
    missing = must_have - _REMOVED_BROAD
    assert not missing, f"Missing from _REMOVED_BROAD: {missing}"


# ── Score range ───────────────────────────────────────────────────────────────

def test_score_quality_range_acne():
    s = score_quality("Mụn trứng cá điều trị bằng isotretinoin. " * 100)
    assert 0 <= s <= 1
    assert s > 0.3  # bài acne nên có score cao


def test_score_quality_range_generic():
    s = score_quality("Lập trình Python rất thú vị và hữu ích. " * 100)
    assert 0 <= s <= 1
    assert s < 0.5  # bài không liên quan nên score thấp
