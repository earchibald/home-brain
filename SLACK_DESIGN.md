# Slack Agent Integration - Design Document

**Status:** In Development  
**Target:** Multi-turn AI conversation bot in Slack DMs  
**Date:** February 14, 2026

## Mission Arc

Build a Slack bot that connects your semantic brain to Slack, enabling natural conversation with:
- **Per-user context isolation** - Each Slack user gets `brain/users/{user_id}/` folder
- **Multi-turn memory** - Conversations persist across messages with automatic summarization
- **Khoj-powered context** - Bot searches your brain before responding
- **Ollama inference** - Uses existing llama3.2 on Mac Mini
- **Socket Mode** - No webhooks, no NAT traversal issues

## Architecture

```
Slack Cloud
    ↓ (WebSocket - Socket Mode)
NUC-2: slack_agent.py
    ↓
conversation_manager.py → brain/users/{user_id}/conversations/
    ↓
khoj_client.py → Search brain for context
    ↓
llm_client.py → Ollama (Mac Mini)
    ↓
Response → Slack
```

## Why This Design?

- **Socket Mode:** NUCs behind NAT, Socket Mode uses persistent WebSocket (no public endpoint needed)
- **Per-user isolation:** Privacy + personalization - each user's data stays separate
- **Conversation summarization:** Llama 3.2 has 8K context - summarize old messages when needed
- **Reuse existing framework:** [agent_platform.py](agent_platform.py), [khoj_client.py](khoj_client.py), [llm_client.py](llm_client.py) already built
- **Systemd service:** Production-grade process management, auto-restart, logging

## Component Overview

### 1. `conversation_manager.py` (New)
Manages conversation history storage and retrieval.

**Key Methods:**
- `load_conversation(user_id, thread_id)` → List[Dict]
- `save_message(user_id, thread_id, role, content)` → None
- `summarize_if_needed(messages, max_tokens=6000)` → List[Dict]
- `estimate_tokens(text)` → int

**Storage Format:** `brain/users/{user_id}/conversations/{thread_id}.json`
```json
{
  "thread_id": "1234567890.123456",
  "user_id": "U01ABC123",
  "created_at": "2026-02-14T10:00:00Z",
  "updated_at": "2026-02-14T10:05:30Z",
  "messages": [
    {"role": "user", "content": "Hello!", "timestamp": "2026-02-14T10:00:00Z"},
    {"role": "assistant", "content": "Hi! How can I help?", "timestamp": "2026-02-14T10:00:05Z"}
  ]
}
```

### 2. `slack_agent.py` (New)
Main Slack bot logic - extends `Agent` base class.

**Key Responsibilities:**
- Initialize Slack Bolt app with Socket Mode
- Register event handlers for DM messages
- Load conversation history
- Search Khoj for relevant context
- Call Ollama for response generation
- Save conversation and post to Slack

**Message Flow:**
1. Slack message event → extract user_id, text, thread_ts
2. Load conversation from `conversation_manager`
3. Optional: Search Khoj for context matching message content
4. Build prompt: system + history + context + user message
5. Call `llm_client.chat(messages)` with llama3.2
6. Save response to conversation history
7. Post to Slack thread

### 3. `slack_bot.py` (New)
Launcher script - entry point for systemd service.

**Responsibilities:**
- Load secrets from environment (SLACK_APP_TOKEN, SLACK_BOT_TOKEN)
- Initialize SlackAgent
- Call `platform.start_service(slack_agent)` (blocks forever)
- Handle signals for graceful shutdown

### 4. `agent_platform.py` (Update)
Add support for long-running service agents.

**New Method:** `start_service(agent)`
- Runs `await agent.run()` indefinitely
- Catches exceptions, sends ntfy notification
- Auto-restarts on failure
- Logs to agent-specific JSONL file

### 5. Systemd Service (Deploy)
Production deployment configuration.

**File:** `/etc/systemd/system/brain-slack-bot.service`
- Auto-start on boot
- Auto-restart on crash
- Integrated with journalctl logging
- Runs as earchibald user

## Implementation Steps

### Phase 1: Core Components (First)
1. ✅ Create `clients/conversation_manager.py` - History storage/retrieval
2. ✅ Create `agents/slack_agent.py` - Main bot logic
3. ✅ Update `agent_platform.py` - Add `start_service()` method
4. ✅ Create `slack_bot.py` - Launcher script

### Phase 2: Slack App Setup
1. Create app at api.slack.com/apps
2. Enable Socket Mode → Get `SLACK_APP_TOKEN` (xapp-*)
3. Add Bot Token Scopes:
   - `app_mentions:read`
   - `chat:write`
   - `im:history`
   - `im:read`
   - `im:write`
4. Install to workspace → Get `SLACK_BOT_TOKEN` (xoxb-*)
5. Add tokens to `secrets.env`:
   ```bash
   export SLACK_APP_TOKEN="xapp-..."
   export SLACK_BOT_TOKEN="xoxb-..."
   ```

### Phase 3: Deploy to NUC-2
1. Install dependencies: `pip install slack-bolt slack-sdk`
2. Copy files to NUC-2: `~/agents/`
3. Test manually: `python slack_bot.py`
4. Create systemd service
5. Enable & start: `sudo systemctl enable --now brain-slack-bot`

