"""
File handler for downloading and extracting text from various file types.
"""

import requests
import logging
from slack_bot.exceptions import (
    UnsupportedFileTypeError,
    FileDownloadError,
    FileExtractionError,
)

logger = logging.getLogger(__name__)


# Supported file types for text extraction
SUPPORTED_FILE_TYPES = {"txt", "md", "pdf"}
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
        # Try with Bearer token first, allow redirects
        logger.info(f"Downloading from Slack: {url[:100]}...")
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)

        # If unauthorized, try without auth (some URLs don't need it)
        if response.status_code == 401:
            logger.warning(
                "Bearer auth failed (401), retrying without auth with redirects"
            )
            response = requests.get(url, timeout=30, allow_redirects=True)

        response.raise_for_status()

        # Detect empty responses
        if not response.content:
            raise FileDownloadError("Empty response from Slack file download")

        # Detect HTML error/login pages (redirect landed on a web page, not a file)
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            logger.error(
                f"Got HTML response instead of file (redirected to {response.url[:100]})"
            )
            raise FileDownloadError(
                f"Got HTML response instead of file content — "
                f"possible auth redirect to {response.url[:100]}"
            )

        logger.info(
            f"Downloaded {len(response.content)} bytes from Slack (final status: {response.status_code}, url: {response.url[:100]})"
        )
        return response.content
    except FileDownloadError:
        raise
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


def extract_text_content(file_content: bytes, file_type: str) -> str:
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
        if file_type == "txt":
            # Plain text - decode directly
            text = file_content.decode("utf-8", errors="replace")
            logger.info(f"Extracted text from .txt file: first 100 chars: {text[:100]}")

        elif file_type == "md":
            # Markdown - decode directly (it's just text)
            text = file_content.decode("utf-8", errors="replace")
            logger.info(f"Extracted text from .md file: first 100 chars: {text[:100]}")

        elif file_type == "pdf":
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
