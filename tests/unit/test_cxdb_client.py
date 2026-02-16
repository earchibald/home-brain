"""
Unit tests for CxdbClient - HTTP API wrapper for the AI Context Store.

Tests verify:
- Context creation returns context_id
- Append turn sends correct payload structure
- Get turns returns turn list
- Health check returns True when healthy
- Health check returns False on connection failure
- API errors raise CxdbApiError
- Filesystem event logging sends correct payload
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from clients.cxdb_client import CxdbClient, CxdbApiError, CxdbConnectionError


def _mock_response(status_code=200, json_data=None):
    """Helper to create a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
    else:
        response.raise_for_status.return_value = None
    return response


@pytest.mark.unit
class TestCxdbClient:
    """Unit tests for CxdbClient with mocked httpx."""

    @pytest.mark.asyncio
    async def test_create_context_returns_id(self):
        """create_context() POSTs to /v1/contexts/create and returns context_id."""
        client = CxdbClient("http://localhost:9010")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(200, {"context_id": 42})
        client.client = mock_http

        context_id = await client.create_context()

        assert context_id == 42
        mock_http.post.assert_called_once_with(
            "http://localhost:9010/v1/contexts/create",
            json={"base_turn_id": "0"},
        )

    @pytest.mark.asyncio
    async def test_append_turn_sends_correct_payload(self):
        """append_turn() sends chat.message payload with role and content."""
        client = CxdbClient("http://localhost:9010")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(
            200, {"turn_id": 7, "turn_hash": "abc123"}
        )
        client.client = mock_http

        result = await client.append_turn(
            context_id=42, role="user", content="Hello cxdb"
        )

        assert result["turn_id"] == 7
        assert result["turn_hash"] == "abc123"
        mock_http.post.assert_called_once_with(
            "http://localhost:9010/v1/contexts/42/append",
            json={
                "type_id": "chat.message",
                "type_version": 1,
                "data": {"role": "user", "content": "Hello cxdb"},
            },
        )

    @pytest.mark.asyncio
    async def test_get_turns_returns_turn_list(self):
        """get_turns() GETs turns and returns the list."""
        client = CxdbClient("http://localhost:9010")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        turns_data = [
            {"turn_id": 1, "type_id": "chat.message", "data": {"role": "user", "content": "hi"}},
            {"turn_id": 2, "type_id": "chat.message", "data": {"role": "assistant", "content": "hello"}},
        ]
        mock_http.get.return_value = _mock_response(200, turns_data)
        client.client = mock_http

        result = await client.get_turns(context_id=42)

        assert len(result) == 2
        assert result[0]["turn_id"] == 1
        mock_http.get.assert_called_once_with(
            "http://localhost:9010/v1/contexts/42/turns",
            params={"limit": 100},
        )

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_healthy(self):
        """health_check() returns True when cxdb responds successfully."""
        client = CxdbClient("http://localhost:9010")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.return_value = _mock_response(200, [])
        client.client = mock_http

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_failure(self):
        """health_check() returns False when cxdb is unreachable."""
        client = CxdbClient("http://localhost:9010")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = httpx.ConnectError("Connection refused")
        client.client = mock_http

        result = await client.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_create_context_raises_on_api_error(self):
        """create_context() raises CxdbApiError on HTTP error response."""
        client = CxdbClient("http://localhost:9010")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(500)
        client.client = mock_http

        with pytest.raises(CxdbApiError):
            await client.create_context()

    @pytest.mark.asyncio
    async def test_log_file_event_sends_filesystem_payload(self):
        """log_file_event() sends filesystem.event payload with path and op."""
        client = CxdbClient("http://localhost:9010")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post.return_value = _mock_response(
            200, {"turn_id": 10, "turn_hash": "fs123"}
        )
        client.client = mock_http

        result = await client.log_file_event(
            context_id=42, file_path="/brain/journal/today.md", operation="write"
        )

        assert result["turn_id"] == 10
        # Verify the payload structure
        call_args = mock_http.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["type_id"] == "filesystem.event"
        assert payload["type_version"] == 1
        assert payload["data"]["path"] == "/brain/journal/today.md"
        assert payload["data"]["op"] == "write"
        assert "timestamp" in payload["data"]
