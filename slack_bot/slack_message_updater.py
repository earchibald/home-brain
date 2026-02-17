"""
Slack message updater for incrementally updating messages with streaming content.

Includes:
  - Legacy functional helpers (update_message_with_stream, stream_response_to_slack)
  - SlackMessageUpdater class with Slack Assistant Framework support
    (setStatus, setTitle, setSuggestedPrompts)
"""

import logging
from typing import Generator
import time

from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


# ==================================================================
# Class-based updater (used by Assistant Framework integration)
# ==================================================================

class SlackMessageUpdater:
    """Handles sending and updating messages in Slack.

    Supports both legacy chat_postMessage / chat_update flows and the
    new Assistant Framework methods (setStatus, setTitle, setSuggestedPrompts).
    """

    def __init__(self, client):
        self.client = client

    # --- Standard message helpers ---

    async def send_initial_message(
        self, channel_id: str, text: str, thread_ts: str = None
    ) -> str:
        """Send an initial message (e.g. 'Thinking...') and return its ts."""
        try:
            response = await self.client.chat_postMessage(
                channel=channel_id, text=text, thread_ts=thread_ts
            )
            return response["ts"]
        except SlackApiError as e:
            logger.error(f"Error sending initial message: {e}")
            raise

    async def update_message(self, channel_id: str, ts: str, text: str):
        """Update an existing message with new text."""
        try:
            await self.client.chat_update(channel=channel_id, ts=ts, text=text)
        except SlackApiError as e:
            logger.error(f"Error updating message: {e}")

    async def send_final_message(
        self, channel_id: str, thread_ts: str, text: str
    ):
        """Send a final new message (useful when status was used instead of placeholder)."""
        try:
            await self.client.chat_postMessage(
                channel=channel_id, text=text, thread_ts=thread_ts
            )
        except SlackApiError as e:
            logger.error(f"Error sending final message: {e}")

    async def send_error_message(
        self, channel_id: str, thread_ts: str, text: str
    ):
        """Send a warning-prefixed error message."""
        try:
            await self.client.chat_postMessage(
                channel=channel_id,
                text=f":warning: {text}",
                thread_ts=thread_ts,
            )
        except SlackApiError as e:
            logger.error(f"Error sending error message: {e}")

    # --- Slack Assistant Framework methods ---

    async def set_assistant_status(
        self, channel_id: str, thread_ts: str, status: str
    ):
        """Set the 'Thinking...' status indicator for an Assistant thread.

        This replaces the need for a temporary 'Thinking...' message.
        The status clears automatically when a new message is posted.
        """
        try:
            await self.client.assistant_threads_setStatus(
                channel_id=channel_id,
                thread_ts=thread_ts,
                status=status,
            )
        except SlackApiError as e:
            logger.error(f"Error setting assistant status: {e}")

    async def set_assistant_title(
        self, channel_id: str, thread_ts: str, title: str
    ):
        """Rename the Assistant thread."""
        try:
            await self.client.assistant_threads_setTitle(
                channel_id=channel_id,
                thread_ts=thread_ts,
                title=title,
            )
        except SlackApiError as e:
            logger.error(f"Error setting assistant title: {e}")

    async def set_suggested_prompts(
        self, channel_id: str, thread_ts: str, prompts: list
    ):
        """Set the quick-start prompts for the thread.

        Args:
            prompts: List of dicts with 'title' and 'message' keys.
        """
        try:
            await self.client.assistant_threads_setSuggestedPrompts(
                channel_id=channel_id,
                thread_ts=thread_ts,
                prompts=prompts,
            )
        except SlackApiError as e:
            logger.error(f"Error setting suggested prompts: {e}")


# Buffer for batching updates (don't update too frequently)
UPDATE_BATCH_SIZE = 500  # characters
UPDATE_MIN_INTERVAL = 0.5  # seconds


def update_message_with_stream(
    client, channel: str, message_ts: str, content: str
) -> None:
    """
    Update a Slack message with streamed content.

    Args:
        client: Slack client instance
        channel: Channel ID
        message_ts: Message timestamp
        content: Content to append/update
    """
    try:
        client.chat_update(channel=channel, ts=message_ts, text=content)
    except Exception:
        # Log but don't fail - streaming continues even if update fails
        pass


def stream_response_to_slack(
    client, channel: str, message_ts: str, stream_generator: Generator[str, None, None]
) -> str:
    """
    Stream response chunks to Slack, batching updates for reasonable frequency.

    Args:
        client: Slack client instance
        channel: Channel ID
        message_ts: Message timestamp to update
        stream_generator: Generator yielding response chunks

    Returns:
        Final accumulated response
    """
    accumulated = ""
    last_update_time = time.time()
    batch_buffer = ""

    for chunk in stream_generator:
        # Add chunk to accumulated response and buffer
        accumulated += chunk
        batch_buffer += chunk

        current_time = time.time()
        time_since_update = current_time - last_update_time

        # Update if we have enough content or enough time has passed
        should_update = (
            len(batch_buffer) >= UPDATE_BATCH_SIZE
            or time_since_update >= UPDATE_MIN_INTERVAL
        )

        if should_update:
            update_message_with_stream(client, channel, message_ts, accumulated)
            batch_buffer = ""
            last_update_time = current_time

    # Final update with complete content
    if batch_buffer or not accumulated:
        update_message_with_stream(client, channel, message_ts, accumulated)

    return accumulated
