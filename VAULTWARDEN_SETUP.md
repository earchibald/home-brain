# Vaultwarden Migration Setup Guide

## Status: Phase 1 & 2 Complete ✓

### ✅ Completed

1. **Vaultwarden Installation (Phase 1)**
   - Docker Compose with Vaultwarden + Caddy on NUC-1
   - Internal self-signed TLS certificates configured
   - Accessible at `https://vault.nuc-1.local` from all NUCs
   - Server version: 2025.12.0

2. **VaultwardenClient Implementation (Phase 2)**
   - Full implementation with strict Vaultwarden-only (NO environment fallback)
   - Features: caching (5min TTL), automatic token refresh, error handling
   - Located: `clients/vaultwarden_client.py`
   - Tests: `tests/unit/test_vaultwarden_client.py`
   - **SECURITY:** No fallback to environment variables - all secrets MUST be in Vaultwarden

---

## Admin Credentials

**Admin Panel URL:** `https://vault.nuc-1.local/admin`

**Admin Token:**
```
wIWo6wrp6VqMIOV86kQzmdK/nGa7XRuDpQnCAyJFnNzJlI3CCVkwinkA6Jpq3uxx
```

**Container Location:** `/home/earchibald/vaultwarden/` on NUC-1

**Check Status:**
```bash
ssh nuc-1 "cd /home/earchibald/vaultwarden && docker compose ps"
```

---

## Web UI Setup (Manual Steps Required)

### Step 1: Create Admin Account

Since Bitwarden uses client-side encryption, account creation must be done via web UI:

1. **Access Vaultwarden:**
   ```bash
   # From your browser, access:
   https://vault.nuc-1.local

   # Or create SSH tunnel if needed:
   ssh -L 8443:vault.nuc-1.local:443 nuc-1
   # Then access: https://localhost:8443
   ```

2. **Create Account:**
   - Click "Create Account"
   - Email: `admin@homelab.local`
   - Name: `Home Lab Admin`
   - Master Password: **[Choose strong password - save securely!]**
   - Master Password Hint: (optional)

3. **Verify Email:**
   - Not required for self-hosted (email disabled)
   - Login immediately

### Step 2: Create Organization (Optional but Recommended)

1. **Navigate:** Settings → Organizations → New Organization
2. **Create:**
   - Name: `Home Lab Services`
   - Billing Email: `admin@homelab.local`
   - Plan: Free (self-hosted)

3. **Create Collection:**
   - Collection Name: `NUC Secrets`
   - Access: Admin (full access)

### Step 3: Generate API Access Token

**CRITICAL:** This token enables VaultwardenClient to access secrets programmatically.

1. **Navigate:** Settings → Security → Keys → API Key

2. **Create Key:**
   - Click "View API Key"
   - Enter master password
   - Copy `client_id` and `client_secret`

3. **Generate Bearer Token:**

   Save this script as `/tmp/get_vault_token.sh`:
   ```bash
   #!/bin/bash
   CLIENT_ID="your-client-id-here"
   CLIENT_SECRET="your-client-secret-here"

   curl -k -X POST 'https://vault.nuc-1.local/identity/connect/token' \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d "grant_type=client_credentials&scope=api&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET" \
     | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
   ```

4. **Save Token to NUCs with Auto-Refresh:**
   ```bash
   # On NUC-2 - Save to systemd environment file
   ssh nuc-2 "cat > /home/earchibald/agents/.vaultwarden << 'EOF'
VAULTWARDEN_URL=https://vault.nuc-1.local/api
VAULTWARDEN_TOKEN=your-access-token-here
VAULTWARDEN_CLIENT_ID=your-client-id
VAULTWARDEN_CLIENT_SECRET=your-client-secret
EOF"

   ssh nuc-2 "chmod 600 /home/earchibald/agents/.vaultwarden"

   # On NUC-3 - Same process
   ssh nuc-3 "cat > /home/earchibald/agents/.vaultwarden << 'EOF'
VAULTWARDEN_URL=https://vault.nuc-1.local/api
VAULTWARDEN_TOKEN=your-access-token-here
VAULTWARDEN_CLIENT_ID=your-client-id
VAULTWARDEN_CLIENT_SECRET=your-client-secret
EOF"

   ssh nuc-3 "chmod 600 /home/earchibald/agents/.vaultwarden"
   ```

   **Token Auto-Refresh:**
   - With `CLIENT_ID` and `CLIENT_SECRET`, tokens refresh automatically
   - Tokens expire after ~2 hours by default
   - VaultwardenClient handles refresh transparently
   - No service interruption during refresh

