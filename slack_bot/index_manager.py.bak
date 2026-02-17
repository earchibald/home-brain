"""
Slack Block Kit UI builder for index management.

Provides helper functions for the /index command: browsing indexed documents,
performing actions (ignore, delete), viewing stats, and configuring gates.
"""

import math
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_SIZE = 10  # Documents per page in the browser

# Action ID prefixes (must match handler registrations in slack_agent.py)
ACTION_BROWSE = "index_browse"
ACTION_PAGE_NEXT = "index_page_next"
ACTION_PAGE_PREV = "index_page_prev"
ACTION_DOC_IGNORE = "index_doc_ignore"
ACTION_DOC_DELETE = "index_doc_delete"
ACTION_FILTER_FOLDER = "index_filter_folder"
ACTION_SHOW_SETUP = "index_show_setup"
ACTION_SETUP_SUBMIT = "index_setup_submit"
ACTION_REINDEX = "index_reindex"
ACTION_CONFIRM_DELETE = "index_confirm_delete"
ACTION_CANCEL_DELETE = "index_cancel_delete"


# ---------------------------------------------------------------------------
# Dashboard (entry point for /index)
# ---------------------------------------------------------------------------


def build_index_dashboard(stats: Dict[str, Any]) -> List[Dict]:
    """Build the main dashboard shown when the user runs /index.

    Args:
        stats: Dict from registry_stats endpoint with keys:
               total_files, total_chunks, gates, ignored_count

    Returns:
        Block Kit blocks list
    """
    blocks: List[Dict] = []

    total_files = stats.get("total_files", 0)
    total_chunks = stats.get("total_chunks", 0)
    ignored_count = stats.get("ignored_count", 0)
    gates = stats.get("gates", {})

    # Header
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "📚 Brain Index Manager"},
    })

    # Stats section
    stats_text = (
        f"*Indexed Files:* {total_files}  |  "
        f"*Chunks:* {total_chunks}  |  "
        f"*Ignored:* {ignored_count}"
    )
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": stats_text},
    })

    # Gate summary
    if gates:
        gate_lines = []
        for directory, mode in sorted(gates.items()):
            icon = "🔒" if mode == "readonly" else "📝"
            gate_lines.append(f"{icon} `{directory}` → {mode}")
        gate_text = "*Directory Gates:*\n" + "\n".join(gate_lines)
    else:
        gate_text = "*Directory Gates:* _None configured — all directories are read/write._"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": gate_text},
    })

    blocks.append({"type": "divider"})

    # Action buttons
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "📂 Browse Documents"},
                "action_id": ACTION_BROWSE,
                "value": "0",  # offset
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "⚙️ Setup Gates"},
                "action_id": ACTION_SHOW_SETUP,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🔄 Reindex All"},
                "action_id": ACTION_REINDEX,
                "style": "primary",
            },
        ],
    })

    return blocks


# ---------------------------------------------------------------------------
# Document Browser (paged list)
# ---------------------------------------------------------------------------


def build_document_browser(
    items: List[Dict[str, Any]],
    total: int,
    offset: int,
    limit: int,
    folder_filter: Optional[str] = None,
) -> List[Dict]:
    """Build a paged document listing with per-doc action buttons.

    Args:
        items: List of document dicts from the API (path, chunks, size, gate, indexed_at).
        total: Total number of matching documents.
        offset: Current offset.
        limit: Page size.
        folder_filter: Current folder filter, or None.

    Returns:
        Block Kit blocks list
    """
    blocks: List[Dict] = []

    current_page = (offset // limit) + 1
    total_pages = max(1, math.ceil(total / limit))
    filter_label = f" in `{folder_filter}`" if folder_filter else ""

    # Header
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*Indexed Documents{filter_label}*  —  "
                f"Page {current_page}/{total_pages}  ({total} files)"
            ),
        },
    })

    blocks.append({"type": "divider"})

    if not items:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_No documents found._"},
        })
        return blocks

    # Document rows
    for doc in items:
        path = doc.get("path", "")
        chunks = doc.get("chunks", 0)
        size_kb = doc.get("size", 0) / 1024
        gate = doc.get("gate", "ungated")
        gate_icon = "🔒" if gate == "readonly" else ("📝" if gate == "readwrite" else "")

        doc_text = f"`{path}`  —  {chunks} chunks, {size_kb:.1f} KB {gate_icon}"

        # Determine available actions based on gate
        elements: List[Dict] = []

        # "Ignore" is always available (removes from index, not from disk)
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "👁️ Ignore"},
            "action_id": ACTION_DOC_IGNORE,
            "value": path,
        })

        # "Delete" only available for non-readonly
        if gate != "readonly":
            elements.append({
                "type": "button",
                "text": {"type": "plain_text", "text": "🗑️ Delete"},
                "action_id": ACTION_DOC_DELETE,
                "value": path,
                "style": "danger",
            })

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": doc_text},
        })
        if elements:
            blocks.append({"type": "actions", "elements": elements})

    blocks.append({"type": "divider"})

    # Pagination buttons
    nav_elements: List[Dict] = []

    if offset > 0:
        prev_offset = max(0, offset - limit)
        nav_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "⬅️ Previous"},
            "action_id": ACTION_PAGE_PREV,
            "value": f"{prev_offset}|{folder_filter or ''}",
        })

    if offset + limit < total:
        next_offset = offset + limit
        nav_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Next ➡️"},
            "action_id": ACTION_PAGE_NEXT,
            "value": f"{next_offset}|{folder_filter or ''}",
        })

    if nav_elements:
        blocks.append({"type": "actions", "elements": nav_elements})

    return blocks


