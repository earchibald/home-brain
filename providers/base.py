"""
Base provider interface for LLM adapters.

Defines the contract that all provider implementations must follow.
"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement list_models(), generate(), and health_check().
    Providers should set id and name class/instance attributes.
    """

    id: str  # Unique identifier (e.g., "ollama_local", "gemini")
    name: str  # Human readable name (e.g., "Mac Mini (Ollama)")

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        Returns a list of model identifiers available on this provider.

        Returns:
            list[str]: Available model names/IDs
        """
        pass

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Generates text based on input prompt.

        Args:
            prompt: The user prompt/question
            system_prompt: Optional system instructions

        Returns:
            str: Generated response text
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Quick check to see if provider is reachable.

        Returns:
            bool: True if provider is healthy/reachable, False otherwise
        """
        pass
