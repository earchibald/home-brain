"""
Semantic Search Client - Query the ChromaDB-based semantic search service.

Drop-in replacement for KhojClient with API compatibility.
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a single search result from semantic search."""

    entry: str
    score: float
    file: str
    heading: str = ""  # Not used but kept for API compatibility
    corpus_id: str = ""  # Not used but kept for API compatibility


class SemanticSearchClient:
    """Async client for ChromaDB semantic search service."""

    def __init__(self, base_url: str = "http://nuc-1.local:42110", timeout: int = 30):
        """Initialize the client.
        
        Args:
            base_url: Base URL for semantic search service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout)
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _ensure_client(self):
        """Ensure async client is initialized."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)

    async def search(
        self, query: str, content_type: str = "markdown", limit: int = 5
    ) -> List[SearchResult]:
        """Search brain content via semantic search.

        Args:
            query: Search query (natural language)
            content_type: Ignored (kept for API compatibility)
            limit: Max results to return

        Returns:
            List of SearchResult objects
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/search"
            params = {
                "q": query,
                "limit": limit,
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            if not data:
                return []

            results = []
            for item in data:
                try:
                    results.append(
                        SearchResult(
                            entry=item.get("entry", ""),
                            score=item.get("score", 0.0),
                            file=item.get("file", ""),
                            heading="",  # Not provided by ChromaDB service
                            corpus_id="",  # Not provided by ChromaDB service
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse search result: {e}")
                    continue

            logger.info(f"Search query '{query}' returned {len(results)} results")
            return results

        except httpx.HTTPError as e:
            logger.error(f"Semantic search error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in search: {e}")
            return []

    async def search_by_folder(
        self, query: str, folder: str, content_type: str = "markdown"
    ) -> List[SearchResult]:
        """Search within a specific brain folder.

        Args:
            query: Search query
            folder: Folder name (e.g., "journal", "work", "learning")
            content_type: Ignored (kept for API compatibility)

        Returns:
            List of SearchResult objects from that folder
        """
        all_results = await self.search(query, content_type, limit=20)

        # Filter results by folder path
        folder_results = [r for r in all_results if f"/{folder}/" in r.file]

        logger.info(
            f"Filtered {len(folder_results)} results from folder '{folder}' "
            f"out of {len(all_results)} total"
        )
        return folder_results

    async def health_check(self) -> bool:
        """Check if semantic search service is available.

        Returns:
            True if service is healthy, False otherwise
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/health"
            response = await self.client.get(url)
            response.raise_for_status()
            
            data = response.json()
            return data.get("status") in ["healthy", "degraded"]

        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the search index.

        Returns:
            Dictionary with index statistics
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/stats"
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    async def trigger_reindex(self, force: bool = False):
        """Trigger index update.

        Args:
            force: If True, perform full re-index
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/update"
            params = {"force": str(force).lower()}
            response = await self.client.post(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Index update: {data.get('status')}")

        except Exception as e:
            logger.error(f"Failed to trigger reindex: {e}")

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None


# Alias for backward compatibility with KhojClient
KhojClient = SemanticSearchClient
