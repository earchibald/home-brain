#!/usr/bin/env python3
"""
Challenge 02: Search should skip low-relevance results.

Setup:
  1. Ask Brain Assistant a very specific question
  2. Brain search may return loosely related results
  3. Only high-relevance results (score >= 0.7) should be injected

Expected: Response uses relevant context OR no context (not irrelevant filler)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    print("Step 1: Asking a specific technical question...")
    response = client.ask(
        "What is the exact ChromaDB collection name used by our semantic search service?",
        timeout=90,
    )
    print(f"  Bot response:\n{response[:500]}")

    # Check that the response doesn't include obvious garbage/irrelevant context
    r_lower = response.lower()

    # If search returned low-score results about unrelated topics, they'd show up
    # as confusing context. A good response either has precise context or no context.
    irrelevant_phrases = [
        "daily log",
        "morning reflection",
        "weekly review",
        "personal development",
    ]
    has_irrelevant = any(p in r_lower for p in irrelevant_phrases)

    if has_irrelevant:
        print("\n❌ FAIL: Response contains irrelevant brain context (low-score results leaked through)")
        return 1
    else:
        print("\n✅ PASS: Response does not contain irrelevant context")
        return 0


if __name__ == "__main__":
    sys.exit(run_challenge())
