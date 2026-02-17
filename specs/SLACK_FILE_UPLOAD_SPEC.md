# Feature Specification: Slack File Upload to Brain Index

## Overview

Enable users to add files to the brain index directly from Slack by either:
1. **Uploading files in DM** — Attach a file to a message sent to the bot
2. **Using a modal interface** — Through the `/index` modal, upload files to a specific directory

## User Stories

### US1: Upload via DM Message
As a user, I want to attach a file to a DM with the bot and have it saved to my brain folder and indexed.

**Acceptance Criteria:**
- When I send a message with a file attachment to the bot DM, the bot detects the file
- Bot shows a modal asking: "Where should I save this file?" with directory options
- User selects a target directory (can type a new path or select from recent/common directories)
- Bot downloads the file, saves it to the brain folder, and triggers indexing
- Bot confirms success with the file path and a link to search for it

### US2: Upload via /index Modal
As a user, I want to click "📤 Add File" in the `/index` dashboard modal and upload a file.

**Acceptance Criteria:**
- Dashboard shows "📤 Add File" button alongside existing Browse/Setup/Reindex buttons
- Clicking opens a stacked modal with:
  - File input (Slack's native file picker won't work in modals, so this requires a workaround)
  - Directory selector (dropdown or text input)
  - Optional: rename the file
- After submission, file is saved and indexed
- Success message with file path displayed

## Technical Design

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SLACK BOT (NUC-2)                         │
├─────────────────────────────────────────────────────────────────────┤
│  1. Detect file_shared or message_with_files event                 │
│  2. Download file from Slack (using existing file_handler.py)      │
│  3. Call semantic_search API to upload file                        │
│  4. Display success/failure modal                                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ POST /api/documents/upload
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   SEMANTIC SEARCH SERVICE (NUC-1)                   │
├─────────────────────────────────────────────────────────────────────┤
│  POST /api/documents/upload                                         │
│    - Receives: file_path (relative), content (bytes), content_type │
│    - Validates: gate permissions, file size, file type             │
│    - Saves file to brain_path/{file_path}                          │
│    - Triggers immediate indexing of file                           │
│    - Returns: {status, path, chunks}                               │
└─────────────────────────────────────────────────────────────────────┘
```

### API Endpoint: POST /api/documents/upload

**Request:**
```json
{
  "file_path": "notes/project-x/meeting-notes.md",
  "content": "<base64-encoded file content>",
  "content_type": "text/markdown",
  "overwrite": false
}
```

**Response (Success):**
```json
{
  "status": "uploaded",
  "path": "notes/project-x/meeting-notes.md",
  "size": 2048,
  "chunks": 3,
  "indexed": true
}
```

**Response (Error Cases):**
- 400: Missing required fields
- 403: Target directory is readonly (gate)
- 409: File already exists (if overwrite=false)
- 413: File too large (>10MB limit)
- 415: Unsupported file type

### Supported File Types for Upload

| Type | Extensions | Indexed | Notes |
|------|------------|---------|-------|
| Markdown | .md | ✅ | Primary knowledge format |
| Plain Text | .txt | ✅ | Simple notes |
| PDF | .pdf | ✅ | Documents (text extracted) |
| Images | .png, .jpg, .jpeg, .gif | ❌ | Stored but not indexed |
| Code | .py, .js, .ts, .go, .rs | ✅ | With syntax highlighting markers |

### Slack Client Changes

**New File: `slack_bot/file_uploader.py`**

```python
"""Handle file uploads from Slack to brain index."""

import base64
from typing import Dict, Optional, Tuple

async def build_upload_destination_modal(
    file_name: str,
    file_size: int,
    common_directories: list[str],
) -> Dict:
    """Build modal asking where to save the uploaded file."""
    ...

async def process_slack_file_upload(
    file_url: str,
    file_name: str,
    target_directory: str,
    slack_token: str,
    semantic_search_client,
) -> Tuple[bool, str]:
    """Download from Slack and upload to brain.
    
    Returns (success, message)
    """
    ...
