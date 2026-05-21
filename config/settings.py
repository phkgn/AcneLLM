# Backward-compatibility shim — import thực tế từ acne_llm.config
# File này giữ nguyên để không vỡ các lệnh cũ, nhưng nguồn thật đã chuyển về
# src/acne_llm/config.py
from acne_llm.config import Settings, settings  # noqa: F401
