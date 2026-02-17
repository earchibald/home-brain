"""
Conversation Manager - Persistent conversation history for Slack bot

Manages per-user conversation storage, retrieval, and automatic summarization
when conversations exceed token limits.

Supports optional cxdb integration for DAG-based conversation history.
When a CxdbClient is provided, messages are dual-written (cxdb + JSON)
with cxdb as the preferred read source and JSON as reliable fallback.
"""

import json
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation history with automatic summarization.

    Also supports Slack Assistant Framework context awareness:
      - Tracking which threads are Assistant threads
      - Storing per-thread context (e.g. focused channel)
    """

    def __init__(self, brain_path: str, llm_client=None, cxdb_client=None):
        """
        Initialize conversation manager

        Args:
            brain_path: Path to brain folder root
            llm_client: Optional LLMClient for summarization
            cxdb_client: Optional CxdbClient for DAG-based history
        """
        self.brain_folder = Path(brain_path)
        self.users_folder = self.brain_folder / "users"
        self.llm_client = llm_client
        self.cxdb_client = cxdb_client

        # Ensure users folder exists
        self.users_folder.mkdir(parents=True, exist_ok=True)

        # Load thread_ts -> context_id mapping (for cxdb)
        self._context_map = self._load_context_map()

        # --- Slack Assistant Framework state ---
        # Key: f"{channel_id}:{thread_ts}" -> Value: Context dictionary
        self.assistant_contexts: Dict[str, Dict] = {}
        # Track which threads are "Assistant" threads vs standard DMs
        self.assistant_threads: set = set()

    def _get_conversation_path(self, user_id: str, thread_id: str) -> Path:
        """Get path to conversation file"""
        user_folder = self.users_folder / user_id / "conversations"
        user_folder.mkdir(parents=True, exist_ok=True)

        # Sanitize thread_id for filename
        safe_thread_id = thread_id.replace("/", "_").replace("\\", "_")
        return user_folder / f"{safe_thread_id}.json"

    # ------------------------------------------------------------------
    # cxdb context mapping helpers
    # ------------------------------------------------------------------

    def _get_context_map_path(self) -> Path:
        """Path to the cxdb context mapping file."""
        return self.brain_folder / "cxdb_map.json"

    def _load_context_map(self) -> Dict[str, int]:
        """Load thread_ts -> context_id mapping from disk."""
        path = self._get_context_map_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load cxdb context map: {e}")
            return {}

    def _save_context_map(self) -> None:
        """Atomically write the context map to disk."""
        path = self._get_context_map_path()
        try:
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(self._context_map, indent=2))
            temp_path.rename(path)
        except Exception as e:
            logger.warning(f"Failed to save cxdb context map: {e}")

    async def _get_or_create_context(self, thread_id: str) -> Optional[int]:
        """Lookup or create a cxdb context for a thread.

        Returns context_id or None if cxdb is unavailable.
        """
        if not self.cxdb_client:
            return None

        # Check existing mapping
        if thread_id in self._context_map:
            return self._context_map[thread_id]

        # Create new context
        try:
            context_id = await self.cxdb_client.create_context()
            self._context_map[thread_id] = context_id
            self._save_context_map()
            return context_id
        except Exception as e:
            logger.warning(f"Failed to create cxdb context for {thread_id}: {e}")
            return None

    def _turns_to_messages(self, turns: List[Dict]) -> List[Dict]:
        """Convert cxdb turns to message format, filtering non-chat turns.

        Args:
            turns: Raw turn list from cxdb.

        Returns:
            List of {role, content, timestamp} dicts.
        """
        messages = []
        for turn in turns:
            if turn.get("type_id") != "chat.message":
                continue
            data = turn.get("data", {})
            msg = {
                "role": data.get("role", "user"),
                "content": data.get("content", ""),
            }
            # Preserve timestamp if available
            if "timestamp" in turn:
                msg["timestamp"] = turn["timestamp"]
            elif "created_at" in turn:
                msg["timestamp"] = turn["created_at"]
            messages.append(msg)
        return messages

    async def load_conversation(self, user_id: str, thread_id: str) -> List[Dict]:
        """
        Load conversation history.

        Tries cxdb first (if a context mapping exists), falls back to JSON.

        Args:
            user_id: Slack user ID
            thread_id: Slack thread timestamp

        Returns:
            List of messages [{"role": "user|assistant", "content": "...", "timestamp": "..."}]
        """
        # Try cxdb first if we have a mapping
        if self.cxdb_client and thread_id in self._context_map:
            try:
                context_id = self._context_map[thread_id]
                turns = await self.cxdb_client.get_turns(context_id)
                messages = self._turns_to_messages(turns)
                if messages:
                    return messages
            except Exception as e:
                logger.warning(f"cxdb load failed for {thread_id}, falling back to JSON: {e}")

        # JSON fallback
        path = self._get_conversation_path(user_id, thread_id)

        if not path.exists():
            return []

        try:
            async with asyncio.Lock():
                data = json.loads(path.read_text())
                return data.get("messages", [])
        except json.JSONDecodeError as e:
            logger.warning(f"Error loading conversation {path}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error loading conversation {path}: {e}")
            return []

    async def save_message(
        self,
        user_id: str,
        thread_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Save a message to conversation history.

        Dual-write: tries cxdb first (best-effort), then always saves to JSON.
        cxdb failure never blocks the JSON write.

        Args:
            user_id: Slack user ID
            thread_id: Slack thread timestamp
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata (model, tokens, latency, etc.)
        """
        # --- cxdb write (best-effort) ---
        cxdb_turn_id = None
        cxdb_turn_hash = None
        if self.cxdb_client:
            try:
                context_id = await self._get_or_create_context(thread_id)
                if context_id is not None:
                    model = metadata.get("model") if metadata else None
                    turn = await self.cxdb_client.append_turn(
                        context_id=context_id, role=role, content=content, model=model,
                    )
                    cxdb_turn_id = turn.get("turn_id")
                    cxdb_turn_hash = turn.get("turn_hash")
            except Exception as e:
                logger.warning(f"cxdb write failed for {thread_id}: {e}")

        # --- JSON write (always) ---
        path = self._get_conversation_path(user_id, thread_id)

        # Load existing conversation
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError:
                # Corrupt file, start fresh
                data = {
                    "thread_id": thread_id,
                    "user_id": user_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "messages": [],
                }
        else:
            data = {
                "thread_id": thread_id,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "messages": [],
            }

        # Add new message
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if metadata:
            message["metadata"] = dict(metadata)
        else:
            message["metadata"] = {}

        # Enrich JSON metadata with cxdb identifiers
        if cxdb_turn_id is not None:
            message["metadata"]["cxdb_turn_id"] = cxdb_turn_id
        if cxdb_turn_hash is not None:
            message["metadata"]["cxdb_turn_hash"] = cxdb_turn_hash

        # Remove empty metadata dict to stay backward-compatible
        if not message["metadata"]:
            del message["metadata"]

        data["messages"].append(message)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Save atomically
        try:
            async with asyncio.Lock():
                temp_path = path.with_suffix(".tmp")
                temp_path.write_text(json.dumps(data, indent=2))
                temp_path.rename(path)
        except Exception as e:
            logger.error(f"Error saving conversation {path}: {e}")
            raise

    def estimate_tokens(self, text: str) -> int:
        """
        Rough token estimation (characters / 4)

        Args:
            text: Text to estimate

        Returns:
            Approximate token count
        """
        return len(text) // 4

    def count_conversation_tokens(self, messages: List[Dict]) -> int:
        """
        Count total tokens in conversation

        Args:
            messages: List of message dicts

        Returns:
            Approximate total token count
        """
        total = 0
        for msg in messages:
            total += self.estimate_tokens(msg.get("content", ""))
        return total

    async def summarize_if_needed(
        self,
        messages: List[Dict],
        max_tokens: int = 6000,
        keep_recent: int = 3,
        summarize_fn=None,
    ) -> List[Dict]:
        """
        Summarize conversation if it exceeds token limit

        Strategy:
        - Always keep last N messages (most recent context)
        - Summarize older messages into single system message
        - Return: [summary_message] + recent_messages

        Args:
            messages: Conversation history
            max_tokens: Maximum allowed tokens
            keep_recent: Number of recent messages to always keep
            summarize_fn: Optional async function(prompt) -> str for summarization.
                         If not provided, uses self.llm_client.

        Returns:
            Compressed message list
        """
        current_tokens = self.count_conversation_tokens(messages)

        if current_tokens <= max_tokens:
            return messages

        if not self.llm_client:
            # No LLM client, just truncate
            print("Warning: Truncating conversation (no LLM client for summarization)")
            return messages[-keep_recent:]

        # Split into old (to summarize) and recent (to keep)
        if len(messages) <= keep_recent:
            # Too few messages, just truncate by tokens
            truncated = []
            token_count = 0
            for msg in reversed(messages):
                msg_tokens = self.estimate_tokens(msg.get("content", ""))
                if token_count + msg_tokens > max_tokens:
                    break
                truncated.insert(0, msg)
                token_count += msg_tokens
            return truncated

        old_messages = messages[:-keep_recent]
        recent_messages = messages[-keep_recent:]

        # Build summary prompt
        conversation_text = "\n\n".join(
            [f"{msg['role'].upper()}: {msg['content']}" for msg in old_messages]
        )

        summary_prompt = f"""Summarize this conversation history concisely, preserving key facts, decisions, and context. Keep it under 500 words.

Conversation:
{conversation_text}

Concise summary:"""

        try:
            # Call LLM to summarize (use provided function or default client)
            if summarize_fn:
                summary = await summarize_fn(summary_prompt)
            else:
                summary = await self.llm_client.complete(
                    prompt=summary_prompt, model="llama3.2", max_tokens=1000
                )

            # Create summary message
            summary_message = {
                "role": "system",
                "content": f"[Previous conversation summary]: {summary.strip()}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "type": "summary",
                    "summarized_messages": len(old_messages),
                },
            }

            # Return summary + recent messages
            return [summary_message] + recent_messages

        except Exception as e:
            print(f"Error summarizing conversation: {e}")
            # Fallback: just keep recent messages
            return recent_messages

    async def search_past_conversations(
        self, user_id: str, query: str, limit: int = 2, exclude_thread: str = None
    ) -> List[Dict]:
        """
        Search past conversations for relevant exchanges.

        Performs simple keyword matching against stored JSON conversation files.
        Returns the most relevant user/assistant exchange pairs.

        Args:
            user_id: Slack user ID
            query: Search query
            limit: Maximum number of exchange pairs to return
            exclude_thread: Thread ID to exclude (current thread)

        Returns:
            List of dicts with keys: user_message, assistant_message, timestamp, thread_id
        """
        user_folder = self.users_folder / user_id / "conversations"

        if not user_folder.exists():
            return []

        # Tokenize query into keywords (lowercase, min 3 chars)
        query_words = [w.lower() for w in query.split() if len(w) >= 3]
        if not query_words:
            return []

        scored_exchanges = []

        for conv_file in user_folder.glob("*.json"):
            try:
                data = json.loads(conv_file.read_text())
                thread_id = data.get("thread_id", "")

                # Skip current thread
                if exclude_thread and thread_id == exclude_thread:
                    continue

                messages = data.get("messages", [])

                # Pair up user/assistant exchanges
                for i in range(len(messages) - 1):
                    if (
                        messages[i].get("role") == "user"
                        and messages[i + 1].get("role") == "assistant"
                    ):
                        user_msg = messages[i].get("content", "")
                        asst_msg = messages[i + 1].get("content", "")
                        combined = (user_msg + " " + asst_msg).lower()

                        # Score: count matching query words
                        score = sum(1 for w in query_words if w in combined)

                        if score > 0:
                            scored_exchanges.append(
                                {
                                    "user_message": user_msg[:200],
                                    "assistant_message": asst_msg[:200],
                                    "timestamp": messages[i].get("timestamp", ""),
                                    "thread_id": thread_id,
                                    "score": score,
                                }
                            )
            except Exception as e:
                logger.warning(f"Error searching conversation file {conv_file}: {e}")
                continue

        # Sort by score descending, take top N
        scored_exchanges.sort(key=lambda x: x["score"], reverse=True)
        return scored_exchanges[:limit]

    async def get_user_conversations(self, user_id: str) -> List[Dict]:
        """
        List all conversations for a user

        Args:
            user_id: Slack user ID

        Returns:
            List of conversation metadata [{"thread_id": "...", "message_count": N, ...}]
        """
        user_folder = self.users_folder / user_id / "conversations"

        if not user_folder.exists():
            return []

        conversations = []
        for conv_file in user_folder.glob("*.json"):
            try:
                data = json.loads(conv_file.read_text())
                conversations.append(
                    {
                        "thread_id": data.get("thread_id"),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "message_count": len(data.get("messages", [])),
                    }
                )
            except Exception as e:
                print(f"Error reading conversation file {conv_file}: {e}")
                continue

        # Sort by updated_at descending
        conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return conversations

    async def delete_conversation(self, user_id: str, thread_id: str) -> bool:
        """
        Delete a conversation (both JSON file and cxdb mapping)

        Args:
            user_id: Slack user ID
            thread_id: Slack thread timestamp

        Returns:
            True if deleted, False if not found
        """
        path = self._get_conversation_path(user_id, thread_id)
        deleted = False

        # Delete JSON file
        if path.exists():
            try:
                path.unlink()
                deleted = True
            except Exception as e:
                print(f"Error deleting conversation {path}: {e}")
                return False
        
        # Clear cxdb mapping
        if thread_id in self._context_map:
            del self._context_map[thread_id]
            self._save_context_map()
            deleted = True
        
        return deleted

    # ------------------------------------------------------------------
    # Slack Assistant Framework methods
    # ------------------------------------------------------------------

    def mark_as_assistant_thread(self, channel_id: str, thread_ts: str) -> None:
        """Mark a specific thread as being part of the Assistant UI surface."""
        if not thread_ts:
            return
        key = f"{channel_id}:{thread_ts}"
        self.assistant_threads.add(key)
        logger.info(f"Marked thread {key} as Assistant thread")

    def is_assistant_thread(self, channel_id: str, thread_ts: str) -> bool:
        """Check if a thread is an Assistant thread."""
        if not thread_ts:
            return False
        key = f"{channel_id}:{thread_ts}"
        return key in self.assistant_threads

    def save_assistant_context(
        self, channel_id: str, thread_ts: str, context: Dict
    ) -> None:
        """Save context provided by assistant_thread_context_changed event.

        This stores information like which channel the user is currently viewing
        so it can be injected into the next LLM prompt.
        """
        if not thread_ts:
            return
        key = f"{channel_id}:{thread_ts}"
        self.assistant_contexts[key] = context
        logger.debug(f"Updated assistant context for {key}: {context}")

    def get_assistant_context(
        self, channel_id: str, thread_ts: str
    ) -> Optional[Dict]:
        """Retrieve the current context for an assistant thread."""
        if not thread_ts:
            return None
        key = f"{channel_id}:{thread_ts}"
        return self.assistant_contexts.get(key)


# Example usage
if __name__ == "__main__":

    async def test():
        # Mock LLM client for testing
        class MockLLM:
            async def complete(self, prompt, model, max_tokens):
                return "This is a test summary of the conversation."

        manager = ConversationManager("/tmp/test_brain", MockLLM())

        # Test save/load
        await manager.save_message("U123", "thread1", "user", "Hello!")
        await manager.save_message("U123", "thread1", "assistant", "Hi there!")

        messages = await manager.load_conversation("U123", "thread1")
        print(f"Loaded {len(messages)} messages")

        # Test token counting
        tokens = manager.count_conversation_tokens(messages)
        print(f"Conversation tokens: {tokens}")

        # Test listing conversations
        conversations = await manager.get_user_conversations("U123")
        print(f"User has {len(conversations)} conversations")

        print("✅ ConversationManager tests passed")

    asyncio.run(test())
