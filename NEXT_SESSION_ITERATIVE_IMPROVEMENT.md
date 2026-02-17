# Brain Assistant Iterative Improvement Plan
**Date:** 2026-02-16
**Status:** Test suite GREEN (174/174 passing) — Ready for feature iteration
**Next Agent Mission:** Use `slack-as-me` tools to create challenge scripts and RAPIDLY iterate on making Brain Assistant actually useful

---

## Current State: We Have the Tools, Now Make It Smart

### What Just Happened (Session Summary)
1. **Fixed all 4 failing health check tests** — Root causes:
   - Wrong mock patch targets (patched `clients.X` instead of `agents.slack_agent.X`)
   - Missing `agent_platform.BrainIO` patch
   - Slack auth treated as non-fatal (fixed: now critical like Ollama)

2. **Test suite is 100% GREEN**: 174 unit + integration tests passing, 0 failures

3. **New testing infrastructure is LIVE**:
   - `python -m tools.slack_as_me ask "question"` — Send DM to Brain Assistant as Eugene
   - `python -m tools.slack_as_me converse` — Multi-turn conversation testing
   - `python -m tools.slack_as_me --agent-instructions` — Get programmatic usage docs for agents
   - All tokens in Vaultwarden, ready to use

---

## The Problem: Brain Assistant is Currently Stupid

**Reality check:** Brain Assistant has fancy infrastructure but doesn't USE it well:

### What's Available But Underutilized
1. **cxdb client** ([clients/cxdb_client.py](clients/cxdb_client.py)) — Fast conversation storage/retrieval
   - Stores user conversations in Postgres via cxdb API
   - Enables semantic search across past conversations
   - **Currently:** Just dual-writes conversations, doesn't USE the search capability

2. **BrainIO** ([clients/brain_io.py](clients/brain_io.py)) — Markdown file brain storage
   - Reads/writes markdown files in structured brain folder
   - Journal entries, notes, projects
   - **Currently:** Not actively used during conversations

3. **Khoj semantic search** ([clients/semantic_search_client.py](clients/semantic_search_client.py))
   - Searches brain markdown files semantically
   - Returns relevant context chunks
   - **Currently:** Called but results often ignored or poorly integrated

4. **ConversationManager** ([clients/conversation_manager.py](clients/conversation_manager.py))
   - Multi-turn conversation history with summarization
   - Token counting and context management
   - **Currently:** Works but doesn't intelligently prune/prioritize context

### The Core Constraint: Llama 3.x Models
- **Primary target:** llama3.2 (6K-8K context window)
- **Challenge:** Small context = must be VERY smart about what goes in
- **Solution:** Maximize external memory (cxdb, brain files), minimize noise in context

---

## The Vision: Iterative Improvement via Challenge Scripts

### The Process
1. **Define a desired behavior** (e.g., "Remember what I told you last week about backups")
2. **Write a challenge script** using `slack-as-me` to test it
3. **Run the script, observe failure** (Brain Assistant gives wrong/incomplete answer)
4. **Fix the code** (improve context injection, search relevance, summarization)
5. **Run the script again, verify success**
6. **Commit, move to next challenge**

### Example Challenge Script
```python
#!/usr/bin/env python3
"""
Challenge: Brain Assistant should remember past conversations from cxdb.

Setup:
  1. Tell Brain Assistant: "My backup strategy is restic to pCloud"
  2. Wait for response
  3. Start new conversation thread
  4. Ask: "What's my backup strategy?"

Expected: Brain Assistant retrieves from cxdb and answers "restic to pCloud"
Actual (current): Probably says "I don't have that information"
"""

from clients.slack_user_client import SlackUserClient

client = SlackUserClient()

# First conversation
print("Setting up context...")
response1 = client.ask("My backup strategy is restic to pCloud for offsite encrypted backups.")
print(f"Bot acknowledged: {response1[:100]}...")

# New conversation (different thread)
print("\nTesting recall...")
response2 = client.ask("What's my backup strategy?")
print(f"Bot response: {response2}")

# Verify
if "restic" in response2.lower() and "pcloud" in response2.lower():
    print("✅ PASS: Brain Assistant remembered from cxdb")
    exit(0)
else:
    print("❌ FAIL: Brain Assistant didn't retrieve past conversation")
    exit(1)
```

---

## Specific Improvement Areas (Prioritized)

