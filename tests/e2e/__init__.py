"""
E2E tests for Brain Assistant Slack bot.

These tests send real messages to the running bot on NUC-2 and verify
responses by polling Slack's conversations.history API.

Requirements:
- SLACK_TEST_BOT_TOKEN: Bot token for "Brain E2E Tester" app
- SLACK_BOT_TOKEN: Bot token for "Brain Assistant" app
- BRAIN_BOT_USER_ID: User ID of Brain Assistant bot
- TEST_BOT_USER_ID: User ID of E2E Tester bot

These tests are marked with @pytest.mark.e2e and skipped when tokens are not set.
"""
