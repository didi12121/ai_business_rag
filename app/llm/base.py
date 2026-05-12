from abc import ABC, abstractmethod


class LlmClient(ABC):

    @abstractmethod
    async def chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        ...
