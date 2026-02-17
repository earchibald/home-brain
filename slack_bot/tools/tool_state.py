"""
Tool state persistence — per-user enable/disable for tools.

Mirrors the ApiKeyStore pattern: JSON file with 0600 permissions.
Storage path: ~/.brain-tool-state.json
"""

import json
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ToolStateStore:
    """Per-user tool enable/disable state, persisted to JSON.

    Schema:
        {
            "user_id": {
                "tool_name": true/false
            }
        }

    Mirrors ApiKeyStore pattern from agents/slack_agent.py.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or os.path.expanduser("~/.brain-tool-state.json")
        self._ensure_file()

    def _ensure_file(self):
        """Create storage file with secure permissions if it doesn't exist."""
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w") as f:
                json.dump({}, f)
            os.chmod(self.storage_path, 0o600)

    def _load(self) -> dict:
        try:
            with open(self.storage_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, data: dict):
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(self.storage_path, 0o600)

    def is_enabled(self, user_id: str, tool_name: str) -> bool:
        """Check if a tool is enabled for a user. Default: True (all tools enabled)."""
        data = self._load()
        user_state = data.get(user_id, {})
        return user_state.get(tool_name, True)

    def set_enabled(self, user_id: str, tool_name: str, enabled: bool):
        """Set enable/disable state for a tool per user."""
        data = self._load()
        if user_id not in data:
            data[user_id] = {}
        data[user_id][tool_name] = enabled
        self._save(data)
        logger.info(f"Tool '{tool_name}' {'enabled' if enabled else 'disabled'} for user {user_id}")

    def get_user_state(self, user_id: str) -> Dict[str, bool]:
        """Get all tool states for a user."""
        data = self._load()
        return data.get(user_id, {})

    def clear_user_state(self, user_id: str):
        """Reset all tool states for a user to defaults."""
        data = self._load()
        if user_id in data:
            del data[user_id]
            self._save(data)
