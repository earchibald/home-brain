"""
Unit tests for FactsCheckSkill — LLM-callable skill for personal context reminders.
"""

import pytest
from slack_bot.tools.builtin.facts_check_skill import FactsCheckSkill


@pytest.mark.unit
class TestFactsCheckSkillInit:
    """Test skill properties."""

    def test_name(self):
        skill = FactsCheckSkill()
        assert skill.name == "facts_check"

    def test_category_is_skill(self):
        skill = FactsCheckSkill()
        assert skill.category == "skill"

    def test_display_name(self):
        skill = FactsCheckSkill()
        assert skill.display_name == "Facts Check"

    def test_description_nonempty(self):
        skill = FactsCheckSkill()
        assert len(skill.description) > 0

    def test_parameters_schema(self):
        skill = FactsCheckSkill()
        schema = skill.parameters_schema
        assert schema["type"] == "object"
        assert "context" in schema["properties"]
        assert "context" in schema["required"]


@pytest.mark.unit
class TestFactsCheckSkillFunctionSpec:
    """Test OpenAI function spec generation."""

    def test_to_function_spec(self):
        skill = FactsCheckSkill()
        spec = skill.to_function_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "facts_check"
        assert "parameters" in spec["function"]

    def test_to_prompt_description(self):
        skill = FactsCheckSkill()
        desc = skill.to_prompt_description()
        assert "facts_check" in desc
        assert "context" in desc


@pytest.mark.unit
class TestFactsCheckSkillExecute:
    """Test skill execution."""

    @pytest.mark.asyncio
    async def test_execute_returns_instruction(self):
        skill = FactsCheckSkill()
        result = await skill.execute(context="coffee preferences")
        assert result.success is True
        assert result.tool_name == "facts_check"
        assert "coffee preferences" in result.content
        assert "REMINDER" in result.content

    @pytest.mark.asyncio
    async def test_execute_default_context(self):
        skill = FactsCheckSkill()
        result = await skill.execute()
        assert result.success is True
        assert "personal information" in result.content

    @pytest.mark.asyncio
    async def test_execute_health_context(self):
        skill = FactsCheckSkill()
        result = await skill.execute(context="health goals")
        assert "health goals" in result.content
        assert "FACTS" in result.content

    @pytest.mark.asyncio
    async def test_execute_to_context_string(self):
        """Result can be formatted for LLM context injection."""
        skill = FactsCheckSkill()
        result = await skill.execute(context="family members")
        ctx_str = result.to_context_string()
        assert "[Tool: facts_check]" in ctx_str
        assert "family members" in ctx_str

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Skill is always available."""
        skill = FactsCheckSkill()
        assert await skill.health_check() is True


@pytest.mark.unit
class TestFactsCheckSkillHiddenFromUI:
    """Verify skill is filtered from /tools UI by category."""

    def test_skill_category_differs_from_builtin(self):
        skill = FactsCheckSkill()
        assert skill.category != "builtin"
        assert skill.category != "mcp"
        assert skill.category == "skill"

    def test_skill_not_in_builtin_list(self):
        """When ToolRegistry.list_tools(category='builtin'), skill is excluded."""
        from slack_bot.tools.tool_registry import ToolRegistry
        from slack_bot.tools.tool_state import ToolStateStore
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ToolStateStore(storage_path=os.path.join(tmpdir, "state.json"))
            registry = ToolRegistry(store)
            registry.register(FactsCheckSkill())

            builtin = registry.list_tools(category="builtin")
            assert len(builtin) == 0  # Skill is NOT shown in builtin

            skills = registry.list_tools(category="skill")
            assert len(skills) == 1
            assert skills[0].name == "facts_check"
