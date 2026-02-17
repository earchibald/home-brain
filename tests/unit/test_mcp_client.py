"""
Unit tests for MCP Client — JSON-RPC over stdio transport.

Tests the MCPClient without spawning real subprocesses.
All subprocess I/O is mocked.
"""

import asyncio
import json
import pytest

from slack_bot.tools.mcp.mcp_client import (
    MCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPToolCallError,
)


# ---- Helpers ----


def _make_response(request_id: int, result: dict) -> bytes:
    """Create a JSON-RPC response line."""
    msg = {"jsonrpc": "2.0", "id": request_id, "result": result}
    return (json.dumps(msg) + "\n").encode("utf-8")


def _make_error_response(request_id: int, code: int, message: str) -> bytes:
    """Create a JSON-RPC error response line."""
    msg = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    return (json.dumps(msg) + "\n").encode("utf-8")


def _make_notification(method: str) -> bytes:
    """Create a JSON-RPC notification line."""
    msg = {"jsonrpc": "2.0", "method": method}
    return (json.dumps(msg) + "\n").encode("utf-8")


class MockStdin:
    """Mock asyncio subprocess stdin."""

    def __init__(self):
        self.written = []
        self._closing = False

    def write(self, data):
        self.written.append(data)

    async def drain(self):
        pass

    def close(self):
        self._closing = True

    async def wait_closed(self):
        pass

    def is_closing(self):
        return self._closing


class MockStdout:
    """Mock asyncio subprocess stdout — feeds predefined lines."""

    def __init__(self, lines: list):
        self._lines = list(lines)  # make copy
        self._index = 0

    async def readline(self):
        if self._index < len(self._lines):
            line = self._lines[self._index]
            self._index += 1
            return line if isinstance(line, bytes) else line.encode("utf-8")
        return b""


class MockProcess:
    """Mock asyncio subprocess."""

    def __init__(self, stdout_lines):
        self.stdin = MockStdin()
        self.stdout = MockStdout(stdout_lines)
        self.stderr = MockStdout([])
        self.pid = 12345
        self.returncode = None

    async def wait(self):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


# ---- Tests ----


@pytest.mark.unit
class TestMCPClientInit:
    """Test client initialization and properties."""

    def test_create_client(self):
        client = MCPClient(command="echo", args=["hello"])
        assert client.command == "echo"
        assert client.args == ["hello"]
        assert client.env == {}
        assert not client.connected

    def test_create_client_with_env(self):
        client = MCPClient(command="npx", args=["-y", "pkg"], env={"KEY": "val"})
        assert client.env == {"KEY": "val"}

    def test_not_connected_by_default(self):
        client = MCPClient(command="echo")
        assert not client.connected


@pytest.mark.unit
class TestMCPClientConnect:
    """Test connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_success(self, monkeypatch):
        """Successful connection sends initialize + notifications/initialized."""
        # Response for initialize (request id=1)
        init_response = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-server", "version": "1.0"},
        })

        process = MockProcess([init_response])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd", args=["--arg"])
        await client.connect()

        assert client.connected
        assert client._server_info["name"] == "test-server"

        # Verify initialize request was sent
        assert len(process.stdin.written) >= 1
        first_msg = json.loads(process.stdin.written[0].decode("utf-8"))
        assert first_msg["method"] == "initialize"
        assert first_msg["params"]["protocolVersion"] == "2024-11-05"

    @pytest.mark.asyncio
    async def test_connect_timeout(self, monkeypatch):
        """Connection times out if server doesn't respond."""
        # Empty stdout — will cause readline to return b""
        process = MockProcess([])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd")
        with pytest.raises(MCPConnectionError, match="Failed to connect"):
            await client.connect()

        assert not client.connected

    @pytest.mark.asyncio
    async def test_disconnect_graceful(self, monkeypatch):
        """Graceful disconnect closes stdin and waits."""
        init_response = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        process = MockProcess([init_response])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd")
        await client.connect()
        assert client.connected

        await client.disconnect()
        assert not client.connected
        assert process.stdin._closing

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """Disconnect is a no-op when not connected."""
        client = MCPClient(command="test-cmd")
        await client.disconnect()  # Should not raise


