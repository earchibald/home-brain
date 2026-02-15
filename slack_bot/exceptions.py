"""
Custom exceptions for slack_bot file handling.
"""


class UnsupportedFileTypeError(Exception):
    """Raised when attempting to process an unsupported file type."""

    pass


class FileDownloadError(Exception):
    """Raised when file download from Slack fails."""

    pass


class FileExtractionError(Exception):
    """Raised when text extraction from file fails."""

    pass
