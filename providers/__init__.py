"""
LLM Provider adapters for dynamic model source switching.

Implements the Adapter/Strategy pattern for switching between:
- Local Ollama instances
- Remote Ollama instances
- Cloud APIs (Gemini, Anthropic)
"""

from providers.base import BaseProvider

__all__ = ["BaseProvider"]
