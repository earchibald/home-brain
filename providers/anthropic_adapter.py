"""
Anthropic Claude API provider adapter.

Requires ANTHROPIC_API_KEY environment variable.
"""

import os
from anthropic import Anthropic
from providers.base import BaseProvider


class AnthropicProvider(BaseProvider):
    """
    Adapter for Anthropic Claude API.

    Requires ANTHROPIC_API_KEY environment variable to be set.
    """

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable must be set for Anthropic provider"
            )

        self.client = Anthropic(api_key=api_key)
        self.id = "anthropic"
        self.name = "Anthropic Claude"

    def list_models(self) -> list[str]:
        """
        Returns available Claude models.

        Returns:
            list[str]: List of Claude model names
        """
        # Hardcoded Claude models
        return [
            "claude-3-5-sonnet-latest",
            "claude-3-opus-latest",
            "claude-3-haiku-latest",
        ]

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Generate text using Claude API.

        Args:
            prompt: User prompt/question
            system_prompt: Optional system instructions

        Returns:
            str: Generated response
        """
        try:
            # Use first available model
            models = self.list_models()
            model = models[0] if models else "claude-3-5-sonnet-latest"

            # Build message
            messages = [{"role": "user", "content": prompt}]

            # Call API
            kwargs = {"model": model, "max_tokens": 1024, "messages": messages}

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            return response.content[0].text
        except Exception:
            return "Error generating response"

    def health_check(self) -> bool:
        """
        Quick health check - verifies API key is set.

        Returns:
            bool: True if API key is configured
        """
        return os.getenv("ANTHROPIC_API_KEY") is not None
