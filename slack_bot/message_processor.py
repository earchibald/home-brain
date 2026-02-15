"""
Message processor for detecting and extracting file information from Slack messages.
"""

from typing import List, Dict, Any
import os


def detect_file_attachments(message_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Detect file attachments in a Slack message.

    Args:
        message_data: Message event data from Slack

    Returns:
        List of file attachment info with name, type, and URL
    """
    attachments = []

    files = message_data.get("files", [])
    for file_obj in files:
        file_name = file_obj.get("name", "")
        if not file_name:
            continue

        # Extract file extension
        _, ext = os.path.splitext(file_name)
        file_type = ext.lstrip(".").lower() if ext else ""

        attachment = {
            "name": file_name,
            "type": file_type,
            "url_private_download": file_obj.get("url_private_download"),
            "mimetype": file_obj.get("mimetype"),
            "size": file_obj.get("size", 0),
        }
        attachments.append(attachment)

    return attachments
