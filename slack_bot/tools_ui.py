"""
Slack Block Kit UI builder for /tools management.

Provides helper functions to build the tool management modal,
following the model_selector.py pattern.
"""

import logging
from typing import Dict, List, Optional

from slack_bot.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def build_tools_ui(registry: ToolRegistry, user_id: str) -> List[Dict]:
    """Build Block Kit blocks for the /tools management modal.

    Shows all registered tools with enable/disable toggles,
    grouped by category (builtin, MCP).

    Args:
        registry: ToolRegistry instance
        user_id: Slack user ID (for per-user enable/disable state)

    Returns:
        List of Block Kit block dicts
    """
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "🔧 Tool Management"},
    })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "Enable or disable tools for your conversations. "
                    "Disabled tools won't be used when generating responses.",
        },
    })

    blocks.append({"type": "divider"})

    # Built-in tools
    builtin_tools = registry.list_tools(category="builtin")
    if builtin_tools:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Built-in Tools*"},
        })

        for tool in builtin_tools:
            enabled = registry.is_enabled(user_id, tool.name)
            status_emoji = "✅" if enabled else "⬜"
            toggle_text = "Disable" if enabled else "Enable"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{status_emoji} *{tool.display_name}*\n{tool.description[:100]}",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": toggle_text},
                    "action_id": f"tool_toggle_{tool.name}",
                    "value": f"{tool.name}:{'disable' if enabled else 'enable'}",
                },
            })

    # MCP tools
    mcp_tools = registry.list_tools(category="mcp")
    if mcp_tools:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*MCP Server Tools*"},
        })

        for tool in mcp_tools:
            enabled = registry.is_enabled(user_id, tool.name)
            status_emoji = "✅" if enabled else "⬜"
            toggle_text = "Disable" if enabled else "Enable"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{status_emoji} *{tool.display_name}*\n{tool.description[:100]}",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": toggle_text},
                    "action_id": f"tool_toggle_{tool.name}",
                    "value": f"{tool.name}:{'disable' if enabled else 'enable'}",
                },
            })

    if not builtin_tools and not mcp_tools:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⚠️ No tools registered. This shouldn't happen — check bot startup logs.",
            },
        })

    return blocks


def parse_tool_toggle_action(action_value: str) -> tuple:
    """Parse a tool toggle action value.

    Args:
        action_value: "tool_name:enable" or "tool_name:disable"

    Returns:
        Tuple of (tool_name, should_enable)
    """
    parts = action_value.split(":", 1)
    if len(parts) != 2:
        return ("", False)
    tool_name = parts[0]
    should_enable = parts[1] == "enable"
    return (tool_name, should_enable)
