# Homepage Updates Complete - User Instructions

## Summary of Changes

All requested updates have been completed:

✅ **Fixed Syncthing Status** - NUC-2 and NUC-3 now show correct status  
✅ **VaultWarden Integration** - Migrated from SOPS to VaultWarden for secrets  
✅ **AI Bookmarks** - Replaced "Favorites" with AI-focused bookmark hierarchy  
✅ **Unifi Pre-configured** - Ready to enable once you add credentials to VaultWarden

## What You Need to Do

### 1. Get VaultWarden API Token

1. Open https://vault.nuc-1.local in your browser
2. Log in with your account
3. Go to **Settings** (gear icon) → **Account Security** → **Keys**
4. Under **API Key**, click **View API Key**
5. Enter your master password when prompted
6. Copy the displayed token (starts with `ey...`)
7. Save it - you'll need it for the next step

### 2. Configure nuc-1 with the Token

```bash
ssh nuc-1.local

# Add token to your shell profile
echo 'export VAULTWARDEN_TOKEN="paste-your-token-here"' >> ~/.bashrc

# Reload your shell
source ~/.bashrc

# Verify it's set
echo $VAULTWARDEN_TOKEN  # Should display your token
```

### 3. Add Unifi Credentials to VaultWarden

In VaultWarden web UI (https://vault.nuc-1.local):

**For Username:**
1. Click **New Item** (+ button in top right)
2. Select **Login** type
3. Fill in:
   - **Name:** `UNIFI_USERNAME` (exact case-sensitive match)
   - **Username:** `UNIFI_USERNAME`
   - **Password:** Your actual Unifi username (e.g., `admin`)
   - **Notes:** "Unifi Controller username for Homepage"
4. Click **Save**

**For Password:**
1. Click **New Item** again
2. Select **Login** type
3. Fill in:
   - **Name:** `UNIFI_PASSWORD` (exact case-sensitive match)
   - **Username:** `UNIFI_PASSWORD`
   - **Password:** Your actual Unifi password
   - **Notes:** "Unifi Controller password for Homepage"
4. Click **Save**

⚠️ **Important:** The "Name" field MUST match exactly (case-sensitive): `UNIFI_USERNAME` and `UNIFI_PASSWORD`

### 4. Test Secret Retrieval (Optional)

```bash
ssh nuc-1.local
cd ~/homepage-config

# Test fetching secrets
python3 fetch_secrets.py

# Should output:
# export UNIFI_USERNAME='your-username'
# export UNIFI_PASSWORD='your-password'
```

If you see warnings about missing secrets, go back to VaultWarden and ensure the names match exactly.

### 5. Enable Unifi Monitoring in Homepage

```bash
ssh nuc-1.local
cd ~/homepage-config

# Edit services.yaml
nano config/services.yaml

# Add this under "Infrastructure" → "nuc-1" (after Semantic Search):
```

```yaml
        - "Unifi":
            href: "https://nuc-1.local:8443"
            description: "Unifi Controller"
            siteMonitor: "https://nuc-1.local:8443"
            widget:
              type: unifi
              url: https://nuc-1.local:8443
              username: {{HOMEPAGE_VAR_UNIFI_USERNAME}}
              password: {{HOMEPAGE_VAR_UNIFI_PASSWORD}}
```

Save and exit (Ctrl+X, Y, Enter in nano).

### 6. Start Homepage with VaultWarden

```bash
ssh nuc-1.local
cd ~/homepage-config

# Start Homepage (will fetch secrets from VaultWarden)
./start_homepage.sh
```

You should see:
```
Fetching secrets from VaultWarden...
Starting Homepage...
Homepage started successfully!
Accessible at: http://nuc-1.local:3000
```

### 7. Verify Everything Works

1. Open http://nuc-1.local:3000 in your browser
2. Check that all services show green status
3. Verify Syncthing NUC-2 and NUC-3 show as "up"
4. If you enabled Unifi, check that the widget displays data
5. Check bookmarks - should show AI-focused categories

## Troubleshooting

### "VAULTWARDEN_TOKEN not set"

```bash
# Check if token is set
ssh nuc-1.local
echo $VAULTWARDEN_TOKEN

# If empty, set it again
export VAULTWARDEN_TOKEN="your-token-here"

# Add to shell profile
echo 'export VAULTWARDEN_TOKEN="..."' >> ~/.bashrc
```

### "Secret not found in VaultWarden"

The secret name must match exactly. Double-check:
1. Log in to VaultWarden
2. Click on the item
3. Verify **Name** field is `UNIFI_USERNAME` or `UNIFI_PASSWORD` (exact case)
4. Edit if needed and save

### Script permission denied

```bash
ssh nuc-1.local
chmod +x ~/homepage-config/start_homepage.sh
chmod +x ~/homepage-config/fetch_secrets.py
```

## What Changed

### Previously (SOPS)
- Secrets stored in encrypted `secrets.env` file
- Required SOPS + age key to decrypt
- Manual deployment of environment file

### Now (VaultWarden)
- Secrets stored in VaultWarden (encrypted at rest)
- API token authenticates access
- Automatic fetch on Homepage startup
- Web UI for easy management
- No SOPS/age key needed

## Documentation

All documentation has been updated:
- **homepage-config/README.md** - Quick reference and deployment guide
- **homepage-config/VAULTWARDEN_SETUP.md** - Complete VaultWarden setup guide
- **SESSION_HANDOFF_2026-02-15-HOMEPAGE.md** - Technical handoff document

## What's Next (Optional)

1. **Add more secrets** - Any future secrets can be added to VaultWarden
2. **Enable auto-start** - Set up systemd service (see VAULTWARDEN_SETUP.md)
3. **Customize bookmarks** - Edit `config/bookmarks.yaml` with your favorites
4. **Add more services** - Add any other services you want to monitor

---

**Homepage is ready to use!** Visit http://nuc-1.local:3000
