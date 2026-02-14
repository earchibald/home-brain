# **Implementation Plan: Ntfy.sh Notification System**

This document outlines the step-by-step plan to implement the `ntfy.sh` notification system as described in `DESIGN_NOTIFICATIONS.md`.

## **1. Generate `ntfy.sh` Topic**

1.  **Generate Topic:** A random topic name was generated: `omnibus-brain-notifications-v3`.
2.  **Update `secrets.env`:** The agent updated the `secrets.env` file to include `NTFY_TOPIC=omnibus-brain-notifications-v3`.

## **2. Create and Distribute `notify.sh` Script**

1.  **Create Script:** A `notify.sh` script with the following content was created:
    ```bash
    #!/bin/bash
    TOPIC="omnibus-brain-notifications-v3"
    TITLE="$1"
    MESSAGE="$2"
    PRIORITY="$3"

    curl -s -X POST -H "Title: $TITLE" -H "Priority: $PRIORITY" -d "$MESSAGE" "https://ntfy.sh/$TOPIC"
    ```
2.  **Distribute and Set Permissions:**
    *   The `notify.sh` script was copied to `/usr/local/bin` on `nuc-1`, `nuc-2`, and `nuc-3`.
    *   The script was made executable on all three NUCs: `sudo chmod +x /usr/local/bin/notify.sh`.

## **3. Integrate with `systemd` Services**

1.  **Modify Service Files:** For `syncthing.service` on `nuc-1` and `nuc-2`, the `OnFailure=` directive was added to the `[Unit]` section:
    ```ini
    [Unit]
    Description=Syncthing - Open Source Continuous File Synchronization
    Documentation=man:syncthing(1)
    OnFailure=notify.sh "[%H] Syncthing Failed" "The Syncthing service has failed." "high"
    ...
    ```
2.  **Reload `systemd`:**
    ```bash
    ssh nuc-1.local 'systemctl --user daemon-reload'
    ssh nuc-2.local 'systemctl --user daemon-reload'
    ```

## **4. Integrate with Docker Containers**

1.  **Modify `docker-compose.yml` for `nuc-1` (Khoj):**
    *   Added a `healthcheck` to the `db` service:
        ```yaml
        healthcheck:
          test: ["CMD-SHELL", "pg_isready -U khoj"]
          interval: 10s
          timeout: 5s
          retries: 5
        ```
    *   Modified `depends_on` for the `khoj` service to wait for `db` to be healthy:
        ```yaml
        depends_on:
          db:
            condition: service_healthy
        ```
    *   Added a `healthcheck` to the `khoj` service:
        ```yaml
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:42110"]
          interval: 1m
          timeout: 10s
          retries: 3
          start_period: 40s
        ```

2.  **Modify `docker-compose.yml` for `nuc-3` (Syncthing):**
    *   Added a `healthcheck` to the `syncthing` service:
        ```yaml
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:8384"]
          interval: 1m
          timeout: 10s
          retries: 3
          start_period: 40s
        ```

3.  **Create Monitoring Script:**
    A new script, `monitor_docker.sh`, was created and placed on `nuc-1` and `nuc-3` to check the health of the containers and send a notification if a container is unhealthy.
    ```bash
    #!/bin/bash
    CONTAINER_NAME="$1"
    HOST_NAME=$(hostname)

    if [ "$(docker inspect -f '{{.State.Health.Status}}' $CONTAINER_NAME)" = "unhealthy" ]; then
      /usr/local/bin/notify.sh "[$HOST_NAME] Docker Alert" "Container $CONTAINER_NAME is unhealthy." "high"
    fi
    ```

4.  **Set up Cron Job for Monitoring:**
    *   On `nuc-1`:
        ```
        * * * * * /home/earchibald/monitor_docker.sh brain_khoj
        * * * * * /home/earchibald/monitor_docker.sh brain_db
        ```
    *   On `nuc-3`:
        ```
        * * * * * /home/earchibald/monitor_docker.sh brain_sync
        ```

## **5. Integrate with Scripts**

1.  **Modify `journal_bot.py`:**
    The file creation logic was wrapped in a `try...except` block, and `notify.sh` is called on failure.
2.  **Modify `backup_brain.sh`:**
    `set -e` and a `trap` were added to the script to call `notify.sh` on error.

## **6. Create Agent Hook**

1.  **Create `agent_notify.py`:**
    ```python
    import subprocess

    def notify(title, message, priority="default"):
        """Sends a notification using the notify.sh script."""
        subprocess.run(["/usr/local/bin/notify.sh", title, message, priority])
    ```
2.  **Place Module:** The module was placed in `~/agents` on `nuc-2`.

## **7. Create User Guide**

A `USER_GUIDE_NOTIFICATIONS.md` file was created with detailed instructions for the user on how to subscribe to the `ntfy.sh` topic on their phone.
