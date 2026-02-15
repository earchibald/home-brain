# Implementation Addendum

Session date: 2026-02-14

## Summary

Completed NUC-2, NUC-3, and end-to-end verification for the distributed AI knowledge mesh. Mac Mini and NUC-1 were already operational from prior sessions.

## Fixes Applied

### 1. NUC-2: Syncthing service not enabled
- **Problem:** Syncthing was running but `disabled` in systemd, meaning it would not survive a reboot.
- **Fix:** `systemctl --user enable syncthing.service`
- **Verified:** Service now shows `enabled`.

### 2. NUC-3: Missing backup cron job
- **Problem:** The `0 3 * * * /home/earchibald/backup_brain.sh` cron entry was missing. Only the `monitor_docker.sh` entry existed.
- **Fix:** Added the backup cron entry alongside existing entries.
- **Verified:** `crontab -l` now shows both monitor and backup entries.

### 3. NUC-2: journal_bot.py syntax error
- **Problem:** The `f.write()` call used a multi-line f-string with literal newlines, which is a `SyntaxError` in Python 3.12 (`unterminated f-string literal`).
- **Fix:** Replaced literal newlines with `\n` escape sequences in the f-string.
- **Verified:** Script runs successfully and creates properly formatted journal entries.

### 4. NUC-1: Khoj content sources not configured
- **Problem:** Khoj v1.42.10 does not read the `KHOJ_CONTENT_DIRECTORIES` or `KHOJ_CONTENT_TYPES` environment variables. The database had zero `LocalMarkdownConfig`, `LocalPlaintextConfig`, or `LocalPdfConfig` entries, so no content was being indexed (0 entries).
- **Fix:** Created content source configurations directly in the Khoj database:
  - `LocalMarkdownConfig` with `input_filter: ["/app/brain/**/*.md"]`
  - `LocalPlaintextConfig` with `input_filter: ["/app/brain/**/*.txt"]`
  - `LocalPdfConfig` with `input_filter: ["/app/brain/**/*.pdf"]`
- **Verified:** After re-indexing, Khoj indexed 3 markdown files and 1 plaintext file. Search API returns correct results.

## Verification Results

### Syncthing File Sync
- Created test file on NUC-2 (`sync_verification_test.md`)
- File appeared on NUC-1 and NUC-3 within 10 seconds
- Created test file on NUC-1 (`reverse_sync_test.md`)
- File appeared on NUC-2 and NUC-3 within 10 seconds
- **Result:** Bidirectional sync confirmed across all 3 NUCs

### Syncthing Cluster Connections
| Source | Target | Status |
|--------|--------|--------|
| NUC-1 | NUC-2 (FLECAZT) | Connected |
| NUC-1 | NUC-3 (C7E6E7M) | Connected |
| NUC-1 | Laptop (5JNLT3O) | Connected |
| NUC-2 | NUC-1 (7ZLYPHB) | Connected |
| NUC-2 | NUC-3 (C7E6E7M) | Connected |
| NUC-3 | NUC-1 (7ZLYPHB) | Connected |
| NUC-3 | NUC-2 (FLECAZT) | Connected |

### Khoj Search
- Triggered re-index via `/api/update?force=true`
- Searched for "sync verification" via `/api/search?q=sync+verification&t=markdown`
- Returned correct results including the test file content
- **Result:** End-to-end pipeline working (file sync -> indexing -> search)

### Ollama Inference
- `curl http://m1-mini.local:11434` returns "Ollama is running"
- Accessible from NUC-1

### Notification System
- Sent test notification from NUC-1 via `notify.sh`
- ntfy.sh API returned success with message ID `ocop5UR9xzNW`
- Topic: `omnibus-brain-notifications-v3`

### Docker Container Health
| Host | Container | Status |
|------|-----------|--------|
| NUC-1 | brain_khoj | Healthy |
| NUC-1 | brain_db | Healthy |
| NUC-3 | brain_sync | Healthy |

### Journal Bot
- Ran successfully after fix
- Created `/home/earchibald/brain/journal/2026-02-14.md` with correct formatting

## 5. NUC-3: pCloud offsite backup integration
- **Goal:** Add offsite backup to pCloud with both browsable sync and encrypted Restic backups.
- **Components installed:**
  - `rclone` on Mac (Homebrew, v1.73.0) — used for OAuth flow
  - `rclone` on NUC-3 (apt, v1.60.1) — used for sync and Restic backend
- **pCloud config:** `~/.config/rclone/rclone.conf` on NUC-3 (US region, `api.pcloud.com`)
- **pCloud folders:**
  - `pcloud:/brain` — browsable mirror of brain files (via `rclone sync`)
  - `pcloud:/brain-backups` — encrypted Restic repository
- **Sync script:** `/home/earchibald/sync_to_pcloud.sh`
  1. `rclone sync` brain folder to `pcloud:/brain` (browsable)
  2. `restic backup` brain folder to `rclone:pcloud:/brain-backups` (encrypted)
  3. `restic forget` with retention: 7 daily, 4 weekly, 6 monthly
  4. Error trap sends notification via `notify.sh`
- **Restic password:** stored at `~/.restic-pcloud-password` (mode 600) and in `secrets.env` (SOPS) as `RESTIC_PCLOUD_PASSWORD`
- **Cron:** `30 3 * * *` — runs 30 minutes after the local backup (3:00 AM)
- **Verified:**
  - Browsable sync: 3 files visible on `pcloud:/brain`
  - Encrypted backup: snapshot `9fabf550` saved to `pcloud:/brain-backups`
  - Restic forget policy applied correctly

## Final State: All Components Operational

| Host | Role | Status |
|------|------|--------|
| Mac Mini | Inference (Ollama) | Running |
| NUC-1 | Librarian (Khoj + Postgres + Syncthing) | Running, indexing, searchable |
| NUC-2 | Automation (Agents + Syncthing) | Running, enabled, cron active |
| NUC-3 | Storage Hub (Syncthing + Restic + pCloud) | Running, healthy, local + offsite backups active |
| Notification System | ntfy.sh | Working across all NUCs |

## Future Implementation Considerations

### Semantic Search Service Migration (Khoj → ChromaDB)

**Context:** The Khoj configuration constraints discovered in section 4 (environment variables not read, manual DB configuration required) were a contributing factor in the decision to migrate to a custom ChromaDB-based semantic search service.

**Migration Drivers:**
- Heavy infrastructure for single API endpoint (<5% of Khoj features used)
- 30-minute indexing delay (cron-based vs. real-time file watching)
- Configuration complexity (env vars not honored, direct DB setup required)
- Zero test coverage for local deployment
- Desire for full control over search behavior

**Migration Guardrails:**
These patterns were identified during the Khoj deployment and should be preserved in any replacement service:

1. **Content Filtering:** Support `.md`, `.txt`, `.pdf` file types with recursive glob patterns (`/path/**/*.md`)
2. **Search API Compatibility:** Preserve `/api/search?q={query}` endpoint format for client compatibility
3. **Response Format:** JSON array with `entry` (snippet), `file` (path), `score` fields
4. **Health Monitoring:** Continue health check endpoint pattern for monitoring and graceful degradation
5. **Indexing Strategy:** Real-time file watching (debounced) plus periodic full scans
6. **Embeddings:** Use `nomic-embed-text` (384d) via Ollama for consistency

**Reference:** See "Semantic Search Service Patterns (Derived from Khoj)" section in `AGENT-INSTRUCTIONS.md` for complete pattern documentation.

**Implementation Status:** Planned for future development. Current Khoj deployment remains operational until replacement service is ready and validated.
