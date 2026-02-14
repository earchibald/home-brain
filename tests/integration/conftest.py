"""
Integration test configuration and fixtures.

Provides integration-specific fixtures and setup to handle module-level
imports that require external resources (brain folders, services).
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

# Setup test brain before any imports
test_brain_path = Path(__file__).parent.parent / 'test_brain'
test_brain_path.mkdir(parents=True, exist_ok=True)
(test_brain_path / 'users').mkdir(parents=True, exist_ok=True)
(test_brain_path / 'journal').mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session", autouse=True)
def mock_agent_platform_on_import():
    """
    Mock agent_platform global instantiation at import time.

    This prevents the global AgentPlatform() call in agent_platform.py
    from failing when importing agents.slack_agent during test discovery.
    """
    with patch('clients.brain_io.BrainIO') as mock_brain:
        with patch('clients.khoj_client.KhojClient') as mock_khoj:
            with patch('clients.llm_client.OllamaClient') as mock_llm:
                # Make mocks return MagicMock instances
                mock_brain.return_value = MagicMock()
                mock_khoj.return_value = MagicMock()
                mock_llm.return_value = MagicMock()

                yield


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment with necessary directories and mocks."""
    # Ensure test brain directory exists
    test_brain_path.mkdir(parents=True, exist_ok=True)

    # Mock the brain folder in environment if needed
    os.environ.setdefault('BRAIN_FOLDER', str(test_brain_path))

    yield

    # Cleanup
    import shutil
    if test_brain_path.exists():
        shutil.rmtree(test_brain_path, ignore_errors=True)
