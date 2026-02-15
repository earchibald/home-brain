# home-brain 🧠

Autonomous home AI system with semantic brain search, multi-turn conversation memory, file attachment processing, and performance monitoring.

## What It Does

A Slack bot that connects to your personal knowledge base (Khoj), remembers conversations, processes file attachments, and uses local LLM inference (Ollama) to provide intelligent responses.

### Core Features

- **🤖 Slack Integration**: Real-time DM responses via Socket Mode
- **🧠 Semantic Search**: Khoj-powered brain search for contextual responses
- **💾 Conversation Memory**: Multi-turn conversations with auto-summarization
- **📎 File Attachments**: Detect, download, and extract text from .txt, .md, .pdf files
- **⚡ Performance Monitoring**: Latency tracking with P95 metrics and alerts
- **📊 Local Inference**: Ollama LLM for privacy-preserving responses
- **🔄 Graceful Degradation**: Continues working even if some services are unavailable

## Architecture

```
Slack (DMs)
    ↓
Socket Mode Handler
    ↓
slack_agent.py (Main Handler)
    ├─→ File Attachment Processing
    ├─→ Khoj Brain Search (for context)
    ├─→ Conversation Memory (history)
    └─→ Ollama LLM (inference)
    ↓
Response sent to Slack
Performance metrics logged
```

## Quick Start

### Prerequisites

- Python 3.10+
- Slack Bot with Socket Mode enabled
- Ollama running (local LLM inference)
- Khoj running (semantic search)
- Brain folder for conversation history

### Installation

```bash
# Clone repo
git clone https://github.com/earchibald/home-brain.git
cd home-brain

# Install dependencies
pip install -r tests/requirements-test.txt

# Set environment variables
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."

# Run the bot
python -m agents.slack_agent
```

### Configuration

Create a config dict with:

```python
config = {
    "khoj_url": "http://nuc-1.local:42110",
    "ollama_url": "http://m1-mini.local:11434",
    "brain_path": "/home/user/brain",
    "model": "llama3.2",
    "enable_file_attachments": True,
    "enable_performance_alerts": True,
    "slow_response_threshold": 30.0,  # Alert if response > 30s
}
```

## Features in Detail

### File Attachments

Automatically processes files sent to the bot:

```
Send in Slack: "Analyze this document" + attach file.pdf
↓
Bot downloads file
Extracts text content
Includes in LLM prompt
↓
Response based on file content
```

Supported: .txt, .md, .pdf (max 1MB)

### Conversation Memory

Persists conversation history per user/thread:

```
Message 1: "I like hiking"
Message 2: "Why is that important?"
↓
Bot remembers context from Message 1
↓
Response: "Based on your interest in hiking..."
```

Auto-summarizes when conversations exceed token limits.

### Performance Monitoring

Tracks response latencies:

```
Response Time: 23.44s
P95 (95th percentile): <30s
Alerts sent if threshold exceeded
Metrics: average, P95, histogram
```

### Khoj Brain Search

Searches personal knowledge base for context:

```
User: "What did I learn about Python?"
↓
Khoj searches brain for "Python" entries
↓
Bot: "Based on your notes about Python:
[Context from brain]
[Sources cited]"
```

## Testing

### Automated Tests

```bash
# All tests
pytest tests/ -v

# By category
pytest tests/unit -v          # Fast unit tests
pytest tests/integration -v   # Component tests
pytest tests/red -v          # Feature tests

# With coverage
pytest tests/ --cov
```

**Current Status**: 67 tests passing ✅

### Manual Testing

```bash
# Validation script
python validate_deployment.py

# Manual Slack testing
python test_slack_bot_manual.py

# Then in Slack:
- Send "Hello" → Basic test
- Attach file + "Can you read this?" → File test
- Send "Tell me a story" → Performance test
```

## Deployment

### Local Development

```bash
python -m agents.slack_agent
```

### NUC-2 Production

Systemd service: `brain-slack-bot`