### 1. **cxdb Conversation Retrieval** (HIGH PRIORITY)
**Problem:** cxdb stores conversations but Brain Assistant never searches them
**File:** [agents/slack_agent.py:600-604](agents/slack_agent.py#L600-L604) `_process_message()`
**Current behavior:** Only uses current thread history
**Desired behavior:**
- Before processing message, search cxdb for relevant past conversations
- Inject 1-2 most relevant past exchanges into context
- Format like: `## Relevant Past Conversations:\n[date] User: ... / Assistant: ...`

**Implementation hints:**
- `self.cxdb.search_conversations(query=message, limit=2)` exists but isn't called
- Add call in `_process_message()` before building context
- Keep it MINIMAL (200-300 tokens max) due to llama3.2 context limits

### 2. **Smarter Khoj Context Injection** (HIGH PRIORITY)
**Problem:** Khoj returns 3 results, all dumped into context regardless of relevance
**File:** [agents/slack_agent.py:658-687](agents/slack_agent.py#L658-L687) `_inject_context()`
**Current behavior:** Takes top 3 Khoj results, formats as big block
**Desired behavior:**
- Filter Khoj results by relevance score (skip if score < 0.7)
- Summarize each result to 1-2 sentences instead of full text
- Prioritize recent entries over old ones (check file timestamp)

**Implementation hints:**
- Khoj returns `score` field — use it for filtering
- Results have `file` field — parse date from filename for recency weighting
- Consider asking LLM to summarize long entries before injection

### 3. **Conversation Summarization Trigger** (MEDIUM PRIORITY)
**Problem:** Conversations grow until context overflows
**File:** [clients/conversation_manager.py:263-265](clients/conversation_manager.py#L263-L265) `_should_summarize()`
**Current behavior:** Summarizes when token count exceeds threshold
**Desired behavior:**
- Lower threshold for llama3.2 (currently ~4000, should be ~2000)
- Summarize more aggressively to leave room for context injection
- Keep last 3 exchanges full, summarize everything older

**Implementation hints:**
- Adjust `max_context_tokens` in config to 2000 for llama3.2
- Test with long conversations via `slack-as-me converse`

### 4. **Brain File Writing** (MEDIUM PRIORITY)
**Problem:** Brain Assistant never suggests saving important info to brain
**Current behavior:** Reads brain files via Khoj, never writes
**Desired behavior:**
- Detect when user shares important information
- Suggest: "Should I save this to your brain? It seems like something you'll want to reference later."
- Provide button UI to confirm (similar to file upload prompt)
- Write to appropriate folder (journal/, notes/, projects/)

**Implementation hints:**
- Add detection in `_process_message()` for keywords: "my", "I use", "remember", "important"
- Use Block Kit modal to confirm write
- `self.brain.write_note(folder="notes", filename=f"{topic}.md", content=...)`

### 5. **File Upload Integration** (LOW PRIORITY)
**Problem:** File upload feature exists but not wired into main agent
**Status:** Implemented in [slack_bot/file_handler.py](slack_bot/file_handler.py), not called
**Desired behavior:** Detect file attachments, extract text, include in context
**Implementation:** Add call to `detect_file_attachments()` in message handler

---

## How to Start (Recommended Workflow)

### Step 1: Write Your First Challenge Script
Pick the **cxdb conversation retrieval** challenge:

```bash
cd /Users/earchibald/LLM/implementation
mkdir -p tests/challenges
vim tests/challenges/01_cxdb_recall.py
```

Contents:
```python
#!/usr/bin/env python3
"""Challenge: Retrieve past conversation from cxdb"""
from clients.slack_user_client import SlackUserClient

client = SlackUserClient()

# Setup
print("Setup: Telling Brain Assistant about backup strategy...")
client.ask("I use restic with pCloud for encrypted offsite backups. The local repo is on NUC-3.")

# Test
print("Test: Asking in new conversation...")
response = client.ask("What backup tool do I use for offsite storage?")

# Verify
if "restic" in response.lower() and "pcloud" in response.lower():
    print(f"✅ PASS\nResponse: {response}")
    exit(0)
else:
    print(f"❌ FAIL\nResponse: {response}")
    exit(1)
```

Make it executable:
```bash
chmod +x tests/challenges/01_cxdb_recall.py
```

### Step 2: Run the Challenge (Expect Failure)
```bash
python tests/challenges/01_cxdb_recall.py
```

Expected output: `❌ FAIL` — Brain Assistant doesn't search cxdb

### Step 3: Fix the Code
Edit [agents/slack_agent.py](agents/slack_agent.py) `_process_message()`:

```python
async def _process_message(self, user_id: str, message: str) -> str:
    """Process message and generate response with context injection"""

    # NEW: Search cxdb for relevant past conversations
    past_context = ""
    try:
        past_convos = await self.cxdb.search_conversations(
            query=message,
            user_id=user_id,
            limit=2
        )
        if past_convos:
            past_context = "## Relevant Past Conversations:\n"
            for convo in past_convos:
                date = convo.get("timestamp", "recent")
                past_context += f"[{date}] You said: {convo['user_message']}\n"
                past_context += f"I replied: {convo['assistant_message']}\n\n"
    except Exception as e:
        self.logger.warning(f"cxdb search failed: {e}")

    # Continue with existing context injection...
    context = await self._inject_context(user_id, message)

    # Combine: past conversations + brain context
    full_context = past_context + context if past_context else context

    # Rest of existing logic...
```

### Step 4: Run Challenge Again (Expect Success)
```bash
python tests/challenges/01_cxdb_recall.py
```

Expected: `✅ PASS` — Brain Assistant now retrieves from cxdb

### Step 5: Commit and Move to Next Challenge
```bash
git add agents/slack_agent.py tests/challenges/01_cxdb_recall.py
git commit -m "feat: Add cxdb conversation retrieval to context injection

Brain Assistant now searches past conversations in cxdb before responding,
enabling recall of information shared in previous threads.

Challenge: tests/challenges/01_cxdb_recall.py
Status: PASSING"
```

---

## Challenge Ideas (Build These Next)

Create challenge scripts in `tests/challenges/` for each:

1. **`02_khoj_relevance_filter.py`** — Khoj should skip low-score results
2. **`03_recent_prioritization.py`** — Recent brain entries should rank higher
3. **`04_context_overflow_handling.py`** — Long conversation should auto-summarize
4. **`05_brain_write_suggestion.py`** — Bot should offer to save important info
5. **`06_file_attachment_extraction.py`** — Upload PDF, bot should read it
6. **`07_multimodal_image_upload.py`** — Upload screenshot, bot should describe it
7. **`08_conversation_threading.py`** — Multi-turn conversation maintains context
8. **`09_source_citation.py`** — Bot should cite brain file sources
9. **`10_timezone_aware_timestamps.py`** — Journal entries use correct timezone

---

## Key Files to Know

### Agent Core
- [agents/slack_agent.py](agents/slack_agent.py) — Main bot logic, message handling
  - `_process_message()` — Entry point for all messages
  - `_inject_context()` — Khoj brain search and context formatting
  - `_health_check()` — Startup dependency validation

### Storage Clients
- [clients/cxdb_client.py](clients/cxdb_client.py) — Postgres conversation storage (fast search)
- [clients/brain_io.py](clients/brain_io.py) — Markdown file I/O for brain folder
- [clients/conversation_manager.py](clients/conversation_manager.py) — Multi-turn conversation history
- [clients/semantic_search_client.py](clients/semantic_search_client.py) — Khoj API client

### Testing Tools
- [clients/slack_user_client.py](clients/slack_user_client.py) — Python API for DMing Brain Assistant as Eugene
- [tools/slack_as_me.py](tools/slack_as_me.py) — CLI wrapper for `slack_user_client`
- [tests/challenges/](tests/challenges/) — **CREATE THIS DIRECTORY** for challenge scripts

---

## Success Metrics

After 5-10 challenge scripts, Brain Assistant should:
- ✅ Recall information from past conversations (cxdb)
- ✅ Surface relevant brain file context (Khoj with filtering)
- ✅ Handle long conversations without context overflow (summarization)
- ✅ Offer to save important information to brain (proactive writes)
- ✅ Process uploaded files (PDF, markdown, code)
- ✅ Cite sources when referencing brain files
- ✅ Maintain context across multi-turn exchanges

---

## Important Reminders

1. **Vaultwarden-only for secrets** — No env var fallback, ever
2. **Test suite must stay green** — Run `pytest tests/ -m "unit or integration"` after each change
3. **Target llama3.2** — Small context window, be ruthless about token usage
4. **Use slack-as-me for all manual testing** — No clicking in Slack UI
5. **Commit after each passing challenge** — Keep git history clean

---

## Next Agent: Your Mission

1. **Create `tests/challenges/` directory**
2. **Write and run `01_cxdb_recall.py`** (expect failure)
3. **Implement cxdb conversation search in `_process_message()`**
4. **Verify challenge passes**
5. **Commit the change**
6. **Write `02_khoj_relevance_filter.py`**
7. **Repeat until Brain Assistant is actually useful**

**Questions?** Check:
- [CLAUDE.md](CLAUDE.md) — Project instructions and token inventory
- [.github/copilot-instructions.md](.github/copilot-instructions.md) — Coding conventions
- `python -m tools.slack_as_me --agent-instructions` — Programmatic usage docs

**Ready?** Start with challenge #1 and press the accelerator. Make Brain Assistant SMART! 🧠🚀
