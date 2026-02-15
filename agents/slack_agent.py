"""
Slack Agent - Multi-turn conversation bot with brain context

Connects to Slack via Socket Mode, handles DM messages with:
- Per-user conversation history
- Khoj context search
- Ollama LLM inference
- Automatic summarization for long conversations
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.errors import SlackApiError

from agent_platform import Agent
from clients.khoj_client import KhojClient
from clients.llm_client import OllamaClient, Message
from clients.brain_io import BrainIO
from clients.conversation_manager import ConversationManager

# Import new slack_bot modules for enhanced features
from slack_bot.message_processor import detect_file_attachments
from slack_bot.file_handler import download_file_from_slack, extract_text_content
from slack_bot.performance_monitor import PerformanceMonitor
from slack_bot.exceptions import (
    FileDownloadError,
    UnsupportedFileTypeError,
    FileExtractionError,
)


class SlackAgent(Agent):
    """Slack conversation bot with brain context and multi-turn memory"""

    def __init__(self, config: Dict):
        super().__init__("slack_agent", config)

        # Slack setup
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.app_token = os.getenv("SLACK_APP_TOKEN")

        if not self.bot_token or not self.app_token:
            raise ValueError(
                "Missing Slack tokens. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in environment."
            )

        # Initialize Slack app
        self.app = AsyncApp(token=self.bot_token)
        self.socket_handler = None

        # Initialize clients
        self.khoj = KhojClient(
            base_url=config.get("khoj_url", "http://192.168.1.195:42110")
        )
        self.llm = OllamaClient(
            base_url=config.get("ollama_url", "http://192.168.1.58:11434")
        )
        self.brain = BrainIO(
            brain_path=config.get("brain_path", "/home/earchibald/brain")
        )

        # Initialize conversation manager
        self.conversations = ConversationManager(
            brain_path=config.get("brain_path", "/home/earchibald/brain"),
            llm_client=self.llm,
        )

        # Configuration
        self.model = config.get("model", "llama3.2")
        self.max_context_tokens = config.get("max_context_tokens", 6000)
        self.enable_khoj_search = config.get("enable_khoj_search", True)
        self.max_search_results = config.get("max_search_results", 3)
        self.system_prompt = config.get(
            "system_prompt",
            """You are Brain Assistant, an AI agent integrated with Eugene's personal knowledge management system. Your mission is to serve as an active thought partner, helping capture insights, retrieve knowledge, and support deep work.

## Your Capabilities

**Memory & Context:**
- Access to Eugene's semantic brain (markdown notes, journals, projects, ideas)
- Multi-turn conversation history for continuity across sessions
- File upload analysis (text, PDF, code)
- When brain context appears above, it's highly relevant—cite sources when referencing it

**Your Role:**
1. **Knowledge Retrieval** - Surface relevant past notes, ideas, and context from the brain
2. **Synthesis** - Connect ideas across conversations and documents
3. **Capture** - Help formulate thoughts worth preserving in the brain
4. **Workflows** - Guide Eugene through processes (brainstorming, research, review)
5. **Analysis** - Process uploaded files, code, research papers

## Operating Principles

**Be Proactive:**
- Suggest connections to existing knowledge when spotted
- Recommend capturing important insights as notes
- Propose workflows when detecting decision points
- Ask clarifying questions to improve understanding

**Be Grounded:**
- Cite brain sources when referencing stored knowledge
- Distinguish between brain-retrieved facts and general knowledge
- Admit uncertainty rather than guessing
- When files are uploaded (marked "## Files Uploaded by User:"), analyze them directly—never suggest external tools

**Be Concise:**
- Default to focused, actionable responses
- Use bullet points for lists and clarity
- Expand depth when requested or contextually appropriate
- Keep citations brief (source file name)

**Conversation Flow:**
- Remember context from earlier in this conversation
- Reference past decisions and agreements made in this thread
- Build on previous exchanges rather than starting fresh each time

## Special Contexts

If Eugene mentions he's **starting a project**, help scope it and suggest creating a project note.
If Eugene is **researching**, offer to summarize findings for brain storage.
If Eugene is **debugging**, offer structured troubleshooting.
If Eugene **uploads a file**, treat it as primary context—analyze and discuss it directly.