```bash
# Status
sudo systemctl status brain-slack-bot

# Logs
sudo journalctl -u brain-slack-bot -f

# Restart
sudo systemctl restart brain-slack-bot
```

## File Structure

```
home-brain/
├── agents/
│   └── slack_agent.py              # Main Slack bot
├── clients/
│   ├── khoj_client.py              # Khoj API client
│   ├── llm_client.py               # Ollama API client
│   ├── brain_io.py                 # Brain folder I/O
│   └── conversation_manager.py     # Conversation history
├── slack_bot/                      # Feature modules
│   ├── file_handler.py             # File download/extraction
│   ├── message_processor.py        # File detection
│   ├── performance_monitor.py      # Latency tracking
│   ├── alerting.py                 # Alert notifications
│   ├── streaming_handler.py        # SSE streaming
│   └── ollama_client.py            # Streaming LLM client
├── tests/                          # Full test suite
│   ├── unit/                       # Unit tests (fast)
│   ├── integration/                # Integration tests
│   └── red/                        # Feature tests
├── DEPLOYMENT_CHECKLIST.md         # Deployment guide
├── READY_FOR_DEPLOYMENT.md         # Status summary
└── RUN_TESTS.md                    # Testing reference
```

## Troubleshooting

### Bot Not Responding

```bash
# Check service
sudo systemctl status brain-slack-bot

# Check logs
sudo journalctl -u brain-slack-bot -n 50

# Check Slack tokens
echo $SLACK_BOT_TOKEN
echo $SLACK_APP_TOKEN
```

### File Attachment Not Working

```bash
# Check logs for "File attachments detected"
sudo journalctl -u brain-slack-bot | grep "attachment"

# Verify file types (.txt, .md, .pdf)
# Check file size (max 1MB)
```

### Slow Responses

```bash
# Check latency in logs
sudo journalctl -u brain-slack-bot | grep "latency"

# Check Ollama performance
curl http://m1-mini.local:11434/api/tags

# Check conversation size
ls -lh ~/brain/users/*/conversations/
```

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Basic response | <15s | Ollama inference + context search |
| File attachment | <5s | Download + text extraction |
| 95th percentile | <30s | Threshold for performance alerts |
| Memory usage | ~200MB | Ollama + Python runtime |
| Concurrent users | Unlimited | Async design |

## Documentation

- **IMPLEMENTATION.md** - Architecture & setup guide
- **IMPLEMENTATION_CRITIQUE.md** - Comprehensive analysis & recommendations ⭐ NEW
- **DEPLOYMENT_CHECKLIST.md** - Step-by-step deployment
- **READY_FOR_DEPLOYMENT.md** - Status & readiness check
- **RUN_TESTS.md** - Comprehensive testing guide
- **TEST_README.md** - 2-minute quick start
- **CLAUDE.md** - Development instructions

## Development

### Technology Stack

- **Language**: Python 3.10+
- **Slack SDK**: slack-bolt (async)
- **LLM**: Ollama (local inference)
- **Brain Search**: Khoj
- **Testing**: pytest + pytest-asyncio
- **Async**: asyncio + aiohttp

### Development Workflow

1. Write failing test (RED)
2. Implement feature (GREEN)
3. Refactor (REFACTOR)
4. Commit with descriptive message
5. Deploy to NUC-2

### Running Tests

```bash
# Watch for changes
pytest tests/ -v --tb=short

# Generate coverage report
pytest tests/ --cov --cov-report=html
open htmlcov/index.html
```

## Future Enhancements

- Response streaming (infrastructure ready, can activate)
- Slack threading support
- Custom commands
- Performance dashboard
- Multi-user workspace support
- Database backend (instead of JSON files)

## License

Private - for personal use

## Contact

For questions or issues, check the logs or review the deployment documentation.

---

**Status**: ✅ Production Ready
**Tests**: 67 passing
**Coverage**: 85%+
**Last Updated**: 2026-02-15
