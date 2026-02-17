"""
Unit tests for FactsStore and FactsTool.
"""

import json
import os
import pytest

from slack_bot.tools.base_tool import ToolResult, UserScopedTool
from slack_bot.tools.builtin.facts_tool import (
    VALID_CATEGORIES,
    FactsStore,
    FactsTool,
    message_references_personal_context,
)


@pytest.fixture
def facts_store(tmp_path):
    """Create a FactsStore with temp storage."""
    return FactsStore("U123", storage_dir=str(tmp_path))


@pytest.fixture
def facts_tool(tmp_path):
    """Create a FactsTool with temp storage."""
    tool = FactsTool(storage_dir=str(tmp_path))
    tool._user_id = "U123"
    return tool


@pytest.mark.unit
class TestFactsStore:
    """Tests for FactsStore persistence."""

    def test_creates_file(self, tmp_path):
        store = FactsStore("U123", storage_dir=str(tmp_path))
        assert os.path.exists(store.storage_path)

    def test_store_new_fact(self, facts_store):
        result = facts_store.store("coffee", "oat milk flat white", "preferences")
        assert result["was_update"] is False
        assert result["old_value"] is None
        assert result["entry"]["key"] == "coffee"
        assert result["entry"]["value"] == "oat milk flat white"

    def test_store_update_fact(self, facts_store):
        facts_store.store("coffee", "black", "preferences")
        result = facts_store.store("coffee", "oat milk flat white", "preferences")
        assert result["was_update"] is True
        assert result["old_value"] == "black"

    def test_get_fact(self, facts_store):
        facts_store.store("name", "Eugene", "personal")
        fact = facts_store.get("name")
        assert fact is not None
        assert fact["value"] == "Eugene"
        assert fact["category"] == "personal"

    def test_get_missing_fact(self, facts_store):
        assert facts_store.get("nonexistent") is None

    def test_list_facts(self, facts_store):
        facts_store.store("a", "val_a", "personal")
        facts_store.store("b", "val_b", "work")
        facts = facts_store.list_facts()
        assert len(facts) == 2

    def test_list_facts_by_category(self, facts_store):
        facts_store.store("a", "val_a", "personal")
        facts_store.store("b", "val_b", "work")
        facts = facts_store.list_facts(category="work")
        assert len(facts) == 1
        assert facts[0]["key"] == "b"

    def test_list_facts_sorted_by_updated(self, facts_store):
        facts_store.store("old", "val1", "personal")
        facts_store.store("new", "val2", "personal")
        facts = facts_store.list_facts()
        # Most recently updated first
        assert facts[0]["key"] == "new"

    def test_delete_fact(self, facts_store):
        facts_store.store("temp", "val", "other")
        assert facts_store.delete("temp") is True
        assert facts_store.get("temp") is None

    def test_delete_nonexistent(self, facts_store):
        assert facts_store.delete("nope") is False

    def test_count(self, facts_store):
        assert facts_store.count() == 0
        facts_store.store("a", "1", "other")
        facts_store.store("b", "2", "other")
        assert facts_store.count() == 2

    def test_context_injection(self, facts_store):
        facts_store.store("coffee", "flat white", "preferences")
        facts_store.store("name", "Eugene", "personal")
        ctx = facts_store.get_context_for_injection()
        assert "Known facts" in ctx
        assert "coffee" in ctx
        assert "Eugene" in ctx

    def test_context_injection_empty(self, facts_store):
        assert facts_store.get_context_for_injection() == ""

    def test_context_injection_limit(self, facts_store):
        for i in range(25):
            facts_store.store(f"fact_{i}", f"value_{i}", "other")
        ctx = facts_store.get_context_for_injection(limit=5)
        # Should only have 5 facts (plus header)
        lines = [l for l in ctx.strip().split("\n") if l.startswith("- ")]
        assert len(lines) == 5

    def test_key_normalization(self, facts_store):
        """Keys are lowercased and spaces replaced with underscores."""
        facts_store.store("My Coffee", "flat white", "preferences")
        fact = facts_store.get("my_coffee")
        assert fact is not None
        assert fact["value"] == "flat white"

    def test_invalid_category_falls_back(self, facts_store):
        result = facts_store.store("x", "y", "not_a_category")
        assert result["entry"]["category"] == "other"

    def test_file_permissions(self, tmp_path):
        store = FactsStore("U123", storage_dir=str(tmp_path))
        store.store("key", "value", "other")
        mode = os.stat(store.storage_path).st_mode & 0o777
        assert mode == 0o600

    def test_per_user_isolation(self, tmp_path):
        store_a = FactsStore("UA", storage_dir=str(tmp_path))
        store_b = FactsStore("UB", storage_dir=str(tmp_path))
        store_a.store("name", "Alice", "personal")
        store_b.store("name", "Bob", "personal")
        assert store_a.get("name")["value"] == "Alice"
        assert store_b.get("name")["value"] == "Bob"


