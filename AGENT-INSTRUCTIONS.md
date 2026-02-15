# **AGENT-INSTRUCTIONS.md: Current Working State and Context**

## **1. Overview**

This document codifies the current working state of the distributed AI knowledge mesh project, including all implementation details, configurations, and decisions made during the setup process. It serves as a comprehensive handover document for another agent to seamlessly pick up and continue development or maintenance.

## **2. Current Implemented State Summary**

The following components have been successfully set up and configured:

*   **Mac Mini (Inference):** Ollama is installed and running, serving `llama3.1:8b` and `nomic-embed-text` models.
*   **NUC-1 (Orchestrator/Scheduler):** Transitioning from "Librarian" role to orchestration hub. Currently runs semantic search service (replacing Khoj), Syncthing for brain folder sync, and will host workflow scheduling, research automation pipelines, and agent coordination. Designed to run unattended workflows, manage multi-step research projects, and coordinate agent execution across the cluster.
*   **NUC-2 (Automation):** Syncthing is installed and configured to sync the `/home/earchibald/brain` folder. A Python environment is set up, along with a daily journaler agent (`journal_bot.py`) that creates daily notes. Runs the interactive Slack bot agent. Notification handling for script errors is integrated.
*   **NUC-3 (Storage Hub):** Docker and Docker Compose are installed, running a Syncthing container configured as an introducer node. Restic is installed, and a backup script (`backup_brain.sh`) with error notifications is set up via cron (Restic repository requires manual initialization). Syncthing is configured to sync the `/home/earchibald/brain` folder with NUC-1 and NUC-2.
*   **Notification System:** A central notification system using `ntfy.sh` has been implemented across all NUCs for critical alerts, integrated with `systemd` services, Docker container health checks, and custom scripts. A modular Python hook (`agent_notify.py`) is available for agent-based notifications.

## **3. Host-Specific Configurations**

### **3.1. NUC-1 (Orchestrator/Scheduler)**

*   **IP Address:** nuc-1.local
*   **SSH Access:** Configured for passwordless SSH for `earchibald` user.
*   **Sudo Rights:** `earchibald` has passwordless `sudo`.
*   **Software:** Docker, Docker Compose, Syncthing.
*   **Role:** Orchestration hub for workflows, research automation, scheduled agent execution, and semantic search services.
*   **Intended Responsibilities:**
    *   Workflow scheduling and coordination (cron-based and event-driven)
    *   Research project automation (multi-step pipelines)
    *   Agent driver (spawn and monitor agents across cluster)
    *   Semantic search service (ChromaDB-based, replacing Khoj)
    *   Integration glue between services (Slack, LLM, brain storage)
*   **`docker-compose.yml` (`~/docker-compose.yml`):**
    ```yaml
    services:
      db:
        image: pgvector/pgvector:pg16
        container_name: brain_db
        restart: unless-stopped
        ports:
          - "5432:5432"
        environment:
          - POSTGRES_DB=khoj
          - POSTGRES_USER=khoj
          - POSTGRES_PASSWORD=internal_secret_db_pass
        volumes:
          - db_data:/var/lib/postgresql/data
        shm_size: 1g
        healthcheck:
          test: ["CMD-SHELL", "pg_isready -U khoj"]
          interval: 10s
          timeout: 5s
          retries: 5

      khoj:
        image: ghcr.io/khoj-ai/khoj:latest
        container_name: brain_khoj
        restart: unless-stopped
        depends_on:
          db:
            condition: service_healthy
        network_mode: host
        command: ["--anonymous-mode", "--host", "0.0.0.0", "--port", "42110"]
        volumes:
          - /home/earchibald/brain:/app/brain
          - /home/earchibald/brain/khoj_config:/app/config
        environment:
          - POSTGRES_HOST=127.0.0.1
          - POSTGRES_PORT=5432
          - POSTGRES_USER=khoj
          - POSTGRES_PASSWORD=internal_secret_db_pass
          - POSTGRES_DB=khoj
          - KHOJ_SEARCH_ENGINE=postgres
          - KHOJ_ADMIN_EMAIL=eugene.archibald@gmail.com
          - KHOJ_ADMIN_PASSWORD=some_secure_password
          - KHOJ_DJANGO_SECRET_KEY=long_random_secret_key_here
          - KHOJ_CONTENT_DIRECTORIES=/app/brain
          - KHOJ_CONTENT_TYPES=markdown,pdf,text
          - OPENAI_API_BASE=http://m1-mini.local:11434/v1
          - OPENAI_API_KEY=any_string
          - OLLAMA_MODEL_NAME=llama3.2
          - KHOJ_EMBEDDING_MODEL=nomic-embed-text
          - KHOJ_DOMAIN=nuc-1.local
          - KHOJ_PORT=42110
          - KHOJ_NO_HTTPS=true
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:42110"]
          interval: 1m
          timeout: 10s
          retries: 3
          start_period: 40s

    volumes:
      db_data:
    ```
