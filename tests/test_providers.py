"""
Tests for LLM provider adapters following the adapter pattern.

Tests the BaseProvider interface and concrete implementations:
- OllamaProvider (local/remote)
- GeminiProvider (cloud API)
- AnthropicProvider (cloud API)
"""

import pytest
from abc import ABC


class TestBaseProvider:
    """Test the BaseProvider abstract interface"""

    def test_base_provider_is_abstract(self):
        """BaseProvider should be abstract and not instantiable"""
        from providers.base import BaseProvider

        # Should not be able to instantiate directly
        with pytest.raises(TypeError):
            BaseProvider()

    def test_base_provider_requires_list_models(self):
        """BaseProvider subclass must implement list_models()"""
        from providers.base import BaseProvider

        class IncompleteProvider(BaseProvider):
            id = "incomplete"
            name = "Incomplete Provider"

            def generate(self, prompt, system_prompt=None):
                return "test"

            def health_check(self):
                return True

        # Should fail without list_models
        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_base_provider_requires_generate(self):
        """BaseProvider subclass must implement generate()"""
        from providers.base import BaseProvider

        class IncompleteProvider(BaseProvider):
            id = "incomplete"
            name = "Incomplete Provider"

            def list_models(self):
                return []

            def health_check(self):
                return True

        # Should fail without generate
        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_base_provider_requires_health_check(self):
        """BaseProvider subclass must implement health_check()"""
        from providers.base import BaseProvider

        class IncompleteProvider(BaseProvider):
            id = "incomplete"
            name = "Incomplete Provider"

            def list_models(self):
                return []

            def generate(self, prompt, system_prompt=None):
                return "test"

        # Should fail without health_check
        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_complete_provider_can_be_instantiated(self):
        """A provider implementing all methods should instantiate"""
        from providers.base import BaseProvider

        class CompleteProvider(BaseProvider):
            id = "complete"
            name = "Complete Provider"

            def list_models(self):
                return ["model1", "model2"]

            def generate(self, prompt, system_prompt=None):
                return f"Response to: {prompt}"

            def health_check(self):
                return True

        # Should succeed
        provider = CompleteProvider()
        assert provider.id == "complete"
        assert provider.name == "Complete Provider"
        assert provider.list_models() == ["model1", "model2"]
        assert "Response to:" in provider.generate("test")
        assert provider.health_check() is True


class TestOllamaProvider:
    """Test OllamaProvider implementation"""

    def test_ollama_provider_initializes_with_base_url(self):
        """OllamaProvider should accept base_url in constructor"""
        from providers.ollama_adapter import OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")
        assert provider.base_url == "http://localhost:11434"
        assert provider.id == "ollama_local"
        assert "Ollama" in provider.name

    def test_ollama_provider_has_default_local_url(self):
        """OllamaProvider should default to localhost:11434"""
        from providers.ollama_adapter import OllamaProvider

        provider = OllamaProvider()
        assert provider.base_url == "http://localhost:11434"

    def test_ollama_provider_list_models_returns_list(self):
        """list_models() should return a list of strings"""
        from providers.ollama_adapter import OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")
        models = provider.list_models()
        assert isinstance(models, list)
        # All items should be strings
        for model in models:
            assert isinstance(model, str)

    def test_ollama_provider_health_check_timeout(self):
        """health_check() should timeout quickly on unreachable host"""
        from providers.ollama_adapter import OllamaProvider
        import time

        # Use a non-routable IP to ensure timeout
        provider = OllamaProvider(base_url="http://192.0.2.1:11434")

        start = time.time()
        result = provider.health_check()
        elapsed = time.time() - start

        assert result is False
        # Should timeout in ~1 second, not hang forever
        assert elapsed < 2.0

    def test_ollama_provider_generate_returns_string(self):
        """generate() should return a string response"""
        from providers.ollama_adapter import OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")
        response = provider.generate("test prompt")
        assert isinstance(response, str)

    def test_ollama_provider_generate_accepts_system_prompt(self):
        """generate() should accept optional system_prompt parameter"""
        from providers.ollama_adapter import OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")
        # Should not raise an error
        response = provider.generate("test prompt", system_prompt="You are a helpful assistant")
        assert isinstance(response, str)


