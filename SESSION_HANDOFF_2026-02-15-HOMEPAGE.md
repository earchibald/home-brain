# Homepage Implementation Handoff - 2026-02-15

This document summarizes the current state of the Homepage implementation on `nuc-1.local`.

## Last Updated

**Date:** 2026-02-15 (evening)  
**Status:** ✅ Fully operational and healthy

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
    - Syncthing (NUC-1, NUC-2, NUC-3): 200 OK
*   Widgets are properly configured (logo, datetime, search)
*   Service ping functionality is enabled
*   Automated monitoring via cron job
*   Configuration files are properly structured
*   Docker Compose configuration is optimized (removed obsolete version field)

### 🔄 Pending / Optional

*   **Unifi Widget:** Infrastructure is in place to add Unifi monitoring if credentials are provided
    - Environment variables configured in docker-compose.yml
    - Widget structure ready in configuration
    - To enable: Add UNIFI_USERNAME and UNIFI_PASSWORD to secrets.env (see README.md)

### ✅ Fixed Issues (from previous session)

1. **Healthcheck Failure:** Changed from `curl` (not available) to `wget` (available)
2. **Widget Configuration:** Moved service widgets from widgets.yaml to proper structure
3. **Service List:** Updated to reflect actual running services (removed Portainer, Unifi Controller since they're not running)
4. **Configuration Format:** Fixed widgets.yaml format to use standard Homepage widget syntax

## Recent Changes (2026-02-15)

### Files Modified

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

4. **homepage-config/README.md (NEW)**
   - Complete documentation for deployment
   - Instructions for configuring Unifi widget
   - Troubleshooting guide
   - Service monitoring details

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

1. **Add Ollama Service Monitoring**  
   - Check if Ollama has a health endpoint on the Mac Mini
   - Add to services.yaml if available

2. **Configure Unifi Widget (Optional)**  
   - Add credentials to secrets.env
   - Re-enable Unifi service in services.yaml
   - Deploy with environment variables

3. **Add Resource Widgets**  
   - Consider adding system resource monitoring (CPU, memory, disk)
   - Requires Homepage to access host metrics

4. **Link Integration**  
   - Add more useful bookmarks
   - Integrate with documentation sites

5. **Service-Specific Widgets**  
   - Vaultwarden widget (if API available)
   - Syncthing status widget

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