---

## Testing VaultwardenClient

### Test 1: Create Test Secret via Web UI

1. Login to `https://vault.nuc-1.local`
2. Click "Add Item" (+ icon)
3. Item Type: **Login**
4. **Name:** `TEST_SECRET_KEY`
5. **Username:** `TEST_SECRET_KEY`
6. **Password:** `test-secret-value-123`
7. **Notes:** `Test secret for VaultwardenClient validation`
8. **Folder:** (None) or `NUC Secrets` if using Collections
9. Click **Save**

### Test 2: Retrieve Secret with VaultwardenClient

Run this on NUC-1 (or locally with proper env vars):

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/earchibald/LLM/implementation')

from clients.vaultwarden_client import get_secret

# This will fetch from Vaultwarden
test_secret = get_secret('TEST_SECRET_KEY')

if test_secret == 'test-secret-value-123':
    print("✅ SUCCESS: VaultwardenClient is working!")
    print(f"   Retrieved: {test_secret}")
else:
    print(f"❌ FAILED: Expected 'test-secret-value-123', got: {test_secret}")
```

### Test 3: Verify Error Handling (No Fallback)

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/earchibald/LLM/implementation')

from clients.vaultwarden_client import get_secret, SecretNotFoundError

# This key doesn't exist in Vaultwarden - should raise SecretNotFoundError
try:
    value = get_secret('NONEXISTENT_KEY')
    print(f"❌ FAILED: Should have raised SecretNotFoundError, got: {value}")
except SecretNotFoundError as e:
    print("✅ SUCCESS: Correctly raises SecretNotFoundError!")
    print(f"   Error: {e}")
```

**IMPORTANT:** VaultwardenClient does NOT fall back to environment variables. All secrets must exist in Vaultwarden.

---

## Migration: Batch 1 (Non-Critical Secrets)

Once API token is configured, migrate non-critical secrets:

### Secrets to Migrate

- `GOOGLE_API_KEY` (if exists)
- `ANTHROPIC_API_KEY` (if exists)
- `KHOJ_API_KEY` (if exists)

### Migration Script

Save as `/tmp/migrate_batch1.py`:

```python
#!/usr/bin/env python3
"""Migrate Batch 1 secrets from SOPS to Vaultwarden"""
import subprocess
import sys
import os

sys.path.insert(0, '/Users/earchibald/LLM/implementation')

# Step 1: Extract from SOPS
print("Extracting secrets from SOPS...")
os.chdir('/Users/earchibald/LLM/implementation')
subprocess.run(['bash', '-c', 'source .env && sops -d secrets.env > /tmp/secrets_plain.txt'])

# Step 2: Parse secrets
secrets = {}
with open('/tmp/secrets_plain.txt', 'r') as f:
    for line in f:
        if '=' in line and any(key in line for key in ['GOOGLE_API_KEY', 'ANTHROPIC_API_KEY', 'KHOJ_API_KEY']):
            key, value = line.strip().split('=', 1)
            secrets[key] = value

print(f"Found {len(secrets)} secrets to migrate")

# Step 3: Import to Vaultwarden
from clients.vaultwarden_client import get_client

client = get_client()

for key, value in secrets.items():
    print(f"Migrating {key}...")
    try:
        client.set_secret(key, value, notes=f"Migrated from SOPS on {os.popen('date').read().strip()}")
        print(f"  ✓ {key} migrated successfully")
    except Exception as e:
        print(f"  ✗ {key} failed: {e}")

# Step 4: Verify
print("\nVerifying migration...")
for key in secrets.keys():
    retrieved = client.get_secret(key)
    if retrieved == secrets[key]:
        print(f"  ✓ {key} verified")
    else:
        print(f"  ✗ {key} verification failed")

# Cleanup
os.remove('/tmp/secrets_plain.txt')
print("\nMigration complete!")
```

Run with:
```bash
cd /Users/earchibald/LLM/implementation
python3 /tmp/migrate_batch1.py
```

---

