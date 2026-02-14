#!/bin/bash
# Wrapper script to decrypt secrets and start Slack bot

set -e

cd /home/earchibald/agents

# Export age key location
export SOPS_AGE_KEY_FILE=/home/earchibald/.config/sops/age/keys.txt

# Decrypt secrets and export them
eval "$(sops -d secrets.env | grep -v '^#' | grep -v '^$')"

# Run the bot
exec venv/bin/python3 slack_bot.py
