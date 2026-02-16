#!/usr/bin/env python3
"""
Challenge 08: Multi-turn conversation should maintain context across exchanges.

Setup:
  1. Start a threaded conversation
  2. Establish facts in turns 1-2
  3. Reference those facts in turn 3 without repeating them

Expected: Bot remembers what was said earlier in the same thread
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    print("Starting multi-turn conversation test...")
    convo = client.conversation()

    # Turn 1: Establish fact
    print("\n--- Turn 1: Establish context ---")
    r1 = convo.ask(
        "I'm working on a project called 'Neptune'. It's a Python web service "
        "that processes satellite imagery to detect ocean temperature changes.",
        timeout=90,
    )
    print(f"  Bot: {r1[:150]}...")

    # Turn 2: Add more context
    print("\n--- Turn 2: Add details ---")
    r2 = convo.ask(
        "The Neptune service uses FastAPI for the REST API and rasterio for "
        "GeoTIFF processing. The main bottleneck is the image processing step.",
        timeout=90,
    )
    print(f"  Bot: {r2[:150]}...")

    # Turn 3: Reference earlier context
    print("\n--- Turn 3: Test recall ---")
    r3 = convo.ask(
        "What processing framework did I say I'm using for the images?",
        timeout=90,
    )
    print(f"  Bot: {r3[:200]}")

    # Verify recall
    r3_lower = r3.lower()
    if "rasterio" in r3_lower:
        print("\n✅ PASS: Bot remembered rasterio from earlier in the thread")
        return 0
    elif "geotiff" in r3_lower or "neptune" in r3_lower:
        print("\n⚠️  PARTIAL: Bot remembers project context but not specific library")
        return 0
    else:
        print("\n❌ FAIL: Bot lost context within the same thread")
        return 1


if __name__ == "__main__":
    sys.exit(run_challenge())
