from abc import ABC, abstractmethod
from typing import Any


class BaseLLM(ABC):
    """
    Abstract base class for Language Models.
    Ensures that any LLM provider implements the required methods.
    """

    @abstractmethod
    def generate_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
        repeat_penalty: float = 1.15,
    ) -> dict[str, Any]:
        """
        Takes a list of message dictionaries (ChatML format) and returns a parsed JSON dictionary.
        """
        pass
