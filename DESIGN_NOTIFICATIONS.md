# **Design Document: Ntfy.sh Notification System**

This document outlines the design for a centralized notification system for the distributed AI knowledge mesh, using `ntfy.sh` as the notification gateway.

## **1. Goals**

*   **Proactive Monitoring:** Automatically notify the user of system failures, errors, and important events.
*   **Centralized Notifications:** Consolidate notifications from all services into a single, user-friendly stream.
*   **Actionable Information:** Provide clear and concise notification content that enables the user to quickly understand the issue and take action if necessary.
*   **Modularity and Extensibility:** Design a system that is easy to extend with new notification triggers and can be integrated with future agent-based workflows.

## **2. Architecture**

The notification system will be based on a simple, decentralized architecture where each service is responsible for sending its own notifications to a shared `ntfy.sh` topic.

*   **`ntfy.sh` Topic:** A private, randomly generated `ntfy.sh` topic (`omnibus-brain-notifications-v3`) will be used as the central notification channel. This topic is stored in the `secrets.env` file.
*   **Notification Script:** A simple shell script, `notify.sh`, will be created and placed in `/usr/local/bin` on each NUC. This script encapsulates the logic for sending notifications to the `ntfy.sh` topic.
*   **Service Integration:** Each service will be configured to call the `notify.sh` script with a message when a notification-worthy event occurs.

## **3. Notification Triggers**

The following events will trigger notifications:

*   **Systemd Service Failures:**
    *   `syncthing.service` on NUC-1 and NUC-2 will use `OnFailure=notify.sh` to send notifications.
*   **Docker Container Health:**
    *   A `monitor_docker.sh` script, run via cron, will check the health of `brain_khoj` (NUC-1) and `brain_sync` (NUC-3) containers. If a container is unhealthy, it will send a notification using `notify.sh`.
    *   `brain_db` (NUC-1) container health is also monitored by `monitor_docker.sh`.
*   **Application Errors:**
    *   Errors in the `journal_bot.py` script (NUC-2) will trigger notifications.
    *   Errors during the Restic backup process (NUC-3) will trigger notifications.
*   **Agent-based Notifications:**
    *   A modular hook (`agent_notify.py`) is provided for agents to send notifications when they require the user's attention.

## **4. Notification Content**

Notifications will be formatted to provide clear and concise information.

*   **Title:** The title of the notification will indicate the source of the event (e.g., `[NUC-1]`, `[NUC-2]`, `[NUC-3]`, `[KHOJ]`, `[AGENT]`).
*   **Message:** The message body will contain a brief description of the event.
*   **Priority:** `ntfy.sh` priorities will be used to indicate the severity of the event (e.g., `high` for critical failures, `default` for informational messages).

## **5. `ntfy.sh` Integration**

*   **Topic:** `omnibus-brain-notifications-v3` is the topic used.
*   **`notify.sh` Script:** The `notify.sh` script uses `curl` to send `POST` requests to `https://ntfy.sh/$TOPIC`.

    ```bash
    #!/bin/bash
    TOPIC="omnibus-brain-notifications-v3"
    TITLE="$1"
    MESSAGE="$2"
    PRIORITY="$3"

    curl -s -X POST -H "Title: $TITLE" -H "Priority: $PRIORITY" -d "$MESSAGE" "https://ntfy.sh/$TOPIC"
    ```

## **6. Agent Hook**

A simple and modular hook is provided for agents to send notifications. This is implemented as a Python function that calls the `notify.sh` script.

*   **`agent_notify.py`:** A Python module with a `notify()` function is available in `~/agents` on NUC-2.

    ```python
    import subprocess

    def notify(title, message, priority="default"):
        """Sends a notification using the notify.sh script."""
        subprocess.run(["/usr/local/bin/notify.sh", title, message, priority])
    ```
*   **Usage:** Agents can import and call this function to send notifications.
    ```python
    from agent_notify import notify

    # ... agent logic ...
    notify("[AGENT] Action Required", "Please review the latest summary.", "high")
    ```
