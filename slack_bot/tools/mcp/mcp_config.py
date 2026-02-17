"""
MCP Server configuration — load, save, and merge config files.

Base config: config/mcp_servers.json (git-tracked)
Local override: config/mcp_servers.local.json (gitignored, machine-specific)

Secret resolution: "vaultwarden:SECRET_NAME" values are resolved
at MCPManager startup via VaultwardenClient.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    transport: str = "stdio"  # "stdio" or "sse"
    command: str = ""  # For stdio transport
    args: List[str] = field(default_factory=list)  # For stdio transport
    env: Dict[str, str] = field(default_factory=dict)
    url: str = ""  # For SSE transport
    headers: Dict[str, str] = field(default_factory=dict)  # For SSE transport
    enabled: bool = False
    description: str = ""


def load_mcp_config(
    base_path: str = "config/mcp_servers.json",
    local_path: Optional[str] = None,
) -> Dict[str, MCPServerConfig]:
    """Load MCP server configurations with local override merge.

    Args:
        base_path: Path to git-tracked base config
        local_path: Path to local override config (default: base_path but .local.json)

    Returns:
        Dict of server name → MCPServerConfig
    """
    if local_path is None:
        local_path = base_path.replace(".json", ".local.json")

    # Load base config
    base_data = {}
    if os.path.exists(base_path):
        try:
            with open(base_path, "r") as f:
                raw = json.load(f)
            base_data = raw.get("mcpServers", {})
        except Exception as e:
            logger.warning(f"Failed to load MCP base config: {e}")

    # Load local override
    local_data = {}
    if os.path.exists(local_path):
        try:
            with open(local_path, "r") as f:
                raw = json.load(f)
            local_data = raw.get("mcpServers", {})
        except Exception as e:
            logger.warning(f"Failed to load MCP local config: {e}")

    # Merge: local overrides base
    merged = {**base_data, **local_data}

    # Parse into dataclasses
    configs = {}
    for name, server_data in merged.items():
        configs[name] = MCPServerConfig(
            name=name,
            transport=server_data.get("transport", "stdio"),
            command=server_data.get("command", ""),
            args=server_data.get("args", []),
            env=server_data.get("env", {}),
            url=server_data.get("url", ""),
            headers=server_data.get("headers", {}),
            enabled=server_data.get("enabled", False),
            description=server_data.get("description", ""),
        )

    return configs


def has_vaultwarden_refs(config: MCPServerConfig) -> bool:
    """Check if a server config has vaultwarden: secret references.

    Args:
        config: MCP server configuration

    Returns:
        True if any env or header value starts with "vaultwarden:"
    """
    for value in config.env.values():
        if isinstance(value, str) and value.startswith("vaultwarden:"):
            return True
    for value in config.headers.values():
        if isinstance(value, str) and value.startswith("vaultwarden:"):
            return True
    return False
