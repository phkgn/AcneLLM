from typing import Protocol
from ..schemas import VisionOutput


class VisionProtocol(Protocol):
    def analyze(self, image_bytes: bytes) -> VisionOutput: ...
