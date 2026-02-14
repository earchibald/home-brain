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
from typing import Dict, List, Optional
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
            llm_client=self.llm
        )
        
        # Configuration
        self.model = config.get("model", "llama3.2")
        self.max_context_tokens = config.get("max_context_tokens", 6000)
        self.enable_khoj_search = config.get("enable_khoj_search", True)
        self.max_search_results = config.get("max_search_results", 3)
        self.system_prompt = config.get(
            "system_prompt",
            """You are a helpful AI assistant with access to the user's semantic brain - a knowledge base of their notes, ideas, and past conversations.

When relevant, search the brain for context to provide informed, personalized responses. Always cite your sources when referencing specific information from the brain.

Be concise but thorough. If you don't know something, say so rather than making assumptions."""
        )
        
        # Register event handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register Slack event handlers"""
        
        @self.app.event("message")
        async def handle_message(event, say, client):
            """Handle incoming DM messages"""

            # Ignore bot messages and threaded replies to avoid loops
            if event.get("subtype") == "bot_message":
                return

            # Only respond to DMs (channel type = "im")
            channel_type = event.get("channel_type")
            if channel_type != "im":
                return

            user_id = event.get("user")
            text = event.get("text", "").strip()
            thread_ts = event.get("thread_ts", event.get("ts"))
            channel_id = event.get("channel")

            if not text:
                return

            working_ts = None
            try:
                # Send "working" indicator
                try:
                    working_msg = await say(text="Working on it... 🧠")
                    working_ts = working_msg.get("ts")
                    self.logger.debug(f"Sent working indicator: {working_ts}")
                except Exception as e:
                    self.logger.warning(f"Failed to send working indicator: {e}")

                # Process message (this is slow - LLM inference)
                response = await self._process_message(user_id, text, thread_ts)

                # Delete working message if we successfully sent it
                if working_ts:
                    try:
                        await client.chat_delete(
                            channel=channel_id,
                            ts=working_ts
                        )
                        self.logger.debug(f"Deleted working indicator: {working_ts}")
                    except Exception as e:
                        self.logger.warning(f"Failed to delete working indicator: {e}")
                        # Continue anyway - working message will still be visible but that's OK

                # Send real response (directly in DM, not in thread)
                await say(text=response)

            except Exception as e:
                error_msg = f"Sorry, I encountered an error: {str(e)}"
                self.logger.error(f"Error processing message from {user_id}: {e}", exc_info=True)

                # Delete working message if we haven't already
                if working_ts:
                    try:
                        await client.chat_delete(
                            channel=channel_id,
                            ts=working_ts
                        )
                    except:
                        pass

                try:
                    await say(text=error_msg)
                except:
                    pass
        
        @self.app.event("app_mention")
        async def handle_mention(event, say):
            """Handle @mentions (future: support channel conversations)"""
            await say("Hi! For now, please DM me directly for conversations.")
    
    async def _process_message(
        self,
        user_id: str,
        text: str,
        thread_id: str
    ) -> str:
        """
        Process incoming message and generate response
        
        Args:
            user_id: Slack user ID
            text: Message text
            thread_id: Thread timestamp
            
        Returns:
            Response text
        """
        start_time = datetime.now()
        
        # Load conversation history
        history = await self.conversations.load_conversation(user_id, thread_id)
        
        # Check if summarization needed
        if self.conversations.count_conversation_tokens(history) > self.max_context_tokens:
            self.logger.info(f"Summarizing conversation for {user_id} (thread {thread_id})")
            history = await self.conversations.summarize_if_needed(
                history,
                max_tokens=self.max_context_tokens
            )
        
        # Search brain for context (if enabled)
        context = ""
        if self.enable_khoj_search and len(text) > 10:
            try:
                search_results = await self.khoj.search(
                    query=text,
                    content_type="markdown",
                    limit=self.max_search_results
                )
                
                if search_results:
                    context = "\n\n**Relevant context from your brain:**\n"
                    for i, result in enumerate(search_results, 1):
                        snippet = result.get("snippet", "")[:200]
                        file_name = result.get("file", "")
                        context += f"\n{i}. {snippet}...\n   (Source: {file_name})\n"
                    
                    self.logger.info(f"Found {len(search_results)} relevant brain entries")
                    
            except Exception as e:
                self.logger.warning(f"Khoj search failed: {e}")
                # Continue without context
        
        # Build prompt
        messages = []
        
        # Add system prompt
        messages.append(Message(
            role="system",
            content=self.system_prompt
        ))
        
        # Add conversation history
        for msg in history:
            messages.append(Message(
                role=msg["role"],
                content=msg["content"]
            ))
        
        # Add current user message with optional context
        user_content = text
        if context:
            user_content = f"{context}\n\n**User message:** {text}"
        
        messages.append(Message(
            role="user",
            content=user_content
        ))
        
        # Generate response using LLM
        try:
            response = await self.llm.chat(
                messages=messages,
                model=self.model
            )
        except Exception as e:
            self.logger.error(f"LLM generation failed: {e}")
            return "Sorry, my AI backend is temporarily unavailable. Please try again shortly."
        
        # Calculate latency
        latency = (datetime.now() - start_time).total_seconds()
        
        # Save conversation
        await self.conversations.save_message(
            user_id=user_id,
            thread_id=thread_id,
            role="user",
            content=text
        )
        
        await self.conversations.save_message(
            user_id=user_id,
            thread_id=thread_id,
            role="assistant",
            content=response,
            metadata={
                "model": self.model,
                "latency": latency,
                "context_used": bool(context)
            }
        )
        
        self.logger.info(
            f"Generated response for {user_id} in {latency:.2f}s "
            f"(history: {len(history)} msgs, context: {bool(context)})"
        )
        
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
        }
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
