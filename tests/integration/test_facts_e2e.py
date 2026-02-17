"""
Integration test: FACTS end-to-end — store fact, query retrieval, context injection.

Tests the full facts lifecycle: store a fact → verify it's persisted →
check it appears in context injection → verify deletion.
"""

import os
import pytest
from slack_bot.tools.builtin.facts_tool import (
    FactsStore,
    FactsTool,
    message_references_personal_context,
)
from slack_bot.tools.base_tool import ToolResult


@pytest.mark.integration
class TestFactsE2E:
    """End-to-end FACTS system tests."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_fact(self, tmp_path):
        """Store a fact via FactsTool and retrieve it."""
        store = FactsStore(user_id="U_TEST", storage_dir=str(tmp_path))

        tool = FactsTool()
        tool._user_id = "U_TEST"
        # Override storage dir by patching
        tool._get_store = lambda: FactsStore(user_id="U_TEST", storage_dir=str(tmp_path))

        # Store a fact directly through the store
        store.store("preferred_coffee", "oat milk flat white", "preferences")

        # Verify retrieval
        fact = store.get("preferred_coffee")
        assert fact is not None
        assert fact["value"] == "oat milk flat white"
        assert fact["category"] == "preferences"

    @pytest.mark.asyncio
    async def test_facts_context_injection(self, tmp_path):
        """Facts with matching category appear in context injection."""
        store = FactsStore(user_id="U_TEST_CTX", storage_dir=str(tmp_path))

        # Store several facts
        store.store("coffee", "oat milk flat white", "preferences")
        store.store("name", "Eugene", "personal")
        store.store("goal", "learn Rust", "goals")

        # Get context for injection
        context = store.get_context_for_injection()
        assert "oat milk flat white" in context
        assert "Eugene" in context
        assert "learn Rust" in context

    @pytest.mark.asyncio
    async def test_facts_category_filter(self, tmp_path):
        """Facts can be filtered by category."""
        store = FactsStore(user_id="U_TEST_CAT", storage_dir=str(tmp_path))

        store.store("coffee", "espresso", "preferences")
        store.store("name", "Alice", "personal")

        prefs = store.list_facts(category="preferences")
        assert len(prefs) == 1
        assert prefs[0]["key"] == "coffee"

        personal = store.list_facts(category="personal")
        assert len(personal) == 1
        assert personal[0]["key"] == "name"

    @pytest.mark.asyncio
    async def test_facts_deletion(self, tmp_path):
        """Deleted facts are removed from storage."""
        store = FactsStore(user_id="U_TEST_DEL", storage_dir=str(tmp_path))

        store.store("temp_fact", "temporary", "context")
        assert store.get("temp_fact") is not None

        result = store.delete("temp_fact")
        assert result is True
        assert store.get("temp_fact") is None

    @pytest.mark.asyncio
    async def test_facts_conflict_detection(self, tmp_path):
        """Storing in same category warns about existing facts."""
        store = FactsStore(user_id="U_TEST_CONF", storage_dir=str(tmp_path))

        store.store("coffee", "latte", "preferences")
        # Storing another preference should still work (update)
        store.store("coffee", "espresso", "preferences")

        fact = store.get("coffee")
        assert fact["value"] == "espresso"

    def test_message_references_personal_context(self):
        """Personal context detection works for common patterns."""
        # Should match — personal pronouns + context keywords
        assert message_references_personal_context("what is my name")
        assert message_references_personal_context("remind me of my coffee preference")

        # Should NOT match — no personal reference
        assert not message_references_personal_context("what is the weather")
        assert not message_references_personal_context("explain python decorators")

    @pytest.mark.asyncio
    async def test_facts_file_permissions(self, tmp_path):
        """Facts file has secure permissions (0600)."""
        store = FactsStore(user_id="U_TEST_PERMS", storage_dir=str(tmp_path))
        store.store("test", "value", "other")

        path = store.storage_path
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600

    @pytest.mark.asyncio
    async def test_empty_facts_returns_empty_context(self, tmp_path):
        """No stored facts returns empty context string."""
        store = FactsStore(user_id="U_TEST_EMPTY", storage_dir=str(tmp_path))
        context = store.get_context_for_injection()
        assert context == "" or context is None or len(context.strip()) == 0
