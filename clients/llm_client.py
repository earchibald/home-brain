"""
Ollama Client - LLM inference client for Mac Mini (192.168.1.58:11434)
"""

import httpx
import logging
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Chat message for Ollama"""
    role: str  # "user", "assistant", "system"
    content: str


class OllamaClient:
    """Async client for Ollama API on Mac Mini (192.168.1.58:11434)"""

    def __init__(
        self, 
        base_url: str = "http://192.168.1.58:11434",
        model: str = "llama3.2",
        timeout: int = 60
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = httpx.Timeout(timeout)
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _ensure_client(self):
        """Ensure async client is initialized"""
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str:
        """
        Generate text completion
        
        Args:
            prompt: Input prompt
            model: Model to use (defaults to self.model)
            max_tokens: Max tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            stream: Whether to stream response
            
        Returns:
            Generated text
        """
        await self._ensure_client()
        
        model = model or self.model
        
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": model,
                "prompt": prompt,
                "num_prediction": max_tokens,
                "temperature": temperature,
                "stream": stream,
            }
            
            if stream:
                # For streaming, we'd need to handle SSE
                logger.warning("Streaming not fully implemented, using non-streaming")
                payload["stream"] = False
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            result = data.get("response", "")
            
            logger.info(f"Generated {len(result)} characters with {model}")
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"Ollama completion error: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error in completion: {e}")
            return ""

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Chat-style completion with message history
        
        Args:
            messages: List of Message objects (conversation history)
            model: Model to use
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt to prepend
            
        Returns:
            Assistant response
        """
        await self._ensure_client()
        
        model = model or self.model
        
        try:
            # Build message list
            msg_list = []
            
            if system_prompt:
                msg_list.append({"role": "system", "content": system_prompt})
            
            for msg in messages:
                msg_list.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": model,
                "messages": msg_list,
                "num_predict": max_tokens,
                "temperature": temperature,
                "stream": False,
            }
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            result = data.get("message", {}).get("content", "")
            
            logger.info(f"Chat completion with {model} returned {len(result)} chars")
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"Ollama chat error: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error in chat: {e}")
            return ""

    async def advice(
        self,
        topic: str,
        context: str,
        specialization: str = "general"
    ) -> str:
        """
        Generate personalized advice using context
        
        Args:
            topic: Topic requiring advice (e.g., "time management", "ADHD strategies")
            context: Background context from brain (past notes, patterns)
            specialization: Type of advice (ADHD, Work, Learning, general)
            
        Returns:
            Personalized advice
        """
        system_prompts = {
            "ADHD": """You are an ADHD coach. Provide practical, evidence-based strategies 
for ADHD management. Keep advice brief (2-3 sentences), actionable, and considerate of 
executive dysfunction. Reference the user's past patterns and successes when available.""",
            
            "Work": """You are a work organization consultant. Provide strategies for 
project management, prioritization, and focus. Be concise and practical. Tailor advice 
to the user's work patterns and challenges.""",
            
            "Learning": """You are a learning coach. Provide study strategies, concept 
explanations, and learning techniques. Match advice to the user's demonstrated learning 
style. Keep explanations clear and actionable.""",
            
            "general": """You are a helpful personal assistant. Provide thoughtful, 
personalized advice based on the user's context. Be concise, practical, and empathetic.""",
        }
        
        system = system_prompts.get(specialization, system_prompts["general"])
        
        prompt = f"""Topic: {topic}

Context from my brain:
{context}

Provide brief, actionable advice tailored to my situation."""
        
        messages = [Message(role="user", content=prompt)]
        
        return await self.chat(
            messages,
            system_prompt=system,
            max_tokens=300
        )

    async def summarize(
        self,
        text: str,
        length: str = "medium",
        focus: Optional[str] = None,
    ) -> str:
        """
        Summarize text
        
        Args:
            text: Text to summarize
            length: "short" (1-2 sentences), "medium" (paragraph), "long" (detailed)
            focus: Optional focus area for summary
            
        Returns:
            Summary
        """
        length_guide = {
            "short": "Provide a 1-2 sentence summary.",
            "medium": "Provide a paragraph-length summary (100-150 words).",
            "long": "Provide a detailed summary (200-300 words).",
        }
        
        guide = length_guide.get(length, length_guide["medium"])
        focus_str = f"\nFocus on: {focus}" if focus else ""
        
        prompt = f"""{guide}{focus_str}

Text to summarize:
---
{text}
---

Summary:"""
        
        result = await self.complete(prompt, max_tokens=500)
        return result.strip()

    async def extract_themes(self, text: str, num_themes: int = 5) -> List[str]:
        """
        Extract main themes/topics from text
        
        Args:
            text: Text to analyze
            num_themes: Number of themes to extract
            
        Returns:
            List of theme strings
        """
        prompt = f"""Extract the {num_themes} main themes or topics from this text.
List them as a simple bullet list with no additional text.

Text:
---
{text}
---

Themes:"""
        
        result = await self.complete(prompt, max_tokens=200)
        
        # Parse bullet list
        themes = [
            line.strip("- ").strip() 
            for line in result.split("\n") 
            if line.strip().startswith("-")
        ]
        
        return themes[:num_themes]

    async def embeddings(self, text: str, model: str = "nomic-embed-text") -> List[float]:
        """
        Generate embeddings for text using nomic-embed-text
        
        Args:
            text: Text to embed
            model: Embedding model to use
            
        Returns:
            Embedding vector
        """
        await self._ensure_client()
        
        try:
            url = f"{self.base_url}/api/embeddings"
            payload = {
                "model": model,
                "prompt": text,
            }
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            embedding = data.get("embedding", [])
            
            logger.info(f"Generated embedding with dimension {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            return []

    async def health_check(self) -> bool:
        """Check if Ollama is reachable and has models"""
        await self._ensure_client()
        
        try:
            response = await self.client.get(f"{self.base_url}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def list_models(self) -> List[str]:
        """Get list of available models on Ollama"""
        await self._ensure_client()
        
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            
            logger.info(f"Available models: {models}")
            return models
            
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    async def close(self):
        """Close the async client"""
        if self.client:
            await self.client.aclose()


# Convenience factory function
async def get_ollama_client(
    base_url: str = "http://192.168.1.58:11434",
    model: str = "llama3.2"
) -> OllamaClient:
    """Factory function to create and return an OllamaClient"""
    return OllamaClient(base_url, model)
