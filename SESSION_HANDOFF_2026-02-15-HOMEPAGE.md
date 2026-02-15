# Homepage Implementation Handoff - 2026-02-15

This document summarizes the current state of the Homepage implementation on `nuc-1.local`.

## Last Updated

**Date:** 2026-02-15 (evening - final update)  
**Status:** ✅ Fully operational with VaultWarden integration ready

## Recent Updates (Evening Session)

### 1. Fixed Syncthing Status Display ✅
**Issue:** Syncthing on NUC-2 and NUC-3 showed as "down" despite being accessible  
**Root Cause:** CSRF protection in Syncthing blocked simple ping checks  
**Solution:** Changed from `ping:` to `siteMonitor:` in services.yaml

### 2. Migrated to VaultWarden for Secrets ✅
**Previously:** Used SOPS for secrets management  
**Now:** Homepage configured to fetch secrets from VaultWarden API  
**Files Created:**
- `fetch_secrets.py` - Python script to fetch secrets from VaultWarden
- `start_homepage.sh` - Startup script that fetches secrets and starts container
- `VAULTWARDEN_SETUP.md` - Complete setup guide

### 3. Updated Bookmarks ✅
**Previously:** Simple "Favorites" with just Google  
**Now:** AI-focused bookmark hierarchy with:
- AI Tools (ChatGPT, Claude, Gemini, Perplexity)
- AI Research (ArXiv, Hugging Face, Papers With Code)
- Development (GitHub, Ollama)
- Documentation (Homepage)

**Note:** Safari bookmarks couldn't be auto-extracted due to macOS permissions. Default AI bookmarks provided instead.

### 4. Pre-configured Unifi Widget
Unifi monitoring is ready to enable once credentials are added to VaultWarden (see instructions below).

## Design

The goal is to set up a Homepage dashboard on `nuc-1.local` to monitor various services on the local network.

### Services Monitored

