---
name: brain-assistant-developer
description: >-
  Develop, test, and tune the Brain Assistant Slack bot — a conversational AI agent with
  semantic search, multi-turn memory, and personal knowledge management. Use this skill
  when working on the slack_agent.py bot, conversation manager, LLM prompts, or running
  the brain_tuner.py evaluation suite. Covers the full stack from Slack event handling
  through conversation persistence (cxdb), brain search, and Ollama LLM inference.
metadata:
  author: earchibald
  version: "1.0"
  project: home-brain
---

# Brain Assistant Developer Skill

You are an expert developer working on the Brain Assistant — a Slack bot that acts as
Eugene's personal AI companion with semantic search over markdown notes and persistent
multi-turn conversation memory.

## Architecture Overview

```
User (Slack DM) → SlackAgent (NUC-2) → OllamaClient (m1-mini.local:11434)
                      ↓                         ↑
              ConversationManager          System Prompt +
              (cxdb + JSON fallback)      Chat History +
                      ↓                  Brain Context
              SemanticSearchClient
              (nuc-1.local:9514)
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
| [agents/slack_agent.py](../../agents/slack_agent.py) | Main bot — event handlers, _process_message, prompt construction |
| [clients/conversation_manager.py](../../clients/conversation_manager.py) | Conversation persistence (cxdb + JSON dual-write) |
| [clients/llm_client.py](../../clients/llm_client.py) | Ollama API client (chat, complete, embeddings) |
| [clients/semantic_search_client.py](../../clients/semantic_search_client.py) | ChromaDB semantic search client |
| [clients/cxdb_client.py](../../clients/cxdb_client.py) | AI Context Store (DAG-based conversation history) |
| [clients/slack_user_client.py](../../clients/slack_user_client.py) | Test client — sends messages AS the user |
| [tools/brain_tuner.py](../../tools/brain_tuner.py) | Dynamic conversation evaluation agent |
| [tests/automated_checklist.py](../../tests/automated_checklist.py) | E2E test suite |

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

### 4. Run E2E Suite

```bash
eval "$(ssh nuc-1.local 'cat /home/earchibald/agents/.vaultwarden')"
python tests/automated_checklist.py --categories 1,2,3
```

## Prompt Architecture

The system prompt and message construction are the two most critical tuning points:

### System Prompt (in slack_agent.py)

The system prompt establishes:
1. **Conversation memory is primary** — the bot remembers what was said in this chat
2. **Brain search is supplementary** — only used when the question is knowledge-seeking
3. **No over-reliance on documents** — brain results must be genuinely relevant

### Message Construction

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

### Conversational Filter

`_is_conversational(message)` detects messages that should skip brain search entirely:
- Short messages (<30 chars)
- Greetings, follow-ups, personal facts
- Recall questions ("what did I say", "do you remember")

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
