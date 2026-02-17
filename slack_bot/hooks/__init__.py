"""
Agent hooks for Brain Assistant.

These hooks leverage the Phase 7 hook infrastructure to enhance responses:
- source_tracker: Track which tools were used during processing
- citation_hook: Add source citations to responses
- intent_classifier: Smart context selection based on user intent
"""

from slack_bot.hooks.source_tracker import SourceTracker, get_tracker, set_tracker
from slack_bot.hooks.citation_hook import citation_hook
from slack_bot.hooks.intent_classifier import intent_classifier_hook

__all__ = [
    "SourceTracker",
    "get_tracker",
    "set_tracker",
    "citation_hook",
    "intent_classifier_hook",
]
