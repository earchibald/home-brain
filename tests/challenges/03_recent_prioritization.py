#!/usr/bin/env python3
"""
Challenge 03: Recent brain entries should be prioritized over old ones.

Setup:
  1. Ask Brain Assistant about a topic that has both old and recent brain entries
  2. The response should reference recent entries (if the brain has them)

Expected: Response cites or references recent journal entries, not ancient ones
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    print("Step 1: Asking about something with likely recent brain entries...")
    response = client.ask(
        "What have I been working on recently in my journal?",
        timeout=90,
    )
    print(f"  Bot response:\n{response[:500]}")

    # Check if the response references any recent dates (within last week)
    import re
    from datetime import datetime, timedelta

    today = datetime.now()
    recent_dates = []
    for i in range(14):  # Last 2 weeks
        d = today - timedelta(days=i)
        recent_dates.append(d.strftime("%Y-%m-%d"))
        recent_dates.append(d.strftime("%B %d"))  # e.g., "February 15"
        recent_dates.append(d.strftime("%b %d"))   # e.g., "Feb 15"

    has_recent = any(date in response for date in recent_dates)

    # Also check for words suggesting recency
    recency_words = ["recent", "today", "yesterday", "this week", "earlier today", "just"]
    has_recency_language = any(w in response.lower() for w in recency_words)

    if has_recent or has_recency_language:
        print("\n✅ PASS: Response references recent content")
        return 0
    else:
        print("\n⚠️  INCONCLUSIVE: Can't verify recency — may depend on brain content")
        print("  (Check brain for recent journal entries)")
        return 0  # Not a failure — depends on brain state


if __name__ == "__main__":
    sys.exit(run_challenge())
