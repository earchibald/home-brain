#!/bin/bash
# Wrapper script to load Vaultwarden credentials and start Slack bot
# CRITICAL: All secrets are fetched from Vaultwarden, NOT from secrets.env

set -e

cd /home/earchibald/agents

# Source Vaultwarden bootstrap credentials
# This file contains VAULTWARDEN_URL, VAULTWARDEN_TOKEN, and optionally
# VAULTWARDEN_CLIENT_ID + VAULTWARDEN_CLIENT_SECRET for auto-refresh
if [[ -f .vaultwarden ]]; then
    export $(grep -v '^#' .vaultwarden | xargs)
else
    echo "❌ .vaultwarden file not found!"
    echo "   Create it with:"
    echo "   VAULTWARDEN_URL=https://vault.nuc-1.local/api"
    echo "   VAULTWARDEN_TOKEN=your-token"
    exit 1
fi

# Run the main slack agent (NOT slack_bot.py which is deprecated)
# slack_agent.py fetches all secrets from Vaultwarden via get_secret()
exec venv/bin/python3 -m agents.slack_agent
