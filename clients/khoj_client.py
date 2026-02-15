"""
Khoj Client - Query and interact with Khoj semantic search engine on NUC-1
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a single search result from Khoj"""
    entry: str
    score: float
    file: str
    heading: str
    corpus_id: str


class KhojClient:
    """Async client for Khoj API on NUC-1 (192.168.1.195:42110)"""

    def __init__(self, base_url: str = "http://192.168.1.195:42110", timeout: int = 30):
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
        """Ensure async client is initialized"""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)

    async def search(
        self, 
        query: str, 
        content_type: str = "markdown",
        limit: int = 5
    ) -> List[SearchResult]:
        """
        Search brain content via Khoj
        
        Args:
            query: Search query (natural language)
            content_type: markdown, plaintext, or pdf
            limit: Max results to return
            
        Returns:
            List of SearchResult objects
        """
        await self._ensure_client()
        
        try:
            url = f"{self.base_url}/api/search"
            params = {
                "q": query,
                "type": content_type,
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
                    results.append(SearchResult(
                        entry=item.get("entry", ""),
                        score=item.get("score", 0),
                        file=item.get("additional", {}).get("file", ""),
                        heading=item.get("additional", {}).get("heading", ""),
                        corpus_id=item.get("corpus_id", ""),
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse search result: {e}")
                    continue
            
            logger.info(f"Search query '{query}' returned {len(results)} results")
            return results
            
        except httpx.HTTPError as e:
            logger.error(f"Khoj search error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in search: {e}")
            return []

    async def search_by_folder(
        self,
        query: str,
        folder: str,
        content_type: str = "markdown"
    ) -> List[SearchResult]:
        """
        Search within a specific brain folder
        
        Args:
            query: Search query
            folder: Folder name (e.g., "journal", "work", "learning")
            content_type: markdown, plaintext, or pdf
            
        Returns:
            List of SearchResult objects from that folder
        """
        all_results = await self.search(query, content_type)
        
        # Filter results by folder path
        filtered = [
            r for r in all_results 
            if f"/{folder}/" in r.file or r.file.endswith(f"/{folder}")
        ]
        
        return filtered

    async def get_recent_activity(
        self,
        hours: int = 24,
        folder: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of recent brain activity
        
        Args:
            hours: How many hours back to look
            folder: Optional folder to filter
            
        Returns:
            Dict with activity stats
        """
        # Query for recent files (this is a heuristic search)
        query = "recent created modified updated"
        results = await self.search(query, limit=20)
        
        if folder:
            results = [r for r in results if f"/{folder}/" in r.file]
        
        return {
            "total_results": len(results),
            "topics": list(set(r.heading.split("/")[0] for r in results)),
            "files": [r.file for r in results],
            "recent_activity": results[:5]
        }

    async def health_check(self) -> bool:
        """Check if Khoj is reachable and healthy"""
        await self._ensure_client()
        
        try:
            response = await self.client.get(f"{self.base_url}/api/settings")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Khoj health check failed: {e}")
            return False

    async def close(self):
        """Close the async client"""
        if self.client:
            await self.client.aclose()


# Convenience context manager
async def get_khoj_client(base_url: str = "http://192.168.1.195:42110") -> KhojClient:
    """Factory function to create and return a KhojClient"""
    return KhojClient(base_url)
