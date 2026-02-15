# Semantic Search Service Deployment Guide

## Prerequisites

- Docker and Docker Compose installed on target host (NUC-1)
- Ollama running with `nomic-embed-text` model
- Brain folder synced via Syncthing at `/home/earchibald/brain`

## Deployment Steps

### 1. Copy service to NUC-1

From your Mac:

```bash
# Create deployment directory
ssh nuc-1 "mkdir -p ~/services"

# Copy entire semantic_search directory
scp -r services/semantic_search nuc-1:~/services/

# Verify files
ssh nuc-1 "ls -la ~/services/semantic_search"
```

### 2. Build and start the service

SSH into NUC-1:

```bash
ssh nuc-1
cd ~/services/semantic_search

# Build the Docker image
docker-compose build

# Start the service
docker-compose up -d

# Check logs
docker-compose logs -f
```

### 3. Verify service is running

```bash
# Check container status
docker ps | grep brain_semantic_search

# Test health endpoint
curl http://localhost:42110/api/health

# Expected response:
# {"status":"healthy","ollama":true,"documents":0}
```

### 4. Wait for initial indexing

The service will automatically start indexing brain files on startup. Monitor progress:

```bash
# Watch logs
docker-compose logs -f semantic-search

# Check stats after indexing completes
curl http://localhost:42110/api/stats
```

### 5. Test search functionality

```bash
# Simple search test
curl "http://localhost:42110/api/search?q=sync+verification&limit=3"

# Expected: JSON array with search results
```

### 6. Add health monitoring (optional)

Add to crontab on NUC-1:

```bash
crontab -e

# Add this line for health checks every minute
* * * * * curl -f http://localhost:42110/api/health || /usr/local/bin/notify.sh "Search Service Down" "Semantic search unhealthy" "high"
```

### 7. Update Slack bot to use new service

The new `SemanticSearchClient` is API-compatible with `KhojClient`. You can either:

**Option A: Keep using KhojClient (aliased)**
```python
from clients.khoj_client import KhojClient  # Will use semantic search via alias
```

**Option B: Explicitly use new client**
```python
from clients.semantic_search_client import SemanticSearchClient as KhojClient
```

No code changes needed in `slack_agent.py` - the import is already compatible.

### 8. Deploy updated client to NUC-2

```bash
# From Mac
scp clients/semantic_search_client.py nuc-2:~/agents/clients/

# Restart Slack bot
ssh nuc-2 "sudo systemctl restart brain-slack-bot"
```

### 9. Validate end-to-end

Test via Slack:

1. Send DM to Brain Assistant: "Search for sync verification test"
2. Verify bot responds with relevant results from semantic search
3. Check service logs for search queries

### 10. Remove Khoj (after validation)

Once new service is validated:

```bash
ssh nuc-1

# Stop and remove Khoj containers
cd ~
docker-compose down

# Remove Khoj reindex cron job
crontab -e
# Delete: */30 * * * * curl -s http://localhost:42110/api/update?force=true > /dev/null 2>&1

# Archive Khoj data (optional)
sudo mv docker-compose.yml docker-compose.yml.khoj.backup
tar czf khoj_data_backup.tar.gz ~/brain/khoj_config

# Remove monitor cron jobs for Khoj containers
crontab -e
# Delete: * * * * * /home/earchibald/monitor_docker.sh brain_khoj
# Delete: * * * * * /home/earchibald/monitor_docker.sh brain_db
```

## Troubleshooting

### Service not starting

```bash
# Check logs
docker-compose logs

# Common issues:
# - Ollama not accessible: Check OLLAMA_URL in docker-compose.yml
# - Brain path not mounted: Verify /home/earchibald/brain exists
# - Port conflict: Port 42110 still used by Khoj
```

### No documents indexed

```bash
# Trigger manual reindex
curl -X POST "http://localhost:42110/api/update?force=true"

# Check brain path permissions
ls -la /home/earchibald/brain

# Verify supported files exist
find /home/earchibald/brain -name "*.md" -o -name "*.txt" -o -name "*.pdf"
```

### Slow search responses

```bash
# Check Ollama performance
curl http://192.168.1.58:11434

# Monitor container resources
docker stats brain_semantic_search

# Consider reducing chunk size in indexer.py if embedding generation is slow
```

### Search returns no results

```bash
# Verify documents indexed
curl http://localhost:42110/api/stats

# Test Ollama embeddings directly
curl http://192.168.1.58:11434/api/embeddings -d '{"model": "nomic-embed-text", "prompt": "test"}'

# Check service logs for errors
docker-compose logs -f
```

## Rollback Plan

If issues occur, rollback to Khoj:

```bash
ssh nuc-1

# Stop semantic search
cd ~/services/semantic_search
docker-compose down

# Restore Khoj
cd ~
docker-compose up -d

# Verify Khoj health
curl http://localhost:42110

# Revert Slack bot import (if changed)
# No changes needed if using KhojClient alias
```

## Performance Baseline

Expected metrics after deployment:

- **Initial indexing**: ~100-200 docs in ~2-5 minutes
- **Search latency**: 200-500ms per query
- **Memory usage**: ~500MB base + ~1KB per document
- **File watch latency**: 5-10 seconds (debounced)

## Success Criteria

- [x] Service starts without errors
- [x] Health check returns "healthy"
- [x] Initial indexing completes within 5 minutes
- [x] Search returns relevant results
- [x] File watching detects new/modified files
- [x] Slack bot successfully queries service
- [x] No performance degradation compared to Khoj