*   **Syncthing Configuration (`~/.config/syncthing/config.xml`):**
    *   **Device ID:** `7ZLYPHB-JAKAPOC-PVTMDCL-3NMVSX4-3APZTOS-GR6US4T-CNNTVHT-32IZMAI`
    *   **API Key:** `YUVnktowkXxpUAEMEi3R4Dy4A7LSVfpa`
    *   **GUI Address:** `0.0.0.0:8384`
    *   **Folders:** Contains "default" and "Brain" (ID: `qknir-pp3n7`, Path: `/home/earchibald/brain`).
    *   **Connected Devices:** NUC-2 (`FLECAZT...`), NUC-3 (`C7E6E7M...`), Eugene's MBP (`5JNLT3O...`).
*   **Cron Jobs:**
    ```
    */30 * * * * curl -s http://localhost:42110/api/update?force=true > /dev/null 2>&1
    * * * * * /home/earchibald/monitor_docker.sh brain_khoj
    * * * * * /home/earchibald/monitor_docker.sh brain_db
    ```

### **Semantic Search Service Patterns (Derived from Khoj)**

These patterns were identified during Khoj deployment and should be preserved in any replacement service:

**Content Filtering & Indexing:**
- Support markdown (`.md`), plaintext (`.txt`), and PDF (`.pdf`) file types
- Use glob patterns for recursive directory matching: `/path/**/*.md`
- Handle file chunking for large documents (preserve context across chunks)
- Watch for file changes and re-index incrementally (debounced triggers)

**Search API:**
- Endpoint: `GET /api/search?q={query}&type={content_type}&limit={n}`
- Response format: `[{"entry": "snippet...", "file": "path/to/file.md", "score": 0.95}]`
- Default limit: 3-5 results
- Snippet length: ~200 characters per result
- Include source file path for citations

**Health & Monitoring:**
- Health check endpoint: `GET /api/health`
- Container/service health checks (1m interval, 10s timeout, 3 retries)
- Monitoring via cron or systemd for service failures
- Graceful degradation: Clients continue without search if service unavailable

**Indexing Cadence:**
- Periodic full re-index: Every 30 minutes (cron-based)
- Event-driven updates: File watcher with 5-10 second debounce
- Initial scan on service startup
- Progress logging for visibility

**Embeddings:**
- Model: `nomic-embed-text` (384 dimensions, efficient for semantic search)
- Generation: Via Ollama API (`/api/embeddings`)
- Batch processing for performance
- Persistent storage of vectors

**Configuration Lessons (from Khoj v1.42.10):**
- Environment variables alone may not suffice (Khoj required direct DB config)
- File-based or API-based configuration more reliable than env vars
- Document folder paths must match between config and runtime mounts
- Health checks essential for dependent services (use `depends_on` with conditions)