*   **nuc-1.local**:
    *   Homepage Dashboard (http://nuc-1.local:3000)
    *   Vaultwarden Password Manager (https://vault.nuc-1.local)
    *   Semantic Search API (http://nuc-1.local:42110)
*   **Syncthing (all NUCs)**:
    *   NUC-1: http://nuc-1.local:8384
    *   NUC-2: http://nuc-2.local:8384
    *   NUC-3: http://nuc-3.local:8384

### Widgets

*   Logo (Homepage icon)
*   Date/Time widget (12-hour format)
*   Search (DuckDuckGo)

### Notifications

*   `ntfy` notification on Homepage container startup.
*   `crontab` job on `nuc-1.local` to monitor the Homepage container and send an `ntfy` notification if it's down.

## Status

The Homepage container is deployed on `nuc-1.local` and is fully functional.

### ✅ Working

*   Homepage is running and accessible at http://nuc-1.local:3000
*   Container health check is working correctly (using `wget`)
*   All configured services are responding:
    - Homepage: 200 OK
    - Vaultwarden: 200 OK
    - Semantic Search: 200 OK
    - Syncthing (NUC-1, NUC-2, NUC-3): 200 OK (using siteMonitor)
*   Widgets are properly configured (logo, datetime, search)
*   Service monitoring is working (changed to siteMonitor for Syncthing)
*   Automated monitoring via cron job
*   Configuration files are properly structured
*   Docker Compose configuration is optimized
*   **VaultWarden integration ready** (secrets fetch script deployed)
*   **AI-focused bookmarks configured**

### 🔄 User Action Required

**To complete VaultWarden setup and enable Unifi monitoring:**

1. **Get VaultWarden API Token:**
   - Log in to https://vault.nuc-1.local
   - Go to Settings → Account Security → Keys
   - Click "View API Key" and copy the token

2. **Set token on nuc-1:**
   ```bash
   ssh nuc-1.local
   echo 'export VAULTWARDEN_TOKEN="your-token-here"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. **Add Unifi credentials to VaultWarden:**
   - Create Login item named `UNIFI_USERNAME`
     - Password field: your Unifi username
   - Create Login item named `UNIFI_PASSWORD`
     - Password field: your Unifi password
   
   **Important:** The "Name" field must match exactly (case-sensitive)

4. **Add Unifi service to Homepage:**
   - Edit `/home/earchibald/homepage-config/config/services.yaml` on nuc-1
   - Add under Infrastructure → nuc-1:
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

5. **Start Homepage with VaultWarden:**
   ```bash
   ssh nuc-1.local
   cd ~/homepage-config
   ./start_homepage.sh
   ```

**Full setup guide:** See `homepage-config/VAULTWARDEN_SETUP.md`

### ✅ Fixed Issues (from previous session)

1. **Healthcheck Failure:** Changed from `curl` (not available) to `wget` (available)
2. **Widget Configuration:** Moved service widgets from widgets.yaml to proper structure
3. **Service List:** Updated to reflect actual running services (removed Portainer, Unifi Controller since they're not running)
4. **Configuration Format:** Fixed widgets.yaml format to use standard Homepage widget syntax

## Recent Changes (2026-02-15)

### Files Modified (Afternoon Session)

1. **homepage-config/docker-compose.yml**
   - Changed healthcheck from `curl` to `wget --quiet --tries=1 --spider`
   - Removed obsolete `version: "3.3"` field
   - Added environment variables for Unifi credentials (with defaults)

2. **homepage-config/config/widgets.yaml**
   - Replaced simple `clock` widget with `datetime` widget (proper format)
   - Added `logo` widget
   - Removed service-specific widgets (moved to services.yaml)

3. **homepage-config/config/services.yaml**
   - Removed non-existent services (Portainer, Unifi Controller, Agent Framework)
   - Added Semantic Search service
   - Added Syncthing monitoring for all 3 NUCs
   - Properly structured with working ping URLs

4. **homepage-config/README.md (updated)**
   - Complete documentation for deployment
   - Instructions for configuring Unifi widget
   - Troubleshooting guide
   - Service monitoring details

### Files Modified (Evening Session)

1. **homepage-config/config/services.yaml**
   - Changed Syncthing from `ping:` to `siteMonitor:` (fixes CSRF issue)

2. **homepage-config/config/bookmarks.yaml**
   - Replaced "Favorites" with AI-focused bookmarks
   - Added: AI Tools, AI Research, Development, Documentation categories
   - Default bookmarks: ChatGPT, Claude, Gemini, Perplexity, ArXiv, HuggingFace, etc.

3. **homepage-config/README.md**
   - Updated to reflect VaultWarden integration
   - Removed SOPS references
   - Added quick deploy instructions

### Files Created (Evening Session)

1. **homepage-config/fetch_secrets.py** (NEW)
   - Python script to fetch secrets from VaultWarden API
   - Uses VaultwardenClient from clients/vaultwarden_client.py
   - Outputs secrets as shell exports
   - Handles missing secrets gracefully

2. **homepage-config/start_homepage.sh** (NEW)
   - Startup script that fetches secrets from VaultWarden
   - Validates VAULTWARDEN_TOKEN is set
   - Starts/restarts Homepage container with secrets
   - Replaces SOPS-based workflow

3. **homepage-config/VAULTWARDEN_SETUP.md** (NEW)
   - Complete guide for migrating from SOPS to VaultWarden
   - Step-by-step instructions for:
     - Creating VaultWarden API token
     - Adding secrets to VaultWarden
     - Configuring environment on nuc-1
     - Testing and troubleshooting
   - Instructions for Unifi widget setup
   - Security notes and best practices

4. **homepage-config/clients/** (DEPLOYED)
   - Copied entire clients directory to nuc-1
   - Provides VaultwardenClient for fetch_secrets.py
   - Required for VaultWarden integration

### Deployment Commands Used

```bash
# Deploy configuration
scp homepage-config/docker-compose.yml nuc-1.local:/home/earchibald/homepage-config/
scp homepage-config/config/*.yaml nuc-1.local:/home/earchibald/homepage-config/config/

# Restart container
ssh nuc-1.local "cd /home/earchibald/homepage-config && docker compose up -d"
```

### Verification Tests

All services tested and confirmed working:
```bash
curl -s -o /dev/null -w "%{http_code}" http://nuc-1.local:3000          # 200
curl -s -o /dev/null -w "%{http_code}" http://nuc-1.local:42110         # 200  
curl -k -s -o /dev/null -w "%{http_code}" https://vault.nuc-1.local     # 200
curl -s -o /dev/null -w "%{http_code}" http://nuc-1.local:8384          # 200
curl -s -o /dev/null -w "%{http_code}" http://nuc-2.local:8384          # 200
curl -s -o /dev/null -w "%{http_code}" http://nuc-3.local:8384          # 200
```

Container health: `Up X seconds (healthy)`

## Configuration Files

### Location on nuc-1.local

```
/home/earchibald/homepage-config/
├── docker-compose.yml
├── monitor_homepage.sh
├── README.md
└── config/
    ├── services.yaml
    ├── widgets.yaml
    ├── bookmarks.yaml
    └── settings.yaml
```

### docker-compose.yml

```yaml
services:
  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    ports:
      - 3000:3000
    volumes:
      - ./config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped
    environment:
      - HOMEPAGE_ALLOWED_HOSTS=nuc-1.local:3000,localhost:3000
      - HOMEPAGE_VAR_UNIFI_USERNAME=${UNIFI_USERNAME:-admin}
      - HOMEPAGE_VAR_UNIFI_PASSWORD=${UNIFI_PASSWORD:-changeme}
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000"]
      interval: 1m30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Monitoring Script

`/home/earchibald/homepage-config/monitor_homepage.sh`:
```bash
#!/bin/bash
if ! docker ps | grep -q homepage; then
  curl -d "Homepage is down!" ntfy.sh/omnibus-brain-notifications-v3
fi
```

**Cron job (runs every minute):**
```
* * * * * /home/earchibald/homepage-config/monitor_homepage.sh
```

## Next Steps / Future Enhancements

### Immediate (User Action Required)

**See [HOMEPAGE_USER_INSTRUCTIONS.md](../HOMEPAGE_USER_INSTRUCTIONS.md) for step-by-step guide.**

1. **Get VaultWarden API token** from https://vault.nuc-1.local
2. **Set token on nuc-1:** `export VAULTWARDEN_TOKEN="..."`
3. **Add Unifi credentials to VaultWarden** (if using Unifi widget)
4. **Start Homepage:** `cd ~/homepage-config && ./start_homepage.sh`

### Optional Enhancements

1. **Add Ollama Service Monitoring**  
   - Check if Ollama has a health endpoint on the Mac Mini
   - Add to services.yaml if available

2. **Enable More VaultWarden Secrets**  
   - Migrate any remaining SOPS secrets to VaultWarden
   - Add to fetch_secrets.py as needed

3. **Customize Bookmarks**  
   - Edit bookmarks.yaml with your personal favorites
   - Current bookmarks are AI-focused defaults

4. **Add Resource Widgets**  
   - Consider adding system resource monitoring (CPU, memory, disk)
   - Requires Homepage to access host metrics

5. **Link Integration**  
   - Add more useful bookmarks
   - Integrate with documentation sites

6. **Service-Specific Widgets**  
   - Vaultwarden widget (if API available)
   - Syncthing status widget

7. **Auto-Start on Boot**  
   - Set up systemd service for Homepage
   - See VAULTWARDEN_SETUP.md for instructions

## Maintenance

### How to Update Configuration

1. Edit config files in `~/LLM/implementation/homepage-config/`
2. Deploy to nuc-1:
   ```bash
   scp homepage-config/config/*.yaml nuc-1.local:/home/earchibald/homepage-config/config/
   ssh nuc-1.local "docker restart homepage"
   ```

### How to View Logs

```bash
ssh nuc-1.local "docker logs homepage --tail 50"
```

### How to Check Health

```bash
ssh nuc-1.local "docker ps --filter name=homepage"
# Look for "(healthy)" in STATUS column
```

## References

*   **Homepage Documentation:** https://gethomepage.dev
*   **Homepage GitHub:** https://github.com/gethomepage/homepage
*   **Widget Documentation:** https://gethomepage.dev/latest/widgets/
*   **Service Integration:** https://gethomepage.dev/latest/configs/services/
*   **Local README:** `homepage-config/README.md`
