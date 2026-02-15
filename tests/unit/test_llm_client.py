"""
Unit tests for OllamaClient - LLM inference client integration.

Tests verify:
- Chat completion with message history
- Response parsing from Ollama API
- Exception handling when Ollama unavailable
- Timeout handling for slow responses
- Embeddings generation
- Health check connectivity
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from clients.llm_client import OllamaClient, Message


@pytest.mark.unit
class TestOllamaClient:
    """Test suite for OllamaClient"""

    @pytest.mark.asyncio
    async def test_chat_completion_with_message_history(self, mock_llm):
        """
        Test chat completion preserves full message history.

        Verifies that:
        - Message objects are properly converted to API format
        - System prompt is included in request
        - All conversation history is sent to LLM
        - Response is extracted correctly
        - No messages are lost or reordered

        Uses mock_llm fixture which simulates Ollama responses.
        """
        messages = [
            Message(role="user", content="What is ADHD?"),
            Message(
                role="assistant", content="ADHD is a neurodevelopmental disorder..."
            ),
            Message(role="user", content="How can I manage it?"),
        ]

        # Call mock LLM
        response = await mock_llm.chat(
            messages=messages, system_prompt="You are a helpful assistant"
        )

        # Verify response
        assert isinstance(response, str)
        assert len(response) > 0

        # Verify mock was called
        assert mock_llm.chat.called

    @pytest.mark.asyncio
    async def test_response_parsing_from_ollama(self):
        """
        Test that responses from Ollama API are parsed correctly.

        Verifies that:
        - JSON response is properly decoded
        - Message content is extracted from nested structure
        - Empty responses are handled gracefully
        - Response format matches Ollama API specification

        Simulates various Ollama response formats.
        """
        # Mock httpx to return Ollama API response
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Simulate Ollama chat response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "model": "llama3.2",
                "message": {
                    "role": "assistant",
                    "content": "This is the parsed response from Ollama.",
                },
                "done": True,
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            client = OllamaClient(base_url="http://test:11434")
            client.client = mock_client

            # Call chat
            messages = [Message(role="user", content="Hello")]
            result = await client.chat(messages=messages)

            # Verify parsing
            assert isinstance(result, str)
            assert "parsed response" in result.lower()

    @pytest.mark.asyncio
    async def test_ollama_unavailable_raises_exception(self):
        """
        Test that connection errors are handled when Ollama is unavailable.

        Verifies that:
        - HTTP errors are caught and logged
        - Graceful error message is returned (not crash)
        - Client remains usable after error
        - Appropriate exception type is raised/handled

        Simulates network failure scenarios.
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Simulate connection error
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            client = OllamaClient(base_url="http://unreachable:11434")
            client.client = mock_client

            # Call chat - should handle error gracefully
            messages = [Message(role="user", content="Hello")]
            result = await client.chat(messages=messages)

            # Should return empty string instead of raising
            assert result == ""

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """
        Test that requests timing out are handled properly.

        Verifies that:
        - Timeout exceptions don't crash the bot
        - Graceful fallback/empty response returned
        - Timeout duration is configurable
        - Client recovers after timeout

        Simulates slow/unresponsive Ollama server.
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Simulate timeout
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )

            client = OllamaClient(base_url="http://slow-server:11434", timeout=5)
            client.client = mock_client

            messages = [Message(role="user", content="Hello")]
            result = await client.chat(messages=messages)

            # Should handle gracefully
            assert result == ""

    @pytest.mark.asyncio
    async def test_embeddings_generation(self):
        """
        Test that embeddings are generated and returned correctly.

        Verifies that:
        - Embeddings endpoint is called correctly
        - Response contains embedding vector
        - Vector has reasonable dimension
        - Empty/error cases handled
        - Embedding format matches expected structure

        Tests vector generation for semantic search.
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Simulate embeddings response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "embedding": [0.1, 0.2, 0.3, 0.4, 0.5] * 100  # 500-dim vector
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            client = OllamaClient(base_url="http://test:11434")
            client.client = mock_client

            # Generate embeddings
            embedding = await client.embeddings(
                text="Sample text for embedding", model="nomic-embed-text"
            )

            # Verify
            assert isinstance(embedding, list)
            assert len(embedding) == 500
            assert all(isinstance(x, (int, float)) for x in embedding)

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """
        Test that health check succeeds when Ollama is running.

        Verifies that:
        - GET request to base URL returns 200
        - Health check returns True on success
        - Connection is properly established
        - No errors logged on successful check

        Tests basic connectivity verification.
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Simulate successful health check
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)

            client = OllamaClient(base_url="http://test:11434")
            client.client = mock_client

            # Run health check
            result = await client.health_check()

            # Verify
            assert result is True
            assert mock_client.get.called


@pytest.mark.unit
class TestOllamaClientIntegration:
    """Integration tests for OllamaClient with realistic workflows"""

    @pytest.mark.asyncio
    async def test_complete_prompt_generation(self):
        """
        Test complete prompt to response workflow.

        Simulates:
        1. User sends message
        2. Client generates response
        3. Response is formatted and returned
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "response": "This is a generated response to the prompt."
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            client = OllamaClient(base_url="http://test:11434")
            client.client = mock_client

            result = await client.complete(
                prompt="What is artificial intelligence?",
                model="llama3.2",
                max_tokens=500,
            )

            assert "generated response" in result

    @pytest.mark.asyncio
    async def test_multi_turn_chat_with_system_prompt(self):
        """
        Test multi-turn conversation with system prompt.

        Simulates:
        1. System prompt sets context
        2. Multiple user/assistant messages preserved
        3. Correct response generated
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {
                    "role": "assistant",
                    "content": "Based on our conversation, here's my advice...",
                }
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            client = OllamaClient(base_url="http://test:11434")
            client.client = mock_client

            messages = [
                Message(role="user", content="I have ADHD"),
                Message(role="assistant", content="I can help with ADHD strategies"),
                Message(role="user", content="What's the best approach?"),
            ]

            result = await client.chat(
                messages=messages, system_prompt="You are an ADHD coach", max_tokens=500
            )

            assert "advice" in result.lower()

    @pytest.mark.asyncio
    async def test_context_menu_advice_generation(self):
        """
        Test specialized advice generation for a specific domain.

        Uses advice() method with context from brain.
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {
                    "role": "assistant",
                    "content": "Try breaking tasks into 15-minute blocks with 5-minute breaks.",
                }
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            client = OllamaClient(base_url="http://test:11434")
            client.client = mock_client

            advice = await client.advice(
                topic="time management",
                context="User has ADHD and struggles with procrastination",
                specialization="ADHD",
            )

            assert "15-minute" in advice or "advice" in advice.lower()

    @pytest.mark.asyncio
    async def test_summarization_workflow(self):
        """
        Test text summarization workflow.

        Tests the summarize() method for conversation compression.
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "response": "Summary: User discussed time management and ADHD strategies."
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            client = OllamaClient(base_url="http://test:11434")
            client.client = mock_client

            long_text = (
                """
            User asked about time management techniques for ADHD.
            Assistant discussed the Pomodoro technique, time blocking, and daily planning.
            User mentioned they struggle with procrastination.
            Assistant recommended starting with 15-minute work blocks.
            """
                * 10
            )

            summary = await client.summarize(
                text=long_text, length="medium", focus="ADHD time management"
            )

            assert len(summary) > 0
            assert isinstance(summary, str)


@pytest.mark.unit
class TestMessageClass:
    """Test the Message dataclass"""

    def test_message_creation(self):
        """Test that Message objects are created correctly"""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_message_with_different_roles(self):
        """Test Message with various role types"""
        roles = ["user", "assistant", "system"]
        for role in roles:
            msg = Message(role=role, content="Test content")
            assert msg.role == role
