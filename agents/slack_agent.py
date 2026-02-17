"""
Slack Agent - Multi-turn conversation bot with brain context

Connects to Slack via Socket Mode, handles DM messages with:
- Per-user conversation history
- Semantic brain search
- Ollama LLM inference
- Automatic summarization for long conversations
"""

import os
import re
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
from clients.semantic_search_client import SemanticSearchClient
from clients.llm_client import OllamaClient, Message
from clients.brain_io import BrainIO
from clients.conversation_manager import ConversationManager
from clients.cxdb_client import CxdbClient
from clients.vaultwarden_client import get_secret
from clients.web_search_client import WebSearchClient

# Import new slack_bot modules for enhanced features
from slack_bot.message_processor import detect_file_attachments
from slack_bot.file_handler import download_file_from_slack, extract_text_content
from slack_bot.performance_monitor import PerformanceMonitor
from slack_bot.model_selector import build_model_selector_ui, apply_model_selection
from slack_bot.index_manager import (
    build_index_dashboard,
    build_document_browser,
    build_delete_confirmation,
    build_gate_setup,
    build_loading_view,
    build_status_view,
    parse_gate_config_text,
    PAGE_SIZE,
    ACTION_BROWSE,
    ACTION_PAGE_NEXT,
    ACTION_PAGE_PREV,
    ACTION_DOC_IGNORE,
    ACTION_DOC_DELETE,
    ACTION_FILTER_FOLDER,
    ACTION_SHOW_SETUP,
    ACTION_SETUP_SUBMIT,
    ACTION_REINDEX,
    ACTION_BACK_DASHBOARD,
    ACTION_CONFIRM_DELETE,
    ACTION_CANCEL_DELETE,
    CALLBACK_GATE_SETUP,
    CALLBACK_CONFIRM_DELETE,
)
from slack_bot.exceptions import (
    FileDownloadError,
    UnsupportedFileTypeError,
    FileExtractionError,
)
from slack_bot.file_uploader import (
    download_file_from_slack_async,
    build_save_to_brain_prompt,
    build_save_note_prompt,
    build_save_note_folder_blocks,
    build_folder_selection_blocks,
    build_upload_result_blocks,
    parse_file_value,
    COMMON_DIRECTORIES,
)

# Import model switching components
from services.model_manager import ModelManager
from providers.gemini_adapter import GeminiProvider, QuotaExhaustedError

# Tool architecture
from slack_bot.tools.base_tool import BaseTool, UserScopedTool, ToolResult
from slack_bot.tools.tool_registry import ToolRegistry
from slack_bot.tools.tool_executor import ToolExecutor
from slack_bot.tools.tool_state import ToolStateStore
from slack_bot.tools.builtin.web_search_tool import WebSearchTool
from slack_bot.tools.builtin.brain_search_tool import BrainSearchTool
from slack_bot.tools.builtin.facts_tool import (
    FactsTool,
    FactsStore,
    message_references_personal_context,
)
from slack_bot.tools.builtin.facts_check_skill import FactsCheckSkill
from slack_bot.mission_manager import MissionManager
from slack_bot.hooks.source_tracker import SourceTracker, set_tracker, clear_tracker
from slack_bot.hooks.citation_hook import citation_hook
from slack_bot.hooks.intent_classifier import intent_classifier_hook
from slack_bot.tools.mcp.mcp_manager import MCPManager
from slack_bot.tools_ui import build_tools_ui, parse_tool_toggle_action
from slack_bot.facts_ui import build_facts_ui, build_fact_edit_view


# ==================================================================
# API Key Storage (secure local file)
# ==================================================================

class ApiKeyStore:
    """
    Secure storage for user API keys.
    
    Stores keys in a JSON file with restricted permissions.
    Keys are stored per-user (Slack user ID).
    """
    
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or os.path.expanduser("~/.brain-api-keys.json")
        self._ensure_file()
    
    def _ensure_file(self):
        """Create storage file with secure permissions if it doesn't exist."""
        import json
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, 'w') as f:
                json.dump({}, f)
            os.chmod(self.storage_path, 0o600)
    
    def _load(self) -> dict:
        import json
        try:
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save(self, data: dict):
        import json
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
        os.chmod(self.storage_path, 0o600)
    
    def set_key(self, user_id: str, provider: str, api_key: str):
        """Store an API key for a user."""
        data = self._load()
        if user_id not in data:
            data[user_id] = {}
        data[user_id][provider] = api_key
        self._save(data)
    
    def get_key(self, user_id: str, provider: str) -> str:
        """Get an API key for a user. Returns None if not set."""
        data = self._load()
        return data.get(user_id, {}).get(provider)
    
    def delete_key(self, user_id: str, provider: str):
        """Delete an API key for a user."""
        data = self._load()
        if user_id in data and provider in data[user_id]:
            del data[user_id][provider]
            self._save(data)
    
    def mask_key(self, api_key: str) -> str:
        """Return masked version of key for display."""
        if not api_key:
            return "(not set)"
        if len(api_key) <= 8:
            return "****"
        return f"{api_key[:4]}...{api_key[-4:]}"


