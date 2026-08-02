from typing import Protocol
from ..schemas import UserInput, AdviseOutput


class PipelineProtocol(Protocol):
    def run(self, user: UserInput) -> AdviseOutput: ...
