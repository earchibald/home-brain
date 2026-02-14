"""
Streaming handler for processing chunks from Ollama and finalizing responses.
"""

from typing import Optional


def process_stream_chunk(chunk: str) -> str:
    """
    Process a single chunk from the streaming response.

    Args:
        chunk: A chunk of text from the streaming response

    Returns:
        Processed chunk ready for display/concatenation
    """
    # Basic processing: return chunk as-is
    # Could add logic here for token cleaning, emoji handling, etc.
    return chunk


def finalize_stream_response(partial_content: str) -> str:
    """
    Finalize a streamed response, ensuring it's complete and well-formed.

    Args:
        partial_content: The accumulated streaming content

    Returns:
        Finalized response string
    """
    # Clean up any incomplete tokens or markers
    content = partial_content.strip()

    # Remove any incomplete token markers
    if content.endswith('[['):
        content = content[:-2]

    return content
