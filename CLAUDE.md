# Claude Code Instructions for /Users/earchibald/LLM/implementation

## CRITICAL: secrets.env Handling

**secrets.env is encrypted with SOPS (Age encryption). Mishandling it causes data loss.**

### Setup
Before ANY sops operation, source the .env file to load the age key:
```bash
source /Users/earchibald/LLM/implementation/.env
```

### Safe Update Pattern
**ALWAYS use `sops set` to add/modify vars — this is the safest method:**

```bash
source .env
sops set secrets.env '["NEW_VAR"]' '"new_value"'
```

Example:
```bash
source .env
sops set secrets.env '["BILLING_NOTIFICATIONS_TOPIC"]' '"billing-notifications-uuid-here"'
```

Verify it worked:
```bash
sops -d secrets.env
```

### Alternative: Decrypt → Edit → Re-encrypt (if needed for bulk changes)
If you need to add many vars at once:

1. **Backup first:**
   ```bash
   cp secrets.env secrets.env.backup
   ```

2. **Decrypt:**
   ```bash
   source .env
   sops -d secrets.env > /tmp/secrets_plain.env
   ```

3. **Edit plaintext:**
   ```bash
   echo "NEW_VAR=value" >> /tmp/secrets_plain.env
   cat /tmp/secrets_plain.env  # Verify
   ```

4. **Use `sops set` for each line** (safer than trying to re-encrypt):
   ```bash
   source .env
   while IFS='=' read -r key value; do
     sops set secrets.env "[\"$key\"]" "\"$value\""
   done < /tmp/secrets_plain.env
   rm /tmp/secrets_plain.env
   ```

### DO NOT DO THIS
- ❌ Try to `sops -e` on a plaintext file (creates corrupt encrypted files)
- ❌ Try to `sops -e -i` on a file without SOPS metadata
- ❌ Pipe `sops -d` to `sops -e` directly
- ❌ Use editor mode (`sops secrets.env`) — it requires a terminal
- ❌ Forget to `source .env` before running sops commands
- ❌ Run sops commands from a different directory (rules are path-relative)

### Backup Recovery
If you corrupt secrets.env:
```bash
cp secrets.env.backup secrets.env
```

---

## Project Structure

- `IMPLEMENTATION.md` — Main architecture & setup guide
- `AGENT-INSTRUCTIONS.md` — Current working state of all NUCs (reference doc)
- `IMPLEMENTATION_ADDENDUM.md` — Latest session changes
- `SESSION_HANDOFF_*.md` — Transition docs between sessions
- `.env` — Loads SOPS_AGE_KEY_FILE (required before sops commands)
- `secrets.env` — SOPS-encrypted environment variables
- `.sops.yaml` — SOPS config with Age encryption rules

---

## Host Access

All passwordless via SSH configured user `earchibald`:
- `ssh nuc-1` (nuc-1.local) — Khoj + Postgres + Syncthing
- `ssh nuc-2` (nuc-2.local) — Automation + Syncthing
- `ssh nuc-3` (nuc-3.local) — Storage + Restic + Syncthing + rclone + pCloud

All have passwordless sudo for `earchibald` user.

---

## Deployment to NUC-2: rsync Safety — CRITICAL

**NEVER use `rsync --delete` when deploying to NUC-2. This will delete pre-existing files.**

NUC-2 contains files that are NOT in the git repository:
- `venv/` — Python virtual environment created during bootstrap (required for service to run)
- `secrets.env` — Encrypted secrets file ignored by gitignore, essential for runtime
- `~/.brain-facts-*.json` — Per-user facts data generated at runtime
- Service state files from systemd

### Safe Deployment
Use rsync with explicit exclusions:

```bash
rsync -avz --exclude venv --exclude secrets.env --exclude ".brain-facts*" \
  /Users/earchibald/LLM/implementation/ nuc-2:/home/earchibald/agents/
```

### After Deployment
Always verify that critical files still exist:

```bash
ssh nuc-2 "ls -la /home/earchibald/agents/venv && \
  test -f /home/earchibald/agents/secrets.env && \
  echo '✅ Deployment OK' || echo '❌ MISSING CRITICAL FILES'"
```

### Lesson Learned: What happens with `--delete`

During Phase 6-7 deployment, rsync with `--delete` was used which caused:
1. `venv/` was deleted (not in local repo)
2. `secrets.env` was deleted (in gitignore, not in repo)
3. Service failed to restart with exit code 127 (python3: command not found)
4. Manual intervention required to recreate venv and restore secrets.env

This is why the exclusion pattern is now mandatory for NUC-2 deployments.

---

## CRITICAL: Secrets Management — Vaultwarden Only

**ALL secrets and tokens MUST be stored in Vaultwarden exclusively.**

- **NO environment variable fallback** — If a secret isn't in Vaultwarden, the code must fail loudly
- **NO tokens in `.env` files, config files, or hardcoded in source**
- **NO `os.getenv()` for secrets** — Always use `VaultwardenClient.get_secret()`
- Vaultwarden credentials are at: `ssh nuc-1 cat /home/earchibald/agents/.vaultwarden`
- Vaultwarden URL: `https://vault.nuc-1.local/api`

