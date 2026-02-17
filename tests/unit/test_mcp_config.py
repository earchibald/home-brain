"""
Unit tests for MCP configuration loading and merging.
"""

import json
import os
import pytest

from slack_bot.tools.mcp.mcp_config import (
    MCPServerConfig,
    has_vaultwarden_refs,
    load_mcp_config,
)


@pytest.fixture
def base_config(tmp_path):
    """Create a base MCP config file."""
    config = {
        "mcpServers": {
            "github": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "vaultwarden:GITHUB_TOKEN"},
                "enabled": False,
                "description": "GitHub MCP server"
            },
            "filesystem": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                "enabled": False,
                "description": "Local filesystem MCP server"
            }
        }
    }
    path = str(tmp_path / "mcp_servers.json")
    with open(path, "w") as f:
        json.dump(config, f)
    return path


@pytest.fixture
def local_config(tmp_path):
    """Create a local override MCP config file."""
    config = {
        "mcpServers": {
            "github": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "ghp_LOCALTOKEN"},
                "enabled": True,
                "description": "GitHub MCP server (local)"
            }
        }
    }
    path = str(tmp_path / "mcp_servers.local.json")
    with open(path, "w") as f:
        json.dump(config, f)
    return path


@pytest.mark.unit
class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass."""

    def test_defaults(self):
        config = MCPServerConfig(name="test")
        assert config.transport == "stdio"
        assert config.enabled is False
        assert config.command == ""
        assert config.args == []
        assert config.env == {}

    def test_full_config(self):
        config = MCPServerConfig(
            name="github",
            transport="stdio",
            command="npx",
            args=["-y", "server"],
            env={"TOKEN": "abc"},
            enabled=True,
            description="GitHub",
        )
        assert config.name == "github"
        assert config.enabled is True
        assert config.args == ["-y", "server"]


@pytest.mark.unit
class TestLoadMCPConfig:
    """Tests for load_mcp_config."""

    def test_load_base_config(self, base_config):
        configs = load_mcp_config(base_path=base_config, local_path="/nonexistent")
        assert "github" in configs
        assert "filesystem" in configs
        assert configs["github"].enabled is False

    def test_local_overrides_base(self, base_config, local_config):
        configs = load_mcp_config(base_path=base_config, local_path=local_config)
        assert configs["github"].enabled is True
        assert configs["github"].env["GITHUB_TOKEN"] == "ghp_LOCALTOKEN"
        # filesystem still from base
        assert "filesystem" in configs

    def test_no_config_files(self, tmp_path):
        configs = load_mcp_config(
            base_path=str(tmp_path / "nope.json"),
            local_path=str(tmp_path / "also_nope.json"),
        )
        assert configs == {}

    def test_auto_local_path(self, base_config):
        """Default local_path is derived from base_path."""
        configs = load_mcp_config(base_path=base_config)
        # Should work without error (local file just won't exist)
        assert "github" in configs


@pytest.mark.unit
class TestHasVaultwardenRefs:
    """Tests for has_vaultwarden_refs."""

    def test_env_with_ref(self):
        config = MCPServerConfig(
            name="test",
            env={"TOKEN": "vaultwarden:GITHUB_TOKEN"},
        )
        assert has_vaultwarden_refs(config) is True

    def test_header_with_ref(self):
        config = MCPServerConfig(
            name="test",
            headers={"Authorization": "vaultwarden:API_KEY"},
        )
        assert has_vaultwarden_refs(config) is True

    def test_no_refs(self):
        config = MCPServerConfig(
            name="test",
            env={"TOKEN": "plain_value"},
        )
        assert has_vaultwarden_refs(config) is False

    def test_empty_config(self):
        config = MCPServerConfig(name="test")
        assert has_vaultwarden_refs(config) is False
