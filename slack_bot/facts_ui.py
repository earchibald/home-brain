"""
Slack Block Kit UI builder for /facts management.

Provides helper functions to build the FACTS management modal,
following the index_manager.py pattern for multi-item list + actions.
"""

import logging
from typing import Dict, List, Optional

from slack_bot.tools.builtin.facts_tool import FactsStore

logger = logging.getLogger(__name__)


def build_facts_ui(user_id: str, storage_dir: Optional[str] = None) -> List[Dict]:
    """Build Block Kit blocks for the /facts management modal.

    Shows all stored facts with edit/delete actions.

    Args:
        user_id: Slack user ID
        storage_dir: Optional custom storage directory

    Returns:
        List of Block Kit block dicts
    """
    store = FactsStore(user_id, storage_dir=storage_dir)
    facts = store.list_facts()

    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "🧠 Your Stored Facts"},
    })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                "Facts are persistent memories about you that the AI uses to "
                "personalize responses. You can add, edit, or delete them."
            ),
        },
    })

    blocks.append({"type": "divider"})

    if not facts:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "No facts stored yet. The AI will learn about you as you chat, "
                    "or you can add facts manually below."
                ),
            },
        })
    else:
        for fact in facts:
            key = fact.get("key", "")
            value = fact.get("value", "")
            category = fact.get("category", "other")
            updated = fact.get("last_updated", "")[:10]

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*[{category}]* `{key}`\n{value}\n_Updated: {updated}_",
                },
                "accessory": {
                    "type": "overflow",
                    "action_id": f"fact_overflow_{key}",
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "✏️ Edit"},
                            "value": f"edit:{key}",
                        },
                        {
                            "text": {"type": "plain_text", "text": "🗑️ Delete"},
                            "value": f"delete:{key}",
                        },
                    ],
                },
            })

    blocks.append({"type": "divider"})

    # Action buttons
    action_elements = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "➕ Add Fact"},
            "action_id": "facts_add_new",
            "style": "primary",
        },
    ]

    if facts:
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "🗑️ Clear All"},
            "action_id": "facts_clear_all",
            "style": "danger",
            "confirm": {
                "title": {"type": "plain_text", "text": "Clear all facts?"},
                "text": {
                    "type": "mrkdwn",
                    "text": f"This will permanently delete all {len(facts)} stored facts.",
                },
                "confirm": {"type": "plain_text", "text": "Yes, clear all"},
                "deny": {"type": "plain_text", "text": "Cancel"},
            },
        })

    blocks.append({
        "type": "actions",
        "elements": action_elements,
    })

    return blocks


def build_fact_edit_view(
    user_id: str,
    key: str = "",
    value: str = "",
    category: str = "other",
    storage_dir: Optional[str] = None,
) -> List[Dict]:
    """Build Block Kit blocks for the fact add/edit form.

    Used as an update_view replacement (not a pushed modal).

    Args:
        user_id: Slack user ID
        key: Pre-filled key (empty for new fact)
        value: Pre-filled value
        category: Pre-filled category
        storage_dir: Optional custom storage directory

    Returns:
        List of Block Kit block dicts
    """
    is_edit = bool(key)
    title = f"Edit Fact: {key}" if is_edit else "Add New Fact"

    from slack_bot.tools.builtin.facts_tool import VALID_CATEGORIES

    category_options = [
        {"text": {"type": "plain_text", "text": cat}, "value": cat}
        for cat in sorted(VALID_CATEGORIES)
    ]

    initial_category = None
    for opt in category_options:
        if opt["value"] == category:
            initial_category = opt
            break

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title},
        },
        {
            "type": "input",
            "block_id": "fact_key_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "fact_key_input",
                "placeholder": {"type": "plain_text", "text": "e.g., preferred_coffee"},
                **({"initial_value": key} if key else {}),
            },
            "label": {"type": "plain_text", "text": "Key"},
        },
        {
            "type": "input",
            "block_id": "fact_value_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "fact_value_input",
                "placeholder": {"type": "plain_text", "text": "e.g., oat milk flat white"},
                "multiline": True,
                **({"initial_value": value} if value else {}),
            },
            "label": {"type": "plain_text", "text": "Value"},
        },
        {
            "type": "input",
            "block_id": "fact_category_block",
            "element": {
                "type": "static_select",
                "action_id": "fact_category_input",
                "placeholder": {"type": "plain_text", "text": "Choose category..."},
                "options": category_options,
                **({"initial_option": initial_category} if initial_category else {}),
            },
            "label": {"type": "plain_text", "text": "Category"},
        },
    ]

    return blocks
