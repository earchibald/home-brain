# VaultWarden Decryption Errors - Troubleshooting Guide

## Problem

Your VaultWarden vault shows items as "[error: cannot decrypt]" - this means the items exist but can't be decrypted with your current master password/encryption key.

## Common Causes

1. **Master password changed** - Items encrypted with old password
2. **Database imported from another instance** - Encryption keys don't match
3. **Corrupted items** - Database corruption or failed encryption
4. **Organization/shared items** - Missing organization key

## Solutions

### Option 1: Delete Corrupted Items and Start Fresh (Recommended)

1. **Log in to VaultWarden:** https://vault.nuc-1.local
2. **For each "[error: cannot decrypt]" item:**
   - Click the three dots (⋮) on the right
   - Select **Delete**
   - Confirm deletion
3. **Create new items** with correct data (see below)

### Option 2: Export and Re-import (If items are important)

If these items contain important data you need to recover:

1. **Check if you can export from another device** where VaultWarden works
2. **Use the old master password** if you changed it recently
3. **Contact VaultWarden admin** if in organization

### Option 3: Reset Vault (Nuclear option)

If you don't care about the corrupted items:

1. **Backup first:** Export anything you can see
2. **Delete your account** via Settings → Delete Account
3. **Re-register** with the same email
4. **Fresh start** with new encryption key

## After Cleaning Up: Add Required Secrets

Once the corrupted items are removed, add the secrets your system needs:

### For Slack Bot (if migrating from SOPS)

1. **SLACK_BOT_TOKEN**
   - Click **New Item** (+ button)
   - Type: **Login**
   - Name: `SLACK_BOT_TOKEN` (exact match)
   - Username: `SLACK_BOT_TOKEN`
   - Password: Your bot token (from secrets.env: `xoxb-...`)
   - Save

2. **SLACK_APP_TOKEN**
   - Click **New Item**
   - Type: **Login**
   - Name: `SLACK_APP_TOKEN` (exact match)
   - Username: `SLACK_APP_TOKEN`
   - Password: Your app token (from secrets.env: `xapp-...`)
   - Save

### For Homepage (optional)

3. **UNIFI_USERNAME**
   - Name: `UNIFI_USERNAME`
   - Username: `UNIFI_USERNAME`
   - Password: Your Unifi username

4. **UNIFI_PASSWORD**
   - Name: `UNIFI_PASSWORD`
   - Username: `UNIFI_PASSWORD`
   - Password: Your Unifi password

## Generate VaultWarden API Token

Once secrets are added correctly:

1. Go to **Settings** (gear icon) → **Account Security** → **Keys**
2. Click **View API Key**
3. Enter your master password
4. Copy the token (starts with `ey...`)
5. Save it securely - this is what your services will use

## Test VaultWarden API Access

```bash
# Set token
export VAULTWARDEN_TOKEN="your-token-here"

# Test retrieval
python3 -c "
import sys
sys.path.insert(0, '/Users/earchibald/LLM/implementation')
from clients.vaultwarden_client import get_secret

try:
    token = get_secret('SLACK_BOT_TOKEN')
    print(f'✅ SLACK_BOT_TOKEN retrieved: {token[:10]}...')
except Exception as e:
    print(f'❌ Error: {e}')
"
```

## Why This Happened

VaultWarden items are encrypted with a key derived from your master password. If:
- You changed your master password without re-encrypting existing items
- Items were created with a different account
- Database was restored from backup with different encryption

Then the items become unreadable. The solution is always to delete them and recreate with the current password.

## Prevention

- **Don't change master password** without understanding the re-encryption process
- **Export regularly** so you have backups
- **Test decryption** after any password changes
- **Use a consistent account** across all access points