### Slack Token Inventory (all in Vaultwarden)
- `SLACK_BOT_TOKEN` — Bot OAuth token (xoxb-) for Brain Assistant
- `SLACK_APP_TOKEN` — App-level token (xapp-) for Socket Mode
- `SLACK_USER_TOKEN` — User OAuth token (xoxp-) for programmatic DM access
- `BRAIN_BOT_USER_ID` — Brain Assistant's Slack user ID
- `SLACK_CONFIG_ACCESS_TOKEN` — Slack App Manifest API access token (12hr expiry)
- `SLACK_CONFIG_REFRESH_TOKEN` — Refresh token for rotating the config access token

---

## Slack App Management (Infrastructure-as-Code)

Slack apps are managed via manifests checked into `manifests/` directory.

### Slash Commands
- `/brain` - Query the knowledge base
- `/model` - Switch between LLM providers (Ollama, Gemini)
- `/apikey` - Manage Gemini API keys (add/view/delete)
- `/tools` - View/enable/disable tools with Block Kit toggles
- `/facts` - View/add/edit/delete personal facts with overflow menus
- `/mission` - View current mission principles

```bash
# Export live app config
python -m tools.slack_app_manager export --app-id A0AFX0RUJ8Y --out manifests/brain-assistant.json

# Update live app from manifest
python -m tools.slack_app_manager update --app-id A0AFX0RUJ8Y --manifest manifests/brain-assistant.json

# Rotate config token (12hr expiry)
python -m tools.slack_app_manager rotate-token
```

### Programmatic Slack User Client
```bash
# Send a DM as the user to Brain Assistant
python -m tools.slack_as_me ask "What's in my brain about backups?"

# Multi-turn conversation
python -m tools.slack_as_me converse

# Agent self-documentation
python -m tools.slack_as_me --agent-instructions
```

---

## Gemini Integration & API Key Management

Brain Assistant supports Google Gemini as an alternative to Ollama for LLM inference.

### Overview
- Per-user API keys stored in `~/.brain-api-keys.json` on NUC-2 (0600 permissions)
- Three Gemini models available:
  - `gemini-pro` (2.0-flash)
  - `gemini-flash` (2.0-flash)
  - `gemini-flash-lite` (2.0-flash-lite)
- Automatic fallback to Ollama on quota exhaustion (429 errors)
- Quota tracking with daily limits (1500 requests/day default)

### `/apikey` Slash Command
Users can manage their Gemini API keys via Slack:
```
/apikey
```
Opens a modal with:
- **Add/Update Key** - Enter new API key (masked input)
- **View Current Key** - Shows masked key (last 4 chars visible)
- **Delete Key** - Removes API key from storage

### Key Files
- `providers/gemini_adapter.py` - GeminiProvider with QuotaExhaustedError handling
- `agents/slack_agent.py` - ApiKeyStore class, `/apikey` command handler, `_generate_with_provider()` method
- `manifests/brain-assistant.json` - Slack app manifest with `/apikey` command registration

### Security
- API keys never logged or exposed in error messages
- Keys masked in UI (only last 4 characters shown)
- Storage file has 0600 permissions (owner read/write only)
- Keys scoped per Slack user ID

### Testing Integration
1. Use `/apikey` to add your Gemini API key
2. Use `/model` to select a Gemini provider (`gemini-pro`, `gemini-flash`, `gemini-flash-lite`)
3. Send a message to test generation
4. On quota exhaustion, bot automatically falls back to Ollama

---

## Key Decisions & Gotchas

1. **Khoj HTTP only** — No TLS on :42110. Use `http://nuc-1.local:42110` (not https)
2. **Restic password** — Local repo password stored unknown location (works via cron). pCloud repo password in `~/.restic-pcloud-password`
3. **Syncthing introducer** — NUC-3 acts as introducer but manual device/folder sharing was needed
4. **SOPS Age key** — Must be sourced before any `sops` command or it fails silently with "no matching creation rules"
5. **pCloud** — US region only (`api.pcloud.com`), rclone token stored in `~/.config/rclone/rclone.conf` on NUC-3
6. **Vaultwarden only** — All secrets must be in Vaultwarden. No environment variable fallback. No exceptions.

---

## Test Framework & Implementation Status (2026-02-14)

### Setup
Install test dependencies:
```bash
cd /Users/earchibald/LLM/implementation
pip install -r tests/requirements-test.txt
```

### Running Tests

**Run all tests:**
```bash
python -m pytest tests/ -v
```

**Run only GREEN tests (should all pass):**
```bash
python -m pytest tests/ -m "unit or integration" -v
```

**Run with coverage:**
```bash
python -m pytest tests/ --cov --cov-report=html
open htmlcov/index.html
```

