# Homepage Dashboard Configuration

This directory contains the configuration for the Homepage dashboard running on nuc-1.local.

## Deployment

The Homepage dashboard is accessible at: http://nuc-1.local:3000

### Quick Deploy (with VaultWarden)

```bash
# From the implementation directory

# 1. Make scripts executable
chmod +x homepage-config/start_homepage.sh
chmod +x homepage-config/fetch_secrets.py

# 2. Deploy files to nuc-1
scp homepage-config/docker-compose.yml nuc-1.local:/home/earchibald/homepage-config/
scp homepage-config/*.sh homepage-config/*.py nuc-1.local:/home/earchibald/homepage-config/
scp homepage-config/config/* nuc-1.local:/home/earchibald/homepage-config/config/
scp -r clients nuc-1.local:/home/earchibald/homepage-config/

# 3. Start on nuc-1
ssh nuc-1.local "cd /home/earchibald/homepage-config && ./start_homepage.sh"
```

### Deploy Updated Configuration Only

```bash
# From the implementation directory
scp homepage-config/config/* nuc-1.local:/home/earchibald/homepage-config/config/

# Restart the container
ssh nuc-1.local "cd /home/earchibald/homepage-config && docker compose restart homepage"
```

## Configuration Files

- `docker-compose.yml` - Container configuration
- `start_homepage.sh` - Startup script with VaultWarden integration
- `fetch_secrets.py` - Fetches secrets from VaultWarden
- `config/services.yaml` - Services to monitor
- `config/widgets.yaml` - Dashboard widgets
- `config/bookmarks.yaml` - Bookmark links (AI-focused hierarchy)
- `config/settings.yaml` - General settings

## Secrets Management (VaultWarden)

Homepage now uses **VaultWarden** instead of SOPS for secrets management.

**See [VAULTWARDEN_SETUP.md](VAULTWARDEN_SETUP.md) for complete setup instructions.**

### Quick Setup Summary

1. Get API token from VaultWarden (Settings → Keys → View API Key)
2. Add secrets to VaultWarden as "Login" items with exact names:
   - `UNIFI_USERNAME` (if using Unifi widget)
   - `UNIFI_PASSWORD` (if using Unifi widget)
3. Set token on nuc-1:
   ```bash
   export VAULTWARDEN_TOKEN="your-token-here"
   ```
4. Start Homepage:
   ```bash
   cd ~/homepage-config
   ./start_homepage.sh
   ```

## Unifi Widget Configuration

The Unifi widget is **pre-configured** but requires credentials in VaultWarden.

### To Enable Unifi Monitoring:

1. **Add credentials to VaultWarden:**
   - Create item named `UNIFI_USERNAME` with your Unifi username in the password field
   - Create item named `UNIFI_PASSWORD` with your Unifi password in the password field

2. **Add Unifi service to services.yaml** (currently removed):
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

3. **Restart Homepage:**
   ```bash
   ssh nuc-1.local "cd ~/homepage-config && ./start_homepage.sh"
   ```

## Monitoring

A cron job runs every minute to monitor the Homepage container:
```bash
* * * * * /home/earchibald/homepage-config/monitor_homepage.sh
```

This sends an ntfy notification if the container is down.

## Health Check

The container includes a health check using wget:
```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000"]
  interval: 1m30s
```

## Services Monitored

### Infrastructure (nuc-1)
- Homepage Dashboard
- Portainer (Docker Management)
- Unifi Controller
- Vaultwarden (Password Manager)

### Agents
- nuc-2: Agent Framework
- nuc-3: Agent Framework  
- m1-mini: Agent Framework

## Troubleshooting

### Container is unhealthy
Check logs: `ssh nuc-1.local "docker logs homepage"`

### Widgets not displaying
1. Verify config files are mounted: `ssh nuc-1.local "docker exec homepage ls -la /app/config"`
2. Check for syntax errors in YAML files
3. Restart container: `ssh nuc-1.local "docker restart homepage"`

### Service status not showing
Ensure the `ping:` URLs are accessible from nuc-1.local
