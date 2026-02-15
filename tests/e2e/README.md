# E2E Tests for Brain Assistant Slack Bot

This directory contains end-to-end tests that verify the Brain Assistant Slack bot works correctly by sending real messages and validating responses.

## Architecture

```
GitHub Actions CI
    ↓
Slack API (sends DM via Test Bot)
    ↓
Brain Assistant (running on NUC-2)
    ↓ processes via Khoj + Ollama
Slack API (posts response)
    ↓
GitHub Actions (polls conversations_history)
    ↓
Assertions on response content
```

## Prerequisites

### 1. Create "Brain E2E Tester" Slack App

1. Go to https://api.slack.com/apps → Create New App
2. Name: `Brain E2E Tester`
3. Add Bot Token Scopes:
   - `chat:write` - send DMs
   - `im:write` - open DM channels
   - `im:history` - read DM history
   - `users:read` - look up bot user ID
4. Install to workspace
5. Copy the Bot User OAuth Token (xoxb-...)

### 2. Add GitHub Secrets

```bash
gh secret set SLACK_TEST_BOT_TOKEN   # xoxb- token from Brain E2E Tester app
gh secret set SLACK_BOT_TOKEN        # xoxb- token from Brain Assistant app
gh secret set BRAIN_BOT_USER_ID      # Brain Assistant's bot user ID (U...)
gh secret set TEST_BOT_USER_ID       # E2E Tester's bot user ID (U...)
```

### 3. Get Bot User IDs

```bash
# Brain Assistant's user ID
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  https://slack.com/api/auth.test | jq -r '.user_id'

# E2E Tester's user ID  
curl -s -H "Authorization: Bearer $SLACK_TEST_BOT_TOKEN" \
  https://slack.com/api/auth.test | jq -r '.user_id'
```

### 4. Configure NUC-2 to Accept Test Bot

Add the test bot's bot_id to the environment on NUC-2:

```bash
# Get the bot_id from a test message or from Slack API
# Set in /etc/systemd/system/brain-slack-bot.service:
Environment="ALLOWED_TEST_BOT_IDS=B_TEST_BOT_ID_HERE"

# Then reload and restart
sudo systemctl daemon-reload
sudo systemctl restart brain-slack-bot
```

## Running Tests

### Locally (with tokens)

```bash
export SLACK_TEST_BOT_TOKEN="xoxb-..."
export SLACK_BOT_TOKEN="xoxb-..."
export BRAIN_BOT_USER_ID="U..."
export TEST_BOT_USER_ID="U..."

python -m pytest tests/e2e/ -m e2e -v
```

### Locally (without tokens - tests will skip)

```bash
python -m pytest tests/e2e/ -m e2e -v
```

### Via GitHub Actions

#### Manual Trigger

```bash
gh workflow run e2e.yml
```

#### Weekly Schedule

Tests run automatically every Monday at 12:00 UTC.

## Test Cases

### test_bot_responds_to_hello()
- Sends "hello" to Brain Assistant
- Waits up to 60 seconds for response
- Verifies response is non-empty

### test_bot_responds_to_question()
- Sends "What is 2+2?" to Brain Assistant
- Waits up to 60 seconds for response
- Verifies response contains "4"

### test_bot_handles_file_attachment()
- Uploads a test .txt file to Brain Assistant
- Waits up to 90 seconds for response
- Verifies response acknowledges the file

## How wait_for_response() Works

The `wait_for_response()` helper function polls Slack's `conversations.history` API:

1. Calls `conversations.history` with `oldest=message_ts` to get messages after the test message
2. Filters out messages from the test bot itself
3. Looks for messages from Brain Assistant (by user_id or bot_id)
4. Retries every 2 seconds until timeout (default 60s)

## Cleanup Policy

E2E tests **do not** clean up after themselves. Test messages remain in the DM channel for debugging and audit purposes.

## Troubleshooting

### Tests skip with "E2E tests require..." message
- Tokens are not set in environment
- This is expected behavior for local dev

### Tests fail with network errors
- Check that Brain Assistant bot is running on NUC-2
- Verify `ALLOWED_TEST_BOT_IDS` is set correctly
- Check Slack API tokens are valid

### Tests timeout waiting for response
- Bot may be down or slow to respond
- Check NUC-2 systemd logs: `ssh nuc-2 'sudo journalctl -u brain-slack-bot -n 100'`
- Verify Khoj and Ollama are accessible from NUC-2

### "Failed to open DM channel" error
- Test bot doesn't have `im:write` scope
- Reinstall the Slack app with correct scopes
