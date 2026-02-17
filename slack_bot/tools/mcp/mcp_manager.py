"""
MCP Manager — lifecycle management for MCP servers.

Handles the full lifecycle of MCP server connections:
- Load config (base + local merge)
- Resolve vaultwarden: secret references
- Start enabled servers (stdio subprocess or SSE HTTP)
- Register discovered tools in the ToolRegistry
- Disconnect servers (unregister tools, terminate/close)
- Reconnect on failure
- Supports stdio (Phase 5) and SSE (Phase 6) transports

Usage in slack_agent.py:
    self.mcp_manager = MCPManager(registry=self.tool_registry)
    await self.mcp_manager.startup()
    # ...
    await self.mcp_manager.shutdown()
"""

import logging
from typing import Any, Dict, List, Optional

from slack_bot.tools.mcp.mcp_client import MCPClient, MCPClientError, MCPConnectionError
from slack_bot.tools.mcp.mcp_config import (
    MCPServerConfig,
    has_vaultwarden_refs,
    load_mcp_config,
)
from slack_bot.tools.mcp.mcp_sse_client import MCPSSEClient
from slack_bot.tools.mcp.mcp_tool_adapter import MCPToolAdapter
from slack_bot.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPManager:
    """Manages the lifecycle of all MCP server connections.

    Attributes:
        registry: ToolRegistry for registering/unregistering MCP tools
        config_path: Path to base MCP config
        local_config_path: Path to local override config (or None for default)
        _configs: Loaded server configurations
        _clients: Active MCPClient instances by server name
        _tool_names: Tool names registered per server (for cleanup)
    """

    def __init__(
        self,
        registry: ToolRegistry,
        config_path: str = "config/mcp_servers.json",
        local_config_path: Optional[str] = None,
    ):
        """Initialize MCP Manager.

        Args:
            registry: ToolRegistry for tool registration
            config_path: Path to base config file
            local_config_path: Path to local override config
        """
        self.registry = registry
        self.config_path = config_path
        self.local_config_path = local_config_path

        self._configs: Dict[str, MCPServerConfig] = {}
        self._clients: Dict[str, MCPClient] = {}
        self._tool_names: Dict[str, List[str]] = {}  # server_name → [tool_names]

    async def startup(self) -> None:
        """Load configs and connect all enabled MCP servers.

        Resolves vaultwarden: secret references, then attempts to connect
        each enabled server. Connection failures are logged but don't
        prevent other servers from starting.
        """
        # Load and merge configs
        self._configs = load_mcp_config(
            base_path=self.config_path,
            local_path=self.local_config_path,
        )

        if not self._configs:
            logger.info("No MCP servers configured")
            return

        logger.info(f"Loaded {len(self._configs)} MCP server configs")

        # Connect enabled servers
        for name, config in self._configs.items():
            if not config.enabled:
                logger.debug(f"MCP server '{name}' is disabled, skipping")
                continue

            try:
                await self.connect_server(name)
            except Exception as e:
                logger.error(f"Failed to start MCP server '{name}': {e}")

    async def shutdown(self) -> None:
        """Disconnect all MCP servers and unregister their tools."""
        server_names = list(self._clients.keys())
        for name in server_names:
            try:
                await self.disconnect_server(name)
            except Exception as e:
                logger.error(f"Error disconnecting MCP server '{name}': {e}")

    async def connect_server(self, name: str) -> None:
        """Connect to a specific MCP server and register its tools.

        Args:
            name: Server name from config

        Raises:
            MCPConnectionError: If server is not in config or connection fails
        """
        config = self._configs.get(name)
        if not config:
            raise MCPConnectionError(f"No config for MCP server '{name}'")

        if config.transport not in ("stdio", "sse"):
            logger.warning(
                f"MCP server '{name}' uses unsupported transport '{config.transport}'"
            )
            return

        if config.transport == "stdio" and not config.command:
            raise MCPConnectionError(
                f"MCP server '{name}' has no command configured"
            )

        if config.transport == "sse" and not config.url:
            raise MCPConnectionError(
                f"MCP server '{name}' has no URL configured for SSE transport"
            )

        # Disconnect existing connection if any
        if name in self._clients:
            await self.disconnect_server(name)

        # Resolve vaultwarden: secret references in env and headers
        resolved_env = await self._resolve_secrets(config)
        resolved_headers = await self._resolve_header_secrets(config)

        # Create transport-specific client
        if config.transport == "sse":
            client = MCPSSEClient(
                url=config.url,
                headers=resolved_headers,
            )
        else:
            client = MCPClient(
                command=config.command,
                args=config.args,
                env=resolved_env,
            )

        try:
            await client.connect()
        except MCPConnectionError:
            raise
        except Exception as e:
            raise MCPConnectionError(
                f"Failed to connect MCP server '{name}': {e}"
            )

        self._clients[name] = client

        # Discover and register tools
        try:
            tools = await client.list_tools()
            registered = self._register_tools(name, tools, client)
            logger.info(
                f"MCP server '{name}' connected with {registered} tools"
            )
        except Exception as e:
            logger.error(f"Failed to list tools from MCP server '{name}': {e}")
            # Still keep the client connected — tools can be listed later

    async def disconnect_server(self, name: str) -> None:
        """Disconnect from a specific MCP server and unregister its tools.

        Args:
            name: Server name
        """
        # Unregister tools first
        tool_names = self._tool_names.pop(name, [])
        for tool_name in tool_names:
            try:
                self.registry.unregister(tool_name)
            except Exception:
                pass  # Tool may already be unregistered
        logger.debug(f"Unregistered {len(tool_names)} tools from MCP server '{name}'")

        # Disconnect client
        client = self._clients.pop(name, None)
        if client:
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting MCP client '{name}': {e}")

        logger.info(f"MCP server '{name}' disconnected")

    async def reconnect_server(self, name: str) -> None:
        """Reconnect to a server (disconnect then connect).

        Args:
            name: Server name
        """
        await self.disconnect_server(name)
        await self.connect_server(name)

    def get_server_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all configured MCP servers.

        Returns:
            Dict of server_name → {enabled, connected, transport, tools, description}
        """
        status = {}
        for name, config in self._configs.items():
            client = self._clients.get(name)
            tools = self._tool_names.get(name, [])
            status[name] = {
                "enabled": config.enabled,
                "connected": client.connected if client else False,
                "transport": config.transport,
                "tools": len(tools),
                "tool_names": tools,
                "description": config.description,
            }
        return status

    def _register_tools(
        self,
        server_name: str,
        mcp_tools: List[Dict[str, Any]],
        client: MCPClient,
    ) -> int:
        """Register MCP tools in the ToolRegistry.

        Args:
            server_name: MCP server name
            mcp_tools: Tool definitions from tools/list
            client: MCPClient for executing tools

        Returns:
            Number of tools registered
        """
        registered = 0
        tool_names = []

        for tool_def in mcp_tools:
            tool_name = tool_def.get("name", "")
            if not tool_name:
                logger.warning(f"MCP tool from '{server_name}' has no name, skipping")
                continue

            adapter = MCPToolAdapter(
                server_name=server_name,
                mcp_tool_name=tool_name,
                description=tool_def.get("description", ""),
                input_schema=tool_def.get("inputSchema", {"type": "object", "properties": {}}),
                client=client,
            )

            self.registry.register(adapter)
            tool_names.append(adapter.name)
            registered += 1

            logger.debug(f"Registered MCP tool: {adapter.name}")

        self._tool_names[server_name] = tool_names
        return registered

    async def _resolve_header_secrets(self, config: MCPServerConfig) -> Dict[str, str]:
        """Resolve vaultwarden: references in SSE transport headers.

        Similar to _resolve_secrets but for config.headers instead of config.env.
        """
        if not config.headers:
            return {}

        has_refs = any(
            isinstance(v, str) and v.startswith("vaultwarden:")
            for v in config.headers.values()
        )
        if not has_refs:
            return dict(config.headers)

        resolved = {}
        for key, value in config.headers.items():
            if isinstance(value, str) and value.startswith("vaultwarden:"):
                secret_name = value[len("vaultwarden:"):]
                try:
                    from clients.vaultwarden_client import get_secret

                    secret_value = get_secret(secret_name)
                    if secret_value:
                        resolved[key] = secret_value
                        logger.debug(f"Resolved secret for MCP header '{key}'")
                    else:
                        logger.warning(
                            f"Secret '{secret_name}' not found in Vaultwarden "
                            f"for MCP server header '{key}'"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to resolve secret '{secret_name}' for MCP header '{key}': {e}"
                    )
            else:
                resolved[key] = value

        return resolved

    async def _resolve_secrets(self, config: MCPServerConfig) -> Dict[str, str]:
        """Resolve vaultwarden: secret references in environment variables.

        Entries like "vaultwarden:GITHUB_TOKEN" are replaced with the
        actual secret value from VaultwardenClient.

        Non-vaultwarden values are passed through unchanged.

        Args:
            config: MCP server config

        Returns:
            Dict of resolved environment variables
        """
        if not has_vaultwarden_refs(config):
            return dict(config.env)

        resolved = {}
        for key, value in config.env.items():
            if isinstance(value, str) and value.startswith("vaultwarden:"):
                secret_name = value[len("vaultwarden:"):]
                try:
                    from clients.vaultwarden_client import get_secret

                    secret_value = get_secret(secret_name)
                    if secret_value:
                        resolved[key] = secret_value
                        logger.debug(f"Resolved secret for MCP env '{key}'")
                    else:
                        logger.warning(
                            f"Secret '{secret_name}' not found in Vaultwarden "
                            f"for MCP server env '{key}'"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to resolve secret '{secret_name}' for MCP env '{key}': {e}"
                    )
            else:
                resolved[key] = value

        return resolved
