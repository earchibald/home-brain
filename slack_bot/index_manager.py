"""
Slack Modal UI builder for index management.

Uses Slack modals (views.open / views.update / views.push) for a polished,
responsive experience.  All public functions return view payloads suitable
for the Slack Web API views.* methods.
"""

import json
import math
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_SIZE = 10  # Documents per page in the browser

# Action IDs for interactive components inside modals
ACTION_BROWSE = "index_browse"
ACTION_PAGE_NEXT = "index_page_next"
ACTION_PAGE_PREV = "index_page_prev"
ACTION_DOC_IGNORE = "index_doc_ignore"
ACTION_DOC_DELETE = "index_doc_delete"
ACTION_FILTER_FOLDER = "index_filter_folder"
ACTION_SHOW_SETUP = "index_show_setup"
ACTION_REINDEX = "index_reindex"
ACTION_BACK_DASHBOARD = "index_back_dashboard"

# Callback IDs for view submissions
CALLBACK_GATE_SETUP = "index_gate_setup_submit"
CALLBACK_CONFIRM_DELETE = "index_confirm_delete_submit"

# Keep old constants for backwards-compat in imports
ACTION_SETUP_SUBMIT = "index_setup_submit"
ACTION_CONFIRM_DELETE = "index_confirm_delete"
ACTION_CANCEL_DELETE = "index_cancel_delete"


# ---------------------------------------------------------------------------
# Loading view  (shown instantly while data fetches)
# ---------------------------------------------------------------------------


