"""
Web Search Tool — wraps WebSearchClient as a BaseTool.

Provides web search capability through the unified tool interface.
"""

import logging
from typing import Any, Dict

from slack_bot.tools.base_tool import BaseTool, ToolResult
from clients.web_search_client import WebSearchClient

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Search the web for current information, facts, and news.

    Wraps the existing WebSearchClient with the BaseTool interface.
    """

    name = "web_search"
    display_name = "Web Search"
    description = (
        "Search the web for current information, facts, news, prices, "
        "recipes, comparisons, and real-world data. Use for any question "
        "about things outside the user's personal knowledge base."
    )
    category = "builtin"

    def __init__(self, client: WebSearchClient):
        """Initialize with an existing WebSearchClient.

        Args:
            client: Configured WebSearchClient instance
        """
        self._client = client

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the web",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 3)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Execute a web search.

        Args:
            query: Search query string
            limit: Max results (default 3)

        Returns:
            ToolResult with formatted search results
        """
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 3)

        if not query:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Missing required parameter: query",
            )

        try:
            results = await self._client.search(query, limit=limit)
            if not results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=f"No web results found for: {query}",
                    raw=[],
                )

            formatted = self._client.format_results(results, max_snippet_length=200)
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=formatted,
                raw=[r.to_dict() for r in results],
            )

        except Exception as e:
            logger.error(f"Web search tool error: {e}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if web search is available."""
        return await self._client.health_check()
