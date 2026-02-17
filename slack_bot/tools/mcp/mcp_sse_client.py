"""
MCP SSE Client — JSON-RPC over HTTP/SSE transport for remote MCP servers.

Communicates with remote MCP servers via:
- HTTP POST for sending JSON-RPC requests
- Server-Sent Events (SSE) for receiving responses

This is the Phase 6 transport complement to the stdio MCPClient.
Both share the same protocol (initialize → tools/list → tools/call)
but differ in transport layer.

Usage:
    client = MCPSSEClient(
        url="http://nuc-1.local:8080/mcp",
        headers={"Authorization": "Bearer token"}
    )
    await client.connect()
    tools = await client.list_tools()
    result = await client.call_tool("search", {"query": "test"})
    await client.disconnect()
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from slack_bot.tools.mcp.mcp_client import (
    MCPClientError,
    MCPConnectionError,
    MCPToolCallError,
    MCP_PROTOCOL_VERSION,
    CLIENT_NAME,
    CLIENT_VERSION,
    CONNECT_TIMEOUT,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class MCPSSEClient:
    """JSON-RPC client for MCP servers over HTTP/SSE transport.

    Sends requests via HTTP POST and receives responses.
    The MCP SSE spec uses:
    - GET /sse — SSE stream for server→client messages (endpoint discovery)
    - POST <endpoint> — client→server JSON-RPC requests

    For simplicity in Phase 6, we use a direct HTTP POST approach
    where the server endpoint is known (configured URL).

    Attributes:
        url: Base URL of the MCP server
        headers: HTTP headers (e.g., Authorization)
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize SSE client.

        Args:
            url: MCP server URL (e.g., "http://nuc-1.local:8080/mcp")
            headers: HTTP headers for authentication etc.
        """
        self.url = url.rstrip("/")
        self.headers = headers or {}

        self._session: Optional[aiohttp.ClientSession] = None
        self._request_id: int = 0
        self._connected: bool = False
        self._server_capabilities: Dict[str, Any] = {}
        self._server_info: Dict[str, Any] = {}
        self._message_endpoint: Optional[str] = None

    @property
    def connected(self) -> bool:
        """Whether the client has an active connection."""
        return self._connected and self._session is not None and not self._session.closed

    async def connect(self) -> None:
        """Connect to the MCP server and initialize the protocol.

        Opens an HTTP session, discovers the message endpoint via SSE,
        then sends the initialize handshake.

        Raises:
            MCPConnectionError: If the server is unreachable or init fails
        """
        if self.connected:
            logger.warning("MCP SSE client already connected")
            return

        try:
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=CONNECT_TIMEOUT),
            )

            # Discover the message endpoint via SSE
            await self._discover_endpoint()

            # Send initialize request
            init_result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": CLIENT_NAME,
                        "version": CLIENT_VERSION,
                    },
                },
                timeout=CONNECT_TIMEOUT,
            )

            self._server_capabilities = init_result.get("capabilities", {})
            self._server_info = init_result.get("serverInfo", {})

            # Send initialized notification
            await self._send_notification("notifications/initialized")

            self._connected = True
            logger.info(
                f"MCP SSE server initialized: {self._server_info.get('name', 'unknown')} "
                f"v{self._server_info.get('version', '?')} at {self.url}"
            )

        except asyncio.TimeoutError:
            await self._cleanup()
            raise MCPConnectionError(
                f"Timeout connecting to MCP SSE server: {self.url}"
            )
        except MCPConnectionError:
            await self._cleanup()
            raise
        except Exception as e:
            await self._cleanup()
            raise MCPConnectionError(
                f"Failed to connect to MCP SSE server {self.url}: {e}"
            )

    async def disconnect(self) -> None:
        """Close the HTTP session."""
        self._connected = False
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._message_endpoint = None
        logger.info(f"MCP SSE server disconnected: {self.url}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server.

        Returns:
            List of tool definitions

        Raises:
            MCPConnectionError: If not connected
        """
        self._ensure_connected()
        result = await self._send_request("tools/list", {})
        tools = result.get("tools", [])
        logger.info(f"MCP SSE server offers {len(tools)} tools")
        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Call an MCP tool.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            List of content blocks

        Raises:
            MCPToolCallError: If the call fails
        """
        self._ensure_connected()

        try:
            result = await self._send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            )

            content = result.get("content", [])
            is_error = result.get("isError", False)

            if is_error:
                error_text = self._extract_text_content(content)
                raise MCPToolCallError(
                    f"MCP SSE tool '{tool_name}' returned error: {error_text}"
                )

            return content

        except MCPToolCallError:
            raise
        except Exception as e:
            raise MCPToolCallError(
                f"Failed to call MCP SSE tool '{tool_name}': {e}"
            )

    # ---- Internal methods ----

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if not self.connected:
            raise MCPConnectionError("MCP SSE client not connected")

    async def _discover_endpoint(self) -> None:
        """Discover the message endpoint via SSE.

        The MCP SSE spec says: GET /sse returns an SSE stream.
        The first event should be an 'endpoint' event with the
        POST URL for sending messages.

        Falls back to using {url}/message if SSE discovery fails.
        """
        sse_url = f"{self.url}/sse"

        try:
            async with self._session.get(sse_url) as resp:
                if resp.status != 200:
                    # SSE endpoint not available, fall back to direct POST
                    self._message_endpoint = f"{self.url}/message"
                    logger.debug(
                        f"SSE endpoint returned {resp.status}, "
                        f"falling back to {self._message_endpoint}"
                    )
                    return

                # Read SSE events until we get 'endpoint'
                async for line in resp.content:
                    decoded = line.decode("utf-8").strip()
                    if decoded.startswith("event: endpoint"):
                        # Next line should be the data
                        data_line = await resp.content.readline()
                        data_decoded = data_line.decode("utf-8").strip()
                        if data_decoded.startswith("data: "):
                            endpoint = data_decoded[6:].strip()
                            # Endpoint may be relative or absolute
                            if endpoint.startswith("http"):
                                self._message_endpoint = endpoint
                            else:
                                self._message_endpoint = f"{self.url}{endpoint}"
                            logger.debug(f"MCP SSE endpoint: {self._message_endpoint}")
                            return
                    elif decoded.startswith("data: "):
                        # Some servers send endpoint in data directly
                        data = decoded[6:].strip()
                        if data.startswith("/") or data.startswith("http"):
                            if data.startswith("http"):
                                self._message_endpoint = data
                            else:
                                self._message_endpoint = f"{self.url}{data}"
                            logger.debug(f"MCP SSE endpoint from data: {self._message_endpoint}")
                            return

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"SSE discovery failed: {e}")

        # Fall back
        self._message_endpoint = f"{self.url}/message"
        logger.debug(f"Using fallback endpoint: {self._message_endpoint}")

    async def _send_request(
        self,
        method: str,
        params: Dict[str, Any],
        timeout: float = REQUEST_TIMEOUT,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request via HTTP POST.

        Args:
            method: RPC method name
            params: Method parameters
            timeout: Request timeout

        Returns:
            Result dict from the response
        """
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        endpoint = self._message_endpoint or f"{self.url}/message"

        try:
            async with self._session.post(
                endpoint,
                json=request,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise MCPClientError(
                        f"MCP SSE HTTP {resp.status}: {body[:200]}"
                    )

                response = await resp.json()

                if "error" in response:
                    error = response["error"]
                    code = error.get("code", -1)
                    message = error.get("message", "Unknown error")
                    raise MCPClientError(f"JSON-RPC error {code}: {message}")

                return response.get("result", {})

        except (MCPClientError, MCPToolCallError):
            raise
        except asyncio.TimeoutError:
            raise MCPClientError(f"Timeout on {method}")
        except aiohttp.ClientError as e:
            raise MCPConnectionError(f"HTTP error on {method}: {e}")

    async def _send_notification(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            notification["params"] = params

        endpoint = self._message_endpoint or f"{self.url}/message"

        try:
            async with self._session.post(endpoint, json=notification) as resp:
                if resp.status != 200 and resp.status != 202:
                    logger.warning(
                        f"MCP SSE notification {method} returned {resp.status}"
                    )
        except Exception as e:
            logger.warning(f"MCP SSE notification {method} failed: {e}")

    async def _cleanup(self) -> None:
        """Clean up session on error."""
        self._connected = False
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._message_endpoint = None

    @staticmethod
    def _extract_text_content(content: List[Dict[str, Any]]) -> str:
        """Extract text from MCP content blocks."""
        texts = []
        for block in content:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts) if texts else str(content)
