"""
Unit tests for SlackUserClient.

Tests the client's core functionality with mocked Slack API calls.
No real Slack connections are made.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from clients.slack_user_client import (
    SlackUserClient,
    Conversation,
    SlackAuthError,
    BotResponseTimeout,
    SlackUserClientError,
)


BOT_USER_ID = "U0BOT123"
USER_ID = "U0USER456"
DM_CHANNEL = "D0DMCHAN789"


@pytest.fixture
def mock_webclient():
    """Mock WebClient with auth_test pre-configured."""
    with patch("clients.slack_user_client.WebClient") as MockWebClient:
        instance = MockWebClient.return_value
        instance.auth_test.return_value = {"user_id": USER_ID}
        instance.conversations_open.return_value = {
            "channel": {"id": DM_CHANNEL}
        }
        instance.chat_postMessage.return_value = {"ts": "1000.000"}
        yield instance


@pytest.fixture
def client(mock_webclient):
    """SlackUserClient with mocked dependencies."""
    return SlackUserClient(
        user_token="xoxp-test-token",
        bot_user_id=BOT_USER_ID,
    )


# ============================================================================
# Initialization
# ============================================================================


@pytest.mark.unit
class TestInit:
    def test_successful_init(self, mock_webclient):
        client = SlackUserClient(
            user_token="xoxp-test", bot_user_id=BOT_USER_ID
        )
        assert client.user_id == USER_ID
        assert client.bot_user_id == BOT_USER_ID

    def test_auth_failure_raises(self):
        with patch("clients.slack_user_client.WebClient") as MockWC:
            from slack_sdk.errors import SlackApiError
            err_response = MagicMock()
            err_response.__getitem__ = lambda self, key: "invalid_auth"
            MockWC.return_value.auth_test.side_effect = SlackApiError(
                message="", response=err_response
            )
            with pytest.raises(SlackAuthError, match="Failed to authenticate"):
                SlackUserClient(user_token="xoxp-bad", bot_user_id=BOT_USER_ID)

    def test_loads_token_from_vaultwarden(self, mock_webclient):
        with patch.object(
            SlackUserClient, "_load_from_vaultwarden",
            side_effect=lambda key: {
                "SLACK_USER_TOKEN": "xoxp-from-vault",
                "BRAIN_BOT_USER_ID": BOT_USER_ID,
            }[key],
        ):
            client = SlackUserClient()
            assert client.bot_user_id == BOT_USER_ID


# ============================================================================
# DM Channel
# ============================================================================


@pytest.mark.unit
class TestDMChannel:
    def test_opens_dm_channel(self, client, mock_webclient):
        channel = client._ensure_dm_channel()
        assert channel == DM_CHANNEL
        mock_webclient.conversations_open.assert_called_once_with(
            users=[BOT_USER_ID]
        )

    def test_caches_dm_channel(self, client, mock_webclient):
        client._ensure_dm_channel()
        client._ensure_dm_channel()
        # Only one API call despite two invocations
        assert mock_webclient.conversations_open.call_count == 1


# ============================================================================
# Sending Messages
# ============================================================================


@pytest.mark.unit
class TestSendMessage:
    def test_sends_to_dm_channel(self, client, mock_webclient):
        ts = client._send_message("hello")
        assert ts == "1000.000"
        mock_webclient.chat_postMessage.assert_called_once_with(
            channel=DM_CHANNEL, text="hello"
        )

    def test_sends_threaded_message(self, client, mock_webclient):
        client._send_message("reply", thread_ts="999.000")
        mock_webclient.chat_postMessage.assert_called_once_with(
            channel=DM_CHANNEL, text="reply", thread_ts="999.000"
        )


# ============================================================================
# Polling for Responses
# ============================================================================


@pytest.mark.unit
class TestPolling:
    def test_finds_bot_response_by_user_id(self, client, mock_webclient):
        mock_webclient.conversations_history.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "I'm the bot", "ts": "1001.000"}
            ]
        }
        response = client._poll_for_response(after_ts="1000.000", timeout=5)
        assert response["text"] == "I'm the bot"

    def test_finds_bot_response_by_bot_id(self, client, mock_webclient):
        mock_webclient.conversations_history.return_value = {
            "messages": [
                {"user": "U0OTHER", "bot_id": "B0BOT", "text": "bot msg", "ts": "1001.000"}
            ]
        }
        response = client._poll_for_response(after_ts="1000.000", timeout=5)
        assert response["text"] == "bot msg"

    def test_ignores_own_messages(self, client, mock_webclient):
        mock_webclient.conversations_history.side_effect = [
            {"messages": [{"user": USER_ID, "text": "my msg", "ts": "1001.000"}]},
            {"messages": [{"user": BOT_USER_ID, "text": "bot reply", "ts": "1002.000"}]},
        ]
        response = client._poll_for_response(after_ts="1000.000", timeout=10)
        assert response["text"] == "bot reply"

    def test_timeout_raises(self, client, mock_webclient):
        mock_webclient.conversations_history.return_value = {"messages": []}
        with pytest.raises(BotResponseTimeout, match="did not respond within 2 seconds"):
            client._poll_for_response(after_ts="1000.000", timeout=2)

    def test_polls_thread_replies(self, client, mock_webclient):
        mock_webclient.conversations_replies.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "threaded reply", "ts": "1002.000"}
            ]
        }
        response = client._poll_for_response(
            after_ts="1000.000", thread_ts="999.000", timeout=5
        )
        assert response["text"] == "threaded reply"
        mock_webclient.conversations_replies.assert_called()

    def test_handles_rate_limiting(self, client, mock_webclient):
        from slack_sdk.errors import SlackApiError
        rate_response = MagicMock()
        rate_response.status_code = 429
        rate_response.headers = {"Retry-After": "1"}
        rate_response.__getitem__ = lambda self, key: "rate_limited"

        mock_webclient.conversations_history.side_effect = [
            SlackApiError(message="", response=rate_response),
            {"messages": [{"user": BOT_USER_ID, "text": "after rate limit", "ts": "1001.000"}]},
        ]
        response = client._poll_for_response(after_ts="1000.000", timeout=10)
        assert response["text"] == "after rate limit"


# ============================================================================
# ask() and ask_raw()
# ============================================================================


@pytest.mark.unit
class TestAsk:
    def test_ask_returns_text(self, client, mock_webclient):
        mock_webclient.conversations_history.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "Hello human!", "ts": "1001.000"}
            ]
        }
        result = client.ask("Hi bot")
        assert result == "Hello human!"

    def test_ask_raw_returns_full_message(self, client, mock_webclient):
        bot_msg = {"user": BOT_USER_ID, "text": "detailed", "ts": "1001.000", "blocks": []}
        mock_webclient.conversations_history.return_value = {"messages": [bot_msg]}
        result = client.ask_raw("test")
        assert result["text"] == "detailed"
        assert "blocks" in result


# ============================================================================
# Conversation (multi-turn)
# ============================================================================


@pytest.mark.unit
class TestConversation:
    def test_first_message_sets_thread(self, client, mock_webclient):
        mock_webclient.conversations_replies.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "first reply", "ts": "1001.000"}
            ]
        }
        convo = client.conversation()
        convo.ask("hello")
        assert convo.thread_ts == "1000.000"  # ts from chat_postMessage

    def test_subsequent_messages_use_thread(self, client, mock_webclient):
        mock_webclient.conversations_replies.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "reply", "ts": "1001.000"}
            ]
        }
        convo = client.conversation()
        convo.ask("first")

        mock_webclient.chat_postMessage.return_value = {"ts": "1002.000"}
        mock_webclient.conversations_replies.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "second reply", "ts": "1003.000"}
            ]
        }
        convo.ask("second")

        # Second message should include thread_ts
        calls = mock_webclient.chat_postMessage.call_args_list
        assert calls[1][1].get("thread_ts") == "1000.000"

    def test_history_tracking(self, client, mock_webclient):
        mock_webclient.conversations_replies.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "reply", "ts": "1001.000"}
            ]
        }
        convo = client.conversation()
        convo.ask("hello")

        assert len(convo.history) == 2
        assert convo.history[0] == {"role": "user", "content": "hello"}
        assert convo.history[1] == {"role": "assistant", "content": "reply"}

    def test_context_manager(self, client, mock_webclient):
        mock_webclient.conversations_replies.return_value = {
            "messages": [
                {"user": BOT_USER_ID, "text": "reply", "ts": "1001.000"}
            ]
        }
        with client.conversation() as convo:
            result = convo.ask("test")
            assert result == "reply"

    def test_ask_raw_in_conversation(self, client, mock_webclient):
        bot_msg = {"user": BOT_USER_ID, "text": "raw reply", "ts": "1001.000"}
        mock_webclient.conversations_replies.return_value = {"messages": [bot_msg]}
        convo = client.conversation()
        result = convo.ask_raw("test")
        assert result["text"] == "raw reply"
        assert len(convo.history) == 2
