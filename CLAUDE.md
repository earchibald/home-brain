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
- `ssh nuc-1` (192.168.1.195) — Khoj + Postgres + Syncthing
- `ssh nuc-2` (192.168.1.196) — Automation + Syncthing
- `ssh nuc-3` (192.168.1.197) — Storage + Restic + Syncthing + rclone + pCloud

All have passwordless sudo for `earchibald` user.

---

## Key Decisions & Gotchas

1. **Khoj HTTP only** — No TLS on :42110. Use `http://nuc-1.local:42110` (not https)
2. **Restic password** — Local repo password stored unknown location (works via cron). pCloud repo password in `~/.restic-pcloud-password`
3. **Syncthing introducer** — NUC-3 acts as introducer but manual device/folder sharing was needed
4. **SOPS Age key** — Must be sourced before any `sops` command or it fails silently with "no matching creation rules"
5. **pCloud** — US region only (`api.pcloud.com`), rclone token stored in `~/.config/rclone/rclone.conf` on NUC-3

---

## Test Framework (2026-02-14c)

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

**Run only GREEN tests (current features, should all pass):**
```bash
python -m pytest tests/ -m "unit or integration" -v
```

**Run only RED tests (future features, expected to fail):**
```bash
python -m pytest tests/ -m red -v
```

**Run specific test file:**
```bash
python -m pytest tests/unit/test_conversation_manager.py -v
```

**Run with coverage:**
```bash
python -m pytest tests/ --cov --cov-report=html
open htmlcov/index.html
```

### Test Structure
- `tests/unit/` - Fast unit tests for individual components (10+ tests)
- `tests/integration/` - Integration tests with mocked externals (21 tests)
- `tests/red/` - RED tests for unimplemented features (8-6-4 = 18 tests)

### Current Status (2026-02-14c)
- ✅ **49 GREEN tests PASSING** - Current features fully tested
- ❌ **20 RED tests FAILING** - Expected! These test features not yet implemented
- **RED test targets for next work:**
  - File attachment handling (8 tests)
  - Response streaming (6 tests)
  - Performance monitoring (4 tests)

### Key Fixes Applied
1. Moved client modules (`khoj_client.py`, `llm_client.py`, `brain_io.py`) into `clients/` directory to match imports
2. Updated integration test fixtures to properly mock sync vs async methods
3. Added error handling to `slack_agent._process_message()` for graceful degradation when conversation save fails
4. Created root `conftest.py` for Python path setup during test collection

### For Next Session
- Run `pytest tests/ -v` to verify test status
- Implement file attachment feature to make RED tests in `tests/red/test_file_attachments.py` pass
- Then implement streaming and performance monitoring features
- Each feature should convert RED tests → GREEN tests

---

## Recent Work (2026-02-14)

- **Session A:** Fixed NUC-2/3 configs, enabled Syncthing, fixed journal_bot.py, configured Khoj indexing
- **Session B:** Added pCloud offsite backup via rclone + Restic (browsable sync + encrypted backup)
- **Session C:** Implemented comprehensive TDD test framework with pytest (49 GREEN + 20 RED tests)

See `SESSION_HANDOFF_*.md` for detailed handoff notes from each session.
