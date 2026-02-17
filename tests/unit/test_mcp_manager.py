"""
Unit tests for MCP Manager — lifecycle management for MCP servers.

Tests use mock MCPClient to avoid spawning real subprocesses.
VaultwardenClient is mocked for secret resolution.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from slack_bot.tools.mcp.mcp_client import MCPClient, MCPConnectionError
from slack_bot.tools.mcp.mcp_sse_client import MCPSSEClient
from slack_bot.tools.mcp.mcp_config import MCPServerConfig
from slack_bot.tools.mcp.mcp_manager import MCPManager
from slack_bot.tools.tool_registry import ToolRegistry
from slack_bot.tools.tool_state import ToolStateStore


# ---- Fixtures ----


@pytest.fixture
def tool_state_store(tmp_path):
    """Create a ToolStateStore with tmp storage."""
    return ToolStateStore(storage_path=str(tmp_path / "tool-state.json"))


@pytest.fixture
def registry(tool_state_store):
    """Create a ToolRegistry."""
    return ToolRegistry(tool_state_store)


@pytest.fixture
def mcp_config_file(tmp_path):
    """Create a test MCP config file with one enabled and one disabled server."""
    config = {
        "mcpServers": {
            "test_server": {
                "transport": "stdio",
                "command": "echo",
                "args": ["hello"],
                "env": {},
                "enabled": True,
                "description": "Test MCP server",
            },
            "disabled_server": {
                "transport": "stdio",
                "command": "echo",
                "args": ["disabled"],
                "env": {},
                "enabled": False,
                "description": "Disabled MCP server",
            },
        }
    }
    path = str(tmp_path / "mcp_servers.json")
    with open(path, "w") as f:
        json.dump(config, f)
    return path


@pytest.fixture
def vault_config_file(tmp_path):
    """Create a config with vaultwarden secret references."""
    config = {
        "mcpServers": {
            "github": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@mcp/server-github"],
                "env": {"GITHUB_TOKEN": "vaultwarden:GITHUB_TOKEN"},
                "enabled": True,
                "description": "GitHub server",
            },
        }
    }
    path = str(tmp_path / "mcp_servers.json")
    with open(path, "w") as f:
        json.dump(config, f)
    return path


def _make_mock_client(tools=None, connect_error=None):
    """Create a mock MCPClient instance.

    Args:
        tools: List of tool defs to return from list_tools
        connect_error: Exception to raise on connect
    """
    client = AsyncMock(spec=MCPClient)
    client.connected = True

    if connect_error:
        client.connect.side_effect = connect_error
        client.connected = False
    else:
        client.connect.return_value = None

    client.list_tools.return_value = tools or []
    client.disconnect.return_value = None
    return client


# ---- Tests ----


@pytest.mark.unit
class TestMCPManagerInit:
    """Test manager initialization."""

    def test_init(self, registry):
        manager = MCPManager(registry=registry)
        assert manager.registry is registry
        assert manager._configs == {}
        assert manager._clients == {}

    def test_init_with_config_path(self, registry):
        manager = MCPManager(
            registry=registry,
            config_path="custom/path.json",
            local_config_path="custom/path.local.json",
        )
        assert manager.config_path == "custom/path.json"
        assert manager.local_config_path == "custom/path.local.json"


@pytest.mark.unit
class TestMCPManagerStartup:
    """Test startup and server connection."""

    @pytest.mark.asyncio
    async def test_startup_no_config_file(self, registry, tmp_path):
        """Startup with missing config is a no-op."""
        manager = MCPManager(
            registry=registry,
            config_path=str(tmp_path / "nonexistent.json"),
        )
        await manager.startup()
        assert len(manager._clients) == 0

    @pytest.mark.asyncio
    async def test_startup_skips_disabled(self, registry, mcp_config_file):
        """Startup skips disabled servers."""
        mock_client = _make_mock_client(tools=[
            {"name": "test_tool", "description": "Test", "inputSchema": {"type": "object", "properties": {}}},
        ])

        manager = MCPManager(registry=registry, config_path=mcp_config_file)

        with patch.object(manager, "connect_server", new_callable=AsyncMock) as mock_connect:
            await manager.startup()
            # Only test_server is enabled, disabled_server should be skipped
            mock_connect.assert_called_once_with("test_server")

    @pytest.mark.asyncio
    async def test_startup_handles_connection_failure(self, registry, mcp_config_file):
        """Startup logs errors but doesn't crash on connection failure."""
        manager = MCPManager(registry=registry, config_path=mcp_config_file)

        with patch.object(
            manager, "connect_server",
            new_callable=AsyncMock,
            side_effect=MCPConnectionError("Connection refused"),
        ):
            # Should not raise
            await manager.startup()


