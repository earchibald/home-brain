"""
Ollama client with streaming support.
"""

from typing import Optional, Generator
import requests
import json


class OllamaStreamingClient:
    """Ollama client with streaming response support."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        """
        Initialize streaming Ollama client.

        Args:
            model: Model name
            base_url: Ollama base URL
        """
        self.model = model
        self.base_url = base_url

    def generate(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs
    ) -> Optional[Generator[str, None, None]]:
        """
        Generate response from Ollama with optional streaming.

        Args:
            prompt: Input prompt
            stream: Whether to stream the response
            **kwargs: Additional arguments

        Returns:
            Generator of response chunks if streaming, response string otherwise
        """
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream
        }

        response = requests.post(url, json=payload, stream=stream)

        if stream:
            return self._parse_streaming_response(response)
        else:
            data = response.json()
            return data.get("response", "")

    def _parse_streaming_response(
        self, response
    ) -> Generator[str, None, None]:
        """Parse streaming response from Ollama."""
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                chunk = data.get("response", "")
                if chunk:
                    yield chunk


class OllamaClient:
    """Standard Ollama client with fallback support."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama client.

        Args:
            model: Model name
            base_url: Ollama base URL
        """
        self.model = model
        self.base_url = base_url

    def generate(
        self,
        prompt: str,
        stream: bool = False,
        fallback: bool = False,
        **kwargs
    ) -> Optional[str]:
        """
        Generate response from Ollama with optional fallback.

        Args:
            prompt: Input prompt
            stream: Whether to attempt streaming
            fallback: Whether to fall back to non-streaming on failure
            **kwargs: Additional arguments

        Returns:
            Response string
        """
        url = f"{self.base_url}/api/generate"

        # Try streaming first if requested
        if stream and fallback:
            try:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True
                }
                response = requests.post(url, json=payload, stream=True, timeout=30)

                # Accumulate streaming response
                accumulated = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        accumulated += data.get("response", "")
                return accumulated
            except Exception:
                # Fall back to non-streaming
                pass

        # Non-streaming request
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        return data.get("response", "")
