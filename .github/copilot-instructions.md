# Copilot Agent Instructions for home-brain

## Project Overview

This is a Python Slack bot that integrates with Khoj (semantic brain search), Ollama (local LLM inference), and a personal knowledge base. It runs on a distributed NUC cluster.

## Repository Structure

```
agents/           - Main agent implementations (slack_agent.py is the primary bot)
clients/          - Service clients (Khoj, Ollama, BrainIO, ConversationManager)
slack_bot/        - Feature modules (file handling, streaming, performance monitoring)
tests/            - Pytest test suite
  unit/           - Fast unit tests (no external deps)
  integration/    - Integration tests (mocked externals)
  red/            - TDD red tests for new features
```

## Key Files

- `agents/slack_agent.py` - Main Slack bot (entry point)
- `agent_platform.py` - Base Agent class
- `clients/khoj_client.py` - Khoj API client
- `clients/llm_client.py` - Ollama LLM client
- `clients/conversation_manager.py` - Multi-turn conversation persistence
- `slack_bot/file_handler.py` - File download and text extraction
- `slack_bot/performance_monitor.py` - Latency tracking and alerting
- `conftest.py` - Root path setup
- `tests/conftest.py` - All test fixtures

## Testing

### Running Tests
```bash
# Run unit + integration tests (CI suite)
python -m pytest tests/ -m "unit or integration" -v

# Run all tests
python -m pytest tests/ -v
```

### Test Configuration
- `tests/pytest.ini` - Pytest config with markers and coverage settings
- Dependencies: `tests/requirements-test.txt`
- App deps: `slack-bolt slack-sdk aiohttp requests PyPDF2`

### Test Markers
- `unit` - Fast tests, no external dependencies
- `integration` - Uses mocks for external services
- `red` - TDD red tests (expected to fail until feature is implemented)
- `remote` - Requires SSH to NUC hardware (skip in CI)
- `requires_secrets` - Needs SOPS secrets (skip in CI)
- `requires_slack` - Needs real Slack tokens (skip in CI)

## Coding Conventions

- Python 3.12+
- Async code uses `asyncio` and `pytest-asyncio`
- Slack SDK: `slack-bolt` with `AsyncApp` and Socket Mode
- Configuration is dict-based (passed to `__init__`)
- Error handling: graceful degradation, never crash the bot
- Custom exceptions in `slack_bot/exceptions.py`

## When Fixing Bugs

1. Reproduce the failure with the existing test command
2. Understand the root cause before changing code
3. Fix the underlying issue - do NOT skip, delete, or `xfail` tests
4. Ensure all unit + integration tests pass after your fix
5. Keep changes minimal and focused on the fix
