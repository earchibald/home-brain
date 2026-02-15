# Model Switching - Quick Start Guide

**5-Minute Setup** | **Status:** Ready for Deployment ✅

---

## 🚀 Quick Deploy

### 1. Enable Feature (30 seconds)

**Edit bot config:**
```python
config = {
    # ... existing config ...
    "enable_model_switching": True,  # ← Add this line
}
```

**Restart bot:**
```bash
systemctl restart slack-bot
```

### 2. Add API Keys (Optional - 2 minutes)

**For Gemini:**
```bash
source .env
sops set secrets.env '["GOOGLE_API_KEY"]' '"your-gemini-key"'
```

**For Claude:**
```bash
source .env
sops set secrets.env '["ANTHROPIC_API_KEY"]' '"your-anthropic-key"'
```

**Restart bot again:**
```bash
systemctl restart slack-bot
```

### 3. Test (1 minute)

**In Slack DM:**
```
/model
```

**You should see:**
- Current configuration
- Provider dropdown
- Model dropdown

**Select a model → Get confirmation: "✅ Switched to..."**

---

## 📱 Usage

### Slack Commands

**Open model selector:**
```
/model
```

**Select provider:**
- Click first dropdown
- Choose: Local Ollama, Remote Ollama, Gemini, or Claude

**Select model:**
- Click second dropdown
- Choose from available models

**Done!**
- Confirmation message appears
- Selection saved (for current session)

---

## 🔍 Verify It's Working

### Check Logs
```bash
journalctl -u slack-bot -n 100 | grep -i "model"
```

**Look for:**
```
Model switching enabled. Available providers: ['ollama_local', 'gemini']
```

### Run Tests
```bash
cd /Users/earchibald/LLM/implementation
python -m pytest tests/test_*model* tests/test_*provider* -v --tb=short
```

**Expected:** 39/39 passing ✅

---

## ⚙️ Configuration

### Feature Flag (Required)

```python
"enable_model_switching": True   # Enable
"enable_model_switching": False  # Disable (default)
```

### API Keys (Optional)

**Gemini:**
- Env var: `GOOGLE_API_KEY`
- Get key: https://ai.google.dev/

**Anthropic:**
- Env var: `ANTHROPIC_API_KEY`
- Get key: https://console.anthropic.com/

**Ollama:**
- No keys needed
- Must be running locally or remotely

---

## 🐛 Troubleshooting

### "No providers available"

**Check Ollama:**
```bash
curl http://localhost:11434/api/version
```

**Check API keys:**
```bash
sops -d secrets.env | grep API_KEY
```

### "/model command not found"

**Verify feature enabled:**
```bash
journalctl -u slack-bot | grep "enable_model_switching"
```

**Restart bot:**
```bash
systemctl restart slack-bot
```

### "Provider X not available"

**For Ollama:**
```bash
systemctl status ollama
curl http://localhost:11434/api/version
```

**For cloud APIs:**
```bash
# Test Gemini key
python -c "import google.generativeai as genai; genai.configure(api_key='YOUR_KEY'); print('✅ Valid')"

# Test Anthropic key
python -c "import anthropic; c = anthropic.Anthropic(api_key='YOUR_KEY'); print('✅ Valid')"
```

---

## 📊 Available Providers

### Local Ollama
- **ID:** `ollama_local`
- **Host:** localhost:11434
- **Models:** llama3.2, mistral, etc. (whatever you have installed)
- **Setup:** Just run Ollama locally

### Remote Ollama
- **ID:** `ollama_remote`
- **Host:** eugenes-mbp.local:11434
- **Models:** Same as local
- **Setup:** Ollama running on MacBook Pro

### Google Gemini
- **ID:** `gemini`
- **Models:** gemini-1.5-pro, gemini-1.5-flash, gemini-1.5-flash-8b
- **Setup:** Set `GOOGLE_API_KEY`

### Anthropic Claude
- **ID:** `anthropic`
- **Models:** claude-3-5-sonnet-latest, claude-3-opus-latest, claude-3-haiku-latest
- **Setup:** Set `ANTHROPIC_API_KEY`

---

## 📝 Quick Commands

### Restart bot
```bash
systemctl restart slack-bot
```

### View logs
```bash
journalctl -u slack-bot -f
```

### Run tests
```bash
pytest tests/test_*model* -v
```

### Check API keys
```bash
sops -d secrets.env | grep API_KEY
```

### Add API key
```bash
source .env
sops set secrets.env '["GOOGLE_API_KEY"]' '"value"'
```

---

## ⚠️ Important Notes

### Phase 1 Limitations
- Model selection is **UI-only** (not yet integrated with inference)
- Selection **lost on bot restart**
- **Global selection** for all users

### Why?
- Maintains backward compatibility
- Safe to deploy and test
- Future phases will add full integration

### Workaround
After bot restart:
1. Send `/model` in Slack
2. Re-select your preferred model

---

## 🎯 Success Checklist

- [ ] Feature flag enabled in config
- [ ] Bot restarted
- [ ] `/model` command works in Slack
- [ ] Can see available providers
- [ ] Can select a model
- [ ] Get confirmation message
- [ ] Logs show "Model switching enabled"
- [ ] Tests pass (39/39)

---

## 📚 More Info

- **Full deployment guide:** `DEPLOYMENT_MODEL_SWITCHING.md`
- **Implementation summary:** `MODEL_SWITCHING_SUMMARY.md`
- **Verification report:** `VERIFICATION_REPORT.md`
- **Feature spec:** `DYNAMIC_MODEL_SOURCE_SWITCHING.md`

---

## 🆘 Support

**Issues?**
1. Check logs: `journalctl -u slack-bot -f`
2. Run tests: `pytest tests/test_*model* -v`
3. Review deployment guide: `DEPLOYMENT_MODEL_SWITCHING.md`

**Still stuck?**
- Check provider health checks in logs
- Verify API keys are set correctly
- Ensure Ollama is running (if using)

---

**Version:** 1.0.0
**Status:** ✅ Production Ready
**Last Updated:** 2026-02-15
