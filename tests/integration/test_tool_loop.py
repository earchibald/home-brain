"""
Integration test: Tool loop — LLM returns <tool_call> blocks, tool executes,
result injected, LLM called again.

Tests the full flow: ToolExecutor parses shim XML → tool runs → result
injected into context → LLM produces final answer.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from slack_bot.tools.base_tool import BaseTool, ToolResult
from slack_bot.tools.tool_executor import (
    ToolExecutor,
    parse_shim_tool_call,
    execute_tool_call,
)
from slack_bot.tools.tool_registry import ToolRegistry
from slack_bot.tools.tool_state import ToolStateStore


# ---- Helpers ----


class MockSearchTool(BaseTool):
    """A mock tool for testing the tool loop."""

    name = "test_search"
    display_name = "Test Search"
    description = "Search for something"
    category = "builtin"

    @property
    def parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs):
        query = kwargs.get("query", "")
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=f"Found 3 results for '{query}': Result A, Result B, Result C",
        )


# ---- Tests ----


@pytest.mark.integration
class TestToolLoop:
    """Test the full tool execution loop."""

    @pytest.mark.asyncio
    async def test_parse_and_execute_tool_call(self, tmp_path):
        """LLM returns <tool_call> XML → tool executes → result returned."""
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        registry = ToolRegistry(store)

        # Register our test tool
        registry.register(MockSearchTool())

        # Simulate LLM output with a tool call
        llm_output = (
            'I\'ll search for that. <tool_call>{"name": "test_search", '
            '"arguments": {"query": "Python async patterns"}}</tool_call>'
        )

        # Parse the tool call
        tool_call = parse_shim_tool_call(llm_output)
        assert tool_call is not None
        assert tool_call.tool_name == "test_search"
        assert tool_call.arguments["query"] == "Python async patterns"

        # Execute the tool
        result = await execute_tool_call(registry, tool_call, user_id="U_TEST")

        assert result.success is True
        assert "Python async patterns" in result.content
        assert "3 results" in result.content

    @pytest.mark.asyncio
    async def test_tool_result_injected_as_context(self, tmp_path):
        """Tool result formatted as context string for LLM injection."""
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        registry = ToolRegistry(store)
        registry.register(MockSearchTool())

        from slack_bot.tools.tool_executor import ToolCall
        tool_call = ToolCall(tool_name="test_search", arguments={"query": "test query"}, raw_text="")
        result = await execute_tool_call(registry, tool_call, user_id="U_TEST")

        context_str = result.to_context_string()
        assert "[Tool: test_search]" in context_str
        assert "test query" in context_str

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, tmp_path):
        """Calling an unknown tool returns an error result."""
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        registry = ToolRegistry(store)

        from slack_bot.tools.tool_executor import ToolCall
        tool_call = ToolCall(tool_name="nonexistent_tool", arguments={"query": "test"}, raw_text="")
        result = await execute_tool_call(registry, tool_call, user_id="U_TEST")

        assert result.success is False
        assert "unknown" in result.error.lower()

    @pytest.mark.asyncio
    async def test_disabled_tool_returns_error(self, tmp_path):
        """Calling a disabled tool returns an error result."""
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        registry = ToolRegistry(store)

        registry.register(MockSearchTool())
        registry.set_enabled("U_TEST", "test_search", False)

        from slack_bot.tools.tool_executor import ToolCall
        tool_call = ToolCall(tool_name="test_search", arguments={"query": "test"}, raw_text="")
        result = await execute_tool_call(registry, tool_call, user_id="U_TEST")

        assert result.success is False

    def test_parse_malformed_xml(self):
        """Malformed XML returns None, no crash."""
        result = parse_shim_tool_call("<tool_call>not json</tool_call>")
        assert result is None

    def test_parse_no_tool_calls(self):
        """LLM output without tool calls returns None."""
        result = parse_shim_tool_call("Just a normal response with no tools.")
        assert result is None

    def test_parse_first_tool_call_found(self):
        """First tool call in output is parsed (parse is single-match)."""
        llm_output = (
            '<tool_call>{"name": "test_search", "arguments": {"query": "first"}}</tool_call>'
        )
        result = parse_shim_tool_call(llm_output)
        assert result is not None
        assert result.arguments["query"] == "first"
