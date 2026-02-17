"""
Tool Executor — parses tool calls, executes tools, manages the tool loop.

Supports two modes:
- **Shim mode** (Ollama): Injects tool descriptions into system prompt,
  parses <tool_call> XML from LLM output, executes tools, re-prompts.
- **Native mode** (Gemini): Uses provider's function-calling API directly.

Safety: MAX_TOOL_ROUNDS=5 limit, 15s timeout per tool execution.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from slack_bot.tools.base_tool import BaseTool, ToolResult, UserScopedTool
from slack_bot.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
TOOL_TIMEOUT_SECONDS = 15.0


@dataclass
class ToolCall:
    """Parsed tool call from LLM output."""

    tool_name: str
    arguments: Dict[str, Any]
    raw_text: str = ""  # Original XML block for stripping from response


# ---- Shim prompt template ----
SHIM_SYSTEM_TEMPLATE = """To use a tool, output EXACTLY this format (one tool per response):
<tool_call>
{{"tool": "tool_name", "arguments": {{"key": "value"}}}}
</tool_call>
Only call one tool per response. If no tool is needed, respond normally.

Available tools:
{tool_descriptions}"""


def build_shim_system_prompt(registry: ToolRegistry, user_id: str) -> str:
    """Build the shim system prompt with available tool descriptions.

    Args:
        registry: ToolRegistry instance
        user_id: Slack user ID (for per-user enable/disable)

    Returns:
        System prompt string with tool descriptions, or empty string if no tools
    """
    descriptions = registry.get_prompt_descriptions(user_id)
    if not descriptions:
        return ""
    return SHIM_SYSTEM_TEMPLATE.format(tool_descriptions=descriptions)


def parse_shim_tool_call(text: str) -> Optional[ToolCall]:
    """Parse a <tool_call> XML block from LLM output.

    Handles:
    - Well-formed XML with JSON body
    - Whitespace variations
    - Missing closing tag (takes to end of string)
    - Malformed JSON (returns None)

    Args:
        text: LLM output text that may contain a tool call

    Returns:
        ToolCall if found and valid, None otherwise
    """
    # Match <tool_call>...</tool_call> with optional whitespace
    pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        # Try without closing tag (LLM sometimes forgets)
        pattern_open = r"<tool_call>\s*(.*)"
        match = re.search(pattern_open, text, re.DOTALL)
        if not match:
            return None

    json_str = match.group(1).strip()
    raw_text = match.group(0)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse tool call JSON: {json_str[:200]}")
        return None

    tool_name = data.get("tool") or data.get("name")
    arguments = data.get("arguments") or data.get("params") or {}

    if not tool_name:
        logger.warning(f"Tool call missing 'tool' field: {data}")
        return None

    if not isinstance(arguments, dict):
        logger.warning(f"Tool call arguments not a dict: {type(arguments)}")
        arguments = {}

    return ToolCall(
        tool_name=str(tool_name),
        arguments=arguments,
        raw_text=raw_text,
    )


async def execute_tool_call(
    registry: ToolRegistry,
    tool_call: ToolCall,
    user_id: str,
) -> ToolResult:
    """Execute a single tool call with timeout guard.

    Sets _user_id on UserScopedTool instances before execution.
    Wraps execution in asyncio.wait_for with TOOL_TIMEOUT_SECONDS timeout.

    Args:
        registry: ToolRegistry instance
        tool_call: Parsed ToolCall
        user_id: Slack user ID

    Returns:
        ToolResult (always — never raises)
    """
    tool = registry.get(tool_call.tool_name)

    if not tool:
        return ToolResult(
            tool_name=tool_call.tool_name,
            success=False,
            error=f"Unknown tool: {tool_call.tool_name}",
        )

    # Check if tool is enabled for this user
    if not registry.is_enabled(user_id, tool_call.tool_name):
        return ToolResult(
            tool_name=tool_call.tool_name,
            success=False,
            error=f"Tool '{tool_call.tool_name}' is disabled",
        )

    # Set user_id on user-scoped tools
    if isinstance(tool, UserScopedTool):
        tool._user_id = user_id

    try:
        result = await asyncio.wait_for(
            tool.execute(**tool_call.arguments),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        logger.info(
            f"Tool '{tool_call.tool_name}' executed: success={result.success}, "
            f"content_len={len(result.content)}"
        )
        return result

    except asyncio.TimeoutError:
        logger.error(f"Tool '{tool_call.tool_name}' timed out after {TOOL_TIMEOUT_SECONDS}s")
        return ToolResult(
            tool_name=tool_call.tool_name,
            success=False,
            error=f"Tool execution timed out after {TOOL_TIMEOUT_SECONDS}s",
        )

    except Exception as e:
        logger.error(f"Tool '{tool_call.tool_name}' execution error: {e}")
        return ToolResult(
            tool_name=tool_call.tool_name,
            success=False,
            error=str(e),
        )


class ToolExecutor:
    """Orchestrates tool execution loops for both shim and native modes.

    Usage:
        executor = ToolExecutor(registry)

        # Shim mode (Ollama) — check LLM output for tool calls
        tool_call = parse_shim_tool_call(llm_output)
        if tool_call:
            result = await execute_tool_call(registry, tool_call, user_id)

        # Full tool loop (Gemini) — run until no more tool calls or MAX_ROUNDS
        final_response = await executor.run_tool_loop(messages, user_id, generate_fn)
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def build_shim_prompt(self, user_id: str) -> str:
        """Build shim system prompt for Ollama."""
        return build_shim_system_prompt(self.registry, user_id)

    def build_native_specs(self, user_id: str) -> List[dict]:
        """Build native function specs for Gemini."""
        return self.registry.get_function_specs(user_id)

    async def run_tool_loop(
        self,
        messages: List,
        user_id: str,
        generate_fn,
        max_rounds: int = MAX_TOOL_ROUNDS,
    ) -> str:
        """Run the tool execution loop (Gemini mode).

        Calls the LLM, checks for tool calls in output, executes tools,
        injects results, and re-calls the LLM until no more tool calls
        or max_rounds is reached.

        Args:
            messages: Current message list (will be mutated with tool results)
            user_id: Slack user ID
            generate_fn: Async function(messages) -> str that calls the LLM
            max_rounds: Maximum tool call rounds (safety limit)

        Returns:
            Final LLM response text (with tool call XML stripped)
        """
        for round_num in range(max_rounds):
            response = await generate_fn(messages)

            tool_call = parse_shim_tool_call(response)
            if not tool_call:
                # No tool call — return clean response
                return response

            logger.info(
                f"Tool loop round {round_num + 1}/{max_rounds}: "
                f"calling {tool_call.tool_name}"
            )

            result = await execute_tool_call(self.registry, tool_call, user_id)

            # Strip tool call XML from LLM response for clean display
            clean_response = response.replace(tool_call.raw_text, "").strip()

            # Add assistant message (with tool call) and tool result to conversation
            if clean_response:
                messages.append({"role": "assistant", "content": clean_response})

            messages.append(
                {
                    "role": "system",
                    "content": f"[Tool result]\n{result.to_context_string()}",
                }
            )

        # Safety: max rounds reached
        logger.warning(f"Tool loop hit max rounds ({max_rounds}) for user {user_id}")
        final_response = await generate_fn(messages)
        return final_response
