"""
Intent Classifier Hook — pre-process hook for smart context selection.

Uses lightweight keyword heuristics (no LLM call) to classify user intent
and decide which context sources to enable. This reduces noise for
small-context models like llama3.2.

Intent Categories:
- GREETING: "hi", "hello", "thanks" → minimal context
- PERSONAL: pronouns + personal keywords → enable facts
- KNOWLEDGE: question words + domain terms → enable brain_search
- RESEARCH: "find", "search", "look up" → enable web_search
- GENERAL: default → standard context injection
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Set

logger = logging.getLogger(__name__)


class Intent(Enum):
    """User intent categories."""
    
    GREETING = "greeting"      # Greeting, thanks, farewell
    PERSONAL = "personal"      # Personal questions (use facts)
    KNOWLEDGE = "knowledge"    # Knowledge questions (use brain)
    RESEARCH = "research"      # Research/lookup (use web)
    TASK = "task"              # Task request (action-focused)
    GENERAL = "general"        # General conversation


@dataclass
class IntentClassification:
    """Result of intent classification."""
    
    primary: Intent
    confidence: float  # 0.0 to 1.0
    enable_brain: bool
    enable_web: bool
    enable_facts: bool
    
    def to_dict(self) -> dict:
        return {
            "intent": self.primary.value,
            "confidence": self.confidence,
            "context": {
                "brain": self.enable_brain,
                "web": self.enable_web,
                "facts": self.enable_facts,
            }
        }


# Keyword patterns for each intent
GREETING_KEYWORDS = {
    "hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye",
    "good morning", "good evening", "morning", "evening", "howdy"
}

PERSONAL_SIGNALS = {
    "my", "me", "i", "i'm", "i've", "mine", "myself"
}

PERSONAL_KEYWORDS = {
    "preference", "prefer", "favorite", "health", "medication",
    "family", "wife", "husband", "son", "daughter", "kids",
    "goal", "goals", "remind", "remember", "stored", "facts",
    "like", "dislike", "allergy", "allergic", "diet"
}

KNOWLEDGE_SIGNALS = {
    "what", "how", "why", "when", "where", "who", "which",
    "explain", "describe", "tell me about", "what's"
}

KNOWLEDGE_KEYWORDS = {
    "note", "notes", "document", "project", "plan", "idea",
    "wrote", "written", "saved", "brain", "knowledge base"
}

RESEARCH_KEYWORDS = {
    "search", "find", "look up", "lookup", "google", "web",
    "current", "latest", "news", "today", "recent", "now",
    "2024", "2025", "2026"  # Current events marker
}

TASK_KEYWORDS = {
    "create", "make", "generate", "write", "draft", "build",
    "update", "change", "modify", "delete", "remove", "add"
}


def _tokenize(text: str) -> Set[str]:
    """Simple word tokenization."""
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-z]+\b', text.lower())
    return set(words)


def _has_overlap(words: Set[str], keywords: Set[str]) -> float:
    """Calculate overlap ratio with keywords."""
    overlap = words & keywords
    if not keywords:
        return 0.0
    return len(overlap) / len(keywords)


def _contains_phrase(text: str, phrases: Set[str]) -> bool:
    """Check if text contains any of the phrases."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in phrases)


def classify_intent(text: str) -> IntentClassification:
    """Classify user intent based on keyword heuristics.
    
    Args:
        text: User message text
        
    Returns:
        IntentClassification with recommended context settings
    """
    text_lower = text.lower().strip()
    words = _tokenize(text_lower)
    
    # Short messages that are just greetings
    if len(words) <= 3 and (words & GREETING_KEYWORDS):
        return IntentClassification(
            primary=Intent.GREETING,
            confidence=0.9,
            enable_brain=False,
            enable_web=False,
            enable_facts=False,
        )
    
    # Check for research intent (time-sensitive/current info)
    research_signal = any(kw in text_lower for kw in RESEARCH_KEYWORDS)
    if research_signal:
        return IntentClassification(
            primary=Intent.RESEARCH,
            confidence=0.8,
            enable_brain=False,  # Skip brain for current info
            enable_web=True,
            enable_facts=False,
        )
    
    # Check for personal intent (FACTS relevant)
    has_personal_signal = bool(words & PERSONAL_SIGNALS)
    has_personal_keyword = _contains_phrase(text_lower, PERSONAL_KEYWORDS)
    if has_personal_signal and has_personal_keyword:
        return IntentClassification(
            primary=Intent.PERSONAL,
            confidence=0.85,
            enable_brain=False,  # Facts are more relevant
            enable_web=False,
            enable_facts=True,
        )
    
    # Check for knowledge intent (brain search relevant)
    has_knowledge_signal = bool(words & KNOWLEDGE_SIGNALS)
    has_knowledge_keyword = _contains_phrase(text_lower, KNOWLEDGE_KEYWORDS)
    # Questions about domain knowledge
    if has_knowledge_signal or has_knowledge_keyword:
        return IntentClassification(
            primary=Intent.KNOWLEDGE,
            confidence=0.75,
            enable_brain=True,
            enable_web=False,
            enable_facts=False,
        )
    
    # Check for task intent
    has_task_signal = bool(words & TASK_KEYWORDS)
    if has_task_signal:
        return IntentClassification(
            primary=Intent.TASK,
            confidence=0.7,
            enable_brain=False,  # Tasks don't need search
            enable_web=False,
            enable_facts=False,
        )
    
    # Default: general conversation with brain context
    return IntentClassification(
        primary=Intent.GENERAL,
        confidence=0.5,
        enable_brain=True,  # Default to including brain context
        enable_web=False,
        enable_facts=True,  # Include relevant facts
    )


async def intent_classifier_hook(event: dict, agent: Any) -> None:
    """Pre-process hook that classifies intent and sets context flags.
    
    This hook is registered with agent.register_hook("pre_process", intent_classifier_hook).
    It runs before message processing and adds intent classification to the event.
    
    The classification is stored in event["intent_classification"] for use by
    subsequent processing steps.
    
    Args:
        event: Event dict (modified in-place)
        agent: SlackAgent instance
    """
    text = event.get("user_message") or event.get("text", "")
    
    if not text:
        logger.debug("intent_classifier_hook: No text to classify")
        return
    
    classification = classify_intent(text)
    
    # Store in event for downstream use
    event["intent_classification"] = classification.to_dict()
    
    logger.info(
        f"intent_classifier_hook: {classification.primary.value} "
        f"(conf={classification.confidence:.2f}, "
        f"brain={classification.enable_brain}, "
        f"web={classification.enable_web}, "
        f"facts={classification.enable_facts})"
    )
