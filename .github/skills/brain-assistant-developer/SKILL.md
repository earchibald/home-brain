````skill
---
name: brain-assistant-developer
description: >-
  Develop, test, and tune the Brain Assistant Slack bot — a conversational AI agent with
  semantic search, multi-turn memory, and personal knowledge management. Use this skill
  when working on the slack_agent.py bot, conversation manager, LLM prompts, or running
  the brain_tuner.py evaluation suite. Covers the full stack from Slack event handling
  through conversation persistence (cxdb), brain search, and Ollama LLM inference.
  Also supports a feedback-driven improvement workflow: pull conversation logs, diagnose
  issues, implement fixes, deploy, and validate — triggered by a simple user command.
metadata:
  author: earchibald
  version: "2.0"
  project: home-brain
---

# Brain Assistant Developer Skill

You are an expert developer working on the Brain Assistant — a Slack bot that acts as
Eugene's personal AI companion with semantic search over markdown notes and persistent
multi-turn conversation memory.

## Trigger: Conversation Feedback Loop

When the user says any of the following trigger phrases, execute the **Feedback-Driven
Improvement Workflow** described below:

- "improve from chat logs"
- "review chat feedback"
- "what's wrong with Archie?"
- "tune the bot"
- "fix from conversation"
- "analyze chat history"

### Feedback-Driven Improvement Workflow

This is a structured, autonomous pipeline. Execute all steps in order. Use the todo
list to track progress through each phase.

#### Phase 1: Gather Conversation Data

1. **Pull latest conversation from cxdb/JSON:**
   ```bash
   # Try cxdb first (may return 424 — known issue with turns endpoint)
   curl -s http://nuc-1.local:9010/v1/contexts | python3 -m json.tool
   # Get the highest-numbered context ID, then:
   curl -s "http://nuc-1.local:9010/v1/contexts/{ID}/turns?limit=100"
   ```

2. **Fallback to JSON files on NUC-2 (if cxdb turns fail):**
   ```bash
   ssh nuc-2.local "ls -lt /home/earchibald/brain/users/U0AELV88VN3/conversations/"
   ssh nuc-2.local "cat /home/earchibald/brain/users/U0AELV88VN3/conversations/{LATEST}.json"
   ```

3. **Also check older conversation files** for recurring patterns:
   ```bash
   ssh nuc-2.local "ls -lt /home/earchibald/brain/users/U0AELV88VN3/conversations/ | head -5"
   ```

#### Phase 2: Analyze for Issues

Read the conversation JSON and look for these specific failure classes:

| Issue Class | What to Look For | Metadata Signal |
|-------------|-----------------|-----------------|
| **Identity confusion** | Bot confuses user/bot pronouns, wrong name attribution | Check if bot adopts user's name as its own or vice versa |
| **Web search not triggered** | User asks for real-world info, `web_search_used: false` | `web_search_used` field in message metadata |
| **Hallucinated results** | Bot claims to search but metadata proves it didn't | `web_search_used: false` + bot says "I searched" |
| **Capability unawareness** | Bot doesn't know its own tools (web search, brain search, /model, /apikey, etc.) | Generic LLM feature list instead of actual capabilities |
| **Conversation memory failure** | Bot forgets facts stated earlier in the same thread | Compare what user said in turn N with bot's response in turn N+M |
| **Brain search override** | Brain context overrides explicit user statement | Bot says brain-sourced info instead of what user told it |
| **Excessive verbosity** | "Notes so far:" on every message, unnecessary preambles | Response length, boilerplate patterns |
| **Wrong model behavior** | Latency spikes, model field doesn't match selection | `model` and `latency` in metadata |
| **Summarization leak** | Summarizer called Ollama when Gemini selected | Sudden latency spike mid-conversation |

For each issue found, record:
- **Turn numbers** where it appears
- **User's exact words** that triggered the issue
- **Bot's response** (problematic part)
- **Root cause hypothesis** mapping to code location
- **Severity**: P0 (broken), P1 (degraded), P2 (annoying)

#### Phase 3: Map Issues to Code

Use these mappings to find the code that needs fixing:

