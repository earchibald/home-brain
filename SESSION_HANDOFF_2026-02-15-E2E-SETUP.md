# Session Handoff: E2E Testing Setup & Deployment
**Date**: February 15, 2026
**Context**: PR #6 merged, code ready. Next: Manual setup for E2E testing
**Status**: 🔄 In Progress - Preparing E2E test infrastructure

---

## Executive Summary

PR #6 successfully merged with complete E2E testing infrastructure:
- ✅ Bot message whitelist implementation (agents/slack_agent.py)
- ✅ E2E test suite (tests/e2e/test_slack_e2e.py) + unit tests
- ✅ GitHub Actions workflow (.github/workflows/e2e.yml)
- ✅ All local tests passing (6 unit tests ✅, 3 E2E tests ⏭️ skipped)

**Next Phase**: Execute 6 manual setup steps to enable live E2E testing

---

## Step 1: Create Slack E2E Tester App

This app sends test messages to the Brain Assistant bot. Follow these steps:

1. Go to: https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. **App name**: `Brain E2E Tester`
4. **Select workspace**: Your brain workspace
5. Click **Create App**

### Add Bot Scopes

1. In left sidebar, go to **"OAuth & Permissions"**
2. Under **"Bot Token Scopes"**, click **"Add an OAuth Scope"**
3. Add these scopes:
   - `chat:write` - Send messages
   - `im:write` - Create/open DMs
   - `im:history` - Read DM history
   - `users:read` - Look up user IDs

4. Click **"Install to Workspace"** at the top
5. **Approve** when prompted
6. Copy the **"Bot User OAuth Token"** (starts with `xoxb-`)

Save this token securely - you'll need it for Step 3.

---

## Step 2: Get Bot User IDs

You need two user IDs. Use these commands to retrieve them:

### Get Brain Assistant Bot's User ID

```bash
# Using your existing Brain Assistant bot token
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  https://slack.com/api/auth.test | jq -r '.user_id'

# Will output something like: U1234567890
```

If `$SLACK_BOT_TOKEN` is not set:
```bash
# You can find this in your current NUC-2 deployment
# SSH to NUC-2 and check:
ssh nuc-2 "grep 'xoxb' /home/earchibald/.env 2>/dev/null || echo 'Token not found in env'"
```

### Get E2E Tester Bot's User ID

```bash
# Using the token you copied in Step 1
curl -s -H "Authorization: Bearer xoxb-YOUR-E2E-TESTER-TOKEN-HERE" \
  https://slack.com/api/auth.test | jq -r '.user_id'

# Will output something like: U9876543210
```

**Save both user IDs** - you'll need them for Step 3.

---

## Step 3: Add GitHub Secrets

These secrets enable the CI workflow to authenticate with Slack:

```bash
# From your home-brain repo directory
cd /Users/earchibald/LLM/implementation

# Set the E2E Tester bot token
gh secret set SLACK_TEST_BOT_TOKEN
# Paste: xoxb-... (from Step 1)

# Set the Brain Assistant bot token
gh secret set SLACK_BOT_TOKEN
# Paste: xoxb-... (your existing token)

# Set Brain Assistant bot's user ID
gh secret set BRAIN_BOT_USER_ID
# Paste: U... (from Step 2)

# Set E2E Tester bot's user ID
gh secret set TEST_BOT_USER_ID
# Paste: U... (from Step 2)

# Optional: Set Slack webhook for notifications
gh secret set SLACK_WEBHOOK_URL
# Paste: https://hooks.slack.com/... (or skip if not needed)

# Verify all secrets are set
gh secret list
```

**Output should show:**
```
SLACK_TEST_BOT_TOKEN        Updated 2026-02-15
SLACK_BOT_TOKEN             Updated 2026-02-15
BRAIN_BOT_USER_ID           Updated 2026-02-15
TEST_BOT_USER_ID            Updated 2026-02-15
SLACK_WEBHOOK_URL           Updated 2026-02-15  (optional)
```

---

## Step 4: Configure NUC-2 Systemd Service

The bot needs to know which test bot IDs to accept. Add this to the systemd service file:

### SSH to NUC-2

```bash
ssh nuc-2
```

### Edit the Systemd Service

```bash
sudo nano /etc/systemd/system/brain-slack-bot.service
```

Find the `[Service]` section and add this line (replace `U...` with the E2E Tester bot ID from Step 2):