### Current Status (Phase 1a+1b complete)
- ✅ **367 GREEN tests PASSING** — 209 baseline + 158 new tool architecture tests
- ✅ **Tool architecture deployed** — 3 tools registered, mission principles loaded
- ✅ **All slash commands wired** — /tools, /facts, /mission with Block Kit UIs
- ✅ **Committed** — `101d8b7`, deployed to NUC-2, health checks green

### Features Implemented via TDD

**1. File Attachment Handling** ✅
- Detects .txt, .md, .pdf file attachments in Slack messages
- Downloads files from Slack API with authentication
- Extracts text content with automatic truncation (max 1MB)
- Graceful error handling for unsupported types and download failures
- Location: `slack_bot/message_processor.py`, `slack_bot/file_handler.py`

**2. Response Streaming** ✅
- Streams responses from Ollama in real-time
- Incrementally updates Slack messages with partial responses
- Batches updates for reasonable frequency (not spamming)
- Falls back to non-streaming if failure occurs
- Location: `slack_bot/streaming_handler.py`, `slack_bot/slack_message_updater.py`, `slack_bot/ollama_client.py`

**3. Performance Monitoring** ✅
- Tracks response latencies and calculates metrics
- Computes average latency, P95 percentile, latency histogram
- Sends alerts when responses exceed threshold (default 30 seconds)
- Supports Slack notifications
- Location: `slack_bot/performance_monitor.py`, `slack_bot/alerting.py`

### Integration with slack_agent.py
These features are implemented but not yet integrated into the main agent. To enable:

1. **File attachments:** Add file detection to `handle_message()` event handler
2. **Streaming:** Update `_process_message()` to use `OllamaStreamingClient`
3. **Performance monitoring:** Add `PerformanceMonitor` instance and call `record_response_time()`

See next session section below.

### File Structure
```
slack_bot/
  ├── __init__.py
  ├── exceptions.py - Custom exception classes
  ├── message_processor.py - File detection from Slack events
  ├── file_handler.py - Download and text extraction
  ├── streaming_handler.py - Chunk processing
  ├── slack_message_updater.py - Incremental message updates
  ├── ollama_client.py - Streaming LLM client
  ├── performance_monitor.py - Latency tracking
  ├── alerting.py - Alert notifications
  ├── mission_manager.py - Hot-reload operator instructions from ~/.brain-mission.md
  ├── tools_ui.py - Block Kit UI for /tools command
  ├── facts_ui.py - Block Kit UI for /facts command
  └── tools/
      ├── __init__.py
      ├── base_tool.py - BaseTool ABC, ToolResult, UserScopedTool
      ├── tool_registry.py - ToolRegistry (register/enable/disable/list)
      ├── tool_executor.py - XML shim parsing, timeout guard, tool loop
      ├── tool_state.py - Per-user enable/disable state (JSON, 0600)
      ├── builtin/
      │   ├── web_search_tool.py - WebSearchTool wrapping WebSearchClient
      │   ├── brain_search_tool.py - BrainSearchTool wrapping SemanticSearchClient
      │   └── facts_tool.py - FactsStore + FactsTool (per-user memory)
      └── mcp/
          └── mcp_config.py - MCP server config (base + local merge)
```

---

## Recent Work

- **2026-02-14 Session A:** Fixed NUC-2/3 configs, enabled Syncthing, fixed journal_bot.py, configured Khoj indexing
- **2026-02-14 Session B:** Added pCloud offsite backup via rclone + Restic (browsable sync + encrypted backup)
- **2026-02-14 Session C:** Implemented comprehensive TDD test framework with pytest (49 GREEN + 20 RED tests)
- **2026-02-16 Session D:** Built Slack-as-user testing tools (SlackUserClient, slack-as-me CLI, manifest manager)
- **2026-02-16 Session E:** Fixed all 4 failing health check tests — 174/174 tests GREEN ✅
- **2026-02-16 Session F:** Integrated Google Gemini provider with dynamic API key management, quota handling, `/apikey` Slack command, automatic Ollama fallback
- **Phase 1a+1b:** Built pluggable tool architecture (BaseTool, ToolRegistry, ToolExecutor, ToolStateStore), FACTS per-user memory, MissionManager hot-reload, 3 built-in tools (web_search, brain_search, facts), `/tools`+`/facts`+`/mission` Slack slash commands, 158 new tests (367 total, 0 failures), committed `101d8b7`, deployed to NUC-2

---

## Next Session: Iterative Improvement Mission 🚀

**Status:** Test suite GREEN, `slack-as-me` tools ready
**Mission:** Use challenge scripts to iteratively improve Brain Assistant intelligence
**See:** [NEXT_SESSION_ITERATIVE_IMPROVEMENT.md](NEXT_SESSION_ITERATIVE_IMPROVEMENT.md) for detailed plan

**Key insight:** Brain Assistant has fancy infrastructure (cxdb, BrainIO, Khoj) but doesn't USE it well.
**Target:** llama3.2 models (small context) — must maximize external memory, minimize noise.

See `SESSION_HANDOFF_*.md` for detailed handoff notes from earlier sessions.
