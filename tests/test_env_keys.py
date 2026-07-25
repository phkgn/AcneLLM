from pathlib import Path


ALLOWLIST = {
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DATAGEN_API_KEY",
}


def test_khong_co_env_key_mo_coi():
    """extra='ignore' nuốt im lặng key gõ sai; test này là chốt chống tái phát."""
    from acne_llm.config import Settings

    fields = set(Settings.model_fields)
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        assert key.lower() in fields or key in ALLOWLIST, (
            f"{key} trong .env không khớp field nào và không có trong ALLOWLIST"
        )


def test_settings_thang_hang_so_module():
    """Chặn tái phát việc hằng số retriever lấn át Settings."""
    from acne_llm.config import settings
    from acne_llm.rag import retriever

    assert retriever._DENSE_MAX_DISTANCE == settings.dense_max_distance
