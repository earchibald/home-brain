"""
Index Control — Centralized state for document gating, ignore lists, and file registry.

Owns .index_control.json (persisted to disk). The Semantic Search Service is the
sole writer; the Slack bot interacts only through the API layer.

State file schema (`.index_control.json`):
{
    "gates": {
        "/journal": "readonly",
        "/projects": "readwrite"
    },
    "ignored": {
        "journal/2026-01-01.md": {
            "mtime": 1706745600.0,
            "size": 1234,
            "ignored_at": "2026-02-15T10:00:00"
        }
    },
    "version": 1
}

File Registry (in-memory, persisted to `.index_registry.json`):
{
    "files": {
        "journal/2026-01-01.md": {
            "chunks": 3,
            "indexed_at": "2026-02-15T10:00:00",
            "size": 1234
        }
    }
}
"""

import copy
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTROL_FILE = ".index_control.json"
REGISTRY_FILE = ".index_registry.json"

GATE_READONLY = "readonly"
GATE_READWRITE = "readwrite"
VALID_GATES = {GATE_READONLY, GATE_READWRITE}

_EMPTY_CONTROL: Dict[str, Any] = {
    "version": 1,
    "gates": {},
    "ignored": {},
}

_EMPTY_REGISTRY: Dict[str, Any] = {
    "files": {},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_relpath(path: str) -> str:
    """Normalize a relative path: strip leading/trailing slashes, collapse ..."""
    cleaned = os.path.normpath(path)
    # Reject traversal attempts
    if cleaned.startswith("..") or cleaned.startswith("/"):
        raise ValueError(f"Invalid relative path: {path}")
    return cleaned


def _file_signature(file_path: Path) -> Tuple[float, int]:
    """Return (mtime, size) for a file on disk."""
    stat = file_path.stat()
    return (stat.st_mtime, stat.st_size)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# IndexControl
# ---------------------------------------------------------------------------


class IndexControl:
    """Centralized state manager for index gating, ignoring, and file registry.

    Thread-safety: This class is expected to be used from a single async event
    loop in the search service process. All mutations are followed by an
    immediate persist to disk so that state survives restarts.
    """

    def __init__(self, data_dir: str):
        """
        Args:
            data_dir: Directory where control/registry JSON files are stored
                      (typically the chroma_data or service working dir).
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._control_path = self.data_dir / CONTROL_FILE
        self._registry_path = self.data_dir / REGISTRY_FILE

        # In-memory state
        self._control: Dict[str, Any] = _EMPTY_CONTROL.copy()
        self._registry: Dict[str, Any] = _EMPTY_REGISTRY.copy()

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        """Load state from disk (tolerates missing / corrupt files)."""
        self._control = self._read_json(self._control_path, _EMPTY_CONTROL)
        self._registry = self._read_json(self._registry_path, _EMPTY_REGISTRY)
        # Ensure required keys
        self._control.setdefault("version", 1)
        self._control.setdefault("gates", {})
        self._control.setdefault("ignored", {})
        self._registry.setdefault("files", {})
        logger.info(
            "IndexControl loaded: %d gates, %d ignored, %d registered files",
            len(self._control["gates"]),
            len(self._control["ignored"]),
            len(self._registry["files"]),
        )

    def _persist_control(self):
        self._write_json(self._control_path, self._control)

    def _persist_registry(self):
        self._write_json(self._registry_path, self._registry)

    @staticmethod
    def _read_json(path: Path, default: Dict) -> Dict:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to read %s: %s — using defaults", path, e)
        # Deep copy to avoid sharing mutable nested dicts across instances
        return copy.deepcopy(default)

    @staticmethod
    def _write_json(path: Path, data: Dict):
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            tmp.replace(path)  # atomic on POSIX
        except Exception as e:
            logger.error("Failed to persist %s: %s", path, e)

    # ------------------------------------------------------------------
    # Gates
    # ------------------------------------------------------------------

    def get_gates(self) -> Dict[str, str]:
        """Return current gate mapping {directory_prefix: 'readonly'|'readwrite'}."""
        return dict(self._control["gates"])

    def set_gate(self, directory: str, mode: str):
        """Set a gate for a directory prefix.

        Args:
            directory: Path prefix relative to brain root (e.g. "journal").
            mode: "readonly" or "readwrite".
        """
        if mode not in VALID_GATES:
            raise ValueError(f"Invalid gate mode: {mode}. Must be one of {VALID_GATES}")
        key = _normalize_relpath(directory)
        self._control["gates"][key] = mode
        self._persist_control()
        logger.info("Gate set: %s → %s", key, mode)

    def remove_gate(self, directory: str):
        """Remove a gate (directory becomes ungated — defaults to readwrite)."""
        key = _normalize_relpath(directory)
        self._control["gates"].pop(key, None)
        self._persist_control()
        logger.info("Gate removed: %s", key)

    def gate_for_path(self, relative_path: str) -> Optional[str]:
        """Return the gate mode that applies to a file path, or None if ungated.

        Matches the *longest* prefix. For example if gates are
        {"journal": "readonly", "journal/private": "readwrite"} then
        "journal/private/note.md" → "readwrite".
        """
        normalized = _normalize_relpath(relative_path)
        best_match: Optional[str] = None
        best_length = 0
        for prefix, mode in self._control["gates"].items():
            if normalized == prefix or normalized.startswith(prefix + "/"):
                if len(prefix) > best_length:
                    best_match = mode
                    best_length = len(prefix)
        return best_match

    def can_delete_file(self, relative_path: str) -> bool:
        """Return True if the file's gate permits physical deletion."""
        gate = self.gate_for_path(relative_path)
        # Ungated or readwrite → deletion allowed
        return gate != GATE_READONLY

    # ------------------------------------------------------------------
    # Ignore list
    # ------------------------------------------------------------------

    def is_ignored(self, relative_path: str, current_signature: Optional[Tuple[float, int]] = None) -> bool:
        """Check if a file is in the ignore list with an unchanged signature.

        If the file's on-disk signature (mtime, size) has changed since it was
        ignored, the ignore entry is automatically lifted and the file becomes
        eligible for re-indexing.

        Args:
            relative_path: Path relative to brain root.
            current_signature: (mtime, size) of the file on disk right now.
                               If None, the file is treated as ignored regardless.

        Returns:
            True if the file should be skipped during indexing.
        """
        key = _normalize_relpath(relative_path)
        entry = self._control["ignored"].get(key)
        if entry is None:
            return False

        if current_signature is None:
            # Can't verify — assume still ignored
            return True

        stored_mtime = entry.get("mtime")
        stored_size = entry.get("size")
        cur_mtime, cur_size = current_signature

        if cur_mtime != stored_mtime or cur_size != stored_size:
            # File has changed — lift the ignore automatically
            logger.info("Ignore lifted for %s (signature changed)", key)
            del self._control["ignored"][key]
            self._persist_control()
            return False

        return True

    def ignore_file(self, relative_path: str, mtime: float, size: int):
        """Add a file to the ignore list with its current signature.

        Args:
            relative_path: Path relative to brain root.
            mtime: File modification time at the moment of ignoring.
            size: File size in bytes at the moment of ignoring.
        """
        key = _normalize_relpath(relative_path)
        self._control["ignored"][key] = {
            "mtime": mtime,
            "size": size,
            "ignored_at": _now_iso(),
        }
        self._persist_control()
        logger.info("Ignored: %s (mtime=%.1f, size=%d)", key, mtime, size)

    def unignore_file(self, relative_path: str):
        """Remove a file from the ignore list (manual re-enable)."""
        key = _normalize_relpath(relative_path)
        if key in self._control["ignored"]:
            del self._control["ignored"][key]
            self._persist_control()
            logger.info("Un-ignored: %s", key)

    def get_ignored_files(self) -> Dict[str, Any]:
        """Return the full ignore list."""
        return dict(self._control["ignored"])

    # ------------------------------------------------------------------
    # File Registry (in-memory + periodic persist)
    # ------------------------------------------------------------------

    def register_file(self, relative_path: str, chunk_count: int, size: int):
        """Record that a file has been indexed."""
        key = _normalize_relpath(relative_path)
        self._registry["files"][key] = {
            "chunks": chunk_count,
            "indexed_at": _now_iso(),
            "size": size,
        }
        # Persist happens in batch via persist_registry() to avoid I/O per file
        # during bulk indexing. Callers should call persist_registry() when done.

    def unregister_file(self, relative_path: str):
        """Remove a file from the registry."""
        key = _normalize_relpath(relative_path)
        self._registry["files"].pop(key, None)

    def get_registered_files(
        self,
        offset: int = 0,
        limit: int = 50,
        folder_filter: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return a paged list of registered files.

        Args:
            offset: Pagination offset.
            limit: Page size (max items to return).
            folder_filter: Optional folder prefix to filter by.

        Returns:
            (items, total_count) where items is a list of dicts with keys:
            path, chunks, indexed_at, size, gate.
        """
        all_files = self._registry["files"]
        items = []
        for path, meta in sorted(all_files.items()):
            if folder_filter:
                norm_filter = _normalize_relpath(folder_filter)
                if not (path == norm_filter or path.startswith(norm_filter + "/")):
                    continue
            gate = self.gate_for_path(path) or "ungated"
            items.append({
                "path": path,
                "chunks": meta.get("chunks", 0),
                "indexed_at": meta.get("indexed_at", ""),
                "size": meta.get("size", 0),
                "gate": gate,
            })

        total = len(items)
        page = items[offset: offset + limit]
        return page, total

    def get_file_info(self, relative_path: str) -> Optional[Dict[str, Any]]:
        """Return registry info for a single file, or None."""
        key = _normalize_relpath(relative_path)
        meta = self._registry["files"].get(key)
        if meta is None:
            return None
        gate = self.gate_for_path(key) or "ungated"
        return {
            "path": key,
            "chunks": meta.get("chunks", 0),
            "indexed_at": meta.get("indexed_at", ""),
            "size": meta.get("size", 0),
            "gate": gate,
        }

    def get_registry_stats(self) -> Dict[str, Any]:
        """Summary statistics for the registry."""
        files = self._registry["files"]
        total_chunks = sum(m.get("chunks", 0) for m in files.values())
        return {
            "total_files": len(files),
            "total_chunks": total_chunks,
            "gates": self.get_gates(),
            "ignored_count": len(self._control["ignored"]),
        }

    def persist_registry(self):
        """Flush registry to disk. Call after bulk indexing."""
        self._persist_registry()
