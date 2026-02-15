"""
Ollama provider adapter for local and remote Ollama instances.

Supports both localhost and networked Ollama servers.
"""

import requests
from ollama import Client
from providers.base import BaseProvider


class OllamaProvider(BaseProvider):
    """
    Adapter for Ollama LLM instances (local or remote).

    Args:
        base_url: Ollama server URL (default: http://localhost:11434)
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.id = "ollama_local"
        self.name = "Ollama (Local)"
        self.client = Client(host=base_url)
        self._cached_models = None

    def list_models(self) -> list[str]:
        """
        Returns available models from Ollama /api/tags endpoint.

        Returns:
            list[str]: List of model names
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            # Extract model names from response
            models = [model["name"] for model in data.get("models", [])]
            return models
        except Exception:
            return []

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Generate text using Ollama client.

        Args:
            prompt: User prompt/question
            system_prompt: Optional system instructions

        Returns:
            str: Generated response
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            # Use cached models or fetch once
            if self._cached_models is None:
                self._cached_models = self.list_models()

            model = self._cached_models[0] if self._cached_models else "llama3.2"

            response = self.client.chat(model=model, messages=messages)
            return response["message"]["content"]
        except Exception:
            # Don't expose internal error details
            return "Error generating response"

    def health_check(self) -> bool:
        """
        Quick health check with 1 second timeout.

        Returns:
            bool: True if Ollama is reachable, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/api/version", timeout=1.0)
            return response.status_code == 200
        except Exception:
            return False
