# Copilot Agent Instructions for home-brain

## Project Overview

This is a Python Slack bot that integrates with a ChromaDB semantic search service (brain search), Ollama (local LLM inference), and a personal knowledge base. It runs on a distributed NUC cluster.

## Repository Structure

```
agents/           - Main agent implementations (slack_agent.py is the primary bot)
clients/          - Service clients (SemanticSearch, Ollama, BrainIO, ConversationManager)
slack_bot/        - Feature modules (file handling, streaming, performance monitoring)
  tools/          - Tool architecture (BaseTool, registry, executor)
    builtin/      - Built-in tools (web_search, brain_search, facts)
    mcp/          - MCP server config and integration stubs
  mission_manager.py - Hot-reload operator instructions from ~/.brain-mission.md
  tools_ui.py     - Block Kit UI for /tools command
  facts_ui.py     - Block Kit UI for /facts command
config/           - Configuration files (mcp_servers.json)
providers/        - LLM provider adapters (Gemini, etc.)
services/         - Service layer (model_manager, etc.)
tests/            - Pytest test suite
  unit/           - Fast unit tests (no external deps)
  integration/    - Integration tests (mocked externals)
  red/            - TDD red tests for new features
```

## Key Files

- `agents/slack_agent.py` - Main Slack bot (entry point)
- `agent_platform.py` - Base Agent class
- `clients/semantic_search_client.py` - Semantic search API client
- `clients/llm_client.py` - Ollama LLM client
- `clients/conversation_manager.py` - Multi-turn conversation persistence
- `clients/vaultwarden_client.py` - Secrets management
- `providers/gemini_adapter.py` - Gemini provider with quota handling
- `slack_bot/file_handler.py` - File download and text extraction
- `slack_bot/performance_monitor.py` - Latency tracking and alerting
- `slack_bot/tools/base_tool.py` - BaseTool ABC, ToolResult, UserScopedTool
- `slack_bot/tools/tool_registry.py` - ToolRegistry (register/enable/disable/list)
- `slack_bot/tools/tool_executor.py` - Shim XML parsing, timeout guard, tool loop
- `slack_bot/tools/tool_state.py` - ToolStateStore (per-user JSON, 0600 perms)
- `slack_bot/tools/builtin/facts_tool.py` - FactsStore + FactsTool (per-user memory)
- `slack_bot/tools/builtin/web_search_tool.py` - WebSearchTool wrapping WebSearchClient
- `slack_bot/tools/builtin/brain_search_tool.py` - BrainSearchTool wrapping SemanticSearchClient
- `slack_bot/tools/mcp/mcp_config.py` - MCP server config loader (base + local merge)
- `slack_bot/mission_manager.py` - Hot-reload mission principles from ~/.brain-mission.md
- `slack_bot/tools_ui.py` - Block Kit UI for /tools command
- `slack_bot/facts_ui.py` - Block Kit UI for /facts command
- `config/mcp_servers.json` - MCP server definitions (GitHub, filesystem)
- `conftest.py` - Root path setup
- `tests/conftest.py` - All test fixtures

## Testing

### Running Tests
```bash
# Run unit + integration tests (CI suite)
python -m pytest tests/ -m "unit or integration" -v

# Run all tests
python -m pytest tests/ -v
```

### Test Configuration
- `tests/pytest.ini` - Pytest config with markers and coverage settings
- Dependencies: `tests/requirements-test.txt`
- App deps: `slack-bolt slack-sdk aiohttp requests PyPDF2 ddgs`

### Test Markers
- `unit` - Fast tests, no external dependencies
- `integration` - Uses mocks for external services
- `red` - TDD red tests (expected to fail until feature is implemented)
- `remote` - Requires SSH to NUC hardware (skip in CI)
- `requires_secrets` - Needs SOPS secrets (skip in CI)
- `requires_slack` - Needs real Slack tokens (skip in CI)

## Gemini Integration & API Key Management

Brain Assistant supports Google Gemini as an alternative to Ollama for LLM inference.

## Tool Architecture (Phase 1a+1b)

The bot uses a pluggable tool system with two modes:
- **Ollama mode**: Eager injection — tools run before LLM call, results injected into context (zero regression from baseline)
- **Gemini mode**: Full tool loop — native function-calling with up to 5 rounds

### Core Components
- `BaseTool(ABC)` — Common interface with `execute()`, `to_function_spec()`, `to_prompt_description()`
- `UserScopedTool(BaseTool)` — Tools that need per-user state (e.g., FACTS)
- `ToolRegistry` — Register/enable/disable tools, follows `model_manager.py` pattern
- `ToolExecutor` — Parses `<tool_call>` XML shim, 15s timeout guard, MAX_TOOL_ROUNDS=5
- `ToolStateStore` — Per-user enable/disable state in `~/.brain-tool-state.json` (0600)

