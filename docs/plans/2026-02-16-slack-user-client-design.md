# Slack User Client & App Manifest Manager

**Date:** 2026-02-16
**Status:** Approved

## Goals

1. **Realistic E2E testing** — Automated tests that exercise Brain Assistant exactly as a real user would, no bot-message filtering bypasses or whitelist hacks.
2. **Agent-to-agent orchestration** — Other agents (Claude Code, automation scripts) can use Brain Assistant as a tool by sending DMs on the user's behalf.
3. **Programmatic Slack app configuration** — Full lifecycle management of Slack apps via manifests (infrastructure-as-code).

## Architecture

```
Agent / Test
    │
    ▼
SlackUserClient (xoxp- user token from Vaultwarden)
    │
    ├─► Slack API: chat.postMessage (send DM as user)
    │
    └─► Slack API: conversations.history (poll for bot reply, 2s interval)
              │
              ▼
       Brain Assistant sees a real human DM
       Responds normally via its bot token
```

Brain Assistant's code does not change. It already handles real user DMs — we're sending them programmatically instead of typing them.

## Components

### 1. SlackUserClient (Python module)

**File:** `clients/slack_user_client.py`

- Token retrieval from Vaultwarden ONLY (no env var fallback)
- `ask(message)` — single request/response
- `conversation()` — multi-turn context manager with thread support
- Polling at 2s intervals, configurable timeout (default 60s)
- Custom exceptions: `BotResponseTimeout`, `SlackAuthError`

### 2. CLI Wrapper

**File:** `tools/slack_as_me.py`

- Commands: `ask`, `converse`
- `--json` flag for machine-readable output
- `--agent-instructions` flag for self-documenting agent usage
- `--timeout` override
- Exit codes: 0 success, 1 timeout, 2 auth error

### 3. Slack Manifest Manager

**File:** `tools/slack_app_manager.py`

- Commands: `export`, `create`, `update`, `diff`
- Manifest files in `manifests/` directory
- Config token refresh via Vaultwarden

### 4. E2E Test Migration

**File:** `tests/e2e/test_brain_as_user.py`

- Replaces old bot-to-bot `test_slack_e2e.py`
- Uses `SlackUserClient` fixtures
- Covers: basic response, multi-turn context, file attachment

## Security

- ALL tokens stored in Vaultwarden exclusively
- No environment variable fallback for any secret
- No tokens in code, config files, or env vars

## Slack App Setup

User token app ("Brain User Client") scopes:
- `chat:write` — send messages as user
- `im:history` — read DM history for polling
- `im:read` — view DM channel metadata

## Implementation Phases

1. SlackUserClient Python module + unit tests
2. CLI wrapper with --agent-instructions
3. E2E test migration
4. Manifest Manager
5. Guardrails & docs (CLAUDE.md, copilot-instructions.md, fix get_secret)
