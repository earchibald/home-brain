"""
File uploader for saving Slack files to brain index.

Handles downloading files from Slack and uploading them to the
semantic search service for indexing.
"""

import logging
import httpx
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)


# Common directories for quick selection
COMMON_DIRECTORIES = ["notes", "journal", "docs", "work", "learning", "inbox"]


async def download_file_from_slack_async(url: str, token: str) -> bytes:
    """Download a file from Slack using async httpx.

    Args:
        url: File URL (url_private_download from Slack)
        token: Slack bot token for authentication

    Returns:
        File content as bytes

    Raises:
        RuntimeError: If download fails
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(url, headers=headers)
            
            # Handle auth failure - try without auth
            if response.status_code == 401:
                logger.warning("Bearer auth failed (401), retrying without auth")
                response = await client.get(url)
            
            response.raise_for_status()
            
            if not response.content:
                raise RuntimeError("Empty response from Slack file download")
            
            # Check for HTML redirect (login page)
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type:
                raise RuntimeError(f"Got HTML response instead of file - possible expired URL")
            
            logger.info(f"Downloaded {len(response.content)} bytes from Slack")
            return response.content
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (403, 410):
            raise RuntimeError("File link has expired. Please re-upload the file.")
        raise RuntimeError(f"Failed to download file: {e}")
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Unexpected error during download: {e}")


def build_save_to_brain_prompt(files: List[Dict]) -> List[Dict]:
    """Build Block Kit blocks asking if user wants to save files to brain.

    Args:
        files: List of file info dicts with 'name', 'size', 'id'

    Returns:
        List of Block Kit blocks
    """
    if not files:
        return []
    
    file_list = "\n".join(f"• `{f['name']}` ({_format_size(f.get('size', 0))})" for f in files[:5])
    if len(files) > 5:
        file_list += f"\n• ... and {len(files) - 5} more"
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📎 *Files shared:*\n{file_list}",
            },
        },
        {
            "type": "actions",
            "block_id": "save_to_brain_prompt",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "💾 Save to Brain"},
                    "action_id": "save_file_to_brain",
                    "style": "primary",
                    # Store file info in value (will be parsed on click)
                    "value": ",".join(f"{f['id']}|{f['name']}|{f.get('url_private_download', '')}" for f in files[:5]),
                },
            ],
        },
    ]
    return blocks


def build_folder_selection_blocks(files: List[Dict], directories: List[str] = None) -> List[Dict]:
    """Build Block Kit blocks for folder selection.

    Args:
        files: List of file info dicts
        directories: Available directories (defaults to COMMON_DIRECTORIES)

    Returns:
        List of Block Kit blocks
    """
    if directories is None:
        directories = COMMON_DIRECTORIES
    
    file_names = ", ".join(f"`{f['name']}`" for f in files[:3])
    if len(files) > 3:
        file_names += f" +{len(files) - 3} more"
    
    # Create buttons for common directories
    dir_buttons = []
    for dir_name in directories[:5]:
        dir_buttons.append({
            "type": "button",
            "text": {"type": "plain_text", "text": f"📁 {dir_name}"},
            "action_id": f"upload_to_dir_{dir_name}",
            "value": dir_name,
        })
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📂 *Save {file_names} to which folder?*",
            },
        },
        {
            "type": "actions",
            "block_id": "folder_selection",
            "elements": dir_buttons,
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_Or type a custom path like `/notes/project-x`_",
                },
            ],
        },
    ]
    return blocks


def build_upload_result_blocks(results: List[Dict]) -> List[Dict]:
    """Build Block Kit blocks showing upload results.

    Args:
        results: List of upload result dicts with 'path', 'status', 'error'

    Returns:
        List of Block Kit blocks
    """
    lines = []
    for result in results:
        if result.get("status") == "uploaded":
            lines.append(f"✅ `{result['path']}` ({result.get('chunks', 0)} chunks indexed)")
        else:
            error = result.get("error", "Unknown error")
            lines.append(f"❌ `{result.get('path', 'unknown')}`: {error}")
    
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Upload Results:*\n" + "\n".join(lines),
            },
        },
    ]


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def build_save_note_prompt(text_preview: str) -> List[Dict]:
    """Build Block Kit blocks suggesting the user save a note to brain.

    Used when the bot detects that the user shared important personal
    information worth preserving (e.g., strategies, decisions, preferences).

    Args:
        text_preview: A short preview of the text to save (max 2000 chars for Slack value)

    Returns:
        List of Block Kit blocks
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "💡 This looks like something worth saving to your brain for future reference.",
            },
        },
        {
            "type": "actions",
            "block_id": "save_note_prompt",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📝 Save to Brain"},
                    "style": "primary",
                    "action_id": "save_note_to_brain",
                    # Slack limits action values to 2000 chars
                    "value": text_preview[:2000],
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Dismiss"},
                    "action_id": "dismiss_save_note",
                },
            ],
        },
    ]
    return blocks


def build_save_note_folder_blocks(directories: List[str] = None) -> List[Dict]:
    """Build Block Kit blocks for folder selection when saving a note.

    Args:
        directories: Available directories (defaults to COMMON_DIRECTORIES)

    Returns:
        List of Block Kit blocks
    """
    if directories is None:
        directories = COMMON_DIRECTORIES

    dir_buttons = []
    for dir_name in directories[:5]:
        dir_buttons.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": f"📁 {dir_name}"},
                "action_id": f"save_note_dir_{dir_name}",
                "value": dir_name,
            }
        )

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "📂 *Save note to which folder?*",
            },
        },
        {
            "type": "actions",
            "block_id": "note_folder_selection",
            "elements": dir_buttons,
        },
    ]
    return blocks


def parse_file_value(value: str) -> List[Dict]:
    """Parse file info from action value string.

    Args:
        value: Comma-separated file info strings (id|name|url)

    Returns:
        List of file info dicts
    """
    files = []
    for item in value.split(","):
        parts = item.split("|", 2)
        if len(parts) >= 2:
            files.append({
                "id": parts[0],
                "name": parts[1],
                "url": parts[2] if len(parts) > 2 else "",
            })
    return files
