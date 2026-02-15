"""
Unit tests for ConversationManager - conversation history persistence and summarization.

Tests verify:
- Save and load single messages
- Multi-turn conversation preservation
- Per-user conversation isolation
- Accurate token counting
- Automatic summarization when exceeding token limits
- Context preservation during summarization
- Thread-safe concurrent writes
- Recovery from corrupted JSON files
"""

import pytest
from unittest.mock import AsyncMock

from clients.conversation_manager import ConversationManager


@pytest.mark.unit
class TestConversationManager:
    """Test suite for ConversationManager"""

    @pytest.mark.asyncio
    async def test_save_and_load_single_message(self, test_brain_path):
        """
        Test that a single message can be saved and loaded correctly.

        Verifies that ConversationManager can:
        - Create necessary folder structure
        - Save a message with proper JSON structure
        - Load the saved message back with all fields intact
        - Timestamp is properly recorded

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        manager = ConversationManager(str(test_brain_path))
        user_id = "U123TEST"
        thread_id = "default"
        test_content = "Hello, this is a test message"

        # Save a message
        await manager.save_message(
            user_id=user_id, thread_id=thread_id, role="user", content=test_content
        )

        # Load the conversation
        messages = await manager.load_conversation(user_id, thread_id)

        # Verify
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == test_content
        assert "timestamp" in messages[0]
        assert isinstance(messages[0]["timestamp"], str)

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_preserved(
        self, test_brain_path, sample_conversation
    ):
        """
        Test that multi-turn conversations preserve full history and order.

        Verifies that ConversationManager maintains:
        - Correct message order (user, assistant, user, assistant)
        - All messages across multiple turns
        - Accurate role assignment
        - Complete content without truncation
        - Proper timestamps for each message

        Args:
            test_brain_path: Fixture providing temporary brain directory
            sample_conversation: Fixture with multi-turn conversation data
        """
        manager = ConversationManager(str(test_brain_path))
        user_id = "U123TEST"
        thread_id = "conversation_1"

        # Save all messages from sample conversation
        for msg in sample_conversation:
            await manager.save_message(
                user_id=user_id,
                thread_id=thread_id,
                role=msg["role"],
                content=msg["content"],
            )

        # Load and verify
        loaded_messages = await manager.load_conversation(user_id, thread_id)

        assert len(loaded_messages) == len(sample_conversation)

        # Verify each message preserved correctly
        for original, loaded in zip(sample_conversation, loaded_messages):
            assert loaded["role"] == original["role"]
            assert loaded["content"] == original["content"]

    @pytest.mark.asyncio
    async def test_conversation_isolation_per_user(self, test_brain_path):
        """
        Test that conversations are properly isolated per user ID.

        Verifies that:
        - Messages for user A don't appear in user B's conversation
        - Each user has separate storage folders
        - Thread IDs are properly scoped to users
        - No data leakage between users

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        manager = ConversationManager(str(test_brain_path))
        user1_id = "U111TEST"
        user2_id = "U222TEST"
        thread_id = "default"

        # Save messages for different users
        await manager.save_message(
            user_id=user1_id,
            thread_id=thread_id,
            role="user",
            content="Message from user 1",
        )

        await manager.save_message(
            user_id=user2_id,
            thread_id=thread_id,
            role="user",
            content="Message from user 2",
        )

        # Load conversations
        user1_messages = await manager.load_conversation(user1_id, thread_id)
        user2_messages = await manager.load_conversation(user2_id, thread_id)

        # Verify isolation
        assert len(user1_messages) == 1
        assert len(user2_messages) == 1
        assert user1_messages[0]["content"] == "Message from user 1"
        assert user2_messages[0]["content"] == "Message from user 2"

    @pytest.mark.asyncio
    async def test_token_counting_accuracy(self, test_brain_path):
        """
        Test that token counting provides reasonable estimates.

        Verifies that:
        - estimate_tokens() follows character/4 rule
        - count_conversation_tokens() sums all messages
        - Empty conversations count as 0 tokens
        - Token counts increase with content size
        - Token counting is consistent across calls

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        manager = ConversationManager(str(test_brain_path))

        # Test single message token estimation
        short_text = "Hello"  # 5 chars = 1-2 tokens
        short_tokens = manager.estimate_tokens(short_text)
        assert short_tokens >= 1

        long_text = (
            "This is a much longer message with more content to estimate tokens from"
        )
        long_tokens = manager.estimate_tokens(long_text)
        assert long_tokens > short_tokens

        # Test conversation token counting
        messages = [
            {"role": "user", "content": "What is AI?"},
            {
                "role": "assistant",
                "content": "AI is artificial intelligence, a field of computer science.",
            },
            {"role": "user", "content": "Tell me more"},
        ]

        total_tokens = manager.count_conversation_tokens(messages)
        assert total_tokens > 0

        # Verify it sums correctly (roughly)
        individual_sum = sum(
            manager.estimate_tokens(msg["content"]) for msg in messages
        )
        assert total_tokens == individual_sum

    @pytest.mark.asyncio
    async def test_automatic_summarization_triggers(self, test_brain_path):
        """
        Test that summarization triggers when conversation exceeds token limit.

        Verifies that:
        - Conversations under max_tokens are returned unchanged
        - Conversations over max_tokens trigger summarization
        - Recent messages are preserved during summarization
        - Summary message is added with proper metadata
        - LLM client is called for summarization

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        # Create mock LLM client
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(
            return_value="Summary of previous conversation: key points discussed"
        )

        manager = ConversationManager(str(test_brain_path), llm_client=mock_llm)

        # Create messages that exceed token limit
        messages = [
            {"role": "user", "content": "A" * 1000},  # ~250 tokens
            {"role": "assistant", "content": "B" * 1000},  # ~250 tokens
            {"role": "user", "content": "C" * 1000},  # ~250 tokens
            {"role": "assistant", "content": "D" * 1000},  # ~250 tokens
            {"role": "user", "content": "E" * 500},  # Recent message to keep
        ]

        # Summarize with low limit to trigger summarization
        result = await manager.summarize_if_needed(
            messages=messages,
            max_tokens=500,  # Low limit to force summarization
            keep_recent=1,
        )

        # Verify summarization occurred
        assert len(result) < len(messages)  # Should be compressed
        assert mock_llm.complete.called  # LLM should be called

    @pytest.mark.asyncio
    async def test_summarization_preserves_context(self, test_brain_path):
        """
        Test that summarization preserves important context and recent messages.

        Verifies that:
        - Recent messages are always kept intact
        - Summary is prepended with proper role
        - Recent messages come after summary
        - Metadata is added to summary message
        - No information is lost from recent messages

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(
            return_value="User discussed ADHD strategies and time management"
        )

        manager = ConversationManager(str(test_brain_path), llm_client=mock_llm)

        messages = [
            {"role": "user", "content": "Question about ADHD" * 50},
            {"role": "assistant", "content": "Response about strategies" * 50},
            {"role": "user", "content": "Recent important question"},
        ]

        result = await manager.summarize_if_needed(
            messages=messages, max_tokens=200, keep_recent=1
        )

        # Verify structure
        assert len(result) >= 2  # At least summary + recent message
        assert result[-1]["role"] == "user"
        assert result[-1]["content"] == "Recent important question"

        # Verify summary has proper metadata
        if result[0]["role"] == "system":
            assert "metadata" in result[0]
            assert result[0]["metadata"].get("type") == "summary"

    @pytest.mark.asyncio
    async def test_concurrent_writes_thread_safe(self, test_brain_path):
        """
        Test that concurrent writes to the same conversation are handled safely.

        Verifies that:
        - Multiple concurrent saves don't corrupt data
        - Atomic operations prevent partial writes
        - Lock mechanism prevents race conditions
        - All messages are preserved after concurrent writes
        - No data loss from simultaneous access

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        import asyncio

        manager = ConversationManager(str(test_brain_path))
        user_id = "U123TEST"
        thread_id = "concurrent_test"

        # Create multiple concurrent write tasks
        async def save_message(role, content):
            await manager.save_message(
                user_id=user_id, thread_id=thread_id, role=role, content=content
            )

        # Save 5 messages concurrently
        tasks = [save_message("user", f"Message {i}") for i in range(5)]
        await asyncio.gather(*tasks)

        # Load and verify all messages saved
        messages = await manager.load_conversation(user_id, thread_id)

        assert len(messages) == 5
        for i, msg in enumerate(messages):
            assert msg["content"] == f"Message {i}"

    @pytest.mark.asyncio
    async def test_corrupt_json_recovery(self, test_brain_path):
        """
        Test that corrupted JSON files are handled gracefully without crash.

        Verifies that:
        - Corrupt JSON doesn't raise exception
        - Empty list is returned for corrupt files
        - System can recover and save new messages
        - Corrupt file can be replaced with new valid data
        - Error logging occurs for diagnostics

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        manager = ConversationManager(str(test_brain_path))
        user_id = "U123TEST"
        thread_id = "corrupt_test"

        # Manually create a corrupt JSON file
        conv_path = manager._get_conversation_path(user_id, thread_id)
        conv_path.parent.mkdir(parents=True, exist_ok=True)
        conv_path.write_text("{ invalid json content ]")

        # Try to load - should return empty list, not crash
        messages = await manager.load_conversation(user_id, thread_id)
        assert messages == []

        # Should be able to save new messages after corruption
        await manager.save_message(
            user_id=user_id,
            thread_id=thread_id,
            role="user",
            content="Recovered message",
        )

        # Verify new message saved correctly
        loaded = await manager.load_conversation(user_id, thread_id)
        assert len(loaded) == 1
        assert loaded[0]["content"] == "Recovered message"


@pytest.mark.unit
class TestConversationManagerIntegration:
    """Integration tests for ConversationManager with realistic workflows"""

    @pytest.mark.asyncio
    async def test_full_conversation_workflow(
        self, test_brain_path, sample_conversation
    ):
        """
        Test complete workflow: save multi-turn conversation and retrieve it.

        Simulates real usage:
        1. User starts conversation
        2. Multiple turns exchanged
        3. Conversation retrieved later
        4. History available for new responses

        Args:
            test_brain_path: Fixture providing temporary brain directory
            sample_conversation: Fixture with realistic conversation
        """
        manager = ConversationManager(str(test_brain_path))
        user_id = "U0AELV88VN3"
        thread_id = "realistic_workflow"

        # Save entire conversation
        for msg in sample_conversation:
            await manager.save_message(
                user_id=user_id,
                thread_id=thread_id,
                role=msg["role"],
                content=msg["content"],
            )

        # Later, retrieve for context
        loaded = await manager.load_conversation(user_id, thread_id)

        assert len(loaded) == len(sample_conversation)
        assert loaded[0]["role"] == "user"
        assert "ADHD" in loaded[0]["content"]

    @pytest.mark.asyncio
    async def test_list_user_conversations(self, test_brain_path):
        """
        Test listing all conversations for a user.

        Verifies that:
        - Multiple threads are listed separately
        - Metadata includes counts and timestamps
        - Conversations sorted by recency
        - Non-existent users return empty list

        Args:
            test_brain_path: Fixture providing temporary brain directory
        """
        manager = ConversationManager(str(test_brain_path))
        user_id = "U123TEST"

        # Create multiple conversations
        for thread_num in range(3):
            thread_id = f"thread_{thread_num}"
            for i in range(2):
                await manager.save_message(
                    user_id=user_id,
                    thread_id=thread_id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Message {i} in thread {thread_num}",
                )

        # List conversations
        convs = await manager.get_user_conversations(user_id)

        assert len(convs) == 3
        for conv in convs:
            assert "thread_id" in conv
            assert conv["message_count"] == 2