def build_loading_view(message: str = "Loading index manager...") -> Dict:
    """Build a lightweight modal view shown while data is being fetched."""
    return {
        "type": "modal",
        "callback_id": "index_loading",
        "title": {"type": "plain_text", "text": "Index Manager"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⏳ *{message}*",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_Fetching data from semantic search service..._",
                    }
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Dashboard  (main view for /index)
# ---------------------------------------------------------------------------


def build_index_dashboard(stats: Dict[str, Any]) -> Dict:
    """Build the main dashboard modal view for /index.

    Args:
        stats: Dict from registry_stats endpoint with keys:
               total_files, total_chunks, gates, ignored_count

    Returns:
        Modal view payload for views.open / views.update
    """
    total_files = stats.get("total_files", 0)
    total_chunks = stats.get("total_chunks", 0)
    ignored_count = stats.get("ignored_count", 0)
    gates = stats.get("gates", {})

    blocks: List[Dict] = []

    # Stats bar
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"📄 *{total_files}* files  ·  "
                f"🧩 *{total_chunks}* chunks  ·  "
                f"🚫 *{ignored_count}* ignored"
            ),
        },
    })

    blocks.append({"type": "divider"})

    # Gate summary
    if gates:
        gate_lines = []
        for directory, mode in sorted(gates.items()):
            icon = "🔒" if mode == "readonly" else "📝"
            gate_lines.append(f"{icon}  `{directory}` → _{mode}_")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Directory Gates*\n" + "\n".join(gate_lines),
            },
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Directory Gates*\n_None configured — all directories are read/write._",
            },
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
                "value": "0",
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

    return {
        "type": "modal",
        "callback_id": "index_dashboard",
        "title": {"type": "plain_text", "text": "Index Manager"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# Document Browser (paged list inside a modal)
# ---------------------------------------------------------------------------


def build_document_browser(
    items: List[Dict[str, Any]],
    total: int,
    offset: int,
    limit: int,
    folder_filter: Optional[str] = None,
) -> Dict:
    """Build a paged document listing as a modal view.

    Returns:
        Modal view payload for views.update
    """
    blocks: List[Dict] = []

    current_page = (offset // limit) + 1
    total_pages = max(1, math.ceil(total / limit))
    filter_label = f" in `{folder_filter}`" if folder_filter else ""

    # Header context
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"📄 *{total} documents{filter_label}*  ·  "
                    f"Page {current_page} of {total_pages}"
                ),
            }
        ],
    })

    blocks.append({"type": "divider"})

    if not items:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_No documents found._"},
        })
    else:
        for doc in items:
            path = doc.get("path", "")
            chunks = doc.get("chunks", 0)
            size_kb = doc.get("size", 0) / 1024
            gate = doc.get("gate", "ungated")

            gate_badge = ""
            if gate == "readonly":
                gate_badge = "  🔒"
            elif gate == "readwrite":
                gate_badge = "  📝"

            doc_text = f"`{path}`{gate_badge}\n{chunks} chunks · {size_kb:.1f} KB"

            # Action buttons per document — use unique action_ids
            elements: List[Dict] = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Ignore"},
                    "action_id": f"{ACTION_DOC_IGNORE}_{path}",
                    "value": path,
                },
            ]

            if gate != "readonly":
                elements.append({
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Delete"},
                    "action_id": f"{ACTION_DOC_DELETE}_{path}",
                    "value": path,
                    "style": "danger",
                })

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": doc_text},
            })
            blocks.append({"type": "actions", "elements": elements})

    blocks.append({"type": "divider"})

    # Pagination nav
    nav_elements: List[Dict] = []
    if offset > 0:
        prev_offset = max(0, offset - limit)
        nav_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "⬅️ Previous"},
            "action_id": ACTION_PAGE_NEXT if False else ACTION_PAGE_PREV,
            "value": f"{prev_offset}|{folder_filter or ''}",
        })

    nav_elements.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "🏠 Dashboard"},
        "action_id": ACTION_BACK_DASHBOARD,
        "value": "0",
    })

    if offset + limit < total:
        next_offset = offset + limit
        nav_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Next ➡️"},
            "action_id": ACTION_PAGE_NEXT,
            "value": f"{next_offset}|{folder_filter or ''}",
        })

    blocks.append({"type": "actions", "elements": nav_elements})

    # Carry pagination state in private_metadata
    metadata = json.dumps({
        "offset": offset,
        "folder_filter": folder_filter,
    })

    return {
        "type": "modal",
        "callback_id": "index_document_browser",
        "title": {"type": "plain_text", "text": "Documents"},
        "close": {"type": "plain_text", "text": "Close"},
        "private_metadata": metadata,
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# Delete Confirmation  (pushed on top of browser)
# ---------------------------------------------------------------------------


def build_delete_confirmation(file_path: str) -> Dict:
    """Build a pushed confirmation view before deleting a file.

    Returns:
        Modal view payload for views.push
    """
    metadata = json.dumps({"file_path": file_path})

    return {
        "type": "modal",
        "callback_id": CALLBACK_CONFIRM_DELETE,
        "title": {"type": "plain_text", "text": "Confirm Delete"},
        "submit": {"type": "plain_text", "text": "Yes, Delete"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": metadata,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "⚠️ *Are you sure?*\n\n"
                        f"This will permanently delete `{file_path}` from disk "
                        "and remove all index entries.\n\n"
                        "*This cannot be undone.*"
                    ),
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Gate Setup  (pushed view with input + submit)
# ---------------------------------------------------------------------------


def build_gate_setup(current_gates: Dict[str, str]) -> Dict:
    """Build the gate configuration view as a pushed modal.

    Returns:
        Modal view payload for views.push (has submit button)
    """
    if current_gates:
        initial_value = "\n".join(
            f"{d} = {m}" for d, m in sorted(current_gates.items())
        )
    else:
        initial_value = "journal = readonly\nprojects = readwrite"

    return {
        "type": "modal",
        "callback_id": CALLBACK_GATE_SETUP,
        "title": {"type": "plain_text", "text": "Gate Setup"},
        "submit": {"type": "plain_text", "text": "💾 Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "Configure which directories are *read-only* "
                        "(can un-index but not delete) vs *read-write* "
                        "(can delete from disk).\n\n"
                        "One gate per line:  `directory = readonly`  or  "
                        "`directory = readwrite`"
                    ),
                },
            },
            {
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
            },
        ],
    }


# ---------------------------------------------------------------------------
# Feedback / status views  (update the current modal in-place)
# ---------------------------------------------------------------------------


def build_status_view(
    title: str,
    message: str,
    *,
    emoji: str = "✅",
    show_back: bool = True,
) -> Dict:
    """Build a simple status/feedback modal view.

    Args:
        title: Modal title bar text (max 24 chars)
        message: Body text (mrkdwn)
        emoji: Status emoji prefix
        show_back: Whether to show a "Back to Dashboard" button

    Returns:
        Modal view payload for views.update
    """
    blocks: List[Dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{emoji} {message}"},
        },
    ]

    if show_back:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🏠 Dashboard"},
                    "action_id": ACTION_BACK_DASHBOARD,
                    "value": "0",
                },
            ],
        })

    return {
        "type": "modal",
        "callback_id": "index_status",
        "title": {"type": "plain_text", "text": title[:24]},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def parse_gate_config_text(text: str) -> Dict[str, str]:
    """Parse gate config text area into a dict.

    Accepts lines like:
        journal = readonly
        projects = readwrite
        # comments and blank lines are ignored

    Raises:
        ValueError: If a line has invalid format or mode.
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
                f"Line {line_num}: Invalid mode '{mode}'. "
                "Must be 'readonly' or 'readwrite'."
            )

        gates[directory] = mode

    return gates
