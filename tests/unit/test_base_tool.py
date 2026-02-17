"""
Unit tests for BaseTool, UserScopedTool, and ToolResult.
"""

import pytest
from slack_bot.tools.base_tool import BaseTool, ToolResult, UserScopedTool


class DummyTool(BaseTool):
    """Concrete BaseTool for testing."""

    name = "dummy"
    display_name = "Dummy Tool"
    description = "A dummy tool for testing"
    category = "builtin"

    @property
    def parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Test query"},
                "limit": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs):
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=f"Executed with query={kwargs.get('query')}",
        )


class DummyUserTool(UserScopedTool):
    """Concrete UserScopedTool for testing."""

    name = "user_dummy"
    display_name = "User Dummy"
    description = "A user-scoped dummy tool"
    category = "builtin"

    @property
    def parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action", "enum": ["read", "write"]},
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs):
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=f"User={self._user_id}, action={kwargs.get('action')}",
        )


@pytest.mark.unit
class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_success_result(self):
        result = ToolResult(tool_name="test", success=True, content="hello")
        assert result.success
        assert result.content == "hello"
        assert result.error is None
        assert result.executed_at  # ISO timestamp

    def test_failure_result(self):
        result = ToolResult(tool_name="test", success=False, error="boom")
        assert not result.success
        assert result.error == "boom"

    def test_to_context_string_success(self):
        result = ToolResult(tool_name="web_search", success=True, content="Found 3 results")
        ctx = result.to_context_string()
        assert "[Tool: web_search]" in ctx
        assert "Found 3 results" in ctx

    def test_to_context_string_error(self):
        result = ToolResult(tool_name="web_search", success=False, error="timeout")
        ctx = result.to_context_string()
        assert "ERROR" in ctx
        assert "timeout" in ctx

    def test_raw_data(self):
        result = ToolResult(tool_name="test", success=True, content="ok", raw={"key": "val"})
        assert result.raw == {"key": "val"}


@pytest.mark.unit
class TestBaseTool:
    """Tests for BaseTool abstract class."""

    def test_concrete_attributes(self):
        tool = DummyTool()
        assert tool.name == "dummy"
        assert tool.display_name == "Dummy Tool"
        assert tool.category == "builtin"

    async def test_execute(self):
        tool = DummyTool()
        result = await tool.execute(query="test")
        assert result.success
        assert "test" in result.content

    async def test_health_check_default(self):
        tool = DummyTool()
        assert await tool.health_check() is True

    def test_to_function_spec(self):
        tool = DummyTool()
        spec = tool.to_function_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "dummy"
        assert "query" in spec["function"]["parameters"]["properties"]

    def test_to_prompt_description(self):
        tool = DummyTool()
        desc = tool.to_prompt_description()
        assert "dummy" in desc
        assert "query" in desc
        assert "(required)" in desc
        assert "limit" in desc
        assert "(optional)" in desc

    def test_repr(self):
        tool = DummyTool()
        assert "DummyTool" in repr(tool)
        assert "dummy" in repr(tool)


@pytest.mark.unit
class TestUserScopedTool:
    """Tests for UserScopedTool."""

    def test_default_user_id_empty(self):
        tool = DummyUserTool()
        assert tool._user_id == ""

    def test_user_id_settable(self):
        tool = DummyUserTool()
        tool._user_id = "U12345"
        assert tool._user_id == "U12345"

    async def test_execute_with_user_id(self):
        tool = DummyUserTool()
        tool._user_id = "U12345"
        result = await tool.execute(action="read")
        assert result.success
        assert "U12345" in result.content

    def test_is_instance_of_base_tool(self):
        tool = DummyUserTool()
        assert isinstance(tool, BaseTool)
        assert isinstance(tool, UserScopedTool)

    def test_to_prompt_description_with_enum(self):
        tool = DummyUserTool()
        desc = tool.to_prompt_description()
        assert "read" in desc
        assert "write" in desc
