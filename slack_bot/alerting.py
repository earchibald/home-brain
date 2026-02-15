"""
Alerting functionality for performance and system issues.
"""

from typing import Optional


def send_performance_alert(
    *args,
    title: str = None,
    message: str = None,
    slack_client=None,
    channel_id: Optional[str] = None,
    **kwargs,
) -> None:
    """
    Send a performance alert via Slack or other notification channels.

    Args:
        *args: Positional arguments (title, message) for compatibility
        title: Alert title
        message: Alert message
        slack_client: Optional Slack client for sending alerts
        channel_id: Optional Slack channel to send alert to
        **kwargs: Additional parameters
    """
    # Handle positional arguments
    if args:
        if len(args) > 0 and not title:
            title = args[0]
        if len(args) > 1 and not message:
            message = args[1]

    # Log the alert
    full_message = f"{title}: {message}" if title and message else str(args)

    # If Slack client provided, send to Slack
    if slack_client and channel_id:
        try:
            slack_client.chat_postMessage(channel=channel_id, text=f"⚠️ {full_message}")
        except Exception:
            # Log but don't fail if Slack notification fails
            pass
