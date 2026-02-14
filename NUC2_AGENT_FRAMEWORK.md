# NUC-2 Agent Framework Design

## Overview

NUC-2 functions as the **autonomous intelligence backend** of your semantic brain. It hosts pluggable agents that:
- Ingest content from multiple sources
- Process and analyze your brain data via Khoj
- Provide personalized advice and learning assistance
- Generate daily journal entries with AI-powered suggestions
- Support future Slack integration for chat-based interaction

## Architecture

### Core Components

```
~/agents/
├── venv/                          # Python 3.10+ virtual environment
├── agent_platform.py              # Core agent runner & lifecycle management
├── clients/
│   ├── khoj_client.py             # Khoj API wrapper (search, embeddings)
│   ├── llm_client.py              # Ollama API wrapper (Mac Mini inference)
│   └── brain_io.py                # Brain folder I/O with Syncthing
├── agents/
│   ├── __init__.py
│   ├── journal_agent.py           # Enhanced journal with AI suggestions
│   ├── advice_agent.py            # Personalized advice (ADHD, learning, work)
│   ├── summary_agent.py           # Convert notes to summaries
│   ├── ingestion_agent.py         # Feed external content into brain
│   └── custom_agent.py            # Template for user-defined agents
├── config.yaml                    # Agent configurations & schedules
├── .env                           # Runtime credentials (local to NUC-2)
└── logs/                          # Agent execution logs
```

### Data Flow

```
External Sources (RSS, APIs, files)
    ↓
[Ingestion Agent] → Brain folder
    ↓ (Syncthing)
[Khoj Index] (NUC-1)
    ↓
[User Query / Chat]
    ↓
[Query Agent] → Khoj search + context
    ↓
[Ollama LLM] (Mac Mini: 192.168.1.58)
    ↓
[Response Agent] → Write to brain + notify user
    ↓
[Slack App] (future) or Khoj Chat UI
```

## Agent Lifecycle

Each agent follows this pattern:

```python
class Agent:
    async def run(self):
        """Main execution entrypoint"""
        # 1. Load context & configuration
        # 2. Query Khoj for relevant data
        # 3. Process via LLM if needed
        # 4. Write outputs to brain folder
        # 5. Notify user on errors
        # 6. Update execution log
```

### Execution Triggers

- **Scheduled:** Cron jobs (daily journal at 6 AM, advice at 8 AM, summaries weekly)
- **Event-based:** File changes in brain, external webhooks
- **On-demand:** API calls from Khoj or future Slack app
- **Reactive:** Notification-driven (e.g., task completion triggers review)

## Core Clients

### `khoj_client.py`

```python
class KhojClient:
    async def search(q: str, content_type: str = "markdown") → List[SearchResult]
    async def get_embeddings(text: str) → List[float]
    async def upsert_content(content: str, metadata: dict) → bool
```

**Usage:** All agents query Khoj to understand existing brain state before generating outputs.

### `llm_client.py`

```python
class OllamaClient:
    async def complete(prompt: str, model: str = "llama3.2", stream: bool = False) → str
    async def chat(messages: List[dict], model: str = "llama3.2") → str
    async def embeddings(text: str) → List[float]
```

**Usage:** Generate advice, summaries, journal suggestions, and thought synthesis.

### `brain_io.py`

```python
class BrainIO:
    async def read_file(path: str) → str
    async def write_file(path: str, content: str, overwrite: bool = False) → bool
    async def list_files(pattern: str) → List[str]
    async def append_to_file(path: str, content: str) → bool
```

**Usage:** Write agent outputs to `/home/earchibald/brain/**/*.md` for Syncthing distribution and Khoj indexing.

## Built-in Agents

### 1. Journal Agent (`journal_agent.py`)

**Schedule:** Daily at 6 AM

**Features:**
- Creates daily entry at `brain/journal/YYYY-MM-DD.md`
- Queries recent brain activity (last 24h)
- Uses Ollama to suggest journal prompts & reflection questions
- Generates "Today's Focus" section with AI-derived priority guidance
- Learns from user input patterns (optional)

**Output:**
```markdown
# Daily Journal: 2026-02-14

## Today's Focus
- [ ] Morning review: Read "ADHD time management" notes from brain
- [ ] Implement: Time-blocking technique from learning agent
- [ ] Check: Progress on "project-X" from work folder

## Your Prompts for Today
1. What was one small win? (builds momentum)
2. Where did you get stuck? (identify support needs)
3. Energy level: Low / Medium / High (track patterns)

## Reflection Space
[User fills in]

## Evening Summary
*(Agent generates this at 10 PM)*
- Detected focus on [topic]
- Suggested follow-up notes created at: [link]
- Tomorrow's tip: [AI-generated learning advice]
```

### 2. Advice Agent (`advice_agent.py`)

**Schedule:** Triggered on-demand via Khoj chat or daily at 9 AM

**Specializations:**
- **ADHD Assistant:** Symptom management, time-blocking, prioritization
- **Work Organizer:** Project tracking, deadline management, focus techniques  
- **Learning Coach:** Study strategies, concept synthesis, knowledge gaps

**Features:**
- Queries brain for context (past advice, successes, failures)
- Generates personalized micro-advice (2-3 min read)
- Learns from user feedback (optional: rate advice quality)
- Proactive suggestions based on detected patterns

