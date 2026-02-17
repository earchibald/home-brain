"""FastAPI service for semantic search API."""
from fastapi import FastAPI, Query, HTTPException, Path as PathParam, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import logging
import asyncio
import os
import re
import aiohttp

from .embedder import OllamaEmbedder
from .vector_store import VectorStore
from .indexer import BrainIndexer
from .index_control import IndexControl, GATE_READONLY, GATE_READWRITE, VALID_GATES

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Brain Semantic Search", version="1.0.0")

# Global instances (initialized on startup)
embedder: Optional[OllamaEmbedder] = None
vector_store: Optional[VectorStore] = None
indexer: Optional[BrainIndexer] = None
index_control: Optional[IndexControl] = None

# Configuration (read from environment variables with defaults)
CONFIG = {
    "ollama_url": os.getenv("OLLAMA_URL", "http://m1-mini.local:11434"),
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
    global embedder, vector_store, indexer, index_control
    
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

    # Initialize index control (state lives alongside chroma data)
    index_control = IndexControl(data_dir=CONFIG["chroma_persist_dir"])
    
    # Initialize indexer with index_control
    indexer = BrainIndexer(
        brain_path=CONFIG["brain_path"],
        embedder=embedder,
        vector_store=vector_store,
        watch_files=CONFIG["watch_files"],
        index_control=index_control,
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


# ======================================================================
# Document Management Endpoints
# ======================================================================


class GateRequest(BaseModel):
    """Request body for setting a directory gate."""
    directory: str = Field(..., description="Directory path relative to brain root")
    mode: str = Field(..., description="Gate mode: 'readonly' or 'readwrite'")


class GatesUpdateRequest(BaseModel):
    """Request body for bulk gate update."""
    gates: Dict[str, str] = Field(..., description="Mapping of directory → mode")


@app.get("/api/documents")
async def list_documents(
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    folder: Optional[str] = Query(None, description="Filter by folder prefix"),
):
    """List indexed documents (paged).

    Returns a page of files from the in-memory registry along with total count.
    """
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")

    items, total = index_control.get_registered_files(
        offset=offset, limit=limit, folder_filter=folder
    )
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@app.get("/api/documents/{file_path:path}")
async def get_document_info(file_path: str):
    """Get index info for a single document."""
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")

    info = index_control.get_file_info(file_path)
    if info is None:
        raise HTTPException(status_code=404, detail=f"File not in index: {file_path}")
    return info


@app.post("/api/documents/{file_path:path}/ignore")
async def ignore_document(file_path: str):
    """Remove a document from the index and add it to the ignore list.

    The document will be re-indexed automatically when its content or
    modification time changes on disk.
    """
    if not index_control or not vector_store:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Verify the file exists in the registry
    info = index_control.get_file_info(file_path)
    if info is None:
        raise HTTPException(status_code=404, detail=f"File not in index: {file_path}")

    # Get current disk signature for the ignore entry
    from pathlib import Path as _Path
    abs_path = _Path(CONFIG["brain_path"]) / file_path
    if abs_path.exists():
        stat = abs_path.stat()
        mtime, size = stat.st_mtime, stat.st_size
    else:
        # File already gone from disk — still remove from index
        mtime, size = 0.0, 0

    # Remove vectors from ChromaDB
    vector_store.delete_by_file_path(file_path)

    # Add to ignore list
    index_control.ignore_file(file_path, mtime=mtime, size=size)

    # Remove from registry
    index_control.unregister_file(file_path)
    index_control.persist_registry()

    return {"status": "ignored", "file": file_path}


@app.post("/api/documents/{file_path:path}/delete")
async def delete_document(file_path: str):
    """Delete a document: remove from index AND delete the source file.

    Respects directory gates. If the file is in a *readonly* directory, the
    request is rejected — use the /ignore endpoint instead.
    """
    if not index_control or not vector_store:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Gate check
    if not index_control.can_delete_file(file_path):
        raise HTTPException(
            status_code=403,
            detail=f"File is in a read-only directory. Use /ignore instead.",
        )

    # Remove vectors
    vector_store.delete_by_file_path(file_path)

    # Remove from registry
    index_control.unregister_file(file_path)
    index_control.persist_registry()

    # Delete source file from disk
    from pathlib import Path as _Path
    abs_path = _Path(CONFIG["brain_path"]) / file_path
    deleted_from_disk = False
    if abs_path.exists():
        try:
            abs_path.unlink()
            deleted_from_disk = True
            logger.info(f"Deleted source file: {abs_path}")
        except Exception as e:
            logger.error(f"Failed to delete source file {abs_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")

    return {
        "status": "deleted",
        "file": file_path,
        "deleted_from_disk": deleted_from_disk,
    }


# ======================================================================
# File Upload Endpoint
# ======================================================================


def _sanitize_path(path: str) -> str:
    """Sanitize file path to prevent traversal attacks.
    
    Raises:
        ValueError: If path is invalid or dangerous
    """
    # Remove leading/trailing slashes and whitespace
    path = path.strip().strip("/")
    
    # Split into components
    parts = path.split("/")
    
    # Check each component
    clean_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part in (".", ".."):
            raise ValueError(f"Invalid path component: {part}")
        if part.startswith("."):
            raise ValueError(f"Hidden files/directories not allowed: {part}")
        # Allow alphanumeric, hyphens, underscores, dots (for extensions)
        if not re.match(r'^[\w\-\.]+$', part):
            raise ValueError(f"Invalid characters in path: {part}")
        clean_parts.append(part)
    
    if not clean_parts:
        raise ValueError("Empty path")
    
    if len(clean_parts) > 5:
        raise ValueError("Path too deep: max 5 directory levels")
    
    return "/".join(clean_parts)


# Max upload size: 10MB
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


@app.post("/api/documents/upload")
async def upload_document(
    file_path: str = Form(..., description="Target path relative to brain root (e.g., 'notes/meeting.md')"),
    file: UploadFile = File(..., description="File to upload"),
    overwrite: bool = Form(False, description="Overwrite if file exists"),
):
    """Upload a file to the brain and trigger indexing.
    
    - Creates parent directories if they don't exist
    - Respects directory gates (cannot upload to readonly directories)
    - Triggers immediate indexing of the uploaded file
    """
    if not index_control or not vector_store or not indexer:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Sanitize and validate path
    try:
        clean_path = _sanitize_path(file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check gate permissions
    if not index_control.can_delete_file(clean_path):  # Same logic: readonly = no write
        raise HTTPException(
            status_code=403,
            detail=f"Directory is read-only. Cannot upload to this location.",
        )

    # Read file content (with size limit)
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB.",
        )

    # Build absolute path
    from pathlib import Path as _Path
    abs_path = _Path(CONFIG["brain_path"]) / clean_path

    # Check if file exists
    if abs_path.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"File already exists. Set overwrite=true to replace.",
        )

    # Create parent directories
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    try:
        abs_path.write_bytes(content)
        logger.info(f"Uploaded file: {abs_path} ({len(content)} bytes)")
    except Exception as e:
        logger.error(f"Failed to write file {abs_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")

    # Trigger indexing
    chunks_indexed = 0
    indexed = False
    try:
        success = await indexer.index_file(abs_path)
        if success:
            indexed = True
            # Get chunk count from vector store
            from .indexer import DocumentProcessor
            text = DocumentProcessor.read_file(abs_path)
            if text:
                chunks_indexed = len(DocumentProcessor.chunk_text(text))
        
        # Register in index control
        index_control.register_file(
            clean_path,
            mtime=abs_path.stat().st_mtime,
            size=len(content),
            chunks=chunks_indexed,
        )
        index_control.persist_registry()
    except Exception as e:
        logger.error(f"Indexing failed for {clean_path}: {e}")
        # File is saved, indexing will happen on next scan

    return {
        "status": "uploaded",
        "path": clean_path,
        "size": len(content),
        "chunks": chunks_indexed,
        "indexed": indexed,
    }


# ======================================================================
# Gate Configuration Endpoints
# ======================================================================


@app.get("/api/config/gates")
async def get_gates():
    """Return current directory gate configuration."""
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")
    return {"gates": index_control.get_gates()}


@app.post("/api/config/gates")
async def set_gate(req: GateRequest):
    """Set or update a single directory gate."""
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")

    if req.mode not in VALID_GATES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{req.mode}'. Must be one of: {', '.join(VALID_GATES)}",
        )

    try:
        index_control.set_gate(req.directory, req.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "directory": req.directory, "mode": req.mode}


