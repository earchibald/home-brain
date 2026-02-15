# Homepage Dashboard Configuration

This directory contains the configuration for the Homepage dashboard running on nuc-1.local.

## Deployment

The Homepage dashboard is accessible at: http://nuc-1.local:3000

### Deploy Updated Configuration

```bash
# From the implementation directory
scp homepage-config/docker-compose.yml nuc-1.local:/home/earchibald/homepage-config/
scp homepage-config/config/* nuc-1.local:/home/earchibald/homepage-config/config/

# Restart the container
ssh nuc-1.local "cd /home/earchibald/homepage-config && docker compose restart homepage"
```

## Configuration Files

- `docker-compose.yml` - Container configuration
- `config/services.yaml` - Services to monitor
- `config/widgets.yaml` - Dashboard widgets
- `config/bookmarks.yaml` - Bookmark links
- `config/settings.yaml` - General settings

## Unifi Widget Configuration

The Unifi widget requires credentials to function. To configure:

1. Add credentials to `secrets.env` in the implementation directory:
   ```bash
   sops -d secrets.env > temp.env
   echo "UNIFI_USERNAME=your_username" >> temp.env
   echo "UNIFI_PASSWORD=your_password" >> temp.env
   sops -e temp.env > secrets.env
   rm temp.env
   ```

2. Deploy with credentials:
   ```bash
   # On nuc-1
   cd /home/earchibald/homepage-config
   sops -d ~/implementation/secrets.env > .env
   docker compose down
   docker compose up -d
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
