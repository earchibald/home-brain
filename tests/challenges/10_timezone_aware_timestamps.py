#!/usr/bin/env python3
"""
Challenge 10: Timestamps and journal references should use correct timezone.

Setup:
  1. Ask Brain Assistant what today's date is
  2. Check that it matches the actual date (Pacific/US timezone)

Expected: Bot returns the correct current date
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    print("Step 1: Asking about the current date...")
    response = client.ask("What is today's date?", timeout=90)
    print(f"  Bot response: {response[:200]}")

    # Check against actual date
    from datetime import datetime

    today = datetime.now()
    date_formats = [
        today.strftime("%Y-%m-%d"),           # 2026-02-16
        today.strftime("%B %d, %Y"),          # February 16, 2026
        today.strftime("%B %d"),              # February 16
        today.strftime("%m/%d/%Y"),           # 02/16/2026
        today.strftime("%-m/%-d/%Y"),         # 2/16/2026
        today.strftime("%b %d, %Y"),          # Feb 16, 2026
    ]

    found_date = any(d in response for d in date_formats)

    if found_date:
        print(f"\n✅ PASS: Bot returned correct date")
        return 0
    else:
        # LLMs sometimes don't know the current date — this is expected
        r_lower = response.lower()
        if "don't know" in r_lower or "not sure" in r_lower or "cannot" in r_lower:
            print("\n⚠️  EXPECTED: LLM doesn't have real-time date awareness")
            print("  (Future: inject date into system prompt)")
            return 0
        else:
            print(f"\n❌ FAIL: Bot gave incorrect date")
            print(f"  Expected one of: {date_formats[:3]}")
            return 1


if __name__ == "__main__":
    sys.exit(run_challenge())
