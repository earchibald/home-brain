"""FastAPI service for semantic search API."""
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Dict, Optional, Any
import logging
import asyncio
import os
import aiohttp

from .embedder import OllamaEmbedder
from .vector_store import VectorStore
from .indexer import BrainIndexer

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Brain Semantic Search", version="1.0.0")

# Global instances (initialized on startup)
embedder: Optional[OllamaEmbedder] = None
vector_store: Optional[VectorStore] = None
indexer: Optional[BrainIndexer] = None

# Configuration (read from environment variables with defaults)
CONFIG = {
    "ollama_url": os.getenv("OLLAMA_URL", "http://192.168.1.58:11434"),
    "embedding_model": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
    "brain_path": os.getenv("BRAIN_PATH", "/home/earchibald/brain"),
    "chroma_persist_dir": os.getenv("CHROMA_PERSIST_DIR", "./chroma_data"),
    "watch_files": os.getenv("WATCH_FILES", "true").lower() == "true",
    "ntfy_url": os.getenv("NTFY_URL", "https://ntfy.sh"),
    "ntfy_topic": os.getenv("NTFY_TOPIC", "")
}


async def _send_startup_notification() -> None:
    """Send a startup notification if NTFY_TOPIC is configured."""
    topic = CONFIG.get("ntfy_topic", "").strip()
    if not topic:
        return

    url = CONFIG.get("ntfy_url", "https://ntfy.sh").rstrip("/")
    notify_url = f"{url}/{topic}"
    payload = "Semantic search service started and ready"

    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                notify_url,
                headers={
                    "Title": "Semantic Search",
                    "Priority": "3"
                },
                data=payload,
                timeout=10
            )
    except Exception as e:
        logger.warning(f"Startup notification failed: {e}")


def configure(config: Dict[str, Any]):
    """Override default configuration.
    
    Args:
        config: Configuration dictionary
    """
    CONFIG.update(config)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global embedder, vector_store, indexer
    
    logger.info("Starting semantic search service")
    
    # Initialize embedder
    embedder = OllamaEmbedder(
        base_url=CONFIG["ollama_url"],
        model=CONFIG["embedding_model"]
    )
    
    # Check Ollama health
    if not await embedder.health_check():
        logger.warning(f"Ollama service not available at {CONFIG['ollama_url']}")
    else:
        logger.info("Ollama service is healthy")
    
    # Initialize vector store
    vector_store = VectorStore(persist_directory=CONFIG["chroma_persist_dir"])
    logger.info(f"Vector store initialized with {vector_store.get_document_count()} documents")
    
    # Initialize indexer
    indexer = BrainIndexer(
        brain_path=CONFIG["brain_path"],
        embedder=embedder,
        vector_store=vector_store,
        watch_files=CONFIG["watch_files"]
    )
    
    # Start file watching
    if CONFIG["watch_files"]:
        indexer.start_watching()
        
    # Perform initial indexing in background
    asyncio.create_task(indexer.index_all())

    # Send startup notification if configured
    await _send_startup_notification()
    
    logger.info("Semantic search service started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    if indexer:
        indexer.stop_watching()
    if embedder:
        await embedder.close()
    logger.info("Semantic search service stopped")


@app.get("/")
async def root():
    """Root endpoint for health checks."""
    return {"status": "running", "service": "Brain Semantic Search"}


@app.get("/api/health")
async def health():
    """Health check endpoint.
    
    Returns:
        Health status
    """
    ollama_healthy = await embedder.health_check() if embedder else False
    doc_count = vector_store.get_document_count() if vector_store else 0
    
    return JSONResponse({
        "status": "healthy" if ollama_healthy else "degraded",
        "ollama": ollama_healthy,
        "documents": doc_count
    })


@app.get("/api/search")
async def search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(3, description="Number of results", ge=1, le=10)
) -> List[Dict[str, Any]]:
    """Search for documents semantically similar to the query.
    
    Args:
        q: Search query text
        limit: Maximum number of results to return (default: 3)
        
    Returns:
        List of search results with 'entry', 'file', 'score' keys
        
    Raises:
        HTTPException: If search fails
    """
    if not embedder or not vector_store:
        raise HTTPException(
            status_code=503, 
            detail="Search service not initialized"
        )
        
    try:
        # Generate query embedding
        logger.info(f"Search query: {q}")
        query_embedding = await embedder.embed_text(q)
        
        # Search vector store
        results = vector_store.search(query_embedding, n_results=limit)
        
        logger.info(f"Found {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update")
async def update_index(force: bool = Query(False, description="Force full re-index")):
    """Trigger index update.
    
    Args:
        force: If True, perform full re-index
        
    Returns:
        Update status
    """
    if not indexer:
        raise HTTPException(
            status_code=503, 
            detail="Indexer not initialized"
        )
        
    if force:
        logger.info("Triggering full re-index")
        asyncio.create_task(indexer.index_all())
        return {"status": "full_reindex_started"}
    else:
        return {"status": "continuous_indexing_active"}


@app.get("/api/stats")
async def stats():
    """Get statistics about the index.
    
    Returns:
        Index statistics
    """
    if not vector_store:
        raise HTTPException(
            status_code=503, 
            detail="Vector store not initialized"
        )
        
    doc_count = vector_store.get_document_count()
    
    return {
        "documents": doc_count,
        "brain_path": CONFIG["brain_path"],
        "embedding_model": CONFIG["embedding_model"],
        "file_watching": CONFIG["watch_files"]
    }


if __name__ == "__main__":
    import uvicorn
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the service
    uvicorn.run(app, host="0.0.0.0", port=42110)
