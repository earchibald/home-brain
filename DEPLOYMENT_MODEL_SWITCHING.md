# Deployment Guide: Dynamic Model Source Switching

## Overview

This feature allows the Slack bot to dynamically switch between multiple LLM providers:
- **Local Ollama** (Mac Mini - localhost:11434)
- **Remote Ollama** (MacBook Pro - eugenes-mbp.local:11434)
- **Google Gemini API**
- **Anthropic Claude API**

## Architecture

```
Slack Bot
    ↓
ModelManager (Discovery & State)
    ↓
BaseProvider Interface
    ├── OllamaProvider (local/remote)
    ├── GeminiProvider
    └── AnthropicProvider
```

## Installation

### 1. Install Dependencies

The required packages are already installed:
```bash
pip install ollama google-generativeai anthropic
```

Verify:
```bash
python -c "import ollama, google.generativeai, anthropic; print('✅ All packages installed')"
```

### 2. Configure Environment Variables

Add API keys to your environment (or `secrets.env`):

```bash
# Google Gemini (optional)
export GOOGLE_API_KEY="your-gemini-api-key"

# Anthropic Claude (optional)
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# Ollama hosts (optional - defaults provided)
export OLLAMA_HOST_LOCAL="http://localhost:11434"
export OLLAMA_HOST_REMOTE="http://eugenes-mbp.local:11434"
```

**Using SOPS for secrets.env:**
```bash
source .env  # Load SOPS_AGE_KEY_FILE
sops set secrets.env '["GOOGLE_API_KEY"]' '"your-key-here"'
sops set secrets.env '["ANTHROPIC_API_KEY"]' '"your-key-here"'
```

### 3. Enable Feature in Bot Configuration

Update your bot startup config to enable model switching:

```python
config = {
    "khoj_url": "http://nuc-1.local:42110",
    "ollama_url": "http://m1-mini.local:11434",
    "brain_path": "/home/earchibald/brain",
    "model": "llama3.2",
    "enable_model_switching": True,  # ← Enable the feature
}
```

**On NUC-2 systemd service:**
Edit `/etc/systemd/system/slack-bot.service` or the startup script to pass `enable_model_switching=True` in the config.

### 4. Verify Installation

Run the test suite:
```bash
cd /Users/earchibald/LLM/implementation
python -m pytest tests/test_providers.py tests/test_model_manager.py tests/test_slack_model_integration.py -v
```

Expected: **32 passing tests** ✅

## Usage

### Slack `/model` Command

1. **Open the model selector:**
   ```
   /model
   ```

2. **View available providers:**
   The UI will show:
   - Current configuration (provider + model)
   - Dropdown to select provider (Local Ollama, Remote Ollama, Gemini, Claude)
   - Dropdown to select model

3. **Select a model:**
   - Choose provider from first dropdown
   - Choose model from second dropdown
   - Confirmation message appears: "✅ Switched to gemini: gemini-1.5-flash"

### Provider Discovery

The `ModelManager` automatically discovers available providers on startup:

**Local Ollama:** Pings `http://localhost:11434/api/version` (1s timeout)
- If reachable → added to available providers
- If unreachable → skipped (no error)

**Remote Ollama:** Pings `http://eugenes-mbp.local:11434/api/version` (1s timeout)
- Same logic as local

**Cloud APIs:** Checks for environment variables
- `GOOGLE_API_KEY` present → Gemini available
- `ANTHROPIC_API_KEY` present → Anthropic available

### Model Selection Persistence

**Current Implementation:** In-memory only
- Model selection persists during bot runtime
- Resets to default on bot restart

**Future Enhancement:** Persistent storage
- Store selection in SQLite or JSON file
- Restore last selection on startup

## Integration Status

### ✅ Complete
- Provider adapters (Ollama, Gemini, Anthropic)
- ModelManager discovery and switching
- Slack `/model` command UI
- Block Kit dropdown interactions
- 32 passing tests

### ⚠️ Partial
- Bot still uses `OllamaClient` directly for message processing
- `/model` command changes provider selection but doesn't affect current inference
- **Reason:** Maintaining backward compatibility with existing bot flow

### 🔄 Future Work

**Phase 2: Full Integration**
1. Update `_process_message()` to use `ModelManager.generate()`
2. Convert message history to prompt format for ModelManager
3. Add model info to conversation metadata
4. Support streaming responses from cloud APIs

