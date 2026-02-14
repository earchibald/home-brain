# **AGENT-INSTRUCTIONS.md: Current Working State and Context**

## **1. Overview**

This document codifies the current working state of the distributed AI knowledge mesh project, including all implementation details, configurations, and decisions made during the setup process. It serves as a comprehensive handover document for another agent to seamlessly pick up and continue development or maintenance.

## **2. Current Implemented State Summary**

The following components have been successfully set up and configured:

*   **Mac Mini (Inference):** Ollama is installed and running, serving `llama3.2` and `nomic-embed-text` models.
*   **NUC-1 (Librarian):** Khoj (with Postgres) is installed via Docker Compose, set up for indexing the `/home/earchibald/brain` folder. Syncthing is installed and configured to sync the `/home/earchibald/brain` folder with NUC-2 and NUC-3. Docker container health checks and a cron job for Khoj re-indexing are in place.
*   **NUC-2 (Automation):** Syncthing is installed and configured to sync the `/home/earchibald/brain` folder. A Python environment is set up, along with a daily journaler agent (`journal_bot.py`) that creates daily notes. Notification handling for script errors is integrated.
*   **NUC-3 (Storage Hub):** Docker and Docker Compose are installed, running a Syncthing container configured as an introducer node. Restic is installed, and a backup script (`backup_brain.sh`) with error notifications is set up via cron (Restic repository requires manual initialization). Syncthing is configured to sync the `/home/earchibald/brain` folder with NUC-1 and NUC-2.
*   **Notification System:** A central notification system using `ntfy.sh` has been implemented across all NUCs for critical alerts, integrated with `systemd` services, Docker container health checks, and custom scripts. A modular Python hook (`agent_notify.py`) is available for agent-based notifications.

## **3. Host-Specific Configurations**

### **3.1. NUC-1 (Librarian)**

*   **IP Address:** 192.168.1.195
*   **SSH Access:** Configured for passwordless SSH for `earchibald` user.
*   **Sudo Rights:** `earchibald` has passwordless `sudo`.
*   **Software:** Docker, Docker Compose, Syncthing.
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
          - OPENAI_API_BASE=http://192.168.1.58:11434/v1
          - OPENAI_API_KEY=any_string
          - OLLAMA_MODEL_NAME=llama3.2
          - KHOJ_EMBEDDING_MODEL=nomic-embed-text
          - KHOJ_DOMAIN=192.168.1.195
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

### **3.2. NUC-2 (Automation)**

*   **IP Address:** 192.168.1.196
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

*   **IP Address:** 192.168.1.197
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

*   **IP Address:** 192.168.1.58
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

## **6. Annex: Outstanding Actions & Context History Reconciliation**

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
