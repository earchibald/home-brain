"""
MCP Tool Adapter — wraps an MCP tool schema as a BaseTool.

Each MCP server exposes multiple tools via tools/list. MCPToolAdapter
wraps one such tool so it can be registered in the ToolRegistry and
used like any built-in tool.

Name convention: mcp_{server_name}_{tool_name}
Category: "mcp"
"""

import logging
from typing import Any, Dict, List, Optional

from slack_bot.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MCPToolAdapter(BaseTool):
    """Adapts a single MCP tool (from tools/list) to the BaseTool interface.

    The adapter holds a reference to the MCPClient that owns it, so
    execute() can call client.call_tool() directly.

    Attributes:
        name: "mcp_{server_name}_{tool_name}"
        display_name: Human-readable name from MCP schema
        description: Tool description from MCP schema
        category: Always "mcp"
        server_name: Name of the MCP server this tool belongs to
        mcp_tool_name: Original tool name from the MCP server
        _input_schema: JSON Schema from MCP server's inputSchema
        _client: Reference to MCPClient (set by MCPManager)
    """

    def __init__(
        self,
        server_name: str,
        mcp_tool_name: str,
        description: str,
        input_schema: Dict[str, Any],
        client: Any,  # MCPClient — avoid circular import
    ):
        """Initialize MCP tool adapter.

        Args:
            server_name: MCP server name (from config)
            mcp_tool_name: Tool name as reported by MCP server
            description: Tool description from MCP server
            input_schema: JSON Schema for tool parameters
            client: MCPClient instance for executing calls
        """
        self.name = f"mcp_{server_name}_{mcp_tool_name}"
        self.display_name = f"[{server_name}] {mcp_tool_name}"
        self.description = description or f"MCP tool: {mcp_tool_name}"
        self.category = "mcp"
        self.server_name = server_name
        self.mcp_tool_name = mcp_tool_name
        self._input_schema = input_schema or {"type": "object", "properties": {}}
        self._client = client

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the MCP server's inputSchema for this tool."""
        return self._input_schema

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the MCP tool via the client.

        Calls client.call_tool() with the tool name and arguments,
        then converts MCP content blocks to a ToolResult.

        Args:
            **kwargs: Tool arguments matching parameters_schema

        Returns:
            ToolResult with content from MCP server
        """
        try:
            content_blocks = await self._client.call_tool(
                self.mcp_tool_name, kwargs
            )

            # Convert content blocks to text
            text_parts = []
            for block in content_blocks:
                block_type = block.get("type", "text")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "image":
                    text_parts.append(f"[Image: {block.get('mimeType', 'image')}]")
                elif block_type == "resource":
                    resource = block.get("resource", {})
                    text_parts.append(
                        f"[Resource: {resource.get('uri', 'unknown')}]\n"
                        f"{resource.get('text', '')}"
                    )
                else:
                    text_parts.append(f"[{block_type}: {block}]")

            content = "\n".join(text_parts)

            return ToolResult(
                tool_name=self.name,
                success=True,
                content=content,
                raw=content_blocks,
            )

        except Exception as e:
            logger.error(f"MCP tool '{self.name}' execution failed: {e}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if the MCP client is still connected."""
        return self._client is not None and self._client.connected
