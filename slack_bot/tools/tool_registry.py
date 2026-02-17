"""
Tool Registry — single source of truth for all registered tools.

Mirrors the ModelManager pattern from services/model_manager.py.
Replaces "Provider" with "Tool" — same structure, same simplicity.
"""

import logging
from typing import Dict, List, Optional

from slack_bot.tools.base_tool import BaseTool, UserScopedTool
from slack_bot.tools.tool_state import ToolStateStore

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of all available tools (built-in, MCP, skills).

    Manages tool registration, discovery, and per-user enable/disable state.
    The ToolExecutor queries this registry to determine which tools are available
    for a given user and provider combination.
    """

    def __init__(self, state_store: Optional[ToolStateStore] = None):
        """Initialize the registry.

        Args:
            state_store: Optional ToolStateStore for per-user enable/disable.
                         Creates a default one if not provided.
        """
        self.tools: Dict[str, BaseTool] = {}
        self._state_store = state_store or ToolStateStore()

    def register(self, tool: BaseTool):
        """Register a tool. Overwrites on name collision (for MCP reconnects).

        Args:
            tool: Tool instance implementing BaseTool
        """
        if tool.name in self.tools:
            logger.warning(f"Overwriting existing tool: {tool.name}")
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} (category={tool.category})")

    def unregister(self, tool_name: str) -> bool:
        """Unregister a tool (e.g., when MCP server disconnects).

        Args:
            tool_name: Name of the tool to remove

        Returns:
            True if the tool was found and removed
        """
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.info(f"Unregistered tool: {tool_name}")
            return True
        return False

    def get(self, tool_name: str) -> Optional[BaseTool]:
        """Get a tool by name.

        Args:
            tool_name: Tool name slug

        Returns:
            BaseTool instance or None if not found
        """
        return self.tools.get(tool_name)

    def list_tools(
        self,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[BaseTool]:
        """List tools with optional filtering.

        Args:
            user_id: If provided with enabled_only, filter by user enable state
            category: Filter by category ("builtin", "mcp", "skill")
            enabled_only: Only return tools enabled for the given user

        Returns:
            List of matching BaseTool instances
        """
        result = list(self.tools.values())

        if category:
            result = [t for t in result if t.category == category]

        if enabled_only and user_id:
            result = [t for t in result if self.is_enabled(user_id, t.name)]

        return result

    def is_enabled(self, user_id: str, tool_name: str) -> bool:
        """Check if a tool is enabled for a user.

        Args:
            user_id: Slack user ID
            tool_name: Tool name slug

        Returns:
            True if enabled (default: True for all tools)
        """
        return self._state_store.is_enabled(user_id, tool_name)

    def set_enabled(self, user_id: str, tool_name: str, enabled: bool):
        """Set enable/disable state for a tool per user.

        Args:
            user_id: Slack user ID
            tool_name: Tool name slug
            enabled: True to enable, False to disable
        """
        self._state_store.set_enabled(user_id, tool_name, enabled)

    def get_enabled_tools_for_llm(self, user_id: str) -> List[BaseTool]:
        """Get all enabled tools for LLM function-calling or shim injection.

        Filters out disabled tools and skills (which are managed separately).

        Args:
            user_id: Slack user ID

        Returns:
            List of enabled BaseTool instances (excluding skills)
        """
        return [
            tool
            for tool in self.tools.values()
            if tool.category != "skill"
            and self._state_store.is_enabled(user_id, tool.name)
        ]

    def get_function_specs(self, user_id: str) -> List[dict]:
        """Get OpenAI function-calling specs for all enabled tools.

        Used by Gemini and other providers with native function-calling.

        Args:
            user_id: Slack user ID

        Returns:
            List of function spec dicts
        """
        return [tool.to_function_spec() for tool in self.get_enabled_tools_for_llm(user_id)]

    def get_prompt_descriptions(self, user_id: str) -> str:
        """Get plaintext tool descriptions for shim mode (Ollama).

        Args:
            user_id: Slack user ID

        Returns:
            Multi-line tool description string
        """
        tools = self.get_enabled_tools_for_llm(user_id)
        if not tools:
            return ""
        return "\n\n".join(tool.to_prompt_description() for tool in tools)
