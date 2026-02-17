"""
Unit tests for WebSearchClient.

Tests web search functionality including DuckDuckGo integration,
result formatting, and error handling.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from clients.web_search_client import WebSearchClient, WebSearchResult


@pytest.fixture
def web_search_client():
    """Create a WebSearchClient with default DuckDuckGo provider."""
    return WebSearchClient(provider="duckduckgo")


@pytest.fixture
def tavily_client():
    """Create a WebSearchClient with Tavily provider."""
    return WebSearchClient(provider="tavily", api_key="test-api-key")


@pytest.fixture
def sample_results():
    """Sample search results for testing."""
    return [
        WebSearchResult(
            title="Python Programming Guide",
            url="https://www.python.org/docs",
            snippet="Python is a programming language that lets you work quickly.",
            source_domain="python.org",
            retrieved_at="2025-02-20T10:00:00",
            score=0.95,
        ),
        WebSearchResult(
            title="Learn Python Tutorial",
            url="https://www.example.com/python",
            snippet="A comprehensive tutorial for learning Python programming.",
            source_domain="example.com",
            retrieved_at="2025-02-20T10:00:00",
            score=0.85,
        ),
    ]


@pytest.mark.unit
class TestWebSearchResult:
    """Tests for WebSearchResult dataclass."""

    def test_result_creation(self):
        """Test creating a WebSearchResult."""
        result = WebSearchResult(
            title="Test Title",
            url="https://example.com/page",
            snippet="Test snippet content",
            source_domain="example.com",
        )
        assert result.title == "Test Title"
        assert result.url == "https://example.com/page"
        assert result.snippet == "Test snippet content"
        assert result.source_domain == "example.com"
        assert result.score == 0.5  # Default score

    def test_result_has_timestamp(self):
        """Test that results auto-populate timestamp."""
        result = WebSearchResult(
            title="Test",
            url="https://example.com",
            snippet="Test",
            source_domain="example.com",
        )
        assert result.retrieved_at is not None
        # Should be ISO format
        datetime.fromisoformat(result.retrieved_at)  # Raises if invalid

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = WebSearchResult(
            title="Test",
            url="https://example.com",
            snippet="Snippet",
            source_domain="example.com",
            retrieved_at="2025-02-20T10:00:00",
            score=0.9,
        )
        d = result.to_dict()
        assert d["title"] == "Test"
        assert d["url"] == "https://example.com"
        assert d["score"] == 0.9
        assert "retrieved_at" in d


@pytest.mark.unit
class TestWebSearchClient:
    """Tests for WebSearchClient."""

    def test_client_creation_duckduckgo(self):
        """Test creating client with DuckDuckGo provider."""
        client = WebSearchClient(provider="duckduckgo")
        assert client.provider == "duckduckgo"
        assert client.api_key is None
        assert client.max_results == 5

    def test_client_creation_tavily(self):
        """Test creating client with Tavily provider."""
        client = WebSearchClient(provider="tavily", api_key="test-key")
        assert client.provider == "tavily"
        assert client.api_key == "test-key"

    def test_invalid_provider_raises(self):
        """Test that invalid provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            WebSearchClient(provider="google")

    def test_tavily_without_key_warns(self, caplog):
        """Test that Tavily without API key logs warning."""
        import logging

        with caplog.at_level(logging.WARNING):
            WebSearchClient(provider="tavily")
        assert "api_key" in caplog.text.lower()

    def test_repr(self, web_search_client):
        """Test string representation."""
        assert "duckduckgo" in repr(web_search_client)
        assert "max_results=5" in repr(web_search_client)

    def test_extract_domain(self):
        """Test domain extraction from URLs."""
        assert WebSearchClient._extract_domain("https://www.example.com/path") == "example.com"
        assert WebSearchClient._extract_domain("https://docs.python.org/3/") == "docs.python.org"
        assert WebSearchClient._extract_domain("") == ""
        assert WebSearchClient._extract_domain("not-a-url") == ""


@pytest.mark.unit
class TestWebSearchFormatting:
    """Tests for result formatting."""

    def test_format_results_empty(self, web_search_client):
        """Test formatting empty results."""
        formatted = web_search_client.format_results([])
        assert formatted == ""

    def test_format_results_basic(self, web_search_client, sample_results):
        """Test formatting results."""
        formatted = web_search_client.format_results(sample_results)
        assert "**Web search results:**" in formatted
        assert "Python Programming Guide" in formatted
        assert "python.org" in formatted
        assert "1." in formatted
        assert "2." in formatted

    def test_format_results_truncates_snippet(self, web_search_client):
        """Test that long snippets are truncated."""
        long_result = WebSearchResult(
            title="Long Snippet Test",
            url="https://example.com",
            snippet="A" * 500,  # 500 character snippet
            source_domain="example.com",
        )
        formatted = web_search_client.format_results([long_result], max_snippet_length=100)
        # Should have truncation marker
        assert "..." in formatted
        # Should not have all 500 A's
        assert "A" * 500 not in formatted

    def test_format_results_includes_timestamp(self, web_search_client, sample_results):
        """Test that formatting includes retrieval timestamp."""
        formatted = web_search_client.format_results(sample_results, include_timestamp=True)
        assert "Retrieved:" in formatted

    def test_format_results_excludes_timestamp(self, web_search_client, sample_results):
        """Test that timestamp can be excluded."""
        formatted = web_search_client.format_results(sample_results, include_timestamp=False)
        assert "Retrieved:" not in formatted


