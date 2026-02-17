# Web Search Capabilities Plan

## Objective

Enable Brain Assistant to search the web for current information, treating web results as a special type of document with appropriate context management for currency and noise reduction.

---

## Design Principles

### Context Currency
- Web content is ephemeral — results should include retrieval timestamps
- Clearly distinguish "fresh web search" from "indexed brain content"
- Consider recency in relevance scoring (recent news vs. evergreen articles)

### Noise Management  
- Web search returns more noise than curated brain content
- Implement result filtering, summarization, and source quality signals
- Limit tokens consumed by web context (separate budget from brain context)
- Prefer authoritative sources when available

### User Experience
- Transparent about when web search was used vs. brain search
- Cite web sources with URLs and retrieval timestamps
- Allow user to request web search explicitly or let bot decide

---

## Architecture

### Approach: Hybrid Tool + Web API

```
┌───────────────────────────────────────────────────────────────────┐
│                         User Query                                 │
└───────────────────────┬───────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                    Query Classifier                                │
│  - Is this about current events? → Web search                      │
│  - Is this about user's personal notes? → Brain search             │
│  - Is this factual/technical? → Both (brain first, web fallback)  │
└───────────────────────┬───────────────────────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
┌──────────────────┐        ┌──────────────────┐
│  Brain Search    │        │   Web Search     │
│ (SemanticSearch) │        │   (WebClient)    │
└────────┬─────────┘        └────────┬─────────┘
         │                           │
         └─────────────┬─────────────┘
                       ▼
┌───────────────────────────────────────────────────────────────────┐
│                    Context Formatter                               │
│  - Merge brain + web results                                       │
│  - Apply token budgets (brain: 2000, web: 1500)                   │
│  - Add source citations and timestamps                            │
└───────────────────────┬───────────────────────────────────────────┘
                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                       LLM Prompt                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Web Search Options

**Option A: Direct Web Search API (Recommended)**
- Use a search API (DuckDuckGo, SerpAPI, Tavily, Brave Search)
- Pros: Purpose-built for search, fast, structured results
- Cons: May require API key (some are free)

**Option B: Web Scraping via Playwright MCP**
- Use available browser tools to navigate and scrape
- Pros: Can handle any website, no API dependency
- Cons: Slower, more complex, fragile

**Option C: Hybrid**
- Use search API for query, Playwright for content extraction
- Best of both worlds but most complex

**Recommendation: Option A with DuckDuckGo or Tavily**
- DuckDuckGo: Free, no API key required
- Tavily: Built for LLM use, good summaries (free tier available)

---

## Implementation Plan

### Phase 1: Web Search Client

**File:** `clients/web_search_client.py`

```python
"""
Web Search Client - Search the web for current information.
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class WebSearchResult:
    """A single web search result."""
    title: str
    url: str
    snippet: str
    retrieved_at: str  # ISO timestamp
    source_domain: str
    score: float = 0.0


class WebSearchClient:
    """Search the web using DuckDuckGo or Tavily API."""
    
    def __init__(
        self,
        provider: str = "duckduckgo",  # "duckduckgo" | "tavily"
        api_key: Optional[str] = None,
        timeout: int = 10,
        max_results: int = 5,
    ):
        self.provider = provider
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout)
        self.max_results = max_results
        self.client = None
    
    async def search(self, query: str, limit: int = 5) -> List[WebSearchResult]:
        """
        Search the web for the given query.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            
        Returns:
            List of WebSearchResult objects
        """
        if self.provider == "duckduckgo":
            return await self._search_duckduckgo(query, limit)
        elif self.provider == "tavily":
            return await self._search_tavily(query, limit)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    async def _search_duckduckgo(self, query: str, limit: int) -> List[WebSearchResult]:
        """Search using DuckDuckGo Instant Answer API."""
        # Using duckduckgo-search library (pip install duckduckgo-search)
        try:
            from duckduckgo_search import AsyncDDGS
            
            async with AsyncDDGS() as ddgs:
                results = []
                async for r in ddgs.text(query, max_results=limit):
                    results.append(WebSearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                        retrieved_at=datetime.now().isoformat(),
                        source_domain=self._extract_domain(r.get("href", "")),
                        score=1.0 - (len(results) * 0.1),  # Simple position-based score
                    ))
                return results
                
        except ImportError:
            logger.error("duckduckgo-search not installed. Run: pip install duckduckgo-search")
            return []
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []
    
    async def _search_tavily(self, query: str, limit: int) -> List[WebSearchResult]:
        """Search using Tavily API (requires API key)."""
        if not self.api_key:
            logger.error("Tavily API key required")
            return []
        
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": limit,
                "include_answer": False,
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
            
            results = []
            for r in data.get("results", []):
                results.append(WebSearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    retrieved_at=datetime.now().isoformat(),
                    source_domain=self._extract_domain(r.get("url", "")),
                    score=r.get("score", 0.5),
                ))
            return results
            
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return []
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        try:
            return urlparse(url).netloc
        except Exception:
            return ""
    
    async def health_check(self) -> bool:
        """Check if web search is available."""
        try:
            results = await self.search("test", limit=1)
            return len(results) > 0
        except Exception:
            return False
    
    async def close(self):
        """Close any open connections."""
        if self.client:
            await self.client.aclose()
```

### Phase 2: Query Classifier

**Function added to `slack_agent.py`:**

```python
def _should_web_search(self, query: str) -> tuple[bool, str]:
    """
    Determine if query should trigger web search.
    
    Returns:
        (should_search, reason)
    """
    query_lower = query.lower()
    
    # Keywords suggesting current events
    current_event_patterns = [
        "today", "yesterday", "this week", "this month",
        "latest", "recent", "current", "now", "breaking",
        "news about", "what happened", "update on",
        "stock price", "weather", "score", "game",
        "2025", "2026",  # Current/future years
    ]
    
    # Keywords suggesting external lookup (not personal notes)
    external_patterns = [
        "what is the population", "how many people",
        "who is the", "when was", "when did",
        "define", "explain what", "tell me about",
        "official documentation", "according to",
    ]
    
    # Keywords suggesting personal context (prefer brain search)
    personal_patterns = [
        "my notes", "my journal", "i wrote", "i mentioned",
        "we discussed", "my project", "my work",
        "remember when", "last time we",
    ]
    
    # Check for personal patterns (skip web search)
    if any(p in query_lower for p in personal_patterns):
        return (False, "personal context")
    
    # Check for current event patterns
    if any(p in query_lower for p in current_event_patterns):
        return (True, "current events")
    
    # Check for external lookup patterns
    if any(p in query_lower for p in external_patterns):
        return (True, "external lookup")
    
    # Default: no web search (prefer brain context)
    return (False, "default to brain")
```

### Phase 3: Context Integration

**Modify `_process_message` in `slack_agent.py`:**

```python
async def _process_message(self, user_id: str, text: str, ...):
    # ... existing conversation loading ...
    
    # ---- Search brain for context ----
    brain_context = ""
    if self.enable_search and len(search_query) > 10:
        brain_context = await self._search_brain(search_query)
    
    # ---- Web search for current context (NEW) ----
    web_context = ""
    should_web, reason = self._should_web_search(text)
    if should_web and self.enable_web_search:
        self.logger.info(f"Web search triggered: {reason}")
        web_results = await self.web_search.search(text, limit=3)
        if web_results:
            web_context = self._format_web_results(web_results)
    
    # ---- Combine contexts with token budgets ----
    full_context = self._merge_contexts(
        brain_context,
        web_context,
        brain_budget=2000,
        web_budget=1500,
    )
    
    # ... rest of message processing ...

def _format_web_results(self, results: List[WebSearchResult]) -> str:
    """Format web search results for LLM context."""
    if not results:
        return ""
    
    lines = ["\n\n**Web search results (retrieved just now):**\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r.title}**")
        lines.append(f"   {r.snippet[:200]}...")
        lines.append(f"   _Source: {r.source_domain} | Retrieved: {r.retrieved_at[:10]}_\n")
    
    return "\n".join(lines)
```

### Phase 4: Configuration

**New config options in `slack_bot.py`:**

```python
config = {
    # ... existing options ...
    "enable_web_search": os.getenv("SLACK_ENABLE_WEB_SEARCH", "true").lower() == "true",
    "web_search_provider": os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo"),
    "tavily_api_key": os.getenv("TAVILY_API_KEY"),  # Optional
    "web_context_budget": int(os.getenv("WEB_CONTEXT_BUDGET", "1500")),
}
```

---

## Testing Plan

### Unit Tests

**File:** `tests/unit/test_web_search_client.py`

```python
@pytest.mark.unit
class TestWebSearchClient:
    
    async def test_duckduckgo_search_returns_results(self):
        """Test that DuckDuckGo search returns results."""
        client = WebSearchClient(provider="duckduckgo")
        results = await client.search("Python programming", limit=3)
        assert len(results) > 0
        assert all(r.url.startswith("http") for r in results)
    
    async def test_result_has_timestamp(self):
        """Test that results include retrieval timestamp."""
        client = WebSearchClient()
        results = await client.search("test query", limit=1)
        if results:  # May fail if search is down
            assert results[0].retrieved_at is not None
    
    async def test_query_classifier_current_events(self):
        """Test that current event queries trigger web search."""
        from agents.slack_agent import SlackAgent
        # ... mock agent and test _should_web_search
```

### Integration Tests

**File:** `tests/integration/test_web_search.py`

```python
@pytest.mark.integration
class TestWebSearchIntegration:
    
    async def test_web_search_triggered_for_news(self, agent_with_mocks):
        """Test that news queries include web context."""
        response = await agent._process_message(
            "U123", "What's happening in tech news today?", "T123"
        )
        # Verify web search was called
        agent.web_search.search.assert_called_once()
    
    async def test_brain_search_preferred_for_personal(self, agent_with_mocks):
        """Test that personal queries skip web search."""
        response = await agent._process_message(
            "U123", "What did I write about productivity?", "T123"
        )
        # Verify web search was NOT called
        agent.web_search.search.assert_not_called()
```

### E2E Tests

**Add to `tests/automated_checklist.py`:**

```python
def test_10_1_web_search_current_events(self) -> tuple[TestStatus, str]:
    """Test that asking about current events triggers web search."""
    response = self.tester.send_and_wait(
        "What are the latest developments in AI this week?"
    )
    if response:
        text = response.get("text", "").lower()
        # Check for web source indicators
        has_web = any(kw in text for kw in [
            "web search", "retrieved", "according to", 
            ".com", ".org", "source:"
        ])
        if has_web:
            return TestStatus.PASS, "Web search results included"
        return TestStatus.PARTIAL, "Responded but no web results visible"
    return TestStatus.FAIL, "No response"
```

---

## Rollout Plan

### Phase 1: Build & Unit Test (Day 1)
- [ ] Implement `WebSearchClient` with DuckDuckGo
- [ ] Add unit tests for client
- [ ] Test locally

### Phase 2: Integration (Day 2)
- [ ] Add query classifier
- [ ] Integrate into `slack_agent.py`
- [ ] Add config options
- [ ] Integration tests

### Phase 3: Deploy & E2E Test (Day 3)
- [ ] Deploy to NUC-2
- [ ] Run automated checklist
- [ ] Manual testing of edge cases

### Phase 4: Iterate (Day 4+)
- [ ] Tune query classifier based on real usage
- [ ] Add Tavily as optional enhanced provider
- [ ] Consider caching for repeated queries
- [ ] Add user feedback mechanism ("Was this helpful?")

---

## Dependencies

**Required:**
```bash
pip install duckduckgo-search
```

**Optional (for enhanced search):**
```bash
pip install tavily-python  # If using Tavily API
```

---

## Token Budget Analysis

Current context structure:
- System prompt: ~600 tokens
- Conversation history: 0-2000 tokens
- Brain context: 0-2000 tokens
- **New: Web context: 0-1500 tokens**
- User message: ~100 tokens
- Total max: ~6200 tokens (fits within 8K context)

With web search enabled, we may need to:
1. Reduce brain context budget to 1500 tokens
2. Implement priority-based trimming (most relevant first)
3. Summarize long web snippets

---

## Success Metrics

1. **Coverage:** Web search triggered for 70%+ of current event queries
2. **Accuracy:** Web search NOT triggered for 90%+ of personal queries
3. **Latency:** Web search adds <3 seconds to response time
4. **Quality:** User reports web results as helpful 70%+ of time

---

## Open Questions

1. **Caching:** Should we cache web results to reduce API calls?
2. **Rate limiting:** How to handle DuckDuckGo rate limits?
3. **Fallbacks:** What if web search fails? Silent degradation or notify user?
4. **User control:** Should users be able to explicitly request web search (`@web`)?

---

## Next Steps

1. Review and approve this plan
2. Implement Phase 1: `WebSearchClient`
3. Run unit tests
4. Continue with integration
