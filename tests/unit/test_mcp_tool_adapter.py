"""
Unit tests for MCP Tool Adapter — wraps MCP tools as BaseTool.
"""

import pytest

from slack_bot.tools.base_tool import ToolResult
from slack_bot.tools.mcp.mcp_tool_adapter import MCPToolAdapter


class MockMCPClient:
    """Mock MCPClient for testing adapter."""

    def __init__(self, connected: bool = True, results=None, error=None):
        self._connected = connected
        self._results = results  # List of content blocks to return
        self._error = error  # Exception to raise
        self.calls = []  # Record calls for assertion

    @property
    def connected(self):
        return self._connected

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if self._error:
            raise self._error
        return self._results or []


@pytest.mark.unit
class TestMCPToolAdapterInit:
    """Test adapter initialization."""

    def test_name_convention(self):
        """Name follows mcp_{server}_{tool} convention."""
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="create_issue",
            description="Create an issue",
            input_schema={"type": "object", "properties": {}},
            client=MockMCPClient(),
        )
        assert adapter.name == "mcp_github_create_issue"
        assert adapter.category == "mcp"

    def test_display_name(self):
        """Display name includes server name."""
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="create_issue",
            description="Create an issue",
            input_schema={},
            client=MockMCPClient(),
        )
        assert "[github]" in adapter.display_name.lower()

    def test_description_fallback(self):
        """Empty description gets a default."""
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="create_issue",
            description="",
            input_schema={},
            client=MockMCPClient(),
        )
        assert "create_issue" in adapter.description

    def test_parameters_schema(self):
        """Parameters schema returns the MCP inputSchema."""
        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        }
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="create_issue",
            description="Create an issue",
            input_schema=schema,
            client=MockMCPClient(),
        )
        assert adapter.parameters_schema == schema

    def test_to_function_spec(self):
        """to_function_spec produces valid OpenAI format."""
        schema = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="search",
            description="Search repos",
            input_schema=schema,
            client=MockMCPClient(),
        )
        spec = adapter.to_function_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "mcp_github_search"
        assert spec["function"]["parameters"] == schema


@pytest.mark.unit
class TestMCPToolAdapterExecute:
    """Test tool execution through the adapter."""

    @pytest.mark.asyncio
    async def test_execute_text_content(self):
        """Execute returns text content from MCP response."""
        client = MockMCPClient(results=[
            {"type": "text", "text": "Issue #42 created"},
        ])
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="create_issue",
            description="Create",
            input_schema={},
            client=client,
        )

        result = await adapter.execute(title="Test")

        assert result.success
        assert "Issue #42" in result.content
        assert result.tool_name == "mcp_github_create_issue"
        # Verify call was forwarded to client
        assert client.calls == [("create_issue", {"title": "Test"})]

    @pytest.mark.asyncio
    async def test_execute_multiple_text_blocks(self):
        """Multiple text blocks are joined."""
        client = MockMCPClient(results=[
            {"type": "text", "text": "Line 1"},
            {"type": "text", "text": "Line 2"},
        ])
        adapter = MCPToolAdapter(
            server_name="fs",
            mcp_tool_name="read_file",
            description="Read",
            input_schema={},
            client=client,
        )

        result = await adapter.execute(path="/tmp/test")
        assert "Line 1" in result.content
        assert "Line 2" in result.content

    @pytest.mark.asyncio
    async def test_execute_image_content(self):
        """Image content blocks get placeholder text."""
        client = MockMCPClient(results=[
            {"type": "image", "mimeType": "image/png", "data": "base64..."},
        ])
        adapter = MCPToolAdapter(
            server_name="fs",
            mcp_tool_name="screenshot",
            description="Screenshot",
            input_schema={},
            client=client,
        )

        result = await adapter.execute()
        assert result.success
        assert "Image" in result.content

    @pytest.mark.asyncio
    async def test_execute_resource_content(self):
        """Resource content blocks include URI."""
        client = MockMCPClient(results=[
            {"type": "resource", "resource": {"uri": "file:///test.md", "text": "# Hello"}},
        ])
        adapter = MCPToolAdapter(
            server_name="fs",
            mcp_tool_name="read",
            description="Read",
            input_schema={},
            client=client,
        )

        result = await adapter.execute()
        assert result.success
        assert "file:///test.md" in result.content
        assert "# Hello" in result.content

    @pytest.mark.asyncio
    async def test_execute_error(self):
        """Client exception produces failed ToolResult."""
        client = MockMCPClient(error=Exception("Connection lost"))
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="create_issue",
            description="Create",
            input_schema={},
            client=client,
        )

        result = await adapter.execute(title="Test")

        assert not result.success
        assert "Connection lost" in result.error

    @pytest.mark.asyncio
    async def test_execute_empty_response(self):
        """Empty response produces success with empty content."""
        client = MockMCPClient(results=[])
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="delete_issue",
            description="Delete",
            input_schema={},
            client=client,
        )

        result = await adapter.execute(issue_id=42)
        assert result.success
        assert result.content == ""


@pytest.mark.unit
class TestMCPToolAdapterHealthCheck:
    """Test health check."""

    @pytest.mark.asyncio
    async def test_health_check_connected(self):
        """Health check returns True when client connected."""
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="test",
            description="Test",
            input_schema={},
            client=MockMCPClient(connected=True),
        )
        assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self):
        """Health check returns False when client disconnected."""
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="test",
            description="Test",
            input_schema={},
            client=MockMCPClient(connected=False),
        )
        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_no_client(self):
        """Health check returns False when client is None."""
        adapter = MCPToolAdapter(
            server_name="github",
            mcp_tool_name="test",
            description="Test",
            input_schema={},
            client=None,
        )
        assert await adapter.health_check() is False
