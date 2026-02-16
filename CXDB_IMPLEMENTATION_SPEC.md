# CXDB Integration & "Filesystem Technique" Specification

## 1. Project Context
We are upgrading a Python-based Slack bot (running on a distributed NUC cluster) to use **CXDB (AI Context Store)**.
*   **Current State**: Conversation history is stored in linear JSON files (`clients/conversation_manager.py`).
*   **Goal**: Integrate `cxdb` to enable DAG-based history (branching) and support the "Filesystem Technique" (tracking file changes as graph nodes).
*   **Constraint**: Use the `cxdb` HTTP API (port 9010) as no Python SDK exists.

## 2. Infrastructure (NUC-1)
We must technically enable the `cxdb` service on the orchestration node (NUC-1).

**Target File**: `~/docker-compose.yml` on NUC-1.
**Service Definition**:
```yaml
  cxdb:
    image: cxdb/cxdb:latest
    container_name: brain_cxdb
    restart: unless-stopped
    ports:
      - "9009:9009" # Binary protocol
      - "9010:9010" # HTTP API
    volumes:
      - /home/earchibald/brain/cxdb_data:/data
    environment:
      - CXDB_DATA_DIR=/data
```

## 3. Python Implementation Requirements

### A. `clients/cxdb_client.py` (New File)
Implement a wrapper for the `cxdb` HTTP API.

**Base URL**: `http://nuc-1.local:9010` (configurable)
**Key Methods**:
1.  `create_context(base_turn_id: Optional[int] = 0) -> int`
    *   `POST /v1/contexts/create`
    *   Returns: `context_id` (int)
2.  `append_turn(context_id: int, role: str, content: str, model: str = None) -> Dict`
    *   `POST /v1/contexts/{id}/append`
    *   Payload:
        ```json
        {
          "type_id": "chat.message",
          "type_version": 1,
          "data": { "role": "user", "content": "..." }
        }
        ```
    *   Returns: Turn object (`turn_id`, `turn_hash`).
3.  `get_turns(context_id: int, limit: int = 100) -> List[Dict]`
    *   `GET /v1/contexts/{id}/turns`

### B. `clients/conversation_manager.py` (Update)
Refactor `ConversationManager` to write to *both* local disk (backup) and `cxdb` (primary logic).

1.  **Initialization**:
    *   Accept `cxdb_client` instance.
    *   Maintain a mapping of `slack_thread_ts` -> `cxdb_context_id`.
    *   *Storage*: Store this mapping in a simple JSON index (`brain/cxdb_map.json`) or inside the existing conversation file metadata.
2.  **`save_message`**:
    *   If `thread_ts` is not mapped, call `cxdb.create_context()`.
    *   Call `cxdb.append_turn()`.
    *   Save to local JSON file (update existing logic to include `cxdb_turn_id` in the message metadata).
3.  **`load_conversation`**:
    *   Try fetching from `cxdb` first.
    *   Fallback to local file if `cxdb` is unreachable.

### C. `agents/slack_agent.py` (Update)
1.  Initialize `CxdbClient` in `__init__`.
2.  Pass it to `ConversationManager`.

## 4. "Filesystem Technique" Foundation
We want to track *file operations* as turns in the DAG.
*   Add method `log_file_event(context_id: int, file_path: str, operation: str)` to `CxdbClient`.
*   Payload Type: `filesystem.event`
*   Data: `{"path": "/brain/...", "op": "write", "timestamp": "..."}`

## 5. Development Plan
1.  **Install**: Update `docker-compose.yml` on NUC-1 (via ssh command or manual instruction script).
2.  **Code**: Create `cxdb_client.py` and unit tests.
3.  **Integrate**: Modify `ConversationManager` and `SlackAgent`.
4.  **Verify**: Ensure bot still replies and data appears in `cxdb`.

## 6. API Reference (CXDB)
*   `GET /v1/contexts` - List contexts
*   `POST /v1/contexts/create` - `{"base_turn_id": "0"}`
*   `POST /v1/contexts/{id}/append` - `{"type_id": "...", "data": {...}}`
*   `GET /v1/contexts/{id}/turns`
