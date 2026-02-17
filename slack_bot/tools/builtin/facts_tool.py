"""
FACTS Tool — Fixed Attribute & Context Tracking System.

Persistent per-user memory for Brain Assistant. Stores facts about the user
(preferences, personal details, contacts, goals) in a JSON file.

Components:
- FactsStore: File-based persistence (mirrors ApiKeyStore pattern)
- FactsTool: UserScopedTool implementation for LLM-driven CRUD
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from slack_bot.tools.base_tool import ToolResult, UserScopedTool

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "personal",
    "preferences",
    "health",
    "work",
    "family",
    "goals",
    "context",
    "other",
}


class FactsStore:
    """Per-user persistent fact storage.

    Storage path: ~/.brain-facts-{user_id}.json (0600 permissions)

    Entry schema:
        {
            "preferred_coffee": {
                "key": "preferred_coffee",
                "value": "oat milk flat white",
                "category": "preferences",
                "created_at": "2026-02-16T10:00:00",
                "last_updated": "2026-02-16T10:00:00"
            }
        }
    """

    def __init__(self, user_id: str, storage_dir: Optional[str] = None):
        self.user_id = user_id
        storage_dir = storage_dir or os.path.expanduser("~")
        self.storage_path = os.path.join(storage_dir, f".brain-facts-{user_id}.json")
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

    def store(self, key: str, value: str, category: str = "other") -> dict:
        """Store or update a fact.

        Args:
            key: Descriptive slug key (e.g., "preferred_coffee")
            value: Fact value
            category: One of VALID_CATEGORIES

        Returns:
            Dict with entry, old_value (if update), was_update bool
        """
        if category not in VALID_CATEGORIES:
            category = "other"

        key = key.strip().lower().replace(" ", "_")
        now = datetime.now().isoformat()

        data = self._load()
        old_value = None
        was_update = False

        if key in data:
            old_value = data[key].get("value")
            was_update = True
            data[key]["value"] = value
            data[key]["category"] = category
            data[key]["last_updated"] = now
        else:
            data[key] = {
                "key": key,
                "value": value,
                "category": category,
                "created_at": now,
                "last_updated": now,
            }

        self._save(data)
        logger.info(f"FACTS: {'Updated' if was_update else 'Stored'} '{key}' for user {self.user_id}")

        return {
            "entry": data[key],
            "old_value": old_value,
            "was_update": was_update,
        }

    def get(self, key: str) -> Optional[dict]:
        """Get a fact by key.

        Args:
            key: Fact key slug

        Returns:
            Fact entry dict, or None if not found
        """
        key = key.strip().lower().replace(" ", "_")
        data = self._load()
        return data.get(key)

    def list_facts(self, category: Optional[str] = None) -> List[dict]:
        """List all facts, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of fact entries, sorted by last_updated descending
        """
        data = self._load()
        facts = list(data.values())

        if category:
            facts = [f for f in facts if f.get("category") == category]

        # Sort by last_updated descending
        facts.sort(key=lambda f: f.get("last_updated", ""), reverse=True)
        return facts

    def delete(self, key: str) -> bool:
        """Delete a fact by key.

        Args:
            key: Fact key slug

        Returns:
            True if the fact existed and was deleted
        """
        key = key.strip().lower().replace(" ", "_")
        data = self._load()
        if key in data:
            del data[key]
            self._save(data)
            logger.info(f"FACTS: Deleted '{key}' for user {self.user_id}")
            return True
        return False

    def clear_all(self) -> int:
        """Delete all facts for this user.

        Returns:
            Number of facts that were deleted
        """
        data = self._load()
        count = len(data)
        if count > 0:
            self._save({})
            logger.info(f"FACTS: Cleared all {count} facts for user {self.user_id}")
        return count

    def get_context_for_injection(self, limit: int = 20) -> str:
        """Format stored facts as context string for system prompt injection.

        Args:
            limit: Maximum facts to include (most recently updated first)

        Returns:
            Formatted context string, or empty string if no facts
        """
        facts = self.list_facts()[:limit]
        if not facts:
            return ""

        lines = ["## Known facts about this user (from FACTS memory):\n"]
        for fact in facts:
            key = fact.get("key", "")
            value = fact.get("value", "")
            category = fact.get("category", "other")
            lines.append(f"- [{category}] {key}: {value}")

        return "\n".join(lines)

    def count(self) -> int:
        """Return the number of stored facts."""
        return len(self._load())


class FactsTool(UserScopedTool):
    """FACTS tool for LLM-driven persistent user memory.

    Supports four operations: store, get, list, delete.
    _user_id is set by ToolExecutor before each execute() call.
    """

    name = "facts"
    display_name = "FACTS Memory"
    description = (
        "Store and retrieve persistent facts about the user. Use to remember "
        "preferences, personal details, contacts, goals. Operations: "
        "store (save a fact), get (retrieve one fact), list (show all facts), "
        "delete (remove a fact)."
    )
    category = "builtin"

    def __init__(self, storage_dir: Optional[str] = None):
        self._storage_dir = storage_dir

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "The operation to perform",
                    "enum": ["store", "get", "list", "delete"],
                },
                "key": {
                    "type": "string",
                    "description": "Descriptive slug key (e.g., 'preferred_coffee', 'spouse_name')",
                },
                "value": {
                    "type": "string",
                    "description": "The fact value (required for 'store' operation)",
                },
                "category": {
                    "type": "string",
                    "description": "Fact category",
                    "enum": list(VALID_CATEGORIES),
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Execute a FACTS operation.

        Args:
            operation: "store", "get", "list", or "delete"
            key: Fact key (required for store/get/delete)
            value: Fact value (required for store)
            category: Fact category (optional, default "other")

        Returns:
            ToolResult with operation results
        """
        operation = kwargs.get("operation", "")
        key = kwargs.get("key", "")
        value = kwargs.get("value", "")
        category = kwargs.get("category", "other")

        if not self._user_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="User ID not set (internal error)",
            )

        store = FactsStore(self._user_id, storage_dir=self._storage_dir)

        if operation == "store":
            if not key or not value:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="'store' requires both 'key' and 'value'",
                )
            result = store.store(key, value, category)
            content = f"Stored fact: {key} = {value} [{category}]"
            if result["was_update"] and result["old_value"] != value:
                content += f"\nNote: Updated from previous value: '{result['old_value']}'"
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=content,
                raw=result,
            )

        elif operation == "get":
            if not key:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="'get' requires 'key'",
                )
            entry = store.get(key)
            if entry:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=f"{entry['key']}: {entry['value']} [{entry.get('category', 'other')}]",
                    raw=entry,
                )
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=f"No fact found with key: {key}",
            )

        elif operation == "list":
            facts = store.list_facts(category=category if category != "other" else None)
            if not facts:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content="No facts stored yet.",
                    raw=[],
                )
            lines = [f"Stored facts ({len(facts)} total):"]
            for fact in facts:
                lines.append(
                    f"- [{fact.get('category', 'other')}] {fact['key']}: {fact['value']}"
                )
            return ToolResult(
                tool_name=self.name,
                success=True,
                content="\n".join(lines),
                raw=facts,
            )

        elif operation == "delete":
            if not key:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="'delete' requires 'key'",
                )
            deleted = store.delete(key)
            if deleted:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=f"Deleted fact: {key}",
                )
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=f"No fact found with key: {key}",
            )

        else:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Unknown operation: {operation}. Use: store, get, list, delete",
            )


def message_references_personal_context(text: str) -> bool:
    """Check if a message likely references personal context (needs FACTS injection).

    Checks for personal pronouns, possessives, and fact-category keywords.

    Args:
        text: User message text

    Returns:
        True if the message likely needs FACTS context
    """
    text_lower = text.lower()

    # Personal pronouns and possessives
    personal_markers = [
        " i ", " my ", " me ", " mine ", " i'm ", " i've ", " i'd ",
        "my ", "i ", " myself",
    ]
    if any(marker in f" {text_lower} " for marker in personal_markers):
        return True

    # Category keywords
    category_keywords = [
        "prefer", "favorite", "favourite", "like", "hate", "allergic",
        "wife", "husband", "spouse", "partner", "kid", "child", "son", "daughter",
        "work", "job", "project", "goal", "plan",
        "health", "doctor", "medicine", "diet",
        "remember", "recall", "you know",
        "what do you know about me",
    ]
    return any(kw in text_lower for kw in category_keywords)
