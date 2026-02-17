"""
Unit tests for MCP SSE Client — JSON-RPC over HTTP/SSE transport.

Tests the MCPSSEClient without making real HTTP requests.
All aiohttp I/O is mocked.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from slack_bot.tools.mcp.mcp_sse_client import MCPSSEClient
from slack_bot.tools.mcp.mcp_client import (
    MCPClientError,
    MCPConnectionError,
    MCPToolCallError,
)


# ---- Helpers ----


def _json_response(data: dict, status: int = 200):
    """Create a mock aiohttp response returning JSON."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    resp.text = AsyncMock(return_value=json.dumps(data))
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _sse_response(lines: list, status: int = 200):
    """Create a mock aiohttp response returning SSE lines."""
    resp = AsyncMock()
    resp.status = status

    # Mock async iterator for content
    async def _iter():
        for line in lines:
            yield line.encode("utf-8") if isinstance(line, str) else line

    resp.content = MagicMock()
    resp.content.__aiter__ = _iter
    resp.content.readline = AsyncMock(side_effect=lines_as_bytes(lines))

    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def lines_as_bytes(lines):
    """Convert list of strings to bytes for readline mock."""
    encoded = [l.encode("utf-8") if isinstance(l, str) else l for l in lines]
    idx = [0]

    async def readline():
        if idx[0] < len(encoded):
            val = encoded[idx[0]]
            idx[0] += 1
            return val
        return b""

    return readline


def _make_jsonrpc_result(request_id: int, result: dict) -> dict:
    """Create a JSON-RPC success response dict."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _make_jsonrpc_error(request_id: int, code: int, message: str) -> dict:
    """Create a JSON-RPC error response dict."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


# ---- Tests ----


@pytest.mark.unit
class TestMCPSSEClientInit:
    """Test SSE client initialization and properties."""

    def test_create_client(self):
        client = MCPSSEClient(url="http://localhost:8080/mcp")
        assert client.url == "http://localhost:8080/mcp"
        assert client.headers == {}
        assert not client.connected

    def test_create_client_with_headers(self):
        client = MCPSSEClient(
            url="http://localhost/mcp",
            headers={"Authorization": "Bearer token123"},
        )
        assert client.headers == {"Authorization": "Bearer token123"}

    def test_url_trailing_slash_stripped(self):
        client = MCPSSEClient(url="http://localhost:8080/mcp/")
        assert client.url == "http://localhost:8080/mcp"

    def test_not_connected_by_default(self):
        client = MCPSSEClient(url="http://localhost/mcp")
        assert not client.connected


