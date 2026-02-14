"""
File handler for downloading and extracting text from various file types.
"""

from typing import Union
import requests
from slack_bot.exceptions import (
    UnsupportedFileTypeError,
    FileDownloadError,
    FileExtractionError,
)


# Supported file types for text extraction
SUPPORTED_FILE_TYPES = {'txt', 'md', 'pdf'}
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB max for extracted text


def download_file_from_slack(url: str, token: str) -> bytes:
    """
    Download a file from Slack using authenticated URL.

    Args:
        url: File URL (url_private_download from Slack)
        token: Slack bot token for authentication

    Returns:
        File content as bytes

    Raises:
        FileDownloadError: If download fails
    """
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        raise FileDownloadError(f"Failed to download file from Slack: {e}")
    except Exception as e:
        raise FileDownloadError(f"Unexpected error during file download: {e}")


def extract_pdf_text(pdf_content: bytes) -> str:
    """
    Extract text from PDF content.

    Args:
        pdf_content: PDF file content as bytes

    Returns:
        Extracted text as string

    Raises:
        FileExtractionError: If extraction fails
    """
    try:
        from PyPDF2 import PdfReader
        import io

        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except ImportError:
        raise FileExtractionError(
            "PyPDF2 not installed. Install with: pip install PyPDF2"
        )
    except Exception as e:
        raise FileExtractionError(f"Failed to extract text from PDF: {e}")


def extract_text_content(
    file_content: bytes, file_type: str
) -> str:
    """
    Extract text content from a file.

    Args:
        file_content: File content as bytes
        file_type: File type (txt, md, pdf, etc.)

    Returns:
        Extracted text as string, truncated to MAX_FILE_SIZE

    Raises:
        UnsupportedFileTypeError: If file type not supported
        FileExtractionError: If extraction fails
    """
    # Validate file type
    if file_type not in SUPPORTED_FILE_TYPES:
        raise UnsupportedFileTypeError(
            f"File type '.{file_type}' not supported. "
            f"Supported types: {', '.join(SUPPORTED_FILE_TYPES)}"
        )

    try:
        if file_type == 'txt':
            # Plain text - decode directly
            text = file_content.decode('utf-8', errors='replace')

        elif file_type == 'md':
            # Markdown - decode directly (it's just text)
            text = file_content.decode('utf-8', errors='replace')

        elif file_type == 'pdf':
            # PDF - use PyPDF2 to extract
            text = extract_pdf_text(file_content)

        else:
            raise UnsupportedFileTypeError(f"File type '.{file_type}' not supported")

        # Truncate to max size if needed
        if len(text) > MAX_FILE_SIZE:
            # Leave room for truncation message
            truncation_msg = "\n\n[File truncated]"
            max_content = MAX_FILE_SIZE - len(truncation_msg)
            text = text[:max_content] + truncation_msg

        return text

    except (UnsupportedFileTypeError, FileExtractionError):
        raise
    except Exception as e:
        raise FileExtractionError(f"Failed to extract text from .{file_type} file: {e}")
