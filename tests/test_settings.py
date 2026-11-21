from acne_llm.config import Settings


def test_latency_defaults(monkeypatch):
    for key in (
        "LLM_NUM_PREDICT",
        "RERANKER_BATCH_SIZE",
        "RERANKER_CACHE_SIZE",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_num_predict == 2048
    assert settings.reranker_batch_size == 16
    assert settings.reranker_cache_size == 2048


def test_ngan_sach_ngu_canh_du_cho_prompt_dai_nhat():
    """num_ctx phải chứa nổi prompt tối đa CỘNG phần sinh.

    Prompt dài nhất = Modelfile SYSTEM (~5.000 ký tự, ollama tự nhét) +
    chat_max_context_chars + HISTORY_CHAR_BUDGET + vài trăm ký tự dữ kiện.
    Tiếng Việt tokenize ~2,5 ký tự/token ở trường hợp xấu nhất.

    Ràng buộc này từng bị vi phạm im lặng: num_ctx=4096 với num_predict=1200 chỉ
    còn 2.896 token cho prompt, trong khi prompt cần 3.900-5.500 -> ollama cắt
    bớt và không báo gì. `OllamaBackend._log_token_budget` bắt tại chỗ khi chạy
    thật; test này bắt ngay khi ai đó chỉnh config.
    """
    from acne_llm.chat.session import HISTORY_CHAR_BUDGET

    s = Settings(_env_file=None)
    ky_tu = 5_000 + s.chat_max_context_chars + HISTORY_CHAR_BUDGET + 700
    token_vao = ky_tu / 2.5                      # 2,5 = trường hợp xấu nhất
    can = token_vao + s.llm_num_predict
    assert can <= s.llm_num_ctx, (
        f"cần ~{can:.0f} token (prompt {token_vao:.0f} + sinh {s.llm_num_predict}) "
        f"nhưng num_ctx={s.llm_num_ctx}. Nâng num_ctx, giảm "
        f"chat_max_context_chars, hoặc giảm num_predict."
    )


def test_latency_settings_parse_from_env(monkeypatch):
    monkeypatch.setenv("LLM_NUM_PREDICT", "512")
    monkeypatch.setenv("RERANKER_BATCH_SIZE", "8")
    monkeypatch.setenv("RERANKER_CACHE_SIZE", "32")

    settings = Settings(_env_file=None)

    assert settings.llm_num_predict == 512
    assert settings.reranker_batch_size == 8
    assert settings.reranker_cache_size == 32
