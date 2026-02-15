"""
Conversation Manager - Persistent conversation history for Slack bot

Manages per-user conversation storage, retrieval, and automatic summarization
when conversations exceed token limits.
"""

import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timezone


class ConversationManager:
    """Manages conversation history with automatic summarization"""

    def __init__(self, brain_path: str, llm_client=None):
        """
        Initialize conversation manager

        Args:
            brain_path: Path to brain folder root
            llm_client: Optional LLMClient for summarization
        """
        self.brain_folder = Path(brain_path)
        self.users_folder = self.brain_folder / "users"
        self.llm_client = llm_client

        # Ensure users folder exists
        self.users_folder.mkdir(parents=True, exist_ok=True)

    def _get_conversation_path(self, user_id: str, thread_id: str) -> Path:
        """Get path to conversation file"""
        user_folder = self.users_folder / user_id / "conversations"
        user_folder.mkdir(parents=True, exist_ok=True)

        # Sanitize thread_id for filename
        safe_thread_id = thread_id.replace("/", "_").replace("\\", "_")
        return user_folder / f"{safe_thread_id}.json"

    async def load_conversation(self, user_id: str, thread_id: str) -> List[Dict]:
        """
        Load conversation history

        Args:
            user_id: Slack user ID
            thread_id: Slack thread timestamp

        Returns:
            List of messages [{"role": "user|assistant", "content": "...", "timestamp": "..."}]
        """
        path = self._get_conversation_path(user_id, thread_id)

        if not path.exists():
            return []

        try:
            async with asyncio.Lock():
                data = json.loads(path.read_text())
                return data.get("messages", [])
        except json.JSONDecodeError as e:
            print(f"Error loading conversation {path}: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error loading conversation {path}: {e}")
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
        Save a message to conversation history

        Args:
            user_id: Slack user ID
            thread_id: Slack thread timestamp
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata (model, tokens, latency, etc.)
        """
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
            message["metadata"] = metadata

        data["messages"].append(message)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Save atomically
        try:
            async with asyncio.Lock():
                temp_path = path.with_suffix(".tmp")
                temp_path.write_text(json.dumps(data, indent=2))
                temp_path.rename(path)
        except Exception as e:
            print(f"Error saving conversation {path}: {e}")
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
        self, messages: List[Dict], max_tokens: int = 6000, keep_recent: int = 3
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
            # Call LLM to summarize
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
        Delete a conversation

        Args:
            user_id: Slack user ID
            thread_id: Slack thread timestamp

        Returns:
            True if deleted, False if not found
        """
        path = self._get_conversation_path(user_id, thread_id)

        if path.exists():
            try:
                path.unlink()
                return True
            except Exception as e:
                print(f"Error deleting conversation {path}: {e}")
                return False
        return False


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
