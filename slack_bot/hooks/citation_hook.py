"""
Citation Hook — post-process hook that adds source citations to responses.

This hook leverages the SourceTracker to append citations when:
- brain_search was used (📚 Brain sources)
- web_search was used (🌐 Web sources)

The citation format is compact by default to preserve context window space.
"""

import logging
from typing import Any

from slack_bot.hooks.source_tracker import get_tracker

logger = logging.getLogger(__name__)


async def citation_hook(response: str, event: dict, agent: Any) -> str:
    """Post-process hook that appends source citations.
    
    This hook is registered with agent.register_hook("post_process", citation_hook).
    It runs after the LLM generates a response, and appends a "Sources" section
    if any sources were used during processing.
    
    Args:
        response: The generated response text
        event: The original event dict with user_id, text, etc.
        agent: The SlackAgent instance (for accessing config)
        
    Returns:
        Response with appended citations, or original if no sources
    """
    tracker = get_tracker()
    
    if not tracker:
        logger.debug("citation_hook: No tracker in context, skipping")
        return response
    
    if not tracker.has_sources():
        logger.debug("citation_hook: Tracker has no sources, skipping")
        return response
    
    # Format citations (compact style for small context windows)
    citations = tracker.format_citations(style="compact")
    
    if not citations:
        return response
    
    # Build enhanced response
    # Add a subtle separator and the citations
    enhanced = f"{response}\n\n---\n{citations}"
    
    logger.info(
        f"citation_hook: Added citations "
        f"(stats={tracker.get_tool_stats()})"
    )
    
    return enhanced