### Built-in Tools
- `web_search` — DuckDuckGo search via WebSearchClient
- `brain_search` — ChromaDB semantic search via SemanticSearchClient
- `facts` — Per-user persistent memory (store/get/list/delete) via FactsStore

### FACTS System
- Per-user JSON storage: `~/.brain-facts-{user_id}.json` (0600 perms)
- Selective injection: only when message references personal context (pronouns + category keywords)
- Categories: personal, preferences, health, work, family, goals, context, other
- Conflict detection on store (warns about existing facts in same category)

### Mission Principles
- Hot-reload from `~/.brain-mission.md` on NUC-2
- Injected into every system prompt as "## Operator Instructions"
- Editable by operator without restart

### MCP (Model Context Protocol) Config
- Base config: `config/mcp_servers.json` (tracked)
- Local override: `config/mcp_servers.local.json` (gitignored)
- Merge strategy: local overrides base at startup

### Slash Commands
- `/tools` — View/enable/disable tools with Block Kit toggles
- `/facts` — View/add/edit/delete personal facts with overflow menus
- `/mission` — View current mission principles

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

## CRITICAL: Secrets Management — Vaultwarden Only

**ALL secrets and tokens MUST be stored in Vaultwarden exclusively.**

- NO environment variable fallback for secrets — code must fail loudly if Vaultwarden is unreachable
- NO tokens in `.env` files, config files, or hardcoded in source
- NO `os.getenv()` for secrets — always use `VaultwardenClient.get_secret()` or `get_client().get_secret()`
- Vaultwarden URL: `https://vault.nuc-1.local/api`
- Vaultwarden credentials: `ssh nuc-1 cat /home/earchibald/agents/.vaultwarden`

## Coding Conventions

- Python 3.12+
- Async code uses `asyncio` and `pytest-asyncio`
- Slack SDK: `slack-bolt` with `AsyncApp` and Socket Mode
- Configuration is dict-based (passed to `__init__`)
- Error handling: graceful degradation, never crash the bot
- Custom exceptions in `slack_bot/exceptions.py`

## When Fixing Bugs

1. Reproduce the failure with the existing test command
2. Understand the root cause before changing code
3. Fix the underlying issue - do NOT skip, delete, or `xfail` tests
4. Ensure all unit + integration tests pass after your fix
5. Keep changes minimal and focused on the fix

## Deployment to NUC-2: rsync Safety

**CRITICAL:** When deploying to NUC-2 via rsync, NEVER use the `--delete` flag.

**Why:** NUC-2 has pre-existing files that are NOT in the git repository:
- `venv/` - Python virtual environment (created during bootstrap)
- `secrets.env` - Encrypted secrets file (handled separately, not in repo)
- `~/.brain-facts-*.json` - Per-user facts data (generated at runtime)

**Safe deployment command:**
```bash
rsync -avz --exclude venv --exclude secrets.env --exclude ".brain-facts*" \
  /Users/earchibald/LLM/implementation/ nuc-2:/home/earchibald/agents/
```

**What happened when --delete was used:** (Lesson from deployment issues)
- `--delete` synchronized deletion of files not in local repo
- This removed venv/ and secrets.env from NUC-2
- Service failed on restart with exit code 127 (python3 not found)
- Had to manually recreate venv and restore secrets.env

**Post-deploy verification:**
```bash
ssh nuc-2 "ls -la /home/earchibald/agents/venv && \
  test -f /home/earchibald/agents/secrets.env && \
  echo 'Deployment OK' || echo 'MISSING FILES'"
```

## CRITICAL: Agent Notification Protocol

**Before ending active work for any reason**, post a notification to alert that work has concluded:

```bash
curl -d "Copilot: Agent needs attention" https://ntfy.sh/belv-agent-needs-attention
```

**WHEN TO POST NOTIFICATION:**
- ✅ Task completed successfully
- ✅ Task failed with unresolved error
- ✅ Switching focus to different subsystem
- ✅ Work session ending (daily cutoff, break, etc.)
- ✅ Blocking issue discovered (waiting on external input)
- ✅ Handoff to next agent required
- ✅ Any circumstance where active work stops

**WHY THIS IS CRITICAL:**
- Alerts the project owner that work has concluded
- Enables asynchronous, batched work without constant monitoring
- Creates audit trail of work transitions
- Prevents "zombie" work sessions (appearing active but actually idle)

**HOW TO INTEGRATE:**
- Add to end of scripts before exit: `curl -d "Copilot: Agent needs attention" https://ntfy.sh/belv-agent-needs-attention || true`
- Use `|| true` to ensure notification failure doesn't block script completion
- Post notification AFTER committing all changes and updating handoff documents
- Include context in handoff docs so next agent knows why work stopped
