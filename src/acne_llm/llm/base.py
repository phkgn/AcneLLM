from typing import Protocol


class LLMProtocol(Protocol):
    model: str
    def generate_text(self, system: str, user: str,
                      temperature: float = 0.3) -> str: ...
