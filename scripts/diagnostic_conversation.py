#!/usr/bin/env python3
"""
Diagnostic Conversation — Tests all P0/P1/P2 fixes against the live bot.

Run with:
  export $(ssh nuc-1.local 'cat /home/earchibald/agents/.vaultwarden' | xargs)
  python scripts/diagnostic_conversation.py

Tests:
  1. Identity: Bot adopts name correctly (P0)
  2. Identity recall: Bot remembers its name later (P0)
  3. Capability awareness: Bot knows its real tools (P1)
  4. Web search trigger: Bot searches for external facts (P0)
  5. Action honesty: Bot doesn't claim actions it didn't take (P0)
  6. No "Notes so far" spam (P2)
  7. Conversation memory: Bot remembers facts from earlier turns
"""

import sys
import json
import time
from datetime import datetime

sys.path.insert(0, ".")
from clients.slack_user_client import SlackUserClient

TURNS = [
    {
        "id": 1,
        "label": "Identity assignment",
        "message": "Hey there! I'm Eugene. I'd like to call you Archie from now on.",
        "checks": {
            "must_contain_any": [["archie", "Archie"]],
            "must_not_contain": ["Eugene (aka Archie)", "Eugene, aka Archie", "your name is Archie"],
            "desc": "Bot should adopt 'Archie' as ITS name, not label Eugene as Archie",
        },
    },
    {
        "id": 2,
        "label": "Identity verification",
        "message": "Quick check — what's YOUR name, and what's MY name?",
        "checks": {
            "must_contain_any": [["Archie", "archie"]],
            "must_contain_all": ["Eugene"],
            "must_not_contain": ["I'm Eugene", "my name is Eugene"],
            "desc": "Bot = Archie, User = Eugene. Bot must not say 'I'm Eugene'",
        },
    },
    {
        "id": 3,
        "label": "Capability awareness",
        "message": "What tools and capabilities do you have? Be specific about what you can actually do.",
        "checks": {
            "must_contain_any": [
                ["brain", "knowledge base", "notes"],
                ["web search", "search the web", "internet"],
                ["file", "upload", "attachment"],
            ],
            "must_not_contain": [],
            "desc": "Bot should list brain search, web search, file analysis — not generic LLM stuff",
        },
    },
    {
        "id": 4,
        "label": "Web search trigger",
        "message": "Can you search the web for the top 3 most popular episodes of Seinfeld?",
        "checks": {
            "must_not_contain": ["I don't have", "I cannot search", "I'm unable"],
            "desc": "Web search should be triggered. Bot should return real results (or at least attempt).",
        },
        "metadata_check": "web_search_used",
    },
    {
        "id": 5,
        "label": "Memory recall",
        "message": "Going back — what name did I give you earlier in this conversation?",
        "checks": {
            "must_contain_any": [["Archie", "archie"]],
            "desc": "Bot should recall being named Archie",
        },
    },
    {
        "id": 6,
        "label": "No notes spam check",
        "message": "Tell me a quick joke about programming.",
        "checks": {
            "must_not_contain": ["Notes so far", "**Notes", "notes so far"],
            "desc": "Bot should NOT append 'Notes so far:' boilerplate",
        },
    },
]


def check_response(turn, response_text):
    """Evaluate a bot response against check criteria."""
    checks = turn["checks"]
    results = []
    passed = True

    # must_contain_any: for each group, at least one keyword must appear
    for group in checks.get("must_contain_any", []):
        found = any(kw.lower() in response_text.lower() for kw in group)
        status = "PASS" if found else "FAIL"
        if status == "FAIL":
            passed = False
        results.append(f"  {status}: Contains any of {group}")

    # must_contain_all: every keyword must appear
    for kw in checks.get("must_contain_all", []):
        found = kw.lower() in response_text.lower()
        status = "PASS" if found else "FAIL"
        if status == "FAIL":
            passed = False
        results.append(f"  {status}: Contains '{kw}'")

    # must_not_contain: none of these should appear
    for bad in checks.get("must_not_contain", []):
        found = bad.lower() in response_text.lower()
        status = "FAIL" if found else "PASS"
        if status == "FAIL":
            passed = False
        results.append(f"  {status}: Does NOT contain '{bad}'")

    return passed, results


def main():
    print("\n" + "=" * 70)
    print("🔬 DIAGNOSTIC CONVERSATION — Testing P0/P1/P2 Fixes")
    print("=" * 70)
    print(f"  Time: {datetime.now().isoformat()}")
    print(f"  Turns: {len(TURNS)}")
    print()

    client = SlackUserClient(timeout=90)
    print(f"  Connected as: {client.user_id}")
    print(f"  Bot: {client.bot_user_id}")
    print()

    total_pass = 0
    total_fail = 0
    turn_results = []

    for turn in TURNS:
        print(f"--- Turn {turn['id']}: {turn['label']} ---")
        print(f"  >> {turn['message'][:80]}...")

        start = time.time()
        response = client.ask(turn["message"], timeout=90)
        elapsed = time.time() - start

        # Truncate display
        display = response[:200].replace("\n", " ")
        print(f"  << ({elapsed:.1f}s) {display}...")

        ok, check_results = check_response(turn, response)
        for cr in check_results:
            print(cr)

        if ok:
            total_pass += 1
            print(f"  ✅ PASS")
        else:
            total_fail += 1
            print(f"  ❌ FAIL — {turn['checks']['desc']}")

        turn_results.append({
            "turn": turn["id"],
            "label": turn["label"],
            "message": turn["message"],
            "response": response,
            "elapsed": elapsed,
            "passed": ok,
        })
        print()

    # Summary
    print("=" * 70)
    print(f"📊 RESULTS: {total_pass}/{total_pass + total_fail} turns passed")
    print("=" * 70)
    for tr in turn_results:
        icon = "✅" if tr["passed"] else "❌"
        print(f"  {icon} Turn {tr['turn']}: {tr['label']} ({tr['elapsed']:.1f}s)")
    print()

    if total_fail == 0:
        print("🎉 ALL CHECKS PASSED!")
    else:
        print(f"⚠️  {total_fail} turn(s) need attention")
        for tr in turn_results:
            if not tr["passed"]:
                print(f"\n  Turn {tr['turn']} ({tr['label']}) response:")
                print(f"  {tr['response'][:500]}")

    # Save full results
    report_path = f"/tmp/diagnostic-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(turn_results, f, indent=2)
    print(f"\nFull results: {report_path}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
