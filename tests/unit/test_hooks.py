"""
Unit tests for the hooks module.

Tests for:
- SourceTracker: tracking and formatting sources
- citation_hook: adding citations to responses
- intent_classifier: classifying user intent
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from slack_bot.hooks.source_tracker import (
    SourceTracker,
    SourceRecord,
    get_tracker,
    set_tracker,
    clear_tracker,
)
from slack_bot.hooks.citation_hook import citation_hook
from slack_bot.hooks.intent_classifier import (
    Intent,
    IntentClassification,
    classify_intent,
    intent_classifier_hook,
)

pytestmark = pytest.mark.unit


# ============================================================
# SourceTracker Tests
# ============================================================

class TestSourceTracker:
    """Tests for SourceTracker class."""

    def test_init_empty(self):
        """New tracker has no records."""
        tracker = SourceTracker()
        assert tracker.records == []
        assert not tracker.has_sources()

    def test_record_source_basic(self):
        """Can record a source with basic info."""
        tracker = SourceTracker()
        tracker.record_source(
            tool_name="brain_search",
            success=True,
            sources=["notes/todo.md", "projects/plan.md"],
        )
        
        assert len(tracker.records) == 1
        assert tracker.records[0].tool_name == "brain_search"
        assert tracker.records[0].success is True
        assert len(tracker.records[0].sources) == 2

    def test_has_sources_with_sources(self):
        """has_sources returns True when sources recorded."""
        tracker = SourceTracker()
        tracker.record_source(
            tool_name="brain_search",
            success=True,
            sources=["doc.md"],
        )
        assert tracker.has_sources() is True

    def test_has_sources_failed_tool(self):
        """has_sources returns False for failed tools."""
        tracker = SourceTracker()
        tracker.record_source(
            tool_name="brain_search",
            success=False,
            sources=["doc.md"],
        )
        assert tracker.has_sources() is False

    def test_get_sources_all(self):
        """get_sources returns all unique sources."""
        tracker = SourceTracker()
        tracker.record_source("brain_search", True, sources=["a.md", "b.md"])
        tracker.record_source("web_search", True, sources=["https://x.com", "a.md"])
        
        sources = tracker.get_sources()
        assert len(sources) == 3  # a.md, b.md, https://x.com (deduped)

    def test_get_sources_filtered(self):
        """get_sources with tool_name filters correctly."""
        tracker = SourceTracker()
        tracker.record_source("brain_search", True, sources=["a.md", "b.md"])
        tracker.record_source("web_search", True, sources=["https://x.com"])
        
        brain = tracker.get_sources("brain_search")
        assert len(brain) == 2
        assert "a.md" in brain
        
        web = tracker.get_sources("web_search")
        assert len(web) == 1
        assert "https://x.com" in web

    def test_format_citations_compact(self):
        """format_citations produces compact format."""
        tracker = SourceTracker()
        tracker.record_source("brain_search", True, sources=["doc1.md", "doc2.md"])
        
        citations = tracker.format_citations(style="compact")
        assert "📚 Brain:" in citations
        assert "doc1.md" in citations

    def test_format_citations_empty(self):
        """format_citations returns empty for no sources."""
        tracker = SourceTracker()
        assert tracker.format_citations() == ""

    def test_format_citations_web_and_brain(self):
        """format_citations includes both web and brain."""
        tracker = SourceTracker()
        tracker.record_source("brain_search", True, sources=["note.md"])
        tracker.record_source("web_search", True, sources=["https://example.com"])
        
        citations = tracker.format_citations()
        assert "📚 Brain:" in citations
        assert "🌐 Web:" in citations

    def test_get_tool_stats(self):
        """get_tool_stats counts sources by tool."""
        tracker = SourceTracker()
        tracker.record_source("brain_search", True, sources=["a.md", "b.md"])
        tracker.record_source("web_search", True, sources=["https://x.com"])
        
        stats = tracker.get_tool_stats()
        assert stats["brain_search"] == 2
        assert stats["web_search"] == 1


class TestSourceTrackerContext:
    """Tests for context-local tracker management."""

    def test_set_and_get_tracker(self):
        """Can set and get tracker in context."""
        tracker = SourceTracker()
        set_tracker(tracker)
        
        assert get_tracker() is tracker
        
        clear_tracker()
        assert get_tracker() is None

    def test_clear_tracker(self):
        """clear_tracker removes context tracker."""
        tracker = SourceTracker()
        set_tracker(tracker)
        clear_tracker()
        
        assert get_tracker() is None


# ============================================================
# Citation Hook Tests
# ============================================================

class TestCitationHook:
    """Tests for citation_hook post-process hook."""

    @pytest.mark.asyncio
    async def test_no_tracker_returns_original(self):
        """Returns original response when no tracker."""
        clear_tracker()
        
        response = "This is the answer."
        result = await citation_hook(response, {}, MagicMock())
        
        assert result == response

    @pytest.mark.asyncio
    async def test_no_sources_returns_original(self):
        """Returns original when tracker has no sources."""
        tracker = SourceTracker()
        set_tracker(tracker)
        
        response = "This is the answer."
        result = await citation_hook(response, {}, MagicMock())
        
        assert result == response
        clear_tracker()

    @pytest.mark.asyncio
    async def test_with_sources_adds_citations(self):
        """Adds citations when sources available."""
        tracker = SourceTracker()
        tracker.record_source("brain_search", True, sources=["my-note.md"])
        set_tracker(tracker)
        
        response = "This is the answer."
        result = await citation_hook(response, {}, MagicMock())
        
        assert "This is the answer." in result
        assert "---" in result
        assert "📚 Brain:" in result
        assert "my-note.md" in result
        
        clear_tracker()


# ============================================================
# Intent Classifier Tests
# ============================================================

class TestIntentClassifier:
    """Tests for intent classification."""

    def test_greeting_hi(self):
        """'hi' is classified as greeting."""
        result = classify_intent("hi")
        assert result.primary == Intent.GREETING
        assert result.enable_brain is False
        assert result.enable_web is False

    def test_greeting_thanks(self):
        """'thanks' is classified as greeting."""
        result = classify_intent("thanks")
        assert result.primary == Intent.GREETING

    def test_research_search(self):
        """'search for...' triggers research intent."""
        result = classify_intent("search for the latest news on AI")
        assert result.primary == Intent.RESEARCH
        assert result.enable_web is True
        assert result.enable_brain is False

    def test_research_current(self):
        """'current price of...' triggers research."""
        result = classify_intent("what is the current price of bitcoin")
        assert result.primary == Intent.RESEARCH

    def test_personal_my_preferences(self):
        """'my preferences' triggers personal intent."""
        result = classify_intent("what are my coffee preferences?")
        assert result.primary == Intent.PERSONAL
        assert result.enable_facts is True

    def test_personal_my_health(self):
        """'my health' triggers personal intent."""
        result = classify_intent("remind me about my health goals")
        assert result.primary == Intent.PERSONAL

    def test_knowledge_question(self):
        """Knowledge questions enable brain search."""
        result = classify_intent("what did I write about the project plan?")
        assert result.primary == Intent.KNOWLEDGE
        assert result.enable_brain is True

    def test_task_create(self):
        """Task requests don't need search."""
        result = classify_intent("create a summary of this")
        assert result.primary == Intent.TASK
        assert result.enable_brain is False

    def test_general_default(self):
        """General questions get default context."""
        result = classify_intent("ok sounds good")
        assert result.primary == Intent.GENERAL

    def test_intent_classification_to_dict(self):
        """IntentClassification serializes to dict."""
        result = classify_intent("hi")
        d = result.to_dict()
        
        assert "intent" in d
        assert "confidence" in d
        assert "context" in d
        assert d["context"]["brain"] is False


class TestIntentClassifierHook:
    """Tests for intent_classifier_hook pre-process hook."""

    @pytest.mark.asyncio
    async def test_adds_classification_to_event(self):
        """Hook adds intent_classification to event."""
        event = {"text": "search for AI news"}
        agent = MagicMock()
        
        await intent_classifier_hook(event, agent)
        
        assert "intent_classification" in event
        assert event["intent_classification"]["intent"] == "research"

    @pytest.mark.asyncio
    async def test_uses_user_message_if_available(self):
        """Hook prefers user_message over text."""
        event = {
            "text": "File attached + hi",
            "user_message": "hi"
        }
        agent = MagicMock()
        
        await intent_classifier_hook(event, agent)
        
        # "hi" should be classified as greeting
        assert event["intent_classification"]["intent"] == "greeting"

    @pytest.mark.asyncio
    async def test_empty_text_skips(self):
        """Hook skips when no text."""
        event = {"text": ""}
        agent = MagicMock()
        
        await intent_classifier_hook(event, agent)
        
        assert "intent_classification" not in event
