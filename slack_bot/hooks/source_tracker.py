"""
Source Tracker — tracks which tools were used during message processing.

This module provides a context-local tracker that records:
- Which tools were executed (brain_search, web_search, facts, etc.)
- What sources were retrieved (document names, URLs, etc.)
- Success/failure status of each tool call

The tracker is set at the start of message processing and available
throughout the request lifecycle. Hooks can access it to:
- Add citations to responses
- Generate source attribution
- Log provenance for debugging
"""

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Context-local storage for the current request's source tracker
_current_tracker: ContextVar[Optional["SourceTracker"]] = ContextVar(
    "source_tracker", default=None
)


@dataclass
class SourceRecord:
    """Record of a single tool invocation and its results."""
    
    tool_name: str
    success: bool
    sources: List[str] = field(default_factory=list)  # Document names, URLs, etc.
    snippets: List[str] = field(default_factory=list)  # Brief excerpts
    metadata: Dict = field(default_factory=dict)  # Additional info (scores, etc.)


class SourceTracker:
    """Tracks tool usage and sources during message processing.
    
    Usage:
        # At start of message processing
        tracker = SourceTracker()
        set_tracker(tracker)
        
        # During tool execution (in tool or executor)
        tracker = get_tracker()
        if tracker:
            tracker.record_source(
                tool_name="brain_search",
                success=True,
                sources=["My Note.md", "Project Plan.md"],
                snippets=["This is relevant context..."]
            )
        
        # In post-process hook
        tracker = get_tracker()
        if tracker and tracker.has_sources():
            citations = tracker.format_citations()
            response += f"\n\n{citations}"
    """
    
    def __init__(self):
        self.records: List[SourceRecord] = []
        self._sources_by_tool: Dict[str, List[str]] = {}
    
    def record_source(
        self,
        tool_name: str,
        success: bool,
        sources: Optional[List[str]] = None,
        snippets: Optional[List[str]] = None,
        **metadata
    ) -> None:
        """Record a tool invocation and its sources.
        
        Args:
            tool_name: Name of the tool (e.g., "brain_search")
            success: Whether the tool succeeded
            sources: List of source identifiers (file names, URLs)
            snippets: Brief excerpts from the sources
            **metadata: Additional info (scores, timestamps, etc.)
        """
        record = SourceRecord(
            tool_name=tool_name,
            success=success,
            sources=sources or [],
            snippets=snippets or [],
            metadata=metadata
        )
        self.records.append(record)
        
        # Index by tool for quick lookup
        if tool_name not in self._sources_by_tool:
            self._sources_by_tool[tool_name] = []
        self._sources_by_tool[tool_name].extend(sources or [])
        
        logger.debug(
            f"SourceTracker: recorded {tool_name} "
            f"(success={success}, sources={len(sources or [])})"
        )
    
    def has_sources(self) -> bool:
        """Check if any sources were recorded."""
        return any(r.sources for r in self.records if r.success)
    
    def get_sources(self, tool_name: Optional[str] = None) -> List[str]:
        """Get all source identifiers, optionally filtered by tool.
        
        Args:
            tool_name: Filter to specific tool, or None for all
            
        Returns:
            List of unique source identifiers
        """
        if tool_name:
            return list(set(self._sources_by_tool.get(tool_name, [])))
        
        all_sources = []
        for sources in self._sources_by_tool.values():
            all_sources.extend(sources)
        return list(set(all_sources))
    
    def format_citations(self, style: str = "compact") -> str:
        """Format recorded sources as citation text.
        
        Args:
            style: "compact" for inline, "detailed" for full list
            
        Returns:
            Formatted citation string
        """
        if not self.has_sources():
            return ""
        
        brain_sources = self.get_sources("brain_search")
        web_sources = self.get_sources("web_search")
        
        parts = []
        
        if brain_sources:
            if style == "compact":
                # Show first 3 sources
                shown = brain_sources[:3]
                remaining = len(brain_sources) - 3
                source_text = ", ".join(f"*{s}*" for s in shown)
                if remaining > 0:
                    source_text += f" (+{remaining} more)"
                parts.append(f"📚 Brain: {source_text}")
            else:
                parts.append("📚 **Brain Sources:**")
                for src in brain_sources:
                    parts.append(f"  • {src}")
        
        if web_sources:
            if style == "compact":
                shown = web_sources[:2]
                remaining = len(web_sources) - 2
                source_text = ", ".join(shown)
                if remaining > 0:
                    source_text += f" (+{remaining} more)"
                parts.append(f"🌐 Web: {source_text}")
            else:
                parts.append("🌐 **Web Sources:**")
                for src in web_sources:
                    parts.append(f"  • {src}")
        
        return "\n".join(parts)
    
    def get_tool_stats(self) -> Dict[str, int]:
        """Get count of sources by tool."""
        return {tool: len(sources) for tool, sources in self._sources_by_tool.items()}


def get_tracker() -> Optional[SourceTracker]:
    """Get the current request's source tracker, if any."""
    return _current_tracker.get()


def set_tracker(tracker: Optional[SourceTracker]) -> None:
    """Set the source tracker for the current request."""
    _current_tracker.set(tracker)


def clear_tracker() -> None:
    """Clear the current tracker (call at end of request)."""
    _current_tracker.set(None)
