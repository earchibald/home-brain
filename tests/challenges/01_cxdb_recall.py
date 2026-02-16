#!/usr/bin/env python3
"""
Challenge 01: Brain Assistant should recall past conversations from cxdb.

Setup:
  1. Tell Brain Assistant: "My backup strategy is restic to pCloud"
  2. Wait for response
  3. Start new conversation (different DM, not threaded reply)
  4. Ask: "What's my backup strategy?"

Expected: Brain Assistant retrieves from past conversations and answers "restic to pCloud"
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    # First conversation — establish context
    print("Step 1: Telling Brain Assistant about backup strategy...")
    response1 = client.ask(
        "My backup strategy is restic to pCloud for encrypted offsite backups. "
        "The local repo is on NUC-3.",
        timeout=90,
    )
    print(f"  Bot response: {response1[:200]}...")

    # Wait for cxdb/JSON to flush
    print("Step 2: Waiting 5 seconds for storage sync...")
    time.sleep(5)

    # Second conversation — test recall in a NEW conversation (not thread)
    print("Step 3: Asking in a new conversation...")
    response2 = client.ask(
        "What backup tool do I use for offsite storage?",
        timeout=90,
    )
    print(f"  Bot response: {response2[:300]}")

    # Verify
    r2_lower = response2.lower()
    if "restic" in r2_lower and "pcloud" in r2_lower:
        print("\n✅ PASS: Brain Assistant remembered past conversation (restic + pCloud)")
        return 0
    elif "restic" in r2_lower or "pcloud" in r2_lower:
        print("\n⚠️  PARTIAL: Found one keyword but not both")
        print("  (May need tuning — keyword matching found partial result)")
        return 1
    else:
        print("\n❌ FAIL: Brain Assistant did not retrieve past conversation context")
        return 1


if __name__ == "__main__":
    sys.exit(run_challenge())
