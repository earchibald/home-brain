"""
Unit tests for ToolExecutor — tool call parsing, execution, and loop.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from slack_bot.tools.base_tool import BaseTool, ToolResult, UserScopedTool
from slack_bot.tools.tool_executor import (
    MAX_TOOL_ROUNDS,
    TOOL_TIMEOUT_SECONDS,
    ToolCall,
    ToolExecutor,
    build_shim_system_prompt,
    execute_tool_call,
    parse_shim_tool_call,
)
from slack_bot.tools.tool_registry import ToolRegistry
from slack_bot.tools.tool_state import ToolStateStore


class FakeTool(BaseTool):
    name = "test_tool"
    display_name = "Test Tool"
    description = "A test tool"
    category = "builtin"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}

    async def execute(self, **kwargs):
        return ToolResult(tool_name=self.name, success=True, content=f"result for {kwargs.get('q')}")


class SlowTool(BaseTool):
    name = "slow_tool"
    display_name = "Slow Tool"
    description = "Takes a long time"
    category = "builtin"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        await asyncio.sleep(60)  # Will be timed out
        return ToolResult(tool_name=self.name, success=True, content="done")


class FakeUserTool(UserScopedTool):
    name = "user_tool"
    display_name = "User Tool"
    description = "User scoped tool"
    category = "builtin"

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(tool_name=self.name, success=True, content=f"user={self._user_id}")


@pytest.fixture
def registry(tmp_path):
    store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
    reg = ToolRegistry(state_store=store)
    reg.register(FakeTool())
    return reg


@pytest.mark.unit
class TestParseShimToolCall:
    """Tests for parse_shim_tool_call."""

    def test_well_formed(self):
        text = 'Let me search. <tool_call>\n{"tool": "web_search", "arguments": {"query": "python"}}\n</tool_call>'
        tc = parse_shim_tool_call(text)
        assert tc is not None
        assert tc.tool_name == "web_search"
        assert tc.arguments == {"query": "python"}

    def test_no_tool_call(self):
        assert parse_shim_tool_call("Just a normal response") is None

    def test_whitespace_variations(self):
        text = '<tool_call>   {"tool": "test", "arguments": {"x": 1}}   </tool_call>'
        tc = parse_shim_tool_call(text)
        assert tc is not None
        assert tc.tool_name == "test"
        assert tc.arguments == {"x": 1}

    def test_missing_closing_tag(self):
        text = '<tool_call>{"tool": "test", "arguments": {}}'
        tc = parse_shim_tool_call(text)
        assert tc is not None
        assert tc.tool_name == "test"

    def test_malformed_json(self):
        text = '<tool_call>not json at all</tool_call>'
        assert parse_shim_tool_call(text) is None

    def test_missing_tool_field(self):
        text = '<tool_call>{"arguments": {"q": "test"}}</tool_call>'
        assert parse_shim_tool_call(text) is None

    def test_name_alias(self):
        """Accepts 'name' as well as 'tool'."""
        text = '<tool_call>{"name": "web_search", "arguments": {"query": "hi"}}</tool_call>'
        tc = parse_shim_tool_call(text)
        assert tc is not None
        assert tc.tool_name == "web_search"

    def test_params_alias(self):
        """Accepts 'params' as well as 'arguments'."""
        text = '<tool_call>{"tool": "web_search", "params": {"query": "hi"}}</tool_call>'
        tc = parse_shim_tool_call(text)
        assert tc.arguments == {"query": "hi"}

    def test_arguments_not_dict(self):
        text = '<tool_call>{"tool": "test", "arguments": "not_a_dict"}</tool_call>'
        tc = parse_shim_tool_call(text)
        assert tc is not None
        assert tc.arguments == {}

    def test_raw_text_captured(self):
        text = 'before <tool_call>{"tool": "t", "arguments": {}}</tool_call> after'
        tc = parse_shim_tool_call(text)
        assert '<tool_call>' in tc.raw_text
        assert '</tool_call>' in tc.raw_text


@pytest.mark.unit
class TestExecuteToolCall:
    """Tests for execute_tool_call."""

    async def test_execute_success(self, registry):
        tc = ToolCall(tool_name="test_tool", arguments={"q": "hello"})
        result = await execute_tool_call(registry, tc, "U123")
        assert result.success
        assert "hello" in result.content

    async def test_unknown_tool(self, registry):
        tc = ToolCall(tool_name="nonexistent", arguments={})
        result = await execute_tool_call(registry, tc, "U123")
        assert not result.success
        assert "Unknown tool" in result.error

    async def test_disabled_tool(self, registry):
        registry.set_enabled("U123", "test_tool", False)
        tc = ToolCall(tool_name="test_tool", arguments={"q": "test"})
        result = await execute_tool_call(registry, tc, "U123")
        assert not result.success
        assert "disabled" in result.error

    async def test_user_scoped_tool_sets_user_id(self, tmp_path):
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        reg = ToolRegistry(state_store=store)
        user_tool = FakeUserTool()
        reg.register(user_tool)

        tc = ToolCall(tool_name="user_tool", arguments={})
        result = await execute_tool_call(reg, tc, "U999")
        assert result.success
        assert "U999" in result.content

    async def test_timeout(self, tmp_path):
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        reg = ToolRegistry(state_store=store)
        reg.register(SlowTool())

        tc = ToolCall(tool_name="slow_tool", arguments={})

        # Patch timeout to be very short for fast test
        with patch("slack_bot.tools.tool_executor.TOOL_TIMEOUT_SECONDS", 0.1):
            result = await execute_tool_call(reg, tc, "U123")
        assert not result.success
        assert "timed out" in result.error

    async def test_execution_error(self, tmp_path):
        """Tool that raises an exception."""

        class FailTool(BaseTool):
            name = "fail"
            display_name = "Fail"
            description = "Always fails"
            category = "builtin"

            @property
            def parameters_schema(self):
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs):
                raise ValueError("kaboom")

        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        reg = ToolRegistry(state_store=store)
        reg.register(FailTool())

        tc = ToolCall(tool_name="fail", arguments={})
        result = await execute_tool_call(reg, tc, "U123")
        assert not result.success
        assert "kaboom" in result.error


@pytest.mark.unit
class TestBuildShimSystemPrompt:
    """Tests for build_shim_system_prompt."""

    def test_with_tools(self, registry):
        prompt = build_shim_system_prompt(registry, "U123")
        assert "tool_call" in prompt
        assert "test_tool" in prompt

    def test_no_tools(self, tmp_path):
        store = ToolStateStore(storage_path=str(tmp_path / "state.json"))
        reg = ToolRegistry(state_store=store)
        prompt = build_shim_system_prompt(reg, "U123")
        assert prompt == ""

    def test_disabled_tool_excluded(self, registry):
        registry.set_enabled("U123", "test_tool", False)
        prompt = build_shim_system_prompt(registry, "U123")
        assert prompt == ""


@pytest.mark.unit
class TestToolExecutor:
    """Tests for the ToolExecutor class."""

    async def test_run_tool_loop_no_tool_call(self, registry):
        executor = ToolExecutor(registry)

        async def fake_generate(messages):
            return "Just a normal response"

        result = await executor.run_tool_loop([], "U123", fake_generate)
        assert result == "Just a normal response"

    async def test_run_tool_loop_one_round(self, registry):
        executor = ToolExecutor(registry)
        call_count = 0

        async def fake_generate(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '<tool_call>{"tool": "test_tool", "arguments": {"q": "hi"}}</tool_call>'
            return "Final answer with test_tool result"

        messages = []
        result = await executor.run_tool_loop(messages, "U123", fake_generate)
        assert "Final answer" in result
        assert call_count == 2

    async def test_run_tool_loop_max_rounds(self, registry):
        executor = ToolExecutor(registry)
        call_count = 0

        async def always_tool_call(messages):
            nonlocal call_count
            call_count += 1
            return '<tool_call>{"tool": "test_tool", "arguments": {"q": "loop"}}</tool_call>'

        messages = []
        result = await executor.run_tool_loop(messages, "U123", always_tool_call, max_rounds=3)
        # 3 rounds of tool calling + 1 final generate
        assert call_count == 4

    def test_build_shim_prompt(self, registry):
        executor = ToolExecutor(registry)
        prompt = executor.build_shim_prompt("U123")
        assert "test_tool" in prompt

    def test_build_native_specs(self, registry):
        executor = ToolExecutor(registry)
        specs = executor.build_native_specs("U123")
        assert len(specs) == 1
        assert specs[0]["function"]["name"] == "test_tool"
