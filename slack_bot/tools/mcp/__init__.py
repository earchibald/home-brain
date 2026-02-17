"""MCP (Model Context Protocol) integration for Brain Assistant.

Provides:
- MCPClient: JSON-RPC over stdio transport
- MCPSSEClient: JSON-RPC over HTTP/SSE transport
- MCPToolAdapter: Wraps MCP tools as BaseTool instances
- MCPManager: Lifecycle management (connect/disconnect/register)
- MCPServerConfig: Config loading with local override merge
"""

from slack_bot.tools.mcp.mcp_client import MCPClient, MCPClientError, MCPConnectionError, MCPToolCallError
from slack_bot.tools.mcp.mcp_config import MCPServerConfig, has_vaultwarden_refs, load_mcp_config
from slack_bot.tools.mcp.mcp_manager import MCPManager
from slack_bot.tools.mcp.mcp_sse_client import MCPSSEClient
from slack_bot.tools.mcp.mcp_tool_adapter import MCPToolAdapter

__all__ = [
    "MCPClient",
    "MCPClientError",
    "MCPConnectionError",
    "MCPSSEClient",
    "MCPToolCallError",
    "MCPManager",
    "MCPServerConfig",
    "MCPToolAdapter",
    "has_vaultwarden_refs",
    "load_mcp_config",
]
