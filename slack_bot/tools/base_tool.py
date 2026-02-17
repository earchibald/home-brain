"""
Base tool interfaces for Brain Assistant's unified tool architecture.

Provides:
- ToolResult: Structured result from tool execution
- BaseTool: Abstract base for all tools (built-in, MCP, skills)
- UserScopedTool: Base for tools that need per-user context (e.g., FACTS)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Structured result from a tool execution.

    Attributes:
        tool_name: Name of the tool that produced this result
        success: Whether the tool executed successfully
        content: Human/LLM-readable result text (for context injection)
        raw: Raw result data (for programmatic use)
        error: Error description if success=False
        executed_at: ISO timestamp of execution
    """

    tool_name: str
    success: bool
    content: str = ""
    raw: Any = None
    error: Optional[str] = None
    executed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_context_string(self) -> str:
        """Format result as a context string for LLM prompt injection."""
        if not self.success:
            return f"[Tool: {self.tool_name}] ERROR: {self.error}"
        return f"[Tool: {self.tool_name}]\n{self.content}"


class BaseTool(ABC):
    """Abstract base class for all Brain Assistant tools.

    Every tool (built-in, MCP adapter, skill) must implement this interface.
    The ToolRegistry discovers and manages tools through this contract.

    Attributes:
        name: Unique slug identifier (e.g., "web_search", "mcp_github_list_repos")
        display_name: Human-readable name for Slack UI
        description: LLM-facing description (used in tool specs and shim prompts)
        category: Tool category ("builtin", "mcp", "skill")
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    category: str = "builtin"

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for tool parameters (OpenAI function-calling compatible).

        Example:
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given parameters.

        Args:
            **kwargs: Parameters matching parameters_schema

        Returns:
            ToolResult with success/failure and content
        """
        ...

    async def health_check(self) -> bool:
        """Check if the tool is available and functional.

        Returns:
            True if the tool can execute, False otherwise
        """
        return True

    def to_function_spec(self) -> Dict[str, Any]:
        """Convert to OpenAI function-calling format.

        Used by Gemini and other providers with native function-calling support.

        Returns:
            Dict in OpenAI function spec format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    def to_prompt_description(self) -> str:
        """Convert to plaintext description for shim mode (Ollama).

        Returns:
            Multi-line description of the tool and its parameters
        """
        schema = self.parameters_schema
        params_desc = []
        props = schema.get("properties", {})
        required = set(schema.get("required", []))

        for param_name, param_info in props.items():
            req_marker = " (required)" if param_name in required else " (optional)"
            param_type = param_info.get("type", "string")
            param_desc = param_info.get("description", "")
            enum_vals = param_info.get("enum")
            enum_str = f" [one of: {', '.join(enum_vals)}]" if enum_vals else ""
            params_desc.append(
                f"  - {param_name} ({param_type}{req_marker}): {param_desc}{enum_str}"
            )

        params_block = "\n".join(params_desc) if params_desc else "  (no parameters)"
        return f"- **{self.name}**: {self.description}\n  Parameters:\n{params_block}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} category={self.category!r}>"


class UserScopedTool(BaseTool, ABC):
    """Base class for tools that operate per-user.

    The ToolExecutor sets _user_id before each execute() call.
    This avoids passing user_id as a hidden kwarg — the contract is explicit.

    Example:
        class FactsTool(UserScopedTool):
            async def execute(self, **kwargs) -> ToolResult:
                store = FactsStore(self._user_id)
                ...
    """

    _user_id: str = ""
