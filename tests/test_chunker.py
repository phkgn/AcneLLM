from acne_llm.rag.chunker import VietnameseChunker


def test_chunker_basic():
    text = ("Mụn viêm là một dạng mụn trứng cá. " * 30 + "\n\n" +
            "Nguyên nhân bao gồm vi khuẩn C. acnes. " * 30)
    ch = VietnameseChunker(chunk_size=80, overlap=15, min_size=20)
    chunks = ch.chunk(text)
    assert len(chunks) >= 2
    assert all(len(c.split()) >= 15 for c in chunks)


def test_chunker_empty():
    ch = VietnameseChunker()
    assert ch.chunk("") == []
    assert ch.chunk("   ") == []


def test_chunker_short():
    ch = VietnameseChunker(min_size=50)
    assert ch.chunk("Mụn.") == []


def test_chunker_filters_english_footer_patterns():
    ch = VietnameseChunker(min_size=5)
    text = "Related articles subscribe to our newsletter privacy policy cookies advertisement"

    assert ch.chunk(text) == []