# ---------------------------------------------------------------------------
# Confirmation dialog for delete
# ---------------------------------------------------------------------------


def build_delete_confirmation(file_path: str, gate: str) -> List[Dict]:
    """Build a confirmation prompt before deleting a file from disk.

    Args:
        file_path: The document path.
        gate: Current gate mode for the document's directory.

    Returns:
        Block Kit blocks list
    """
    blocks: List[Dict] = []

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"⚠️ *Are you sure you want to delete this file?*\n\n"
                f"`{file_path}`\n\n"
                f"This will *permanently remove the file from disk* and "
                f"remove all index entries. This cannot be undone."
            ),
        },
    })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Yes, Delete"},
                "action_id": ACTION_CONFIRM_DELETE,
                "value": file_path,
                "style": "danger",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Cancel"},
                "action_id": ACTION_CANCEL_DELETE,
                "value": file_path,
            },
        ],
    })

    return blocks


# ---------------------------------------------------------------------------
# Gate Setup UI
# ---------------------------------------------------------------------------


def build_gate_setup(current_gates: Dict[str, str]) -> List[Dict]:
    """Build the gate configuration UI.

    Shows current gates and provides a text area for editing them in a simple
    line-by-line format:  directory = mode

    Args:
        current_gates: Current gate mapping {directory: mode}.

    Returns:
        Block Kit blocks list
    """
    blocks: List[Dict] = []

    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "⚙️ Directory Gate Configuration"},
    })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                "Configure which directories are *read-only* (can unindex but not delete files) "
                "and which are *read-write* (can delete files from disk).\n\n"
                "Ungated directories default to read-write.\n\n"
                "*Format:* One gate per line: `directory = readonly` or `directory = readwrite`\n"
                "*Example:*\n```\njournal = readonly\nprojects = readwrite\narchive = readonly\n```"
            ),
        },
    })

    # Pre-fill current gates
    if current_gates:
        initial_value = "\n".join(
            f"{d} = {m}" for d, m in sorted(current_gates.items())
        )
    else:
        initial_value = "journal = readonly\nprojects = readwrite"

    blocks.append({
        "type": "input",
        "block_id": "gate_config_block",
        "label": {"type": "plain_text", "text": "Gate Rules"},
        "element": {
            "type": "plain_text_input",
            "action_id": "gate_config_input",
            "multiline": True,
            "initial_value": initial_value,
            "placeholder": {
                "type": "plain_text",
                "text": "journal = readonly\nprojects = readwrite",
            },
        },
    })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "💾 Save Gates"},
                "action_id": ACTION_SETUP_SUBMIT,
                "style": "primary",
            },
        ],
    })

    return blocks


def parse_gate_config_text(text: str) -> Dict[str, str]:
    """Parse the gate config text area into a dict.

    Accepts lines like:
        journal = readonly
        projects = readwrite
        # comments are ignored
        (blank lines are ignored)

    Args:
        text: Raw text from the Slack input.

    Returns:
        Dict mapping directory → mode.

    Raises:
        ValueError: If a line has an invalid format or mode.
    """
    gates: Dict[str, str] = {}
    valid_modes = {"readonly", "readwrite"}

    for line_num, line in enumerate(text.strip().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise ValueError(
                f"Line {line_num}: Expected 'directory = mode', got: {line}"
            )

        directory, _, mode = line.partition("=")
        directory = directory.strip().strip("/")
        mode = mode.strip().lower()

        if not directory:
            raise ValueError(f"Line {line_num}: Empty directory name")
        if mode not in valid_modes:
            raise ValueError(
                f"Line {line_num}: Invalid mode '{mode}'. Must be 'readonly' or 'readwrite'."
            )

        gates[directory] = mode

    return gates
