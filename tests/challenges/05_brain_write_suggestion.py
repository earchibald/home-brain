#!/usr/bin/env python3
"""
Challenge 05: Bot should offer to save important information to brain.

Setup:
  1. Send a message with personal info patterns ("I use...", "My strategy...")
  2. Bot should respond AND offer to save the info

Expected: After the LLM response, a "Save to Brain" button appears
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    print("Step 1: Sharing important personal information...")
    # Use ask_raw to get the full message object including blocks
    raw = client.ask_raw(
        "I use a specific workflow for code reviews: first I run the test suite locally, "
        "then I review the diff in VS Code, then I check for security implications, "
        "and finally I leave inline comments on the PR. My approach always includes "
        "running tests before even looking at the code changes.",
        timeout=90,
    )
    response_text = raw.get("text", "")
    print(f"  Bot response: {response_text[:200]}...")

    # Now check if there's a follow-up message with save blocks
    # The save suggestion comes as a separate message after the response
    import time
    time.sleep(3)

    # Poll for the save suggestion message
    channel = client._ensure_dm_channel()
    try:
        result = client._client.conversations_history(
            channel=channel,
            limit=5,
        )
        messages = result.get("messages", [])

        # Look for a message with "Save to Brain" or save-note blocks
        found_save_prompt = False
        for msg in messages:
            text = msg.get("text", "").lower()
            blocks = msg.get("blocks", [])

            if "save" in text and "brain" in text:
                found_save_prompt = True
                break

            for block in blocks:
                elements = block.get("elements", [])
                for el in elements:
                    if el.get("action_id") == "save_note_to_brain":
                        found_save_prompt = True
                        break
    except Exception as e:
        print(f"  Error checking for save prompt: {e}")
        found_save_prompt = False

    if found_save_prompt:
        print("\n✅ PASS: Brain Assistant offered to save information")
        return 0
    else:
        print("\n❌ FAIL: No 'Save to Brain' prompt appeared")
        print("  (Check _should_suggest_save() patterns)")
        return 1


if __name__ == "__main__":
    sys.exit(run_challenge())
