#!/bin/bash
# NUC-2 Agent Launcher - wrapper for running agents with proper paths

AGENTS_HOME="/home/earchibald/agents"
VENV="$AGENTS_HOME/venv/bin/python"
PLATFORM="$AGENTS_HOME/agent_platform.py"
LOG_DIR="$AGENTS_HOME/logs"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Agent name to run
AGENT="${1:-journal}"

# Timestamp for logging
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Run the agent with proper environment
cd "$AGENTS_HOME"
echo "[$TIMESTAMP] Running agent: $AGENT" >> "$LOG_DIR/agent_launcher.log"

$VENV "$PLATFORM" "$AGENT" >> "$LOG_DIR/${AGENT}.log" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$TIMESTAMP] ✓ Agent completed successfully" >> "$LOG_DIR/agent_launcher.log"
else
    echo "[$TIMESTAMP] ✗ Agent failed with exit code $EXIT_CODE" >> "$LOG_DIR/agent_launcher.log"
fi

exit $EXIT_CODE
