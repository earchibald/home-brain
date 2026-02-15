# **Project Omnibus: The Semantic Brain Architecture (v3.0) - E2E Implementation Guide**

This document provides a complete end-to-end guide for setting up the 6-node distributed AI knowledge mesh.

## **1. Prerequisites**

*   **SSH Access:** Ensure you have SSH access to all NUCs (`nuc-1.local`, `nuc-2.local`, `nuc-3.local`) and the Mac Mini (`m1-mini.local`) as the `earchibald` user.
*   **Sudo Rights:** The `earchibald` user must have passwordless `sudo` rights on all NUCs. You can set this up by running the following command on each NUC:
    ```bash
    echo "earchibald ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/earchibald
    ```

## **2. System Topology**

| Host         | Role           | IP            | Key Services                 |
| :----------- | :------------- | :------------ | :--------------------------- |
| **NUC-1**    | **Librarian**  | nuc-1.local | Khoj (RAG App), Postgres, Syncthing |
| **NUC-2**    | **Automation** | nuc-2.local | Python Agents, Scrapers, Syncthing |
| **NUC-3**    | **Storage Hub**| nuc-3.local | Syncthing (Introducer), Restic |
| **Mac Mini** | **Inference**  | m1-mini.local  | Ollama (Llama 3.2)           |
| **Laptop**   | **Workstation**| *DHCP*        | Local Agent, Just CLI, Syncthing |
| **Mobile**   | **Secondary**  | *DHCP*        | Khoj Client                  |


## **3. Mac Mini: Inference Implementation**

**Role:** The GPU/NPU provider.

1.  **Install Ollama:**
    ```bash
    brew install ollama
    ```
2.  **Pull Models:**
    ```bash
    ollama pull llama3.2
    ollama pull nomic-embed-text
    ```
3.  **Serve:** Ensure `OLLAMA_HOST=0.0.0.0` is set in the environment so other nodes can reach it.
4.  **Verification:**
    ```bash
    curl http://localhost:11434
    ```
    You should see "Ollama is running".

## **4. NUC-3: Storage Hub & Syncthing Introducer**

**Role:** The Central Source of Truth and Syncthing Introducer.

1.  **Install Docker:**
    ```bash
    sudo apt update
    sudo apt install -y docker.io docker-compose-v2
    sudo usermod -aG docker earchibald
    ```
    **Note:** You will need to log out and log back in for the group change to take effect.

2.  **Create Docker Compose file:**
    Create a `~/docker-compose.yml` file with the following content:
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
    ```

3.  **Start Syncthing:**
    ```bash
    mkdir -p /home/earchibald/brain
    sudo chown earchibald:earchibald /home/earchibald/brain
    docker compose up -d
    ```

4.  **Install Restic:**
    ```bash
    sudo apt install -y restic
    ```

5.  **Create Backup Script:**
    Create a `~/backup_brain.sh` file:
    ```bash
    #!/bin/bash
    restic -r /mnt/external_drive/brain_backup backup /home/earchibald/brain
    restic -r /mnt/external_drive/brain_backup forget --keep-daily 7 --keep-weekly 4
    ```
    Make it executable:
    ```bash
    chmod +x ~/backup_brain.sh
    ```

6.  **Set up Cron Job:**
    ```bash
    echo "0 3 * * * /home/earchibald/backup_brain.sh" | crontab -
    ```

7.  **Manual Step: Initialize Restic Repo:**
    *   Ensure an external drive is mounted at `/mnt/external_drive`.
    *   Run the following command and set a password for the repository:
        ```bash
        restic init --repo /mnt/external_drive/brain_backup
        ```

## **5. NUC-2: Automation Implementation**

**Role:** The Worker Bee.

1.  **Install Python Environment:**
    ```bash
    sudo apt update
    sudo apt install -y python3-venv python3-pip
    mkdir -p ~/agents
    python3 -m venv ~/agents/venv
    ```

2.  **Create Journaler Agent:**
    Create a `~/agents/journal_bot.py` file:
    ```python
    import os
    from datetime import datetime

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
    ```

3.  **Set up Cron Job:**
    ```bash
    echo "0 6 * * * /home/earchibald/agents/venv/bin/python ~/agents/journal_bot.py" | crontab -
    ```

## **6. NUC-1: Librarian Implementation**

**Role:** The AI Search Engine.

*   The `docker-compose.yml` for Khoj and Postgres should already be present on this machine. If not, here is the content:
    ```yaml
    services:
      db:
        image: pgvector/pgvector:pg16
        container_name: brain_db
        restart: unless-stopped
        environment:
          - POSTGRES_DB=khoj
          - POSTGRES_USER=khoj
          - POSTGRES_PASSWORD=internal_secret_db_pass
        volumes:
          - db_data:/var/lib/postgresql/data
        shm_size: 1g

      khoj:
        image: ghcr.io/khoj-ai/khoj:latest
        container_name: brain_khoj
        restart: unless-stopped
        depends_on:
          - db
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

    volumes:
      db_data:
    ```
*   **Start Khoj and Postgres:**
    ```bash
    docker compose up -d
    ```
*   **Set up Cron Job for re-indexing:**
    ```bash
    echo "*/30 * * * * curl -s http://localhost:42110/api/update?force=true > /dev/null 2>&1" | crontab -
    ```

## **7. Syncthing Cluster Configuration**

This section details how to connect all three NUCs into a single Syncthing cluster.

1.  **Install Syncthing on NUC-1 and NUC-2:**
    ```bash
    ssh nuc-1.local 'sudo apt install -y syncthing'
    ssh nuc-2.local 'sudo apt install -y syncthing'
    ```

2.  **Enable and Start Syncthing Services:**
    ```bash
    ssh nuc-1.local 'loginctl enable-linger earchibald && systemctl --user enable --now syncthing.service'
    ssh nuc-2.local 'loginctl enable-linger earchibald && systemctl --user enable --now syncthing.service'
    ```

3.  **Configure Remote GUI Access:**
    For both `nuc-1.local` and `nuc-2.local`, modify the Syncthing `config.xml` to allow remote access.
    ```bash
    ssh nuc-1.local "sed -i 's/127.0.0.1:8384/0.0.0.0:8384/' ~/.config/syncthing/config.xml"
    ssh nuc-2.local "sed -i 's/127.0.0.1:8384/0.0.0.0:8384/' ~/.config/syncthing/config.xml"
    ```
    Then, restart the services:
    ```bash
    ssh nuc-1.local 'systemctl --user restart syncthing.service'
    ssh nuc-2.local 'systemctl --user restart syncthing.service'
    ```

4.  **Connect Devices:**
    Use the Syncthing Web UIs to connect all devices and share the "brain" folder.
    *   **nuc-1:** `http://nuc-1.local:8384`
    *   **nuc-2:** `http://nuc-2.local:8384`
    *   **nuc-3:** `http://nuc-3.local:8384`

    **Note:** It is recommended to perform this step manually through the Web UI for the first-time setup.

## **8. Final Verification**

1.  **Create a test file:**
    ```bash
    ssh nuc-2.local 'echo "Hello, Semantic Brain!" > /home/earchibald/brain/test.md'
    ```
2.  **Check for the file on other NUCs:**
    Wait a few seconds, then run:
    ```bash
    ssh nuc-1.local 'cat /home/earchibald/brain/test.md'
    ssh nuc-3.local 'cat /home/earchibald/brain/test.md'
    ```
3.  **Search for the file in Khoj:**
    *   Go to `http://nuc-1.local:42110`.
    *   Search for "Hello, Semantic Brain!".
