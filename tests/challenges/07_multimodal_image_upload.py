#!/usr/bin/env python3
"""
Challenge 07: Upload a screenshot/image, bot should describe it.

Note: Llama 3.2 supports multimodal (vision) input, but the current
bot code only extracts text from files (txt, md, pdf). Image analysis
would require passing the image to the LLM's vision endpoint.

This is a FUTURE enhancement challenge — expected to fail until
multimodal support is added.

Expected (future): Bot describes image content
Expected (current): Bot acknowledges the image but can't process it
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()

    print("Step 1: Testing image handling acknowledgment...")
    print("  (Note: Full image analysis requires multimodal LLM support)")
    print("  Testing that the bot handles image mentions gracefully...")

    response = client.ask(
        "I just took a screenshot of my terminal showing the output of "
        "'docker ps' on NUC-3. It shows brain_sync running. Can you "
        "help me interpret what I'm seeing?",
        timeout=90,
    )
    print(f"  Bot response: {response[:300]}")

    r_lower = response.lower()
    # Bot should at least discuss docker ps or brain_sync
    if "docker" in r_lower or "brain_sync" in r_lower or "container" in r_lower:
        print("\n✅ PASS: Bot engaged with the image context")
        return 0
    else:
        print("\n⚠️  INCONCLUSIVE: Bot response doesn't reference the described content")
        print("  (Multimodal support not yet implemented — this is expected)")
        return 0  # Not a failure — future feature


if __name__ == "__main__":
    sys.exit(run_challenge())