```ini
[Service]
Type=notify
User=earchibald
WorkingDirectory=/home/earchibald/agents
ExecStart=/home/earchibald/agents/venv/bin/python /home/earchibald/agents/slack_agent.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=brain-slack-bot

# Add this line (replace U123... with your TEST_BOT_USER_ID from Step 2):
Environment="ALLOWED_TEST_BOT_IDS=U123456789ABC"

# Environment for Slack tokens and other config
Environment="SLACK_BOT_TOKEN=xoxb-..."
# ... other existing environments
```

### Reload and Restart Service

```bash
sudo systemctl daemon-reload
sudo systemctl restart brain-slack-bot

# Verify it started correctly
sudo systemctl status brain-slack-bot

# Expected output:
# ● brain-slack-bot.service - Brain Assistant Slack Bot
#   Loaded: loaded (/etc/systemd/system/brain-slack-bot.service; enabled; vendor preset: disabled)
#   Active: active (running) since...
```

### Check Service Logs

```bash
# View recent logs
sudo journalctl -u brain-slack-bot -n 20 -f

# You should see:
# brain-slack-bot[PID]: [timestamp] INFO - SlackAgent: Connected to Slack
```

Exit SSH when done:
```bash
exit
```

---

## Step 5: Trigger First E2E Test Run

Everything is now configured! Trigger the first test:

```bash
cd /Users/earchibald/LLM/implementation

# Trigger the workflow manually
gh workflow run e2e.yml

# Check status
gh run list --workflow=e2e.yml

# Expected output:
# STATUS   TITLE            WORKFLOW       BRANCH  EVENT             ID          CREATED
# completed  E2E Tests      e2e.yml        main    workflow_dispatch  12345678... 2min ago
```

### What the Test Does

1. **Test "hello"**: Sends "hello from e2e test" to Brain Assistant, waits for response
2. **Test "question"**: Sends "What is 2+2?" and verifies response contains "4"
3. **Test "file"**: Uploads a .txt file and verifies acknowledgment

### Expected Behavior

- Each test waits up to 60 seconds for a response
- Tests skip gracefully if offline
- Messages remain in DM for debugging

---

## Step 6: Verify Results & Notifications

### Monitor the Workflow Run

```bash
# Watch the workflow in real-time
gh run watch <run-id>

# Or check via web
gh run view <run-id> --web
```

### Expected Success Output

```
tests/e2e/test_slack_e2e.py::TestSlackBotE2E::test_bot_responds_to_hello PASSED
tests/e2e/test_slack_e2e.py::TestSlackBotE2E::test_bot_responds_to_question PASSED
tests/e2e/test_slack_e2e.py::TestSlackBotE2E::test_bot_handles_file_attachment PASSED

========================= 3 passed in X.XXs =========================
```

### Slack Notifications

If you set `SLACK_WEBHOOK_URL`:
- ✅ **Success**: Slack receives green notification with test link
- 🔴 **Failure**: Slack receives red notification with error details