@pytest.mark.unit
class TestMCPClientListTools:
    """Test tools/list protocol."""

    @pytest.mark.asyncio
    async def test_list_tools(self, monkeypatch):
        """List tools returns tool definitions from server."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        tools_resp = _make_response(2, {
            "tools": [
                {
                    "name": "create_issue",
                    "description": "Create a GitHub issue",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                        "required": ["title"],
                    },
                },
                {
                    "name": "list_repos",
                    "description": "List repositories",
                    "inputSchema": {"type": "object", "properties": {}},
                },
            ]
        })

        process = MockProcess([init_resp, tools_resp])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd")
        await client.connect()
        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "create_issue"
        assert tools[1]["name"] == "list_repos"

    @pytest.mark.asyncio
    async def test_list_tools_not_connected(self):
        """list_tools raises when not connected."""
        client = MCPClient(command="test-cmd")
        with pytest.raises(MCPConnectionError, match="not connected"):
            await client.list_tools()


@pytest.mark.unit
class TestMCPClientCallTool:
    """Test tools/call protocol."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self, monkeypatch):
        """Successful tool call returns content blocks."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        call_resp = _make_response(2, {
            "content": [
                {"type": "text", "text": "Issue #42 created successfully"}
            ]
        })

        process = MockProcess([init_resp, call_resp])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd")
        await client.connect()
        result = await client.call_tool("create_issue", {"title": "Test"})

        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert "Issue #42" in result[0]["text"]

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self, monkeypatch):
        """Tool call with isError=True raises MCPToolCallError."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        error_resp = _make_response(2, {
            "content": [{"type": "text", "text": "Permission denied"}],
            "isError": True,
        })

        process = MockProcess([init_resp, error_resp])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd")
        await client.connect()

        with pytest.raises(MCPToolCallError, match="Permission denied"):
            await client.call_tool("create_issue", {"title": "Test"})

    @pytest.mark.asyncio
    async def test_call_tool_json_rpc_error(self, monkeypatch):
        """JSON-RPC error in response raises MCPClientError."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        rpc_error = _make_error_response(2, -32601, "Method not found")

        process = MockProcess([init_resp, rpc_error])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd")
        await client.connect()

        with pytest.raises(MCPToolCallError, match="Failed to call MCP tool"):
            await client.call_tool("nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        """call_tool raises when not connected."""
        client = MCPClient(command="test-cmd")
        with pytest.raises(MCPConnectionError, match="not connected"):
            await client.call_tool("test", {})


@pytest.mark.unit
class TestMCPClientProtocol:
    """Test JSON-RPC protocol handling edge cases."""

    @pytest.mark.asyncio
    async def test_skips_notifications_in_response_stream(self, monkeypatch):
        """Client skips server notifications while waiting for response."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        notification = _make_notification("some/event")
        tools_resp = _make_response(2, {
            "tools": [{"name": "test_tool", "description": "Test", "inputSchema": {"type": "object", "properties": {}}}]
        })

        process = MockProcess([init_resp, notification, tools_resp])

        async def mock_create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess)

        client = MCPClient(command="test-cmd")
        await client.connect()
        tools = await client.list_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"

    def test_extract_text_content_basic(self):
        """Extract text from content blocks."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        result = MCPClient._extract_text_content(content)
        assert result == "Hello\nWorld"

    def test_extract_text_content_empty(self):
        """Extract text from empty content."""
        assert MCPClient._extract_text_content([]) == "[]"

    def test_extract_text_content_non_text(self):
        """Non-text blocks are stringified."""
        content = [{"type": "image", "data": "base64..."}]
        result = MCPClient._extract_text_content(content)
        assert "image" in result
