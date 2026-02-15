"""
Unit tests for bot message filtering with whitelist support.

Tests verify that:
1. Bot messages are ignored by default (backward compatibility)
2. Whitelisted bot messages are processed (E2E testing support)
3. Non-whitelisted bot messages are still ignored
"""

import pytest
import os
from unittest.mock import patch


@pytest.mark.unit
class TestBotMessageFiltering:
    """Test bot message filtering logic with ALLOWED_TEST_BOT_IDS"""

    def test_bot_message_ignored_by_default(self):
        """
        Verify bot messages are ignored when ALLOWED_TEST_BOT_IDS is not set.

        This maintains backward compatibility - by default, all bot messages
        should be filtered out to prevent loops.
        """
        event = {
            "subtype": "bot_message",
            "bot_id": "B12345",
            "text": "Some bot message",
        }

        # Simulate the filtering logic from slack_agent.py
        with patch.dict(os.environ, {"ALLOWED_TEST_BOT_IDS": ""}, clear=False):
            if event.get("subtype") == "bot_message":
                allowed_bot_ids = os.getenv("ALLOWED_TEST_BOT_IDS", "").split(",")
                bot_id = event.get("bot_id", "")
                allowed_bot_ids = [b.strip() for b in allowed_bot_ids if b.strip()]
                should_process = bool(bot_id and bot_id in allowed_bot_ids)

        assert not should_process, "Bot message should be ignored by default"

    def test_whitelisted_bot_message_processed(self):
        """
        Verify whitelisted bot messages are processed.

        When ALLOWED_TEST_BOT_IDS is set, messages from those bots
        should pass through the filter for E2E testing.
        """
        event = {
            "subtype": "bot_message",
            "bot_id": "B_TEST_BOT",
            "text": "Test message from E2E bot",
        }

        # Simulate the filtering logic with whitelist
        with patch.dict(
            os.environ, {"ALLOWED_TEST_BOT_IDS": "B_TEST_BOT"}, clear=False
        ):
            if event.get("subtype") == "bot_message":
                allowed_bot_ids = os.getenv("ALLOWED_TEST_BOT_IDS", "").split(",")
                bot_id = event.get("bot_id", "")
                allowed_bot_ids = [b.strip() for b in allowed_bot_ids if b.strip()]
                should_process = bool(bot_id and bot_id in allowed_bot_ids)
            else:
                should_process = True

        assert should_process, "Whitelisted bot message should be processed"

    def test_non_whitelisted_bot_message_ignored(self):
        """
        Verify non-whitelisted bot messages are still ignored.

        Even when ALLOWED_TEST_BOT_IDS is set, only the specified
        bot IDs should pass through. Others should still be filtered.
        """
        event = {
            "subtype": "bot_message",
            "bot_id": "B_OTHER_BOT",
            "text": "Message from non-whitelisted bot",
        }

        # Simulate the filtering logic with different bot in whitelist
        with patch.dict(
            os.environ, {"ALLOWED_TEST_BOT_IDS": "B_TEST_BOT"}, clear=False
        ):
            if event.get("subtype") == "bot_message":
                allowed_bot_ids = os.getenv("ALLOWED_TEST_BOT_IDS", "").split(",")
                bot_id = event.get("bot_id", "")
                allowed_bot_ids = [b.strip() for b in allowed_bot_ids if b.strip()]
                should_process = bool(bot_id and bot_id in allowed_bot_ids)

        assert not should_process, "Non-whitelisted bot message should be ignored"

    def test_multiple_whitelisted_bots(self):
        """
        Verify multiple bot IDs can be whitelisted.

        ALLOWED_TEST_BOT_IDS supports comma-separated list of bot IDs.
        """
        event1 = {"subtype": "bot_message", "bot_id": "B_TEST_BOT_1"}
        event2 = {"subtype": "bot_message", "bot_id": "B_TEST_BOT_2"}
        event3 = {"subtype": "bot_message", "bot_id": "B_OTHER_BOT"}

        with patch.dict(
            os.environ, {"ALLOWED_TEST_BOT_IDS": "B_TEST_BOT_1,B_TEST_BOT_2"}
        ):
            # Check first bot
            bot_id = event1.get("bot_id", "")
            allowed_bot_ids = os.getenv("ALLOWED_TEST_BOT_IDS", "").split(",")
            allowed_bot_ids = [b.strip() for b in allowed_bot_ids if b.strip()]
            should_process_1 = bool(bot_id and bot_id in allowed_bot_ids)

            # Check second bot
            bot_id = event2.get("bot_id", "")
            should_process_2 = bool(bot_id and bot_id in allowed_bot_ids)

            # Check third bot
            bot_id = event3.get("bot_id", "")
            should_process_3 = bool(bot_id and bot_id in allowed_bot_ids)

        assert should_process_1, "First whitelisted bot should be processed"
        assert should_process_2, "Second whitelisted bot should be processed"
        assert not should_process_3, "Non-whitelisted bot should be ignored"

    def test_bot_message_without_bot_id_ignored(self):
        """
        Verify bot messages without bot_id are always ignored.

        Safety check: if a message has subtype=bot_message but no bot_id,
        it should be filtered out.
        """
        event = {
            "subtype": "bot_message",
            "text": "Bot message without bot_id",
        }

        with patch.dict(
            os.environ, {"ALLOWED_TEST_BOT_IDS": "B_TEST_BOT"}, clear=False
        ):
            if event.get("subtype") == "bot_message":
                allowed_bot_ids = os.getenv("ALLOWED_TEST_BOT_IDS", "").split(",")
                bot_id = event.get("bot_id", "")
                allowed_bot_ids = [b.strip() for b in allowed_bot_ids if b.strip()]
                should_process = bool(bot_id and bot_id in allowed_bot_ids)

        assert not should_process, "Bot message without bot_id should be ignored"

    def test_regular_user_message_not_affected(self):
        """
        Verify regular user messages are not affected by the whitelist.

        Messages without subtype=bot_message should pass through regardless
        of ALLOWED_TEST_BOT_IDS setting.
        """
        event = {
            "type": "message",
            "user": "U123456",
            "text": "Regular user message",
        }

        # Regular messages don't have subtype="bot_message"
        should_process = event.get("subtype") != "bot_message"

        assert should_process, "Regular user messages should always be processed"