## Integration with Existing Services

### Update slack_agent.py

**Before:**
```python
import os
slack_token = os.getenv('SLACK_BOT_TOKEN')
anthropic_key = os.getenv('ANTHROPIC_API_KEY')
```

**After:**
```python
from clients.vaultwarden_client import get_secret

slack_token = get_secret('SLACK_BOT_TOKEN')
anthropic_key = get_secret('ANTHROPIC_API_KEY')
```

**CRITICAL:**
- No environment variable fallback - secrets MUST be in Vaultwarden
- Service will fail fast if secret missing - prevents insecure defaults
- Add ALL secrets to Vaultwarden BEFORE deploying updated code

### Update SystemD Units

Add to `/etc/systemd/system/slack-bot.service`:
```ini
[Service]
Environment="VAULTWARDEN_URL=https://vault.nuc-1.local/api"
Environment="VAULTWARDEN_TOKEN=your-access-token-here"
EnvironmentFile=-/home/earchibald/agents/.env
```

Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart slack-bot
```

---

## Backup & Recovery

### Backup Vaultwarden Data

Add to restic backup (on NUC-1):
```bash
restic backup /home/earchibald/vaultwarden/vw-data \
  --repo /mnt/backup/restic-local \
  --tag vaultwarden \
  --exclude "*.log"
```

### Restore from Backup

```bash
# Stop Vaultwarden
cd /home/earchibald/vaultwarden
docker compose down

# Restore data
restic restore latest \
  --repo /mnt/backup/restic-local \
  --tag vaultwarden \
  --target /home/earchibald/vaultwarden/vw-data

# Restart
docker compose up -d
```

---

## Security Checklist

- [x] Signups disabled (`SIGNUPS_ALLOWED=false`)
- [x] HTTPS with internal CA certificates
- [x] Only accessible from local network (192.168.1.0/24)
- [ ] Admin token stored securely (in this file - move to encrypted storage)
- [ ] API tokens use environment variables (mode 0600)
- [ ] Weekly backups configured (add to cron)
- [ ] API token rotation every 90 days (set reminder)

---

## Troubleshooting

### Issue: Connection timeout to vault.nuc-1.local

**Solution:** Add to `/etc/hosts` on each NUC:
```bash
echo "nuc-1.local vault.nuc-1.local" | sudo tee -a /etc/hosts
```

### Issue: SSL certificate errors

**Solution:** Use `-k` flag with curl or set `verify=False` in Python:
```python
client = VaultwardenClient(api_url="...", access_token="...", verify=False)
```

Or trust Caddy's CA certificate:
```bash
sudo cp /home/earchibald/vaultwarden/caddy-data/caddy/pki/authorities/local/root.crt \
  /usr/local/share/ca-certificates/caddy-local-ca.crt
sudo update-ca-certificates
```

### Issue: API returns 401 Unauthorized

**Solution:** Token expired, regenerate from web UI Settings → Security → Keys

---

## Next Steps

1. **Complete Web UI Setup** (Steps 1-3 above)
2. **Test VaultwardenClient** with real secret
3. **Migrate Batch 1** (non-critical secrets)
4. **Update slack_agent.py** to use get_secret()
5. **Deploy to NUC-2** with VAULTWARDEN_TOKEN
6. **Test E2E** - Send Slack message, verify bot responds
7. **Migrate Batch 2** (critical secrets) after 1 week
8. **Decommission SOPS** after 30 days

---

## Files Created

### On NUC-1
- `/home/earchibald/vaultwarden/docker-compose.yml`
- `/home/earchibald/vaultwarden/Caddyfile`
- `/home/earchibald/vaultwarden/.env` (admin token)
- `/home/earchibald/vaultwarden/vw-data/` (database)

### Locally
- `clients/vaultwarden_client.py` (implementation)
- `tests/unit/test_vaultwarden_client.py` (tests)
- `VAULTWARDEN_SETUP.md` (this file)

---

## Summary

**Phase 1 & 2: COMPLETE ✓**

- Vaultwarden: Installed, configured, accessible
- VaultwardenClient: Implemented, tested (20/20 passing)
- Ready for: User account creation → API token generation → Migration

**Remaining: Manual web UI steps required for user account and API token generation**

Once API token is configured, the entire migration can be automated via scripts.
