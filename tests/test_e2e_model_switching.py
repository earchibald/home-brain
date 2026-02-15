"""
End-to-end tests for model switching feature.

Tests the complete flow from provider discovery through model selection.
"""

import pytest
import os
from services.model_manager import ModelManager
from slack_bot.model_selector import (
    build_model_selector_ui,
    apply_model_selection,
    get_models_for_provider,
)


class TestE2EModelSwitching:
    """End-to-end tests for complete model switching flow"""

    def test_complete_flow_with_cloud_provider(self):
        """Test complete flow: discovery → UI → selection → generation"""
        # Setup: Configure cloud provider
        os.environ["GOOGLE_API_KEY"] = "test-key"

        # Step 1: Initialize and discover
        manager = ModelManager()
        manager.discover_available_sources()

        assert len(manager.providers) > 0, "Should discover at least one provider"
        assert "gemini" in manager.providers, "Gemini should be discovered"

        # Step 2: Build UI
        blocks = build_model_selector_ui(manager)

        assert len(blocks) > 0, "UI should have blocks"
        assert any(b["type"] == "section" for b in blocks), "Should have section blocks"

        # Step 3: Get models for provider
        models = get_models_for_provider(manager, "gemini")

        assert len(models) > 0, "Should have Gemini models"
        assert "gemini-1.5-flash" in models, "Should include flash model"

        # Step 4: Apply selection
        result = apply_model_selection(manager, "gemini", "gemini-1.5-flash")

        assert result["success"] is True, "Selection should succeed"
        assert manager.current_provider_id == "gemini"
        assert manager.current_model_name == "gemini-1.5-flash"

        # Step 5: Verify configuration
        config = manager.get_current_config()

        assert config["provider_id"] == "gemini"
        assert config["model_name"] == "gemini-1.5-flash"
        assert "Gemini" in config["provider_name"]

        # Cleanup
        del os.environ["GOOGLE_API_KEY"]

    def test_complete_flow_with_multiple_providers(self):
        """Test discovery and switching between multiple providers"""
        # Setup: Configure multiple providers
        os.environ["GOOGLE_API_KEY"] = "test-key-1"
        os.environ["ANTHROPIC_API_KEY"] = "test-key-2"

        # Discover all providers
        manager = ModelManager()
        manager.discover_available_sources()

        assert len(manager.providers) >= 2, "Should discover multiple providers"

        # Get all available providers
        available = manager.get_available_providers()

        assert len(available) >= 2
        provider_ids = [p["id"] for p in available]
        assert "gemini" in provider_ids
        assert "anthropic" in provider_ids

        # Switch to Gemini
        apply_model_selection(manager, "gemini", "gemini-1.5-flash")
        assert manager.current_provider_id == "gemini"

        # Switch to Anthropic
        apply_model_selection(manager, "anthropic", "claude-3-5-sonnet-latest")
        assert manager.current_provider_id == "anthropic"
        assert manager.current_model_name == "claude-3-5-sonnet-latest"

        # Cleanup
        del os.environ["GOOGLE_API_KEY"]
        del os.environ["ANTHROPIC_API_KEY"]

    def test_error_handling_flow(self):
        """Test error handling when providers are unavailable"""
        # Ensure no API keys
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]

        # Initialize manager
        manager = ModelManager()
        manager.discover_available_sources()

        # Try to select non-existent provider
        result = apply_model_selection(manager, "nonexistent", "test-model")

        assert result["success"] is False
        assert "error" in result
        assert "not available" in result["error"].lower()

    def test_ui_updates_after_selection(self):
        """Test UI reflects current selection"""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()

        # Before selection
        blocks_before = build_model_selector_ui(manager)
        import json

        ui_str_before = json.dumps(blocks_before)
        assert "no model selected" in ui_str_before.lower()

        # Make selection
        apply_model_selection(manager, "anthropic", "claude-3-haiku-latest")

        # After selection
        blocks_after = build_model_selector_ui(manager)
        ui_str_after = json.dumps(blocks_after)

        assert "claude" in ui_str_after.lower() or "anthropic" in ui_str_after.lower()
        assert "haiku" in ui_str_after.lower()

        del os.environ["ANTHROPIC_API_KEY"]

    @pytest.mark.skipif(
        "SKIP_OLLAMA_TESTS" in os.environ,
        reason="Ollama tests skipped (set SKIP_OLLAMA_TESTS to skip)",
    )
    def test_ollama_discovery_and_selection(self):
        """Test Ollama provider discovery (requires running Ollama)"""
        manager = ModelManager()
        manager.discover_available_sources()

        # Check if local Ollama was discovered
        if "ollama_local" in manager.providers:
            # Test selection
            models = get_models_for_provider(manager, "ollama_local")
            if models:
                result = apply_model_selection(
                    manager, "ollama_local", models[0]
                )
                assert result["success"] is True

    def test_provider_list_format(self):
        """Test that provider list has correct format for UI"""
        os.environ["GOOGLE_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()

        providers = manager.get_available_providers()

        # Verify structure
        for provider in providers:
            assert "id" in provider
            assert "name" in provider
            assert "models" in provider
            assert isinstance(provider["models"], list)
            assert len(provider["models"]) > 0

        del os.environ["GOOGLE_API_KEY"]

    def test_concurrent_discovery_calls(self):
        """Test that multiple discovery calls don't break state"""
        os.environ["GOOGLE_API_KEY"] = "test-key"

        manager = ModelManager()

        # Call discovery multiple times
        manager.discover_available_sources()
        providers_1 = len(manager.providers)

        manager.discover_available_sources()
        providers_2 = len(manager.providers)

        manager.discover_available_sources()
        providers_3 = len(manager.providers)

        # Should be consistent
        assert providers_1 == providers_2 == providers_3

        del os.environ["GOOGLE_API_KEY"]


if __name__ == "__main__":
    # Run E2E tests with verbose output
    pytest.main([__file__, "-v", "-s"])
