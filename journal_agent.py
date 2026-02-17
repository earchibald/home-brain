"""
Journal Agent - Enhanced daily journaling with AI-powered suggestions
"""

import sys
from pathlib import Path
from datetime import datetime

# Add clients to path
sys.path.insert(0, str(Path(__file__).parent.parent / "clients"))

from agent_platform import Agent


class JournalAgent(Agent):
    """
    Creates daily journal entries with:
    - AI-generated reflection prompts
    - Focus recommendations based on recent activity
    - Evening summary template
    """

    async def run(self) -> bool:
        """Generate today's journal entry"""
        today = datetime.now().strftime("%Y-%m-%d")
        journal_path = f"journal/{today}.md"

        # Check if journal already exists
        existing = await self.brain_io.read_file(journal_path)
        if existing:
            self.logger.info(f"Journal entry already exists for {today}")
            return True

        try:
            # Get recent brain activity for context
            activity = await self.search.get_recent_activity(hours=24, folder="brain")

            # Generate AI prompts and focus recommendations
            prompts = await self._generate_prompts(activity)
            focus = await self._generate_focus(activity)

            # Build journal entry
            entry = self._build_journal_entry(today, prompts, focus)

            # Write to brain
            success = await self.brain_io.write_file(
                journal_path, entry, overwrite=False
            )

            if success:
                await self.notify(
                    "[NUC-2] ✓ Daily Journal Created",
                    f"Journal entry created for {today}",
                )
                await self.log_execution(True, f"Generated journal for {today}")
            else:
                await self.log_execution(False, "Failed to write journal file")

            return success

        except Exception as e:
            self.logger.error(f"Journal generation failed: {e}", exc_info=True)
            await self.notify(
                "[NUC-2] Journal Agent Failed",
                f"Error generating journal: {str(e)}",
                priority="high",
            )
            await self.log_execution(False, str(e))
            return False

    async def _generate_prompts(self, activity: dict) -> list:
        """Generate reflection prompts using LLM"""
        try:
            recent_topics = activity.get("topics", [])

            if not recent_topics:
                return [
                    "What's one thing you accomplished today?",
                    "Where did you get stuck or struggle?",
                    "What did you learn?",
                ]

            topics_str = ", ".join(recent_topics[:3])

            prompt = f"""Generate 3 brief journaling prompts (1 sentence each) based on these 
recent activity topics: {topics_str}

Make prompts reflective and actionable. Format as a simple numbered list."""

            response = await self.llm.complete(prompt, max_tokens=200)

            # Parse response into list
            lines = response.strip().split("\n")
            prompts = [
                line.strip("0123456789.- ")
                for line in lines
                if line.strip() and any(c.isalpha() for c in line)
            ]

            return prompts[:3] if prompts else self._default_prompts()

        except Exception as e:
            self.logger.warning(f"Failed to generate prompts: {e}")
            return self._default_prompts()

    async def _generate_focus(self, activity: dict) -> str:
        """Generate today's focus recommendations"""
        try:
            recent_activity = activity.get("recent_activity", [])

            if not recent_activity:
                return "Review your notes from the past week and pick 3 things to focus on today."

            # Build context from recent activity
            context = "\n".join(
                [
                    f"- {result.heading}: {result.entry[:100]}..."
                    for result in recent_activity[:5]
                ]
            )

            prompt = f"""Based on these recent notes, suggest 2-3 specific focus areas for today.
Be brief and actionable.

Recent Activity:
{context}

Today's Focus Recommendations:"""

            response = await self.llm.complete(prompt, max_tokens=150)
            return response.strip()

        except Exception as e:
            self.logger.warning(f"Failed to generate focus: {e}")
            return "Reflect on your recent activity and choose your top priorities."

    def _default_prompts(self) -> list:
        """Default prompts if LLM fails"""
        return [
            "What was one small win today? (builds momentum)",
            "Where did you get stuck or struggle? (identify support needs)",
            "What did you learn or discover? (capture knowledge)",
        ]

    def _build_journal_entry(self, today: str, prompts: list, focus: str) -> str:
        """Build the markdown journal entry"""
        return f"""# Daily Journal: {today}

## Today's Focus
{focus}

## Reflection Prompts
{chr(10).join(f"{i + 1}. {p}" for i, p in enumerate(prompts))}

## Your Reflections
[Write your thoughts here throughout the day]

---
*Entry created automatically by NUC-2 Journal Agent*
"""
