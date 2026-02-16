# Tuning Guide

## What to Tune

### 1. System Prompt (highest impact)

Location: `agents/slack_agent.py`, `self.system_prompt`

The system prompt defines the bot's personality and priorities. Key principles:
- Conversation memory is primary, brain search is secondary
- Be concise, be warm, don't be sycophantic
- Cite brain sources only when genuinely relevant

### 2. _is_conversational() filter

Location: `agents/slack_agent.py`, `_is_conversational()`

Controls which messages skip brain search. Too aggressive = misses relevant
searches. Too permissive = brain search drowns out conversation memory.

### 3. min_relevance_score

Location: `agents/slack_agent.py`, config `min_relevance_score` (default 0.7)

Higher = fewer brain results (less noise). Lower = more results (more context).

### 4. Message construction order

The order of messages in the LLM prompt matters enormously:

```
[system] → [history] → [supplementary context] → [user message]
```

The user message should ALWAYS be last. Brain context should be clearly
labeled as supplementary so the LLM doesn't confuse it with conversation.

### 5. context_budget / summarization_threshold

How much of the context window is reserved for injected context vs.
conversation history. More budget for context = less room for history.

## How to Tune

### Iterative Process

1. Run `brain_tuner.py --scenario all` to get baseline
2. Make ONE change (prompt wording, filter rule, threshold)
3. Deploy: `rsync + ssh restart`
4. Re-run tuner
5. Compare results
6. Repeat

### Common Tuning Moves

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Bot forgets what you said | History not loading | Check thread_ts keying |
| Bot always talks about docs | Brain search too aggressive | Tighten `_is_conversational()` or raise `min_relevance_score` |
| Bot ignores brain entirely | `_is_conversational()` too broad | Narrow the patterns |
| Bot is verbose/sycophantic | System prompt issue | Tighten prompt style instructions |
| Bot confused by context | Brain context overwhelming | Reduce `max_search_results` or raise `min_relevance_score` |
| Bot slow to respond | Token budget too large | Reduce `max_context_tokens` |

### Running Targeted Tests

```bash
# Just test name recall
python tools/brain_tuner.py --scenario name-recall -v

# Test context vs search balance
python tools/brain_tuner.py --scenario context-vs-search -v

# Test personality continuity
python tools/brain_tuner.py --scenario personality -v
```

## Adding New Scenarios

Add a function to `tools/brain_tuner.py`:

```python
def scenario_my_test(engine: ConversationEngine) -> ScenarioResult:
    result = ScenarioResult(scenario_name="my-test")
    turns = [
        {
            "message": "...",
            "checks": [
                {"name": "...", "type": "contains", "value": ["keyword"]},
            ],
        },
    ]
    # ... drive turns through engine.chat() and engine.evaluate()
    return result
```

Then add it to `SCENARIOS` dict at the bottom of the file.
