"""
Unit tests for ToolStateStore — per-user tool enable/disable persistence.
"""

import json
import os
import pytest

from slack_bot.tools.tool_state import ToolStateStore


@pytest.fixture
def state_store(tmp_path):
    """Create a ToolStateStore with a temp storage path."""
    path = str(tmp_path / "tool-state.json")
    return ToolStateStore(storage_path=path)


@pytest.mark.unit
class TestToolStateStore:
    """Tests for ToolStateStore persistence."""

    def test_creates_file_on_init(self, tmp_path):
        path = str(tmp_path / "state.json")
        assert not os.path.exists(path)
        ToolStateStore(storage_path=path)
        assert os.path.exists(path)

    def test_default_enabled(self, state_store):
        """All tools default to enabled."""
        assert state_store.is_enabled("U123", "web_search") is True
        assert state_store.is_enabled("U123", "nonexistent_tool") is True

    def test_disable_tool(self, state_store):
        state_store.set_enabled("U123", "web_search", False)
        assert state_store.is_enabled("U123", "web_search") is False

    def test_enable_tool(self, state_store):
        state_store.set_enabled("U123", "web_search", False)
        state_store.set_enabled("U123", "web_search", True)
        assert state_store.is_enabled("U123", "web_search") is True

    def test_per_user_isolation(self, state_store):
        state_store.set_enabled("U123", "web_search", False)
        assert state_store.is_enabled("U123", "web_search") is False
        assert state_store.is_enabled("U456", "web_search") is True

    def test_persistence(self, tmp_path):
        """Data survives re-instantiation."""
        path = str(tmp_path / "state.json")
        store1 = ToolStateStore(storage_path=path)
        store1.set_enabled("U123", "facts", False)

        store2 = ToolStateStore(storage_path=path)
        assert store2.is_enabled("U123", "facts") is False

    def test_get_user_state(self, state_store):
        state_store.set_enabled("U123", "web_search", False)
        state_store.set_enabled("U123", "brain_search", True)
        user_state = state_store.get_user_state("U123")
        assert user_state == {"web_search": False, "brain_search": True}

    def test_get_user_state_empty(self, state_store):
        assert state_store.get_user_state("U999") == {}

    def test_clear_user_state(self, state_store):
        state_store.set_enabled("U123", "web_search", False)
        state_store.clear_user_state("U123")
        assert state_store.is_enabled("U123", "web_search") is True
        assert state_store.get_user_state("U123") == {}

    def test_file_permissions(self, tmp_path):
        path = str(tmp_path / "state.json")
        store = ToolStateStore(storage_path=path)
        store.set_enabled("U123", "test", True)
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600

    def test_handles_corrupt_file(self, tmp_path):
        """Gracefully handles corrupt JSON."""
        path = str(tmp_path / "state.json")
        with open(path, "w") as f:
            f.write("not valid json{{{")
        store = ToolStateStore(storage_path=path)
        # Should fallback to defaults
        assert store.is_enabled("U123", "anything") is True
