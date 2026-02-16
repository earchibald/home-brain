#!/usr/bin/env python3
"""
Fetch E2E test credentials from Slack API and store in Vaultwarden.

Retrieves:
- BRAIN_BOT_USER_ID via auth.test API (using SLACK_BOT_TOKEN)
- E2E_TEST_CHANNEL_ID via conversations.list API (searches for #e2e-testing or #bot-testing)

Note: SLACK_TEST_BOT_TOKEN cannot be retrieved via API - it's only displayed once
during bot installation. You'll need to:
1. Go to https://api.slack.com/apps
2. Find the "E2E Tester" app (or create a new one)
3. Copy the Bot User OAuth Token from OAuth & Permissions page
4. Run this script with --test-bot-token to add it to Vaultwarden
"""

import argparse
import sys
from typing import Optional

from clients.vaultwarden_client import get_client
from clients.vaultwarden_client import VaultwardenClient
from slack_sdk import WebClient


def get_brain_bot_user_id(slack_token: str) -> str:
    """Get Brain Assistant bot user ID using auth.test API."""
    client = WebClient(token=slack_token)
    response = client.auth_test()
    
    if not response["ok"]:
        raise ValueError(f"auth.test failed: {response.get('error')}")
    
    return response["user_id"]


def find_e2e_test_channel(slack_token: str) -> Optional[str]:
    """Find E2E test channel by name."""
    client = WebClient(token=slack_token)
    
    # Common E2E test channel names
    test_channel_names = [
        "e2e-testing",
        "bot-testing", 
        "brain-testing",
        "automated-tests",
        "e2e-tests"
    ]
    
    # List all channels (including private ones if bot is a member)
    response = client.conversations_list(
        types="public_channel,private_channel",
        exclude_archived=True,
        limit=1000
    )
    
    if not response["ok"]:
        raise ValueError(f"conversations.list failed: {response.get('error')}")
    
    channels = response["channels"]
    
    # Search for test channels
    for channel in channels:
        if channel["name"] in test_channel_names:
            return channel["id"]
    
    # If not found, list available channels
    print("\nNo standard test channel found. Available channels:")
    for channel in channels[:20]:  # Show first 20
        print(f"  #{channel['name']} - {channel['id']}")
    
    return None


def store_credentials(
    vaultwarden: VaultwardenClient,
    brain_bot_user_id: Optional[str] = None,
    e2e_test_channel_id: Optional[str] = None,
    test_bot_token: Optional[str] = None
):
    """Store credentials in Vaultwarden."""
    
    if brain_bot_user_id:
        vaultwarden.set_secret(
            "BRAIN_BOT_USER_ID",
            brain_bot_user_id,
            "Brain Assistant Slack user ID (for E2E tests)"
        )
        print(f"✓ Stored BRAIN_BOT_USER_ID: {brain_bot_user_id}")
    
    if e2e_test_channel_id:
        vaultwarden.set_secret(
            "E2E_TEST_CHANNEL_ID",
            e2e_test_channel_id,
            "E2E test channel ID"
        )
        print(f"✓ Stored E2E_TEST_CHANNEL_ID: {e2e_test_channel_id}")
    
    if test_bot_token:
        vaultwarden.set_secret(
            "SLACK_TEST_BOT_TOKEN",
            test_bot_token,
            "E2E Tester bot OAuth token"
        )
        print(f"✓ Stored SLACK_TEST_BOT_TOKEN: {test_bot_token[:20]}...")


def main():
    parser = argparse.ArgumentParser(description="Fetch E2E credentials from Slack API")
    parser.add_argument(
        "--test-bot-token",
        help="E2E Tester bot token (xoxb-...) to store in Vaultwarden"
    )
    parser.add_argument(
        "--channel-id",
        help="Manually specify E2E test channel ID instead of auto-detecting"
    )
    parser.add_argument(
        "--skip-brain-bot",
        action="store_true",
        help="Skip fetching Brain Bot user ID"
    )
    
    args = parser.parse_args()
    
    # Get Vaultwarden client
    print("Connecting to Vaultwarden...")
    vaultwarden = get_client()
    
    brain_bot_user_id = None
    e2e_test_channel_id = args.channel_id
    
    # Fetch Brain Bot user ID (unless skipped)
    if not args.skip_brain_bot:
        try:
            print("\nFetching Brain Assistant bot user ID...")
            slack_bot_token = vaultwarden.get_secret("SLACK_BOT_TOKEN")
            brain_bot_user_id = get_brain_bot_user_id(slack_bot_token)
            print(f"  Found: {brain_bot_user_id}")
        except Exception as e:
            print(f"  ⚠ Failed: {e}")
    
    # Find E2E test channel (if not manually specified)
    if not e2e_test_channel_id:
        try:
            print("\nSearching for E2E test channel...")
            slack_bot_token = vaultwarden.get_secret("SLACK_BOT_TOKEN")
            e2e_test_channel_id = find_e2e_test_channel(slack_bot_token)
            if e2e_test_channel_id:
                print(f"  Found: {e2e_test_channel_id}")
        except Exception as e:
            print(f"  ⚠ Failed: {e}")
    
    # Store credentials
    print("\nStoring credentials in Vaultwarden...")
    store_credentials(
        vaultwarden,
        brain_bot_user_id=brain_bot_user_id,
        e2e_test_channel_id=e2e_test_channel_id,
        test_bot_token=args.test_bot_token
    )
    
    # Summary
    print("\n" + "="*60)
    print("Summary:")
    print(f"  BRAIN_BOT_USER_ID: {'✓' if brain_bot_user_id else '✗'}")
    print(f"  E2E_TEST_CHANNEL_ID: {'✓' if e2e_test_channel_id else '✗'}")
    print(f"  SLACK_TEST_BOT_TOKEN: {'✓' if args.test_bot_token else '✗'}")
    
    if not args.test_bot_token:
        print("\nTo add SLACK_TEST_BOT_TOKEN:")
        print("  1. Go to https://api.slack.com/apps")
        print("  2. Find 'E2E Tester' app (or create new bot)")
        print("  3. Copy Bot User OAuth Token from OAuth & Permissions")
        print(f"  4. Run: python {__file__} --test-bot-token xoxb-...")
    
    if not e2e_test_channel_id and not args.channel_id:
        print("\nTo manually specify test channel:")
        print(f"  python {__file__} --channel-id C12345...")


if __name__ == "__main__":
    main()
