"""
Unit tests for Agent Hooks framework (Phase 7).

Tests the register_hook, _run_pre_process_hooks, and _run_post_process_hooks
methods on SlackAgent without requiring real Slack connections.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---- Helpers ----


def _make_mock_agent():
    """Create a minimal mock SlackAgent with hook support.

    We instantiate just the hook-related attributes rather than
    the full SlackAgent (which requires Slack tokens).
    """
    agent = MagicMock()
    agent.agent_hooks = {
        "pre_process": [],
        "post_process": [],
    }
    agent.logger = MagicMock()

    # Import the real methods and bind them
    from agents.slack_agent import SlackAgent
    import types

    agent.register_hook = types.MethodType(SlackAgent.register_hook, agent)
    agent._run_pre_process_hooks = types.MethodType(SlackAgent._run_pre_process_hooks, agent)
    agent._run_post_process_hooks = types.MethodType(SlackAgent._run_post_process_hooks, agent)

    return agent


# ---- Tests ----


@pytest.mark.unit
class TestRegisterHook:
    """Test hook registration."""

    def test_register_pre_process_hook(self):
        agent = _make_mock_agent()
        hook_fn = AsyncMock()
        agent.register_hook("pre_process", hook_fn)
        assert hook_fn in agent.agent_hooks["pre_process"]

    def test_register_post_process_hook(self):
        agent = _make_mock_agent()
        hook_fn = AsyncMock()
        agent.register_hook("post_process", hook_fn)
        assert hook_fn in agent.agent_hooks["post_process"]

    def test_register_invalid_hook_type(self):
        agent = _make_mock_agent()
        with pytest.raises(ValueError, match="Invalid hook type"):
            agent.register_hook("invalid", AsyncMock())

    def test_register_multiple_hooks(self):
        agent = _make_mock_agent()
        hook_a = AsyncMock()
        hook_b = AsyncMock()
        agent.register_hook("pre_process", hook_a)
        agent.register_hook("pre_process", hook_b)
        assert len(agent.agent_hooks["pre_process"]) == 2


@pytest.mark.unit
class TestPreProcessHooks:
    """Test pre_process hook dispatch."""

    @pytest.mark.asyncio
    async def test_pre_process_hooks_called(self):
        agent = _make_mock_agent()
        hook_fn = AsyncMock()
        agent.register_hook("pre_process", hook_fn)

        event = {"user_id": "U123", "text": "hello"}
        await agent._run_pre_process_hooks(event)

        hook_fn.assert_called_once_with(event, agent)

    @pytest.mark.asyncio
    async def test_pre_process_hooks_multiple(self):
        agent = _make_mock_agent()
        hook_a = AsyncMock()
        hook_b = AsyncMock()
        agent.register_hook("pre_process", hook_a)
        agent.register_hook("pre_process", hook_b)

        event = {"user_id": "U123", "text": "hello"}
        await agent._run_pre_process_hooks(event)

        hook_a.assert_called_once()
        hook_b.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_process_hook_error_logged(self):
        """Hook errors are logged but don't propagate."""
        agent = _make_mock_agent()
        bad_hook = AsyncMock(side_effect=Exception("Hook failed"))
        agent.register_hook("pre_process", bad_hook)

        event = {"user_id": "U123", "text": "hello"}
        # Should not raise
        await agent._run_pre_process_hooks(event)

        agent.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_process_hook_error_doesnt_block_others(self):
        """An error in one hook doesn't block subsequent hooks."""
        agent = _make_mock_agent()
        bad_hook = AsyncMock(side_effect=Exception("Hook failed"))
        good_hook = AsyncMock()
        agent.register_hook("pre_process", bad_hook)
        agent.register_hook("pre_process", good_hook)

        event = {"user_id": "U123", "text": "hello"}
        await agent._run_pre_process_hooks(event)

        good_hook.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_process_no_hooks(self):
        """No hooks is a no-op."""
        agent = _make_mock_agent()
        event = {"user_id": "U123", "text": "hello"}
        await agent._run_pre_process_hooks(event)  # Should not raise


@pytest.mark.unit
class TestPostProcessHooks:
    """Test post_process hook dispatch."""

    @pytest.mark.asyncio
    async def test_post_process_hooks_called(self):
        agent = _make_mock_agent()
        hook_fn = AsyncMock(return_value=None)
        agent.register_hook("post_process", hook_fn)

        event = {"user_id": "U123", "text": "hello"}
        result = await agent._run_post_process_hooks("response text", event)

        hook_fn.assert_called_once_with("response text", event, agent)
        assert result == "response text"  # None return keeps original

    @pytest.mark.asyncio
    async def test_post_process_hook_modifies_response(self):
        """Post-process hook can modify the response."""
        agent = _make_mock_agent()
        hook_fn = AsyncMock(return_value="modified response")
        agent.register_hook("post_process", hook_fn)

        event = {"user_id": "U123", "text": "hello"}
        result = await agent._run_post_process_hooks("original", event)

        assert result == "modified response"

    @pytest.mark.asyncio
    async def test_post_process_hooks_chain(self):
        """Multiple post-process hooks chain modifications."""
        agent = _make_mock_agent()

        async def hook_a(response, event, agent):
            return response + " [a]"

        async def hook_b(response, event, agent):
            return response + " [b]"

        agent.register_hook("post_process", hook_a)
        agent.register_hook("post_process", hook_b)

        event = {"user_id": "U123", "text": "hello"}
        result = await agent._run_post_process_hooks("start", event)

        assert result == "start [a] [b]"

    @pytest.mark.asyncio
    async def test_post_process_hook_error_logged(self):
        """Hook errors are logged but don't propagate."""
        agent = _make_mock_agent()
        bad_hook = AsyncMock(side_effect=Exception("Hook failed"))
        agent.register_hook("post_process", bad_hook)

        event = {"user_id": "U123", "text": "hello"}
        result = await agent._run_post_process_hooks("response", event)

        assert result == "response"  # Original preserved
        agent.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_process_hook_non_string_return_ignored(self):
        """Non-string returns from hooks are ignored (original preserved)."""
        agent = _make_mock_agent()
        hook_fn = AsyncMock(return_value=42)  # Not a string
        agent.register_hook("post_process", hook_fn)

        event = {"user_id": "U123", "text": "hello"}
        result = await agent._run_post_process_hooks("response", event)

        assert result == "response"

    @pytest.mark.asyncio
    async def test_post_process_no_hooks(self):
        """No hooks returns original response."""
        agent = _make_mock_agent()
        event = {"user_id": "U123", "text": "hello"}
        result = await agent._run_post_process_hooks("response", event)
        assert result == "response"
