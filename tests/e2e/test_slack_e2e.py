"""
E2E tests for Brain Assistant Slack bot.

These tests send real DMs to the running bot on NUC-2 and verify responses
by polling Slack's conversations.history API. They test the full stack:
- Slack bot receives message via Socket Mode
- Processes message through Khoj search + Ollama LLM
- Posts response back to DM
- CI polls for response and validates content

Prerequisites:
- Brain Assistant bot running on NUC-2 with ALLOWED_TEST_BOT_IDS set
- SLACK_TEST_BOT_TOKEN: Bot token for "Brain E2E Tester" app (xoxb-...)
- SLACK_BOT_TOKEN: Bot token for "Brain Assistant" app (xoxb-...)
- BRAIN_BOT_USER_ID: User ID of Brain Assistant bot (U...)
- TEST_BOT_USER_ID: User ID of E2E Tester bot (U...)

All tests are skipped if tokens are not set (safe for local dev).
"""

import os
import time
import pytest
from typing import Optional, Dict, Any
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


# Environment variable checks
SLACK_TEST_BOT_TOKEN = os.getenv("SLACK_TEST_BOT_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
BRAIN_BOT_USER_ID = os.getenv("BRAIN_BOT_USER_ID")
TEST_BOT_USER_ID = os.getenv("TEST_BOT_USER_ID")
E2E_TEST_CHANNEL_ID = os.getenv("E2E_TEST_CHANNEL_ID")

# Check if all required tokens are present
has_all_tokens = all(
    [SLACK_TEST_BOT_TOKEN, SLACK_BOT_TOKEN, BRAIN_BOT_USER_ID, TEST_BOT_USER_ID, E2E_TEST_CHANNEL_ID]
)

# Skip reason message
skip_reason = (
    "E2E tests require SLACK_TEST_BOT_TOKEN, SLACK_BOT_TOKEN, "
    "BRAIN_BOT_USER_ID, TEST_BOT_USER_ID, and E2E_TEST_CHANNEL_ID environment variables"
)


@pytest.fixture
def test_bot_client() -> Optional[WebClient]:
    """Slack client for E2E Tester bot (sends messages)"""
    if not has_all_tokens:
        pytest.skip(skip_reason)
    return WebClient(token=SLACK_TEST_BOT_TOKEN)


@pytest.fixture
def brain_bot_client() -> Optional[WebClient]:
    """Slack client for Brain Assistant bot (reads responses)"""
    if not has_all_tokens:
        pytest.skip(skip_reason)
    return WebClient(token=SLACK_BOT_TOKEN)


@pytest.fixture
def test_channel() -> str:
    """
    Return the pre-configured test channel ID.
    
    The channel must be created manually and both test and brain bots
    must be members of it. This avoids needing additional Slack scopes.
    
    Returns:
        str: Channel ID from E2E_TEST_CHANNEL_ID env var
    """
    return E2E_TEST_CHANNEL_ID



def wait_for_response(
    client: WebClient,
    channel_id: str,
    after_ts: str,
    timeout_seconds: int = 60,
    poll_interval: int = 2,
) -> Optional[Dict[str, Any]]:
    """
    Poll conversations.history for a new message from Brain Assistant.

    Args:
        client: Slack WebClient (must have im:history scope)
        channel_id: DM channel ID
        after_ts: Message timestamp to start searching after
        timeout_seconds: Maximum time to wait for response
        poll_interval: Seconds to wait between polls

    Returns:
        Dict with message data if found, None if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        try:
            # Get recent messages (limit to 10 most recent)
            response = client.conversations_history(
                channel=channel_id, oldest=after_ts, limit=10
            )

            messages = response.get("messages", [])

            # Look for a message from Brain Assistant (not from test bot)
            for msg in messages:
                user_id = msg.get("user", "")
                bot_id = msg.get("bot_id", "")

                # Skip messages from test bot itself
                if user_id == TEST_BOT_USER_ID:
                    continue

                # Look for message from Brain Assistant
                # Bot messages have bot_id field, direct messages from bots have user field
                # We need to check both cases to handle different message types
                is_from_brain_bot = user_id == BRAIN_BOT_USER_ID
                # Note: We can't check bot_id == BRAIN_BOT_USER_ID because bot_id is different
                # from user_id. For now, accept any bot message that's not from test bot.
                # In practice, only Brain Assistant should be responding in this DM.
                is_bot_response = bot_id and user_id != TEST_BOT_USER_ID
                
                if is_from_brain_bot or is_bot_response:
                    return msg

            # No response yet, wait and retry
            time.sleep(poll_interval)

        except SlackApiError as e:
            print(f"Error polling for response: {e.response['error']}")
            time.sleep(poll_interval)

    return None


@pytest.mark.e2e
@pytest.mark.skipif(not has_all_tokens, reason=skip_reason)
class TestSlackBotE2E:
    """End-to-end tests for Brain Assistant Slack bot"""

    def test_bot_responds_to_hello(
        self, test_bot_client: WebClient, brain_bot_client: WebClient, test_channel: str
    ):
        """
        Test basic response: Send "hello" and verify bot responds.

        Scenario:
        1. E2E Tester sends "hello" to Brain Assistant
        2. Poll conversations.history for response within 60s
        3. Verify response is received and non-empty

        Expected: Bot responds with a greeting within 60 seconds
        """
        # Send test message
        try:
            response = test_bot_client.chat_postMessage(
                channel=test_channel, text="hello", as_user=True
            )
            message_ts = response["ts"]
            print(f"✉️  Sent test message: hello (ts={message_ts})")
        except SlackApiError as e:
            pytest.fail(f"Failed to send message: {e.response['error']}")

        # Wait for response
        print("⏳ Waiting for bot response...")
        bot_response = wait_for_response(
            brain_bot_client, test_channel, after_ts=message_ts, timeout_seconds=60
        )

        # Assertions
        assert bot_response is not None, "Bot did not respond within 60 seconds"

        response_text = bot_response.get("text", "")
        assert len(response_text) > 0, "Bot response was empty"

        print(f"✅ Bot responded: {response_text[:100]}...")

    def test_bot_responds_to_question(
        self, test_bot_client: WebClient, brain_bot_client: WebClient, test_channel: str
    ):
        """
        Test substantive response: Send a question and verify meaningful answer.

        Scenario:
        1. E2E Tester sends "What is 2+2?" to Brain Assistant
        2. Poll conversations.history for response within 60s
        3. Verify response contains the expected answer

        Expected: Bot responds with "4" in the answer within 60 seconds
        """
        # Send test message
        test_question = "What is 2+2?"
        try:
            response = test_bot_client.chat_postMessage(
                channel=test_channel, text=test_question, as_user=True
            )
            message_ts = response["ts"]
            print(f"✉️  Sent test message: {test_question} (ts={message_ts})")
        except SlackApiError as e:
            pytest.fail(f"Failed to send message: {e.response['error']}")

        # Wait for response
        print("⏳ Waiting for bot response...")
        bot_response = wait_for_response(
            brain_bot_client, test_channel, after_ts=message_ts, timeout_seconds=60
        )

        # Assertions
        assert bot_response is not None, "Bot did not respond within 60 seconds"

        response_text = bot_response.get("text", "").lower()
        assert len(response_text) > 0, "Bot response was empty"

        # Verify response contains the answer "4"
        assert "4" in response_text, f"Expected '4' in response, got: {response_text}"

        print(f"✅ Bot responded correctly: {response_text[:100]}...")

    def test_bot_handles_file_attachment(
        self, test_bot_client: WebClient, brain_bot_client: WebClient, test_channel: str
    ):
        """
        Test file attachment handling: Upload a text file and verify bot processes it.

        Scenario:
        1. E2E Tester uploads a .txt file with "Test file content" to Brain Assistant
        2. Includes message "Here's a file for you"
        3. Poll conversations.history for response within 90s (file processing takes longer)
        4. Verify response acknowledges the file

        Expected: Bot responds mentioning the file or its content within 90 seconds

        Note: This test uploads a real file to Slack. The file will remain in the DM
        history after the test completes (we don't clean up test messages).
        """
        # Create a temporary test file
        import tempfile

        test_content = "Test file content for E2E validation"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(test_content)
            tmp_path = tmp.name

        try:
            # Upload file with message
            response = test_bot_client.files_upload_v2(
                channel=test_channel,
                file=tmp_path,
                title="test_e2e.txt",
                initial_comment="Here's a file for you",
            )

            # Get the message timestamp from the file upload
            # files_upload_v2 returns the file object, we need to get the message ts
            file_info = response.get("file", {})
            # For file uploads, we need to wait a bit and then look for the message
            time.sleep(2)

            # Get latest message timestamp as reference point
            history = test_bot_client.conversations_history(channel=test_channel, limit=1)
            message_ts = history["messages"][0]["ts"]

            print(f"✉️  Uploaded test file: test_e2e.txt (ts={message_ts})")

        except SlackApiError as e:
            pytest.fail(f"Failed to upload file: {e.response['error']}")
        finally:
            # Clean up temporary file
            os.unlink(tmp_path)

        # Wait for response (file processing takes longer)
        print("⏳ Waiting for bot response (file processing)...")
        bot_response = wait_for_response(
            brain_bot_client, test_channel, after_ts=message_ts, timeout_seconds=90
        )

        # Assertions
        assert bot_response is not None, "Bot did not respond within 90 seconds"

        response_text = bot_response.get("text", "").lower()
        assert len(response_text) > 0, "Bot response was empty"

        # Verify response acknowledges the file
        # Could mention "file", "attachment", or the actual content
        has_file_reference = any(
            keyword in response_text
            for keyword in ["file", "attachment", "content", "test_e2e"]
        )

        assert (
            has_file_reference
        ), f"Expected file acknowledgment in response, got: {response_text}"

        print(f"✅ Bot processed file attachment: {response_text[:100]}...")
