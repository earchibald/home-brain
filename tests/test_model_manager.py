"""
Tests for ModelManager - the service that manages provider discovery and switching.
"""

import pytest
import os


class TestModelManager:
    """Test ModelManager discovery and switching logic"""

    def test_model_manager_initializes(self):
        """ModelManager should initialize with empty state"""
        from services.model_manager import ModelManager

        manager = ModelManager()
        assert manager.providers == {}
        assert manager.current_provider_id is None
        assert manager.current_model_name is None

    def test_model_manager_discover_finds_cloud_providers(self):
        """discover_available_sources() should find cloud providers when API keys are set"""
        from services.model_manager import ModelManager

        # Set API keys
        os.environ["GOOGLE_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()

        # Should have discovered Gemini and Anthropic
        assert "gemini" in manager.providers
        assert "anthropic" in manager.providers

        # Clean up
        del os.environ["GOOGLE_API_KEY"]
        del os.environ["ANTHROPIC_API_KEY"]

    def test_model_manager_discover_skips_cloud_without_keys(self):
        """discover_available_sources() should skip cloud providers without API keys"""
        from services.model_manager import ModelManager

        # Ensure no API keys
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]

        manager = ModelManager()
        manager.discover_available_sources()

        # Should NOT have cloud providers
        assert "gemini" not in manager.providers
        assert "anthropic" not in manager.providers

    def test_model_manager_set_model_updates_state(self):
        """set_model() should update current provider and model"""
        from services.model_manager import ModelManager

        os.environ["GOOGLE_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()

        # Set a model
        manager.set_model(provider_id="gemini", model_name="gemini-1.5-flash")

        assert manager.current_provider_id == "gemini"
        assert manager.current_model_name == "gemini-1.5-flash"

        del os.environ["GOOGLE_API_KEY"]

    def test_model_manager_set_model_validates_provider(self):
        """set_model() should raise error if provider not available"""
        from services.model_manager import ModelManager

        manager = ModelManager()
        manager.discover_available_sources()

        # Try to set non-existent provider
        with pytest.raises(ValueError, match="Provider.*not available"):
            manager.set_model(provider_id="nonexistent", model_name="test")

    def test_model_manager_generate_delegates_to_provider(self):
        """generate() should delegate to the current provider"""
        from services.model_manager import ModelManager

        os.environ["GOOGLE_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()
        manager.set_model(provider_id="gemini", model_name="gemini-1.5-flash")

        # Should delegate to Gemini provider
        response = manager.generate(prompt="test")
        assert isinstance(response, str)

        del os.environ["GOOGLE_API_KEY"]

    def test_model_manager_generate_requires_provider_set(self):
        """generate() should raise error if no provider is set"""
        from services.model_manager import ModelManager

        manager = ModelManager()

        with pytest.raises(ValueError, match="No provider.*selected"):
            manager.generate(prompt="test")

    def test_model_manager_get_current_config(self):
        """get_current_config() should return current provider and model info"""
        from services.model_manager import ModelManager

        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()
        manager.set_model(provider_id="anthropic", model_name="claude-3-5-sonnet-latest")

        config = manager.get_current_config()
        assert config["provider_id"] == "anthropic"
        assert config["model_name"] == "claude-3-5-sonnet-latest"
        assert "Anthropic" in config["provider_name"] or "Claude" in config["provider_name"]

        del os.environ["ANTHROPIC_API_KEY"]
