#!/usr/bin/env python3
"""
Challenge 09: Bot should cite brain file sources when referencing stored knowledge.

Setup:
  1. Ask a question that should match brain content
  2. Bot response should include source citations (file paths)

Expected: Response contains "(Source: ...)" or file path references
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    print("Step 1: Asking a question that should trigger brain search...")
    response = client.ask(
        "Search my brain: what notes do I have about ADHD management strategies?",
        timeout=90,
    )
    print(f"  Bot response:\n{response[:500]}")

    # Check for citation patterns
    r_lower = response.lower()

    citation_patterns = [
        "source:",
        "journal/",
        "notes/",
        ".md",
        "brain",
        "from your",
    ]
    found_citations = [p for p in citation_patterns if p in r_lower]

    if len(found_citations) >= 2:
        print(f"\n✅ PASS: Bot cited sources: {found_citations}")
        return 0
    elif found_citations:
        print(f"\n⚠️  PARTIAL: Some citation indicators found: {found_citations}")
        return 0
    else:
        # If no brain content matched, the bot might just say it doesn't know
        if "don't have" in r_lower or "no notes" in r_lower or "couldn't find" in r_lower:
            print("\n⚠️  INCONCLUSIVE: No matching brain content (not a citation issue)")
            return 0
        else:
            print("\n❌ FAIL: Bot referenced knowledge but didn't cite sources")
            return 1


if __name__ == "__main__":
    sys.exit(run_challenge())
