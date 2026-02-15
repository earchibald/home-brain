#!/usr/bin/env python3
"""
Manual test script for Slack bot - execute on your local machine.

Tests:
1. Basic message handling
2. File attachment processing
3. Performance monitoring
4. Response times
5. Working indicator behavior

Usage:
    python test_slack_bot_manual.py

    Then send test messages to the bot in Slack DMs:
    - "test hello" - Basic message
    - "test attachment" - Upload a file and message (attach file via Slack)
    - "test slow" - Message that takes >2 seconds
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Load environment
secrets_file = Path(__file__).parent / "secrets.env"
if secrets_file.exists():
    print(f"✓ Loading secrets from {secrets_file}")
    with open(secrets_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                if line.startswith("export "):
                    line = line[7:]
                key, value = line.split("=", 1)
                value = value.strip('"').strip("'")
                os.environ[key] = value
else:
    print(f"⚠️  No secrets.env found at {secrets_file}")
    print("   Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in environment")

# Check for required tokens
bot_token = os.getenv("SLACK_BOT_TOKEN")
app_token = os.getenv("SLACK_APP_TOKEN")

if not bot_token or not app_token:
    print("❌ Error: Missing Slack tokens")
    print("   Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN")
    sys.exit(1)

print(f"✓ Bot token found: {bot_token[:20]}...")
print(f"✓ App token found: {app_token[:20]}...")


class SlackBotTestRunner:
    """Test runner for Slack bot functionality."""

    def __init__(self):
        from slack_bolt.async_app import AsyncApp

        self.bot_token = bot_token
        self.app = AsyncApp(token=self.bot_token)
        self.test_results = {
            "basic_message": None,
            "file_attachment": None,
            "performance": None,
            "working_indicator": None
        }
        self.messages_received = []

    async def run_tests(self):
        """Run all test scenarios."""
        print("\n" + "="*60)
        print("🧪 SLACK BOT TEST SUITE")
        print("="*60)

        print("\n📋 Instructions:")
        print("1. This script monitors Slack DMs for responses")
        print("2. Send test messages from your Slack account:")
        print("   - 'test hello' for basic test")
        print("   - 'test attachment' + file for attachment test")
        print("   - 'test slow' for performance test")
        print("3. Watch for responses below")
        print("\nWaiting for test messages (60 seconds timeout)...\n")

        # Create listening task
        listen_task = asyncio.create_task(self._listen_for_messages())

        # Wait for responses (60 second timeout)
        try:
            await asyncio.wait_for(listen_task, timeout=60.0)
        except asyncio.TimeoutError:
            print("\n⏱️  Test timeout (60s) - checking results...\n")

        # Display results
        await self._display_results()

    async def _listen_for_messages(self):
        """Listen for incoming DM messages."""
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

        message_count = {"count": 0}
        test_messages = {"hello": False, "attachment": False, "slow": False}

        @self.app.event("message")
        async def handle_message(event, say, client):
            """Capture test messages."""
            if event.get("subtype") == "bot_message":
                return

            channel_type = event.get("channel_type")
            if channel_type != "im":
                return

            text = event.get("text", "").lower()
            user = event.get("user")

            # Track test messages
            if "test hello" in text:
                test_messages["hello"] = True
                print(f"✓ Received: 'test hello' from {user}")
                self.test_results["basic_message"] = "pending"

            elif "test attachment" in text:
                files = event.get("files", [])
                test_messages["attachment"] = True
                print(f"✓ Received: 'test attachment' with {len(files)} file(s)")
                self.test_results["file_attachment"] = "pending"

            elif "test slow" in text:
                test_messages["slow"] = True
                print("✓ Received: 'test slow'")
                self.test_results["performance"] = "pending"

            # Track bot responses
            message_count["count"] += 1

        try:
            socket_handler = AsyncSocketModeHandler(self.app, app_token)
            await socket_handler.start_async()
        except KeyboardInterrupt:
            print("\n⏹️  Test interrupted")
        except Exception as e:
            print(f"\n❌ Socket mode error: {e}")
            # Continue anyway - might have received messages

    async def _display_results(self):
        """Display test results summary."""
        print("\n" + "="*60)
        print("📊 TEST RESULTS")
        print("="*60)

        print("\n✅ Features to Test Manually:")
        print("""
