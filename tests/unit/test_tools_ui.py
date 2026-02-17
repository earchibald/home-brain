"""
Unit tests for tools_ui and facts_ui — Slack Block Kit builders.
"""

import pytest

from slack_bot.tools.base_tool import BaseTool, ToolResult
from slack_bot.tools.tool_registry import ToolRegistry
from slack_bot.tools.tool_state import ToolStateStore
from slack_bot.tools_ui import build_tools_ui, parse_tool_toggle_action
from slack_bot.facts_ui import build_facts_ui, build_fact_edit_view


class DummyBuiltinTool(BaseTool):
    name = "web_search"
    display_name = "Web Search"
    description = "Search the web for information"
    category = "builtin"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(tool_name=self.name, success=True, content="ok")


class DummyMCPTool(BaseTool):
    name = "mcp_github"
    display_name = "GitHub MCP"
    description = "GitHub MCP server tool"
    category = "mcp"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(tool_name=self.name, success=True, content="ok")


@pytest.fixture
def registry(tmp_path):
    store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
    reg = ToolRegistry(state_store=store)
    reg.register(DummyBuiltinTool())
    return reg


@pytest.mark.unit
class TestToolsUI:
    """Tests for build_tools_ui."""

    def test_builds_blocks(self, registry):
        blocks = build_tools_ui(registry, "U123")
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_shows_tool_name(self, registry):
        blocks = build_tools_ui(registry, "U123")
        text = str(blocks)
        assert "Web Search" in text

    def test_toggle_button(self, registry):
        blocks = build_tools_ui(registry, "U123")
        text = str(blocks)
        assert "tool_toggle_web_search" in text

    def test_disabled_tool_shows_enable(self, registry):
        registry.set_enabled("U123", "web_search", False)
        blocks = build_tools_ui(registry, "U123")
        text = str(blocks)
        assert "Enable" in text

    def test_mcp_section_when_mcp_tools(self, registry):
        registry.register(DummyMCPTool())
        blocks = build_tools_ui(registry, "U123")
        text = str(blocks)
        assert "MCP Server Tools" in text

    def test_no_mcp_section_without_mcp_tools(self, registry):
        blocks = build_tools_ui(registry, "U123")
        text = str(blocks)
        assert "MCP Server Tools" not in text

    def test_empty_registry(self, tmp_path):
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        reg = ToolRegistry(state_store=store)
        blocks = build_tools_ui(reg, "U123")
        text = str(blocks)
        assert "No tools registered" in text


@pytest.mark.unit
class TestParseToolToggleAction:
    """Tests for parse_tool_toggle_action."""

    def test_enable(self):
        name, should_enable = parse_tool_toggle_action("web_search:enable")
        assert name == "web_search"
        assert should_enable is True

    def test_disable(self):
        name, should_enable = parse_tool_toggle_action("web_search:disable")
        assert name == "web_search"
        assert should_enable is False

    def test_invalid(self):
        name, should_enable = parse_tool_toggle_action("garbage")
        assert name == ""
        assert should_enable is False


@pytest.mark.unit
class TestFactsUI:
    """Tests for build_facts_ui."""

    def test_builds_blocks_empty(self, tmp_path):
        blocks = build_facts_ui("U999", storage_dir=str(tmp_path))
        assert isinstance(blocks, list)
        text = str(blocks)
        assert "No facts stored" in text

    def test_builds_blocks_with_facts(self, tmp_path):
        from slack_bot.tools.builtin.facts_tool import FactsStore
        store = FactsStore("U123", storage_dir=str(tmp_path))
        store.store("coffee", "flat white", "preferences")
        store.store("name", "Eugene", "personal")

        blocks = build_facts_ui("U123", storage_dir=str(tmp_path))
        text = str(blocks)
        assert "coffee" in text
        assert "Eugene" in text

    def test_add_button_present(self, tmp_path):
        blocks = build_facts_ui("U999", storage_dir=str(tmp_path))
        text = str(blocks)
        assert "facts_add_new" in text

    def test_clear_button_with_facts(self, tmp_path):
        from slack_bot.tools.builtin.facts_tool import FactsStore
        store = FactsStore("U123", storage_dir=str(tmp_path))
        store.store("key", "value", "other")

        blocks = build_facts_ui("U123", storage_dir=str(tmp_path))
        text = str(blocks)
        assert "facts_clear_all" in text

    def test_overflow_menu(self, tmp_path):
        from slack_bot.tools.builtin.facts_tool import FactsStore
        store = FactsStore("U123", storage_dir=str(tmp_path))
        store.store("coffee", "flat white", "preferences")

        blocks = build_facts_ui("U123", storage_dir=str(tmp_path))
        text = str(blocks)
        assert "fact_overflow_coffee" in text


@pytest.mark.unit
class TestFactEditView:
    """Tests for build_fact_edit_view."""

    def test_new_fact_form(self, tmp_path):
        blocks = build_fact_edit_view("U123", storage_dir=str(tmp_path))
        assert isinstance(blocks, list)
        text = str(blocks)
        assert "Add New Fact" in text
        assert "fact_key_input" in text
        assert "fact_value_input" in text
        assert "fact_category_input" in text

    def test_edit_fact_form(self, tmp_path):
        blocks = build_fact_edit_view(
            "U123",
            key="coffee",
            value="flat white",
            category="preferences",
            storage_dir=str(tmp_path),
        )
        text = str(blocks)
        assert "Edit Fact" in text
        assert "coffee" in text
