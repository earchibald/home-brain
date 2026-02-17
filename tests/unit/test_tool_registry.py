"""
Unit tests for ToolRegistry — tool registration, lookup, and filtering.
"""

import pytest
from unittest.mock import MagicMock

from slack_bot.tools.base_tool import BaseTool, ToolResult, UserScopedTool
from slack_bot.tools.tool_registry import ToolRegistry
from slack_bot.tools.tool_state import ToolStateStore


class MockTool(BaseTool):
    """Mock built-in tool."""

    def __init__(self, name="mock", display_name="Mock", category="builtin"):
        self.name = name
        self.display_name = display_name
        self.description = f"A mock {name} tool"
        self.category = category

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}

    async def execute(self, **kwargs):
        return ToolResult(tool_name=self.name, success=True, content="ok")


class MockUserTool(UserScopedTool):
    """Mock user-scoped tool."""

    def __init__(self, name="user_mock"):
        self.name = name
        self.display_name = "User Mock"
        self.description = "A mock user-scoped tool"
        self.category = "builtin"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(tool_name=self.name, success=True, content=f"user={self._user_id}")


@pytest.fixture
def registry(tmp_path):
    """Create a ToolRegistry with temp state store."""
    store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
    return ToolRegistry(state_store=store)


@pytest.mark.unit
class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_tool(self, registry):
        tool = MockTool()
        registry.register(tool)
        assert registry.get("mock") is tool

    def test_register_overwrites(self, registry):
        tool1 = MockTool(name="web")
        tool2 = MockTool(name="web")
        registry.register(tool1)
        registry.register(tool2)
        assert registry.get("web") is tool2

    def test_unregister(self, registry):
        tool = MockTool()
        registry.register(tool)
        assert registry.unregister("mock") is True
        assert registry.get("mock") is None

    def test_unregister_nonexistent(self, registry):
        assert registry.unregister("nope") is False

    def test_list_all_tools(self, registry):
        registry.register(MockTool(name="a"))
        registry.register(MockTool(name="b"))
        assert len(registry.list_tools()) == 2

    def test_list_by_category(self, registry):
        registry.register(MockTool(name="builtin1", category="builtin"))
        registry.register(MockTool(name="mcp1", category="mcp"))
        builtins = registry.list_tools(category="builtin")
        assert len(builtins) == 1
        assert builtins[0].name == "builtin1"

    def test_list_enabled_only(self, registry):
        registry.register(MockTool(name="a"))
        registry.register(MockTool(name="b"))
        registry.set_enabled("U123", "b", False)
        enabled = registry.list_tools(user_id="U123", enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].name == "a"

    def test_is_enabled_default_true(self, registry):
        registry.register(MockTool(name="test"))
        assert registry.is_enabled("U123", "test") is True

    def test_set_enabled(self, registry):
        registry.register(MockTool(name="test"))
        registry.set_enabled("U123", "test", False)
        assert registry.is_enabled("U123", "test") is False

    def test_get_enabled_tools_for_llm(self, registry):
        registry.register(MockTool(name="a", category="builtin"))
        registry.register(MockTool(name="b", category="skill"))  # Excluded by category
        registry.register(MockTool(name="c", category="builtin"))
        registry.set_enabled("U123", "c", False)
        tools = registry.get_enabled_tools_for_llm("U123")
        names = [t.name for t in tools]
        assert "a" in names
        assert "b" not in names  # skill excluded
        assert "c" not in names  # disabled

    def test_get_function_specs(self, registry):
        registry.register(MockTool(name="a"))
        specs = registry.get_function_specs("U123")
        assert len(specs) == 1
        assert specs[0]["function"]["name"] == "a"

    def test_get_prompt_descriptions(self, registry):
        registry.register(MockTool(name="web_search"))
        desc = registry.get_prompt_descriptions("U123")
        assert "web_search" in desc

    def test_get_prompt_descriptions_empty(self, registry):
        assert registry.get_prompt_descriptions("U123") == ""

    def test_get_nonexistent_tool(self, registry):
        assert registry.get("nope") is None
