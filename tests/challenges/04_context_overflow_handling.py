#!/usr/bin/env python3
"""
Challenge 04: Long conversations should auto-summarize without context overflow.

Setup:
  1. Start a multi-turn conversation with 8+ exchanges
  2. Each exchange should include substantial content
  3. Verify the bot continues responding coherently after context fills up

Expected: Bot doesn't crash, still responds, and references earlier context
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.slack_user_client import SlackUserClient


def run_challenge():
    client = SlackUserClient()
    convo = client.conversation()

    messages = [
        "Let's discuss my NUC cluster architecture. I have three NUCs: NUC-1 is the orchestrator running semantic search, NUC-2 runs automation and the Slack bot, NUC-3 is storage with Syncthing and backups.",
        "For the inference layer, I use a Mac Mini M1 running Ollama with llama3.2 and nomic-embed-text models. It handles all LLM and embedding requests.",
        "My backup strategy involves three tiers: local Restic backups on NUC-3 external drive, offsite encrypted Restic to pCloud, and browsable rclone sync to pCloud.",
        "The semantic search service uses ChromaDB with nomic-embed-text embeddings. It indexes markdown, PDF, and text files from the brain folder.",
        "Syncthing keeps the brain folder synchronized across all three NUCs. NUC-3 is the introducer node. The folder ID is qknir-pp3n7.",
        "For notifications, I use ntfy.sh with a topic for alerts. All NUCs have a notify.sh script that sends alerts on service failures.",
        "The Slack bot uses slack-bolt with Socket Mode. It connects to semantic search for brain search and Ollama for inference. Conversations are stored in JSON and cxdb.",
        "Now, given everything I've told you about my setup, what would happen if NUC-1 went offline?",
    ]

    print("Running multi-turn conversation test...")
    responses = []

    for i, msg in enumerate(messages, 1):
        print(f"\n--- Turn {i}/{len(messages)} ---")
        print(f"  User: {msg[:80]}...")

        try:
            response = convo.ask(msg, timeout=120)
            responses.append(response)
            print(f"  Bot:  {response[:120]}...")
        except Exception as e:
            print(f"\n❌ FAIL: Bot failed at turn {i}: {e}")
            return 1

    # Verify the final response references earlier context
    final = responses[-1].lower()

    # The bot should mention consequences of NUC-1 going offline
    # based on the architecture described in earlier turns
    keywords = ["search", "semantic", "orchestrat", "chromadb"]
    found = [k for k in keywords if k in final]

    if len(found) >= 2:
        print(f"\n✅ PASS: Bot maintained context across {len(messages)} turns")
        print(f"  Referenced: {', '.join(found)}")
        return 0
    elif len(found) >= 1:
        print(f"\n⚠️  PARTIAL: Bot referenced some earlier context ({', '.join(found)})")
        return 0
    else:
        print(f"\n❌ FAIL: Bot lost context — final response doesn't reference architecture")
        print(f"  Final response: {responses[-1][:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(run_challenge())
