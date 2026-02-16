#!/usr/bin/env python3
"""Add Brain Assistant to E2E test channel"""
import sys
sys.path.insert(0, '.')

from clients.vaultwarden_client import get_client
from slack_sdk import WebClient

# Get Brain Assistant's token from Vaultwarden
bot_token = get_client().get_secret('SLACK_BOT_TOKEN')
bot_client = WebClient(token=bot_token)

# Brain Assistant's user ID
brain_bot_id = 'U0AEZ9EJMRB'
test_channel = 'C0AFGEV35PB'

# Check if bot is in the channel
try:
    response = bot_client.conversations_members(channel=test_channel)
    members = response['members']
    
    if brain_bot_id in members:
        print(f'✓ Brain Assistant is already in channel #{test_channel}')
    else:
        print(f'✗ Brain Assistant NOT in channel (has {len(members)} members)')
        print('Inviting bot...')
        inv_response = bot_client.conversations_invite(channel=test_channel, users=brain_bot_id)
        print(f'✓ Bot invited successfully')
except Exception as e:
    print(f'Error: {e}')
