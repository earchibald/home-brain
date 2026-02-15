# Homepage Implementation Plan

This document outlines the steps to deploy and configure Homepage on nuc-1.local.

## 1. Research

*   [x] Read the documentation at https://gethomepage.dev to understand its features and deployment methods.

## 2. Planning

*   [x] Create a deployment plan.

## 3. Implementation

*   [x] SSH into nuc-1.local.
*   [x] Verify Docker installation.
*   [x] Create `docker-compose.yml` for Homepage.
*   [x] Create Homepage configuration files (`services.yaml`, `widgets.yaml`, `bookmarks.yaml`, `settings.yaml`).
*   [x] Deploy Homepage using `docker-compose up -d`.
*   [ ] Verify the deployment by accessing the web interface.

## 4. Configuration Details

### Services

We will monitor the following services:

*   **nuc-1.local**:
    *   Homepage
    *   Portainer
    *   Vaultwarden
*   **nuc-2.local**:
    *   Agent Framework
*   **nuc-3.local**:
    *   Agent Framework
*   **m1-mini.local**:
    *   Agent Framework

### Widgets

*   Clock
*   Weather
*   Search
*   Caddy

### Bookmarks

*   Links to internal services and documentation.

## 5. Notifications

*   [x] Add `ntfy` notifications for when the homepage docker comes up.
*   [x] Set up a `crontab` job to monitor the homepage service once a minute and send an `ntfy` notification if it's down.