```

**Slack Event Handler: `message` with files**

```python
@self.app.event("message")
async def handle_message_with_files(event, client, say):
    """Handle messages that include file attachments."""
    files = event.get("files", [])
    if files:
        # Open modal to select destination
        await client.views_open(
            trigger_id=...,  # Need to get from shortcut/action
            view=build_upload_destination_modal(...)
        )
```

**Challenge: trigger_id**

Messages don't provide a `trigger_id`. We have two options:

1. **Use a follow-up action** — Bot replies with a button "Save this file to Brain", clicking provides trigger_id
2. **Use ephemeral message** — Show inline Block Kit with directory selection, no modal

**Recommended: Option 1 (Follow-up button)**
- Cleaner UX
- Works with Slack's modal system
- User explicitly confirms they want to save the file

### Flow Diagram

```
User uploads file in DM
        │
        ▼
Bot receives message event with files[]
        │
        ▼
Bot replies: "📎 I see you shared a file: {name}
              Would you like to save it to your brain?"
              [💾 Save to Brain]
        │
        ▼
User clicks button → trigger_id available
        │
        ▼
Modal opens: "Save {filename} to..."
  ┌─────────────────────────────────┐
  │ Directory: [notes/________] ▼  │
  │ ──────────────────────────────  │
  │ Common: journal, notes, docs   │
  │ ──────────────────────────────  │
  │ Rename: [{filename}__________] │
  │                                 │
  │           [Cancel] [Save]       │
  └─────────────────────────────────┘
        │
        ▼
view_submission → download file → upload API → success modal
```

### Error Handling

| Scenario | User Message |
|----------|--------------|
| File too large | "⚠️ File exceeds 10MB limit. Please upload a smaller file." |
| Unsupported type | "⚠️ File type `.xyz` is not supported. Supported: .md, .txt, .pdf, .py, etc." |
| Readonly directory | "🔒 The directory `journal` is read-only. Choose a different destination." |
| File exists | "⚠️ File already exists at this path. [Overwrite] [Choose different name]" |
| Network error | "⚠️ Failed to download file from Slack. Please try again." |
| Index error | "⚠️ File saved but indexing failed. It will be indexed on next scan." |

### Security Considerations

1. **File size limit** — 10MB max to prevent abuse
2. **Gate enforcement** — Cannot upload to readonly directories
3. **File type validation** — Whitelist of allowed extensions
4. **Path traversal prevention** — Sanitize file_path to prevent `../` attacks
5. **Slack token validation** — Only accept files from authenticated Slack requests

### Implementation Tasks

1. **API Layer (NUC-1)**
   - [ ] Add `POST /api/documents/upload` endpoint to search_api.py
   - [ ] Add file writing logic with gate checks
   - [ ] Add immediate indexing of uploaded file
   - [ ] Add path sanitization
   - [ ] Update OpenAPI docs

2. **Client Layer**
   - [ ] Add `upload_document()` method to SemanticSearchClient
   - [ ] Create `slack_bot/file_uploader.py` module

3. **Slack Handlers**
   - [ ] Add "Save to Brain" button handler for file messages
   - [ ] Add upload destination modal builder
   - [ ] Add view_submission handler for upload modal
   - [ ] Add "Add File" button to /index dashboard (for future URL-based upload)

4. **Testing**
   - [ ] Unit tests for upload endpoint
   - [ ] Integration tests for full flow
   - [ ] Manual Slack UI testing

### Out of Scope (Future Enhancements)

- **Bulk upload** — Upload multiple files at once
- **URL import** — Paste a URL to download and save
- **Folder sync** — Sync entire Slack channel files to a folder
- **Image OCR** — Extract text from images for indexing
- **Version control** — Track file history/versions

## Success Metrics

- Upload completes in <5 seconds for files <1MB
- Clear error messages for all failure modes
- File appears in search results within 10 seconds of upload
- Zero data loss (file always saved before indexing attempted)

## Timeline Estimate

| Phase | Effort |
|-------|--------|
| API endpoint | 30 min |
| Client method | 15 min |
| Slack handlers | 45 min |
| Testing & fixes | 30 min |
| **Total** | ~2 hours |
