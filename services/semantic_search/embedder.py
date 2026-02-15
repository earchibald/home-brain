"""Embedder for generating text embeddings via Ollama."""
import asyncio
from typing import List, Optional
import aiohttp
import logging

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """Client for generating embeddings using Ollama's nomic-embed-text model."""
    
    def __init__(self, base_url: str = "http://192.168.1.58:11434", model: str = "nomic-embed-text"):
        """Initialize the embedder.
        
        Args:
            base_url: Base URL for Ollama API
            model: Embedding model to use (default: nomic-embed-text)
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def _ensure_session(self):
        """Ensure aiohttp session is initialized."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            
    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text string.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (384 dimensions for nomic-embed-text)
            
        Raises:
            Exception: If embedding generation fails
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        
        try:
            async with self.session.post(url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                return data["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise
            
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in parallel.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        tasks = [self.embed_text(text) for text in texts]
        return await asyncio.gather(*tasks)
        
    async def health_check(self) -> bool:
        """Check if Ollama service is available.
        
        Returns:
            True if service is healthy, False otherwise
        """
        await self._ensure_session()
        
        try:
            async with self.session.get(self.base_url) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
