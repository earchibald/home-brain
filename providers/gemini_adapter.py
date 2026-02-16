"""
Google Gemini API provider adapter.

Supports dynamic API key configuration and quota handling.
"""

import os
import logging
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class QuotaExhaustedError(Exception):
    """Raised when Gemini daily quota is exhausted (429 error)."""
    
    def __init__(self, model: str, message: str = None):
        self.model = model
        self.message = message or f"Gemini quota exhausted for model {model}. Try again tomorrow or switch models."
        super().__init__(self.message)


@dataclass
class GeminiModel:
    """Gemini model configuration."""
    id: str
    display_name: str
    api_name: str
    
    
# Available Gemini models
GEMINI_MODELS = [
    GeminiModel(id="gemini-pro", display_name="Gemini 2.0 Pro", api_name="gemini-2.0-flash"),
    GeminiModel(id="gemini-flash", display_name="Gemini 2.0 Flash", api_name="gemini-2.0-flash"),
    GeminiModel(id="gemini-flash-lite", display_name="Gemini 2.0 Flash-Lite", api_name="gemini-2.0-flash-lite"),
]


class GeminiProvider:
    """
    Adapter for Google Gemini API with dynamic API key and quota handling.
    
    Supports runtime API key configuration (not just env vars) and
    gracefully handles 429 quota errors.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Optional API key. Falls back to GOOGLE_API_KEY env var.
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self._genai = None
        self._current_model: str = "gemini-flash"  # Default to flash
        
        self.id = "gemini"
        self.name = "Google Gemini"
        
        if self._api_key:
            self._configure()
    
    def _configure(self):
        """Configure the genai library with current API key."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._genai = genai
        except ImportError:
            logger.error("google-generativeai package not installed. Run: pip install google-generativeai")
            self._genai = None
    
    @property
    def api_key(self) -> Optional[str]:
        """Get current API key (masked)."""
        if not self._api_key:
            return None
        return f"...{self._api_key[-4:]}" if len(self._api_key) > 4 else "****"
    
    def set_api_key(self, api_key: str):
        """
        Set or update the API key at runtime.
        
        Args:
            api_key: New Gemini API key
        """
        self._api_key = api_key
        self._configure()
        logger.info(f"Gemini API key updated: ...{api_key[-4:]}")
    
    def set_model(self, model_id: str):
        """
        Set the current model.
        
        Args:
            model_id: Model ID (gemini-pro, gemini-flash, gemini-flash-lite)
        """
        valid_ids = [m.id for m in GEMINI_MODELS]
        if model_id not in valid_ids:
            raise ValueError(f"Invalid model: {model_id}. Valid: {valid_ids}")
        self._current_model = model_id
        logger.info(f"Gemini model set to: {model_id}")
    
    def _get_api_model_name(self, model_id: str = None) -> str:
        """Get the actual API model name for a model ID."""
        model_id = model_id or self._current_model
        for m in GEMINI_MODELS:
            if m.id == model_id:
                return m.api_name
        return "gemini-2.0-flash"  # Default fallback

    def list_models(self) -> List[str]:
        """
        Returns available Gemini models.
        
        Returns:
            List of model display names
        """
        return [m.display_name for m in GEMINI_MODELS]
    
    def list_model_ids(self) -> List[str]:
        """Returns model IDs (for use with set_model)."""
        return [m.id for m in GEMINI_MODELS]

    def generate(self, prompt: str, system_prompt: str = None, model_id: str = None) -> str:
        """
        Generate text using Gemini API.
        
        Args:
            prompt: User prompt/question
            system_prompt: Optional system instructions
            model_id: Optional specific model to use
            
        Returns:
            Generated response
            
        Raises:
            QuotaExhaustedError: If 429 quota error received
            ValueError: If no API key configured
        """
        if not self._api_key:
            raise ValueError("Gemini API key not configured. Use /apikey command to set it.")
        
        if not self._genai:
            self._configure()
            if not self._genai:
                return "Error: google-generativeai package not installed"
        
        api_model_name = self._get_api_model_name(model_id)
        
        try:
            model = self._genai.GenerativeModel(
                api_model_name,
                system_instruction=system_prompt if system_prompt else None
            )
            
            response = model.generate_content(prompt)
            
            logger.info(f"Gemini ({api_model_name}) response: {len(response.text)} chars")
            return response.text
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Check for quota/rate limit errors
            if "429" in str(e) or "quota" in error_str or "rate" in error_str or "resource_exhausted" in error_str:
                logger.warning(f"Gemini quota exhausted: {e}")
                raise QuotaExhaustedError(model_id or self._current_model, str(e))
            
            logger.error(f"Gemini generation error: {e}")
            return f"Error generating response: {e}"
    
    async def chat(
        self,
        messages: List,
        model_id: str = None,
        system_prompt: str = None,
    ) -> str:
        """
        Chat-style completion compatible with OllamaClient interface.
        
        Args:
            messages: List of Message objects
            model_id: Optional model ID
            system_prompt: Optional system prompt
            
        Returns:
            Assistant response
        """
        # Build conversation prompt from messages
        conversation = []
        for msg in messages:
            role = getattr(msg, 'role', msg.get('role', 'user'))
            content = getattr(msg, 'content', msg.get('content', ''))
            if role == "system":
                # Prepend system messages to system_prompt
                system_prompt = f"{system_prompt}\n\n{content}" if system_prompt else content
            else:
                conversation.append(f"{role.upper()}: {content}")
        
        prompt = "\n\n".join(conversation)
        return self.generate(prompt, system_prompt=system_prompt, model_id=model_id)

    def health_check(self) -> bool:
        """
        Check if Gemini is configured and reachable.
        
        Returns:
            True if API key is set
        """
        return bool(self._api_key)
    
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self._api_key)