@pytest.mark.unit
class TestFactsTool:
    """Tests for FactsTool (LLM-driven CRUD)."""

    async def test_store_operation(self, facts_tool):
        result = await facts_tool.execute(
            operation="store", key="coffee", value="flat white", category="preferences"
        )
        assert result.success
        assert "coffee" in result.content
        assert "flat white" in result.content

    async def test_store_requires_key_and_value(self, facts_tool):
        result = await facts_tool.execute(operation="store", key="coffee")
        assert not result.success
        assert "requires" in result.error

    async def test_store_update_shows_old_value(self, facts_tool):
        await facts_tool.execute(operation="store", key="drink", value="tea")
        result = await facts_tool.execute(operation="store", key="drink", value="coffee")
        assert result.success
        assert "tea" in result.content  # old value surfaced

    async def test_get_operation(self, facts_tool):
        await facts_tool.execute(operation="store", key="name", value="Eugene")
        result = await facts_tool.execute(operation="get", key="name")
        assert result.success
        assert "Eugene" in result.content

    async def test_get_missing(self, facts_tool):
        result = await facts_tool.execute(operation="get", key="nonexistent")
        assert result.success
        assert "No fact found" in result.content

    async def test_get_requires_key(self, facts_tool):
        result = await facts_tool.execute(operation="get")
        assert not result.success
        assert "requires" in result.error

    async def test_list_operation(self, facts_tool):
        await facts_tool.execute(operation="store", key="a", value="1")
        await facts_tool.execute(operation="store", key="b", value="2")
        result = await facts_tool.execute(operation="list")
        assert result.success
        assert "2 total" in result.content
        assert isinstance(result.raw, list)

    async def test_list_empty(self, facts_tool):
        result = await facts_tool.execute(operation="list")
        assert result.success
        assert "No facts" in result.content

    async def test_delete_operation(self, facts_tool):
        await facts_tool.execute(operation="store", key="temp", value="val")
        result = await facts_tool.execute(operation="delete", key="temp")
        assert result.success
        assert "Deleted" in result.content

    async def test_delete_missing(self, facts_tool):
        result = await facts_tool.execute(operation="delete", key="nope")
        assert result.success
        assert "No fact found" in result.content

    async def test_delete_requires_key(self, facts_tool):
        result = await facts_tool.execute(operation="delete")
        assert not result.success

    async def test_unknown_operation(self, facts_tool):
        result = await facts_tool.execute(operation="explode")
        assert not result.success
        assert "Unknown operation" in result.error

    async def test_no_user_id(self, tmp_path):
        tool = FactsTool(storage_dir=str(tmp_path))
        # _user_id is empty by default
        result = await tool.execute(operation="list")
        assert not result.success
        assert "User ID not set" in result.error

    def test_is_user_scoped(self, facts_tool):
        assert isinstance(facts_tool, UserScopedTool)

    def test_parameters_schema(self, facts_tool):
        schema = facts_tool.parameters_schema
        assert "operation" in schema["properties"]
        assert "required" in schema
        assert "operation" in schema["required"]

    def test_tool_metadata(self, facts_tool):
        assert facts_tool.name == "facts"
        assert facts_tool.category == "builtin"


@pytest.mark.unit
class TestMessageReferencesPersonalContext:
    """Tests for message_references_personal_context."""

    def test_personal_pronouns(self):
        assert message_references_personal_context("I like coffee") is True
        assert message_references_personal_context("my wife's name") is True
        assert message_references_personal_context("tell me about") is True
        assert message_references_personal_context("I'm working on") is True

    def test_category_keywords(self):
        assert message_references_personal_context("what is my favorite food") is True
        assert message_references_personal_context("remember from last time") is True
        assert message_references_personal_context("my health goals") is True
        assert message_references_personal_context("my work project") is True

    def test_no_personal_context(self):
        assert message_references_personal_context("What is Python?") is False
        assert message_references_personal_context("explain quantum physics") is False
        assert message_references_personal_context("how does DNS operate") is False

    def test_family_keywords(self):
        assert message_references_personal_context("wife") is True
        assert message_references_personal_context("husband") is True
        assert message_references_personal_context("my daughter") is True

    def test_what_do_you_know(self):
        assert message_references_personal_context("what do you know about me") is True
