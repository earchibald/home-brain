"""
Integration test: MCP stdio protocol — mock subprocess, test JSON-RPC logic.

Tests the MCPClient protocol handling without real subprocess spawning.
Validates: initialize handshake, tool listing, tool calling, error handling.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from slack_bot.tools.mcp.mcp_client import (
    MCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPToolCallError,
)


# ---- Helpers (matching test_mcp_client.py patterns) ----


def _make_response(request_id: int, result: dict) -> bytes:
    msg = {"jsonrpc": "2.0", "id": request_id, "result": result}
    return (json.dumps(msg) + "\n").encode("utf-8")


def _make_error_response(request_id: int, code: int, message: str) -> bytes:
    msg = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    return (json.dumps(msg) + "\n").encode("utf-8")


class MockStdin:
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
    def __init__(self, lines: list):
        self._lines = list(lines)
        self._index = 0

    async def readline(self):
        if self._index < len(self._lines):
            line = self._lines[self._index]
            self._index += 1
            return line if isinstance(line, bytes) else line.encode("utf-8")
        return b""


class MockProcess:
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


# ---- Integration Tests ----


@pytest.mark.integration
class TestMCPStdioProtocol:
    """Test full JSON-RPC protocol flow over mock stdio."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, monkeypatch):
        """Test connect → list_tools → call_tool → disconnect."""
        # Build response sequence: init, list_tools, call_tool
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "integration-test", "version": "1.0"},
        })
        tools_resp = _make_response(2, {
            "tools": [
                {
                    "name": "echo",
                    "description": "Echo input",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                    },
                },
            ],
        })
        call_resp = _make_response(3, {
            "content": [{"type": "text", "text": "Echoed: hello world"}],
            "isError": False,
        })

        process = MockProcess([init_resp, tools_resp, call_resp])

        async def mock_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        client = MCPClient(command="test-server", args=["--mode", "test"])

        # Connect
        await client.connect()
        assert client.connected

        # Verify init request sent
        init_msg = json.loads(process.stdin.written[0].decode("utf-8"))
        assert init_msg["method"] == "initialize"
        assert init_msg["params"]["protocolVersion"] == "2024-11-05"

        # List tools
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "echo"

        # Call tool
        content = await client.call_tool("echo", {"text": "hello world"})
        assert len(content) == 1
        assert "hello world" in content[0]["text"]

        # Disconnect
        await client.disconnect()
        assert not client.connected

    @pytest.mark.asyncio
    async def test_server_error_response(self, monkeypatch):
        """Server returns JSON-RPC error on tool call."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        error_resp = _make_error_response(2, -32601, "Method not found")

        process = MockProcess([init_resp, error_resp])

        async def mock_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        client = MCPClient(command="test-server")
        await client.connect()

        with pytest.raises(MCPClientError, match="Method not found"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_tool_call_with_error_flag(self, monkeypatch):
        """Tool call succeeds but isError=True in response."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        call_resp = _make_response(2, {
            "content": [{"type": "text", "text": "Access denied"}],
            "isError": True,
        })

        process = MockProcess([init_resp, call_resp])

        async def mock_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        client = MCPClient(command="test-server")
        await client.connect()

        with pytest.raises(MCPToolCallError, match="Access denied"):
            await client.call_tool("admin", {"action": "delete"})

    @pytest.mark.asyncio
    async def test_env_vars_passed_to_subprocess(self, monkeypatch):
        """Environment variables are forwarded to subprocess."""
        init_resp = _make_response(1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        })
        process = MockProcess([init_resp])
        captured_kwargs = {}

        async def mock_subprocess(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        client = MCPClient(
            command="test-server",
            env={"GITHUB_TOKEN": "ghp_test", "DEBUG": "1"},
        )
        await client.connect()

        # Verify env was passed to subprocess
        assert "env" in captured_kwargs
        assert captured_kwargs["env"]["GITHUB_TOKEN"] == "ghp_test"
        assert captured_kwargs["env"]["DEBUG"] == "1"