**Output Example:**
```markdown
# Your Personal Advice - 2026-02-14

## 🧠 ADHD Insight
Based on your notes about "time blindness" and "hyperfocus episodes":
- Set phone timer for transitions (3-min warning before context switch)
- Your pattern: Hyperfocus 10:30 AM - 1 PM (use for hardest task)
- Try: "Tiny wins" journal to celebrate done-ness

## 📚 Learning Tip  
Saw you studying "Docker concepts" - your learning style indicates visual examples help.
→ Create a quick diagram file at: `brain/learning/docker-mental-model.md`

## 🎯 This Week's Focus
Your projects: [extracted from work notes]
Recommended: Focus on [bottleneck] first (efficiency gain: 3.2x based on similar tasks)
```

### 3. Summary Agent (`summary_agent.py`)

**Schedule:** Weekly on Friday at 3 PM

**Features:**
- Extracts key themes from week's notes
- Generates brief summaries by topic
- Identifies knowledge gaps / follow-ups needed
- Creates actionable next-week plan

**Output:**
```markdown
# Weekly Summary - Week of Feb 10-16, 2026

## Key Topics This Week
- Docker deployment (5 notes)
- Python debugging (2 notes)
- ADHD strategies (4 notes)

## Synthesis
[LLM-generated insights combining all notes]

## Action Items
- [ ] Follow up on: [incomplete thought from notes]
- [ ] Learn more: [concept mentioned 3x, understanding unclear]
- [ ] Implement: [technique from advice that seems promising]
```

### 4. Ingestion Agent (`ingestion_agent.py`)

**Handles:**
- RSS feed parsing → brain/feeds/
- File uploads from pCloud folder
- Email forwarding (future)
- Webhook triggers (future)

**Output:**
```markdown
# Source: "The ADHD Nerd" Newsletter - 2026-02-14

Original: https://...

Key Points:
- [Auto-extracted summary]
- [Bulleted insights]

Tags: `#adhd` `#neurodiverse` `#newsletter`
Source Tags: `#rss` `#external`
```

## Execution Model

### Scheduled Jobs (Cron + Agent Runner)

```bash
# NUC-2 crontab
0 6 * * * /home/earchibald/agents/venv/bin/python -m agents.journal_agent
0 9 * * * /home/earchibald/agents/venv/bin/python -m agents.advice_agent
0 3 * * 5 /home/earchibald/agents/venv/bin/python -m agents.summary_agent
*/30 * * * * /home/earchibald/agents/agent_platform.py --check-events
```

### On-Demand Execution (API)

```python
# Future Slack app or HTTP API
POST /api/agents/query
{
  "agent": "advice_agent",
  "prompt": "I'm struggling with time management",
  "context": {"type": "chat", "user": "slack:@eugene"}
}
```

### Error Handling & Notifications

All agents use `agent_notify.py`:

```python
from agent_notify import notify

try:
    await agent.run()
except Exception as e:
    notify(
        "[AGENT] Journal Bot Failed",
        f"Error generating daily journal: {str(e)}",
        priority="high"
    )
    logging.error(f"Agent failed: {e}", exc_info=True)
```

## Configuration (`config.yaml`)

```yaml
agents:
  journal_agent:
    enabled: true
    schedule: "0 6 * * *"  # Cron format
    config:
      brain_path: /home/earchibald/brain
      output_folder: journal
      llm_model: llama3.2
      max_tokens: 500

  advice_agent:
    enabled: true
    schedule: "0 9 * * *"
    config:
      specializations: [ADHD, Work, Learning]
      context_lookback_days: 30

  ingestion_agent:
    enabled: true
    rss_feeds:
      - url: https://...
        category: neuroscience
      - url: https://...
        category: productivity

clients:
  khoj:
    base_url: http://192.168.1.195:42110
    timeout: 30s
  
  ollama:
    base_url: http://192.168.1.58:11434
    timeout: 60s
    model: llama3.2

notifications:
  enabled: true
  topic: omnibus-brain-notifications-v3
  priority_errors: high
  priority_info: default
```

## Integration Points

### With Khoj (Already Working)
- **Search:** Find relevant past notes before generating advice/summaries
- **Indexing:** Agent outputs automatically indexed by Khoj
- **Chat:** Future: Agents respond to user queries in Khoj chat interface

### With Ollama (Mac Mini)
- **Inference:** All LLM calls go through Ollama on 192.168.1.58:11434
- **Model:** llama3.2 for advice, summaries, journal suggestions
- **Embedding:** Use nomic-embed-text for semantic search enrichment

### With Syncthing (Brain Distribution)
- **Write:** Agent outputs go to `~/brain/**/*.md`
- **Sync:** Automatically distributed to all NUCs within seconds
- **Index:** Khoj picks up new files automatically

### With Slack (Future)
- **Chat Interface:** Agents become conversational via Slack app
- **Notifications:** Agent alerts sent as Slack messages
- **Logging:** Chat history stored in brain as conversation logs

## Testing Strategy

1. **Unit Tests:** Individual agent methods (mocked Khoj/Ollama)
2. **Integration Tests:** Full agent run with real Khoj/Ollama
3. **Manual Testing:** Run agents manually before scheduling
4. **Monitoring:** Cron job logs, notification tracking

## Next Steps

1. ✅ Design NUC-2 architecture (this document)
2. → Implement core clients (khoj, ollama, brain_io)
3. → Implement agent_platform.py (lifecycle management)
4. → Build journal_agent.py
5. → Build advice_agent.py
6. → Add integration tests
7. → Schedule via cron
8. → Monitor & iterate
9. → Design Slack connector (future phase)

---

**Status:** Framework designed. Ready for implementation.

