"""
Web Search Client - Search the web for current information.

Provides WebSearchClient for searching the web using DuckDuckGo or Tavily,
treating results as timestamped documents with source tracking.
"""

import logging
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class WebSearchResult:
    """A single web search result with provenance tracking."""

    title: str
    url: str
    snippet: str
    source_domain: str
    retrieved_at: str = field(default_factory=lambda: datetime.now().isoformat())
    score: float = 0.5

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_domain": self.source_domain,
            "retrieved_at": self.retrieved_at,
            "score": self.score,
        }


class WebSearchClient:
    """
    Search the web using DuckDuckGo (free) or Tavily (API key required).

    Usage:
        client = WebSearchClient(provider="duckduckgo")
        results = await client.search("Python programming", limit=5)
        for r in results:
            print(f"{r.title}: {r.url}")

    Providers:
        - duckduckgo: Free, no API key required
        - tavily: Requires TAVILY_API_KEY, better summaries
    """

    def __init__(
        self,
        provider: str = "duckduckgo",
        api_key: Optional[str] = None,
        timeout: int = 10,
        max_results: int = 5,
    ):
        """
        Initialize web search client.

        Args:
            provider: Search provider ("duckduckgo" or "tavily")
            api_key: API key (required for Tavily)
            timeout: Request timeout in seconds
            max_results: Default max results per search
        """
        self.provider = provider.lower()
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results

        if self.provider not in ("duckduckgo", "tavily"):
            raise ValueError(f"Unknown provider: {provider}. Use 'duckduckgo' or 'tavily'")

        if self.provider == "tavily" and not api_key:
            logger.warning("Tavily provider requires api_key; searches will fail without it")

    async def search(self, query: str, limit: Optional[int] = None) -> List[WebSearchResult]:
        """
        Search the web for the given query.

        Args:
            query: Search query string
            limit: Maximum results to return (defaults to self.max_results)

        Returns:
            List of WebSearchResult objects, ordered by relevance
        """
        limit = limit or self.max_results

        if not query or not query.strip():
            logger.warning("Empty search query")
            return []

        try:
            if self.provider == "duckduckgo":
                return await self._search_duckduckgo(query.strip(), limit)
            elif self.provider == "tavily":
                return await self._search_tavily(query.strip(), limit)
        except Exception as e:
            logger.error(f"Web search failed ({self.provider}): {e}")
            return []

        return []

    async def _search_duckduckgo(self, query: str, limit: int) -> List[WebSearchResult]:
        """Search using DuckDuckGo via ddgs library (sync API wrapped in asyncio)."""
        import asyncio

        try:
            from ddgs import DDGS
        except ImportError:
            logger.error("ddgs not installed. Run: pip install ddgs")
            return []

        results = []
        retrieved_at = datetime.now().isoformat()

        def _sync_search():
            """Run sync search in thread executor."""
            try:
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=limit))
            except Exception as e:
                logger.error(f"DuckDuckGo sync search error: {e}")
                return []

        try:
            # Run sync search in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            raw_results = await loop.run_in_executor(None, _sync_search)

            for r in raw_results:
                url = r.get("href", "")
                results.append(
                    WebSearchResult(
                        title=r.get("title", "Untitled"),
                        url=url,
                        snippet=r.get("body", ""),
                        source_domain=self._extract_domain(url),
                        retrieved_at=retrieved_at,
                        # Position-based scoring: first result = 1.0, decreasing
                        score=max(0.5, 1.0 - (len(results) * 0.1)),
                    )
                )
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")

        return results

    async def _search_tavily(self, query: str, limit: int) -> List[WebSearchResult]:
        """Search using Tavily API - requires API key."""
        if not self.api_key:
            logger.error("Tavily API key required but not provided")
            return []

        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed. Run: pip install httpx")
            return []

        results = []
        retrieved_at = datetime.now().isoformat()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": limit,
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                )
                response.raise_for_status()
                data = response.json()

            for r in data.get("results", []):
                url = r.get("url", "")
                results.append(
                    WebSearchResult(
                        title=r.get("title", "Untitled"),
                        url=url,
                        snippet=r.get("content", ""),
                        source_domain=self._extract_domain(url),
                        retrieved_at=retrieved_at,
                        score=r.get("score", 0.5),
                    )
                )
        except Exception as e:
            logger.error(f"Tavily search error: {e}")

        return results

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL."""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    async def health_check(self) -> bool:
        """
        Check if web search is available.

        Returns:
            True if search returns results for a test query
        """
        try:
            results = await self.search("test", limit=1)
            return len(results) > 0
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def format_results(
        self,
        results: List[WebSearchResult],
        max_snippet_length: int = 200,
        include_timestamp: bool = True,
    ) -> str:
        """
        Format search results as a context string for LLM prompts.

        Args:
            results: List of WebSearchResult objects
            max_snippet_length: Max characters per snippet
            include_timestamp: Whether to include retrieval timestamp

        Returns:
            Formatted string suitable for LLM context injection
        """
        if not results:
            return ""

        lines = ["\n**Web search results:**\n"]

        for i, r in enumerate(results, 1):
            snippet = r.snippet
            if len(snippet) > max_snippet_length:
                snippet = snippet[:max_snippet_length].rstrip() + "..."

            lines.append(f"{i}. **{r.title}**")
            lines.append(f"   {snippet}")
            source_info = f"Source: {r.source_domain}"
            if include_timestamp:
                date_part = r.retrieved_at[:10] if r.retrieved_at else "unknown"
                source_info += f" | Retrieved: {date_part}"
            lines.append(f"   _{source_info}_\n")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"WebSearchClient(provider='{self.provider}', max_results={self.max_results})"
