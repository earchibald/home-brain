#!/usr/bin/env python3
"""
slack-as-me: Send Slack DMs as yourself to interact with bots.

CLI wrapper around SlackUserClient for agents, tests, and scripts.
All tokens are loaded from Vaultwarden exclusively.

Usage:
    python -m tools.slack_as_me ask "What's in my brain about backups?"
    python -m tools.slack_as_me ask --json "summarize my notes"
    python -m tools.slack_as_me converse
    echo -e "question 1\\nquestion 2" | python -m tools.slack_as_me converse --json
    python -m tools.slack_as_me --agent-instructions
"""

import argparse
import json
import sys
import time

AGENT_INSTRUCTIONS = """# slack-as-me: Agent Instructions

## What This Tool Does
Sends Slack DMs to Brain Assistant **as the real user** (not as a bot).
The bot sees a genuine human message and responds naturally.
All tokens are loaded from Vaultwarden - no configuration needed.

## Commands

### Single Question
```bash
python -m tools.slack_as_me ask --json "your question here"
```
Returns JSON:
```json
{"response": "bot's answer", "thread_ts": "1234567890.123456", "elapsed_seconds": 8.2}
```

### Multi-Turn Conversation
```bash
echo -e "first question\\nsecond question" | python -m tools.slack_as_me converse --json
```
Returns one JSON object per line (JSONL):
```json
{"turn": 1, "question": "first question", "response": "...", "thread_ts": "...", "elapsed_seconds": 5.1}
{"turn": 2, "question": "second question", "response": "...", "thread_ts": "...", "elapsed_seconds": 7.3}
```

## Exit Codes
- 0: Success
- 1: Bot did not respond within timeout
- 2: Authentication error (token invalid or Vaultwarden unreachable)

## Options
- `--json`: Machine-readable JSON output (default is plain text)
- `--timeout SECONDS`: Override default 60s timeout per response

## Notes
- Brain Assistant typically takes 5-15 seconds to respond
- Multi-turn conversations maintain thread context automatically
- Rate limiting is handled internally (2s poll interval)
"""


def cmd_ask(args, client):
    """Handle the 'ask' command."""
    message = " ".join(args.message)
    start = time.time()

    try:
        if args.json:
            raw = client.ask_raw(message, timeout=args.timeout)
            elapsed = time.time() - start
            output = {
                "response": raw.get("text", ""),
                "thread_ts": raw.get("ts", ""),
                "elapsed_seconds": round(elapsed, 1),
            }
            print(json.dumps(output))
        else:
            response = client.ask(message, timeout=args.timeout)
            print(response)
    except Exception as e:
        return _handle_error(e, args.json)

    return 0


def cmd_converse(args, client):
    """Handle the 'converse' command."""
    convo = client.conversation()
    turn = 0

    if sys.stdin.isatty():
        # Interactive mode
        print("Conversation with Brain Assistant (type /quit to exit)")
        print("-" * 50)
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                break

            if line.strip().lower() in ("/quit", "/exit", "/q"):
                break

            if not line.strip():
                continue

            turn += 1
            start = time.time()

            try:
                if args.json:
                    raw = convo.ask_raw(line, timeout=args.timeout)
                    elapsed = time.time() - start
                    output = {
                        "turn": turn,
                        "question": line,
                        "response": raw.get("text", ""),
                        "thread_ts": raw.get("ts", ""),
                        "elapsed_seconds": round(elapsed, 1),
                    }
                    print(json.dumps(output))
                else:
                    response = convo.ask(line, timeout=args.timeout)
                    print(f"Bot: {response}")
                    print()
            except Exception as e:
                return _handle_error(e, args.json)
    else:
        # Pipe mode - read lines from stdin
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            turn += 1
            start = time.time()

            try:
                if args.json:
                    raw = convo.ask_raw(line, timeout=args.timeout)
                    elapsed = time.time() - start
                    output = {
                        "turn": turn,
                        "question": line,
                        "response": raw.get("text", ""),
                        "thread_ts": raw.get("ts", ""),
                        "elapsed_seconds": round(elapsed, 1),
                    }
                    print(json.dumps(output))
                else:
                    response = convo.ask(line, timeout=args.timeout)
                    print(response)
            except Exception as e:
                return _handle_error(e, args.json)

    convo.close()
    return 0


def _handle_error(e, use_json):
    """Handle errors with appropriate exit codes."""
    from clients.slack_user_client import BotResponseTimeout, SlackAuthError

    if isinstance(e, BotResponseTimeout):
        if use_json:
            print(json.dumps({"error": str(e), "type": "timeout"}))
        else:
            print(f"Timeout: {e}", file=sys.stderr)
        return 1
    elif isinstance(e, SlackAuthError):
        if use_json:
            print(json.dumps({"error": str(e), "type": "auth_error"}))
        else:
            print(f"Auth error: {e}", file=sys.stderr)
        return 2
    else:
        if use_json:
            print(json.dumps({"error": str(e), "type": "error"}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        prog="slack-as-me",
        description="Send Slack DMs as yourself to interact with bots.",
    )
    parser.add_argument(
        "--agent-instructions",
        action="store_true",
        help="Print agent usage instructions and exit.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output in JSON format."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds per response (default: 60).",
    )

    subparsers = parser.add_subparsers(dest="command")

    # ask command
    ask_parser = subparsers.add_parser("ask", help="Send a single message and get response.")
    ask_parser.add_argument("message", nargs="+", help="Message to send.")
    ask_parser.add_argument("--json", action="store_true", dest="json", help="JSON output.")
    ask_parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds.")

    # converse command
    converse_parser = subparsers.add_parser("converse", help="Multi-turn conversation.")
    converse_parser.add_argument("--json", action="store_true", dest="json", help="JSON output.")
    converse_parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds.")

    args = parser.parse_args()

    if args.agent_instructions:
        print(AGENT_INSTRUCTIONS)
        return 0

    if not args.command:
        parser.print_help()
        return 0

    # Import here so --agent-instructions works without Vaultwarden access
    from clients.slack_user_client import SlackUserClient

    try:
        client = SlackUserClient(timeout=args.timeout)
    except Exception as e:
        return _handle_error(e, getattr(args, "json", False))

    if args.command == "ask":
        return cmd_ask(args, client)
    elif args.command == "converse":
        return cmd_converse(args, client)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