@pytest.mark.unit
class TestMCPSSEClientConnect:
    """Test connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Successful connection discovers endpoint + initializes."""
        init_result = _make_jsonrpc_result(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-sse-server", "version": "2.0"},
        })

        with patch("aiohttp.ClientSession") as MockSession:
            session = AsyncMock()
            MockSession.return_value = session
            session.closed = False
            session.close = AsyncMock()

            # SSE endpoint discovery — GET /sse returns 404, fallback
            sse_resp = AsyncMock()
            sse_resp.status = 404
            sse_resp.__aenter__ = AsyncMock(return_value=sse_resp)
            sse_resp.__aexit__ = AsyncMock(return_value=False)

            # POST /message for initialize
            init_resp = _json_response(init_result)
            # POST for initialized notification
            notif_resp = _json_response({}, status=200)

            session.get = MagicMock(return_value=sse_resp)
            session.post = MagicMock(side_effect=[init_resp, notif_resp])

            client = MCPSSEClient(url="http://localhost:8080/mcp")
            await client.connect()

            assert client.connected
            assert client._server_info["name"] == "test-sse-server"
            assert client._message_endpoint == "http://localhost:8080/mcp/message"

    @pytest.mark.asyncio
    async def test_connect_fallback_endpoint(self):
        """Falls back to /message when SSE discovery fails."""
        init_result = _make_jsonrpc_result(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "fallback-test", "version": "1.0"},
        })

        with patch("aiohttp.ClientSession") as MockSession:
            session = AsyncMock()
            MockSession.return_value = session
            session.closed = False
            session.close = AsyncMock()

            # SSE returns 404 — triggers fallback
            sse_resp = AsyncMock()
            sse_resp.status = 404
            sse_resp.__aenter__ = AsyncMock(return_value=sse_resp)
            sse_resp.__aexit__ = AsyncMock(return_value=False)

            init_resp = _json_response(init_result)
            notif_resp = _json_response({}, status=200)

            session.get = MagicMock(return_value=sse_resp)
            session.post = MagicMock(side_effect=[init_resp, notif_resp])

            client = MCPSSEClient(url="http://localhost:8080/mcp")
            await client.connect()

            assert client.connected
            assert client._message_endpoint == "http://localhost:8080/mcp/message"

    @pytest.mark.asyncio
    async def test_connect_timeout(self):
        """Connection times out on SSE discovery."""
        with patch("aiohttp.ClientSession") as MockSession:
            session = AsyncMock()
            MockSession.return_value = session
            session.closed = False
            session.close = AsyncMock()

            # SSE discovery times out
            sse_resp = AsyncMock()
            sse_resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
            sse_resp.__aexit__ = AsyncMock(return_value=False)
            session.get = MagicMock(return_value=sse_resp)

            # POST also times out (init request)
            post_resp = AsyncMock()
            post_resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
            post_resp.__aexit__ = AsyncMock(return_value=False)
            session.post = MagicMock(return_value=post_resp)

            client = MCPSSEClient(url="http://localhost:8080/mcp")
            with pytest.raises(MCPConnectionError):
                await client.connect()

            assert not client.connected

    @pytest.mark.asyncio
    async def test_connect_network_error(self):
        """Connection fails on network error."""
        import aiohttp

        with patch("aiohttp.ClientSession") as MockSession:
            session = AsyncMock()
            MockSession.return_value = session
            session.closed = False
            session.close = AsyncMock()

            # SSE discovery fails with network error
            sse_resp = AsyncMock()
            sse_resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Network down"))
            sse_resp.__aexit__ = AsyncMock(return_value=False)
            session.get = MagicMock(return_value=sse_resp)

            # POST also fails
            post_resp = AsyncMock()
            post_resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Network down"))
            post_resp.__aexit__ = AsyncMock(return_value=False)
            session.post = MagicMock(return_value=post_resp)

            client = MCPSSEClient(url="http://localhost:8080/mcp")
            with pytest.raises(MCPConnectionError):
                await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Disconnect closes the session."""
        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        session.close = AsyncMock()
        client._session = session

        await client.disconnect()

        assert not client.connected
        session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """Disconnect is a no-op when not connected."""
        client = MCPSSEClient(url="http://localhost/mcp")
        await client.disconnect()  # Should not raise


@pytest.mark.unit
class TestMCPSSEClientListTools:
    """Test tools discovery."""

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """List tools returns tool definitions."""
        tools_result = _make_jsonrpc_result(1, {
            "tools": [
                {
                    "name": "search",
                    "description": "Search stuff",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                },
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                },
            ],
        })

        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        client._session = session
        client._message_endpoint = "http://localhost/mcp/message"

        session.post = MagicMock(return_value=_json_response(tools_result))

        tools = await client.list_tools()
        assert len(tools) == 2
        assert tools[0]["name"] == "search"
        assert tools[1]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_list_tools_not_connected(self):
        """Raises when not connected."""
        client = MCPSSEClient(url="http://localhost/mcp")
        with pytest.raises(MCPConnectionError, match="not connected"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_list_tools_empty(self):
        """Returns empty list when server has no tools."""
        tools_result = _make_jsonrpc_result(1, {"tools": []})
        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        client._session = session
        client._message_endpoint = "http://localhost/mcp/message"

        session.post = MagicMock(return_value=_json_response(tools_result))
        tools = await client.list_tools()
        assert tools == []


@pytest.mark.unit
class TestMCPSSEClientCallTool:
    """Test tool invocation."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """Successful tool call returns content blocks."""
        tool_result = _make_jsonrpc_result(1, {
            "content": [{"type": "text", "text": "Search result: found 3 items"}],
            "isError": False,
        })

        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        client._session = session
        client._message_endpoint = "http://localhost/mcp/message"

        session.post = MagicMock(return_value=_json_response(tool_result))

        content = await client.call_tool("search", {"query": "test"})
        assert len(content) == 1
        assert content[0]["text"] == "Search result: found 3 items"

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self):
        """Tool call with isError=true raises MCPToolCallError."""
        tool_result = _make_jsonrpc_result(1, {
            "content": [{"type": "text", "text": "Permission denied"}],
            "isError": True,
        })

        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        client._session = session
        client._message_endpoint = "http://localhost/mcp/message"

        session.post = MagicMock(return_value=_json_response(tool_result))

        with pytest.raises(MCPToolCallError, match="Permission denied"):
            await client.call_tool("admin_action", {"action": "delete"})

    @pytest.mark.asyncio
    async def test_call_tool_jsonrpc_error(self):
        """JSON-RPC error in response raises MCPClientError."""
        error_result = _make_jsonrpc_error(1, -32601, "Method not found")

        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        client._session = session
        client._message_endpoint = "http://localhost/mcp/message"

        session.post = MagicMock(return_value=_json_response(error_result))

        with pytest.raises(MCPToolCallError, match="Failed to call"):
            await client.call_tool("unknown_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        """Raises when not connected."""
        client = MCPSSEClient(url="http://localhost/mcp")
        with pytest.raises(MCPConnectionError, match="not connected"):
            await client.call_tool("search", {"query": "test"})

    @pytest.mark.asyncio
    async def test_call_tool_http_500(self):
        """HTTP 500 error raises MCPToolCallError."""
        error_resp = AsyncMock()
        error_resp.status = 500
        error_resp.text = AsyncMock(return_value="Internal Server Error")
        error_resp.__aenter__ = AsyncMock(return_value=error_resp)
        error_resp.__aexit__ = AsyncMock(return_value=False)

        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        client._session = session
        client._message_endpoint = "http://localhost/mcp/message"

        session.post = MagicMock(return_value=error_resp)

        with pytest.raises(MCPToolCallError, match="Failed to call"):
            await client.call_tool("search", {"query": "test"})

    @pytest.mark.asyncio
    async def test_call_tool_with_no_arguments(self):
        """Tool call without arguments sends empty dict."""
        tool_result = _make_jsonrpc_result(1, {
            "content": [{"type": "text", "text": "OK"}],
            "isError": False,
        })

        client = MCPSSEClient(url="http://localhost/mcp")
        client._connected = True
        session = AsyncMock()
        session.closed = False
        client._session = session
        client._message_endpoint = "http://localhost/mcp/message"

        session.post = MagicMock(return_value=_json_response(tool_result))

        content = await client.call_tool("ping")
        assert content[0]["text"] == "OK"


@pytest.mark.unit
class TestMCPSSEClientHelpers:
    """Test internal helper methods."""

    def test_extract_text_content(self):
        """Extract text from content blocks."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        result = MCPSSEClient._extract_text_content(content)
        assert result == "Hello\nWorld"

    def test_extract_text_content_empty(self):
        """Returns stringified content when no text blocks."""
        content = [{"type": "image", "url": "http://example.com/img.png"}]
        result = MCPSSEClient._extract_text_content(content)
        assert "image" in result

    def test_extract_text_content_no_blocks(self):
        """Returns stringified content for empty list."""
        result = MCPSSEClient._extract_text_content([])
        assert result == "[]"

    def test_ensure_connected_raises(self):
        client = MCPSSEClient(url="http://localhost/mcp")
        with pytest.raises(MCPConnectionError, match="not connected"):
            client._ensure_connected()
