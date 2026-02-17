"""
Integration test: Mission principles injection into _process_message context.

Tests that MissionManager loads content from file and it gets
properly formatted for system prompt injection.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from slack_bot.mission_manager import MissionManager


@pytest.mark.integration
class TestMissionInjection:
    """Test mission principles loading and injection."""

    @pytest.mark.asyncio
    async def test_load_mission_from_file(self, tmp_path):
        """MissionManager loads content from a file."""
        mission_file = tmp_path / ".brain-mission.md"
        mission_file.write_text(
            "# Mission\n\n"
            "1. Be helpful and concise\n"
            "2. Always cite sources\n"
            "3. Protect user privacy\n"
        )

        manager = MissionManager(mission_path=str(mission_file))
        content = await manager.load()

        assert "Be helpful and concise" in content
        assert "Always cite sources" in content
        assert "Protect user privacy" in content

    @pytest.mark.asyncio
    async def test_mission_formatted_for_injection(self, tmp_path):
        """Mission content is formatted with section header for injection."""
        mission_file = tmp_path / ".brain-mission.md"
        mission_file.write_text("Be very precise in responses.")

        manager = MissionManager(mission_path=str(mission_file))
        formatted = await manager.get_for_prompt()

        assert "Operator Instructions" in formatted or "Be very precise" in formatted

    @pytest.mark.asyncio
    async def test_mission_missing_file_returns_default(self, tmp_path):
        """Missing mission file returns default content and creates file."""
        mission_path = str(tmp_path / "nonexistent-mission.md")
        manager = MissionManager(mission_path=mission_path)
        content = await manager.load()

        # Should not crash, should return default content
        assert content is not None
        assert len(content) > 0
        # File should have been created with default
        assert os.path.exists(mission_path)

    @pytest.mark.asyncio
    async def test_mission_hot_reload(self, tmp_path):
        """Mission content updates when file changes."""
        mission_file = tmp_path / ".brain-mission.md"
        mission_file.write_text("Version 1: Be brief.")

        manager = MissionManager(mission_path=str(mission_file))
        content_v1 = await manager.load()
        assert "Version 1" in content_v1

        # Update the file
        mission_file.write_text("Version 2: Be thorough.")
        content_v2 = await manager.load()
        assert "Version 2" in content_v2

    @pytest.mark.asyncio
    async def test_mission_empty_file(self, tmp_path):
        """Empty mission file returns default content."""
        mission_file = tmp_path / ".brain-mission.md"
        mission_file.write_text("")

        manager = MissionManager(mission_path=str(mission_file))
        content = await manager.load()

        # Empty file should trigger default
        assert content is not None
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_mission_multiline_complex_content(self, tmp_path):
        """Complex multi-section mission file is loaded fully."""
        mission_content = """# Brain Mission Principles

## Core Values
- Accuracy above all
- User privacy is sacred
- Respond in the user's language

## Behavioral Guidelines
1. Never make up information
2. Cite sources when possible
3. Ask clarifying questions when ambiguous

## Tone
- Professional but friendly
- Concise unless asked for detail
"""
        mission_file = tmp_path / ".brain-mission.md"
        mission_file.write_text(mission_content)

        manager = MissionManager(mission_path=str(mission_file))
        content = await manager.load()

        assert "Accuracy above all" in content
        assert "Never make up information" in content
        assert "Professional but friendly" in content

    def test_format_for_system_prompt_static(self):
        """Static format method wraps content correctly."""
        formatted = MissionManager.format_for_system_prompt("Be concise.")
        assert "Be concise." in formatted
        assert "Operator Instructions" in formatted
