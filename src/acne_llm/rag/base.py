from typing import Protocol
from ..schemas import RetrievalOutput


class RAGProtocol(Protocol):
    def retrieve(self, query: str, top_k: int = 20) -> RetrievalOutput: ...
