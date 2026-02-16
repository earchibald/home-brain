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

    async def search_conversations(
        self, query: str, user_id: str = None, limit: int = 2
    ) -> List[Dict]:
        """Search past conversations for relevant context via cxdb API.

        Iterates through recent contexts and turns, performing simple keyword
        matching to find relevant past exchanges.

        Args:
            query: Search query text.
            user_id: Optional user ID filter (unused currently).
            limit: Maximum results to return.

        Returns:
            List of dicts with user_message, assistant_message, timestamp.
        """
        await self._ensure_client()

        query_words = [w.lower() for w in query.split() if len(w) >= 3]
        if not query_words:
            return []

        try:
            contexts = await self.list_contexts()
            results = []

            for ctx in contexts[:20]:  # Limit context scan for performance
                ctx_id = ctx.get("context_id")
                if not ctx_id:
                    continue

                try:
                    turns = await self.get_turns(ctx_id, limit=50)

                    # Pair user/assistant turns
                    for i in range(len(turns) - 1):
                        if turns[i].get("type_id") != "chat.message":
                            continue
                        if turns[i + 1].get("type_id") != "chat.message":
                            continue

                        user_data = turns[i].get("data", {})
                        asst_data = turns[i + 1].get("data", {})

                        if (
                            user_data.get("role") != "user"
                            or asst_data.get("role") != "assistant"
                        ):
                            continue

                        combined = (
                            user_data.get("content", "")
                            + " "
                            + asst_data.get("content", "")
                        ).lower()
                        score = sum(1 for w in query_words if w in combined)

                        if score > 0:
                            results.append(
                                {
                                    "user_message": user_data.get("content", "")[:200],
                                    "assistant_message": asst_data.get("content", "")[
                                        :200
                                    ],
                                    "timestamp": turns[i].get("created_at", ""),
                                    "score": score,
                                }
                            )
                except Exception:
                    continue

            results.sort(key=lambda x: x.get("score", 0), reverse=True)
            return results[:limit]

        except Exception as e:
            logger.warning(f"cxdb conversation search failed: {e}")
            return []

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
