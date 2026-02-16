"""
Slack User Client - Act as a real user in Slack programmatically.

Sends DMs to Brain Assistant (or any bot) using a Slack User Token (xoxp-),
so the bot sees a genuine human message. Supports single-shot and multi-turn
conversations with polling-based response capture.

All tokens are retrieved from Vaultwarden exclusively - no environment
variable fallback.
"""

import time
from typing import Optional, Dict, Any, List
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackUserClientError(Exception):
    """Base exception for SlackUserClient errors."""
    pass


class SlackAuthError(SlackUserClientError):
    """Raised when Slack authentication fails."""
    pass


class BotResponseTimeout(SlackUserClientError):
    """Raised when the bot doesn't respond within the timeout period."""
    pass


class SlackUserClient:
    """Client that acts as a real Slack user to interact with bots.

    Uses a User OAuth Token (xoxp-) to send messages as the user and
    polls conversations.history to capture bot replies.

    All tokens are loaded from Vaultwarden - no fallback to environment
    variables.
    """

    DEFAULT_TIMEOUT = 60
    DEFAULT_POLL_INTERVAL = 2

    def __init__(
        self,
        user_token: Optional[str] = None,
        bot_user_id: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ):
        """Initialize the Slack User Client.

        Args:
            user_token: Slack user OAuth token (xoxp-). If None, loads from Vaultwarden.
            bot_user_id: User ID of the bot to interact with. If None, loads from Vaultwarden.
            timeout: Default timeout in seconds for waiting on bot responses.
            poll_interval: Seconds between polling attempts.
        """
        self.timeout = timeout
        self.poll_interval = poll_interval

        # Load token from Vaultwarden if not provided directly
        if user_token is None:
            user_token = self._load_from_vaultwarden("SLACK_USER_TOKEN")
        if bot_user_id is None:
            bot_user_id = self._load_from_vaultwarden("BRAIN_BOT_USER_ID")

        self.bot_user_id = bot_user_id
        self._client = WebClient(token=user_token)
        self._dm_channel_id: Optional[str] = None

        # Verify auth on init
        try:
            auth = self._client.auth_test()
            self.user_id = auth["user_id"]
        except SlackApiError as e:
            raise SlackAuthError(f"Failed to authenticate with Slack: {e.response['error']}")

    @staticmethod
    def _load_from_vaultwarden(key: str) -> str:
        """Load a secret from Vaultwarden. No fallback."""
        from clients.vaultwarden_client import get_client
        client = get_client()
        return client.get_secret(key)

    def _ensure_dm_channel(self) -> str:
        """Open or retrieve the DM channel with the bot."""
        if self._dm_channel_id is not None:
            return self._dm_channel_id

        try:
            result = self._client.conversations_open(users=[self.bot_user_id])
            self._dm_channel_id = result["channel"]["id"]
            return self._dm_channel_id
        except SlackApiError as e:
            raise SlackUserClientError(
                f"Failed to open DM channel with bot {self.bot_user_id}: {e.response['error']}"
            )

    def _send_message(self, text: str, thread_ts: Optional[str] = None) -> str:
        """Send a message to the bot's DM channel.

        Args:
            text: Message text to send.
            thread_ts: Thread timestamp for threaded replies.

        Returns:
            Message timestamp (ts) of the sent message.
        """
        channel = self._ensure_dm_channel()
        kwargs: Dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        try:
            result = self._client.chat_postMessage(**kwargs)
            return result["ts"]
        except SlackApiError as e:
            raise SlackUserClientError(f"Failed to send message: {e.response['error']}")

    def _poll_for_response(
        self,
        after_ts: str,
        thread_ts: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Poll conversations.history for a bot response.

        Args:
            after_ts: Only consider messages after this timestamp.
            thread_ts: If set, poll thread replies instead of channel history.
            timeout: Override default timeout.

        Returns:
            Dict with the bot's response message data.

        Raises:
            BotResponseTimeout: If no response within timeout.
        """
        timeout = timeout or self.timeout
        channel = self._ensure_dm_channel()
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                if thread_ts:
                    result = self._client.conversations_replies(
                        channel=channel, ts=thread_ts, oldest=after_ts, limit=20
                    )
                else:
                    result = self._client.conversations_history(
                        channel=channel, oldest=after_ts, limit=10
                    )

                messages = result.get("messages", [])
                for msg in messages:
                    msg_user = msg.get("user", "")
                    msg_text = msg.get("text", "").lower().strip()
                    
                    # Skip "Working..." indicator messages
                    if "working" in msg_text[:30] and len(msg_text) < 50:
                        continue
                    
                    # Accept messages from the bot (by user ID or bot_id presence)
                    is_from_bot = msg_user == self.bot_user_id
                    has_bot_id = bool(msg.get("bot_id")) and msg_user != self.user_id
                    if is_from_bot or has_bot_id:
                        return msg

            except SlackApiError as e:
                # Rate limiting - back off
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 5))
                    time.sleep(retry_after)
                    continue
                raise SlackUserClientError(f"Error polling for response: {e.response['error']}")

            time.sleep(self.poll_interval)

        raise BotResponseTimeout(
            f"Bot did not respond within {timeout} seconds"
        )

    def ask(self, message: str, timeout: Optional[int] = None) -> str:
        """Send a message and wait for the bot's response.

        Args:
            message: Text to send to the bot.
            timeout: Override default timeout in seconds.

        Returns:
            The bot's response text.
        """
        send_ts = self._send_message(message)
        response = self._poll_for_response(after_ts=send_ts, timeout=timeout)
        return response.get("text", "")

    def ask_raw(self, message: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Send a message and return the full bot response message object.

        Args:
            message: Text to send to the bot.
            timeout: Override default timeout in seconds.

        Returns:
            Full Slack message dict from the bot.
        """
        send_ts = self._send_message(message)
        return self._poll_for_response(after_ts=send_ts, timeout=timeout)

    def conversation(self) -> "Conversation":
        """Start a multi-turn conversation with the bot.

        Returns:
            Conversation context manager for multi-turn exchanges.
        """
        return Conversation(self)


class Conversation:
    """Multi-turn conversation with a bot, maintaining thread context.

    Usage:
        convo = client.conversation()
        r1 = convo.ask("Hello")
        r2 = convo.ask("Tell me more")  # same thread
        convo.close()

    Or as a context manager:
        with client.conversation() as convo:
            r1 = convo.ask("Hello")
            r2 = convo.ask("Follow up")
    """

    def __init__(self, client: SlackUserClient):
        self._client = client
        self._thread_ts: Optional[str] = None
        self._history: List[Dict[str, str]] = []

    def __enter__(self) -> "Conversation":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def ask(self, message: str, timeout: Optional[int] = None) -> str:
        """Send a message in this conversation thread and wait for response.

        The first message starts a new thread. Subsequent messages reply
        in the same thread, preserving conversation context.

        Args:
            message: Text to send.
            timeout: Override default timeout.

        Returns:
            The bot's response text.
        """
        send_ts = self._client._send_message(message, thread_ts=self._thread_ts)

        # First message establishes the thread
        if self._thread_ts is None:
            self._thread_ts = send_ts

        response = self._client._poll_for_response(
            after_ts=send_ts,
            thread_ts=self._thread_ts,
            timeout=timeout,
        )

        response_text = response.get("text", "")
        self._history.append({"role": "user", "content": message})
        self._history.append({"role": "assistant", "content": response_text})

        return response_text

    def ask_raw(self, message: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Send a message and return the full response message object."""
        send_ts = self._client._send_message(message, thread_ts=self._thread_ts)

        if self._thread_ts is None:
            self._thread_ts = send_ts

        response = self._client._poll_for_response(
            after_ts=send_ts,
            thread_ts=self._thread_ts,
            timeout=timeout,
        )

        response_text = response.get("text", "")
        self._history.append({"role": "user", "content": message})
        self._history.append({"role": "assistant", "content": response_text})

        return response

    @property
    def history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return list(self._history)

    @property
    def thread_ts(self) -> Optional[str]:
        """Get the thread timestamp for this conversation."""
        return self._thread_ts

    def close(self) -> None:
        """Close the conversation (no-op, but signals intent)."""
        pass
