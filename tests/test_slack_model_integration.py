"""
Tests for Slack bot integration with ModelManager.

Tests the logic for building Block Kit UI and handling model switching.
"""

import pytest
import os


class TestSlackModelIntegration:
    """Test Slack /model command integration logic"""

    def test_build_model_selector_ui_structure(self):
        """build_model_selector_ui() should return proper Block Kit structure"""
        from slack_bot.model_selector import build_model_selector_ui
        from services.model_manager import ModelManager

        os.environ["GOOGLE_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()

        # Build UI
        blocks = build_model_selector_ui(manager)

        assert isinstance(blocks, list)
        assert len(blocks) > 0

        # Should have at least one section block
        assert any(block["type"] == "section" for block in blocks)

        del os.environ["GOOGLE_API_KEY"]

    def test_build_model_selector_shows_current_config(self):
        """UI should display current provider/model configuration"""
        from slack_bot.model_selector import build_model_selector_ui
        from services.model_manager import ModelManager

        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()
        manager.set_model("anthropic", "claude-3-5-sonnet-latest")

        blocks = build_model_selector_ui(manager)

        # Convert blocks to JSON string to search
        import json

        blocks_str = json.dumps(blocks)

        # Should mention the current model somewhere
        assert "claude" in blocks_str.lower() or "anthropic" in blocks_str.lower()

        del os.environ["ANTHROPIC_API_KEY"]

    def test_handle_provider_selection(self):
        """Selecting a provider should return updated model options"""
        from slack_bot.model_selector import get_models_for_provider
        from services.model_manager import ModelManager

        os.environ["GOOGLE_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()

        # Get models for Gemini
        models = get_models_for_provider(manager, "gemini")

        assert isinstance(models, list)
        assert len(models) > 0
        assert all(isinstance(m, str) for m in models)

        del os.environ["GOOGLE_API_KEY"]

    def test_handle_model_selection(self):
        """Selecting a model should update ModelManager state"""
        from slack_bot.model_selector import apply_model_selection
        from services.model_manager import ModelManager

        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        manager = ModelManager()
        manager.discover_available_sources()

        # Apply selection
        result = apply_model_selection(
            manager, provider_id="anthropic", model_name="claude-3-haiku-latest"
        )

        assert result["success"] is True
        assert manager.current_provider_id == "anthropic"
        assert manager.current_model_name == "claude-3-haiku-latest"

        del os.environ["ANTHROPIC_API_KEY"]

    def test_handle_invalid_provider_selection(self):
        """Selecting invalid provider should return error"""
        from slack_bot.model_selector import apply_model_selection
        from services.model_manager import ModelManager

        manager = ModelManager()
        manager.discover_available_sources()

        # Try invalid provider
        result = apply_model_selection(
            manager, provider_id="nonexistent", model_name="test"
        )

        assert result["success"] is False
        assert "error" in result
