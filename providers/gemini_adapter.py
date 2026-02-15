"""
Google Gemini API provider adapter.

Requires GOOGLE_API_KEY environment variable.
"""

import os
import google.generativeai as genai
from providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    """
    Adapter for Google Gemini API.

    Requires GOOGLE_API_KEY environment variable to be set.
    """

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable must be set for Gemini provider"
            )

        genai.configure(api_key=api_key)
        self.id = "gemini"
        self.name = "Google Gemini"

    def list_models(self) -> list[str]:
        """
        Returns available Gemini models.

        Returns:
            list[str]: List of Gemini model names
        """
        # Hardcoded common Gemini models for now
        # In future, could query API for available models
        return [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
        ]

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Generate text using Gemini API.

        Args:
            prompt: User prompt/question
            system_prompt: Optional system instructions

        Returns:
            str: Generated response
        """
        try:
            # Use first available model
            models = self.list_models()
            model_name = models[0] if models else "gemini-1.5-flash"

            model = genai.GenerativeModel(model_name)

            # Combine system prompt and user prompt
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            response = model.generate_content(full_prompt)
            return response.text
        except Exception:
            return "Error generating response"

    def health_check(self) -> bool:
        """
        Quick health check - verifies API key is set.

        Returns:
            bool: True if API key is configured
        """
        return os.getenv("GOOGLE_API_KEY") is not None
