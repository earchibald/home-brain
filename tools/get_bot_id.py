#!/usr/bin/env python3
"""Get bot_id for a Slack bot token"""
import sys
from slack_sdk import WebClient

if len(sys.argv) < 2:
    print("Usage: python get_bot_id.py <bot_token>")
    sys.exit(1)

token = sys.argv[1]
client = WebClient(token=token)

# auth.test returns user_id but for bots we need the bot_id
auth_response = client.auth_test()
print(f"user_id: {auth_response['user_id']}")

# Get bot info
bot_response = client.bots_info(bot=auth_response['user_id'])
print(f"bot_id: {bot_response['bot']['id']}")
print(f"bot_name: {bot_response['bot']['name']}")