### Phase 4: Testing & Validation
1. **Connection:** Verify systemd status shows "active (running)"
2. **Hello world:** DM bot "Hello!" → receives response < 30s
3. **Multi-turn:** Send 3+ messages → bot references history
4. **Context:** Ask about brain content → bot searches Khoj
5. **User isolation:** Second user DMs → separate conversation files
6. **Error handling:** Stop Ollama → bot sends friendly error message
7. **Persistence:** Restart service → conversations still accessible

## Configuration

### Environment Variables (secrets.env)
```bash
# Slack tokens (get from api.slack.com)
export SLACK_APP_TOKEN="xapp-1-..."
export SLACK_BOT_TOKEN="xoxb-..."

# Existing (already configured)
export KHOJ_URL="http://192.168.1.195:42110"
export OLLAMA_URL="http://192.168.1.58:11434"
export BRAIN_FOLDER="/home/earchibald/brain"
export NTFY_TOPIC="brain-notifications"
```

### Agent Configuration (config.yaml)
```yaml
agents:
  slack_agent:
    enabled: true
    service: true  # Runs continuously, not cron-scheduled
    model: "llama3.2"
    max_context_tokens: 6000
    enable_khoj_search: true
    search_before_response: true
    max_search_results: 3
    notification:
      on_error: true
      on_start: true
```

## Conversation Management

### Token Budget
- **Llama 3.2 context window:** 8192 tokens
- **Reserve for response:** 2048 tokens
- **Available for prompt:** 6144 tokens
- **Breakdown:**
  - System prompt: ~200 tokens
  - Khoj context (optional): ~1000 tokens
  - Conversation history: ~4944 tokens
  - User message: Variable

### Summarization Strategy
When conversation exceeds ~4000 tokens:
1. Keep system prompt + last 3 messages (always fresh)
2. Summarize older messages using Ollama:
   ```
   Summarize this conversation history concisely, preserving key facts and context:
   [older messages]
   ```
3. Replace old messages with summary
4. Continue conversation with compressed history

### File Structure
```
brain/
├── users/
│   ├── U01ABC123/  # Slack user ID
│   │   ├── conversations/
│   │   │   ├── 1234567890.123456.json  # Thread timestamp
│   │   │   ├── 1234567891.234567.json
│   │   │   └── ...
│   │   └── context/  # Future: user-specific notes
│   │       └── profile.md
│   └── U02DEF456/
│       └── conversations/
│           └── ...
```

## Error Handling

### Graceful Degradation
1. **Ollama unavailable** → "Sorry, my AI backend is temporarily unavailable. Please try again shortly."
2. **Khoj unavailable** → Skip context search, still generate response
3. **Conversation file corrupt** → Start new conversation, log error
4. **Token limit exceeded** → Force summarization, retry
5. **Slack API error** → Retry with exponential backoff (3 attempts)

### Notifications
- **Critical errors** → ntfy.sh alert + log to `logs/slack_agent.jsonl`
- **Service start/stop** → Info notification
- **High response latency (>30s)** → Warning notification

## Security & Privacy

### Token Management
- Slack tokens stored in `secrets.env` (encrypted with SOPS)
- Never log tokens or user message content
- Environment variables loaded at runtime only

### User Data
- Each user's conversations isolated in separate folders
- No cross-user data access
- Conversation files readable only by bot (cron job permissions)
- Future: Add user consent tracking for data retention

### Rate Limiting
- Max 10 concurrent conversations
- Max 100 messages/hour per user
- Ollama queue to prevent overload

## Future Enhancements

### Phase 2 Features
- **Slash commands:** `/brain search <query>`, `/brain summarize today`
- **Thread support:** Respond in public channels when mentioned
- **File uploads:** Accept PDFs/docs → ingest into brain
- **Proactive agents:** Bot DMs you with daily journal/advice prompts

### Phase 3 Features
- **Voice notes:** Transcribe audio messages → text conversation
- **Image analysis:** Describe/OCR images shared in DMs
- **Task management:** Create/track TODOs in brain
- **Calendar integration:** Schedule-aware responses

### Phase 4 Features
- **Multi-modal:** Images, PDFs, audio all in one conversation
- **Agent router:** Detect intent → route to specialized agents
- **Collaborative brain:** Shared brain access with permission controls
- **Analytics:** Conversation insights, usage patterns

## Success Criteria

### Minimum Viable Product (MVP)
- ✅ Bot responds to Slack DMs using llama3.2
- ✅ Conversations persist across messages
- ✅ Per-user isolation (separate brain folders)
- ✅ Systemd service runs 24/7 on NUC-2
- ✅ Error handling with user-friendly messages

### Stretch Goals
- Context-aware responses (searches Khoj before replying)
- Summarization when conversations get long
- Sub-5 second response time for simple queries
- Proactive notifications (daily journal prompts)

## Development Timeline

- **Day 1 (Today):** Core implementation (conversation_manager, slack_agent, platform updates)
- **Day 2:** Slack app setup, token configuration, initial deployment
- **Day 3:** Testing, debugging, user isolation validation
- **Day 4:** Systemd service, production deployment
- **Day 5:** Monitoring, optimization, documentation

## References

- [NUC2_AGENT_FRAMEWORK.md](NUC2_AGENT_FRAMEWORK.md) - Agent platform architecture
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - System topology
- [Slack Bolt Python SDK](https://slack.dev/bolt-python/)
- [Socket Mode Docs](https://api.slack.com/apis/connections/socket)

---

**Next Steps:** Create `conversation_manager.py`, `slack_agent.py`, update `agent_platform.py`, create launcher.
