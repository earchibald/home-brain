#!/bin/bash
# deploy_and_diagnose.sh — One-shot deploy + diagnostic conversation + analysis
# Run this when back on the home LAN (NUCs reachable)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Phase 1: Deploy fixes to NUC-2 ==="
rsync -av agents/slack_agent.py nuc-2.local:/home/earchibald/agents/agents/
ssh nuc-2.local "sudo systemctl restart brain-slack-bot"
echo "Waiting for bot to start..."
sleep 5
ssh nuc-2.local "sudo systemctl is-active brain-slack-bot"
echo "✅ Bot deployed and running"

echo ""
echo "=== Phase 2: Load Vaultwarden credentials ==="
eval "$(ssh nuc-1.local 'cat /home/earchibald/agents/.vaultwarden')"
echo "✅ Credentials loaded"

echo ""
echo "=== Phase 3: Run brain tuner (all scenarios) ==="
python tools/brain_tuner.py --scenario all --verbose --report /tmp/tuner-report-$(date +%Y%m%d-%H%M%S).json
echo "✅ Tuner complete"

echo ""
echo "=== Phase 4: Pull latest conversation for analysis ==="
LATEST_CONV=$(ssh nuc-2.local "ls -t /home/earchibald/brain/users/U0AELV88VN3/conversations/ | head -1")
echo "Latest conversation: $LATEST_CONV"
ssh nuc-2.local "cat /home/earchibald/brain/users/U0AELV88VN3/conversations/$LATEST_CONV" > /tmp/latest-conversation.json
echo "✅ Conversation saved to /tmp/latest-conversation.json"

echo ""
echo "=== Done! ==="
echo "Review /tmp/latest-conversation.json for issues"
echo "Run 'python tools/brain_tuner.py --scenario name-recall --verbose' for quick identity test"
