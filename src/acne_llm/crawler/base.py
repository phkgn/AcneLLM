from typing import Protocol, Iterable
from ..schemas.kb import DocumentRaw


class CrawlerProtocol(Protocol):
    name: str
    async def discover(self) -> list[str]: ...
    async def fetch_and_extract(self, urls: list[str]) -> Iterable[DocumentRaw]: ...
