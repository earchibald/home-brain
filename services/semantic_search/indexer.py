"""File system indexer with real-time monitoring for semantic search."""
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Set
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
import fnmatch

from .embedder import OllamaEmbedder
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process documents for indexing."""
    
    SUPPORTED_EXTENSIONS = {'.md', '.txt', '.pdf'}
    CHUNK_SIZE = 1000  # Characters per chunk
    CHUNK_OVERLAP = 200  # Overlap between chunks
    
    @staticmethod
    def should_index(file_path: Path) -> bool:
        """Determine if a file should be indexed.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file should be indexed
        """
        return file_path.suffix.lower() in DocumentProcessor.SUPPORTED_EXTENSIONS
        
    @staticmethod
    def read_file(file_path: Path) -> Optional[str]:
        """Read file content.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File content as string, or None if read fails
        """
        try:
            if file_path.suffix.lower() == '.pdf':
                # For PDF, use PyPDF2 (already used in file_handler.py)
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        text = []
                        for page in reader.pages:
                            text.append(page.extract_text() or '')
                        return '\n'.join(text)
                except Exception as e:
                    logger.error(f"Failed to read PDF {file_path}: {e}")
                    return None
            else:
                # Text files
                return file_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return None
            
    @classmethod
    def chunk_text(cls, text: str) -> List[str]:
        """Split text into overlapping chunks.
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        if len(text) <= cls.CHUNK_SIZE:
            return [text]
            
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + cls.CHUNK_SIZE
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - cls.CHUNK_OVERLAP
            
        return chunks


class BrainIndexerEventHandler(FileSystemEventHandler):
    """Handle file system events for real-time indexing."""
    
    def __init__(self, indexer: 'BrainIndexer'):
        self.indexer = indexer
        self.pending_files: Set[str] = set()
        self.debounce_task: Optional[asyncio.Task] = None
        self.debounce_delay = 5.0  # 5 second debounce
        
    def on_created(self, event: FileSystemEvent):
        """Handle file creation."""
        if not event.is_directory:
            self._schedule_index(event.src_path)
            
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification."""
        if not event.is_directory:
            self._schedule_index(event.src_path)
            
    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion."""
        if not event.is_directory:
            asyncio.create_task(self.indexer.remove_file(Path(event.src_path)))
            
    def _schedule_index(self, file_path: str):
        """Schedule file for indexing with debouncing.
        
        Args:
            file_path: Path to the file
        """
        path = Path(file_path)
        if DocumentProcessor.should_index(path):
            self.pending_files.add(file_path)
            
            # Cancel existing debounce task
            if self.debounce_task and not self.debounce_task.done():
                self.debounce_task.cancel()
                
            # Schedule new debounce task
            self.debounce_task = asyncio.create_task(self._debounced_index())
            
    async def _debounced_index(self):
        """Execute indexing after debounce delay."""
        await asyncio.sleep(self.debounce_delay)
        
        if self.pending_files:
            files = list(self.pending_files)
            self.pending_files.clear()
            
            logger.info(f"Indexing {len(files)} files after debounce")
            for file_path in files:
                await self.indexer.index_file(Path(file_path))


class BrainIndexer:
    """Index brain documents with real-time file monitoring."""
    
    def __init__(
        self, 
        brain_path: str,
        embedder: OllamaEmbedder,
        vector_store: VectorStore,
        watch_files: bool = True
    ):
        """Initialize the indexer.
        
        Args:
            brain_path: Path to brain directory
            embedder: Embedder for generating embeddings
            vector_store: Vector store for storing embeddings
            watch_files: Enable real-time file watching
        """
        self.brain_path = Path(brain_path)
        self.embedder = embedder
        self.vector_store = vector_store
        self.watch_files = watch_files
        
        self.observer: Optional[Observer] = None
        self.event_handler: Optional[BrainIndexerEventHandler] = None
        
    async def index_file(self, file_path: Path) -> bool:
        """Index a single file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if indexing succeeded
        """
        if not DocumentProcessor.should_index(file_path):
            return False
            
        logger.info(f"Indexing {file_path}")
        
        # Read file content
        content = DocumentProcessor.read_file(file_path)
        if not content:
            logger.warning(f"Skipping {file_path}: empty or unreadable")
            return False
            
        # Remove old entries for this file
        relative_path = str(file_path.relative_to(self.brain_path))
        self.vector_store.delete_by_file_path(relative_path)
        
        # Chunk the content
        chunks = DocumentProcessor.chunk_text(content)
        
        # Generate embeddings
        try:
            embeddings = await self.embedder.embed_batch(chunks)
        except Exception as e:
            logger.error(f"Failed to generate embeddings for {file_path}: {e}")
            return False
            
        # Store in vector store
        file_paths = [relative_path] * len(chunks)
        chunk_indices = list(range(len(chunks)))
        
        self.vector_store.add_documents(
            texts=chunks,
            embeddings=embeddings,
            file_paths=file_paths,
            chunk_indices=chunk_indices
        )
        
        return True
        
    async def remove_file(self, file_path: Path):
        """Remove a file from the index.
        
        Args:
            file_path: Path to the file
        """
        try:
            relative_path = str(file_path.relative_to(self.brain_path))
            self.vector_store.delete_by_file_path(relative_path)
            logger.info(f"Removed {file_path} from index")
        except Exception as e:
            logger.error(f"Failed to remove {file_path}: {e}")
            
    async def index_all(self):
        """Index all files in the brain directory."""
        logger.info(f"Starting full index of {self.brain_path}")
        start_time = time.time()
        
        # Find all indexable files
        files = []
        for ext in DocumentProcessor.SUPPORTED_EXTENSIONS:
            files.extend(self.brain_path.rglob(f"*{ext}"))
            
        logger.info(f"Found {len(files)} files to index")
        
        # Index each file
        success_count = 0
        for file_path in files:
            if await self.index_file(file_path):
                success_count += 1
                
        elapsed = time.time() - start_time
        logger.info(
            f"Indexing complete: {success_count}/{len(files)} files indexed "
            f"in {elapsed:.1f}s"
        )
        
        doc_count = self.vector_store.get_document_count()
        logger.info(f"Total documents in vector store: {doc_count}")
        
    def start_watching(self):
        """Start watching for file changes."""
        if not self.watch_files:
            return
            
        self.event_handler = BrainIndexerEventHandler(self)
        self.observer = Observer()
        self.observer.schedule(
            self.event_handler, 
            str(self.brain_path), 
            recursive=True
        )
        self.observer.start()
        logger.info(f"Started watching {self.brain_path}")
        
    def stop_watching(self):
        """Stop watching for file changes."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped file watching")