class SlackAgent(Agent):
    """Slack conversation bot with brain context and multi-turn memory"""

    def __init__(self, config: Dict):
        super().__init__("slack_agent", config)

        # Slack setup - load from Vaultwarden or environment variables
        try:
            self.bot_token = get_secret("SLACK_BOT_TOKEN")
            self.app_token = get_secret("SLACK_APP_TOKEN")
        except Exception as e:
            raise ValueError(
                f"Failed to load Slack tokens: {e}\n"
                "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN as environment variables,\n"
                "or add them to Vaultwarden."
            )

        if not self.bot_token or not self.app_token:
            raise ValueError(
                "Missing Slack tokens in Vaultwarden. Add SLACK_BOT_TOKEN and SLACK_APP_TOKEN."
            )

        # Initialize Slack app
        self.app = AsyncApp(token=self.bot_token)
        self.socket_handler = None

        # Initialize clients
        self.search = SemanticSearchClient(
            base_url=config.get("search_url", "http://nuc-1.local:9514")
        )
        self.llm = OllamaClient(
            base_url=config.get("ollama_url", "http://m1-mini.local:11434")
        )
        self.brain = BrainIO(
            brain_path=config.get("brain_path", "/home/earchibald/brain")
        )

        # Initialize cxdb client (optional — bot works without it)
        self.cxdb = CxdbClient(
            base_url=config.get("cxdb_url", "http://nuc-1.local:9010")
        )

        # Initialize conversation manager with cxdb for dual-write
        self.conversations = ConversationManager(
            brain_path=config.get("brain_path", "/home/earchibald/brain"),
            llm_client=self.llm,
            cxdb_client=self.cxdb,
        )

        # Configuration
        self.model = config.get("model", "llama3.2")
        self.max_context_tokens = config.get("max_context_tokens", 6000)
        # Reserve tokens for context injection (cxdb + search results)
        self.context_budget = config.get("context_budget", 2000)
        self.summarization_threshold = config.get(
            "summarization_threshold",
            max(self.max_context_tokens - self.context_budget, 2000),
        )
        self.enable_search = config.get("enable_search", True)
        self.max_search_results = config.get("max_search_results", 3)
        self.min_relevance_score = config.get("min_relevance_score", 0.7)
        
        # Web search configuration
        self.enable_web_search = config.get("enable_web_search", True)
        self.web_search_provider = config.get("web_search_provider", "duckduckgo")
        self.web_context_budget = config.get("web_context_budget", 1500)
        self.web_search = WebSearchClient(
            provider=self.web_search_provider,
            api_key=config.get("tavily_api_key"),
            max_results=3,
        )
        
        self.system_prompt = config.get(
            "system_prompt",
            """You are Brain Assistant, Eugene's personal AI companion. Your default name is "Brain Assistant" but Eugene may give you a nickname — when he does, adopt it as YOUR name (e.g., "I'd like to call you Archie" means YOU are now Archie, not the user).

## Identity — THIS IS CRITICAL

There are exactly two entities in this conversation:
- **The human** = Eugene (the user typing messages)
- **The AI assistant** = You (Brain Assistant, or whatever nickname Eugene gives you)

When Eugene says "I'll call you Archie", that means:
- YOUR name is now Archie (you are the AI)
- Eugene's name is still Eugene (he is the human)
- CORRECT response: "Got it, I'm Archie! How can I help, Eugene?"
- WRONG response: "Nice to meet you, Eugene (aka Archie)" ← NO, Eugene is NOT Archie

When Eugene says "My name is Eugene":
- The HUMAN's name is Eugene
- YOUR name is whatever it was before

Never confuse who is who. "You" in Eugene's messages = the AI. "I/me" in Eugene's messages = Eugene.

## Your Two Knowledge Sources

1. **Conversation Memory** (PRIMARY) — What Eugene told you in this conversation. Always prioritize this. If Eugene says his project is called "Project Nova", remember it — even if your notes mention different projects.

2. **Brain (Knowledge Base)** (SECONDARY) — Eugene's notes, journals, documents. Use to enrich answers, but never override what Eugene just said.

## Your Capabilities

You have these real capabilities (powered by tools that run automatically):
- **Brain search** — I can search Eugene's personal knowledge base (markdown notes, journals, documents) for relevant context
- **Web search** — I can search the internet for current information, facts, news, and real-world data
- **Conversation memory** — I remember everything said in this conversation, plus I can recall relevant past conversations
- **File analysis** — When Eugene uploads a file, I can read and analyze its contents
- **Save to brain** — I can help save important information to Eugene's knowledge base

Slash commands Eugene can use: `/model` (switch AI models), `/apikey` (manage API keys), `/reset` (clear conversation), `/index` (manage knowledge base)

IMPORTANT: Only claim you performed an action if the [Actions taken] note in context confirms it. If web_search=no, do NOT say "I searched the web" — instead say "I don't have web search results for this" or just answer from your knowledge.

## Core Behaviors

**Conversation First:**
- Build on prior exchanges, don't restart each message
- If you know something from conversation, say so confidently
- Never pretend to forget what was just discussed

**Knowledge Base Second:**
- Use brain context to add depth, cite sources briefly (filename only)
- Say "From your notes..." vs "From our chat..."
- Skip brain context if it's not genuinely relevant

**Style:**
- Concise, direct, use bullets for lists
- Warm but not sycophantic
- Ask clarifying questions when genuinely uncertain
- If Eugene uploads a file, analyze it directly
- Do NOT append "Notes so far:" to every message — only provide session summaries when Eugene explicitly asks for them""",
        )

        # Initialize performance monitoring
        self.performance_monitor = PerformanceMonitor(
            slow_threshold_seconds=config.get("slow_response_threshold", 30.0)
        )

        # Initialize model manager for dynamic provider switching
        self.model_manager = ModelManager()
        self.enable_model_switching = config.get("enable_model_switching", False)
        self.ollama_url = config.get("ollama_url")  # Store for /model command
        if self.enable_model_switching:
            # Pass configured Ollama URL for discovery
            self.model_manager.discover_available_sources(ollama_url=self.ollama_url)
            self.logger.info(
                f"Model switching enabled. Available providers: {list(self.model_manager.providers.keys())}"
            )
        
        # API key store for user-provided keys (Gemini, etc.)
        self.api_key_store = ApiKeyStore()

        # ---- Tool architecture (Phase 1a/1b) ----
        self.tool_state_store = ToolStateStore()
        self.tool_registry = ToolRegistry(self.tool_state_store)
        self.tool_executor = ToolExecutor(self.tool_registry)

        # Register built-in tools
        self.tool_registry.register(WebSearchTool(self.web_search))
        self.tool_registry.register(BrainSearchTool(self.search, self.min_relevance_score))
        self.tool_registry.register(FactsTool())

        # Register skills (hidden from /tools UI, LLM-callable)
        self.tool_registry.register(FactsCheckSkill())

        # Mission principles (hot-reloads from ~/.brain-mission.md)
        self.mission_manager = MissionManager()

        # MCP servers (Phase 5 — stdio transport, Phase 6 — SSE transport)
        self.mcp_manager = MCPManager(
            registry=self.tool_registry,
            config_path=config.get("mcp_config_path", "config/mcp_servers.json"),
        )

        # Agent hooks (Phase 7) — pre/post processing extensibility
        self.agent_hooks = {
            "pre_process": [],    # async (event: dict, agent: SlackAgent) → None
            "post_process": [],   # async (response: str, event: dict, agent: SlackAgent) → str|None
        }
        
        # Register built-in hooks
        self.register_hook("pre_process", intent_classifier_hook)
        self.register_hook("post_process", citation_hook)

        # Feature flags
        self.enable_file_attachments = config.get("enable_file_attachments", True)
        self.enable_performance_alerts = config.get("enable_performance_alerts", True)

        # Register event handlers
        self._register_handlers()

    def _is_current_model_available(self) -> bool:
        """
        Check if the currently configured model is available.

        Returns:
            bool: True if model is available, False otherwise
        """
        # If model switching is enabled, check the model_manager's selection
        if self.enable_model_switching and self.model_manager:
            config = self.model_manager.get_current_config()
            # If user has already selected a model via /model, it's considered available
            if config.get("provider_id"):
                return True
            # If no explicit selection made, allow fallback to default Ollama
            # Don't block messages just because /model wasn't used
            return True

        if not self.model:
            return True  # No specific model configured, use default

        # Note: Don't try to call self.llm.list_models() here as it's async
        # and we'd need to await it. Just trust the config is valid.
        return True

    async def _generate_with_provider(
        self,
        messages: list,
        user_id: str,
        say_func=None,
    ) -> tuple[str, str, bool]:
        """
        Generate LLM response using the appropriate provider.
        
        Checks if user has selected a cloud provider (e.g., Gemini) and uses it
        if configured. Falls back to Ollama if cloud provider fails (e.g., quota).
        
        Args:
            messages: List of Message objects for the conversation
            user_id: Slack user ID (for API key lookup)
            say_func: Optional say function to notify user of fallback
            
        Returns:
            tuple of (response_text, model_used, quota_exhausted)
        """
        # Check if user has a Gemini key and Gemini is selected
        gemini_key = self.api_key_store.get_key(user_id, "gemini")
        config = self.model_manager.get_current_config() if self.enable_model_switching else {}
        
        provider_id = config.get("provider_id")
        model_name = config.get("model_name")
        
        # If Gemini is selected and user has a key, try Gemini first
        if provider_id == "gemini" and gemini_key:
            try:
                gemini = self.model_manager.providers.get("gemini")
                if gemini:
                    # Ensure key is set
                    gemini.set_api_key(gemini_key)
                    
                    # Extract system prompt from messages
                    system_prompt = None
                    user_messages = []
                    for msg in messages:
                        if msg.role == "system":
                            system_prompt = (system_prompt or "") + "\n" + msg.content
                        else:
                            user_messages.append(msg)
                    
                    # Build conversation prompt
                    conversation_parts = []
                    for msg in user_messages:
                        role_label = "User" if msg.role == "user" else "Assistant"
                        conversation_parts.append(f"{role_label}: {msg.content}")
                    
                    prompt = "\n\n".join(conversation_parts)
                    
                    response = gemini.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        model_id=model_name,
                    )
                    
                    self.logger.info(f"Generated response with Gemini ({model_name})")
                    return response, f"gemini/{model_name}", False
                    
            except QuotaExhaustedError as e:
                self.logger.warning(f"Gemini quota exhausted for user {user_id}: {e}")
                
                # Notify user and fall back to Ollama
                if say_func:
                    await say_func(
                        text="⚠️ *Gemini daily quota exhausted* — falling back to Ollama. "
                             "Use `/model` to switch providers, or try Gemini again tomorrow.",
                        # Don't add to thread - send as DM
                    )
                
                # Fall through to Ollama below
                
            except Exception as e:
                self.logger.error(f"Gemini generation failed: {e}")
                # Fall through to Ollama
        
        # Default: Use Ollama
        try:
            response = await self.llm.chat(messages=messages, model=self.model)
            return response, f"ollama/{self.model}", False
        except Exception as e:
            self.logger.error(f"Ollama generation failed: {e}")
            raise

    def register_hook(self, hook_type: str, fn) -> None:
        """Register an agent hook function.

        Args:
            hook_type: "pre_process" or "post_process"
            fn: Async callable. pre_process receives (event, agent).
                post_process receives (response, event, agent) and may return
                a modified response string (or None to keep original).

        Raises:
            ValueError: If hook_type is invalid
        """
        if hook_type not in self.agent_hooks:
            raise ValueError(f"Invalid hook type: {hook_type}. Must be one of {list(self.agent_hooks.keys())}")
        self.agent_hooks[hook_type].append(fn)
        self.logger.info(f"Registered {hook_type} hook: {getattr(fn, '__name__', str(fn))}")

    async def _run_pre_process_hooks(self, event: dict) -> None:
        """Run all pre_process hooks. Errors are logged, never surfaced."""
        for hook in self.agent_hooks.get("pre_process", []):
            try:
                await hook(event, self)
            except Exception as e:
                self.logger.error(f"Pre-process hook error ({getattr(hook, '__name__', '?')}): {e}")

    async def _run_post_process_hooks(self, response: str, event: dict) -> str:
        """Run all post_process hooks. Hooks may return modified response.

        Args:
            response: Generated response text
            event: Original event dict

        Returns:
            Possibly modified response text
        """
        for hook in self.agent_hooks.get("post_process", []):
            try:
                result = await hook(response, event, self)
                if result is not None and isinstance(result, str):
                    response = result
            except Exception as e:
                self.logger.error(f"Post-process hook error ({getattr(hook, '__name__', '?')}): {e}")
        return response

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
            channel_id = event.get("channel")

            # Conversation key: For DMs, use channel_id so ALL messages
            # between this user and the bot share ONE persistent conversation.
            # For threaded messages, use thread_ts so threads are separate.
            # Previously this used event["ts"] (unique per message), which
            # meant every DM created a new conversation — zero memory.
            if channel_type == "im":
                thread_ts = event.get("thread_ts") or channel_id
            else:
                thread_ts = event.get("thread_ts", event.get("ts"))

            self.logger.info(
                f"Conversation key: channel_type={channel_type}, "
                f"event.thread_ts={event.get('thread_ts')}, "
                f"channel_id={channel_id}, resolved thread_ts={thread_ts}"
            )

            self.logger.debug(f"Message event keys: {list(event.keys())}")
            self.logger.debug(f"Message has 'files' key: {'files' in event}")

            # Handle file attachments if present
            file_attachments_for_save = []  # Track files for "Save to Brain" button
            if self.enable_file_attachments:
                attachments = detect_file_attachments(event)
                self.logger.info(f"File attachments detected: {len(attachments)}")
                for attachment in attachments:
                    # Track for save button (don't process content yet)
                    file_attachments_for_save.append({
                        "id": attachment.get("id", ""),
                        "name": attachment.get("name", "unknown"),
                        "size": attachment.get("size", 0),
                        "url_private_download": attachment.get("url_private_download", ""),
                    })

            # If files were shared with no/minimal text, offer to save immediately (skip LLM)
            # Check for truly empty message or just Slack's auto-generated upload text
            is_file_only = (
                file_attachments_for_save and 
                (not user_message or len(user_message) < 10)  # Empty or very short (likely auto-generated)
            )
            
            self.logger.info(f"user_message='{user_message}' (len={len(user_message)}), file_only={is_file_only}")
            
            if is_file_only:
                self.logger.info(f"File-only message, offering save prompt for {len(file_attachments_for_save)} files")
                save_blocks = build_save_to_brain_prompt(file_attachments_for_save)
                if save_blocks:
                    await say(blocks=save_blocks, text="Save files to brain?")
                return  # Don't process through LLM

            # If no text message and no files, nothing to do
            if not user_message.strip():
                return

            # Check if current model is available, prompt selection if not
            if self.enable_model_switching and not self._is_current_model_available():
                self.logger.warning(f"Configured model not available, prompting user {user_id} to select model")
                await say(
                    text="⚠️ Your preferred model isn't available. Please select a model:",
                    blocks=build_model_selector_ui(self.model_manager),
                    response_type="ephemeral"
                )
                return

            # If there are files WITH a text message, process file content for LLM context
            file_content = ""
            if file_attachments_for_save:
                self.logger.info(f"Processing {len(file_attachments_for_save)} file(s) for LLM context")
                for attachment in file_attachments_for_save:
                    try:
                        # Re-fetch full attachment info from event
                        full_attachment = next(
                            (a for a in detect_file_attachments(event) if a.get("id") == attachment["id"]),
                            attachment
                        )
                        file_content += await self._process_file_attachment(
                            full_attachment, channel_id, user_id
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to process attachment {attachment['name']}: {e}")

            # Combine text and file content for LLM
            has_attachments = bool(file_content)
            text = (
                f"{user_message}\n\n## Files Uploaded by User:\n{file_content}"
                if file_content
                else user_message
            )

            working_ts = None
            try:
                # Send "working" indicator (customize based on attachment presence)
                working_text = (
                    "Analyzing attachment... 📎"
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

                # If files were shared with text, also offer to save them
                if file_attachments_for_save:
                    save_blocks = build_save_to_brain_prompt(file_attachments_for_save)
                    if save_blocks:
                        await say(blocks=save_blocks, text="Save files to brain?")

                # If user shared important info, suggest saving as a note
                if (
                    not file_attachments_for_save
                    and self._should_suggest_save(user_message)
                ):
                    note_blocks = build_save_note_prompt(user_message)
                    if note_blocks:
                        await say(
                            blocks=note_blocks,
                            text="Save this to your brain?",
                        )

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

        def _load_user_gemini_key(self_ref, user_id: str) -> bool:
            """Load user's Gemini API key into the provider. Returns True if key exists."""
            gemini_key = self_ref.api_key_store.get_key(user_id, "gemini")
            if gemini_key and "gemini" in self_ref.model_manager.providers:
                self_ref.model_manager.providers["gemini"].set_api_key(gemini_key)
                return True
            return False

        @self.app.command("/model")
        async def handle_model_command(ack, respond, command):
            """Handle /model command for dynamic model switching"""
            await ack()

            if not self.enable_model_switching:
                await respond(
                    text="⚠️ Model switching is not enabled in this bot configuration.",
                    response_type="ephemeral",
                )
                return

            try:
                user_id = command["user_id"]

                # Refresh provider discovery with configured Ollama URL
                self.model_manager.discover_available_sources(ollama_url=self.ollama_url)

                # Load user's Gemini API key into provider
                gemini_configured = _load_user_gemini_key(self, user_id)

                # Build UI (no provider pre-selected on initial load)
                blocks = build_model_selector_ui(
                    self.model_manager,
                    gemini_configured=gemini_configured,
                )

                await respond(
                    text="Model Selection",
                    blocks=blocks,
                    response_type="ephemeral",
                )
                self.logger.info(f"User {user_id} opened /model UI (gemini_configured={gemini_configured})")

            except Exception as e:
                self.logger.error(f"Error handling /model command: {e}", exc_info=True)
                await respond(
                    text=f"⚠️ Error loading model selector: {str(e)}",
                    response_type="ephemeral",
                )

        @self.app.action("select_provider")
        async def handle_provider_selection(ack, body, action, respond):
            """Handle provider selection - dynamically rebuild model list for chosen provider."""
            await ack()

            if not self.enable_model_switching:
                return

            try:
                selected_provider_id = action["selected_option"]["value"]
                user_id = body["user"]["id"]

                # Load user's Gemini API key
                gemini_configured = _load_user_gemini_key(self, user_id)

                # Rebuild UI with only the selected provider's models
                blocks = build_model_selector_ui(
                    self.model_manager,
                    selected_provider_id=selected_provider_id,
                    gemini_configured=gemini_configured,
                )

                await respond(
                    text="Model Selection",
                    blocks=blocks,
                    response_type="ephemeral",
                    replace_original=True,
                )
                self.logger.info(
                    f"User {user_id} selected provider: {selected_provider_id} "
                    f"(gemini_configured={gemini_configured})"
                )

            except Exception as e:
                self.logger.error(f"Error handling provider selection: {e}", exc_info=True)
                await respond(
                    text=f"⚠️ Error: {str(e)}",
                    response_type="ephemeral",
                    replace_original=False,
                )

        @self.app.action("select_model")
        async def handle_model_selection(ack, action, respond):
            """Handle model selection from dropdown"""
            await ack()

            if not self.enable_model_switching:
                return

            try:
                # Parse selection value (format: "provider_id:model_name")
                selected_value = action["selected_option"]["value"]
                provider_id, model_name = selected_value.split(":", 1)

                # Apply selection
                result = apply_model_selection(self.model_manager, provider_id, model_name)

                if result["success"]:
                    # Get provider name for clearer message
                    provider_name = self.model_manager.providers.get(provider_id, {}).name if hasattr(self.model_manager.providers.get(provider_id), 'name') else provider_id

                    await respond(
                        text=f"✅ **Selection saved:** {provider_name} - `{model_name}`\n_Note: Phase 1 - Selection saved but not yet used for inference_",
                        response_type="ephemeral",
                        replace_original=False,
                    )
                    self.logger.info(f"Model switched to {provider_id}:{model_name}")
                else:
                    await respond(
                        text=f"⚠️ {result.get('error', 'Failed to switch model')}",
                        response_type="ephemeral",
                        replace_original=False,
                    )

            except Exception as e:
                self.logger.error(f"Error handling model selection: {e}", exc_info=True)
                await respond(
                    text=f"⚠️ Error: {str(e)}",
                    response_type="ephemeral",
                    replace_original=False,
                )

        # ==================================================================
        # /apikey command - Manage API keys for cloud providers
        # ==================================================================

        @self.app.command("/apikey")
        async def handle_apikey_command(ack, command, client):
            """Handle /apikey command - open modal to manage API keys."""
            await ack()

            user_id = command["user_id"]
            trigger_id = command["trigger_id"]

            # Get current key status
            gemini_key = self.api_key_store.get_key(user_id, "gemini")
            gemini_masked = self.api_key_store.mask_key(gemini_key) if gemini_key else "(not set)"

            # Build modal
            modal = {
                "type": "modal",
                "callback_id": "apikey_submit",
                "title": {"type": "plain_text", "text": "🔑 API Keys"},
                "submit": {"type": "plain_text", "text": "Save"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Configure API keys for cloud AI providers*\n\nKeys are stored securely and used only by you."
                        }
                    },
                    {"type": "divider"},
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Google Gemini*\nCurrent: `{gemini_masked}`\n_Get a key at: https://aistudio.google.com/apikey_"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "gemini_key_block",
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "gemini_key_input",
                            "placeholder": {"type": "plain_text", "text": "AIza..."},
                        },
                        "label": {"type": "plain_text", "text": "New Gemini API Key"},
                        "hint": {"type": "plain_text", "text": "Leave blank to keep current key"}
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "🗑️ Delete Gemini Key"},
                                "action_id": "delete_gemini_key",
                                "style": "danger",
                                "confirm": {
                                    "title": {"type": "plain_text", "text": "Delete API Key?"},
                                    "text": {"type": "plain_text", "text": "This will remove your Gemini API key."},
                                    "confirm": {"type": "plain_text", "text": "Delete"},
                                    "deny": {"type": "plain_text", "text": "Cancel"}
                                }
                            }
                        ]
                    },
                    {"type": "divider"},
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "💡 After setting, use `/model` to select Gemini models.\nGemini has a daily quota — if exhausted, switch models."
                            }
                        ]
                    }
                ]
            }

            await client.views_open(trigger_id=trigger_id, view=modal)
            self.logger.info(f"User {user_id} opened /apikey modal")

        @self.app.view("apikey_submit")
        async def handle_apikey_submit(ack, body, client, view):
            """Handle API key modal submission."""
            await ack()

            user_id = body["user"]["id"]
            values = view["state"]["values"]

            # Extract Gemini key
            gemini_key = values.get("gemini_key_block", {}).get("gemini_key_input", {}).get("value")

            if gemini_key:
                # Store the new key
                self.api_key_store.set_key(user_id, "gemini", gemini_key.strip())

                # Update the model manager's Gemini provider if it exists
                if "gemini" in self.model_manager.providers:
                    gemini_provider = self.model_manager.providers["gemini"]
                    gemini_provider.set_api_key(gemini_key.strip())

                self.logger.info(f"User {user_id} updated Gemini API key")

                # Notify user
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"✅ Gemini API key saved! Use `/model` to select a Gemini model."
                )
            else:
                # User didn't change the key, that's okay
                pass

        @self.app.action("delete_gemini_key")
        async def handle_delete_gemini_key(ack, body, client):
            """Handle Gemini key deletion."""
            await ack()

            user_id = body["user"]["id"]
            self.api_key_store.delete_key(user_id, "gemini")
            self.logger.info(f"User {user_id} deleted Gemini API key")

            # Notify user
            await client.chat_postMessage(
                channel=user_id,
                text="🗑️ Your Gemini API key has been deleted."
            )

        # ==================================================================
        # /reset command - Delete conversation history (triple confirmation)
        # ==================================================================

        @self.app.command("/reset")
        async def handle_reset_command(ack, command, respond):
            """Handle /reset command - nuke conversation history with triple confirmation."""
            await ack()

            user_id = command["user_id"]
            channel_id = command["channel_id"]

            await respond(
                text="⚠️ *Reset Conversation Memory*",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "⚠️ *Warning: This will delete ALL conversation history in this DM.*\n\n"
                                "This includes:\n"
                                "• All past messages and responses\n"
                                "• Conversation context and memory\n"
                                "• Any ongoing discussion threads\n\n"
                                "*This action CANNOT be undone.*"
                            ),
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Yes, delete history"},
                                "style": "danger",
                                "value": f"{user_id}:{channel_id}",
                                "action_id": "reset_confirm_1",
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Cancel"},
                                "action_id": "reset_cancel",
                            },
                        ],
                    },
                ],
                response_type="ephemeral",
            )

        @self.app.action("reset_confirm_1")
        async def handle_reset_confirm_1(ack, action, respond):
            """First confirmation - show stronger warning."""
            await ack()

            user_id, channel_id = action["value"].split(":")

            await respond(
                text="⚠️ *Second Confirmation Required*",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "🚨 *Are you absolutely sure?*\n\n"
                                "Once deleted, you will lose:\n"
                                "• All context about previous conversations\n"
                                "• Any information I've learned about you\n"
                                "• The ability to reference past discussions\n\n"
                                "The conversation will restart from scratch.\n\n"
                                "*Still want to proceed?*"
                            ),
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Confirm deletion"},
                                "style": "danger",
                                "value": f"{user_id}:{channel_id}",
                                "action_id": "reset_confirm_2",
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Cancel"},
                                "action_id": "reset_cancel",
                            },
                        ],
                    },
                ],
                response_type="ephemeral",
                replace_original=True,
            )

        @self.app.action("reset_confirm_2")
        async def handle_reset_confirm_2(ack, action, respond):
            """Second confirmation - final warning before deletion."""
            await ack()

            user_id, channel_id = action["value"].split(":")

            await respond(
                text="🚨 *FINAL WARNING*",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "🚨 *LAST CHANCE TO CANCEL*\n\n"
                                "This is your final warning. Clicking 'DELETE' below will:\n\n"
                                "❌ Permanently erase all conversation history\n"
                                "❌ Remove all context and memory\n"
                                "❌ Cannot be recovered or undone\n\n"
                                "**This is irreversible.**\n\n"
                                "Only proceed if you are 100% certain."
                            ),
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "DELETE (cannot be undone)"},
                                "style": "danger",
                                "value": f"{user_id}:{channel_id}",
                                "action_id": "reset_confirm_3",
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Cancel"},
                                "action_id": "reset_cancel",
                            },
                        ],
                    },
                ],
                response_type="ephemeral",
                replace_original=True,
            )

        @self.app.action("reset_confirm_3")
        async def handle_reset_confirm_3(ack, action, respond):
            """Third confirmation - actually delete the conversation."""
            await ack()

            user_id, channel_id = action["value"].split(":")

            try:
                # Delete the conversation
                deleted = await self.conversations.delete_conversation(user_id, channel_id)

                if deleted:
                    await respond(
                        text="✅ *Conversation history deleted*",
                        blocks=[
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": (
                                        "✅ **Conversation history has been deleted.**\n\n"
                                        "All memory and context has been cleared.\n"
                                        "Our next conversation will start fresh.\n\n"
                                        "_You can continue chatting normally now._"
                                    ),
                                },
                            }
                        ],
                        response_type="ephemeral",
                        replace_original=True,
                    )
                    self.logger.info(f"User {user_id} deleted conversation in {channel_id}")
                else:
                    await respond(
                        text="ℹ️ No conversation history found to delete.",
                        response_type="ephemeral",
                        replace_original=True,
                    )

            except Exception as e:
                self.logger.error(f"Error deleting conversation: {e}", exc_info=True)
                await respond(
                    text=f"⚠️ Error deleting conversation: {str(e)}",
                    response_type="ephemeral",
                    replace_original=True,
                )

        @self.app.action("reset_cancel")
        async def handle_reset_cancel(ack, respond):
            """Handle cancellation of reset."""
            await ack()
            await respond(
                text="✅ Cancelled - conversation history preserved.",
                response_type="ephemeral",
                replace_original=True,
            )

        # ==================================================================
        # /index command and modal-based action handlers
        # ==================================================================

        @self.app.command("/index")
        async def handle_index_command(ack, command, client):
            """Handle /index — open modal with loading state, then update with data."""
            await ack()

            # Open modal immediately with loading view (uses trigger_id)
            trigger_id = command["trigger_id"]
            loading_view = build_loading_view()
            result = await client.views_open(trigger_id=trigger_id, view=loading_view)
            view_id = result["view"]["id"]

            # Fetch data and update the modal in-place
            try:
                stats = await self.search.get_registry_stats()
                if not stats:
                    stats = {"total_files": 0, "total_chunks": 0, "gates": {}, "ignored_count": 0}
                dashboard = build_index_dashboard(stats)
                await client.views_update(view_id=view_id, view=dashboard)
                self.logger.info(f"User {command['user_id']} opened /index dashboard")
            except Exception as e:
                self.logger.error(f"Error handling /index command: {e}", exc_info=True)
                error_view = build_status_view("Index Manager", f"Error loading dashboard: {e}", emoji="⚠️")
                await client.views_update(view_id=view_id, view=error_view)

        # --- helper to refresh dashboard in an existing modal ---
        async def _update_to_dashboard(client, view_id):
            """Fetch fresh stats and update the modal to the dashboard view."""
            loading = build_loading_view("Refreshing dashboard...")
            await client.views_update(view_id=view_id, view=loading)
            stats = await self.search.get_registry_stats()
            if not stats:
                stats = {"total_files": 0, "total_chunks": 0, "gates": {}, "ignored_count": 0}
            await client.views_update(view_id=view_id, view=build_index_dashboard(stats))

        @self.app.action(ACTION_BACK_DASHBOARD)
        async def handle_back_dashboard(ack, body, client):
            """Return to the dashboard view."""
            await ack()
            view_id = body["view"]["id"]
            try:
                await _update_to_dashboard(client, view_id)
            except Exception as e:
                self.logger.error(f"Error returning to dashboard: {e}", exc_info=True)

        @self.app.action(ACTION_BROWSE)
        async def handle_browse(ack, body, action, client):
            """Browse Documents — update modal with paged document list."""
            await ack()
            view_id = body["view"]["id"]
            loading = build_loading_view("Loading documents...")
            await client.views_update(view_id=view_id, view=loading)
            try:
                offset = int(action.get("value", "0"))
                page = await self.search.list_documents(offset=offset, limit=PAGE_SIZE)
                browser = build_document_browser(
                    items=[{
                        "path": d.path, "chunks": d.chunks,
                        "size": d.size, "gate": d.gate, "indexed_at": d.indexed_at,
                    } for d in page.items],
                    total=page.total, offset=page.offset, limit=PAGE_SIZE,
                )
                await client.views_update(view_id=view_id, view=browser)
            except Exception as e:
                self.logger.error(f"Error browsing documents: {e}", exc_info=True)
                err = build_status_view("Documents", f"Error loading documents: {e}", emoji="⚠️")
                await client.views_update(view_id=view_id, view=err)

        @self.app.action(ACTION_PAGE_NEXT)
        @self.app.action(ACTION_PAGE_PREV)
        async def handle_page_nav(ack, body, action, client):
            """Pagination — update modal with next/previous page."""
            await ack()
            view_id = body["view"]["id"]
            try:
                parts = action.get("value", "0|").split("|", 1)
                offset = int(parts[0])
                folder_filter = parts[1] if len(parts) > 1 and parts[1] else None
                page = await self.search.list_documents(offset=offset, limit=PAGE_SIZE, folder=folder_filter)
                browser = build_document_browser(
                    items=[{
                        "path": d.path, "chunks": d.chunks,
                        "size": d.size, "gate": d.gate, "indexed_at": d.indexed_at,
                    } for d in page.items],
                    total=page.total, offset=page.offset, limit=PAGE_SIZE,
                    folder_filter=folder_filter,
                )
                await client.views_update(view_id=view_id, view=browser)
            except Exception as e:
                self.logger.error(f"Error in page navigation: {e}", exc_info=True)

        # --- per-document Ignore/Delete use regex matching on action_id ---

        @self.app.action(re.compile(f"^{ACTION_DOC_IGNORE}_"))
        async def handle_doc_ignore(ack, body, action, client):
            """Ignore a document — update modal with feedback."""
            await ack()
            view_id = body["view"]["id"]
            file_path = action.get("value", "")
            loading = build_loading_view(f"Ignoring {file_path}...")
            await client.views_update(view_id=view_id, view=loading)
            try:
                success = await self.search.ignore_document(file_path)
                if success:
                    view = build_status_view(
                        "Document Ignored",
                        f"`{file_path}` removed from index and added to ignore list.",
                        emoji="👁️",
                    )
                else:
                    view = build_status_view(
                        "Ignore Failed",
                        f"Failed to ignore `{file_path}`.",
                        emoji="⚠️",
                    )
                await client.views_update(view_id=view_id, view=view)
            except Exception as e:
                self.logger.error(f"Error ignoring document: {e}", exc_info=True)
                err = build_status_view("Error", str(e), emoji="⚠️")
                await client.views_update(view_id=view_id, view=err)

        @self.app.action(re.compile(f"^{ACTION_DOC_DELETE}_"))
        async def handle_doc_delete_prompt(ack, body, action, client):
            """Delete button — push a confirmation view on top."""
            await ack()
            trigger_id = body["trigger_id"]
            file_path = action.get("value", "")
            confirm_view = build_delete_confirmation(file_path)
            await client.views_push(trigger_id=trigger_id, view=confirm_view)

        @self.app.view(CALLBACK_CONFIRM_DELETE)
        async def handle_confirm_delete(ack, view, body, client):
            """User clicked 'Yes, Delete' in the confirmation modal."""
            import json as _json
            metadata = _json.loads(view.get("private_metadata", "{}"))
            file_path = metadata.get("file_path", "")

            # Acknowledge with an update showing progress
            await ack(response_action="update", view=build_loading_view(f"Deleting {file_path}..."))

            # The parent view (document browser) is underneath; get its id
            parent_view_id = body.get("view", {}).get("previous_view_id")

            try:
                success = await self.search.delete_document(file_path)
                if success:
                    msg = f"`{file_path}` has been deleted from disk and removed from the index."
                    emoji = "🗑️"
                else:
                    msg = f"Failed to delete `{file_path}`. It may be in a read-only directory."
                    emoji = "⚠️"
            except Exception as e:
                self.logger.error(f"Error deleting document: {e}", exc_info=True)
                msg = f"Error: {e}"
                emoji = "⚠️"

            # Update the confirmation view with result + back button
            result_view = build_status_view("Delete Result", msg, emoji=emoji)
            # The ack already updated, so use views_update on current view
            try:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=result_view,
                )
            except Exception:
                pass  # View may already be closed

        @self.app.action(ACTION_SHOW_SETUP)
        async def handle_show_setup(ack, body, client):
            """Setup Gates — push a gate config form on top of the dashboard."""
            await ack()
            trigger_id = body["trigger_id"]
            try:
                gates = await self.search.get_gates()
                setup_view = build_gate_setup(gates)
                await client.views_push(trigger_id=trigger_id, view=setup_view)
            except Exception as e:
                self.logger.error(f"Error showing gate setup: {e}", exc_info=True)

        @self.app.view(CALLBACK_GATE_SETUP)
        async def handle_gate_submit(ack, view, body, client):
            """User clicked 'Save' in the gate setup modal."""
            state = view.get("state", {}).get("values", {})
            text = state.get("gate_config_block", {}).get("gate_config_input", {}).get("value", "")

            try:
                gates = parse_gate_config_text(text)
            except ValueError as e:
                await ack(response_action="errors", errors={"gate_config_block": str(e)})
                return

            # Acknowledge with loading
            await ack(response_action="update", view=build_loading_view("Saving gates..."))

            try:
                success = await self.search.replace_gates(gates)
                if success:
                    summary = "\n".join(
                        f"{'🔒' if m == 'readonly' else '📝'} `{d}` → {m}"
                        for d, m in sorted(gates.items())
                    )
                    result = build_status_view("Gates Saved", f"Gate configuration updated:\n{summary}")
                else:
                    result = build_status_view("Save Failed", "Failed to save gate configuration.", emoji="⚠️")
                await client.views_update(view_id=body["view"]["id"], view=result)
            except Exception as e:
                self.logger.error(f"Error saving gates: {e}", exc_info=True)
                err = build_status_view("Error", str(e), emoji="⚠️")
                try:
                    await client.views_update(view_id=body["view"]["id"], view=err)
                except Exception:
                    pass

        @self.app.action(ACTION_REINDEX)
        async def handle_reindex(ack, body, client):
            """Reindex All — update modal with progress feedback."""
            await ack()
            view_id = body["view"]["id"]
            loading = build_loading_view("Starting full re-index...")
            await client.views_update(view_id=view_id, view=loading)
            try:
                await self.search.trigger_reindex(force=True)
                result = build_status_view(
                    "Reindex Started",
                    "Full re-index started. This may take a few minutes.\n"
                    "You can close this dialog and check back later.",
                    emoji="🔄",
                )
                await client.views_update(view_id=view_id, view=result)
            except Exception as e:
                self.logger.error(f"Error triggering reindex: {e}", exc_info=True)
                err = build_status_view("Error", str(e), emoji="⚠️")
                await client.views_update(view_id=view_id, view=err)

        # ==================================================================
        # File Upload to Brain Handlers
        # ==================================================================

        # Store pending file uploads (keyed by user_id)
        self._pending_uploads: Dict[str, List[Dict]] = {}

        @self.app.action("save_file_to_brain")
        async def handle_save_to_brain(ack, body, action, client):
            """User clicked 'Save to Brain' - show folder selection."""
            await ack()
            channel = body["channel"]["id"]
            user_id = body["user"]["id"]
            
            # Parse file info from action value
            files = parse_file_value(action.get("value", ""))
            if not files:
                await client.chat_postMessage(
                    channel=channel,
                    text="⚠️ No files found to save.",
                )
                return
            
            # Store pending files for this user
            self._pending_uploads[user_id] = files
            
            # Show folder selection
            blocks = build_folder_selection_blocks(files, COMMON_DIRECTORIES)
            await client.chat_postMessage(
                channel=channel,
                blocks=blocks,
                text="Select a folder to save files to",
            )

        @self.app.action(re.compile(r"^upload_to_dir_"))
        async def handle_upload_to_dir(ack, body, action, client):
            """User selected a folder - upload files there."""
            await ack()
            channel = body["channel"]["id"]
            user_id = body["user"]["id"]
            
            # Extract directory from action_id (e.g., "upload_to_dir_notes" -> "notes")
            dir_name = action["action_id"].replace("upload_to_dir_", "")
            
            # Get pending files
            files = self._pending_uploads.pop(user_id, [])
            if not files:
                await client.chat_postMessage(
                    channel=channel,
                    text="⚠️ No pending files. Please upload files again.",
                )
                return
            
            # Send progress message
            progress_msg = await client.chat_postMessage(
                channel=channel,
                text=f"📤 Uploading {len(files)} file(s) to `{dir_name}/`...",
            )
            
            # Process each file
            results = []
            for file_info in files:
                file_url = file_info.get("url", "")
                file_name = file_info.get("name", "unknown")
                target_path = f"{dir_name}/{file_name}"
                
                try:
                    # Download from Slack
                    content = await download_file_from_slack_async(
                        file_url, self.bot_token
                    )
                    
                    # Upload to brain
                    result = await self.search.upload_document(
                        file_path=target_path,
                        content=content,
                        filename=file_name,
                        overwrite=False,
                    )
                    
                    if result.get("status") == "uploaded":
                        results.append({
                            "path": result.get("path", target_path),
                            "status": "uploaded",
                            "chunks": result.get("chunks", 0),
                        })
                        self.logger.info(f"Uploaded {target_path} to brain")
                    else:
                        error = result.get("error", "Unknown error")
                        results.append({
                            "path": target_path,
                            "status": "failed",
                            "error": error,
                        })
                        self.logger.error(f"Upload failed for {target_path}: {error}")
                        
                except Exception as e:
                    self.logger.error(f"Error uploading {file_name}: {e}", exc_info=True)
                    results.append({
                        "path": target_path,
                        "status": "failed",
                        "error": str(e),
                    })
            
            # Update message with results
            result_blocks = build_upload_result_blocks(results)
            await client.chat_update(
                channel=channel,
                ts=progress_msg["ts"],
                blocks=result_blocks,
                text="Upload complete",
            )

        # ==================================================================
        # Save Note to Brain Handlers
        # ==================================================================

        # Store pending note text (keyed by user_id)
        self._pending_notes: Dict[str, str] = {}

        @self.app.action("save_note_to_brain")
        async def handle_save_note(ack, body, action, client):
            """User clicked 'Save to Brain' for a note - show folder selection."""
            await ack()
            channel = body["channel"]["id"]
            user_id = body["user"]["id"]

            # Store the note text for this user
            note_text = action.get("value", "")
            if not note_text:
                await client.chat_postMessage(
                    channel=channel, text="⚠️ No text found to save."
                )
                return

            self._pending_notes[user_id] = note_text

            # Show folder selection
            blocks = build_save_note_folder_blocks(COMMON_DIRECTORIES)
            await client.chat_postMessage(
                channel=channel,
                blocks=blocks,
                text="Select a folder to save note to",
            )

        @self.app.action("dismiss_save_note")
        async def handle_dismiss_save_note(ack, body, client):
            """User dismissed the save note prompt."""
            await ack()
            # No action needed - just dismiss

        @self.app.action(re.compile(r"^save_note_dir_"))
        async def handle_save_note_dir(ack, body, action, client):
            """User selected a folder for saving the note."""
            await ack()
            channel = body["channel"]["id"]
            user_id = body["user"]["id"]

            dir_name = action["action_id"].replace("save_note_dir_", "")
            note_text = self._pending_notes.pop(user_id, "")

            if not note_text:
                await client.chat_postMessage(
                    channel=channel,
                    text="⚠️ No pending note. Please try again.",
                )
                return

            # Generate filename from date and first few words
            date_str = datetime.now().strftime("%Y-%m-%d")
            # Create a slug from the first ~5 words
            words = re.sub(r"[^a-z0-9\s]", "", note_text.lower()).split()[:5]
            slug = "-".join(words) if words else "note"
            filename = f"{date_str}-{slug}.md"
            target_path = f"{dir_name}/{filename}"

            try:
                # Format as markdown note
                md_content = f"# Note: {' '.join(words).title()}\n"
                md_content += f"*Saved: {date_str}*\n\n"
                md_content += note_text + "\n"

                success = await self.brain.write_file(
                    target_path, md_content, overwrite=False
                )

                if success:
                    await client.chat_postMessage(
                        channel=channel,
                        text=f"✅ Saved to `{target_path}` in your brain.",
                    )
                    self.logger.info(f"Saved note to brain: {target_path}")
                else:
                    await client.chat_postMessage(
                        channel=channel,
                        text=f"⚠️ Could not save — file may already exist: `{target_path}`",
                    )
            except Exception as e:
                self.logger.error(f"Error saving note: {e}", exc_info=True)
                await client.chat_postMessage(
                    channel=channel,
                    text=f"⚠️ Error saving note: {str(e)}",
                )

        # ==================================================================
        # /tools command - Manage tool enable/disable state
        # ==================================================================

        @self.app.command("/tools")
        async def handle_tools_command(ack, command, respond):
            """Handle /tools command - show tool management UI."""
            await ack()

            try:
                user_id = command["user_id"]
                blocks = build_tools_ui(self.tool_registry, user_id)
                await respond(
                    text="Tool Management",
                    blocks=blocks,
                    response_type="ephemeral",
                )
                self.logger.info(f"User {user_id} opened /tools UI")
            except Exception as e:
                self.logger.error(f"Error handling /tools command: {e}", exc_info=True)
                await respond(
                    text=f"⚠️ Error loading tools: {str(e)}",
                    response_type="ephemeral",
                )

        @self.app.action(re.compile(r"^tool_toggle_"))
        async def handle_tool_toggle(ack, body, action, respond):
            """Handle tool enable/disable toggle."""
            await ack()

            try:
                user_id = body["user"]["id"]
                tool_name, should_enable = parse_tool_toggle_action(
                    action.get("value", "")
                )

                if not tool_name:
                    await respond(
                        text="⚠️ Invalid tool toggle action.",
                        response_type="ephemeral",
                        replace_original=False,
                    )
                    return

                self.tool_registry.set_enabled(user_id, tool_name, should_enable)
                status = "enabled" if should_enable else "disabled"
                self.logger.info(f"User {user_id} {status} tool: {tool_name}")

                # Rebuild and replace the tool list
                blocks = build_tools_ui(self.tool_registry, user_id)
                await respond(
                    text="Tool Management",
                    blocks=blocks,
                    response_type="ephemeral",
                    replace_original=True,
                )
            except Exception as e:
                self.logger.error(f"Error toggling tool: {e}", exc_info=True)
                await respond(
                    text=f"⚠️ Error: {str(e)}",
                    response_type="ephemeral",
                    replace_original=False,
                )

        # ==================================================================
        # /facts command - Manage persistent user facts (FACTS)
        # ==================================================================

        @self.app.command("/facts")
        async def handle_facts_command(ack, command, client):
            """Handle /facts command - open modal for fact management."""
            await ack()

            try:
                user_id = command["user_id"]
                trigger_id = command["trigger_id"]
                blocks = build_facts_ui(user_id)

                modal = {
                    "type": "modal",
                    "callback_id": "facts_modal_stub",
                    "title": {"type": "plain_text", "text": "🧠 Facts"},
                    "close": {"type": "plain_text", "text": "Done"},
                    "blocks": blocks,
                }

                await client.views_open(trigger_id=trigger_id, view=modal)
                self.logger.info(f"User {user_id} opened /facts modal")
            except Exception as e:
                self.logger.error(f"Error handling /facts command: {e}", exc_info=True)

        @self.app.action("facts_add_new")
        async def handle_facts_add_new(ack, body, client):
            """Handle 'Add Fact' button — push add/edit form onto modal stack."""
            await ack()

            try:
                user_id = body["user"]["id"]
                trigger_id = body["trigger_id"]
                form_blocks = build_fact_edit_view(user_id)

                add_view = {
                    "type": "modal",
                    "callback_id": "fact_add_submit",
                    "title": {"type": "plain_text", "text": "➕ Add Fact"},
                    "submit": {"type": "plain_text", "text": "Save"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "private_metadata": user_id,
                    "blocks": form_blocks,
                }

                await client.views_push(trigger_id=trigger_id, view=add_view)
            except Exception as e:
                self.logger.error(f"Error opening add fact form: {e}", exc_info=True)

        @self.app.action(re.compile(r"^fact_overflow_"))
        async def handle_fact_overflow(ack, body, action, client):
            """Handle fact overflow menu (edit/delete)."""
            await ack()

            try:
                user_id = body["user"]["id"]
                selected = action.get("selected_option", {}).get("value", "")

                if not selected or ":" not in selected:
                    return

                op, key = selected.split(":", 1)

                if op == "delete":
                    store = FactsStore(user_id)
                    store.delete(key)
                    self.logger.info(f"User {user_id} deleted fact: {key}")

                    # Refresh the modal
                    view_id = body["view"]["id"]
                    blocks = build_facts_ui(user_id)
                    updated_view = {
                        "type": "modal",
                        "callback_id": "facts_modal_stub",
                        "title": {"type": "plain_text", "text": "🧠 Facts"},
                        "close": {"type": "plain_text", "text": "Done"},
                        "blocks": blocks,
                    }
                    await client.views_update(view_id=view_id, view=updated_view)

                elif op == "edit":
                    store = FactsStore(user_id)
                    fact = store.get(key)
                    if fact:
                        trigger_id = body["trigger_id"]
                        form_blocks = build_fact_edit_view(
                            user_id,
                            key=key,
                            value=fact.get("value", ""),
                            category=fact.get("category", "other"),
                        )

                        import json as _json
                        edit_view = {
                            "type": "modal",
                            "callback_id": "fact_edit_submit",
                            "title": {"type": "plain_text", "text": "✏️ Edit Fact"},
                            "submit": {"type": "plain_text", "text": "Save"},
                            "close": {"type": "plain_text", "text": "Cancel"},
                            "private_metadata": _json.dumps({"user_id": user_id, "original_key": key}),
                            "blocks": form_blocks,
                        }

                        await client.views_push(trigger_id=trigger_id, view=edit_view)
            except Exception as e:
                self.logger.error(f"Error handling fact overflow: {e}", exc_info=True)

        @self.app.action("facts_clear_all")
        async def handle_facts_clear_all(ack, body, client):
            """Handle 'Clear All' button — delete every fact for this user."""
            await ack()

            try:
                user_id = body["user"]["id"]
                store = FactsStore(user_id)
                facts = store.list_facts()
                for fact in facts:
                    store.delete(fact["key"])
                self.logger.info(f"User {user_id} cleared all {len(facts)} facts")

                # Refresh modal
                view_id = body["view"]["id"]
                blocks = build_facts_ui(user_id)
                updated_view = {
                    "type": "modal",
                    "callback_id": "facts_modal_stub",
                    "title": {"type": "plain_text", "text": "🧠 Facts"},
                    "close": {"type": "plain_text", "text": "Done"},
                    "blocks": blocks,
                }
                await client.views_update(view_id=view_id, view=updated_view)
            except Exception as e:
                self.logger.error(f"Error clearing facts: {e}", exc_info=True)

        @self.app.view("fact_add_submit")
        async def handle_fact_add_submit(ack, view, body, client):
            """Handle fact add modal submission."""
            await ack()

            try:
                user_id = view.get("private_metadata", body["user"]["id"])
                values = view["state"]["values"]

                key = values.get("fact_key_block", {}).get("fact_key_input", {}).get("value", "").strip()
                value = values.get("fact_value_block", {}).get("fact_value_input", {}).get("value", "").strip()
                category = (
                    values.get("fact_category_block", {})
                    .get("fact_category_input", {})
                    .get("selected_option", {})
                    .get("value", "other")
                )

                if not key or not value:
                    return

                store = FactsStore(user_id)
                store.store(key, value, category)
                self.logger.info(f"User {user_id} added fact: {key} [{category}]")

                # DM user confirmation
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"✅ Fact saved: `{key}` = {value}",
                )
            except Exception as e:
                self.logger.error(f"Error saving fact: {e}", exc_info=True)

        @self.app.view("fact_edit_submit")
        async def handle_fact_edit_submit(ack, view, body, client):
            """Handle fact edit modal submission."""
            await ack()

            try:
                import json as _json
                metadata = _json.loads(view.get("private_metadata", "{}"))
                user_id = metadata.get("user_id", body["user"]["id"])
                original_key = metadata.get("original_key", "")

                values = view["state"]["values"]

                new_key = values.get("fact_key_block", {}).get("fact_key_input", {}).get("value", "").strip()
                value = values.get("fact_value_block", {}).get("fact_value_input", {}).get("value", "").strip()
                category = (
                    values.get("fact_category_block", {})
                    .get("fact_category_input", {})
                    .get("selected_option", {})
                    .get("value", "other")
                )

                if not new_key or not value:
                    return

                store = FactsStore(user_id)

                # If key changed, delete the old one
                if original_key and original_key != new_key:
                    store.delete(original_key)

                store.store(new_key, value, category)
                self.logger.info(f"User {user_id} edited fact: {original_key} → {new_key} [{category}]")

                await client.chat_postMessage(
                    channel=user_id,
                    text=f"✅ Fact updated: `{new_key}` = {value}",
                )
            except Exception as e:
                self.logger.error(f"Error editing fact: {e}", exc_info=True)

        # ==================================================================
        # /mission command - View/edit agent mission principles
        # ==================================================================

        @self.app.command("/mission")
        async def handle_mission_command(ack, command, client):
            """Handle /mission command - open modal to view/edit mission principles."""
            await ack()

            try:
                user_id = command["user_id"]
                trigger_id = command["trigger_id"]

                current_mission = await self.mission_manager.load()

                modal = {
                    "type": "modal",
                    "callback_id": "mission_submit",
                    "title": {"type": "plain_text", "text": "🎯 Mission"},
                    "submit": {"type": "plain_text", "text": "Save"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "*Agent Mission Principles*\n\n"
                                    "These principles guide how the AI assistant behaves. "
                                    "They are injected into every system prompt.\n\n"
                                    "Edit below to customize your assistant's behavior."
                                ),
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "input",
                            "block_id": "mission_text_block",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "mission_text_input",
                                "multiline": True,
                                "initial_value": current_mission,
                            },
                            "label": {"type": "plain_text", "text": "Mission Principles"},
                        },
                    ],
                }

                await client.views_open(trigger_id=trigger_id, view=modal)
                self.logger.info(f"User {user_id} opened /mission modal")
            except Exception as e:
                self.logger.error(f"Error handling /mission command: {e}", exc_info=True)

        @self.app.view("mission_submit")
        async def handle_mission_submit(ack, view, body, client):
            """Handle mission modal submission — save updated principles."""
            await ack()

            try:
                user_id = body["user"]["id"]
                values = view["state"]["values"]
                new_mission = (
                    values.get("mission_text_block", {})
                    .get("mission_text_input", {})
                    .get("value", "")
                    .strip()
                )

                if new_mission:
                    saved = await self.mission_manager.save(new_mission)
                    if saved:
                        await client.chat_postMessage(
                            channel=user_id,
                            text="✅ Mission principles updated! Changes take effect on your next message.",
                        )
                        self.logger.info(f"User {user_id} updated mission principles ({len(new_mission)} chars)")
                    else:
                        await client.chat_postMessage(
                            channel=user_id,
                            text="⚠️ Failed to save mission principles.",
                        )
            except Exception as e:
                self.logger.error(f"Error saving mission: {e}", exc_info=True)

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
            user_message: Original user message (without attachments), used for brain search
            has_attachments: Whether the message includes file attachments

        Returns:
            Response text
        """
        start_time = datetime.now()

        # Initialize source tracker for this request
        tracker = SourceTracker()
        set_tracker(tracker)

        # Run pre-process hooks (Phase 7)
        hook_event = {
            "user_id": user_id,
            "text": text,
            "thread_id": thread_id,
            "user_message": user_message,
            "has_attachments": has_attachments,
        }
        await self._run_pre_process_hooks(hook_event)

        # Load conversation history
        history = await self.conversations.load_conversation(user_id, thread_id)

        # Check if summarization needed (lower threshold to reserve room for context injection)
        if (
            self.conversations.count_conversation_tokens(history)
            > self.summarization_threshold
        ):
            self.logger.info(
                f"Summarizing conversation for {user_id} (thread {thread_id})"
            )
            
            # Create summarization function that respects current model selection
            async def summarize_with_current_model(prompt: str) -> str:
                """Summarize using the currently selected model."""
                from clients.llm_client import Message
                messages = [Message(role="user", content=prompt)]
                response, model_used, _ = await self._generate_with_provider(
                    messages=messages,
                    user_id=user_id,
                    say_func=None,  # Don't notify on summarization
                )
                self.logger.info(f"Summarized conversation with {model_used}")
                return response
            
            history = await self.conversations.summarize_if_needed(
                history,
                max_tokens=self.summarization_threshold,
                summarize_fn=summarize_with_current_model,
            )

        # ---- NEW: Search past conversations for relevant context ----
        past_context = ""
        try:
            past_convos = await self.conversations.search_past_conversations(
                user_id=user_id,
                query=user_message or text,
                limit=2,
                exclude_thread=thread_id,
            )
            if past_convos:
                past_context = "\n\n**Relevant past conversations:**\n"
                for convo in past_convos:
                    ts = convo.get("timestamp", "recent")[:10]  # Just the date
                    past_context += f"[{ts}] You said: {convo['user_message'][:150]}\n"
                    past_context += f"I replied: {convo['assistant_message'][:150]}\n\n"
                self.logger.info(
                    f"Found {len(past_convos)} relevant past conversations"
                )
        except Exception as e:
            self.logger.warning(f"Past conversation search failed: {e}")

        # ---- Search brain for context (if enabled) ----
        # Skip search when files are attached - the file IS the context
        # Use original user message for search, not combined text with attachments
        context = ""
        search_query = user_message if user_message else text
        # Truncate query to reasonable length (avoid URL too long errors)
        search_query = search_query[:500]

        # Skip brain search for conversational messages (greetings, follow-ups,
        # recall questions) — these should be answered from conversation history
        is_conv = self._is_conversational(search_query)
        should_search = (
            self.enable_search
            and len(search_query) > 10
            and not has_attachments
            and not is_conv
        )

        if is_conv:
            self.logger.info(f"Skipping brain search for conversational message: '{search_query[:60]}'")

        if should_search:
            try:
                search_results = await self.search.search(
                    query=search_query,
                    content_type="markdown",
                    limit=self.max_search_results,
                )

                if search_results:
                    # ---- NEW: Filter by relevance score ----
                    filtered = []
                    for result in search_results:
                        score = getattr(result, "score", None)
                        # Keep results with no score (backward compat) or high score
                        if score is None or score >= self.min_relevance_score:
                            filtered.append(result)

                    # Keep at least one result if all were filtered out
                    if not filtered and search_results:
                        filtered = [search_results[0]]

                    search_results = filtered

                if search_results:
                    context = "\n\n**Relevant context from your brain:**\n"
                    for i, result in enumerate(search_results, 1):
                        # SearchResult is a dataclass with attributes, not a dict
                        snippet = result.entry[:200] if hasattr(result, "entry") else ""
                        file_name = result.file if hasattr(result, "file") else ""
                        score_str = ""
                        if hasattr(result, "score") and result.score:
                            score_str = f" [relevance: {result.score:.0%}]"
                        context += f"\n{i}. {snippet}...\n   (Source: {file_name}{score_str})\n"

                    self.logger.info(
                        f"Found {len(search_results)} relevant brain entries (after filtering)"
                    )

            except Exception as e:
                self.logger.warning(f"Brain search failed: {e}")
                # Continue without context

        # ---- Web search for current information (if enabled) ----
        web_context = ""
        should_web, web_reason = self._should_web_search(search_query)
        if should_web and self.enable_web_search and not has_attachments:
            try:
                self.logger.info(f"Web search triggered: {web_reason}")
                web_results = await self.web_search.search(search_query, limit=3)
                if web_results:
                    web_context = self.web_search.format_results(
                        web_results, max_snippet_length=self.web_context_budget // 5
                    )
                    self.logger.info(f"Found {len(web_results)} web search results")
            except Exception as e:
                self.logger.warning(f"Web search failed: {e}")
                # Continue without web context

        # ---- Combine past conversations + brain context + web context ----
        full_context = past_context + context + web_context

        # Build prompt
        messages = []

        # Add system prompt
        messages.append(Message(role="system", content=self.system_prompt))

        # ---- FACTS context injection (if message references personal context) ----
        facts_context = ""
        try:
            search_text = user_message or text
            if message_references_personal_context(search_text):
                facts_store = FactsStore(user_id)
                facts_context = facts_store.get_context_for_injection(limit=20)
                if facts_context:
                    messages.append(Message(role="system", content=facts_context))
                    self.logger.info(f"Injected FACTS context ({facts_store.count()} facts stored)")
        except Exception as e:
            self.logger.warning(f"FACTS injection failed: {e}")

        # ---- Mission principles injection ----
        try:
            mission_prompt = await self.mission_manager.get_for_prompt()
            if mission_prompt:
                messages.append(Message(role="system", content=mission_prompt))
        except Exception as e:
            self.logger.warning(f"Mission principles injection failed: {e}")

        # Add conversation history — this is the PRIMARY context
        for msg in history:
            messages.append(Message(role=msg["role"], content=msg["content"]))

        # Add current user message FIRST, then supplementary context
        # Context is injected as a system message AFTER history but BEFORE
        # the user message so the LLM sees the conversation flow naturally.
        if full_context:
            messages.append(Message(
                role="system",
                content=f"[Supplementary context — use only if relevant to the user's message]\n{full_context}"
            ))

        # Inject action metadata so the LLM knows what actually happened
        # This prevents the LLM from claiming it searched when it didn't
        action_note = (
            f"[Actions taken: brain_search={'yes' if context else 'no'}, "
            f"web_search={'yes' if web_context else 'no'}, "
            f"past_conversations={'yes' if past_context else 'no'}, "
            f"facts_loaded={'yes' if facts_context else 'no'}]"
        )
        messages.append(Message(role="system", content=action_note))

        messages.append(Message(role="user", content=text))

        # Generate response using provider-aware method
        # Handles Gemini/Ollama selection and quota fallback
        try:
            response, model_used, quota_exhausted = await self._generate_with_provider(
                messages=messages,
                user_id=user_id,
            )
            
            # If quota was exhausted, prepend a notice
            if quota_exhausted:
                response = (
                    "⚠️ *Gemini quota exhausted — using Ollama*\n"
                    "Use `/model` to switch providers.\n\n"
                    + response
                )
                
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
                    "model": model_used,
                    "latency": latency,
                    "context_used": bool(full_context),
                    "past_convos_found": bool(past_context),
                    "web_search_used": bool(web_context),
                },
            )
        except Exception as e:
            self.logger.warning(f"Failed to save conversation for {user_id}: {e}")
            # Continue anyway - user still gets their response

        self.logger.info(
            f"Generated response for {user_id} in {latency:.2f}s "
            f"(history: {len(history)} msgs, context: {bool(full_context)}, "
            f"past_convos: {bool(past_context)}, web_search: {bool(web_context)})"
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

        # Run post-process hooks (Phase 7) — may modify response
        response = await self._run_post_process_hooks(response, hook_event)

        # Clean up source tracker
        clear_tracker()

        return response

    def _should_web_search(self, query: str) -> tuple[bool, str]:
        """
        Determine if query should trigger web search.
        
        Web search is triggered for:
        - Current events (news, recent updates)
        - External factual lookups (populations, definitions, etc.)
        
        Web search is skipped for:
        - Personal context queries (notes, journals, past conversations)
        - Very short queries
        
        Args:
            query: The user's message text
            
        Returns:
            Tuple of (should_search: bool, reason: str)
        """
        query_lower = query.lower()
        
        # Skip very short queries
        if len(query) < 15:
            return (False, "query too short")
        
        # Keywords suggesting current events
        current_event_patterns = [
            "today", "yesterday", "this week", "this month",
            "latest", "recent", "current", "now", "breaking",
            "news about", "what happened", "update on",
            "what's happening", "what is happening",
            "stock price", "weather", "score", "game",
            "2025", "2026",  # Current/future years
        ]
        
        # Keywords suggesting external lookup (not personal notes)
        external_patterns = [
            "what is the population", "how many people",
            "who is the", "when was", "when did",
            "define ", "explain what", "tell me about",
            "official documentation", "according to",
            "how do i ", "how to ",
            "search the web", "google ",
            "look up", "find out",
            # Broader factual query patterns
            "top 3", "top 5", "top 10", "best ",
            "list of ", "examples of ", "list the ",
            "can you search", "can you find", "find me",
            "what are the", "what were the",
            "episodes of", "season ", "cast of",
            "recipe for", "ingredients for",
            "price of", "cost of", "value of",
            "reviews of", "rating of",
            "history of", "origin of",
            "compare ", "difference between",
            "vs ", " versus ",
        ]
        
        # Keywords suggesting personal context (prefer brain search only)
        personal_patterns = [
            "my notes", "my journal", "i wrote", "i mentioned",
            "we discussed", "my project", "my work",
            "remember when", "last time we", "earlier we",
            "my brain", "from my", "in my notes",
            "what did i", "what do i",
        ]
        
        # Check for personal patterns first (skip web search)
        if any(p in query_lower for p in personal_patterns):
            return (False, "personal context")
        
        # Check for current event patterns
        if any(p in query_lower for p in current_event_patterns):
            return (True, "current events")
        
        # Check for external lookup patterns
        if any(p in query_lower for p in external_patterns):
            return (True, "external lookup")
        
        # Default: no web search (prefer brain context)
        return (False, "default to brain")

    @staticmethod
    def _is_conversational(message: str) -> bool:
        """Check if a message is conversational (should use chat history, not brain search).

        Returns True for greetings, follow-ups, personal fact sharing, recall
        questions, and other messages where brain document search would be
        irrelevant or harmful (biasing the LLM toward documents over memory).

        Args:
            message: The user's message text

        Returns:
            True if the message is conversational and should skip brain search
        """
        msg = message.lower().strip()

        # Very short messages are almost always conversational
        if len(msg) < 30:
            return True

        conversational_patterns = [
            # Greetings
            "hello", "hey", "hi ", "hi!", "howdy", "good morning", "good afternoon",
            "good evening", "what's up", "how are you",
            # Follow-ups and recall
            "what did i", "what was", "do you remember", "earlier i",
            "i just said", "i told you", "i mentioned", "what project",
            "what name", "what did we", "remember when", "you said",
            "we were talking", "going back to", "as i said",
            "can you recall", "what's my", 
            # Personal fact sharing
            "my name is", "call me", "i'm called", "i go by",
            "i'm working on", "i'm building", "i prefer",
            "i like to be called",
            # Conversation management
            "thank you", "thanks", "got it", "ok", "okay",
            "sure", "yes", "no", "right", "correct",
            "never mind", "forget it", "let's move on",
            # Meta-conversational
            "can you help", "i need help", "let's talk about",
            "i want to discuss", "can we",
        ]

        return any(p in msg for p in conversational_patterns)

    @staticmethod
    def _should_suggest_save(message: str) -> bool:
        """Check if a message contains information worth saving to brain.

        Detects patterns suggesting the user is sharing personal facts,
        strategies, decisions, or preferences that would be valuable to
        persist in the brain knowledge base.

        Args:
            message: The user's message text

        Returns:
            True if the message appears save-worthy
        """
        message_lower = message.lower()

        # Security exclusions — never suggest saving secrets
        security_words = ["password", "secret", "token", "credential", "api key", "api_key"]
        if any(w in message_lower for w in security_words):
            return False

        # Must be substantial (not a short question)
        if len(message) < 50:
            return False

        # Save-worthy patterns
        patterns = [
            "i use ",
            "i prefer ",
            "my strategy",
            "my approach",
            "my workflow",
            "remember that",
            "important:",
            "note to self",
            "i always ",
            "i decided ",
            "i chose ",
            "my setup",
            "my config",
            "i currently ",
            "for future reference",
            "fyi ",
            "my backup",
            "my process",
            "my system",
            "my rule",
            "going forward",
        ]

        return any(pattern in message_lower for pattern in patterns)

    async def run(self):
        """
        Main agent loop - starts Socket Mode handler (blocks indefinitely)
        """
        self.logger.info("Starting Slack agent with Socket Mode...")

        try:
            # Health check
            await self._health_check()

            # Start MCP servers (non-critical — failures logged but don't block)
            try:
                await self.mcp_manager.startup()
            except Exception as e:
                self.logger.warning(f"⚠️ MCP startup failed (non-critical): {e}")

            # Start Socket Mode handler
            self.socket_handler = AsyncSocketModeHandler(self.app, self.app_token)

            self.logger.info("✅ Slack agent connected and ready")
            await self.notify("Slack Bot", "Slack agent started and connected")

            # This blocks forever, listening for events
            await self.socket_handler.start_async()

        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
            await self.mcp_manager.shutdown()
            await self.notify("Slack Bot", "Slack agent shutting down")

        except Exception as e:
            self.logger.error(f"Fatal error in Slack agent: {e}", exc_info=True)
            await self.notify("Slack Bot Error", f"⚠️ Slack agent crashed: {e}")
            raise

    async def _health_check(self):
        """Check if all dependencies are available"""
        errors = []

        # Check semantic search
        try:
            await self.search.health_check()
            self.logger.info("✅ Semantic search connection OK")
        except Exception as e:
            errors.append(f"Search unavailable: {e}")
            self.logger.warning(f"⚠️ Search unavailable: {e}")

        # Check Ollama
        try:
            await self.llm.health_check()
            self.logger.info("✅ Ollama connection OK")
        except Exception as e:
            errors.append(f"Ollama unavailable: {e}")
            self.logger.error(f"❌ Ollama unavailable: {e}")

        # Check cxdb (non-critical)
        try:
            if await self.cxdb.health_check():
                self.logger.info("✅ cxdb connection OK")
            else:
                self.logger.warning("⚠️ cxdb unavailable (will use JSON fallback)")
        except Exception as e:
            self.logger.warning(f"⚠️ cxdb unavailable: {e} (will use JSON fallback)")

        # Check brain folder
        brain_path = Path(self.brain.brain_path)
        if not brain_path.exists():
            errors.append(f"Brain folder not found: {brain_path}")
            self.logger.error(f"❌ Brain folder not found: {brain_path}")
        else:
            self.logger.info("✅ Brain folder OK")

        # Check web search (non-critical)
        if self.enable_web_search:
            try:
                if await self.web_search.health_check():
                    self.logger.info("✅ Web search OK")
                else:
                    self.logger.warning("⚠️ Web search unavailable (will continue without)")
            except Exception as e:
                self.logger.warning(f"⚠️ Web search unavailable: {e} (will continue without)")

        # Check Slack auth
        try:
            auth_test = await self.app.client.auth_test()
            bot_name = auth_test.get("user", "Unknown")
            self.logger.info(f"✅ Slack auth OK (bot: {bot_name})")
        except SlackApiError as e:
            errors.append(f"Slack auth failed: {e}")
            self.logger.error(f"❌ Slack auth failed: {e}")

        # Check tool registry (non-critical)
        try:
            tool_count = len(self.tool_registry.list_tools())
            self.logger.info(f"✅ Tool registry OK ({tool_count} tools registered)")
        except Exception as e:
            self.logger.warning(f"⚠️ Tool registry check failed: {e}")

        # Check mission manager (non-critical)
        try:
            mission = await self.mission_manager.load()
            self.logger.info(f"✅ Mission principles OK ({len(mission)} chars)")
        except Exception as e:
            self.logger.warning(f"⚠️ Mission principles unavailable: {e}")

        # Check MCP config (non-critical, just report)
        try:
            mcp_status = self.mcp_manager.get_server_status()
            enabled_count = sum(1 for s in mcp_status.values() if s["enabled"])
            self.logger.info(f"✅ MCP config OK ({len(mcp_status)} servers, {enabled_count} enabled)")
        except Exception as e:
            self.logger.warning(f"⚠️ MCP config check failed: {e}")

        if errors:
            # Ollama and Slack are critical — fail startup if either is down
            critical_errors = [e for e in errors if "Ollama" in e or "Slack" in e]
            if critical_errors:
                raise RuntimeError(f"Health check failed: {'; '.join(critical_errors)}")


def main():
    """Main entry point for Slack agent.
    
    All secrets are fetched from Vaultwarden. Bootstrap credentials 
    (VAULTWARDEN_TOKEN) must be set in environment before calling.
    """
    # Test configuration - non-secret values only
    config = {
        "search_url": os.getenv("SEARCH_URL", "http://nuc-1.local:9514"),
        "ollama_url": os.getenv("OLLAMA_URL", "http://m1-mini.local:11434"),
        "brain_folder": os.getenv("BRAIN_FOLDER", "/home/earchibald/brain"),
        "model": os.getenv("SLACK_MODEL", "llama3.2"),
        "max_context_tokens": 6000,
        "enable_search": True,
        "max_search_results": 3,
        "enable_web_search": os.getenv("ENABLE_WEB_SEARCH", "true").lower() == "true",
        "web_search_provider": os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo"),
        "tavily_api_key": os.getenv("TAVILY_API_KEY"),
        "enable_model_switching": True,
        "notification": {
            "enabled": True
        },
    }

    print("🚀 Starting Slack agent...")
    print(f"   Search: {config['search_url']}")
    print(f"   Ollama: {config['ollama_url']}")
    print(f"   Brain: {config['brain_folder']}")
    print(f"   Model: {config['model']}")
    print(f"   Web Search: {'enabled' if config['enable_web_search'] else 'disabled'} ({config['web_search_provider']})")

    agent = SlackAgent(config)

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n👋 Slack agent stopped")


# Production mode - secrets loaded from Vaultwarden
if __name__ == "__main__":
    main()
