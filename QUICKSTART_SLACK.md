# Slack Bot Quickstart Guide

Get your semantic brain connected to Slack in 30 minutes.

## What You'll Build

A Slack bot that:
- **Responds to Slack DMs** using llama3.2 
- **Searches your brain** for relevant context before answering
- **Remembers conversations** with automatic history management
- **Isolates users** - each person gets their own brain folder
- **Runs 24/7** as a systemd service on NUC-2

## Prerequisites

- ✅ NUC-2 agent platform deployed ([NUC2_AGENT_FRAMEWORK.md](NUC2_AGENT_FRAMEWORK.md))
- ✅ Khoj running on NUC-1 (192.168.1.195:42110)
- ✅ Ollama running on Mac Mini (192.168.1.58:11434)
- ✅ Slack workspace where you can create apps
- ✅ SSH access to NUC-2

## Step 1: Create Slack App (10 min)

### 1.1 Create New App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Name: `Brain Assistant` (or whatever you like)
5. Select your workspace
6. Click **"Create App"**

### 1.2 Enable Socket Mode

1. In left sidebar → **Socket Mode**
2. Toggle **"Enable Socket Mode"** to ON
3. Name the token: `brain-socket-token`
4. Click **"Generate"**
5. **SAVE THIS TOKEN** → starts with `xapp-`
   ```
   SLACK_APP_TOKEN=xapp-1-A07...
   ```

### 1.3 Add Bot Token Scopes

1. In left sidebar → **OAuth & Permissions**
2. Scroll down to **"Bot Token Scopes"**
3. Click **"Add an OAuth Scope"** and add these:
   - `app_mentions:read` - See when bot is @mentioned
   - `chat:write` - Send messages
   - `chat:write.customize` - Customize bot name/icon per message (optional)
   - `im:history` - Read DM history
   - `im:read` - Read DM info
   - `im:write` - Send DMs

### 1.4 Install App to Workspace

1. Scroll to top of **OAuth & Permissions** page
2. Click **"Install to Workspace"**
3. Review permissions → Click **"Allow"**
4. **SAVE THE BOT TOKEN** → starts with `xoxb-`
   ```
   SLACK_BOT_TOKEN=xoxb-1234...
   ```

### 1.5 Enable Events (for Socket Mode)

1. In left sidebar → **Event Subscriptions**
2. Toggle **"Enable Events"** to ON
3. Under **"Subscribe to bot events"** add:
   - `app_mention` - When someone @mentions bot
   - `message.im` - When user sends DM

4. Click **"Save Changes"**

### 1.6 Get Your User ID (for testing)

1. Open Slack workspace
2. Click your profile picture → **Profile**
3. Click **"More"** (three dots) → **"Copy member ID"**
4. Save this for testing: `U01ABC123...`

**✅ You're done in Slack!** You now have:
- `SLACK_APP_TOKEN` (xapp-...)
- `SLACK_BOT_TOKEN` (xoxb-...)

## Step 2: Configure Secrets (5 min)

### 2.1 Add Tokens to secrets.env

On your local machine, edit `secrets.env`:

```bash
nano secrets.env
```

Add these lines (replace with your actual tokens):

```bash
# Slack Bot Tokens
export SLACK_BOT_TOKEN="xoxb-1234-5678-abcdefghijklmnop"
export SLACK_APP_TOKEN="xapp-1-A07-123456-abcdef123456"

# System URLs (already configured, verify these are correct)
export KHOJ_URL="http://192.168.1.195:42110"
export OLLAMA_URL="http://192.168.1.58:11434"
export BRAIN_FOLDER="/home/earchibald/brain"
export NTFY_TOPIC="brain-notifications"
```

**Security:** This file should be encrypted with SOPS if you commit it to git.

## Step 3: Deploy to NUC-2 (10 min)

### 3.1 Run Deployment Script

From your local machine (in this directory):

```bash
./deploy_slack_bot.sh
```

This script will:
- ✅ Install `slack-bolt` and `slack-sdk` on NUC-2
- ✅ Copy all Slack bot files to NUC-2
- ✅ Setup secrets.env (or verify it exists)
- ✅ Install systemd service
- ✅ Enable auto-start on boot

### 3.2 Manual Deployment (if script fails)

