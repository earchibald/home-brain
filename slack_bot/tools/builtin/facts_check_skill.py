"""
FACTS Check Skill — reminds the LLM to check user facts.

A skill is a BaseTool subclass with category="skill". Skills are registered
in ToolRegistry but filtered from the /tools UI. The LLM can call them;
users don't see or manage them directly.

FactsCheckSkill: Returns a formatted instruction string reminding the LLM
to check the user's FACTS before answering a personal question.
"""

import logging
from typing import Any, Dict

from slack_bot.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class FactsCheckSkill(BaseTool):
    """Skill that reminds the LLM to check the user's stored facts.

    When the LLM is about to answer a personal question, it can call
    this skill to get a reminder instruction. The instruction tells
    the LLM to consult FACTS context before responding.

    This is a "skill" (not a user-visible tool), so it:
    - Has category="skill"
    - Is registered in ToolRegistry
    - Is filtered from the /tools UI
    - Can be called by the LLM via tool dispatch
    """

    name = "facts_check"
    display_name = "Facts Check"
    description = (
        "Check the user's stored personal facts before answering. "
        "Call this when the user asks about their preferences, personal details, "
        "health information, contacts, goals, or other personal context."
    )
    category = "skill"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": (
                        "Brief description of what personal context is needed "
                        "(e.g., 'coffee preferences', 'family members', 'health goals')"
                    ),
                },
            },
            "required": ["context"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Return a reminder instruction to check FACTS.

        Args:
            context: Description of what personal context is needed

        Returns:
            ToolResult with instruction text
        """
        context = kwargs.get("context", "personal information")

        instruction = (
            f"REMINDER: Check the user's stored FACTS for {context}. "
            "The FACTS system contains personal details, preferences, health info, "
            "contacts, goals, and other persistent user context. "
            "If relevant facts have been injected into the system prompt, "
            "use them to personalize your response. "
            "If no matching facts are available, ask the user for the information "
            "and suggest storing it with the FACTS tool for future reference."
        )

        logger.debug(f"FactsCheckSkill called for context: {context}")

        return ToolResult(
            tool_name=self.name,
            success=True,
            content=instruction,
        )
