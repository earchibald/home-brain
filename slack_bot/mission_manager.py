"""
Mission Manager — editable agent behavior directives.

Manages ~/.brain-mission.md, a plaintext file of behavior principles
that gets injected into every system prompt. Hot-reloads without bot restart.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MISSION = """## Agent Mission Principles
- Always check FACTS before answering personal questions.
- Prioritize conversation context over brain search results.
- Be concise and direct.
- When the user shares personal details, proactively store them as FACTS.
- Cite sources when using brain search results.
"""


class MissionManager:
    """Load, save, and format the mission principles file.

    Path: ~/.brain-mission.md (local to NUC-2, not Syncthing).
    Hot-reloads on every prompt generation — no restart needed.
    """

    def __init__(self, mission_path: Optional[str] = None):
        self.mission_path = mission_path or os.path.expanduser("~/.brain-mission.md")

    async def load(self) -> str:
        """Read mission file, returning default if missing.

        Returns:
            Mission principles content string
        """
        try:
            if os.path.exists(self.mission_path):
                with open(self.mission_path, "r") as f:
                    content = f.read().strip()
                if content:
                    return content
        except Exception as e:
            logger.warning(f"Failed to read mission file: {e}")

        # Return default and persist it
        await self.save(DEFAULT_MISSION.strip())
        return DEFAULT_MISSION.strip()

    async def save(self, content: str) -> bool:
        """Save updated mission principles.

        Args:
            content: New mission principles text

        Returns:
            True if saved successfully
        """
        try:
            with open(self.mission_path, "w") as f:
                f.write(content)
            logger.info(f"Mission principles saved ({len(content)} chars)")
            return True
        except Exception as e:
            logger.error(f"Failed to save mission file: {e}")
            return False

    async def get_for_prompt(self) -> str:
        """Get mission principles formatted for system prompt injection.

        Always does a fresh file read (cheap local IO) for hot-reload.

        Returns:
            Formatted mission string for system prompt
        """
        content = await self.load()
        return self.format_for_system_prompt(content)

    @staticmethod
    def format_for_system_prompt(content: str) -> str:
        """Wrap mission content in an operator instructions section.

        Args:
            content: Raw mission text

        Returns:
            Formatted string for system prompt injection
        """
        return f"## Operator Instructions (Mission Principles)\n\n{content}"