If the script doesn't work, do it manually:

```bash
# 1. Copy files
scp clients/conversation_manager.py nuc-2:/home/earchibald/agents/clients/
scp agents/slack_agent.py nuc-2:/home/earchibald/agents/agents/
scp slack_bot.py nuc-2:/home/earchibald/agents/
scp secrets.env nuc-2:/home/earchibald/agents/

# 2. Install dependencies
ssh nuc-2 "cd /home/earchibald/agents && source venv/bin/activate && pip install slack-bolt slack-sdk aiohttp"

# 3. Test import
ssh nuc-2 "cd /home/earchibald/agents && source venv/bin/activate && python3 -c 'from agents.slack_agent import SlackAgent; print(\"OK\")'"

# 4. Install systemd service
scp brain-slack-bot.service nuc-2:/tmp/
ssh nuc-2 "sudo mv /tmp/brain-slack-bot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable brain-slack-bot"
```

## Step 4: Start the Bot (2 min)

### 4.1 Start Service

```bash
ssh nuc-2 sudo systemctl start brain-slack-bot
```

### 4.2 Check Status

```bash
ssh nuc-2 sudo systemctl status brain-slack-bot
```

You should see:
```
● brain-slack-bot.service - Brain Slack Bot
   Loaded: loaded
   Active: active (running)
```

### 4.3 Monitor Logs

```bash
ssh nuc-2 sudo journalctl -u brain-slack-bot -f
```

Look for:
```
✅ Khoj connection OK
✅ Ollama connection OK
✅ Brain folder OK
✅ Slack auth OK
✅ Slack agent connected and ready
```

Press `Ctrl+C` to exit logs.

## Step 5: Test in Slack (5 min)

### 5.1 Find Your Bot

1. Open Slack workspace
2. In sidebar, click **"Apps"**
3. Find **"Brain Assistant"** (or whatever you named it)
4. Click to open DM

### 5.2 Send Hello World

Type in the DM:
```
Hello!
```

**Expected behavior:**
- Bot shows typing indicator
- After 5-15 seconds, bot responds with AI-generated message
- Response is personalized and conversational

### 5.3 Test Multi-Turn Conversation

```
You: What's your name?
Bot: [introduces itself]

You: What did I just ask you?
Bot: [references previous question about name]
```

✅ **If bot references previous messages, multi-turn is working!**

### 5.4 Test Context Search

If you have content in your brain, try:
```
What do you know about [topic in your brain]?
```

Bot should search Khoj and reference specific files.

## Step 6: Verify User Isolation (3 min)

### 6.1 Check Conversation Files

```bash
ssh nuc-2 ls -la /home/earchibald/brain/users/
```

You should see a folder named with your Slack user ID (e.g., `U01ABC123/`).

### 6.2 View Conversation

```bash
ssh nuc-2 cat /home/earchibald/brain/users/U01ABC123/conversations/*.json
```

You should see JSON with your messages and bot responses.

### 6.3 Test Second User (optional)

Have another person in your workspace DM the bot. Their conversations should be stored in a separate folder.

## Troubleshooting

### Bot Doesn't Respond

**Check service status:**
```bash
ssh nuc-2 sudo systemctl status brain-slack-bot
```

**Check logs:**
```bash
ssh nuc-2 sudo journalctl -u brain-slack-bot -n 50
```

**Common issues:**
- **Token error:** Check `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in secrets.env
- **"Ollama unavailable":** Check Mac Mini is running: `curl http://192.168.1.58:11434`
- **"Khoj unavailable":** Check NUC-1 is running: `curl http://192.168.1.195:42110`

### Slow Responses (>30 seconds)

**Check Ollama:**
```bash
curl -X POST http://192.168.1.58:11434/api/generate -d '{
  "model": "llama3.2",
  "prompt": "Hello",
  "stream": false
}'
```

If slow or fails → restart Ollama on Mac Mini.

### Connection Refused

**Check Socket Mode:**
1. Go to https://api.slack.com/apps → Your App
2. Socket Mode → Verify it's ON
3. Check token hasn't been revoked

**Check service is running:**
```bash
ssh nuc-2 sudo systemctl restart brain-slack-bot
```

### Import Errors

