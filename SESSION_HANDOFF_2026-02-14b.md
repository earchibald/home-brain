# Session Handoff — 2026-02-14 (Session B: pCloud Integration)

## What Was Done This Session

### pCloud Offsite Backup — COMPLETE

Implemented dual offsite backup strategy on NUC-3 (nuc-3.local):

1. **Installed rclone** on Mac (Homebrew v1.73.0) and NUC-3 (apt v1.60.1)
2. **Completed pCloud OAuth** — token stored in `~/.config/rclone/rclone.conf` on NUC-3 (mode 600, US region `api.pcloud.com`)
3. **Created pCloud directories:**
   - `pcloud:/brain` — browsable mirror of brain files
   - `pcloud:/brain-backups` — encrypted Restic repository (repo ID `996d917e48`)
4. **Created sync script** at `/home/earchibald/sync_to_pcloud.sh`:
   - `rclone sync` for browsable copy
   - `restic backup` + `restic forget` for encrypted backup (7 daily, 4 weekly, 6 monthly)
   - Error trap sends ntfy notification
5. **Restic password file** at `~/.restic-pcloud-password` (mode 600) — same password as local Restic repo (`res-2026-pwd`)
6. **Cron job** added: `30 3 * * *` (30 min after local backup at 3:00 AM)
7. **Verified end-to-end** — manual run succeeded, browsable files visible on pCloud, Restic snapshot confirmed

### Files Modified
- **NUC-3:** `~/sync_to_pcloud.sh` (new), `~/.config/rclone/rclone.conf` (new), `~/.restic-pcloud-password` (new), crontab (added entry)
- **Local:** `secrets.env` (user manually added `RESTIC_PCLOUD_PASSWORD` via SOPS), `IMPLEMENTATION_ADDENDUM.md` (updated), `AGENT-INSTRUCTIONS.md` (updated)

### Documents Updated
- `AGENT-INSTRUCTIONS.md` — added pCloud/rclone config, sync script, and cron entry to NUC-3 section
- `IMPLEMENTATION_ADDENDUM.md` — added section 5 documenting the pCloud integration

---

## SOPS / secrets.env Notes

**Important for future agents:** To use `sops`, you MUST load the `.env` file first:
```bash
export SOPS_AGE_KEY_FILE=/Users/earchibald/.config/sops/age/agent_key.txt
```
This is stored in `/Users/earchibald/LLM/implementation/.env`. Without it, `sops` commands will fail with encryption/decryption errors.

Current `secrets.env` contents (encrypted via SOPS with Age):
- `NTFY_TOPIC` — ntfy.sh notification topic
- `RESTIC_PCLOUD_PASSWORD` — Restic password for pCloud repo

Note: `SSH_USERNAME` and `SSH_PASSWORD` may have been removed during the user's manual edit — verify if needed.

---

## Open Question: NUC-2 Automation Role

The user's last question before ending the session was about **what NUC-2 should actually do**. This is the most important next task.

### Current State of NUC-2
- Syncthing: running, syncing brain folder
- `journal_bot.py`: creates a daily journal file at 6 AM (minimal — just a date header)
- `agent_notify.py`: helper module for notifications
- Python venv at `~/agents/venv`
- That's it — very barebones

### What IMPLEMENTATION.md Says
NUC-2 is described as "Python Agents, Scrapers, Syncthing" but the implementation guide is vague on specifics beyond the journal bot.

### User's Specific Questions
1. What should NUC-2 actually do beyond journal_bot?
2. What do we integrate with Khoj?
3. Can Khoj automations/agents be integrated with delegation to NUC-2?

### Research Needed
- **Khoj automations API**: Khoj has an automations feature (scheduled queries, recurring reports). Investigate whether these can trigger external scripts or delegate to NUC-2.
- **Khoj agents API**: Khoj supports custom agents. Can an agent be configured to call out to NUC-2 for compute-heavy tasks?
- **Practical automation ideas for NUC-2:**
  - Web scrapers that feed content into the brain folder (Syncthing propagates to Khoj)
  - Summarization agents (pull from Khoj search, run through Ollama on Mac Mini, write results back)
  - RSS/feed ingestion into brain
  - Periodic knowledge graph or index maintenance
  - More sophisticated journal bot (daily summaries, weekly reviews using LLM)

### How to Investigate
```bash
# Check Khoj API endpoints
curl -s http://nuc-1.local:42110/api/ | python3 -m json.tool

# Check Khoj automations
curl -s http://nuc-1.local:42110/api/automations

# Check what's on NUC-2
ssh nuc-2 'ls -la ~/agents/ && pip list 2>/dev/null'

# Check Khoj version for feature availability
ssh nuc-1 'docker exec brain_khoj pip show khoj-assistant 2>/dev/null'
```

---

## System Topology (Current)

| Host | IP | Role | Key Services | Backup |
|------|----|------|-------------|--------|
| Mac Mini | m1-mini.local | Inference | Ollama (llama3.2, nomic-embed-text) | — |
| NUC-1 | nuc-1.local | Librarian | Khoj (HTTP on :42110, no TLS), Postgres, Syncthing | — |
| NUC-2 | nuc-2.local | Automation | Syncthing, journal_bot.py, Python venv | — |
| NUC-3 | nuc-3.local | Storage Hub | Syncthing (Docker, introducer), Restic, rclone | Local (3 AM) + pCloud (3:30 AM) |

### NUC-3 Crontab
```
* * * * * /home/earchibald/monitor_docker.sh brain_sync
0 3 * * * /home/earchibald/backup_brain.sh
30 3 * * * /home/earchibald/sync_to_pcloud.sh
```

### Access Notes
- All NUCs accessible via `ssh nuc-1`, `ssh nuc-2`, `ssh nuc-3` (passwordless SSH)
- All NUCs have passwordless sudo for `earchibald`
- Khoj web UI: `http://nuc-1.local:42110` or `http://nuc-1.local:42110` (HTTP only, not HTTPS)
- Khoj runs in `--anonymous-mode`
- Notification topic: `omnibus-brain-notifications-v3` via ntfy.sh

### Key Passwords
- Restic (both local and pCloud repos): `res-2026-pwd`
- Stored in `~/.restic-pcloud-password` on NUC-3 for pCloud repo
- Local Restic repo password storage location: unknown (works from cron but not found in any config file — investigate if needed)