@app.put("/api/config/gates")
async def replace_gates(req: GatesUpdateRequest):
    """Replace all gates with the provided mapping."""
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")

    # Validate all modes first
    for directory, mode in req.gates.items():
        if mode not in VALID_GATES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode '{mode}' for '{directory}'.",
            )

    # Clear existing and set new
    for existing_dir in list(index_control.get_gates().keys()):
        index_control.remove_gate(existing_dir)
    for directory, mode in req.gates.items():
        try:
            index_control.set_gate(directory, mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "gates": index_control.get_gates()}


@app.delete("/api/config/gates/{directory:path}")
async def remove_gate(directory: str):
    """Remove a gate for a directory."""
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")

    index_control.remove_gate(directory)
    return {"status": "ok", "directory": directory}


# ======================================================================
# Ignore List Endpoints
# ======================================================================


@app.get("/api/ignored")
async def list_ignored():
    """Return the current ignore list."""
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")
    return {"ignored": index_control.get_ignored_files()}


@app.delete("/api/ignored/{file_path:path}")
async def unignore(file_path: str):
    """Remove a file from the ignore list (manual re-enable).

    The file will be picked up on the next indexing pass.
    """
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")

    index_control.unignore_file(file_path)
    return {"status": "unignored", "file": file_path}


# ======================================================================
# Extended Stats
# ======================================================================


@app.get("/api/registry/stats")
async def registry_stats():
    """Detailed index statistics including gates and ignore counts."""
    if not index_control:
        raise HTTPException(status_code=503, detail="Index control not initialized")
    return index_control.get_registry_stats()


if __name__ == "__main__":
    import uvicorn
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the service
    uvicorn.run(app, host="0.0.0.0", port=9514)
