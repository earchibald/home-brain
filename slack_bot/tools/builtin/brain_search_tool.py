"""
Brain Search Tool — wraps SemanticSearchClient as a BaseTool.

Provides semantic search over the user's personal knowledge base.
"""

import logging
from typing import Any, Dict

from slack_bot.tools.base_tool import BaseTool, ToolResult
from clients.semantic_search_client import SemanticSearchClient
from slack_bot.hooks.source_tracker import get_tracker

logger = logging.getLogger(__name__)


class BrainSearchTool(BaseTool):
    """Search the user's personal knowledge base (brain) for relevant notes.

    Wraps the existing SemanticSearchClient with the BaseTool interface.
    """

    name = "brain_search"
    display_name = "Brain Search"
    description = (
        "Search the user's personal knowledge base (markdown notes, journals, "
        "documents) for relevant information. Use when the user asks about "
        "their own notes, projects, or previously stored knowledge."
    )
    category = "builtin"

    def __init__(self, client: SemanticSearchClient, min_relevance_score: float = 0.7):
        """Initialize with an existing SemanticSearchClient.

        Args:
            client: Configured SemanticSearchClient instance
            min_relevance_score: Minimum relevance threshold (0.0–1.0)
        """
        self._client = client
        self._min_score = min_relevance_score

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query for the knowledge base",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 3)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Execute a brain search.

        Args:
            query: Natural language search query
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
            results = await self._client.search(
                query=query, content_type="markdown", limit=limit
            )

            if not results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=f"No relevant notes found for: {query}",
                    raw=[],
                )

            # Filter by relevance score (keep at least 1)
            filtered = [
                r
                for r in results
                if getattr(r, "score", None) is None
                or r.score >= self._min_score
            ]
            if not filtered and results:
                filtered = [results[0]]

            # Format results
            lines = ["\n**Relevant context from your brain:**\n"]
            raw_results = []
            for i, result in enumerate(filtered, 1):
                snippet = result.entry[:200] if hasattr(result, "entry") else ""
                file_name = result.file if hasattr(result, "file") else ""
                score_str = ""
                if hasattr(result, "score") and result.score:
                    score_str = f" [relevance: {result.score:.0%}]"
                lines.append(f"{i}. {snippet}...")
                lines.append(f"   (Source: {file_name}{score_str})\n")
                raw_results.append({
                    "entry": snippet,
                    "file": file_name,
                    "score": getattr(result, "score", None),
                })

            # Record sources for citation hook
            tracker = get_tracker()
            if tracker:
                source_files = [r.get("file", "") for r in raw_results if r.get("file")]
                snippets = [r.get("entry", "")[:100] for r in raw_results]
                tracker.record_source(
                    tool_name=self.name,
                    success=True,
                    sources=source_files,
                    snippets=snippets,
                )

            return ToolResult(
                tool_name=self.name,
                success=True,
                content="\n".join(lines),
                raw=raw_results,
            )

        except Exception as e:
            logger.error(f"Brain search tool error: {e}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if semantic search service is available."""
        return await self._client.health_check()
