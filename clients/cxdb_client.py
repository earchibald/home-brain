"""
CXDB Client - HTTP API wrapper for the AI Context Store.

Provides async methods for managing conversation contexts and turns
via the cxdb HTTP API (port 9010). Follows the SemanticSearchClient
pattern: httpx.AsyncClient, lazy init, health_check.
"""

import httpx
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CxdbError(Exception):
    """Base exception for cxdb client errors."""
    pass


class CxdbConnectionError(CxdbError):
    """Raised when cxdb is unreachable."""
    pass


class CxdbApiError(CxdbError):
    """Raised when cxdb returns an API error."""

    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class CxdbClient:
    """Async HTTP client for the cxdb AI Context Store."""

    def __init__(self, base_url: str = "http://nuc-1.local:9010", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout)
        self.client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        """Ensure async client is initialized (lazy init)."""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)

    async def health_check(self) -> bool:
        """Check if cxdb is reachable.

        Returns:
            True if cxdb responds to GET /v1/contexts, False otherwise.
        """
        await self._ensure_client()
        try:
            response = await self.client.get(f"{self.base_url}/v1/contexts")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"cxdb health check failed: {e}")
            return False

    async def list_contexts(self) -> List[Dict]:
        """List all contexts.

        Returns:
            List of context dicts from cxdb.

        Raises:
            CxdbConnectionError: If cxdb is unreachable.
            CxdbApiError: If cxdb returns an error.
        """
        await self._ensure_client()
        try:
            response = await self.client.get(f"{self.base_url}/v1/contexts")
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as e:
            raise CxdbConnectionError(f"Cannot connect to cxdb: {e}") from e
        except httpx.HTTPStatusError as e:
            raise CxdbApiError(str(e), status_code=e.response.status_code) from e

    async def create_context(self, base_turn_id: int = 0) -> int:
        """Create a new context.

        Args:
            base_turn_id: Base turn ID for branching (0 for new root context).

        Returns:
            The new context_id (int).

        Raises:
            CxdbConnectionError: If cxdb is unreachable.
            CxdbApiError: If cxdb returns an error.
        """
        await self._ensure_client()
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/contexts/create",
                json={"base_turn_id": str(base_turn_id)},
            )
            response.raise_for_status()
            data = response.json()
            return data["context_id"]
        except httpx.ConnectError as e:
            raise CxdbConnectionError(f"Cannot connect to cxdb: {e}") from e
        except httpx.HTTPStatusError as e:
            raise CxdbApiError(str(e), status_code=e.response.status_code) from e

    async def append_turn(
        self,
        context_id: int,
        role: str,
        content: str,
        model: Optional[str] = None,
    ) -> Dict:
        """Append a chat message turn to a context.

        Args:
            context_id: The context to append to.
            role: Message role ("user" or "assistant").
            content: Message content.
            model: Optional model name used for generation.

        Returns:
            Turn object with turn_id and turn_hash.

        Raises:
            CxdbConnectionError: If cxdb is unreachable.
            CxdbApiError: If cxdb returns an error.
        """
        await self._ensure_client()
        payload = {
            "type_id": "chat.message",
            "type_version": 1,
            "data": {"role": role, "content": content},
        }
        if model:
            payload["data"]["model"] = model

        try:
            response = await self.client.post(
                f"{self.base_url}/v1/contexts/{context_id}/append",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as e:
            raise CxdbConnectionError(f"Cannot connect to cxdb: {e}") from e
        except httpx.HTTPStatusError as e:
            raise CxdbApiError(str(e), status_code=e.response.status_code) from e

    async def get_turns(self, context_id: int, limit: int = 100) -> List[Dict]:
        """Get turns for a context.

        Args:
            context_id: The context to get turns for.
            limit: Maximum number of turns to return.

        Returns:
            List of turn dicts.

        Raises:
            CxdbConnectionError: If cxdb is unreachable.
            CxdbApiError: If cxdb returns an error.
        """
        await self._ensure_client()
        try:
            response = await self.client.get(
                f"{self.base_url}/v1/contexts/{context_id}/turns",
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as e:
            raise CxdbConnectionError(f"Cannot connect to cxdb: {e}") from e
        except httpx.HTTPStatusError as e:
            raise CxdbApiError(str(e), status_code=e.response.status_code) from e

    async def log_file_event(
        self, context_id: int, file_path: str, operation: str
    ) -> Dict:
        """Log a filesystem event as a turn in the context DAG.

        Args:
            context_id: The context to log the event in.
            file_path: Path of the file operated on.
            operation: Operation type (e.g. "write", "read", "delete").

        Returns:
            Turn object with turn_id and turn_hash.

        Raises:
            CxdbConnectionError: If cxdb is unreachable.
            CxdbApiError: If cxdb returns an error.
        """
        await self._ensure_client()
        payload = {
            "type_id": "filesystem.event",
            "type_version": 1,
            "data": {
                "path": file_path,
                "op": operation,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/v1/contexts/{context_id}/append",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as e:
            raise CxdbConnectionError(f"Cannot connect to cxdb: {e}") from e
        except httpx.HTTPStatusError as e:
            raise CxdbApiError(str(e), status_code=e.response.status_code) from e

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