@pytest.mark.unit
class TestMCPManagerConnectServer:
    """Test connecting to individual servers."""

    @pytest.mark.asyncio
    async def test_connect_registers_tools(self, registry, mcp_config_file):
        """Connecting a server registers its tools in the registry."""
        mock_client = _make_mock_client(tools=[
            {"name": "create_issue", "description": "Create issue", "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}}},
            {"name": "list_repos", "description": "List repos", "inputSchema": {"type": "object", "properties": {}}},
        ])

        manager = MCPManager(registry=registry, config_path=mcp_config_file)
        manager._configs = {
            "test_server": MCPServerConfig(
                name="test_server",
                transport="stdio",
                command="echo",
                args=["hello"],
                enabled=True,
            ),
        }

        with patch(
            "slack_bot.tools.mcp.mcp_manager.MCPClient",
            return_value=mock_client,
        ):
            await manager.connect_server("test_server")

        # Check tools were registered
        assert registry.get("mcp_test_server_create_issue") is not None
        assert registry.get("mcp_test_server_list_repos") is not None
        assert len(manager._tool_names["test_server"]) == 2

    @pytest.mark.asyncio
    async def test_connect_unknown_server(self, registry, mcp_config_file):
        """Connecting unknown server raises."""
        manager = MCPManager(registry=registry, config_path=mcp_config_file)
        manager._configs = {}

        with pytest.raises(MCPConnectionError, match="No config"):
            await manager.connect_server("nonexistent")

    @pytest.mark.asyncio
    async def test_connect_sse_transport(self, registry):
        """SSE transport creates MCPSSEClient and connects."""
        mock_client = AsyncMock(spec=MCPSSEClient)
        mock_client.connected = True
        mock_client.connect.return_value = None
        mock_client.list_tools.return_value = [
            {"name": "remote_search", "description": "Remote search", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}},
        ]
        mock_client.disconnect.return_value = None

        manager = MCPManager(registry=registry)
        manager._configs = {
            "remote": MCPServerConfig(
                name="remote",
                transport="sse",
                url="http://localhost:8080/mcp",
                headers={"Authorization": "Bearer test"},
                enabled=True,
            ),
        }

        with patch(
            "slack_bot.tools.mcp.mcp_manager.MCPSSEClient",
            return_value=mock_client,
        ):
            await manager.connect_server("remote")

        assert "remote" in manager._clients
        assert registry.get("mcp_remote_remote_search") is not None

    @pytest.mark.asyncio
    async def test_connect_sse_missing_url(self, registry):
        """SSE transport without URL raises MCPConnectionError."""
        manager = MCPManager(registry=registry)
        manager._configs = {
            "remote": MCPServerConfig(
                name="remote",
                transport="sse",
                url="",
                enabled=True,
            ),
        }

        with pytest.raises(MCPConnectionError, match="no URL configured"):
            await manager.connect_server("remote")

    @pytest.mark.asyncio
    async def test_connect_reconnects_existing(self, registry):
        """Connecting already-connected server disconnects first."""
        manager = MCPManager(registry=registry)
        manager._configs = {
            "test": MCPServerConfig(
                name="test",
                transport="stdio",
                command="echo",
                enabled=True,
            ),
        }

        # Simulate existing connection
        old_client = _make_mock_client()
        manager._clients["test"] = old_client
        manager._tool_names["test"] = ["mcp_test_old_tool"]
        registry.register(MagicMock(name="mcp_test_old_tool"))

        new_client = _make_mock_client(tools=[
            {"name": "new_tool", "description": "New", "inputSchema": {"type": "object", "properties": {}}},
        ])

        with patch(
            "slack_bot.tools.mcp.mcp_manager.MCPClient",
            return_value=new_client,
        ):
            await manager.connect_server("test")

        # Old client should have been disconnected
        old_client.disconnect.assert_called_once()


