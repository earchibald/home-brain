"""
E2E tests for Brain Assistant using SlackUserClient.

These tests send real DMs to the running Brain Assistant bot AS THE USER
(not as a test bot). This exercises the exact same code path as production:
no bot-message filtering, no whitelist, no special handling.

Prerequisites:
- Brain Assistant bot running on NUC-2
- SLACK_USER_TOKEN in Vaultwarden (xoxp- user OAuth token)
- BRAIN_BOT_USER_ID in Vaultwarden
- Vaultwarden accessible (VAULTWARDEN_TOKEN etc. in environment)

Tests are skipped if Vaultwarden is not accessible.
"""

import pytest
from clients.slack_user_client import (
    SlackUserClient,
    SlackAuthError,
    BotResponseTimeout,
)


def _vaultwarden_available() -> bool:
    """Check if Vaultwarden credentials are configured."""
    import os
    return bool(os.getenv("VAULTWARDEN_TOKEN"))


skip_reason = (
    "E2E tests require Vaultwarden access with SLACK_USER_TOKEN and BRAIN_BOT_USER_ID. "
    "Set VAULTWARDEN_TOKEN, VAULTWARDEN_URL, etc. in environment."
)


@pytest.fixture(scope="module")
def slack_user_client():
    """Real SlackUserClient acting as the user. Requires Vaultwarden access."""
    if not _vaultwarden_available():
        pytest.skip(skip_reason)
    try:
        return SlackUserClient()
    except (SlackAuthError, Exception) as e:
        pytest.skip(f"Could not initialize SlackUserClient: {e}")


@pytest.fixture
def brain_conversation(slack_user_client):
    """Multi-turn conversation with Brain Assistant."""
    convo = slack_user_client.conversation()
    yield convo
    convo.close()


@pytest.mark.e2e
@pytest.mark.skipif(not _vaultwarden_available(), reason=skip_reason)
class TestBrainAsUser:
    """E2E tests that interact with Brain Assistant as the real user."""

    def test_basic_response(self, slack_user_client):
        """Bot responds to a simple greeting sent as the user."""
        response = slack_user_client.ask("hello", timeout=60)
        assert response is not None
        assert len(response) > 0
        print(f"Bot responded: {response[:100]}...")

    def test_question_answer(self, slack_user_client):
        """Bot answers a factual question correctly."""
        response = slack_user_client.ask("What is 2+2?", timeout=60)
        assert response is not None
        assert "4" in response, f"Expected '4' in response, got: {response}"
        print(f"Bot answered correctly: {response[:100]}...")

    def test_multi_turn_context(self, brain_conversation):
        """Bot maintains context across multiple turns in a thread."""
        r1 = brain_conversation.ask("My favorite color is blue. Remember that.")
        assert r1 is not None
        assert len(r1) > 0

        r2 = brain_conversation.ask("What is my favorite color?")
        assert r2 is not None
        assert "blue" in r2.lower(), f"Expected 'blue' in response, got: {r2}"
        print(f"Multi-turn context maintained: {r2[:100]}...")

    def test_conversation_history_tracking(self, brain_conversation):
        """Conversation object tracks history correctly."""
        brain_conversation.ask("Tell me a short fact.")
        assert len(brain_conversation.history) == 2
        assert brain_conversation.history[0]["role"] == "user"
        assert brain_conversation.history[1]["role"] == "assistant"
        assert brain_conversation.thread_ts is not None

    def test_timeout_handling(self, slack_user_client):
        """Verify timeout raises BotResponseTimeout (with very short timeout)."""
        # Use 1 second timeout - bot can't possibly respond that fast
        with pytest.raises(BotResponseTimeout):
            slack_user_client.ask("test timeout", timeout=1)
