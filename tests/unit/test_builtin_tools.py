"""
Unit tests for WebSearchTool and BrainSearchTool — tool wrappers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from slack_bot.tools.base_tool import BaseTool, ToolResult
from slack_bot.tools.builtin.web_search_tool import WebSearchTool
from slack_bot.tools.builtin.brain_search_tool import BrainSearchTool


@pytest.fixture
def mock_web_client():
    client = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.format_results = MagicMock(return_value="formatted results")
    return client


@pytest.fixture
def mock_search_client():
    client = AsyncMock()
    client.search = AsyncMock(return_value=[])
    return client


@pytest.fixture
def web_tool(mock_web_client):
    return WebSearchTool(client=mock_web_client)


@pytest.fixture
def brain_tool(mock_search_client):
    return BrainSearchTool(client=mock_search_client)


@pytest.mark.unit
class TestWebSearchTool:
    """Tests for WebSearchTool."""

    def test_is_base_tool(self, web_tool):
        assert isinstance(web_tool, BaseTool)

    def test_metadata(self, web_tool):
        assert web_tool.name == "web_search"
        assert web_tool.category == "builtin"

    def test_parameters_schema(self, web_tool):
        schema = web_tool.parameters_schema
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    async def test_execute_no_query(self, web_tool):
        result = await web_tool.execute()
        assert not result.success
        assert "query" in result.error

    async def test_execute_no_results(self, web_tool, mock_web_client):
        mock_web_client.search.return_value = []
        result = await web_tool.execute(query="test query")
        assert result.success
        assert "No web results" in result.content

    async def test_execute_with_results(self, web_tool, mock_web_client):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"title": "Test", "url": "https://example.com"}
        mock_web_client.search.return_value = [mock_result]
        mock_web_client.format_results.return_value = "**Test**: https://example.com"

        result = await web_tool.execute(query="test query")
        assert result.success
        assert "Test" in result.content

    async def test_execute_search_error(self, web_tool, mock_web_client):
        mock_web_client.search.side_effect = Exception("network error")
        result = await web_tool.execute(query="test")
        assert not result.success
        assert "network error" in result.error

    def test_function_spec(self, web_tool):
        spec = web_tool.to_function_spec()
        assert spec["function"]["name"] == "web_search"

    def test_prompt_description(self, web_tool):
        desc = web_tool.to_prompt_description()
        assert "web_search" in desc
        assert "query" in desc


@pytest.mark.unit
class TestBrainSearchTool:
    """Tests for BrainSearchTool."""

    def test_is_base_tool(self, brain_tool):
        assert isinstance(brain_tool, BaseTool)

    def test_metadata(self, brain_tool):
        assert brain_tool.name == "brain_search"
        assert brain_tool.category == "builtin"

    async def test_execute_no_query(self, brain_tool):
        result = await brain_tool.execute()
        assert not result.success
        assert "query" in result.error

    async def test_execute_no_results(self, brain_tool, mock_search_client):
        mock_search_client.search.return_value = []
        result = await brain_tool.execute(query="test")
        assert result.success
        assert "No relevant notes" in result.content

    async def test_execute_with_results(self, brain_tool, mock_search_client):
        mock_result = MagicMock()
        mock_result.entry = "This is a test result about Python"
        mock_result.file = "notes/python.md"
        mock_result.score = 0.95
        mock_search_client.search.return_value = [mock_result]

        result = await brain_tool.execute(query="python")
        assert result.success
        assert "Python" in result.content
        assert "python.md" in result.content

    async def test_execute_filters_low_relevance(self, brain_tool, mock_search_client):
        high = MagicMock()
        high.entry = "High relevance"
        high.file = "a.md"
        high.score = 0.9

        low = MagicMock()
        low.entry = "Low relevance"
        low.file = "b.md"
        low.score = 0.3

        mock_search_client.search.return_value = [high, low]

        result = await brain_tool.execute(query="test")
        assert result.success
        # Should include high relevance but not low
        assert "High relevance" in result.content

    async def test_execute_keeps_at_least_one(self, brain_tool, mock_search_client):
        """Even if all results are below threshold, keep the best one."""
        low = MagicMock()
        low.entry = "Only result"
        low.file = "c.md"
        low.score = 0.3

        mock_search_client.search.return_value = [low]

        result = await brain_tool.execute(query="test")
        assert result.success
        assert "Only result" in result.content

    async def test_execute_search_error(self, brain_tool, mock_search_client):
        mock_search_client.search.side_effect = Exception("service down")
        result = await brain_tool.execute(query="test")
        assert not result.success
        assert "service down" in result.error