@pytest.mark.unit
class TestMCPManagerDisconnect:
    """Test server disconnection."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_tools(self, registry):
        """Disconnect unregisters all tools from that server."""
        manager = MCPManager(registry=registry)

        # Set up mock state
        mock_client = _make_mock_client()
        manager._clients["test"] = mock_client
        manager._tool_names["test"] = ["mcp_test_tool_a", "mcp_test_tool_b"]

        # Register mock tools
        mock_tool_a = MagicMock()
        mock_tool_a.name = "mcp_test_tool_a"
        mock_tool_b = MagicMock()
        mock_tool_b.name = "mcp_test_tool_b"
        registry.register(mock_tool_a)
        registry.register(mock_tool_b)

        await manager.disconnect_server("test")

        assert "test" not in manager._clients
        assert "test" not in manager._tool_names
        assert registry.get("mcp_test_tool_a") is None
        assert registry.get("mcp_test_tool_b") is None
        mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_server(self, registry):
        """Disconnect non-existent server is a no-op."""
        manager = MCPManager(registry=registry)
        await manager.disconnect_server("nonexistent")  # Should not raise


@pytest.mark.unit
class TestMCPManagerShutdown:
    """Test full shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_all(self, registry):
        """Shutdown disconnects all connected servers."""
        manager = MCPManager(registry=registry)

        client_a = _make_mock_client()
        client_b = _make_mock_client()
        manager._clients = {"server_a": client_a, "server_b": client_b}
        manager._tool_names = {"server_a": [], "server_b": []}

        await manager.shutdown()

        assert len(manager._clients) == 0
        client_a.disconnect.assert_called_once()
        client_b.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_handles_errors(self, registry):
        """Shutdown continues if one disconnect fails."""
        manager = MCPManager(registry=registry)

        client_a = _make_mock_client()
        client_a.disconnect.side_effect = Exception("Disconnect failed")
        client_b = _make_mock_client()

        manager._clients = {"server_a": client_a, "server_b": client_b}
        manager._tool_names = {"server_a": [], "server_b": []}

        await manager.shutdown()  # Should not raise
        # server_b should still have been disconnected
        client_b.disconnect.assert_called_once()


@pytest.mark.unit
class TestMCPManagerStatus:
    """Test server status reporting."""

    def test_get_server_status(self, registry):
        """Status reports all configured servers."""
        manager = MCPManager(registry=registry)
        manager._configs = {
            "server_a": MCPServerConfig(
                name="server_a",
                transport="stdio",
                command="echo",
                enabled=True,
                description="Server A",
            ),
            "server_b": MCPServerConfig(
                name="server_b",
                transport="sse",
                enabled=False,
                description="Server B",
            ),
        }

        mock_client = MagicMock()
        mock_client.connected = True
        manager._clients = {"server_a": mock_client}
        manager._tool_names = {"server_a": ["mcp_server_a_tool1", "mcp_server_a_tool2"]}

        status = manager.get_server_status()

        assert status["server_a"]["enabled"] is True
        assert status["server_a"]["connected"] is True
        assert status["server_a"]["tools"] == 2
        assert status["server_b"]["enabled"] is False
        assert status["server_b"]["connected"] is False

    def test_get_server_status_empty(self, registry):
        """Status with no configs returns empty dict."""
        manager = MCPManager(registry=registry)
        assert manager.get_server_status() == {}