**Phase 3: Advanced Features**
1. Per-user model preferences
2. Per-conversation model memory
3. Automatic fallback (if primary provider fails, try secondary)
4. Cost tracking for cloud API usage
5. Performance comparison dashboard

## Troubleshooting

### "No providers available"
**Cause:** No Ollama servers reachable AND no API keys set

**Fix:**
1. Check Ollama is running: `curl http://localhost:11434/api/version`
2. Verify API keys: `echo $GOOGLE_API_KEY`
3. Check bot logs for discovery errors

### "/model command not found"
**Cause:** Feature flag not enabled OR bot not restarted

**Fix:**
1. Verify `enable_model_switching=True` in config
2. Restart bot: `systemctl restart slack-bot` (on NUC-2)
3. Check logs: `journalctl -u slack-bot -f`

### "Provider X not available"
**Cause:** Provider failed health check or missing credentials

**Fix for Ollama:**
```bash
# Check if Ollama is running
systemctl status ollama

# Check network connectivity
ping -c 3 eugenes-mbp.local
curl http://eugenes-mbp.local:11434/api/version
```

**Fix for Cloud APIs:**
```bash
# Verify API keys are set
sops -d secrets.env | grep API_KEY

# Test API key validity
python -c "import google.generativeai as genai; genai.configure(api_key='YOUR_KEY'); print(genai.list_models())"
```

### Model selection doesn't affect responses
**Expected:** This is current behavior (Phase 1)

**Workaround:** Model selection UI is functional but not yet integrated into inference pipeline

**Timeline:** Phase 2 integration (future PR)

## Deployment Checklist

- [ ] Dependencies installed (`ollama`, `google-generativeai`, `anthropic`)
- [ ] API keys added to `secrets.env` (if using cloud providers)
- [ ] Feature flag enabled (`enable_model_switching=True`)
- [ ] Bot restarted
- [ ] Tests passing (32/32)
- [ ] `/model` command works in Slack
- [ ] Provider discovery logs show available providers
- [ ] Model selection UI displays correctly
- [ ] Selection confirmation messages appear

## Testing

### Unit Tests
```bash
# All provider tests
pytest tests/test_providers.py -v

# ModelManager tests
pytest tests/test_model_manager.py -v

# Slack integration tests
pytest tests/test_slack_model_integration.py -v

# Full suite
pytest tests/test_*provider* tests/test_*model* -v
```

### Manual Testing
1. Start bot with feature enabled
2. Send `/model` in Slack DM
3. Verify UI appears with current config
4. Select different provider + model
5. Verify confirmation message
6. Check bot logs for state change

### Integration Testing
```bash
# Run E2E tests (if available)
python -m pytest tests/test_e2e_model_switching.py -v
```

## Performance Considerations

**Discovery Overhead:**
- Runs on bot startup (one-time)
- Runs on `/model` command (user-initiated)
- Health checks timeout after 1s per provider
- Total discovery time: ~2-3 seconds max

**Runtime Overhead:**
- Negligible (simple state management)
- No performance impact on message processing

## Security Notes

1. **API Keys:** Store in encrypted `secrets.env` via SOPS
2. **Network Access:** Ollama servers must be on trusted network
3. **User Permissions:** `/model` command available to all DM users
   - Future: Add role-based access control

## Monitoring

**Key Metrics to Track:**
- Provider discovery success rate
- Model switching frequency
- Provider failover events (future)
- API cost per provider (future)

**Logs to Monitor:**
```bash
# Check model switching events
journalctl -u slack-bot | grep "Model switched"

# Check discovery results
journalctl -u slack-bot | grep "Available providers"

# Check errors
journalctl -u slack-bot | grep -i error
```

## Rollback Plan

If issues arise, disable the feature:

```python
config = {
    # ...
    "enable_model_switching": False,  # Disable feature
}
```

Restart bot. All existing functionality remains unchanged.

## Support

**Documentation:**
- Feature spec: `DYNAMIC_MODEL_SOURCE_SWITCHING.md`
- Implementation details: `tests/test_providers.py`

**Issues:**
- Check logs: `journalctl -u slack-bot -f`
- Run tests: `pytest tests/test_*model* -v`
- Review provider health checks in ModelManager

---

**Version:** 1.0.0
**Last Updated:** 2026-02-15
**Status:** Phase 1 Complete ✅
