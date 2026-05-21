from acne_llm.config import Settings


def test_latency_defaults(monkeypatch):
    for key in (
        "CHAT_USE_LLM_PLANNER",
        "LLM_NUM_PREDICT",
        "RERANKER_BATCH_SIZE",
        "RERANKER_CACHE_SIZE",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.chat_use_llm_planner is False
    assert settings.llm_num_predict == 1024
    assert settings.reranker_batch_size == 16
    assert settings.reranker_cache_size == 2048


def test_latency_settings_parse_from_env(monkeypatch):
    monkeypatch.setenv("CHAT_USE_LLM_PLANNER", "true")
    monkeypatch.setenv("LLM_NUM_PREDICT", "512")
    monkeypatch.setenv("RERANKER_BATCH_SIZE", "8")
    monkeypatch.setenv("RERANKER_CACHE_SIZE", "32")

    settings = Settings(_env_file=None)

    assert settings.chat_use_llm_planner is True
    assert settings.llm_num_predict == 512
    assert settings.reranker_batch_size == 8
    assert settings.reranker_cache_size == 32