@pytest.mark.unit
class TestMCPManagerSecretResolution:
    """Test vaultwarden secret resolution."""

    @pytest.mark.asyncio
    async def test_resolve_plain_env(self, registry):
        """Non-vaultwarden env vars pass through unchanged."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(
            name="test",
            env={"PATH": "/usr/bin", "HOME": "/home/user"},
        )
        resolved = await manager._resolve_secrets(config)
        assert resolved == {"PATH": "/usr/bin", "HOME": "/home/user"}

    @pytest.mark.asyncio
    async def test_resolve_vaultwarden_refs(self, registry):
        """vaultwarden: prefixed values are resolved."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(
            name="test",
            env={"GITHUB_TOKEN": "vaultwarden:GITHUB_TOKEN", "EXTRA": "plain"},
        )

        with patch("slack_bot.tools.mcp.mcp_manager.get_secret", create=True) as mock_get:
            # Mock the import that happens inside the method
            with patch(
                "clients.vaultwarden_client.get_secret",
                return_value="ghp_test123",
            ):
                resolved = await manager._resolve_secrets(config)

        assert resolved["GITHUB_TOKEN"] == "ghp_test123"
        assert resolved["EXTRA"] == "plain"

    @pytest.mark.asyncio
    async def test_resolve_vaultwarden_failure(self, registry):
        """Failed Vaultwarden lookup logs warning, skips key."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(
            name="test",
            env={"TOKEN": "vaultwarden:MISSING_SECRET"},
        )

        with patch(
            "clients.vaultwarden_client.get_secret",
            side_effect=Exception("Vaultwarden unreachable"),
        ):
            resolved = await manager._resolve_secrets(config)

        # Missing secret should not be in resolved env
        assert "TOKEN" not in resolved


@pytest.mark.unit
class TestMCPManagerHeaderSecretResolution:
    """Test vaultwarden secret resolution for SSE headers."""

    @pytest.mark.asyncio
    async def test_resolve_plain_headers(self, registry):
        """Non-vaultwarden headers pass through unchanged."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(
            name="test",
            headers={"Content-Type": "application/json", "X-Custom": "value"},
        )
        resolved = await manager._resolve_header_secrets(config)
        assert resolved == {"Content-Type": "application/json", "X-Custom": "value"}

    @pytest.mark.asyncio
    async def test_resolve_empty_headers(self, registry):
        """Empty headers returns empty dict."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(name="test", headers={})
        resolved = await manager._resolve_header_secrets(config)
        assert resolved == {}

    @pytest.mark.asyncio
    async def test_resolve_no_headers(self, registry):
        """Config with no headers returns empty dict."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(name="test")
        resolved = await manager._resolve_header_secrets(config)
        assert resolved == {}

    @pytest.mark.asyncio
    async def test_resolve_vaultwarden_header_refs(self, registry):
        """vaultwarden: prefixed header values are resolved."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(
            name="test",
            headers={"Authorization": "vaultwarden:API_TOKEN", "X-Extra": "plain"},
        )

        with patch(
            "clients.vaultwarden_client.get_secret",
            return_value="Bearer secret123",
        ):
            resolved = await manager._resolve_header_secrets(config)

        assert resolved["Authorization"] == "Bearer secret123"
        assert resolved["X-Extra"] == "plain"

    @pytest.mark.asyncio
    async def test_resolve_header_vaultwarden_failure(self, registry):
        """Failed Vaultwarden lookup logs error, skips header."""
        manager = MCPManager(registry=registry)
        config = MCPServerConfig(
            name="test",
            headers={"Authorization": "vaultwarden:MISSING_SECRET"},
        )

        with patch(
            "clients.vaultwarden_client.get_secret",
            side_effect=Exception("Vaultwarden unreachable"),
        ):
            resolved = await manager._resolve_header_secrets(config)

        assert "Authorization" not in resolved
