"""
ModelManager - Service for managing LLM provider discovery and switching.

Acts as the state machine for the dynamic model source switching feature.
"""

import os
from typing import Dict, Optional
from providers.base import BaseProvider
from providers.ollama_adapter import OllamaProvider
from providers.gemini_adapter import GeminiProvider
from providers.anthropic_adapter import AnthropicProvider


class ModelManager:
    """
    Manages LLM providers and handles switching between them.

    Implements discovery of available providers (local Ollama, remote Ollama, cloud APIs)
    and provides a unified interface for model selection and text generation.
    """

    def __init__(self):
        """Initialize ModelManager with empty state"""
        self.providers: Dict[str, BaseProvider] = {}
        self.current_provider_id: Optional[str] = None
        self.current_model_name: Optional[str] = None

    def discover_available_sources(self, ollama_url: str = None):
        """
        Discover and register available LLM providers.

        Args:
            ollama_url: Optional Ollama URL from config (e.g., from OLLAMA_URL env var)

        Checks:
        - Configured Ollama (if ollama_url provided)
        - Local Ollama (localhost:11434)
        - Remote Ollama (eugenes-mbp.local:11434)
        - Google Gemini API (if GOOGLE_API_KEY is set)
        - Anthropic Claude API (if ANTHROPIC_API_KEY is set)
        """
        # Check configured Ollama URL first (from config)
        if ollama_url:
            try:
                configured_ollama = OllamaProvider(base_url=ollama_url)
                if configured_ollama.health_check():
                    # Extract hostname from URL for clearer naming
                    import re
                    hostname = re.search(r'://([^:]+)', ollama_url)
                    host_display = hostname.group(1) if hostname else ollama_url
                    configured_ollama.id = "ollama_configured"
                    configured_ollama.name = f"Ollama ({host_display})"
                    self.providers["ollama_configured"] = configured_ollama
            except Exception:
                pass

        # Check Mac Mini Ollama (should be different from configured)
        mac_mini_url = "http://m1-mini.local:11434"
        if mac_mini_url != ollama_url:  # Don't check if it's already the configured one
            try:
                mac_mini = OllamaProvider(base_url=mac_mini_url)
                if mac_mini.health_check():
                    mac_mini.id = "ollama_mac_mini"
                    mac_mini.name = "Ollama (Mac Mini - m1-mini.local)"
                    self.providers["ollama_mac_mini"] = mac_mini
            except Exception:
                pass

        # Check local Ollama (on NUC-2 itself)
        if ollama_url != "http://localhost:11434":  # Don't duplicate if already configured
            try:
                local_ollama = OllamaProvider(base_url="http://localhost:11434")
                if local_ollama.health_check():
                    local_ollama.id = "ollama_local"
                    local_ollama.name = "Ollama (NUC-2 Local)"
                    self.providers["ollama_local"] = local_ollama
            except Exception:
                pass

        # Check Google Gemini
        if os.getenv("GOOGLE_API_KEY"):
            try:
                gemini = GeminiProvider()
                self.providers["gemini"] = gemini
            except Exception:
                pass

        # Check Anthropic Claude
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                anthropic = AnthropicProvider()
                self.providers["anthropic"] = anthropic
            except Exception:
                pass

    def set_model(self, provider_id: str, model_name: str):
        """
        Set the current active provider and model.

        Args:
            provider_id: ID of the provider (e.g., "ollama_local", "gemini")
            model_name: Name of the model to use

        Raises:
            ValueError: If provider_id is not in available providers
        """
        if provider_id not in self.providers:
            raise ValueError(
                f"Provider '{provider_id}' not available. "
                f"Available providers: {list(self.providers.keys())}"
            )

        self.current_provider_id = provider_id
        self.current_model_name = model_name

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Generate text using the current provider.

        Args:
            prompt: User prompt/question
            system_prompt: Optional system instructions

        Returns:
            str: Generated response

        Raises:
            ValueError: If no provider is currently selected
        """
        if not self.current_provider_id:
            raise ValueError(
                "No provider currently selected. Call set_model() first."
            )

        provider = self.providers[self.current_provider_id]
        return provider.generate(prompt, system_prompt)

    def get_current_config(self) -> dict:
        """
        Get current configuration information.

        Returns:
            dict: Current provider_id, model_name, and provider_name
        """
        if not self.current_provider_id:
            return {
                "provider_id": None,
                "model_name": None,
                "provider_name": None,
            }

        provider = self.providers[self.current_provider_id]
        return {
            "provider_id": self.current_provider_id,
            "model_name": self.current_model_name,
            "provider_name": provider.name,
        }

    def get_available_providers(self) -> list[dict]:
        """
        Get list of available providers with their models.

        Returns:
            list[dict]: List of provider information dicts
        """
        result = []
        for provider_id, provider in self.providers.items():
            result.append(
                {
                    "id": provider_id,
                    "name": provider.name,
                    "models": provider.list_models(),
                }
            )
        return result
