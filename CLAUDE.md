# Claude Code Instructions for /Users/earchibald/LLM/implementation

## CRITICAL: secrets.env Handling

**secrets.env is encrypted with SOPS (Age encryption). Mishandling it causes data loss.**

### Setup
Before ANY sops operation, source the .env file to load the age key:
```bash
source /Users/earchibald/LLM/implementation/.env
```

### Safe Update Pattern
**ALWAYS use `sops set` to add/modify vars — this is the safest method:**

```bash
source .env
sops set secrets.env '["NEW_VAR"]' '"new_value"'
```

Example:
```bash
source .env
sops set secrets.env '["BILLING_NOTIFICATIONS_TOPIC"]' '"billing-notifications-uuid-here"'
```

Verify it worked:
```bash
sops -d secrets.env
```

### Alternative: Decrypt → Edit → Re-encrypt (if needed for bulk changes)
If you need to add many vars at once:

1. **Backup first:**
   ```bash
   cp secrets.env secrets.env.backup
   ```

2. **Decrypt:**
   ```bash
   source .env
   sops -d secrets.env > /tmp/secrets_plain.env
   ```

3. **Edit plaintext:**
   ```bash
   echo "NEW_VAR=value" >> /tmp/secrets_plain.env
   cat /tmp/secrets_plain.env  # Verify
   ```

4. **Use `sops set` for each line** (safer than trying to re-encrypt):
   ```bash
   source .env
   while IFS='=' read -r key value; do
     sops set secrets.env "[\"$key\"]" "\"$value\""
   done < /tmp/secrets_plain.env
   rm /tmp/secrets_plain.env
   ```

### DO NOT DO THIS
- ❌ Try to `sops -e` on a plaintext file (creates corrupt encrypted files)
- ❌ Try to `sops -e -i` on a file without SOPS metadata
- ❌ Pipe `sops -d` to `sops -e` directly
- ❌ Use editor mode (`sops secrets.env`) — it requires a terminal
- ❌ Forget to `source .env` before running sops commands
- ❌ Run sops commands from a different directory (rules are path-relative)

### Backup Recovery
If you corrupt secrets.env:
```bash
cp secrets.env.backup secrets.env
```

---

## Project Structure

- `IMPLEMENTATION.md` — Main architecture & setup guide
- `AGENT-INSTRUCTIONS.md` — Current working state of all NUCs (reference doc)
- `IMPLEMENTATION_ADDENDUM.md` — Latest session changes
- `SESSION_HANDOFF_*.md` — Transition docs between sessions
- `.env` — Loads SOPS_AGE_KEY_FILE (required before sops commands)
- `secrets.env` — SOPS-encrypted environment variables
- `.sops.yaml` — SOPS config with Age encryption rules

---

## Host Access

All passwordless via SSH configured user `earchibald`:
- `ssh nuc-1` (nuc-1.local) — Khoj + Postgres + Syncthing
- `ssh nuc-2` (nuc-2.local) — Automation + Syncthing
- `ssh nuc-3` (nuc-3.local) — Storage + Restic + Syncthing + rclone + pCloud

All have passwordless sudo for `earchibald` user.

---

## Key Decisions & Gotchas

1. **Khoj HTTP only** — No TLS on :42110. Use `http://nuc-1.local:42110` (not https)
2. **Restic password** — Local repo password stored unknown location (works via cron). pCloud repo password in `~/.restic-pcloud-password`
3. **Syncthing introducer** — NUC-3 acts as introducer but manual device/folder sharing was needed
4. **SOPS Age key** — Must be sourced before any `sops` command or it fails silently with "no matching creation rules"
5. **pCloud** — US region only (`api.pcloud.com`), rclone token stored in `~/.config/rclone/rclone.conf` on NUC-3

---

## Test Framework & Implementation Status (2026-02-14)

### Setup
Install test dependencies:
```bash
cd /Users/earchibald/LLM/implementation
pip install -r tests/requirements-test.txt
```

### Running Tests

**Run all tests:**
```bash
python -m pytest tests/ -v
```

**Run only GREEN tests (should all pass):**
```bash
python -m pytest tests/ -m "unit or integration" -v
```

**Run with coverage:**
```bash
python -m pytest tests/ --cov --cov-report=html
open htmlcov/index.html
```

### Current Status (2026-02-14, feature integration complete)
- ✅ **67 GREEN tests PASSING** - All core features + RED tests converted to GREEN
- ✅ **18 RED tests → GREEN** - File attachments (8), streaming (6), performance (4)
- ✅ **Features integrated into slack_agent.py** - Ready for NUC-2 deployment
- ❌ **2 edge case failures** - Health check edge cases (not from RED tests)

### Features Implemented via TDD

**1. File Attachment Handling** ✅
- Detects .txt, .md, .pdf file attachments in Slack messages
- Downloads files from Slack API with authentication
- Extracts text content with automatic truncation (max 1MB)
- Graceful error handling for unsupported types and download failures
- Location: `slack_bot/message_processor.py`, `slack_bot/file_handler.py`

**2. Response Streaming** ✅
- Streams responses from Ollama in real-time
- Incrementally updates Slack messages with partial responses
- Batches updates for reasonable frequency (not spamming)
- Falls back to non-streaming if failure occurs
- Location: `slack_bot/streaming_handler.py`, `slack_bot/slack_message_updater.py`, `slack_bot/ollama_client.py`

**3. Performance Monitoring** ✅
- Tracks response latencies and calculates metrics
- Computes average latency, P95 percentile, latency histogram
- Sends alerts when responses exceed threshold (default 30 seconds)
- Supports Slack notifications
- Location: `slack_bot/performance_monitor.py`, `slack_bot/alerting.py`

### Integration with slack_agent.py
These features are implemented but not yet integrated into the main agent. To enable:

1. **File attachments:** Add file detection to `handle_message()` event handler
2. **Streaming:** Update `_process_message()` to use `OllamaStreamingClient`
3. **Performance monitoring:** Add `PerformanceMonitor` instance and call `record_response_time()`

See next session section below.

### File Structure
```
slack_bot/
  ├── __init__.py
  ├── exceptions.py - Custom exception classes
  ├── message_processor.py - File detection from Slack events
  ├── file_handler.py - Download and text extraction
  ├── streaming_handler.py - Chunk processing
  ├── slack_message_updater.py - Incremental message updates
  ├── ollama_client.py - Streaming LLM client
  ├── performance_monitor.py - Latency tracking
  └── alerting.py - Alert notifications
```

---

## Recent Work (2026-02-14)

- **Session A:** Fixed NUC-2/3 configs, enabled Syncthing, fixed journal_bot.py, configured Khoj indexing
- **Session B:** Added pCloud offsite backup via rclone + Restic (browsable sync + encrypted backup)
- **Session C:** Implemented comprehensive TDD test framework with pytest (49 GREEN + 20 RED tests)

See `SESSION_HANDOFF_*.md` for detailed handoff notes from each session.