| Issue Category | Primary File | Key Location |
|---------------|-------------|--------------|
| Identity/pronoun confusion | `agents/slack_agent.py` | `self.system_prompt` (~L224-256) |
| Web search not triggering | `agents/slack_agent.py` | `_should_web_search()` (~L1771-1835) |
| Capability unawareness | `agents/slack_agent.py` | `self.system_prompt` (~L224-256) |
| Conversation memory failure | `clients/conversation_manager.py` | `load_conversation()`, `save_message()` |
| Brain search override | `agents/slack_agent.py` | `_process_message()` (~L1528-1718), message construction |
| Excessive verbosity | `agents/slack_agent.py` | `self.system_prompt` |
| Wrong model behavior | `agents/slack_agent.py` | `_generate_with_provider()` (~L309-394) |
| Summarization model | `clients/conversation_manager.py` | `summarize_if_needed()` |
| Conversational filter | `agents/slack_agent.py` | `_is_conversational()` (~L1837-1881) |

Read the relevant code sections, understand the current implementation, then proceed.

#### Phase 4: Implement Fixes

1. **Make surgical changes** — fix only what's broken, don't refactor unrelated code
2. **Run unit + integration tests locally:**
   ```bash
   python -m pytest tests/ -m "unit or integration" -v
   ```
3. **Verify no regressions** — all existing tests must still pass

#### Phase 5: Deploy and Validate

1. **Deploy to NUC-2:**
   ```bash
   # Deploy specific files that changed
   rsync -av agents/slack_agent.py nuc-2.local:/home/earchibald/agents/agents/
   rsync -av clients/conversation_manager.py nuc-2.local:/home/earchibald/agents/clients/
   # Add any other changed files...

   ssh nuc-2.local "sudo systemctl restart brain-slack-bot"
   ```

2. **Verify service is running:**
   ```bash
   ssh nuc-2.local "sudo systemctl status brain-slack-bot --no-pager"
   ```

3. **Run brain tuner for regression check:**
   ```bash
   eval "$(ssh nuc-1.local 'cat /home/earchibald/agents/.vaultwarden')"
   python tools/brain_tuner.py --scenario all --verbose
   ```

4. **Tail logs and confirm healthy behavior:**
   ```bash
   ssh nuc-2.local "sudo journalctl -u brain-slack-bot --since '2 minutes ago' --no-pager"
   ```

#### Phase 6: Report

Provide a summary to the user with:
- Issues found (table format)
- Fixes applied (with file/line references)
- Test results
- Tuner results
- Any remaining issues that need manual attention or larger architectural work

### Known Issue Patterns (Updated from Chat Analysis)

These patterns have been observed in production conversations and should be checked
for during every feedback loop run:

**1. Identity Confusion with Small Models (llama3.2)**
The bot confuses user/bot identity when names are assigned. Example: User says "I'll
call you Archie" → bot responds "Eugene (aka Archie)". The system prompt addresses
this but llama3.2 doesn't follow it reliably.
- **Fix approach**: Add few-shot examples to system prompt showing correct behavior
- **Monitor**: Turn pairs where user corrects the bot about names

**2. Web Search False Negatives**
`_should_web_search()` uses pattern matching and misses many valid search queries.
Example: "Return a list of top 3 episodes of The Jeffersons" → no match, no search.
- **Fix approach**: Add broader trigger patterns, or flip to a deny-list model
- **Monitor**: Messages where `web_search_used: false` but topic is clearly external

**3. Capability Hallucination**
Bot has no awareness of its actual tool set. When asked "What can you do?", it lists
generic LLM features instead of: brain search, web search, file upload analysis,
save-to-brain, /model, /apikey, /reset, /index.
- **Fix approach**: Add capabilities list to system prompt
- **Monitor**: Any "What can you do?" type question in logs

**4. LLM Claims Actions It Didn't Take**
Bot says "I searched the web" when metadata shows `web_search_used: false`. This is
a hallucination/confabulation pattern.
- **Fix approach**: Inject action metadata into context (e.g., "[Note: web search was
  NOT performed for this query]") so the LLM can't lie about what happened

---

## Architecture Overview

```
User (Slack DM) → SlackAgent (NUC-2) → OllamaClient (m1-mini.local:11434)
                      ↓                    OR → GeminiProvider (API)
              ConversationManager                    ↑
              (cxdb + JSON fallback)          System Prompt +
                      ↓                      Chat History +
              SemanticSearchClient            Brain Context +
              (nuc-1.local:9514)             Web Search Results
                      ↓
              WebSearchClient
              (DuckDuckGo / Tavily)
```

### Key Insight: DM Conversation Keying

DMs use `channel_id` as the conversation key (not `thread_ts`). In Slack DMs, each
message has a unique `ts` but no `thread_ts`. Using `channel_id` ensures all messages
in a DM conversation share one persistent history.

