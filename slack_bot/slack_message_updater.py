"""
Slack message updater for incrementally updating messages with streaming content.
"""

from typing import Generator
import time


# Buffer for batching updates (don't update too frequently)
UPDATE_BATCH_SIZE = 500  # characters
UPDATE_MIN_INTERVAL = 0.5  # seconds


def update_message_with_stream(
    client,
    channel: str,
    message_ts: str,
    content: str
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
        client.chat_update(
            channel=channel,
            ts=message_ts,
            text=content
        )
    except Exception:
        # Log but don't fail - streaming continues even if update fails
        pass


def stream_response_to_slack(
    client,
    channel: str,
    message_ts: str,
    stream_generator: Generator[str, None, None]
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
            update_message_with_stream(
                client,
                channel,
                message_ts,
                accumulated
            )
            batch_buffer = ""
            last_update_time = current_time

    # Final update with complete content
    if batch_buffer or not accumulated:
        update_message_with_stream(
            client,
            channel,
            message_ts,
            accumulated
        )

    return accumulated
