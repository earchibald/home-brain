"""
Unit tests for MissionManager — mission principles loading/saving/formatting.
"""

import os
import pytest

from slack_bot.mission_manager import DEFAULT_MISSION, MissionManager


@pytest.fixture
def mission_manager(tmp_path):
    """Create a MissionManager with temp path."""
    return MissionManager(mission_path=str(tmp_path / "mission.md"))


@pytest.mark.unit
class TestMissionManager:
    """Tests for MissionManager."""

    async def test_load_creates_default(self, mission_manager):
        """First load creates file with default content."""
        content = await mission_manager.load()
        assert "Mission Principles" in content
        assert os.path.exists(mission_manager.mission_path)

    async def test_save_and_load(self, mission_manager):
        custom = "Be helpful and concise."
        await mission_manager.save(custom)
        content = await mission_manager.load()
        assert content == custom

    async def test_save_returns_true(self, mission_manager):
        result = await mission_manager.save("test content")
        assert result is True

    async def test_load_existing_file(self, tmp_path):
        path = str(tmp_path / "mission.md")
        with open(path, "w") as f:
            f.write("Custom mission content")
        mm = MissionManager(mission_path=path)
        content = await mm.load()
        assert content == "Custom mission content"

    async def test_load_empty_file_returns_default(self, tmp_path):
        path = str(tmp_path / "mission.md")
        with open(path, "w") as f:
            f.write("")
        mm = MissionManager(mission_path=path)
        content = await mm.load()
        assert "Mission Principles" in content

    async def test_get_for_prompt(self, mission_manager):
        await mission_manager.save("Be concise.")
        prompt = await mission_manager.get_for_prompt()
        assert "Operator Instructions" in prompt
        assert "Be concise." in prompt

    def test_format_for_system_prompt(self):
        result = MissionManager.format_for_system_prompt("Be helpful.")
        assert "## Operator Instructions" in result
        assert "Be helpful." in result

    async def test_hot_reload(self, mission_manager):
        """Modifying the file is picked up on next get_for_prompt."""
        await mission_manager.save("Version 1")
        v1 = await mission_manager.get_for_prompt()
        assert "Version 1" in v1

        # Directly modify file
        with open(mission_manager.mission_path, "w") as f:
            f.write("Version 2")

        v2 = await mission_manager.get_for_prompt()
        assert "Version 2" in v2

    async def test_default_mission_content(self):
        """Default mission has useful directives."""
        assert "FACTS" in DEFAULT_MISSION
        assert "concise" in DEFAULT_MISSION

    async def test_save_failure_returns_false(self, tmp_path):
        mm = MissionManager(mission_path="/nonexistent/dir/mission.md")
        result = await mm.save("test")
        assert result is False
