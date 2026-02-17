#!/usr/bin/env python3
"""
DEPRECATED: This file is maintained for backwards compatibility only.

Use agents/slack_agent.py directly instead:
    python -m agents.slack_agent

Or via start_slack_bot.sh:
    ./start_slack_bot.sh

All secrets are now fetched from Vaultwarden, NOT secrets.env.
The start script sources .vaultwarden for bootstrap credentials only.
"""

import sys
import warnings

warnings.warn(
    "slack_bot.py is DEPRECATED. Use 'python -m agents.slack_agent' instead. "
    "All secrets should be in Vaultwarden, not secrets.env.",
    DeprecationWarning,
    stacklevel=2
)

print("=" * 60)
print("  ⚠️  DEPRECATED: Use agents/slack_agent.py instead!")
print("=" * 60)
print()
print("This launcher is deprecated. The correct approach is:")
print()
print("  1. Source Vaultwarden credentials:")
print("     export \\$(grep -v '^#' .vaultwarden | xargs)")
print()
print("  2. Run the main agent:")
print("     python -m agents.slack_agent")
print()
print("Or use the wrapper script:")
print("     ./start_slack_bot.sh")
print()
print("Redirecting to agents.slack_agent...")
print()

# Forward to the correct entry point
from agents.slack_agent import main
main()