**Why Replace Khoj:**
- Heavy infrastructure (Postgres, pgvector, Django, Docker stack)
- Used <5% of features (only semantic search, not chat/LLM)
- 30-minute indexing delay (cron-based, not real-time)
- Configuration constraints (env vars not read, manual DB setup)
- Custom service provides: faster indexing, simpler deployment, full control

### **3.2. NUC-2 (Automation)**

*   **IP Address:** nuc-2.local
*   **SSH Access:** Configured for passwordless SSH for `earchibald` user.
*   **Sudo Rights:** `earchibald` has passwordless `sudo`.
*   **Software:** Syncthing, Python environment (`python3-venv`, `python3-pip`).
*   **Syncthing Configuration (`~/.config/syncthing/config.xml`):**
    *   **Device ID:** `FLECAZT-FP6N4YD-WTCJUD6-SBRFYEU-EDUHVH4-KGH4SLB-FSZV4VI-VFYH3QU`
    *   **API Key:** `SLrsbHYYm92vg7nfCDhukLbSm65n9WH4`
    *   **GUI Address:** `0.0.0.0:8384`
    *   **Folders:** Contains "default" and "Brain" (ID: `qknir-pp3n7`, Path: `/home/earchibald/brain`).
    *   **Connected Devices:** NUC-1 (`7ZLYPHB...`), NUC-3 (`C7E6E7M...`).
*   **Python Environment:**
    *   `~/agents/venv` created.
*   **`journal_bot.py` (`~/agents/journal_bot.py`):**
    ```python
    import os
    from datetime import datetime
    import subprocess

    def notify(title, message, priority="default"):
        """Sends a notification using the notify.sh script."""
        subprocess.run(["/usr/local/bin/notify.sh", title, message, priority])

    try:
        BRAIN_PATH = "/home/earchibald/brain/journal"
        DATE_STR = datetime.now().strftime("%Y-%m-%d")
        FILE_PATH = os.path.join(BRAIN_PATH, f"{DATE_STR}.md")

        if not os.path.exists(os.path.dirname(FILE_PATH)):
            os.makedirs(os.path.dirname(FILE_PATH))

        if not os.path.exists(FILE_PATH):
            with open(FILE_PATH, "w") as f:
                f.write(f"# Daily Log: {DATE_STR}

* Created automatically by NUC-2
")
    except Exception as e:
        notify("[NUC-2] Journal Bot Failed", f"The journal bot script failed with error: {e}", "high")
    ```
*   **Cron Jobs:**
    ```
    0 6 * * * /home/earchibald/agents/venv/bin/python /home/earchibald/agents/journal_bot.py
    ```
*   **`agent_notify.py` (`~/agents/agent_notify.py`):**
    ```python
    import subprocess

    def notify(title, message, priority="default"):
        """Sends a notification using the notify.sh script."""
        subprocess.run(["/usr/local/bin/notify.sh", title, message, priority])
    ```

### **3.3. NUC-3 (Storage Hub)**

*   **IP Address:** nuc-3.local
*   **SSH Access:** Configured for passwordless SSH for `earchibald` user.
*   **Sudo Rights:** `earchibald` has passwordless `sudo`.
*   **Software:** Docker, Docker Compose, Restic, Syncthing (in Docker).
*   **`docker-compose.yml` (`~/docker-compose.yml`):**
    ```yaml
    services:
      syncthing:
        image: syncthing/syncthing
        container_name: brain_sync
        hostname: nuc3-storage
        environment:
          - PUID=1000
          - PGID=1000
        volumes:
          - /home/earchibald/brain:/var/syncthing
        ports:
          - 8384:8384 # Web UI
          - 22000:22000/tcp # Transfer
          - 22000:22000/udp # Transfer
          - 21027:21027/udp # Discovery
        restart: unless-stopped
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:8384"]
          interval: 1m
          timeout: 10s
          retries: 3
          start_period: 40s
    ```
