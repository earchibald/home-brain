# Brain Assistant Human Test Checklist

## Overview

This checklist is designed for manual testing of the Brain Assistant Slack bot. Complete each test case, record the result (Pass/Fail/Partial), and add notes. Return this completed document to the agent for analysis.

**Testing Date:** _____________  
**Tester Name:** _____________  
**Bot Version/Deploy Time:** _____________

---

## What the Bot MUST Do (Critical Capabilities)

These are core functionalities that the bot **must** perform correctly. Any failures here block production use.

### 1. Basic Responsiveness

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 1.1 | Bot responds to DM | Send "Hello" in DM to Brain Assistant | Bot responds within 30 seconds | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 1.2 | Working indicator | Send any message | See "Working..." message appear, then disappear when response arrives | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 1.3 | Multi-sentence query | Ask "What is TypeScript and why would I use it over JavaScript?" | Bot provides coherent, multi-paragraph response | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 1.4 | Response quality | Ask a technical question in your domain | Response is accurate and helpful | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 2. Multi-Turn Conversation

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 2.1 | Context retention | 1. Ask "What's 25 times 4?" 2. Follow up with "Now divide that by 5" | Bot remembers previous answer (100) and calculates 20 | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 2.2 | Pronoun resolution | 1. Say "Let's discuss Python" 2. Then ask "What testing frameworks does it have?" | Bot understands "it" refers to Python | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 2.3 | Long conversation | Exchange 5+ messages in one thread | Bot maintains context throughout | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 3. Brain Search Integration

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 3.1 | Brain search triggered | Ask about a topic you know is in your brain notes | Bot includes "Relevant context from your brain:" section | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 3.2 | Citations included | Same as above | Response cites source files (e.g., "Source: journal/2026-02-10.md") | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 3.3 | Graceful degradation | If search service is down, bot should still respond | Bot responds without crashing (may lack brain context) | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 4. Error Handling

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 4.1 | Empty message handling | Send just whitespace or empty message | Bot either ignores or responds appropriately | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 4.2 | Very long message | Send a 2000+ character message | Bot handles without crashing | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 4.3 | Bot doesn't self-respond | Observe bot's behavior | Bot doesn't respond to its own messages | ⬜ Pass ⬜ Fail ⬜ Partial | |

---

## What the Bot SHOULD Do (Important Capabilities)

These features improve the experience significantly. Partial or missing functionality here is acceptable short-term.

### 5. File Handling

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 5.1 | Text file analysis | Upload a .txt or .md file | Bot analyzes and discusses content | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 5.2 | Code file analysis | Upload a .py, .js, or .ts file | Bot reads and can discuss the code | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 5.3 | PDF analysis | Upload a PDF file | Bot extracts and discusses text content | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 5.4 | Multi-file upload | Upload 2+ files at once | Bot acknowledges and can discuss both | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 5.5 | Save to brain | Click "Save to Brain" button after upload | File saved to brain folder | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 6. Index Management (/index command)

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 6.1 | Open dashboard | Type `/index` | Modal opens showing index stats | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 6.2 | Browse documents | Click "Browse Documents" | Document list appears with pagination | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 6.3 | Reindex trigger | Click "Reindex All" | Confirmation shown, reindex starts | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 7. Model Switching (/model command)

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 7.1 | Show current model | Type `/model` | Modal shows current model selection | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 7.2 | Switch model | Select different model, click Save | Next response uses new model | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 8. Performance

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 8.1 | Response time | Send typical query | Response arrives within 30 seconds | ⬜ Pass ⬜ Fail ⬜ Partial | Actual time: ___ s |
| 8.2 | No timeouts | Send 5 queries in sequence | All receive responses | ⬜ Pass ⬜ Fail ⬜ Partial | |

---

## Stretch Goals (Future Vision)

These are capabilities we're working toward. Document any observations that could inform development.

### 9. Proactive Intelligence (NOT YET IMPLEMENTED)

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 9.1 | Connection suggestions | Discuss a topic | Bot proactively connects to related brain content | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 9.2 | Capture recommendations | Share an insight | Bot suggests saving it as a note | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 9.3 | Workflow guidance | Mention "starting a project" | Bot offers to help scope and create note | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 10. Web Search (PLANNED)

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 10.1 | Current events | Ask about recent news | Bot finds and cites current information | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 10.2 | Real-time data | Ask "What's the weather in Austin?" | Bot retrieves current weather | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 10.3 | Source attribution | Any web search | Bot cites web sources used | ⬜ Pass ⬜ Fail ⬜ Partial | |

### 11. Advanced Memory (PLANNED)

| # | Test Case | Steps | Expected Result | Status | Notes |
|---|-----------|-------|-----------------|--------|-------|
| 11.1 | Cross-session memory | New conversation references old one | Bot recalls previous conversation context | ⬜ Pass ⬜ Fail ⬜ Partial | |
| 11.2 | Preference learning | Repeatedly correct bot on style | Bot adapts to your preferences | ⬜ Pass ⬜ Fail ⬜ Partial | |

---

## Summary

**Critical MUST Tests (1-4):**
- Total: 11 tests  
- Passed: ___  
- Failed: ___  
- Partial: ___

**Important SHOULD Tests (5-8):**
- Total: 13 tests  
- Passed: ___  
- Failed: ___  
- Partial: ___

**Stretch Goal Tests (9-11):**
- Total: 7 tests  
- Passed: ___  
- Failed: ___  
- Partial: ___

---

## Critical Issues Found

List any blocking issues that prevent production use:

1. 
2. 
3. 

---

## Improvement Suggestions

List observations for future enhancement:

1. 
2. 
3. 

---

## Test Environment Details

- **NUC-2 Status:** Running / Down / Unknown  
- **NUC-1 (Search Service):** Running / Down / Unknown  
- **Mac Mini (Ollama):** Running / Down / Unknown  
- **Bot Logs Checked:** Yes / No  
- **Log Location:** `/home/earchibald/agents/logs/`

---

## How to Use This Checklist

1. **Before testing:** Ensure all services are running:
   ```bash
   ssh nuc-2 "sudo systemctl status brain-slack-bot"
   ssh nuc-1 "curl -s http://localhost:9514/api/health"
   ssh m1-mini "curl -s http://localhost:11434/api/tags | head -5"
   ```

2. **During testing:** Fill in Status (check one box) and Notes for each test

3. **After testing:** Count results in Summary section, list issues, and return to agent

4. **For failures:** Include the exact input, expected output, and actual output in Notes
