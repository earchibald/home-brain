"""
Advice Agent - Personalized advice for ADHD, work, and learning
"""

import sys
from pathlib import Path
from datetime import datetime

# Add clients to path
sys.path.insert(0, str(Path(__file__).parent.parent / "clients"))

from agent_platform import Agent


class AdviceAgent(Agent):
    """
    Provides personalized advice using brain context:
    - ADHD strategies & symptom management
    - Work organization & productivity
    - Learning techniques & study strategies
    
    Learns from brain notes about successes and failures.
    """

    async def run(self) -> bool:
        """Generate daily advice based on brain context"""
        today = datetime.now().strftime("%Y-%m-%d")
        advice_path = f"advice/{today}-daily-advice.md"
        
        try:
            # Check if advice already exists
            existing = await self.brain_io.read_file(advice_path)
            if existing:
                self.logger.info(f"Advice already generated for {today}")
                return True
            
            # Get recent activity and context
            context = await self._gather_context()
            
            # Generate advice for each specialization
            adhd_advice = await self._generate_adhd_advice(context)
            work_advice = await self._generate_work_advice(context)
            learning_advice = await self._generate_learning_advice(context)
            
            # Build advice document
            advice = self._build_advice_document(today, adhd_advice, work_advice, learning_advice)
            
            # Write to brain
            success = await self.brain_io.write_file(advice_path, advice, overwrite=False)
            
            if success:
                await self.notify(
                    "[NUC-2] ✓ Daily Advice Generated",
                    f"Personalized advice created for {today}"
                )
                await self.log_execution(True, f"Generated advice for {today}")
            else:
                await self.log_execution(False, "Failed to write advice file")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Advice generation failed: {e}", exc_info=True)
            await self.notify(
                "[NUC-2] Advice Agent Failed",
                f"Error generating advice: {str(e)}",
                priority="high"
            )
            await self.log_execution(False, str(e))
            return False

    async def _gather_context(self) -> dict:
        """Gather brain context for advice generation"""
        try:
            # Get recent notes
            recent_files = await self.brain_io.get_recent_files(hours=168)  # Last week
            
            context = {
                "recent_files": recent_files[:5],
                "journal_activity": "",
                "work_activity": "",
                "adhd_patterns": "",
            }
            
            # Try to find ADHD-related notes
            adhd_results = await self.khoj.search_by_folder(
                "ADHD time management focus",
                folder="learning"
            )
            if adhd_results:
                context["adhd_patterns"] = "\n".join([
                    r.entry[:200] for r in adhd_results[:3]
                ])
            
            # Try to find work activity
            work_results = await self.khoj.search_by_folder(
                "project work deadline",
                folder="work"
            )
            if work_results:
                context["work_activity"] = "\n".join([
                    r.entry[:200] for r in work_results[:3]
                ])
            
            return context
            
        except Exception as e:
            self.logger.warning(f"Failed to gather context: {e}")
            return {}

    async def _generate_adhd_advice(self, context: dict) -> str:
        """Generate ADHD-specific advice"""
        try:
            prompt = f"""You are an ADHD coach. Based on the user's notes and patterns, 
provide ONE specific, actionable ADHD management tip for today. Keep it brief (2-3 sentences).

Recent ADHD patterns from their notes:
{context.get("adhd_patterns", "No specific patterns found - provide general ADHD tip.")}

Provide practical advice that considers:
- Executive dysfunction challenges
- Time blindness and task initiation
- Hyperfocus management
- Environmental optimization

Format: A single tip that the user can implement in the next hour."""
            
            response = await self.llm.complete(prompt, max_tokens=150)
            return response.strip()
            
        except Exception as e:
            self.logger.warning(f"Failed to generate ADHD advice: {e}")
            return "💡 Tip: Use a timer for task transitions to manage time blindness."

    async def _generate_work_advice(self, context: dict) -> str:
        """Generate work advice"""
        try:
            prompt = f"""You are a work productivity consultant. Based on the user's recent 
work activity, provide ONE quick productivity tip for today (2-3 sentences).

Recent work context:
{context.get("work_activity", "No specific work activity - provide general productivity tip.")}

Consider their current workload and suggest:
- Single focus area if multiple projects
- Time-blocking suggestion
- Priority ranking if needed

Format: Actionable work advice."""
            
            response = await self.llm.complete(prompt, max_tokens=150)
            return response.strip()
            
        except Exception as e:
            self.logger.warning(f"Failed to generate work advice: {e}")
            return "💼 Tip: Schedule your hardest task for peak energy hours."

    async def _generate_learning_advice(self, context: dict) -> str:
        """Generate learning advice"""
        try:
            prompt = f"""You are a learning coach. Based on the user's learning history, 
provide ONE study or learning tip for today (2-3 sentences).

Recent learning context:
{context.get("recent_files", "No specific learning activity.")}

Suggest:
- A study technique if they're learning something
- Concept connection if possible
- Break recommendation if deep focus detected

Format: Practical learning advice."""
            
            response = await self.llm.complete(prompt, max_tokens=150)
            return response.strip()
            
        except Exception as e:
            self.logger.warning(f"Failed to generate learning advice: {e}")
            return "📚 Tip: Take a 5-minute break every 25 minutes to consolidate learning."

    def _build_advice_document(
        self,
        today: str,
        adhd: str,
        work: str,
        learning: str
    ) -> str:
        """Build the markdown advice document"""
        return f"""# Your Personal Advice - {today}

## 🧠 ADHD Management
{adhd}

## 💼 Work & Productivity  
{work}

## 📚 Learning & Development
{learning}

---

## 💭 Reflection
*Which tip resonates with you today? Try implementing one before assessing impact.*

*Want to explore more? Search your brain for related topics or ask questions in Khoj.*

Generated by NUC-2 Advice Agent | [Edit](obsidian://open) | [Share](#)
"""