You're not just answering questions—you're helping build and navigate a system of thought.""",
        )

        # Initialize performance monitoring
        self.performance_monitor = PerformanceMonitor(
            slow_threshold_seconds=config.get("slow_response_threshold", 30.0)
        )

        # Feature flags
        self.enable_file_attachments = config.get("enable_file_attachments", True)
        self.enable_performance_alerts = config.get("enable_performance_alerts", True)

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register Slack event handlers"""

        @self.app.event("message")
        async def handle_message(event, say, client):
            """Handle incoming DM messages"""

            # Ignore bot messages, but allow whitelisted test bots for E2E testing
            if event.get("subtype") == "bot_message":
                allowed_bot_ids = os.getenv("ALLOWED_TEST_BOT_IDS", "").split(",")
                bot_id = event.get("bot_id", "")
                # Filter out empty strings from split
                allowed_bot_ids = [b.strip() for b in allowed_bot_ids if b.strip()]
                if bot_id not in allowed_bot_ids or not bot_id:
                    return

            # Accept DMs and public channel messages (for E2E testing)
            channel_type = event.get("channel_type")
            if channel_type not in ["im", "public_channel"]:
                return

            user_id = event.get("user")
            user_message = event.get(
                "text", ""
            ).strip()  # Keep original message separate
            thread_ts = event.get("thread_ts", event.get("ts"))
            channel_id = event.get("channel")

            self.logger.debug(f"Message event keys: {list(event.keys())}")
            self.logger.debug(f"Message has 'files' key: {'files' in event}")

            # Handle file attachments if present
            file_content = ""
            if self.enable_file_attachments:
                attachments = detect_file_attachments(event)
                self.logger.info(f"File attachments detected: {len(attachments)}")
                for attachment in attachments:
                    try:
                        file_content += await self._process_file_attachment(
                            attachment, channel_id, user_id
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to process attachment {attachment['name']}: {e}"
                        )
                        # Continue - file processing failure shouldn't stop message handling

            # Combine text and file content for LLM
            has_attachments = bool(file_content)
            text = (
                f"{user_message}\n\n## Files Uploaded by User:\n{file_content}"
                if file_content
                else user_message
            )

            if not text:
                return

            working_ts = None
            try:
                # Send "working" indicator (customize based on attachment presence)
                working_text = (
                    "Ingesting attachment... 📎"
                    if file_content
                    else "Working on it... 🧠"
                )
                try:
                    working_msg = await say(text=working_text)
                    working_ts = working_msg.get("ts")
                    self.logger.debug(f"Sent working indicator: {working_ts}")
                except Exception as e:
                    self.logger.warning(f"Failed to send working indicator: {e}")

                # Process message (this is slow - LLM inference)
                response = await self._process_message(
                    user_id, text, thread_ts, user_message=user_message, has_attachments=has_attachments
                )

                # Delete working message if we successfully sent it
                if working_ts:
                    try:
                        await client.chat_delete(channel=channel_id, ts=working_ts)
                        self.logger.debug(f"Deleted working indicator: {working_ts}")
                    except Exception as e:
                        self.logger.warning(f"Failed to delete working indicator: {e}")
                        # Continue anyway - working message will still be visible but that's OK

                # Send real response (directly in DM, not in thread)
                await say(text=response)

            except Exception as e:
                error_msg = f"Sorry, I encountered an error: {str(e)}"
                self.logger.error(
                    f"Error processing message from {user_id}: {e}", exc_info=True
                )

                # Delete working message if we haven't already
                if working_ts:
                    try:
                        await client.chat_delete(channel=channel_id, ts=working_ts)
                    except Exception:
                        pass

                try:
                    await say(text=error_msg)
                except Exception:
                    pass

        @self.app.event("app_mention")
        async def handle_mention(event, say):
            """Handle @mentions (future: support channel conversations)"""
            await say("Hi! For now, please DM me directly for conversations.")

    async def _process_file_attachment(
        self, attachment: Dict, channel_id: str, user_id: str
    ) -> str:
        """
        Process a file attachment and extract text content.

        Args:
            attachment: File attachment info from detect_file_attachments()
            channel_id: Slack channel ID
            user_id: Slack user ID

        Returns:
            Extracted text content, or empty string on failure
        """
        file_name = attachment.get("name", "unknown")
        file_type = attachment.get("type", "")
        url = attachment.get("url_private_download", "")

        self.logger.info(
            f"Processing attachment: {file_name}, type: {file_type}, has_url: {bool(url)}"
        )

        if not url or not file_type:
            self.logger.warning(f"Missing URL or type for attachment {file_name}")
            return ""

        try:
            # Download file from Slack
            self.logger.info(f"Downloading {file_name} from Slack...")
            file_content = download_file_from_slack(url, token=self.bot_token)
            self.logger.info(f"Downloaded {file_name}, extracting text...")

            # Extract text content
            text = extract_text_content(file_content, file_type=file_type)

            self.logger.info(f"Extracted text from {file_name} ({len(text)} chars)")
            return f"**File: {file_name}**\n{text}\n"

        except (FileDownloadError, FileExtractionError, UnsupportedFileTypeError) as e:
            self.logger.warning(f"Error processing attachment {file_name}: {e}")
            return f"*Could not process file {file_name}: {str(e)}*\n"

    async def _process_message(
        self, user_id: str, text: str, thread_id: str, user_message: str = "", has_attachments: bool = False
    ) -> str:
        """
        Process incoming message and generate response

        Args:
            user_id: Slack user ID
            text: Message text (may include file attachment content)
            thread_id: Thread timestamp
            user_message: Original user message (without attachments), used for Khoj search
            has_attachments: Whether the message includes file attachments

        Returns:
            Response text
        """
        start_time = datetime.now()

        # Load conversation history
        history = await self.conversations.load_conversation(user_id, thread_id)

        # Check if summarization needed
        if (
            self.conversations.count_conversation_tokens(history)
            > self.max_context_tokens
        ):
            self.logger.info(
                f"Summarizing conversation for {user_id} (thread {thread_id})"
            )
            history = await self.conversations.summarize_if_needed(
                history, max_tokens=self.max_context_tokens
            )

        # Search brain for context (if enabled)
        # Skip Khoj search when files are attached - the file IS the context
        # Use original user message for Khoj search, not combined text with attachments
        context = ""
        khoj_query = user_message if user_message else text
        # Truncate query to reasonable length for Khoj (avoid URL too long errors)
        khoj_query = khoj_query[:500]

        if self.enable_khoj_search and len(khoj_query) > 10 and not has_attachments:
            try:
                search_results = await self.khoj.search(
                    query=khoj_query,
                    content_type="markdown",
                    limit=self.max_search_results,
                )

                if search_results:
                    context = "\n\n**Relevant context from your brain:**\n"
                    for i, result in enumerate(search_results, 1):
                        # SearchResult is a dataclass with attributes, not a dict
                        snippet = result.entry[:200] if hasattr(result, "entry") else ""
                        file_name = result.file if hasattr(result, "file") else ""
                        context += f"\n{i}. {snippet}...\n   (Source: {file_name})\n"

                    self.logger.info(
                        f"Found {len(search_results)} relevant brain entries"
                    )

            except Exception as e:
                self.logger.warning(f"Khoj search failed: {e}")
                # Continue without context

        # Build prompt
        messages = []

        # Add system prompt
        messages.append(Message(role="system", content=self.system_prompt))

        # Add conversation history
        for msg in history:
            messages.append(Message(role=msg["role"], content=msg["content"]))

        # Add current user message with optional context
        user_content = text
        if context:
            user_content = f"{context}\n\n**User message:** {text}"

        messages.append(Message(role="user", content=user_content))

        # Generate response using LLM
        try:
            response = await self.llm.chat(messages=messages, model=self.model)
        except Exception as e:
            self.logger.error(f"LLM generation failed: {e}")
            return "Sorry, my AI backend is temporarily unavailable. Please try again shortly."

        # Calculate latency
        latency = (datetime.now() - start_time).total_seconds()

        # Save conversation (with error handling to ensure response is still sent)
        try:
            await self.conversations.save_message(
                user_id=user_id, thread_id=thread_id, role="user", content=text
            )

            await self.conversations.save_message(
                user_id=user_id,
                thread_id=thread_id,
                role="assistant",
                content=response,
                metadata={
                    "model": self.model,
                    "latency": latency,
                    "context_used": bool(context),
                },
            )
        except Exception as e:
            self.logger.warning(f"Failed to save conversation for {user_id}: {e}")
            # Continue anyway - user still gets their response

        self.logger.info(
            f"Generated response for {user_id} in {latency:.2f}s "
            f"(history: {len(history)} msgs, context: {bool(context)})"
        )

        # Record performance metrics
        if self.enable_performance_alerts:
            try:
                self.performance_monitor.record_response_time(
                    request_id=f"{user_id}:{thread_id}",
                    duration_seconds=latency,
                    user_id=user_id,
                    channel_id=thread_id,
                )
            except Exception as e:
                self.logger.warning(f"Failed to record performance metric: {e}")

        return response

    async def run(self):
        """
        Main agent loop - starts Socket Mode handler (blocks indefinitely)
        """
        self.logger.info("Starting Slack agent with Socket Mode...")

        try:
            # Health check
            await self._health_check()

            # Start Socket Mode handler
            self.socket_handler = AsyncSocketModeHandler(self.app, self.app_token)

            self.logger.info("✅ Slack agent connected and ready")
            await self.notify("Slack Bot", "Slack agent started and connected")

            # This blocks forever, listening for events
            await self.socket_handler.start_async()

        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
            await self.notify("Slack Bot", "Slack agent shutting down")

        except Exception as e:
            self.logger.error(f"Fatal error in Slack agent: {e}", exc_info=True)
            await self.notify("Slack Bot Error", f"⚠️ Slack agent crashed: {e}")
            raise

    async def _health_check(self):
        """Check if all dependencies are available"""
        errors = []

        # Check Khoj
        try:
            await self.khoj.health_check()
            self.logger.info("✅ Khoj connection OK")
        except Exception as e:
            errors.append(f"Khoj unavailable: {e}")
            self.logger.warning(f"⚠️ Khoj unavailable: {e}")

        # Check Ollama
        try:
            await self.llm.health_check()
            self.logger.info("✅ Ollama connection OK")
        except Exception as e:
            errors.append(f"Ollama unavailable: {e}")
            self.logger.error(f"❌ Ollama unavailable: {e}")

        # Check brain folder
        brain_path = Path(self.brain.brain_path)
        if not brain_path.exists():
            errors.append(f"Brain folder not found: {brain_path}")
            self.logger.error(f"❌ Brain folder not found: {brain_path}")
        else:
            self.logger.info("✅ Brain folder OK")

        # Check Slack auth
        try:
            auth_test = await self.app.client.auth_test()
            bot_name = auth_test.get("user", "Unknown")
            self.logger.info(f"✅ Slack auth OK (bot: {bot_name})")
        except SlackApiError as e:
            errors.append(f"Slack auth failed: {e}")
            self.logger.error(f"❌ Slack auth failed: {e}")

        if errors:
            # Log all errors but only fatal if Ollama or Slack is down
            critical_errors = [e for e in errors if "Ollama" in e or "Slack" in e]
            if critical_errors:
                raise RuntimeError(f"Health check failed: {'; '.join(critical_errors)}")