class TestGeminiProvider:
    """Test GeminiProvider implementation"""

    def test_gemini_provider_requires_api_key(self):
        """GeminiProvider should check for GOOGLE_API_KEY"""
        from providers.gemini_adapter import GeminiProvider
        import os

        # Save original value
        original_key = os.environ.get("GOOGLE_API_KEY")

        # Remove API key
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

        # Should raise ValueError without API key
        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            GeminiProvider()

        # Restore
        if original_key:
            os.environ["GOOGLE_API_KEY"] = original_key

    def test_gemini_provider_initializes_with_api_key(self):
        """GeminiProvider should initialize when API key is present"""
        from providers.gemini_adapter import GeminiProvider
        import os

        # Set a test API key
        os.environ["GOOGLE_API_KEY"] = "test-api-key"

        provider = GeminiProvider()
        assert provider.id == "gemini"
        assert "Gemini" in provider.name

        # Clean up
        del os.environ["GOOGLE_API_KEY"]

    def test_gemini_provider_list_models_returns_list(self):
        """list_models() should return available Gemini models"""
        from providers.gemini_adapter import GeminiProvider
        import os

        os.environ["GOOGLE_API_KEY"] = "test-api-key"
        provider = GeminiProvider()
        models = provider.list_models()

        assert isinstance(models, list)
        assert len(models) > 0
        # Should include common Gemini models
        assert any("gemini" in m.lower() for m in models)

        del os.environ["GOOGLE_API_KEY"]

    def test_gemini_provider_health_check(self):
        """health_check() should return True when API key is set"""
        from providers.gemini_adapter import GeminiProvider
        import os

        os.environ["GOOGLE_API_KEY"] = "test-api-key"
        provider = GeminiProvider()

        # With API key set, health check should pass
        assert provider.health_check() is True

        del os.environ["GOOGLE_API_KEY"]


class TestAnthropicProvider:
    """Test AnthropicProvider implementation"""

    def test_anthropic_provider_requires_api_key(self):
        """AnthropicProvider should check for ANTHROPIC_API_KEY"""
        from providers.anthropic_adapter import AnthropicProvider
        import os

        # Save original value
        original_key = os.environ.get("ANTHROPIC_API_KEY")

        # Remove API key
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]

        # Should raise ValueError without API key
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider()

        # Restore
        if original_key:
            os.environ["ANTHROPIC_API_KEY"] = original_key

    def test_anthropic_provider_initializes_with_api_key(self):
        """AnthropicProvider should initialize when API key is present"""
        from providers.anthropic_adapter import AnthropicProvider
        import os

        # Set a test API key
        os.environ["ANTHROPIC_API_KEY"] = "test-api-key"

        provider = AnthropicProvider()
        assert provider.id == "anthropic"
        assert "Claude" in provider.name or "Anthropic" in provider.name

        # Clean up
        del os.environ["ANTHROPIC_API_KEY"]

    def test_anthropic_provider_list_models_returns_list(self):
        """list_models() should return available Claude models"""
        from providers.anthropic_adapter import AnthropicProvider
        import os

        os.environ["ANTHROPIC_API_KEY"] = "test-api-key"
        provider = AnthropicProvider()
        models = provider.list_models()

        assert isinstance(models, list)
        assert len(models) > 0
        # Should include Claude models
        assert any("claude" in m.lower() for m in models)

        del os.environ["ANTHROPIC_API_KEY"]

    def test_anthropic_provider_health_check(self):
        """health_check() should return True when API key is set"""
        from providers.anthropic_adapter import AnthropicProvider
        import os

        os.environ["ANTHROPIC_API_KEY"] = "test-api-key"
        provider = AnthropicProvider()

        # With API key set, health check should pass
        assert provider.health_check() is True

        del os.environ["ANTHROPIC_API_KEY"]
