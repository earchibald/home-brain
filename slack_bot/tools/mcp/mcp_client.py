"""
MCP Client — JSON-RPC over stdio transport for MCP servers.

Manages a subprocess running an MCP server, communicates via
stdin/stdout using the MCP JSON-RPC protocol.

Protocol flow:
  → initialize(protocolVersion, capabilities, clientInfo)
  ← result
  → notifications/initialized
  → tools/list
  ← {tools: [{name, description, inputSchema}]}
  → tools/call(name, arguments)
  ← {content: [{type: "text", text: "..."}]}

Lifecycle: connect() → list_tools() → call_tool() → disconnect()
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# MCP protocol version we support
MCP_PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "brain-assistant"
CLIENT_VERSION = "1.0.0"

# Timeouts
CONNECT_TIMEOUT = 30.0
REQUEST_TIMEOUT = 30.0


class MCPClientError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPConnectionError(MCPClientError):
    """Failed to connect to or communicate with MCP server."""
    pass


class MCPToolCallError(MCPClientError):
    """Error executing an MCP tool call."""
    pass


class MCPClient:
    """JSON-RPC client for MCP servers over stdio transport.

    Spawns a subprocess, sends JSON-RPC requests via stdin,
    reads JSON-RPC responses from stdout.

    Usage:
        client = MCPClient(command="npx", args=["-y", "@modelcontextprotocol/server-github"])
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("list_repos", {"owner": "user"})
        await client.disconnect()
    """

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """Initialize MCP client.

        Args:
            command: Executable to run (e.g., "npx", "python")
            args: Command-line arguments
            env: Additional environment variables for the subprocess
        """
        self.command = command
        self.args = args or []
        self.env = env or {}

        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._connected: bool = False
        self._server_capabilities: Dict[str, Any] = {}
        self._server_info: Dict[str, Any] = {}
        self._read_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Whether the client is connected to a running server."""
        return self._connected and self._process is not None and self._process.returncode is None

    async def connect(self) -> None:
        """Start the MCP server subprocess and initialize the protocol.

        Raises:
            MCPConnectionError: If the server fails to start or initialize
        """
        if self.connected:
            logger.warning("MCP client already connected")
            return

        try:
            # Build environment: inherit current env + add overrides
            process_env = {**os.environ, **self.env}

            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
            )

            logger.info(
                f"MCP server started: {self.command} {' '.join(self.args)} "
                f"(pid={self._process.pid})"
            )

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

            # Send initialized notification (no response expected)
            await self._send_notification("notifications/initialized")

            self._connected = True
            logger.info(
                f"MCP server initialized: {self._server_info.get('name', 'unknown')} "
                f"v{self._server_info.get('version', '?')}"
            )

        except asyncio.TimeoutError:
            await self._cleanup()
            raise MCPConnectionError(
                f"Timeout connecting to MCP server: {self.command}"
            )
        except Exception as e:
            await self._cleanup()
            raise MCPConnectionError(
                f"Failed to connect to MCP server: {e}"
            )

    async def disconnect(self) -> None:
        """Gracefully shut down the MCP server subprocess."""
        if not self._process:
            return

        try:
            # Close stdin to signal EOF
            if self._process.stdin and not self._process.stdin.is_closing():
                self._process.stdin.close()
                await self._process.stdin.wait_closed()

            # Wait briefly for graceful exit
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("MCP server did not exit gracefully, terminating")
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning("MCP server did not terminate, killing")
                    self._process.kill()
                    await self._process.wait()

        except ProcessLookupError:
            pass  # Already exited

        self._connected = False
        self._process = None
        logger.info(f"MCP server disconnected: {self.command}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server.

        Returns:
            List of tool definitions, each with name, description, inputSchema

        Raises:
            MCPConnectionError: If not connected
            MCPClientError: If the request fails
        """
        self._ensure_connected()

        result = await self._send_request("tools/list", {})
        tools = result.get("tools", [])

        logger.info(f"MCP server offers {len(tools)} tools")
        for tool in tools:
            logger.debug(f"  MCP tool: {tool.get('name', '?')}")

        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            List of content blocks, each with {type, text} or other fields

        Raises:
            MCPConnectionError: If not connected
            MCPToolCallError: If the tool call fails
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
                    f"MCP tool '{tool_name}' returned error: {error_text}"
                )

            return content

        except MCPToolCallError:
            raise
        except Exception as e:
            raise MCPToolCallError(
                f"Failed to call MCP tool '{tool_name}': {e}"
            )

    # ---- Internal methods ----

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if not self.connected:
            raise MCPConnectionError("MCP client not connected")

    async def _send_request(
        self,
        method: str,
        params: Dict[str, Any],
        timeout: float = REQUEST_TIMEOUT,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response.

        Args:
            method: RPC method name
            params: Method parameters
            timeout: Response timeout in seconds

        Returns:
            Result dict from the response

        Raises:
            MCPClientError: On protocol errors
            asyncio.TimeoutError: On timeout
        """
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        await self._write_message(request)

        response = await asyncio.wait_for(
            self._read_response(self._request_id),
            timeout=timeout,
        )

        if "error" in response:
            error = response["error"]
            code = error.get("code", -1)
            message = error.get("message", "Unknown error")
            raise MCPClientError(f"JSON-RPC error {code}: {message}")

        return response.get("result", {})

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: Notification method name
            params: Optional parameters
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            notification["params"] = params

        await self._write_message(notification)

    async def _write_message(self, message: Dict[str, Any]) -> None:
        """Write a JSON-RPC message to the server's stdin.

        Args:
            message: JSON-RPC message dict
        """
        if not self._process or not self._process.stdin:
            raise MCPConnectionError("No process stdin available")

        data = json.dumps(message)
        line = data + "\n"

        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

        logger.debug(f"MCP → {message.get('method', '?')} (id={message.get('id', 'N/A')})")

    async def _read_response(self, request_id: int) -> Dict[str, Any]:
        """Read a JSON-RPC response matching the given request ID.

        Skips over notifications and responses for other request IDs.
        Uses a lock to prevent interleaved reads.

        Args:
            request_id: Expected response ID

        Returns:
            JSON-RPC response dict
        """
        async with self._read_lock:
            while True:
                line = await self._read_line()
                if not line:
                    raise MCPConnectionError("MCP server closed stdout")

                try:
                    message = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(f"MCP: Invalid JSON from server: {e}")
                    continue

                # Skip notifications (no id field)
                if "id" not in message:
                    logger.debug(f"MCP notification: {message.get('method', '?')}")
                    continue

                # Check if this is our response
                if message.get("id") == request_id:
                    logger.debug(
                        f"MCP ← response for id={request_id}: "
                        f"{'error' if 'error' in message else 'result'}"
                    )
                    return message

                # Response for different request ID — shouldn't happen in
                # serial request mode but log and skip
                logger.warning(
                    f"MCP: Got response for id={message.get('id')}, "
                    f"expected {request_id}"
                )

    async def _read_line(self) -> Optional[str]:
        """Read a single line from the server's stdout.

        Returns:
            Decoded line string, or None if EOF
        """
        if not self._process or not self._process.stdout:
            return None

        try:
            line = await self._process.stdout.readline()
            if not line:
                return None
            return line.decode("utf-8").strip()
        except Exception as e:
            logger.error(f"MCP read error: {e}")
            return None

    async def _cleanup(self) -> None:
        """Clean up subprocess on error."""
        if self._process:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
        self._process = None
        self._connected = False

    @staticmethod
    def _extract_text_content(content: List[Dict[str, Any]]) -> str:
        """Extract text from MCP content blocks.

        Args:
            content: List of content blocks

        Returns:
            Concatenated text content
        """
        texts = []
        for block in content:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts) if texts else str(content)