```python
# In handle_message:
if channel_type == "im":
    thread_ts = event.get("thread_ts") or channel_id  # channel_id for DMs
else:
    thread_ts = event.get("thread_ts", event.get("ts"))  # thread_ts for channels
```

## File Map

| File | Purpose |
|------|---------|
| [agents/slack_agent.py](../../agents/slack_agent.py) | Main bot — event handlers, _process_message, prompt construction, /model, /apikey, /reset, /index |
| [clients/conversation_manager.py](../../clients/conversation_manager.py) | Conversation persistence (cxdb + JSON dual-write), summarization |
| [clients/llm_client.py](../../clients/llm_client.py) | Ollama API client (chat, complete, embeddings) |
| [clients/semantic_search_client.py](../../clients/semantic_search_client.py) | ChromaDB semantic search client |
| [clients/cxdb_client.py](../../clients/cxdb_client.py) | AI Context Store (DAG-based conversation history) |
| [clients/web_search_client.py](../../clients/web_search_client.py) | DuckDuckGo/Tavily web search |
| [clients/slack_user_client.py](../../clients/slack_user_client.py) | Test client — sends messages AS the user |
| [providers/gemini_adapter.py](../../providers/gemini_adapter.py) | GeminiProvider with quota handling |
| [slack_bot/model_selector.py](../../slack_bot/model_selector.py) | Block Kit UI for /model command (dynamic provider/model filtering) |
| [slack_bot/file_handler.py](../../slack_bot/file_handler.py) | File download and text extraction |
| [tools/brain_tuner.py](../../tools/brain_tuner.py) | Dynamic conversation evaluation agent |
| [tests/automated_checklist.py](../../tests/automated_checklist.py) | E2E test suite |

## Bot Capabilities (What the LLM Can Actually Do)

The LLM itself has **no tool-use / function-calling capability**. All capabilities are
orchestrated by Python code before/after the LLM call:

| Capability | Trigger | Implementation |
|-----------|---------|---------------|
| **Brain search** | Non-conversational messages >10 chars | `SemanticSearchClient` → ChromaDB (nuc-1.local:9514) |
| **Web search** | `_should_web_search()` pattern match | `WebSearchClient` → DuckDuckGo/Tavily |
| **Conversation memory** | Always (DM channel keying) | `ConversationManager` → cxdb + JSON files |
| **Past conversation recall** | Always (query-based search) | `ConversationManager.search_past_conversations()` |
| **File analysis** | Slack file attachment detected | `FileHandler` → text extraction → injected into context |
| **Save to brain** | Bot suggests via `_should_suggest_save()` | `BrainIO` or `SemanticSearchClient` upload |
| **Model switching** | `/model` slash command | `ModelManager` + `model_selector.py` UI |
| **Gemini integration** | `/apikey` + `/model` select Gemini provider | `GeminiProvider` with quota fallback to Ollama |
| **Conversation reset** | `/reset` slash command (triple confirmation) | `ConversationManager.delete_conversation()` |
| **Index management** | `/index` slash command | Browse, ignore, delete, gate, reindex brain folders |

**Critical gap**: The LLM has no way to invoke tools itself. It cannot decide to
search the web — that decision is made by pattern matching in Python. Future work:
implement MCP client/server for structured tool dispatch.

## Development Workflow

### 1. Make Changes

Edit files locally, then deploy to NUC-2:

```bash
rsync -av agents/slack_agent.py nuc-2.local:/home/earchibald/agents/agents/
ssh nuc-2.local "sudo systemctl restart brain-slack-bot"
```

### 2. Test with Brain Tuner

```bash
# Load Vaultwarden credentials (required for SlackUserClient)
eval "$(ssh nuc-1.local 'cat /home/earchibald/agents/.vaultwarden')"

# Run the name recall scenario (primary success metric)
python tools/brain_tuner.py --scenario name-recall --verbose

# Run all scenarios
python tools/brain_tuner.py --scenario all --report /tmp/tuner-report.json
```

### 3. Check Bot Logs

```bash
ssh nuc-2.local "sudo journalctl -u brain-slack-bot -f --no-pager"
```

Key log patterns:
- `history: N msgs` — conversation history loaded (should be >0 for follow-ups)
- `Skipping brain search for conversational message` — conversational filter working
- `Found N relevant brain entries` — brain search results returned

### 4. Run Unit + Integration Tests

```bash
python -m pytest tests/ -m "unit or integration" -v
```