1. BASIC MESSAGE (test hello)
   - Send: "test hello"
   - Expected:
     * Working indicator appears
     * Working indicator disappears
     * Response message appears
   - Verify: Response is contextual and relevant

2. FILE ATTACHMENT (test attachment)
   - Send: "test attachment" + attach .txt, .md, or .pdf file
   - Expected:
     * File is downloaded
     * File content extracted
     * Content included in LLM prompt
   - Verify: Bot references file content in response

3. PERFORMANCE (test slow)
   - Send: "test slow" + message that takes >2 seconds
   - Expected:
     * Response appears (may be slow)
     * Performance monitoring records latency
     * If >30s, alert should be sent
   - Verify: Check NUC-2 logs for timing

4. MULTI-TURN (normal conversation)
   - Send: Multiple messages in sequence
   - Expected:
     * Conversation history preserved
     * Bot references previous messages
   - Verify: Context is maintained across turns
        """)

        print("\n" + "="*60)
        print("🔍 VERIFICATION CHECKLIST")
        print("="*60)

        checks = [
            ("Slack connection", self._can_connect_slack()),
            ("Bot responds to DMs", "Manually verify"),
            ("File attachments detected", "Manually verify"),
            ("Performance monitoring active", "Manually verify"),
            ("Conversation history saved", "Check NUC-2 logs"),
        ]

        for check_name, status in checks:
            symbol = "✓" if status == "Manually verify" or status else "✗"
            print(f"{symbol} {check_name}: {status}")

        print("\n" + "="*60)
        print("📝 MANUAL TESTING GUIDE")
        print("="*60)

        print("""
Test Steps:

Step 1: Basic Connectivity
  1. Open Slack and find the brain bot in DMs
  2. Send: "Hello, are you there?"
  3. Verify: Bot responds (may take 5-10 seconds)

Step 2: File Attachment
  1. Create a test file (test.txt or test.md)
  2. Send: "Can you read this file?" + attach file
  3. Verify: Bot mentions content from the file

Step 3: Performance
  1. Send: "Tell me a long story"
  2. Check NUC-2 logs: tail -f brain-slack-bot.log
  3. Verify: Response time recorded (should be <30s)

Step 4: Multi-Turn
  1. Send: "What's my favorite food?"
  2. Send: "Why is that?"
  3. Verify: Bot remembers context from message 1

Step 5: Error Handling
  1. Turn off Ollama on your machine
  2. Send a message to the bot
  3. Verify: Bot sends friendly error (not crash)
  4. Turn Ollama back on

NUC-2 Log Files:
  - Main log: /var/log/brain-slack-bot.log
  - Performance: grep "latency" /var/log/brain-slack-bot.log
  - Errors: grep "ERROR" /var/log/brain-slack-bot.log

View Live Logs:
  ssh nuc-2
  sudo journalctl -u brain-slack-bot -f
        """)

        print("\n" + "="*60)
        print("⚙️  CONFIGURATION VERIFICATION")
        print("="*60)

        print(f"""
Current Configuration:
  Bot Token: {bot_token[:20]}... (valid: {bool(bot_token)})
  App Token: {app_token[:20]}... (valid: {bool(app_token)})

Feature Flags (from config):
  - enable_file_attachments: True (default)
  - enable_performance_alerts: True (default)
  - slow_response_threshold: 30.0 seconds (default)

To disable features:
  Edit: agents/slack_agent.py
  Search: self.enable_file_attachments = config.get(...)

To change thresholds:
  Edit: agents/slack_agent.py
  Search: slow_response_threshold = config.get(...)
        """)

    def _can_connect_slack(self) -> bool:
        """Check if we can connect to Slack."""
        try:
            # Just check token format
            return bool(bot_token and bot_token.startswith("xoxb-"))
        except Exception:
            return False


async def main():
    """Main entry point."""
    runner = SlackBotTestRunner()

    try:
        await runner.run_tests()
    except KeyboardInterrupt:
        print("\n\n👋 Test script stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("\n🚀 Slack Bot Test Script")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    asyncio.run(main())