# Test mode
if __name__ == "__main__":
    # Load environment from secrets.env if available
    secrets_file = Path(__file__).parent.parent / "secrets.env"
    if secrets_file.exists():
        print(f"Loading secrets from {secrets_file}")
        with open(secrets_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    # Parse: export KEY="value" or KEY=value
                    if line.startswith("export "):
                        line = line[7:]
                    key, value = line.split("=", 1)
                    value = value.strip('"').strip("'")
                    os.environ[key] = value

    # Test configuration
    config = {
        "khoj_url": os.getenv("KHOJ_URL", "http://192.168.1.195:42110"),
        "ollama_url": os.getenv("OLLAMA_URL", "http://192.168.1.58:11434"),
        "brain_folder": os.getenv("BRAIN_FOLDER", "/tmp/test_brain"),
        "model": "llama3.2",
        "max_context_tokens": 6000,
        "enable_khoj_search": True,
        "max_search_results": 3,
        "notification": {
            "enabled": False  # Disable for testing
        },
    }

    print("🚀 Starting Slack agent in test mode...")
    print(f"   Khoj: {config['khoj_url']}")
    print(f"   Ollama: {config['ollama_url']}")
    print(f"   Brain: {config['brain_folder']}")
    print("\nPress Ctrl+C to stop\n")

    agent = SlackAgent(config)

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n👋 Slack agent stopped")
