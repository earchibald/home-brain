# E2E Slack Bot Testing - Implementation Summary

## Overview
Implemented end-to-end testing for the Brain Assistant Slack bot from GitHub Actions CI, enabling automated validation of the full stack (Slack → NUC-2 bot → Khoj → Ollama → Slack response).

## Changes Made

### 1. Modified `agents/slack_agent.py` (lines 111-118)
Added support for whitelisting test bot messages while maintaining backward compatibility:

```python
# Ignore bot messages, but allow whitelisted test bots for E2E testing
if event.get("subtype") == "bot_message":
    allowed_bot_ids = os.getenv("ALLOWED_TEST_BOT_IDS", "").split(",")
    bot_id = event.get("bot_id", "")
    # Filter out empty strings from split
    allowed_bot_ids = [b.strip() for b in allowed_bot_ids if b.strip()]
    if bot_id not in allowed_bot_ids or not bot_id:
        return
```

**Behavior:**
- Default: All bot messages ignored (backward compatible)
- With `ALLOWED_TEST_BOT_IDS` set: Only whitelisted bots can message the bot
- Empty/missing bot_id: Always ignored (security)

### 2. Created E2E Test Suite (`tests/e2e/`)

#### `tests/e2e/test_slack_e2e.py` (342 lines)
Three comprehensive E2E tests:

1. **test_bot_responds_to_hello()**
   - Sends "hello" to Brain Assistant
   - Waits up to 60 seconds for response
   - Validates non-empty response

2. **test_bot_responds_to_question()**
   - Sends "What is 2+2?" to Brain Assistant
   - Waits up to 60 seconds for response
   - Validates response contains "4"

3. **test_bot_handles_file_attachment()**
   - Uploads test .txt file to Brain Assistant
   - Waits up to 90 seconds for response (file processing takes longer)
   - Validates response acknowledges the file

**Key Features:**
- `wait_for_response()` helper polls `conversations.history` API
- Tests skip gracefully when tokens not available
- Uses proper Slack SDK WebClient for API calls
- All tests marked with `@pytest.mark.e2e`

#### `tests/e2e/README.md` (183 lines)
Comprehensive documentation including:
- Architecture diagram
- Setup instructions (Slack app creation, GitHub secrets)
- Bot user ID discovery commands
- NUC-2 configuration steps
- Local and CI test execution instructions
- Troubleshooting guide

### 3. Created GitHub Actions Workflow (`.github/workflows/e2e.yml`)

**Triggers:**
- Manual: `workflow_dispatch` with optional Slack notification toggle
- Scheduled: Weekly on Mondays at 12:00 UTC (noon)

**Features:**
- Runs E2E tests with real Slack tokens from GitHub secrets
- Uploads test results as artifacts (30-day retention)
- Posts success/failure notifications to Slack via webhook
- Includes failure details in Slack notification (last 20 lines of output)
- 15-minute timeout to prevent hung workflows

**Required GitHub Secrets:**
- `SLACK_TEST_BOT_TOKEN` - Bot token for E2E Tester app
- `SLACK_BOT_TOKEN` - Bot token for Brain Assistant app
- `BRAIN_BOT_USER_ID` - User ID of Brain Assistant
- `TEST_BOT_USER_ID` - User ID of E2E Tester
- `SLACK_WEBHOOK_URL` - Incoming webhook for notifications

### 4. Created Unit Tests (`tests/unit/test_bot_message_filtering.py`)

Six unit tests validating bot message filtering logic:
1. `test_bot_message_ignored_by_default` - Default behavior
2. `test_whitelisted_bot_message_processed` - Whitelist works
3. `test_non_whitelisted_bot_message_ignored` - Non-whitelisted blocked
4. `test_multiple_whitelisted_bots` - Multiple IDs supported
5. `test_bot_message_without_bot_id_ignored` - Security check
6. `test_regular_user_message_not_affected` - User messages unaffected

All tests pass and use explicit boolean conversion for clarity.

## Test Results

### Unit Tests
✅ All 6 new unit tests pass
```bash
pytest tests/unit/test_bot_message_filtering.py -v
# 6 passed in 0.25s
```

### E2E Tests (without tokens)
✅ Tests skip gracefully
```bash
pytest tests/e2e/ -m e2e -v
# 3 skipped in 0.42s
```

### Security Scan
✅ No CodeQL alerts found
```
Analysis Result for 'actions, python'. Found 0 alerts:
- actions: No alerts found.
- python: No alerts found.
```

## Deployment Checklist

### Prerequisites (User Manual Steps)
- [x] Create "Brain E2E Tester" Slack app with required scopes
- [x] Add GitHub secrets via `gh secret set`
- [x] Get bot user IDs from Slack API

### NUC-2 Configuration
On NUC-2, edit `/etc/systemd/system/brain-slack-bot.service`:

```ini
[Service]
Environment="ALLOWED_TEST_BOT_IDS=B_TEST_BOT_ID_HERE"
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart brain-slack-bot
```

### Manual Test Run
After NUC-2 is configured:
```bash
gh workflow run e2e.yml
```

Check the `#github` Slack channel for success/failure notification.

## Design Decisions

1. **Whitelist-based approach**: More secure than blacklist; explicit control over which bots can message
2. **Backward compatibility**: Default behavior unchanged (all bot messages ignored)
3. **No test cleanup**: Test messages remain in DM for debugging/audit trail
4. **Polling strategy**: 2-second poll interval, 60-90 second timeout (balances responsiveness vs. API rate limits)
5. **File upload test**: Uses real Slack file upload to validate full attachment pipeline
6. **Weekly schedule**: Balances continuous validation with cost/resource usage

## Future Enhancements

Potential improvements for future sessions:
- Add health check step to verify bot is running before sending DMs
- Test multi-turn conversation memory
- Test Khoj brain search integration with specific content
- Add test cleanup option (delete test messages)
- Expand to test streaming responses
- Add performance assertions (response latency)

## Files Changed
- `agents/slack_agent.py` - Bot message filtering logic
- `.github/workflows/e2e.yml` - E2E test workflow
- `tests/e2e/__init__.py` - E2E test package
- `tests/e2e/test_slack_e2e.py` - E2E test suite
- `tests/e2e/README.md` - E2E test documentation
- `tests/unit/test_bot_message_filtering.py` - Unit tests

## Verification Commands

```bash
# Run unit tests
python -m pytest tests/unit/test_bot_message_filtering.py -v

# Run E2E tests (with tokens)
export SLACK_TEST_BOT_TOKEN="xoxb-..."
export SLACK_BOT_TOKEN="xoxb-..."
export BRAIN_BOT_USER_ID="U..."
export TEST_BOT_USER_ID="U..."
python -m pytest tests/e2e/ -m e2e -v

# Verify E2E tests skip without tokens
python -m pytest tests/e2e/ -m e2e -v

# Trigger workflow manually
gh workflow run e2e.yml

# Check workflow status
gh run list --workflow=e2e.yml
```

## Security Summary
✅ No vulnerabilities detected by CodeQL
✅ Whitelist-based security model (explicit allow)
✅ Bot messages without bot_id always ignored
✅ Tests use proper authentication (OAuth tokens)
✅ Secrets managed via GitHub Secrets (not in code)
