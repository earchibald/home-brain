# Semantic Search Service

ChromaDB-based semantic search service for the Brain Assistant knowledge mesh.

## Architecture

- **embedder.py**: Ollama client for generating nomic-embed-text embeddings (384 dimensions)
- **vector_store.py**: ChromaDB wrapper for vector storage and retrieval
- **indexer.py**: File system indexer with watchdog for real-time monitoring
- **search_api.py**: FastAPI service providing REST API

## API Endpoints

### `GET /api/search`
Search for documents semantically similar to query.

**Parameters:**
- `q`: Search query (required)
- `limit`: Number of results (default: 3, max: 10)

**Response:**
```json
[
  {
    "entry": "Document snippet (200 chars)...",
    "file": "path/to/file.md",
    "score": 0.95
  }
]
```

### `GET /api/health`
Check service health.

**Response:**
```json
{
  "status": "healthy",
  "ollama": true,
  "documents": 42
}
```

### `POST /api/update?force=true`
Trigger full re-index (force=true) or check continuous indexing status.

### `GET /api/stats`
Get index statistics.

## Deployment

### Docker (Recommended)

```bash
cd services/semantic_search
docker-compose up -d
```

Service runs on port **42110** (same as Khoj for drop-in replacement).

### Local Development

```bash
cd services/semantic_search
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows
pip install -r requirements.txt
python search_api.py
```

## Configuration

Environment variables (see `docker-compose.yml`):

- `OLLAMA_URL`: Ollama API URL (default: `http://192.168.1.58:11434`)
- `EMBEDDING_MODEL`: Model name (default: `nomic-embed-text`)
- `BRAIN_PATH`: Path to brain directory (default: `/home/earchibald/brain`)
- `CHROMA_PERSIST_DIR`: ChromaDB data directory (default: `./chroma_data`)
- `WATCH_FILES`: Enable file watching (default: `true`)

## Features

- **Real-time indexing**: Watches files with 5-second debounce
- **Supported formats**: Markdown (`.md`), text (`.txt`), PDF (`.pdf`)
- **Chunking**: 1000-character chunks with 200-character overlap
- **API compatibility**: Drop-in replacement for Khoj `/api/search` endpoint
- **Graceful degradation**: Clients can continue without search if service unavailable

## Migration from Khoj

1. Deploy semantic search service
2. Verify health: `curl http://192.168.1.195:42110/api/health`
3. Test search: `curl "http://192.168.1.195:42110/api/search?q=test"`
4. Update client code (optional - API compatible)
5. Stop Khoj containers: `docker-compose down` (in NUC-1 ~/)
6. Remove Khoj cron job: `crontab -e` and delete reindex line

## Monitoring

Health check via cron (same pattern as Khoj):

```bash
* * * * * curl -f http://localhost:42110/api/health || /usr/local/bin/notify.sh "Search Service Down" "Semantic search unhealthy" "high"
```

## Performance

- **Indexing**: ~100 docs/min (depends on Ollama throughput)
- **Search latency**: ~200-500ms (embedding generation + vector search)
- **Memory**: ~500MB base + ~1KB per document chunk
- **Storage**: ~4KB per document chunk (ChromaDB persistence)
