# User Guide: The Semantic Brain

This document explains how to use your distributed AI knowledge mesh.

## **1. Quickstart: Your First Note**

1.  **Create a new note:**
    *   On any of the NUCs (`nuc-1`, `nuc-2`, or `nuc-3`), create a new markdown file inside the `~/brain` directory.
    *   For example, on `nuc-1`:
        ```bash
        echo "This is my first note about Large Language Models." > ~/brain/my_first_note.md
        ```

2.  **Wait for it to sync:**
    *   The file will be automatically synced to all other NUCs within a few seconds.

3.  **Search for it in Khoj:**
    *   Open your web browser and go to `http://nuc-1.local:42110`.
    *   In the search bar, type "Large Language Models".
    *   Your new note should appear in the search results.

## **2. How to Use the System**

### **Adding New Information**

*   Simply create, edit, or delete markdown (`.md`), text (`.txt`), or PDF (`.pdf`) files in the `~/brain` directory on any of the NUCs.
*   The system is designed to be "hands-off". Any changes you make will be automatically synced and indexed.

### **Searching Your Brain**

*   The primary interface for searching your knowledge base is the **Khoj Web UI**.
*   **URL:** `http://nuc-1.local:42110`
*   You can perform keyword-based searches or ask natural language questions.

### **The Daily Journal**

*   A new journal entry is automatically created for you every day at 6am in the `~/brain/journal` directory.
*   The file will be named with the current date (e.g., `2026-02-14.md`).
*   You can add your own notes to this file.

## **3. How It Works**

*   **Syncthing:** This is the core of the file synchronization. It ensures that the `~/brain` directory is identical across all three NUCs.
*   **Khoj:** This is your personal AI search engine. It automatically watches the `~/brain` directory for changes and indexes your notes, making them searchable.
*   **Ollama:** This provides the AI models (like Llama 3.2) that Khoj uses for its more advanced search features.

## **4. Checking System Status**

You can monitor the status of the various services using these commands:

*   **Check Khoj Logs:**
    ```bash
    ssh nuc-1.local "docker logs brain_khoj --tail 50"
    ```

*   **Check Syncthing Status (nuc-1):**
    ```bash
    ssh nuc-1.local 'curl -s -H "X-API-Key: YUVnktowkXxpUAEMEi3R4Dy4A7LSVfpa" http://localhost:8384/rest/system/status'
    ```

*   **Check Syncthing Status (nuc-2):**
    ```bash
    ssh nuc-2.local 'curl -s -H "X-API-Key: SLrsbHYYm92vg7nfCDhukLbSm65n9WH4" http://localhost:8384/rest/system/status'
    ```

*   **Check Syncthing Status (nuc-3):**
    ```bash
    ssh nuc-3.local 'docker exec brain_sync curl -s -H "X-API-Key: yspxnLe5LXtTPYyTKdVppgM6iVcpjPzp" http://localhost:8384/rest/system/status'
    ```
