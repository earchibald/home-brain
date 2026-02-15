# Quick Testing Guide

## 🚀 TL;DR - Get Started in 2 Minutes

```bash
# 1. Validate everything is ready
python validate_deployment.py

# 2. Run automated tests
pytest tests/ -v

# 3. Start manual testing
python test_slack_bot_manual.py

# 4. Send test messages in Slack
# In Slack DM with @brain-assistant:
# - "test hello"
# - "test attachment" (+ file)
# - "test slow"
```

---

## 📋 What's Included

| Script | Purpose | Duration |
|--------|---------|----------|
| `validate_deployment.py` | Check everything is ready | 10s |
| `test_slack_bot_manual.py` | Interactive Slack testing | 60s |
| `pytest tests/` | Full automated test suite | 1s |
| `RUN_TESTS.md` | Detailed testing guide | Reference |

---

## ✅ Test Scenarios

### Automated (67 tests, <1 second)
- File attachment detection ✓
- File content extraction ✓
- Performance monitoring ✓
- Conversation history ✓
- Error handling ✓

### Manual (5-10 minutes)

1. **Basic Message**
   ```
   Send: "Hello, how are you?"
   Expect: Response in <30 seconds
   ```

2. **File Attachment**
   ```
   Send: "Read this file" + attach .md file
   Expect: Bot mentions file content
   ```

3. **Multi-Turn**
   ```
   Send: "My hobby is dancing"
   Send: "Why do I love it?"
   Expect: Bot remembers context
   ```

4. **Performance**
   ```
   Send: "Long detailed response"
   Check: NUC-2 logs show latency
   ```

5. **Error Handling**
   ```
   Stop Ollama
   Send: Message
   Expect: Friendly error, no crash
   ```

---

## 🔧 Setup

### First Time Only
```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Load Slack credentials
export $(cat secrets.env | grep -v '^#' | xargs)
```

### Each Test Session
```bash
# Validate system
python validate_deployment.py

# See: ✅ DEPLOYMENT READY FOR TESTING
```

---

## 📊 Test Results

**Current Status:**
- ✅ 67 tests PASSING
- ⚠️ 2 intentional edge case failures
- 🟢 File attachments: Implemented & tested
- 🟢 Performance monitoring: Implemented & tested
- 🔵 Streaming infrastructure: Implemented, not yet active

**Coverage:**
- agents/slack_agent.py: 85%+
- slack_bot/: 90%+
- clients/: 85%+

---

## 🗂️ File Organization

```
/Users/earchibald/LLM/implementation/
├── test_slack_bot_manual.py     ← Manual test script
├── validate_deployment.py        ← Validation script
├── RUN_TESTS.md                 ← Detailed guide
├── TEST_README.md               ← This file
│
├── agents/
│   └── slack_agent.py           ← Main bot (integrated)
│
├── slack_bot/                   ← Feature modules
│   ├── file_handler.py
│   ├── performance_monitor.py
│   ├── alerting.py
│   └── ... (6 more modules)
│
└── tests/
    ├── conftest.py
    ├── unit/                    ← Fast tests
    ├── integration/             ← Component tests
    └── red/                     ← Feature tests
```

---

## 🐛 Troubleshooting

### Tests Won't Run
```bash
# Reinstall dependencies
pip install -r tests/requirements-test.txt

# Check Python version
python --version  # Need 3.10+
```

### Bot Not Responding
```bash
# Check service on NUC-2
ssh nuc-2
sudo systemctl status brain-slack-bot

# View logs
sudo journalctl -u brain-slack-bot -f
```

### File Upload Not Working
```bash
# Verify feature is enabled
grep "enable_file_attachments" agents/slack_agent.py

# Check logs for errors
ssh nuc-2
sudo journalctl -u brain-slack-bot -f | grep "attachment"
```

---

## 📚 Full Documentation

See `RUN_TESTS.md` for:
- Detailed scenario instructions
- NUC-2 log viewing commands
- Performance metric verification
- Coverage report generation
- CI/CD setup examples

---

## ✨ Features Tested

### File Attachments ✅
- Detect .txt, .md, .pdf files
- Download from Slack API
- Extract text content
- Truncate to 1MB max
- Include in LLM prompts

### Performance Monitoring ✅
- Track response latency
- Calculate average & P95
- Send alerts if >30s
- Generate histograms

### Streaming Ready 🔵
- Modules implemented
- SSE streaming support
- Slack message updates
- Fallback to non-streaming
- *Activate via config change*

### Core Features ✅
- Multi-turn conversations
- Khoj brain context search
- Working indicator UX
- Error handling
- Graceful degradation

---

## 🎯 Success Criteria

After running all tests, you should see:

```
✅ Validation: All checks passed
✅ Automated: 67 tests passed
✅ Manual: All 5 scenarios passed
✅ Logs: No errors in NUC-2 logs
✅ Performance: Response times <30s
```

---

## 📞 Need Help?

1. **Check logs**: `ssh nuc-2 && sudo journalctl -u brain-slack-bot -f`
2. **Run validation**: `python validate_deployment.py`
3. **Review config**: `cat agents/slack_agent.py | grep -A5 "enable_"`
4. **See test details**: `pytest tests/ -vv --tb=short`

---

**Ready to test?**
```bash
python validate_deployment.py
```

If all checks pass → Start with `test_slack_bot_manual.py` or `pytest tests/`
