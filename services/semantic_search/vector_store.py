"""Vector store using ChromaDB for semantic search."""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional, Tuple
import logging
import hashlib
from pathlib import Path

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB-based vector store for document embeddings."""
    
    def __init__(self, persist_directory: str = "./chroma_data"):
        """Initialize the vector store.
        
        Args:
            persist_directory: Directory to persist ChromaDB data
        """
        self.persist_directory = persist_directory
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False
        ))
        
        # Create or get collection
        self.collection = self.client.get_or_create_collection(
            name="brain_documents",
            metadata={"description": "Personal knowledge base documents"}
        )
        
    def _generate_doc_id(self, file_path: str, chunk_index: int = 0) -> str:
        """Generate deterministic document ID from file path and chunk index.
        
        Args:
            file_path: Path to the source file
            chunk_index: Index of the chunk within the file
            
        Returns:
            Unique document ID
        """
        content = f"{file_path}:{chunk_index}"
        return hashlib.md5(content.encode()).hexdigest()
        
    def add_documents(
        self, 
        texts: List[str], 
        embeddings: List[List[float]], 
        file_paths: List[str],
        chunk_indices: Optional[List[int]] = None
    ):
        """Add documents to the vector store.
        
        Args:
            texts: List of document texts
            embeddings: List of embedding vectors
            file_paths: List of source file paths
            chunk_indices: Optional list of chunk indices (default: all 0)
        """
        if chunk_indices is None:
            chunk_indices = [0] * len(texts)
            
        # Generate document IDs
        doc_ids = [
            self._generate_doc_id(path, idx) 
            for path, idx in zip(file_paths, chunk_indices)
        ]
        
        # Build metadata for each document
        metadatas = [
            {"file_path": path, "chunk_index": idx}
            for path, idx in zip(file_paths, chunk_indices)
        ]
        
        try:
            self.collection.add(
                ids=doc_ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            logger.info(f"Added {len(texts)} documents to vector store")
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise
            
    def search(
        self, 
        query_embedding: List[float], 
        n_results: int = 3
    ) -> List[Dict[str, any]]:
        """Search for similar documents.
        
        Args:
            query_embedding: Query embedding vector
            n_results: Number of results to return
            
        Returns:
            List of search results with 'entry', 'file', 'score' keys
        """
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            # Transform ChromaDB results to API format
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    # Truncate to ~200 characters (snippet length)
                    snippet = doc[:200] + "..." if len(doc) > 200 else doc
                    
                    formatted_results.append({
                        "entry": snippet,
                        "file": results['metadatas'][0][i]['file_path'],
                        "score": results['distances'][0][i]
                    })
                    
            return formatted_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
            
    def delete_by_file_path(self, file_path: str):
        """Delete all documents associated with a file path.
        
        Args:
            file_path: Path to the file to remove
        """
        try:
            # Query for all documents with this file path
            results = self.collection.get(
                where={"file_path": file_path}
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"Deleted {len(results['ids'])} documents for {file_path}")
                
        except Exception as e:
            logger.error(f"Failed to delete documents for {file_path}: {e}")
            
    def clear_all(self):
        """Clear all documents from the collection."""
        try:
            # Delete the collection and recreate it
            self.client.delete_collection(name="brain_documents")
            self.collection = self.client.get_or_create_collection(
                name="brain_documents",
                metadata={"description": "Personal knowledge base documents"}
            )
            logger.info("Cleared all documents from vector store")
        except Exception as e:
            logger.error(f"Failed to clear vector store: {e}")
            
    def get_document_count(self) -> int:
        """Get the total number of documents in the collection.
        
        Returns:
            Number of documents
        """
        return self.collection.count()