Check your notification channel (typically #github or configured webhook).

### Check Artifacts

```bash
# Download test results
gh run download <run-id> -D e2e-results

# View test output
cat e2e-results/e2e-test-results/e2e-output.txt
```

---

## Troubleshooting

### "E2E tests require..." message in local run
**Status**: Expected if tokens not exported
```bash
# Export tokens and try again
export SLACK_TEST_BOT_TOKEN="xoxb-..."
export SLACK_BOT_TOKEN="xoxb-..."
export BRAIN_BOT_USER_ID="U..."
export TEST_BOT_USER_ID="U..."
python -m pytest tests/e2e/ -m e2e -v
```

### Tests timeout waiting for response
**Root causes**:
1. Brain Assistant bot not running on NUC-2
2. ALLOWED_TEST_BOT_IDS not set or incorrect
3. Slack tokens invalid
4. Khoj/Ollama not accessible

**Debug**:
```bash
# Check NUC-2 service
ssh nuc-2 "sudo systemctl status brain-slack-bot"

# View logs
ssh nuc-2 "sudo journalctl -u brain-slack-bot -n 50"

# Verify the test bot was added to ALLOWED_TEST_BOT_IDS
ssh nuc-2 "sudo systemctl cat brain-slack-bot.service | grep ALLOWED"
```

### "Failed to open DM channel" error
- Test bot missing `im:write` scope
- Reinstall Slack app with correct scopes (see Step 1)

### Workflow can't reach Slack API
- GitHub Actions firewall may block
- Check `.github/workflows/e2e.yml` for any firewall rules

---

## Next Steps After Successful E2E Test

1. **Verify in Slack**: Check Brain Assistant DM for test messages and responses
2. **Weekly Runs**: Workflow now runs automatically every Monday at noon UTC
3. **Manual Trigger**: Run `gh workflow run e2e.yml` anytime to test
4. **Monitor**: Check Slack notifications for failures

---

## Architecture Reference

```
┌─────────────────────────────────────┐
│  GitHub Actions (E2E Workflow)      │
│  - Manual trigger                   │
│  - Weekly Monday schedule           │
└──────────────┬──────────────────────┘
               │
               │ SLACK_TEST_BOT_TOKEN
               ↓
    ┌──────────────────────┐
    │   Slack API          │
    │ chat.postMessage     │
    │ conversations.history│
    └──────────────┬───────┘
                   │
                   ↓
    ┌─────────────────────────┐
    │  DM: Tester → Assistant │
    │  "hello from e2e test"  │
    └──────────────┬──────────┘
                   │
                   ↓
    ┌────────────────────────────────┐
    │  Brain Assistant (NUC-2)       │
    │  1. Receive message            │
    │  2. Khoj search                │
    │  3. Ollama LLM inference       │
    │  4. Post response              │
    └──────────────┬─────────────────┘
                   │
                   ↓
    ┌─────────────────────────────┐
    │  Response in DM             │
    │  (captured by CI via API)   │
    └──────────────┬──────────────┘
                   │
                   ↓
    ┌──────────────────────────────┐
    │  CI polls conversations.history
    │  Assert response content     │
    │  ✅ PASS or ❌ FAIL          │
    └──────────────┬───────────────┘
                   │
                   ↓
    ┌──────────────────────────────┐
    │  Post Slack notification     │
    │  (success or failure)        │
    └──────────────────────────────┘
```

---

## File Locations Reference

| File | Purpose |
|------|---------|
| `agents/slack_agent.py` | Bot message filtering (line 111-118) |
| `.github/workflows/e2e.yml` | E2E test workflow |
| `tests/e2e/test_slack_e2e.py` | E2E test suite |
| `tests/unit/test_bot_message_filtering.py` | Unit tests for filtering |
| `tests/e2e/README.md` | Full E2E documentation |
| `/etc/systemd/system/brain-slack-bot.service` | NUC-2 service (NUC-2 only) |

---

## Quick Command Reference

```bash
# Get bot user IDs
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" https://slack.com/api/auth.test | jq -r '.user_id'

# Add secrets
gh secret set SLACK_TEST_BOT_TOKEN
gh secret set SLACK_BOT_TOKEN
gh secret set BRAIN_BOT_USER_ID
gh secret set TEST_BOT_USER_ID

# List secrets
gh secret list

# Trigger workflow
gh workflow run e2e.yml

# Check workflow status
gh run list --workflow=e2e.yml

# View NUC-2 service
ssh nuc-2 "sudo systemctl status brain-slack-bot"

# View NUC-2 logs (live)
ssh nuc-2 "sudo journalctl -u brain-slack-bot -f"

# Run E2E tests locally (with tokens)
python -m pytest tests/e2e/ -m e2e -v
```

---

## Success Criteria

✅ **E2E Testing Complete When:**
1. Slack E2E Tester app created with correct scopes
2. Both bot user IDs retrieved
3. All GitHub secrets added
4. NUC-2 service configured with ALLOWED_TEST_BOT_IDS
5. First workflow run completes successfully
6. Slack notifications received and confirmed
7. All 3 E2E tests **PASSED** (not skipped)

---

## Known Limitations

- **Tests are slow** (60-90s timeout) - by design
- **Messages not cleaned up** - kept for audit trail
- **Weekly by default** - manual trigger available for ad-hoc testing
- **No health checks** - relies on message timeout to detect failures

---

## Current Status

- ✅ Code merged and tested locally
- ✅ Unit tests passing (6/6)
- 🔄 Awaiting manual Slack app setup
- 🔄 Awaiting GitHub secrets configuration
- 🔄 Awaiting NUC-2 service configuration

**Next action**: Start with **Step 1: Create Slack E2E Tester App**