*   **Syncthing Configuration (inside `brain_sync` container at `/var/syncthing/config/config.xml`):**
    *   **Device ID:** `C7E6E7M-TWZW24Y-IYLBIUF-KUM44T4-S4JSK35-3Y7VJUA-PNS6EWL-K74UWQP`
    *   **API Key:** `yspxnLe5LXtTPYyTKdVppgM6iVcpjPzp`
    *   **GUI Address:** `0.0.0.0:8384`
    *   **Folders:** Contains "Brain" (ID: `qknir-pp3n7`, Path: `/var/syncthing/brain`).
    *   **Connected Devices:** NUC-1 (`7ZLYPHB...`), NUC-2 (`FLECAZT...`).
*   **`backup_brain.sh` (`~/backup_brain.sh`):**
    ```bash
    #!/bin/bash
    set -e

    function notify_on_error {
      /usr/local/bin/notify.sh "[NUC-3] Restic Backup Failed" "The Restic backup script failed." "high"
    }

    trap notify_on_error ERR

    restic -r /mnt/external_drive/brain_backup backup /home/earchibald/brain
    restic -r /mnt/external_drive/brain_backup forget --keep-daily 7 --keep-weekly 4
    ```
*   **Cron Jobs:**
    ```
    0 3 * * * /home/earchibald/backup_brain.sh
    30 3 * * * /home/earchibald/sync_to_pcloud.sh
    * * * * * /home/earchibald/monitor_docker.sh brain_sync
    ```
*   **Restic Setup (Local):**
    *   The `/mnt/external_drive` directory exists and is owned by `earchibald`.
    *   Restic repository initialized at `/mnt/external_drive/brain_backup`.
*   **Restic Setup (pCloud — offsite):**
    *   Restic repository initialized at `rclone:pcloud:/brain-backups` (repo ID `996d917e48`).
    *   Password file: `~/.restic-pcloud-password` (mode 600). Same password as local Restic repo.
*   **rclone / pCloud Configuration:**
    *   rclone config: `~/.config/rclone/rclone.conf` (mode 600, US region `api.pcloud.com`)
    *   `pcloud:/brain` — browsable mirror (rclone sync)
    *   `pcloud:/brain-backups` — encrypted Restic repository
*   **`sync_to_pcloud.sh` (`~/sync_to_pcloud.sh`):**
    ```bash
    #!/bin/bash
    set -e
    trap '/usr/local/bin/notify.sh "[NUC-3] pCloud Sync Failed" "The pCloud sync script failed." "high"' ERR

    # Browsable sync — mirrors brain folder to pCloud
    rclone sync /home/earchibald/brain/brain/ pcloud:/brain --transfers 4 --checkers 8

    # Encrypted backup via Restic
    export RESTIC_REPOSITORY="rclone:pcloud:/brain-backups"
    export RESTIC_PASSWORD_FILE="/home/earchibald/.restic-pcloud-password"
    restic backup /home/earchibald/brain/brain
    restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6
    ```

### **3.4. Mac Mini (Inference)**

*   **IP Address:** m1-mini.local
*   **Software:** Ollama.
*   **Models:** `llama3.2`, `nomic-embed-text` are pulled.
*   **Environment:** `OLLAMA_HOST=0.0.0.0` is set.

## **4. Network Configuration (Syncthing Cluster)**

