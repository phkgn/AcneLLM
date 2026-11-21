import re
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


_GETATTR_SETTINGS = re.compile(
    r'getattr\(\s*[A-Za-z_][A-Za-z0-9_.]*settings[A-Za-z0-9_.]*\s*,\s*'
    r'["\']([a-z_][a-z0-9_]*)["\']',
    re.IGNORECASE,
)


def test_getattr_settings_khong_tro_vao_field_ma():
    """``getattr(settings, "ten_sai", default)`` nuốt lỗi y hệt extra='ignore'.

    Đã dính một lần thật: ``chat_min_chunk_score`` không tồn tại trong Settings
    nên ``chat/_retrieval.py`` luôn rơi về hằng số 0.25 và mọi lần tune ngưỡng
    lọc chunk nhiễu đều vô tác dụng.
    """
    from acne_llm.config import Settings

    fields = set(Settings.model_fields)
    src = Path(__file__).resolve().parents[1] / "src" / "acne_llm"
    orphans: list[str] = []
    for path in src.rglob("*.py"):
        if "__pycache__" in path.parts or ".bak" in path.name:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for match in _GETATTR_SETTINGS.finditer(line):
                if match.group(1) not in fields:
                    orphans.append(f"{path.name}:{lineno} -> {match.group(1)}")
    assert not orphans, "getattr(settings, ...) trỏ vào field không tồn tại: " + "; ".join(orphans)
