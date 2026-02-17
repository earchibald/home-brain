"""
Integration tests for web search functionality in SlackAgent.

Tests verify query classification, web search triggering, and context integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directories to path for imports
import sys
from pathlib import Path

# Set test brain path before ANY imports
test_brain_path = Path(__file__).parent.parent / "test_brain"
test_brain_path.mkdir(parents=True, exist_ok=True)
(test_brain_path / "users").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock brain_io module BEFORE importing anything that depends on agent_platform
mock_brain_io = MagicMock()
mock_brain_io.BrainIO = MagicMock(return_value=MagicMock())
sys.modules["brain_io"] = mock_brain_io

from clients.web_search_client import WebSearchClient, WebSearchResult


def get_slack_agent():
    """Lazy import to ensure mocks are in place"""
    with patch("agents.slack_agent.BrainIO"):
        from agents.slack_agent import SlackAgent
        return SlackAgent


@pytest.fixture
def mock_web_search_results():
    """Sample web search results for testing."""
    return [
        WebSearchResult(
            title="Latest AI News 2026",
            url="https://news.example.com/ai-2026",
            snippet="AI breakthroughs continue to reshape the technology landscape...",
            source_domain="news.example.com",
            retrieved_at="2026-02-16T10:00:00",
            score=0.95,
        ),
        WebSearchResult(
            title="AI Research Updates",
            url="https://research.example.com/ai",
            snippet="New research papers published this week on machine learning...",
            source_domain="research.example.com",
            retrieved_at="2026-02-16T10:00:00",
            score=0.85,
        ),
    ]


@pytest.mark.integration
class TestWebSearchQueryClassifier:
    """Tests for the query classification logic."""

    @pytest.fixture
    def agent_config(self, test_brain_path):
        """Configuration for test Slack agent with web search enabled"""
        return {
            "search_url": "http://nuc-1.local:9514",
            "ollama_url": "http://m1-mini.local:11434",
            "brain_path": str(test_brain_path),
            "model": "llama3.2",
            "max_context_tokens": 6000,
            "enable_search": True,
            "enable_web_search": True,
            "max_search_results": 3,
            "notification": {"enabled": False},
        }

    @pytest.fixture
    def mock_secrets(self):
        """Mock Vaultwarden get_secret for Slack tokens"""
        token_map = {
            "SLACK_BOT_TOKEN": "xoxb-test-token-12345",
            "SLACK_APP_TOKEN": "xapp-test-token-67890",
        }
        with patch("agents.slack_agent.get_secret", side_effect=lambda k, **kw: token_map.get(k)):
            yield

    @pytest.fixture
    def agent_for_classifier(self, agent_config, mock_secrets):
        """Create SlackAgent for testing query classifier."""
        with patch("agents.slack_agent.AsyncApp"):
            SlackAgent = get_slack_agent()
            agent = SlackAgent(agent_config)
            return agent

    def test_current_events_trigger_web_search(self, agent_for_classifier):
        """Current event queries should trigger web search."""
        agent = agent_for_classifier
        
        # Current news patterns
        should, reason = agent._should_web_search("What's the latest news about AI today?")
        assert should is True
        assert reason == "current events"

        should, reason = agent._should_web_search("What happened in tech this week?")
        assert should is True
        assert reason == "current events"

        should, reason = agent._should_web_search("Breaking news on climate change")
        assert should is True
        assert reason == "current events"

    def test_external_lookup_triggers_web_search(self, agent_for_classifier):
        """Factual lookup queries should trigger web search."""
        agent = agent_for_classifier

        should, reason = agent._should_web_search("What is the population of France?")
        assert should is True
        assert reason == "external lookup"

        should, reason = agent._should_web_search("How do I configure nginx?")
        assert should is True
        assert reason == "external lookup"

        should, reason = agent._should_web_search("Define machine learning concepts")
        assert should is True
        assert reason == "external lookup"

    def test_personal_queries_skip_web_search(self, agent_for_classifier):
        """Personal context queries should NOT trigger web search."""
        agent = agent_for_classifier

        should, reason = agent._should_web_search("What did my notes say about project X?")
        assert should is False
        assert reason == "personal context"

        should, reason = agent._should_web_search("What do I know about machine learning?")
        assert should is False
        assert reason == "personal context"

        should, reason = agent._should_web_search("From my journal, what goals did I set?")
        assert should is False
        assert reason == "personal context"

    def test_short_queries_skip_web_search(self, agent_for_classifier):
        """Very short queries should not trigger web search."""
        agent = agent_for_classifier

        should, reason = agent._should_web_search("Hello")
        assert should is False
        assert reason == "query too short"

        should, reason = agent._should_web_search("What?")
        assert should is False

    def test_ambiguous_queries_default_to_brain(self, agent_for_classifier):
        """Ambiguous queries should prefer brain search."""
        agent = agent_for_classifier

        should, reason = agent._should_web_search("Tell me something interesting about productivity")
        assert should is False
        assert reason == "default to brain"


@pytest.mark.integration
class TestWebSearchIntegration:
    """Tests for web search integration in message processing."""

    @pytest.fixture
    def agent_config(self, test_brain_path):
        """Configuration for test Slack agent with web search enabled"""
        return {
            "search_url": "http://nuc-1.local:9514",
            "ollama_url": "http://m1-mini.local:11434",
            "brain_path": str(test_brain_path),
            "model": "llama3.2",
            "max_context_tokens": 6000,
            "enable_search": True,
            "enable_web_search": True,
            "max_search_results": 3,
            "notification": {"enabled": False},
        }

    @pytest.fixture
    def mock_secrets(self):
        """Mock Vaultwarden get_secret for Slack tokens"""
        token_map = {
            "SLACK_BOT_TOKEN": "xoxb-test-token-12345",
            "SLACK_APP_TOKEN": "xapp-test-token-67890",
        }
        with patch("agents.slack_agent.get_secret", side_effect=lambda k, **kw: token_map.get(k)):
            yield

    @pytest.fixture
    async def agent_with_all_mocks(self, agent_config, mock_secrets, mock_search, mock_llm):
        """Create agent with all dependencies mocked."""
        with patch("agents.slack_agent.AsyncApp"):
            SlackAgent = get_slack_agent()
            agent = SlackAgent(agent_config)
            agent.search = mock_search
            agent.llm = mock_llm

            # Mock conversations
            agent.conversations = MagicMock()
            agent.conversations.load_conversation = AsyncMock(return_value=[])
            agent.conversations.save_message = AsyncMock()
            agent.conversations.summarize_if_needed = AsyncMock(return_value=[])
            agent.conversations.count_conversation_tokens = MagicMock(return_value=100)
            agent.conversations.search_past_conversations = AsyncMock(return_value=[])

            agent.brain = MagicMock()
            
            # Mock web search
            agent.web_search = MagicMock()
            agent.web_search.search = AsyncMock(return_value=[])
            agent.web_search.format_results = MagicMock(return_value="")
            
            yield agent

    @pytest.mark.asyncio
    async def test_web_search_called_for_news_query(
        self, agent_with_all_mocks, mock_web_search_results
    ):
        """Web search should be called for current events queries."""
        agent = agent_with_all_mocks
        agent.web_search.search = AsyncMock(return_value=mock_web_search_results)
        agent.web_search.format_results = MagicMock(return_value="**Web results**\n...")

        await agent._process_message(
            user_id="U123",
            text="What's the latest news about AI today?",
            thread_id="T123",
        )

        # Web search should have been called
        agent.web_search.search.assert_called_once()
        agent.web_search.format_results.assert_called_once()

    @pytest.mark.asyncio
    async def test_web_search_not_called_for_personal_query(self, agent_with_all_mocks):
        """Web search should NOT be called for personal context queries."""
        agent = agent_with_all_mocks

        await agent._process_message(
            user_id="U123",
            text="What did my notes say about project planning?",
            thread_id="T123",
        )

        # Web search should NOT have been called
        agent.web_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_search_skipped_when_disabled(self, agent_with_all_mocks):
        """Web search should be skipped when enable_web_search is False."""
        agent = agent_with_all_mocks
        agent.enable_web_search = False

        await agent._process_message(
            user_id="U123",
            text="What's the latest news about AI today?",
            thread_id="T123",
        )

        # Web search should NOT have been called
        agent.web_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_search_skipped_when_attachments_present(
        self, agent_with_all_mocks
    ):
        """Web search should be skipped when file attachments are present."""
        agent = agent_with_all_mocks

        await agent._process_message(
            user_id="U123",
            text="Analyze this file about AI news",
            thread_id="T123",
            has_attachments=True,
        )

        # Web search should NOT have been called (file is the context)
        agent.web_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_search_failure_continues_without_crash(
        self, agent_with_all_mocks
    ):
        """Web search failure should not crash the bot."""
        agent = agent_with_all_mocks
        agent.web_search.search = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise
        response = await agent._process_message(
            user_id="U123",
            text="What's the latest news about AI today?",
            thread_id="T123",
        )

        # LLM response should still be returned despite web search failure
        assert response is not None
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_metadata_includes_web_search_flag(
        self, agent_with_all_mocks, mock_web_search_results
    ):
        """Saved conversation should include web_search_used metadata."""
        agent = agent_with_all_mocks
        agent.web_search.search = AsyncMock(return_value=mock_web_search_results)
        agent.web_search.format_results = MagicMock(return_value="**Web results**\n...")

        await agent._process_message(
            user_id="U123",
            text="What's the latest news about AI today?",
            thread_id="T123",
        )

        # Check save_message was called with web_search_used metadata
        calls = agent.conversations.save_message.call_args_list
        # Second call should be assistant message with metadata
        assistant_call = calls[1]
        metadata = assistant_call.kwargs.get("metadata", {})
        assert metadata.get("web_search_used") is True
