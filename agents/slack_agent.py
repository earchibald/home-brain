"""
Slack Agent - Multi-turn conversation bot with brain context

Connects to Slack via Socket Mode, handles DM messages with:
- Per-user conversation history
- Khoj context search
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
        self.khoj = SemanticSearchClient(
            base_url=config.get("khoj_url", "http://nuc-1.local:42110")
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
        # Reserve tokens for context injection (cxdb + Khoj results)
        self.context_budget = config.get("context_budget", 2000)
        self.summarization_threshold = config.get(
            "summarization_threshold",
            max(self.max_context_tokens - self.context_budget, 2000),
        )
        self.enable_khoj_search = config.get("enable_khoj_search", True)
        self.max_search_results = config.get("max_search_results", 3)
        self.min_relevance_score = config.get("min_relevance_score", 0.7)
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
            # Otherwise fall through to default check

        if not self.model:
            return True  # No specific model configured, use default

        try:
            # Check if model exists in current LLM client's available models
            available_models = self.llm.list_models()
            return self.model in available_models
        except Exception as e:
            self.logger.warning(f"Failed to check model availability: {e}")
            return False  # Assume unavailable if we can't check

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
                # Refresh provider discovery with configured Ollama URL
                self.model_manager.discover_available_sources(ollama_url=self.ollama_url)

                # Build UI
                blocks = build_model_selector_ui(self.model_manager)

                await respond(
                    text="Model Selection",
                    blocks=blocks,
                    response_type="ephemeral",
                )
                self.logger.info(f"User {command['user_id']} opened /model UI")

            except Exception as e:
                self.logger.error(f"Error handling /model command: {e}", exc_info=True)
                await respond(
                    text=f"⚠️ Error loading model selector: {str(e)}",
                    response_type="ephemeral",
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
                stats = await self.khoj.get_registry_stats()
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
            stats = await self.khoj.get_registry_stats()
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
                page = await self.khoj.list_documents(offset=offset, limit=PAGE_SIZE)
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
                page = await self.khoj.list_documents(offset=offset, limit=PAGE_SIZE, folder=folder_filter)
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
                success = await self.khoj.ignore_document(file_path)
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
                success = await self.khoj.delete_document(file_path)
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
                gates = await self.khoj.get_gates()
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
                success = await self.khoj.replace_gates(gates)
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
                await self.khoj.trigger_reindex(force=True)
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
                    result = await self.khoj.upload_document(
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

        # Check if summarization needed (lower threshold to reserve room for context injection)
        if (
            self.conversations.count_conversation_tokens(history)
            > self.summarization_threshold
        ):
            self.logger.info(
                f"Summarizing conversation for {user_id} (thread {thread_id})"
            )
            history = await self.conversations.summarize_if_needed(
                history, max_tokens=self.summarization_threshold
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
                self.logger.warning(f"Khoj search failed: {e}")
                # Continue without context

        # ---- Combine past conversations + brain context ----
        full_context = past_context + context

        # Build prompt
        messages = []

        # Add system prompt
        messages.append(Message(role="system", content=self.system_prompt))

        # Add conversation history
        for msg in history:
            messages.append(Message(role=msg["role"], content=msg["content"]))

        # Add current user message with optional context
        user_content = text
        if full_context:
            user_content = f"{full_context}\n\n**User message:** {text}"

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
                    "context_used": bool(full_context),
                    "past_convos_found": bool(past_context),
                },
            )
        except Exception as e:
            self.logger.warning(f"Failed to save conversation for {user_id}: {e}")
            # Continue anyway - user still gets their response

        self.logger.info(
            f"Generated response for {user_id} in {latency:.2f}s "
            f"(history: {len(history)} msgs, context: {bool(full_context)}, "
            f"past_convos: {bool(past_context)})"
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

        # Check Slack auth
        try:
            auth_test = await self.app.client.auth_test()
            bot_name = auth_test.get("user", "Unknown")
            self.logger.info(f"✅ Slack auth OK (bot: {bot_name})")
        except SlackApiError as e:
            errors.append(f"Slack auth failed: {e}")
            self.logger.error(f"❌ Slack auth failed: {e}")

        if errors:
            # Ollama and Slack are critical — fail startup if either is down
            critical_errors = [e for e in errors if "Ollama" in e or "Slack" in e]
            if critical_errors:
                raise RuntimeError(f"Health check failed: {'; '.join(critical_errors)}")


# Production mode - secrets loaded from environment variables or Vaultwarden
if __name__ == "__main__":

    # Test configuration
    config = {
        "khoj_url": os.getenv("KHOJ_URL", "http://nuc-1.local:42110"),
        "ollama_url": os.getenv("OLLAMA_URL", "http://m1-mini.local:11434"),
        "brain_folder": os.getenv("BRAIN_FOLDER", "/home/earchibald/brain"),
        "model": os.getenv("SLACK_MODEL", "llama3.2"),
        "max_context_tokens": 6000,
        "enable_khoj_search": True,
        "max_search_results": 3,
        "notification": {
            "enabled": True
        },
    }

    print("🚀 Starting Slack agent...")
    print(f"   Khoj: {config['khoj_url']}")
    print(f"   Ollama: {config['ollama_url']}")
    print(f"   Brain: {config['brain_folder']}")
    print(f"   Model: {config['model']}")

    agent = SlackAgent(config)

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n👋 Slack agent stopped")
