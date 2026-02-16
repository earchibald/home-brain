# Brain Assistant Architecture Reference

## Message Flow (DM)

```
1. User sends DM to Brain Assistant in Slack
2. Slack Socket Mode delivers event to SlackAgent.handle_message()
3. Handler extracts:
   - user_id: Slack user ID
   - channel_id: DM channel (stable, same for all DMs with this user)
   - thread_ts: channel_id for top-level DMs, thread_ts for threaded replies
   - text: user's message
4. SlackAgent._process_message() is called with (user_id, text, thread_ts)
5. ConversationManager.load_conversation(user_id, thread_ts) loads history
6. If history > token threshold, summarize older messages
7. Search past conversations for relevant context (keyword match)
8. If not conversational: search brain (ChromaDB semantic search)
9. If web-worthy: search web (DuckDuckGo)
10. Build LLM message list:
    [system_prompt] + [history...] + [supplementary_context?] + [user_message]
11. OllamaClient.chat(messages) → response
12. Save both user message and response to ConversationManager
13. Return response text to Slack
```

## Conversation Manager Dual-Write

Messages are written to BOTH:
1. **cxdb** (primary, best-effort) — HTTP API on nuc-1.local:9010
2. **JSON files** (fallback, always) — /home/earchibald/brain/users/{user_id}/conversations/{thread_id}.json

Reads prefer cxdb if a context mapping exists, fall back to JSON otherwise.

## Context Map (cxdb_map.json)

Maps Slack thread/channel IDs to cxdb context IDs:

```json
{
  "D0ABCDEF123": 55,  // DM channel → cxdb context
  "1771234567.890123": 12  // Thread ts → cxdb context (legacy)
}
```

## Token Budget

- `max_context_tokens`: 6000 (total budget for LLM context window)
- `context_budget`: 2000 (reserved for brain + web context injection)
- `summarization_threshold`: max_context_tokens - context_budget = 4000
- When history exceeds threshold, older messages are summarized by the LLM

## Relevance Filtering

Brain search results are filtered by `min_relevance_score` (default: 0.7).
Only results above this threshold are included. If all results are below
threshold, the single best result is kept as a fallback.

## Conversational Message Detection

`_is_conversational(message)` returns True for messages that should skip
brain search. This prevents the bot from pulling irrelevant document context
for conversational exchanges.

Categories:
- Short messages (<30 chars)
- Greetings: "hello", "hey", "hi", "good morning"
- Follow-ups: "what did I", "do you remember", "earlier I", "I told you"
- Personal facts: "my name is", "call me", "I'm working on"
- Conversation management: "thanks", "ok", "never mind"
- Meta-conversational: "can you help", "let's talk about"

## Service Endpoints

| Service | Host | Port | Purpose |
|---------|------|------|---------|
| Brain Assistant (Slack) | nuc-2.local | Socket Mode | Bot service |
| Semantic Search (ChromaDB) | nuc-1.local | 9514 | Brain search |
| Ollama | m1-mini.local | 11434 | LLM inference |
| cxdb | nuc-1.local | 9010 | Conversation store |
| Vaultwarden | vault.nuc-1.local | 443 | Secrets |
| Web Search | DuckDuckGo | HTTPS | Web lookup |
