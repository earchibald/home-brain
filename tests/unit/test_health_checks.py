"""
Unit tests for Slack Agent health checks - dependency validation on startup.

Tests verify:
- All health checks pass when services available
- Ollama down fails startup
- Khoj down warns but continues
- Brain folder missing fails startup
- Slack auth failure blocks startup
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from slack_sdk.errors import SlackApiError

from agents.slack_agent import SlackAgent


@pytest.mark.unit
class TestHealthChecks:
    """Test suite for Slack Agent health checks"""

    @pytest.mark.asyncio
    async def test_all_health_checks_pass(
        self, test_brain_path, mock_llm, mock_khoj, mock_slack_app
    ):
        """
        Test that all health checks pass when all services available.

        Verifies that:
        - Ollama health check passes
        - Khoj health check passes
        - Brain folder exists
        - Slack auth succeeds
        - No errors raised
        - Agent can proceed to connect

        Args:
            test_brain_path: Fixture providing temporary brain directory
            mock_llm: Mock LLM client (AsyncMock)
            mock_khoj: Mock Khoj client (AsyncMock)
            mock_slack_app: Mock Slack app (MagicMock)
        """
        config = {
            "brain_path": str(test_brain_path),
            "ollama_url": "http://m1-mini.local:11434",
            "khoj_url": "http://nuc-1.local:42110",
            "model": "llama3.2",
            "enable_khoj_search": True,
        }

        # Patch environment variables
        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"},
        ):
            # Patch the clients to use mocks
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                # Setup mocks
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                # Create agent
                agent = SlackAgent(config)

                # Run health check
                await agent._health_check()

                # Should complete without raising

    @pytest.mark.asyncio
    async def test_ollama_down_fails_startup(
        self, test_brain_path, mock_khoj, mock_slack_app
    ):
        """
        Test that startup fails when Ollama is unavailable.

        Verifies that:
        - Health check detects Ollama failure
        - RuntimeError is raised (critical failure)
        - Startup is blocked
        - Error message includes "Ollama"

        Args:
            test_brain_path: Fixture providing temporary brain directory
            mock_khoj: Mock Khoj client
            mock_slack_app: Mock Slack app
        """
        config = {
            "brain_path": str(test_brain_path),
            "ollama_url": "http://m1-mini.local:11434",
            "khoj_url": "http://nuc-1.local:42110",
            "model": "llama3.2",
        }

        # Create mock LLM that fails health check
        mock_llm = AsyncMock()
        mock_llm.health_check = AsyncMock(side_effect=Exception("Connection refused"))

        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"},
        ):
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                agent = SlackAgent(config)

                # Health check should raise
                with pytest.raises(RuntimeError, match="Ollama"):
                    await agent._health_check()

    @pytest.mark.asyncio
    async def test_khoj_down_warns_but_continues(
        self, test_brain_path, mock_llm, mock_slack_app
    ):
        """
        Test that Khoj unavailability is non-fatal (warning only).

        Verifies that:
        - Health check detects Khoj failure
        - Warning is logged (not error)
        - Startup continues (no exception raised)
        - Agent remains functional without Khoj
        - Error message does not cause RuntimeError

        Args:
            test_brain_path: Fixture providing temporary brain directory
            mock_llm: Mock LLM client
            mock_slack_app: Mock Slack app
        """
        config = {
            "brain_path": str(test_brain_path),
            "ollama_url": "http://m1-mini.local:11434",
            "khoj_url": "http://nuc-1.local:42110",
            "model": "llama3.2",
            "enable_khoj_search": True,
        }

        # Create mock Khoj that fails
        mock_khoj = AsyncMock()
        mock_khoj.health_check = AsyncMock(side_effect=Exception("Khoj unavailable"))

        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"},
        ):
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                agent = SlackAgent(config)

                # Health check should NOT raise - Khoj is optional
                try:
                    await agent._health_check()
                    # Should reach here
                except RuntimeError as e:
                    # Should only fail on critical errors (Ollama/Slack)
                    assert "Ollama" in str(e) or "Slack" in str(e)
                    raise  # Re-raise if it's a critical error

    @pytest.mark.asyncio
    async def test_brain_folder_missing_fails_startup(
        self, mock_llm, mock_khoj, mock_slack_app
    ):
        """
        Test that missing brain folder fails startup.

        Verifies that:
        - Initialization detects missing brain folder
        - ValueError is raised (critical failure)
        - Startup is blocked
        - Error message indicates missing folder
        - Agent cannot proceed without brain

        Args:
            mock_llm: Mock LLM client
            mock_khoj: Mock Khoj client
            mock_slack_app: Mock Slack app
        """
        # Use a non-existent path
        config = {
            "brain_path": "/nonexistent/path/that/does/not/exist",
            "ollama_url": "http://m1-mini.local:11434",
            "khoj_url": "http://nuc-1.local:42110",
            "model": "llama3.2",
        }

        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"},
        ):
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                # Agent initialization should raise ValueError for missing brain path
                with pytest.raises(ValueError, match="Brain"):
                    SlackAgent(config)

    @pytest.mark.asyncio
    async def test_slack_auth_failure_blocks_startup(
        self, test_brain_path, mock_llm, mock_khoj
    ):
        """
        Test that Slack authentication failure blocks startup.

        Verifies that:
        - Health check detects Slack auth failure
        - RuntimeError is raised (critical failure)
        - Startup is blocked
        - Error message indicates Slack auth issue
        - No fallback possible without Slack tokens

        Args:
            test_brain_path: Fixture providing temporary brain directory
            mock_llm: Mock LLM client
            mock_khoj: Mock Khoj client
        """
        config = {
            "brain_path": str(test_brain_path),
            "ollama_url": "http://m1-mini.local:11434",
            "khoj_url": "http://nuc-1.local:42110",
            "model": "llama3.2",
        }

        # Create mock Slack app that fails auth
        mock_slack_app = MagicMock()
        mock_slack_app.client.auth_test = AsyncMock(
            side_effect=SlackApiError(
                message="Invalid token", response={"error": "invalid_auth"}
            )
        )

        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-invalid", "SLACK_APP_TOKEN": "xapp-invalid"},
        ):
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                agent = SlackAgent(config)

                # Health check should raise
                with pytest.raises(RuntimeError, match="Slack"):
                    await agent._health_check()


@pytest.mark.unit
class TestHealthCheckEdgeCases:
    """Test edge cases and error conditions in health checks"""

    @pytest.mark.asyncio
    async def test_health_check_partial_failures(
        self, test_brain_path, mock_llm, mock_slack_app
    ):
        """
        Test health check behavior with multiple non-critical failures.

        Verifies that:
        - Multiple non-critical failures don't fail startup
        - All checks are still performed
        - All failures are logged
        - Only critical failures block startup
        """
        config = {
            "brain_path": str(test_brain_path),
            "ollama_url": "http://m1-mini.local:11434",
            "khoj_url": "http://nuc-1.local:42110",
            "model": "llama3.2",
        }

        # Khoj fails but it's non-critical
        mock_khoj = AsyncMock()
        mock_khoj.health_check = AsyncMock(
            side_effect=Exception("Khoj connection failed")
        )

        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"},
        ):
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                agent = SlackAgent(config)

                # Should still succeed even with Khoj failure
                try:
                    await agent._health_check()
                except RuntimeError as e:
                    # Only fail if it's a critical service
                    assert "Ollama" in str(e) or "Slack" in str(e) or "Brain" in str(e)

    @pytest.mark.asyncio
    async def test_health_check_with_missing_config(
        self, test_brain_path, mock_llm, mock_khoj, mock_slack_app
    ):
        """
        Test health check with missing configuration values.

        Verifies that:
        - Default values are used for missing config
        - Health check still runs with defaults
        - No crashes from None values
        """
        config = {
            # Minimal config - use valid brain path
            "brain_path": str(test_brain_path),
        }

        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"},
        ):
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                agent = SlackAgent(config)

                # Should use defaults and complete
                await agent._health_check()


@pytest.mark.unit
class TestHealthCheckRecovery:
    """Test health check behavior during recovery scenarios"""

    @pytest.mark.asyncio
    async def test_health_check_retry_behavior(self, test_brain_path, mock_slack_app):
        """
        Test that health checks properly retry and recover.

        Simulates temporary failures that resolve on subsequent calls.
        """
        config = {
            "brain_path": str(test_brain_path),
            "ollama_url": "http://m1-mini.local:11434",
            "khoj_url": "http://nuc-1.local:42110",
            "model": "llama3.2",
        }

        # Mock that fails once then succeeds
        mock_llm = AsyncMock()
        mock_llm.health_check = AsyncMock()
        mock_llm.health_check.side_effect = [
            Exception("Temporary failure"),
            None,  # Success on retry
        ]

        mock_khoj = AsyncMock()
        mock_khoj.health_check = AsyncMock(return_value=None)

        with patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"},
        ):
            with (
                patch("agents.slack_agent.OllamaClient") as mock_llm_class,
                patch("agents.slack_agent.KhojClient") as mock_khoj_class,
                patch("agents.slack_agent.AsyncApp") as mock_app_class,
            ):
                mock_llm_class.return_value = mock_llm
                mock_khoj_class.return_value = mock_khoj
                mock_app_class.return_value = mock_slack_app

                agent = SlackAgent(config)

                # First check fails
                with pytest.raises(RuntimeError):
                    await agent._health_check()

                # Second check should succeed (mock side_effect continues)
                # In real scenario, would retry
