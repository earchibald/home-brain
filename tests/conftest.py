"""
Core pytest fixtures and configuration for the test framework.

This module provides shared fixtures for all test categories (unit, integration,
remote, e2e, red). Fixtures are designed to be async-aware and provide realistic
mock data matching production structures.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import agents and clients modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any


# ============================================================================
# Async Event Loop Management
# ============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests.

    Required for pytest-asyncio to manage the event loop across test sessions.
    This fixture ensures consistent async behavior across all test types.

    Yields:
        asyncio.AbstractEventLoop: Event loop for async test execution
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# File System Fixtures
# ============================================================================


@pytest.fixture
def test_brain_path(tmp_path) -> Path:
    """
    Temporary brain folder with realistic directory structure.

    Creates a temporary directory matching production brain layout with
    users/ and journal/ subdirectories. Useful for testing conversation
    persistence, brain I/O operations, and file-based storage.

    Args:
        tmp_path: pytest's temporary directory fixture

    Returns:
        Path: Path to temp brain folder with users/ and journal/ subdirectories
    """
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "users").mkdir()
    (brain / "journal").mkdir()
    return brain


# ============================================================================
# Slack Event Fixtures
# ============================================================================


@pytest.fixture
def sample_slack_event() -> Dict[str, Any]:
    """
    Realistic Slack DM message event.

    Returns a properly formatted Slack event that matches the structure of
    real Slack message events. Useful for testing message handlers, event
    processing, and integration with Slack AsyncApp.

    Returns:
        Dict[str, Any]: Dict matching Slack event structure with all required fields
    """
    return {
        "channel_type": "im",
        "user": "U01TEST123",
        "text": "Hello, bot!",
        "ts": "1234567890.123456",
        "channel": "C01TEST",
        "type": "message",
    }


@pytest.fixture
def sample_conversation() -> List[Dict[str, str]]:
    """
    Multi-turn conversation for testing context and memory.

    Returns a sample conversation with multiple user/assistant exchanges,
    timestamps, and realistic content. Useful for testing conversation
    management, history retrieval, token counting, and summarization.

    Returns:
        List[Dict[str, str]]: List of message dicts with role, content, and timestamp
    """
    return [
        {
            "role": "user",
            "content": "What is ADHD?",
            "timestamp": "2026-02-14T10:00:00",
        },
        {
            "role": "assistant",
            "content": "ADHD is a neurodevelopmental disorder characterized by persistent inattention and/or hyperactivity-impulsivity.",
            "timestamp": "2026-02-14T10:00:15",
        },
        {
            "role": "user",
            "content": "How can I manage it?",
            "timestamp": "2026-02-14T10:01:00",
        },
        {
            "role": "assistant",
            "content": "You can manage ADHD through medication, therapy, lifestyle changes, and structured routines.",
            "timestamp": "2026-02-14T10:01:25",
        },
    ]


# ============================================================================
# LLM Client Mocks
# ============================================================================


@pytest.fixture
def mock_llm() -> AsyncMock:
    """
    Mock LLM client with async methods.

    Provides an AsyncMock that simulates the LLM client's interface,
    including chat(), complete(), and health_check() methods. Returns
    predefined responses suitable for testing prompt injection, context
    handling, and error scenarios.

    Returns:
        AsyncMock: Mock LLM client with properly configured async methods
    """
    mock = AsyncMock()
    mock.chat.return_value = "This is a test response from the LLM."
    mock.complete.return_value = "Test completion."
    mock.health_check.return_value = True
    return mock


# ============================================================================
# Semantic Search Client Mocks
# ============================================================================


@pytest.fixture
def mock_search() -> AsyncMock:
    """
    Mock semantic search client with async search() method.

    Provides an AsyncMock that simulates the SemanticSearchClient interface,
    including search() and health_check() methods. Returns realistic
    search results with proper metadata (entry, score, file path, heading).

    Returns:
        AsyncMock: Mock search client returning sample search results
    """
    mock = AsyncMock()
    mock.search.return_value = [
        {
            "entry": "Sample brain entry about productivity and time management",
            "score": 0.95,
            "file": "journal/2026-02-10.md",
            "heading": "Morning Reflection",
        },
        {
            "entry": "Notes on personal development and growth strategies",
            "score": 0.87,
            "file": "journal/2026-02-09.md",
            "heading": "Weekly Review",
        },
    ]
    mock.health_check.return_value = True
    return mock


# ============================================================================
# Slack App Mocks
# ============================================================================


@pytest.fixture
def mock_slack_app() -> MagicMock:
    """
    Mock Slack AsyncApp with event handlers and API methods.

    Provides a MagicMock that simulates the Slack AsyncApp's interface,
    including say() for sending messages, client.chat_delete() for cleanup,
    and client.auth_test() for authentication checks. Designed to support
    testing message sending, working indicator cleanup, and event handling.

    Returns:
        MagicMock: Mock Slack app with say(), client.chat_delete(), and auth_test() mocked
    """
    app = MagicMock()

    # Mock say() to return message with timestamp (simulates successful message post)
    async def mock_say(text: str, **kwargs) -> Dict[str, Any]:
        """Simulate successful Slack message post."""
        return {"ts": "1234567890.999999", "ok": True}

    app.say = AsyncMock(side_effect=mock_say)

    # Mock chat_delete for cleaning up working indicator
    app.client.chat_delete = AsyncMock(return_value={"ok": True})

    # Mock auth_test for startup verification
    app.client.auth_test = AsyncMock(
        return_value={"user": "brain_assistant", "user_id": "U0ASSISTANT"}
    )

    # Mock message sending for error handling scenarios
    app.client.chat_postMessage = AsyncMock(
        return_value={"ts": "1234567890.888888", "ok": True}
    )

    return app


# ============================================================================
# Notification Mocks
# ============================================================================


@pytest.fixture
def mock_ntfy():
    """
    Mock subprocess for ntfy.sh notifications.

    Patches subprocess.run to intercept ntfy.sh notification calls.
    Allows tests to verify that alerts are sent on errors without
    making actual HTTP requests.

    Yields:
        MagicMock: Patched subprocess.run for ntfy notification captures
    """
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        yield mock_run


# ============================================================================
# Remote Test Fixtures (SSH)
# ============================================================================


@pytest.fixture(scope="session")
def ssh_nuc2():
    """
    SSH connection pool to NUC-2 (remote service).

    Establishes a persistent SSH connection to NUC-2 for remote testing.
    Reused across all remote tests for performance. Requires:
    - Network access to nuc-2
    - SSH key authentication configured
    - earchibald user account on NUC-2

    Yields:
        paramiko.SSHClient: Connected SSH client for NUC-2 operations

    Raises:
        paramiko.AuthenticationException: If SSH authentication fails
        paramiko.SSHException: If SSH connection fails
    """
    try:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect("nuc-2", username="earchibald", timeout=10)

        yield client
    finally:
        client.close()


@pytest.fixture
def remote_test_brain(ssh_nuc2) -> str:
    """
    Create temporary brain folder on NUC-2 for remote testing.

    Creates a test brain directory on NUC-2 with proper structure (users/,
    journal/), allowing tests to verify real service behavior. Automatically
    cleans up the test directory after the test completes.

    Args:
        ssh_nuc2: SSH connection fixture to NUC-2

    Returns:
        str: Path to temporary brain folder on NUC-2 (e.g., /tmp/brain_test_abc12345)

    Note:
        - Test directory is created with users/ subdirectory
        - Cleanup is automatic after test completes
        - Tests using this fixture should be marked @pytest.mark.remote
    """
    import uuid

    test_id = str(uuid.uuid4())[:8]
    brain_path = f"/tmp/brain_test_{test_id}"

    # Create folder structure on remote
    stdin, stdout, stderr = ssh_nuc2.exec_command(f"mkdir -p {brain_path}/users")
    stdout.channel.recv_exit_status()  # Wait for completion

    yield brain_path

    # Cleanup after test
    ssh_nuc2.exec_command(f"rm -rf {brain_path}")


# ============================================================================
# Parametrization Helpers
# ============================================================================


@pytest.fixture(params=["U01TEST123", "U02TEST456", "U03TEST789"])
def multiple_users(request) -> str:
    """
    Parametrized fixture providing multiple test user IDs.

    Useful for testing multi-user scenarios, user isolation, and
    concurrent message handling without code duplication.

    Args:
        request: pytest request object with param

    Returns:
        str: User ID from parametrized list
    """
    return request.param


@pytest.fixture(
    params=[
        {"text": "hello", "type": "message", "user": "U01TEST"},
        {"text": "", "type": "message", "user": "U01TEST"},
        {"text": "test", "type": "app_mention", "user": "U01TEST"},
    ]
)
def slack_event_variants(request) -> Dict[str, Any]:
    """
    Parametrized fixture providing various Slack event types.

    Covers message events, empty messages, and app mentions for
    comprehensive event handler testing.

    Args:
        request: pytest request object with param

    Returns:
        Dict[str, Any]: Slack event variant
    """
    event = {
        "channel_type": "im",
        "user": request.param.get("user", "U01TEST123"),
        "ts": "1234567890.123456",
        "channel": "C01TEST",
        **request.param,
    }
    return event
