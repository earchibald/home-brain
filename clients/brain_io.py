"""
Brain I/O - File system operations for the brain folder on Syncthing
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BrainIO:
    """Async file operations for /home/earchibald/brain folder"""

    def __init__(self, brain_path: str = "/home/earchibald/brain"):
        self.brain_path = Path(brain_path)

        if not self.brain_path.exists():
            raise ValueError(f"Brain path does not exist: {brain_path}")

        if not self.brain_path.is_dir():
            raise ValueError(f"Brain path is not a directory: {brain_path}")

        logger.info(f"Initialized BrainIO with path: {brain_path}")

    async def read_file(self, relative_path: str) -> Optional[str]:
        """
        Read a file from the brain folder

        Args:
            relative_path: Path relative to brain_path (e.g., "journal/2026-02-14.md")

        Returns:
            File contents or None if not found
        """
        file_path = self.brain_path / relative_path

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return None

        if not file_path.is_file():
            logger.warning(f"Not a file: {file_path}")
            return None

        try:
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None, lambda: file_path.read_text(encoding="utf-8")
            )
            logger.info(f"Read file: {relative_path} ({len(content)} bytes)")
            return content
        except Exception as e:
            logger.error(f"Error reading file {relative_path}: {e}")
            return None

    async def write_file(
        self,
        relative_path: str,
        content: str,
        overwrite: bool = False,
        encoding: str = "utf-8",
    ) -> bool:
        """
        Write content to a file in the brain folder

        Args:
            relative_path: Path relative to brain_path
            content: Content to write
            overwrite: Whether to overwrite if file exists
            encoding: Text encoding

        Returns:
            True if successful, False otherwise
        """
        file_path = self.brain_path / relative_path

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.exists() and not overwrite:
            logger.warning(f"File exists and overwrite=False: {file_path}")
            return False

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: file_path.write_text(content, encoding=encoding)
            )
            logger.info(f"Wrote file: {relative_path} ({len(content)} bytes)")
            return True
        except Exception as e:
            logger.error(f"Error writing file {relative_path}: {e}")
            return False

    async def append_file(self, relative_path: str, content: str) -> bool:
        """
        Append content to an existing file (or create if not exists)

        Args:
            relative_path: Path relative to brain_path
            content: Content to append

        Returns:
            True if successful
        """
        file_path = self.brain_path / relative_path

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            loop = asyncio.get_event_loop()
            current = ""
            if file_path.exists():
                current = await self.read_file(relative_path) or ""

            new_content = current + content
            await loop.run_in_executor(
                None, lambda: file_path.write_text(new_content, encoding="utf-8")
            )
            logger.info(f"Appended to file: {relative_path} ({len(content)} bytes)")
            return True
        except Exception as e:
            logger.error(f"Error appending to file {relative_path}: {e}")
            return False

    async def list_files(
        self, pattern: str = "**/*.md", relative: bool = True
    ) -> List[str]:
        """
        List files in brain folder matching pattern

        Args:
            pattern: Glob pattern (e.g., "journal/*.md", "**/*.txt")
            relative: Return relative paths if True, absolute if False

        Returns:
            List of file paths
        """
        try:
            loop = asyncio.get_event_loop()

            async def glob_files():
                matches = list(self.brain_path.glob(pattern))
                if relative:
                    return [
                        str(m.relative_to(self.brain_path))
                        for m in matches
                        if m.is_file()
                    ]
                else:
                    return [str(m) for m in matches if m.is_file()]

            files = await loop.run_in_executor(
                None,
                lambda: (
                    glob_files() if asyncio.iscoroutinefunction(glob_files) else None
                ),
            )

            # Sync version if async didn't work
            matches = list(self.brain_path.glob(pattern))
            if relative:
                files = [
                    str(m.relative_to(self.brain_path)) for m in matches if m.is_file()
                ]
            else:
                files = [str(m) for m in matches if m.is_file()]

            logger.info(f"Found {len(files)} files matching pattern {pattern}")
            return files

        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []

    async def ensure_folder(self, relative_path: str) -> bool:
        """
        Ensure a folder exists in the brain directory

        Args:
            relative_path: Folder path relative to brain_path

        Returns:
            True if folder exists or was created
        """
        folder_path = self.brain_path / relative_path

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: folder_path.mkdir(parents=True, exist_ok=True)
            )
            logger.info(f"Ensured folder: {relative_path}")
            return True
        except Exception as e:
            logger.error(f"Error ensuring folder {relative_path}: {e}")
            return False

    async def get_file_timestamp(self, relative_path: str) -> Optional[float]:
        """Get modification time of a file"""
        file_path = self.brain_path / relative_path

        if not file_path.exists():
            return None

        try:
            return file_path.stat().st_mtime
        except Exception as e:
            logger.error(f"Error getting file timestamp: {e}")
            return None

    async def get_recent_files(
        self, hours: int = 24, pattern: str = "**/*.md"
    ) -> List[str]:
        """
        Get recently modified files

        Args:
            hours: How many hours back
            pattern: File pattern to match

        Returns:
            List of recent files (relative paths)
        """
        from datetime import timedelta

        cutoff_time = (datetime.now() - timedelta(hours=hours)).timestamp()
        recent = []

        try:
            files = await self.list_files(pattern)

            for file_path in files:
                mtime = await self.get_file_timestamp(file_path)
                if mtime and mtime > cutoff_time:
                    recent.append(file_path)

            recent.sort(
                reverse=True, key=lambda x: asyncio.run(self.get_file_timestamp(x)) or 0
            )
            logger.info(f"Found {len(recent)} recent files from last {hours} hours")
            return recent

        except Exception as e:
            logger.error(f"Error getting recent files: {e}")
            return []

    def get_brain_path(self) -> Path:
        """Get the brain path as a Path object"""
        return self.brain_path

    def get_brain_path_str(self) -> str:
        """Get the brain path as a string"""
        return str(self.brain_path)


# Convenience factory function
def get_brain_io(brain_path: str = "/home/earchibald/brain") -> BrainIO:
    """Factory function to create and return a BrainIO instance"""
    return BrainIO(brain_path)