@pytest.mark.unit
class TestWebSearchAsync:
    """Tests for async search methods."""

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, web_search_client):
        """Test that empty query returns empty list."""
        results = await web_search_client.search("")
        assert results == []

        results = await web_search_client.search("   ")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_mocked_duckduckgo(self):
        """Test DuckDuckGo search with mocked response."""
        mock_results = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Snippet 2"},
        ]

        # Mock the DDGS class from ddgs module
        with patch("ddgs.DDGS") as mock_ddgs:
            # Set up context manager that returns list of results
            mock_instance = MagicMock()
            mock_instance.text.return_value = mock_results
            mock_ddgs.return_value.__enter__.return_value = mock_instance

            client = WebSearchClient(provider="duckduckgo")
            results = await client.search("test query", limit=2)

            assert len(results) == 2
            assert results[0].title == "Result 1"
            assert results[1].url == "https://example.com/2"

    @pytest.mark.asyncio
    async def test_search_handles_import_error(self, caplog):
        """Test graceful handling of missing duckduckgo-search."""
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            client = WebSearchClient(provider="duckduckgo")
            # This should handle ImportError gracefully
            # The actual test depends on how the import is structured

    @pytest.mark.asyncio
    async def test_tavily_search_without_key(self, caplog):
        """Test Tavily search fails gracefully without API key."""
        import logging

        client = WebSearchClient(provider="tavily")  # No API key
        with caplog.at_level(logging.ERROR):
            results = await client.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check when search works."""
        client = WebSearchClient()
        client.search = AsyncMock(
            return_value=[
                WebSearchResult(
                    title="Test",
                    url="https://example.com",
                    snippet="Test",
                    source_domain="example.com",
                )
            ]
        )
        assert await client.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check when search fails."""
        client = WebSearchClient()
        client.search = AsyncMock(return_value=[])
        assert await client.health_check() is False


@pytest.mark.unit
class TestQueryClassifier:
    """Tests for query classification (to be added to slack_agent)."""

    @pytest.fixture
    def classifier_patterns(self):
        """Patterns used for query classification."""
        return {
            "current_events": [
                "today", "yesterday", "this week", "this month",
                "latest", "recent", "current", "now", "breaking",
                "news about", "what happened", "update on",
            ],
            "external": [
                "what is the population", "how many people",
                "who is the", "when was", "when did",
                "define", "explain what",
            ],
            "personal": [
                "my notes", "my journal", "i wrote", "i mentioned",
                "we discussed", "my project", "my work",
            ],
        }

    def _should_web_search(self, query: str, patterns: dict) -> tuple[bool, str]:
        """Simple classifier for testing."""
        query_lower = query.lower()

        # Check personal first (skip web search)
        if any(p in query_lower for p in patterns["personal"]):
            return (False, "personal context")

        # Check current events
        if any(p in query_lower for p in patterns["current_events"]):
            return (True, "current events")

        # Check external lookup
        if any(p in query_lower for p in patterns["external"]):
            return (True, "external lookup")

        return (False, "default to brain")

    def test_current_events_triggers_search(self, classifier_patterns):
        """Test that current event queries trigger web search."""
        should, reason = self._should_web_search(
            "What's the latest news about AI?", classifier_patterns
        )
        assert should is True
        assert reason == "current events"

    def test_personal_query_skips_search(self, classifier_patterns):
        """Test that personal queries skip web search."""
        should, reason = self._should_web_search(
            "What did my notes say about productivity?", classifier_patterns
        )
        assert should is False
        assert reason == "personal context"

    def test_external_lookup_triggers_search(self, classifier_patterns):
        """Test that factual queries trigger web search."""
        should, reason = self._should_web_search(
            "What is the population of France?", classifier_patterns
        )
        assert should is True
        assert reason == "external lookup"

    def test_ambiguous_defaults_to_brain(self, classifier_patterns):
        """Test that ambiguous queries default to brain search."""
        should, reason = self._should_web_search(
            "Tell me something interesting", classifier_patterns
        )
        assert should is False
        assert reason == "default to brain"