### 5. Run E2E Suite

```bash
eval "$(ssh nuc-1.local 'cat /home/earchibald/agents/.vaultwarden')"
python tests/automated_checklist.py --categories 1,2,3
```

## Prompt Architecture

The system prompt and message construction are the two most critical tuning points:

### System Prompt (in slack_agent.py ~L224-256)

The system prompt establishes:
1. **Identity rules** — explicit "you are the bot, user is the human" with naming examples
2. **Conversation memory is primary** — the bot remembers what was said in this chat
3. **Brain search is supplementary** — only used when the question is knowledge-seeking
4. **No over-reliance on documents** — brain results must be genuinely relevant
5. **Capabilities awareness** — should list what the bot can actually do (gap: currently missing)

### Message Construction (in _process_message ~L1528-1718)

```python
messages = [
    Message(role="system", content=system_prompt),
    # CONVERSATION HISTORY — primary context
    *[Message(role=msg["role"], content=msg["content"]) for msg in history],
    # SUPPLEMENTARY CONTEXT — only if relevant
    Message(role="system", content=f"[Supplementary context...]\n{brain_results}"),  # optional
    # USER'S ACTUAL MESSAGE — last, so it's fresh in attention
    Message(role="user", content=text),
]
```

Key principle: Brain context is injected as a system message between history and the
user message, NOT prepended to the user message. This prevents the LLM from treating
brain search results as the user's words.

### Conversational Filter (_is_conversational ~L1837-1881)

`_is_conversational(message)` detects messages that should skip brain search entirely:
- Short messages (<30 chars)
- Greetings, follow-ups, personal facts
- Recall questions ("what did I say", "do you remember")

### Web Search Trigger (_should_web_search ~L1771-1835)

Pattern-based decision for web search. Known gaps:
- Misses factual queries that don't contain explicit "search" keywords
- Can't detect when brain context is insufficient for the question

## Common Issues and Fixes

### Bot shows "history: 0 msgs" for every DM

**Root cause:** `thread_ts` resolving to `event["ts"]` (unique per message).
**Fix:** Use `channel_id` as conversation key for DMs.

### Bot over-relies on brain search results

**Root cause:** Brain context was prepended to user message, making the LLM treat it as the question.
**Fix:** Inject brain context as a separate system message marked "[Supplementary context]".

### Bot doesn't recall conversation facts

**Check:** Is `_is_conversational()` correctly classifying the message? Is history loading?
**Debug:** Check logs for `history: N msgs` — should be >0 for follow-up messages.

### Conversation files pile up with 1 message each

**Root cause:** Same as "history: 0 msgs" — each message creates a new file.
**Fix:** Use `channel_id` keying.

### Bot confuses user name and bot name

**Root cause:** Small models (llama3.2) struggle with pronoun resolution in naming context.
**Fix:** Add few-shot examples to system prompt. Consider stronger model for complex conversations.

### Web search not triggered for explicit requests

**Root cause:** `_should_web_search()` doesn't match queries like "list the top episodes of X".
**Fix:** Add more trigger patterns or flip to deny-list approach.

### Bot claims it searched when it didn't

**Root cause:** LLM confabulates actions. No metadata injection tells it what actually happened.
**Fix:** Add `[Actions taken: brain_search=yes, web_search=no]` to context.

## Success Metrics

The primary metric is the **name-recall scenario**: Can the bot remember who we are
and what name we gave it, 5 chat turns later?

```bash
python tools/brain_tuner.py --scenario name-recall
```

All checks should pass:
- Turn 1: Acknowledges the name
- Turn 4: Recalls the name when asked
- Turn 5: Recalls the project name when asked

## Secrets Management

All secrets are in Vaultwarden (vault.nuc-1.local). Load them with:

```bash
eval "$(ssh nuc-1.local 'cat /home/earchibald/agents/.vaultwarden')"
```

**Never** use `os.getenv()` for secrets in production code. Use `get_secret()` from
`clients/vaultwarden_client.py`.

## Model Configuration

| Provider | Models | Notes |
|----------|--------|-------|
| Ollama | llama3.2 (default), llama3.1:8b | Local, m1-mini.local:11434 |
| Gemini | gemini-pro (2.0-flash), gemini-flash, gemini-flash-lite | Per-user API key, quota fallback to Ollama |

Switching via `/model` command. Provider + model selection persists per session.
Gemini keys managed via `/apikey` command (stored in `~/.brain-api-keys.json` on NUC-2).
````
