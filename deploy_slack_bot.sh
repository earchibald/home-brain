#!/bin/bash
# Deploy Slack Bot to NUC-2
# 
# This script deploys the Slack bot agent to NUC-2 and sets up the systemd service.
# Run from your local machine: ./deploy_slack_bot.sh

set -e  # Exit on error

echo "=================================================="
echo "  Slack Bot Deployment to NUC-2"
echo "=================================================="
echo ""

NUC="nuc-2"
REMOTE_DIR="/home/earchibald/agents"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "📋 Pre-flight checks..."

# Check if we can reach NUC-2
if ! ssh "$NUC" "echo 'Connected'" &> /dev/null; then
    echo "❌ Cannot connect to $NUC. Check SSH connection."
    exit 1
fi
echo "✅ Connection to $NUC OK"

# Check if required files exist locally
REQUIRED_FILES=(
    "slack_bot.py"
    "agents/slack_agent.py"
    "clients/conversation_manager.py"
    "brain-slack-bot.service"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$LOCAL_DIR/$file" ]]; then
        echo "❌ Missing required file: $file"
        exit 1
    fi
done
echo "✅ All required files present"

echo ""
echo "📦 Step 1: Installing dependencies on NUC-2..."
ssh "$NUC" "cd $REMOTE_DIR && source venv/bin/activate && pip install slack-bolt slack-sdk aiohttp ddgs"

echo ""
echo "📤 Step 2: Copying files to NUC-2..."

# Copy conversation manager
echo "   - conversation_manager.py"
scp "$LOCAL_DIR/clients/conversation_manager.py" "$NUC:$REMOTE_DIR/clients/"

# Copy slack agent
echo "   - slack_agent.py"
scp "$LOCAL_DIR/agents/slack_agent.py" "$NUC:$REMOTE_DIR/agents/"

# Copy launcher
echo "   - slack_bot.py"
scp "$LOCAL_DIR/slack_bot.py" "$NUC:$REMOTE_DIR/"

# Make launcher executable
ssh "$NUC" "chmod +x $REMOTE_DIR/slack_bot.py"

echo ""
echo "🔐 Step 3: Checking secrets configuration..."

# Check if secrets.env exists on NUC-2
if ssh "$NUC" "[[ -f $REMOTE_DIR/secrets.env ]]"; then
    echo "✅ secrets.env exists on NUC-2"
    
    # Check for Slack tokens
    if ssh "$NUC" "grep -q 'SLACK_BOT_TOKEN' $REMOTE_DIR/secrets.env && grep -q 'SLACK_APP_TOKEN' $REMOTE_DIR/secrets.env"; then
        echo "✅ Slack tokens found in secrets.env"
    else
        echo "⚠️  Slack tokens not found in secrets.env"
        echo ""
        echo "You need to add these lines to $NUC:$REMOTE_DIR/secrets.env:"
        echo ""
        echo "  export SLACK_BOT_TOKEN=\"xoxb-your-bot-token\""
        echo "  export SLACK_APP_TOKEN=\"xapp-your-app-token\""
        echo ""
        echo "Get these tokens from: https://api.slack.com/apps"
        echo ""
        read -p "Press Enter once you've added the tokens (or Ctrl+C to abort)..."
    fi
else
    echo "⚠️  secrets.env not found on NUC-2"
    echo ""
    echo "Creating template secrets.env..."
    
    ssh "$NUC" "cat > $REMOTE_DIR/secrets.env" << 'EOF'
# Slack Bot Tokens (get from https://api.slack.com/apps)
export SLACK_BOT_TOKEN="xoxb-your-bot-token-here"
export SLACK_APP_TOKEN="xapp-your-app-token-here"

# System URLs (defaults - adjust if needed)
export SEARCH_URL="http://nuc-1.local:9514"
export OLLAMA_URL="http://m1-mini.local:11434"
export BRAIN_FOLDER="/home/earchibald/brain"
export NTFY_TOPIC="brain-notifications"

# Slack Bot Configuration (optional)
export SLACK_MODEL="llama3.2"
export SLACK_MAX_CONTEXT_TOKENS="6000"
export SLACK_ENABLE_SEARCH="true"
export SLACK_MAX_SEARCH_RESULTS="3"
EOF
    
    echo "✅ Template created at $NUC:$REMOTE_DIR/secrets.env"
    echo ""
    echo "⚠️  You MUST edit secrets.env and add your Slack tokens before continuing!"
    echo ""
    echo "Run this command:"
    echo "  ssh $NUC nano $REMOTE_DIR/secrets.env"
    echo ""
    read -p "Press Enter once you've configured secrets.env (or Ctrl+C to abort)..."
fi

echo ""
echo "🧪 Step 4: Testing configuration..."

echo "   Testing Slack agent import..."
if ssh "$NUC" "cd $REMOTE_DIR && source venv/bin/activate && python3 -c 'from agents.slack_agent import SlackAgent; print(\"OK\")'"; then
    echo "✅ Slack agent imports successfully"
else
    echo "❌ Failed to import Slack agent"
    exit 1
fi

echo ""
echo "🎯 Step 5: Setting up systemd service..."

# Copy service file
echo "   - Copying service file"
scp "$LOCAL_DIR/brain-slack-bot.service" "$NUC:/tmp/"

# Install service
echo "   - Installing service"
ssh "$NUC" "sudo mv /tmp/brain-slack-bot.service /etc/systemd/system/"

# Reload systemd
echo "   - Reloading systemd"
ssh "$NUC" "sudo systemctl daemon-reload"

# Enable service
echo "   - Enabling service"
ssh "$NUC" "sudo systemctl enable brain-slack-bot"

echo "✅ Systemd service installed and enabled"

echo ""
echo "=================================================="
echo "  ✅ Deployment Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the service:"
echo "   ssh $NUC sudo systemctl start brain-slack-bot"
echo ""
echo "2. Check status:"
echo "   ssh $NUC sudo systemctl status brain-slack-bot"
echo ""
echo "3. View logs:"
echo "   ssh $NUC sudo journalctl -u brain-slack-bot -f"
echo ""
echo "4. Test in Slack:"
echo "   - Open Slack workspace"
echo "   - Find your bot in Apps"
echo "   - Send a DM: \"Hello!\""
echo ""
echo "Useful commands:"
echo "  Stop:    ssh $NUC sudo systemctl stop brain-slack-bot"
echo "  Restart: ssh $NUC sudo systemctl restart brain-slack-bot"
echo "  Disable: ssh $NUC sudo systemctl disable brain-slack-bot"
echo ""