The Syncthing cluster consists of `nuc-1`, `nuc-2`, and `nuc-3` with `nuc-3` acting as the introducer. The `/home/earchibald/brain` folder (mapped to `/var/syncthing/brain` in `nuc-3`'s container) is fully synced between all three NUCs.

*   **Syncthing Device IDs:**
    *   NUC-1: `7ZLYPHB-JAKAPOC-PVTMDCL-3NMVSX4-3APZTOS-GR6US4T-CNNTVHT-32IZMAI`
    *   NUC-2: `FLECAZT-FP6N4YD-WTCJUD6-SBRFYEU-EDUHVH4-KGH4SLB-FSZV4VI-VFYH3QU`
    *   NUC-3: `C7E6E7M-TWZW24Y-IYLBIUF-KUM44T4-S4JSK35-3Y7VJUA-PNS6EWL-K74UWQP`
*   **Shared Folder ID:** `qknir-pp3n7` (label: "Brain")

## **5. Notification System Configuration**

*   **`ntfy.sh` Topic:** `omnibus-brain-notifications-v3` (stored in `secrets.env`).
*   **`notify.sh` Script (`/usr/local/bin/notify.sh` on all NUCs):**
    ```bash
    #!/bin/bash
    TOPIC="omnibus-brain-notifications-v3"
    TITLE="$1"
    MESSAGE="$2"
    PRIORITY="$3"

    curl -s -X POST -H "Title: $TITLE" -H "Priority: $PRIORITY" -d "$MESSAGE" "https://ntfy.sh/$TOPIC"
    ```
*   **Integration Points:**
    *   **`systemd`:** `syncthing.service` on NUC-1 and NUC-2 (using `OnFailure=`).
    *   **Docker Healthchecks:** `monitor_docker.sh` (cron job) for `brain_khoj`, `brain_db` (NUC-1) and `brain_sync` (NUC-3).
    *   **Scripts:** `journal_bot.py` (NUC-2) and `backup_brain.sh` (NUC-3) include direct calls to `notify.sh` on error.
*   **`agent_notify.py` (Modular Hook, `~/agents/agent_notify.py` on NUC-2):**
    ```python
    import subprocess

    def notify(title, message, priority="default"):
        """Sends a notification using the notify.sh script."""
        subprocess.run(["/usr/local/bin/notify.sh", title, message, priority])
    ```

## **6. Agent Handoff Protocol**

To ensure seamless handoffs between agents and maintain continuity across work sessions, follow this protocol:

### **6.1 Handoff Document Maintenance**

**Core Principle:** After every significant task step, update the relevant handoff document. This keeps it always ready for another agent to pick up work at any moment.

**Why This Matters:**
- Eliminates "what was I doing?" discovery phase
- Creates audit trail of work transitions
- Enables asynchronous, turn-based work by multiple agents
- Maintains project continuity across sessions

### **6.2 Handoff Documents Architecture**

The project maintains multiple handoff documents by subsystem:

| Document | Location | Purpose | Updated When |
|----------|----------|---------|--------------|
| **Infrastructure & Config** | `AGENT-INSTRUCTIONS.md` | Host configs, credentials, services, infrastructure | Infrastructure changes, new hosts, service modifications |
| **Slack Bot Implementation** | `SLACK_AGENT_HANDOFF.md` | Complete Slack bot code, deployment, status | After each feature/fix, before deploying |
| **Work Sessions** | `SESSION_HANDOFF_[DATE].md` | Ad-hoc tasks, experiments, debugging sessions | At end of each work session |
| **Project Designs** | `SLACK_DESIGN.md`, etc | When creating new subsystems | During design/implementation |

### **6.3 What Must Be In Every Handoff Update**

After completing a significant task step, update the relevant handoff document with:

**1. Current Status (Vital)**
- What's ✅ working
- What's 🔄 in progress
- What's ❌ broken
- What's ⚠️ partially done

**2. Recent Changes (Vital)**
- Files modified (with line numbers if relevant)
- Deployments made (which hosts, what services)
- Infrastructure changes
- Security/credential updates

**3. Test Results**
- What was validated
- What failed and how to reproduce
- Performance metrics if relevant

**4. Next Steps (Vital)**
- What must happen next (ordered by priority)
- Estimated effort for each step
- Any blockers or unknowns

**5. Code Location & Context**
- Key files and their purposes
- Critical functions/methods
- Known technical debt or gotchas

**6. Deployment & Service State**
- What's running where (which NUC/host)
- Service status (systemd, Docker, etc)
- Recent restarts or errors

### **6.4 When to Update Handoff Documents**

Update immediately after:

| Trigger | Example |
|---------|---------|
| ✅ Feature implemented | "Added 'Working...' indicator to Slack bot" |
| ✅ Bug fixed | "Fixed message format mismatch (dict → Message)" |
| ✅ Deployed to production | "Deployed slack_agent.py to NUC-2 service" |
| ✅ Service started/modified | "Systemd service restarted, all health checks pass" |
| ✅ Infrastructure changed | "New NUC added, Syncthing configured" |
| ✅ Credentials updated | "SOPS secrets rotated, age key backed up" |
| ✅ Issue discovered | "Found message response delay, root cause identified" |
| ✅ Test results returned | "User testing: bot works but response too slow" |
| ✅ Switching subsystems | "Moving from Slack to database work" |
| ✅ Work session ending | "Stopping for the day, here's status for next agent" |

**DO NOT wait until another agent is needed. Update proactively after each step.**

### **6.5 SLACK_AGENT_HANDOFF.md as Template**

This document exemplifies the comprehensive handoff format:

**Sections it includes:**
1. **Current Status** - What works, what's in progress, what needs work
2. **Architecture** - System diagram, component overview
3. **File Inventory** - Each file listed with purpose, location, key methods
4. **Dependencies** - External services, Python packages, versions
5. **Deployment Procedure** - Step-by-step deployment instructions
6. **Testing** - How to validate changes work
7. **Known Issues & Fixes** - What's broken and solutions
8. **Troubleshooting Guide** - Common problems with solutions
9. **Next Steps** - Immediate, medium, and future priorities with code snippets
10. **Reference Docs** - Links to related files and APIs
11. **Success Metrics** - How to know if work succeeded

**Length:** Comprehensive but practical (typically 800-1500 lines for a complete subsystem)

### **6.6 Minimal Update Example**

For a small fix to existing functionality:

```markdown
## Recent Fix: Slack Bot Message Format

**Issue:** Bot crashes when calling LLM due to message type mismatch

**Root Cause:** slack_agent.py passed List[Dict] but llm_client.chat() expects List[Message]

**Solution Implemented:**
- Added `Message` to imports: `from clients.llm_client import OllamaClient, Message`
- Replaced dict construction with Message objects (lines 192-213)
- Deployed to NUC-2 via `scp agents/slack_agent.py nuc-2:/home/earchibald/agents/agents/`
- Restarted service: `sudo systemctl restart brain-slack-bot`

**Status:** ✅ Fixed and tested
- Service running: `● brain-slack-bot.service - Active: active (running)`
- Bot received test message and responded correctly
- All health checks passing

**Next Step:** Test multi-turn conversation memory (code already implemented)
```

### **6.7 File Naming Convention**

- **Active subsystem docs:** `{SUBSYSTEM}_HANDOFF.md` (e.g., `SLACK_AGENT_HANDOFF.md`)
- **Session docs:** `SESSION_HANDOFF_{DATE}.md` (e.g., `SESSION_HANDOFF_2026-02-14.md`)
- **Main reference:** Always `AGENT-INSTRUCTIONS.md`
- **Design docs:** `{SUBSYSTEM}_DESIGN.md` (e.g., `SLACK_DESIGN.md`)

### **6.8 Git Commit Integration**

Every handoff document update should be committed with clear messaging:

```bash
# After implementing a feature
git add SLACK_AGENT_HANDOFF.md
git commit -m "Handoff: Slack bot - Added 'Working...' indicator, ready for next session"

# After fixing a bug
git add SLACK_AGENT_HANDOFF.md
git commit -m "Handoff: Fixed message format bug, service running, multi-turn tests pending"

# At session end
git add SESSION_HANDOFF_2026-02-14.md
git commit -m "Session close: Database work complete, see handoff doc for next steps"
```

This creates an audit trail showing exactly when each piece of work was done and by whom (based on git history).

### **6.9 Document Update Checklist**

Before committing work and handing off to another agent, verify:

- [ ] **Status Section:** Clearly marks what works, what's broken, what's pending
- [ ] **Recent Changes:** Lists all files modified with specific line numbers
- [ ] **Test Results:** Documents what was tested and any failures
- [ ] **Next Steps:** Orders tasks by priority with estimated effort
- [ ] **Blockers:** Lists anything waiting on external resources
- [ ] **Code Location:** Points to exact files and line ranges for next steps
- [ ] **Deployment State:** Shows current service status and configuration
- [ ] **Git Commit:** Accompanying commit message explains the handoff

### **6.10 Cross-Project Handoff Example**

When moving work between major subsystems, create a mini-index in main `AGENT-INSTRUCTIONS.md`:

```markdown
## Current Work Status

| Subsystem | Status | Handoff Doc | Next Agent |
|-----------|--------|-------------|-----------|
| Slack Bot | 🔄 In Progress | SLACK_AGENT_HANDOFF.md | Add "Working..." indicator |
| Database | ✅ Complete | N/A | Ready for use |
| Backup System | ❌ Broken | SESSION_HANDOFF_2026-02-14.md | Debug Restic timeout |
```

This lets any agent quickly scan what needs work and where to find context.

### **6.11 Automation Opportunities**

Future improvements to consider:

- **Template Generator:** Script that creates `{SUBSYSTEM}_HANDOFF.md` with boilerplate
- **Structure Validator:** Verify handoff docs have required sections
- **Diff Summary:** Auto-generate "recent changes" section from git diffs
- **Pre-Deployment Hook:** Require handoff update before `git push`
- **Agent API:** Query current status of any subsystem programmatically

## **7. Annex: Outstanding Actions & Context History Reconciliation**

This section tracks any manual steps performed by the user, specific decisions made during the implementation process, or any known discrepancies to ensure all context from the interactive session is preserved.

*   **SSH Key Setup:** User manually set up SSH keys on all NUCs.
*   **Passwordless Sudo:** User manually configured passwordless `sudo` for `earchibald` on NUC-1, NUC-2, and NUC-3.
*   **`secrets.env` Update:** The `NTFY_TOPIC` (`omnibus-brain-notifications-v3`) was added to `secrets.env` by the agent using `sops -d -i secrets.env`, `echo "..." >> secrets.env`, and `sops -e -i secrets.env`.
*   **Restic Repository Initialization:** User manually initialized the Restic repository on NUC-3 by running `restic init --repo /mnt/external_drive/brain_backup` and setting a password. This required the agent to first create `/mnt/external_drive` and set its ownership.
*   **Syncthing Introducer Functionality:** The introducer functionality for Syncthing (NUC-3) did not automatically connect NUC-1 and NUC-2 as expected. Manual intervention was required to add NUC-1 to NUC-2, and NUC-2 to NUC-1, and to explicitly share the "Brain" folder from NUC-1 to NUC-2 and NUC-3.
*   **Syncthing `autoAcceptFolders` issue:** Despite setting `autoAcceptFolders=true` for devices, folders were not auto-accepted due to path conflicts or missing `.stfolder` markers. Manual addition of folders via API and creation of `.stfolder` were necessary.
*   **Khoj Database Connection Issue:** The `brain_khoj` container initially failed to connect to `brain_db` due to a timing issue. This was resolved by adding a `healthcheck` to the `db` service and making `khoj` `depends_on` the `db` service with `condition: service_healthy`.
*   **Syncthing on NUC-1:** Syncthing was already installed on NUC-1, so no installation was performed.
*   **Syncthing on NUC-2:** `systemctl --user enable-linger earchibald` was needed to ensure Syncthing service persistence.
