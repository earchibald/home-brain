"""
Semantic Search Client - Query the ChromaDB-based semantic search service.
"""

import httpx
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a single search result from semantic search."""

    entry: str
    score: float
    file: str
    heading: str = ""  # Not used but kept for API compatibility
    corpus_id: str = ""  # Not used but kept for API compatibility


@dataclass
class DocumentInfo:
    """Represents a single indexed document from the registry."""

    path: str
    chunks: int = 0
    indexed_at: str = ""
    size: int = 0
    gate: str = "ungated"


@dataclass
class DocumentListPage:
    """A page of documents from the listing endpoint."""

    items: List[DocumentInfo] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50


class SemanticSearchClient:
    """Async client for ChromaDB semantic search service."""

    def __init__(self, base_url: str = "http://nuc-1.local:9514", timeout: int = 30):
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

    # ------------------------------------------------------------------
    # Document management (index control)
    # ------------------------------------------------------------------

    async def list_documents(
        self, offset: int = 0, limit: int = 50, folder: Optional[str] = None
    ) -> DocumentListPage:
        """List indexed documents from the registry.

        Args:
            offset: Pagination offset
            limit: Page size
            folder: Optional folder prefix to filter by

        Returns:
            DocumentListPage with items and pagination info
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/documents"
            params: Dict[str, Any] = {"offset": offset, "limit": limit}
            if folder:
                params["folder"] = folder
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            items = [
                DocumentInfo(
                    path=item.get("path", ""),
                    chunks=item.get("chunks", 0),
                    indexed_at=item.get("indexed_at", ""),
                    size=item.get("size", 0),
                    gate=item.get("gate", "ungated"),
                )
                for item in data.get("items", [])
            ]
            return DocumentListPage(
                items=items,
                total=data.get("total", 0),
                offset=data.get("offset", offset),
                limit=data.get("limit", limit),
            )

        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return DocumentListPage()

    async def get_document_info(self, file_path: str) -> Optional[DocumentInfo]:
        """Get index info for a single document.

        Args:
            file_path: Relative path to the document

        Returns:
            DocumentInfo or None if not found
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/documents/{file_path}"
            response = await self.client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return DocumentInfo(
                path=data.get("path", file_path),
                chunks=data.get("chunks", 0),
                indexed_at=data.get("indexed_at", ""),
                size=data.get("size", 0),
                gate=data.get("gate", "ungated"),
            )

        except Exception as e:
            logger.error(f"Failed to get document info for {file_path}: {e}")
            return None

    async def ignore_document(self, file_path: str) -> bool:
        """Remove a document from the index and add it to the ignore list.

        Args:
            file_path: Relative path to the document

        Returns:
            True if successful
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/documents/{file_path}/ignore"
            response = await self.client.post(url)
            response.raise_for_status()
            logger.info(f"Ignored document: {file_path}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to ignore document {file_path}: {e.response.status_code} {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to ignore document {file_path}: {e}")
            return False

    async def delete_document(self, file_path: str) -> bool:
        """Delete a document from the index AND from disk.

        Will fail if the file is in a read-only gated directory.

        Args:
            file_path: Relative path to the document

        Returns:
            True if successful
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/documents/{file_path}/delete"
            response = await self.client.post(url)
            response.raise_for_status()
            logger.info(f"Deleted document: {file_path}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to delete document {file_path}: {e.response.status_code} {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete document {file_path}: {e}")
            return False

    async def upload_document(
        self,
        file_path: str,
        content: bytes,
        filename: str,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Upload a file to the brain index.

        Args:
            file_path: Target path relative to brain root (e.g., 'notes/meeting.md')
            content: File content as bytes
            filename: Original filename (for multipart form)
            overwrite: If True, overwrite existing file

        Returns:
            Dict with status, path, size, chunks, indexed
            Empty dict on failure

        Raises:
            None - returns empty dict on all errors, logs details
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/documents/upload"
            
            # Use multipart form data
            files = {"file": (filename, content)}
            data = {"file_path": file_path, "overwrite": str(overwrite).lower()}
            
            response = await self.client.post(url, files=files, data=data)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Uploaded document: {file_path} ({result.get('size', 0)} bytes, {result.get('chunks', 0)} chunks)")
            return result

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            try:
                error_detail = e.response.json().get("detail", error_detail)
            except Exception:
                pass
            logger.error(f"Failed to upload document {file_path}: {e.response.status_code} {error_detail}")
            return {"error": error_detail, "status_code": e.response.status_code}
        except Exception as e:
            logger.error(f"Failed to upload document {file_path}: {e}")
            return {"error": str(e)}

    async def get_gates(self) -> Dict[str, str]:
        """Get current directory gate configuration.

        Returns:
            Dict mapping directory prefix to gate mode ('readonly'/'readwrite')
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/config/gates"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("gates", {})

        except Exception as e:
            logger.error(f"Failed to get gates: {e}")
            return {}

    async def set_gate(self, directory: str, mode: str) -> bool:
        """Set a single directory gate.

        Args:
            directory: Directory prefix relative to brain root
            mode: 'readonly' or 'readwrite'

        Returns:
            True if successful
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/config/gates"
            response = await self.client.post(url, json={"directory": directory, "mode": mode})
            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(f"Failed to set gate {directory}={mode}: {e}")
            return False

    async def replace_gates(self, gates: Dict[str, str]) -> bool:
        """Replace all gates with a new mapping.

        Args:
            gates: Full mapping of directory → mode

        Returns:
            True if successful
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/config/gates"
            response = await self.client.put(url, json={"gates": gates})
            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(f"Failed to replace gates: {e}")
            return False

    async def get_registry_stats(self) -> Dict[str, Any]:
        """Get detailed index statistics including gates and ignore counts.

        Returns:
            Dict with total_files, total_chunks, gates, ignored_count
        """
        await self._ensure_client()

        try:
            url = f"{self.base_url}/api/registry/stats"
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to get registry stats: {e}")
            return {}

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None