**Reinstall dependencies:**
```bash
ssh nuc-2 "cd /home/earchibald/agents && source venv/bin/activate && pip install --upgrade slack-bolt slack-sdk aiohttp"
```

## Useful Commands

### Service Management

```bash
# Start
ssh nuc-2 sudo systemctl start brain-slack-bot

# Stop
ssh nuc-2 sudo systemctl stop brain-slack-bot

# Restart
ssh nuc-2 sudo systemctl restart brain-slack-bot

# Status
ssh nuc-2 sudo systemctl status brain-slack-bot

# Logs (live)
ssh nuc-2 sudo journalctl -u brain-slack-bot -f

# Logs (last 100 lines)
ssh nuc-2 sudo journalctl -u brain-slack-bot -n 100
```

### Conversation Management

```bash
# List all users
ssh nuc-2 ls /home/earchibald/brain/users/

# List conversations for a user
ssh nuc-2 ls /home/earchibald/brain/users/U01ABC123/conversations/

# View conversation
ssh nuc-2 cat /home/earchibald/brain/users/U01ABC123/conversations/1234567890.123456.json

# Delete conversation (if needed)
ssh nuc-2 rm /home/earchibald/brain/users/U01ABC123/conversations/1234567890.123456.json
```

### Testing Without Slack

Run bot locally (for debugging):

```bash
ssh nuc-2
cd /home/earchibald/agents
source venv/bin/activate
python3 slack_bot.py
```

Press `Ctrl+C` to stop. Logs appear in terminal.

## Configuration Options

Edit `secrets.env` on NUC-2 to customize:

```bash
# LLM model to use (default: llama3.2)
export SLACK_MODEL="llama3.2"

# Max tokens for conversation history (default: 6000)
export SLACK_MAX_CONTEXT_TOKENS="6000"

# Enable Khoj context search (default: true)
export SLACK_ENABLE_SEARCH="true"

# Max search results to include (default: 3)
export SLACK_MAX_SEARCH_RESULTS="3"
```

After changing, restart service:
```bash
ssh nuc-2 sudo systemctl restart brain-slack-bot
```

## Next Steps

### For Production Use

1. **Add more users** - Invite team to workspace, bot handles each separately
2. **Monitor usage** - Check logs daily for errors or performance issues
3. **Tune prompts** - Edit system prompt in [slack_agent.py](agents/slack_agent.py)
4. **Add commands** - Implement slash commands for common queries

### Enhancement Ideas

From [SLACK_DESIGN.md](SLACK_DESIGN.md):

- **Slash commands:** `/brain search <query>`, `/brain summarize today`
- **Thread support:** Respond when @mentioned in channels
- **File uploads:** Accept PDFs → ingest into brain
- **Proactive messages:** Bot DMs you with daily journal prompts
- **Voice notes:** Transcribe audio messages
- **Task management:** Create TODOs from conversations

### Debugging Tips

**Enable verbose logging:**

Edit [slack_agent.py](agents/slack_agent.py), change log level:

```python
logging.basicConfig(level=logging.DEBUG)  # Was: INFO
```

Restart service to apply.

**Test individual components:**

```bash
# Test conversation manager
ssh nuc-2 "cd /home/earchibald/agents && source venv/bin/activate && python3 clients/conversation_manager.py"

# Test Khoj client
ssh nuc-2 "cd /home/earchibald/agents && source venv/bin/activate && python3 -c 'import asyncio; from clients.khoj_client import KhojClient; asyncio.run(KhojClient().health_check())'"

# Test LLM client
ssh nuc-2 "cd /home/earchibald/agents && source venv/bin/activate && python3 -c 'import asyncio; from clients.llm_client import LLMClient; asyncio.run(LLMClient().complete(\"Hello\"))'"
```

## Support

If you run into issues:

1. **Check logs first:** `ssh nuc-2 sudo journalctl -u brain-slack-bot -n 100`
2. **Verify health:** All services (Khoj, Ollama, brain folder) accessible
3. **Test tokens:** Use Slack API tester at api.slack.com
4. **Review design:** See [SLACK_DESIGN.md](SLACK_DESIGN.md) for architecture details

---

**🎉 You're all set!** Your semantic brain is now accessible via Slack DMs. Start chatting!
