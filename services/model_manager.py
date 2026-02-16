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
        import socket

        def resolve_host(url: str) -> str:
            """Extract and resolve hostname from URL to IP for deduplication."""
            try:
                import re
                match = re.search(r'://([^:]+)', url)
                if match:
                    hostname = match.group(1)
                    # Resolve to IP for comparison
                    return socket.gethostbyname(hostname)
            except Exception:
                pass
            return url

        discovered_ips = set()

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
                    discovered_ips.add(resolve_host(ollama_url))
            except Exception:
                pass

        # Check M4 Pro Laptop
        laptop_url = "http://Eugenes-MacBook-Pro.local:11434"
        laptop_ip = resolve_host(laptop_url)
        if laptop_ip not in discovered_ips:
            try:
                laptop = OllamaProvider(base_url=laptop_url)
                if laptop.health_check():
                    laptop.id = "ollama_laptop"
                    laptop.name = "Ollama (M4 Pro Laptop)"
                    self.providers["ollama_laptop"] = laptop
                    discovered_ips.add(laptop_ip)
            except Exception:
                pass

        # Check M1 Mac Mini (m1-mini)
        m1_mini_url = "http://m1-mini.local:11434"
        m1_mini_ip = resolve_host(m1_mini_url)
        if m1_mini_ip not in discovered_ips:
            try:
                m1_mini = OllamaProvider(base_url=m1_mini_url)
                if m1_mini.health_check():
                    m1_mini.id = "ollama_m1_mini"
                    m1_mini.name = "Ollama (M1 Mini - m1-mini.local)"
                    self.providers["ollama_m1_mini"] = m1_mini
                    discovered_ips.add(m1_mini_ip)
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

        # Always register Gemini (even without API key - can be added via /apikey)
        try:
            gemini = GeminiProvider()  # Will check env var, but won't fail without it
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
