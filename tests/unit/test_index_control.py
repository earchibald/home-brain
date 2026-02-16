"""
Unit tests for IndexControl — gating, ignore list, and file registry.
"""

import json
import os
import pytest
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.semantic_search.index_control import (
    IndexControl,
    GATE_READONLY,
    GATE_READWRITE,
    _normalize_relpath,
)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def control_dir(tmp_path):
    """Temporary directory for IndexControl state files."""
    return str(tmp_path / "control_data")


@pytest.fixture
def ic(control_dir):
    """Fresh IndexControl instance."""
    return IndexControl(data_dir=control_dir)


# ======================================================================
# Path normalization
# ======================================================================


class TestNormalizeRelpath:
    @pytest.mark.unit
    def test_basic(self):
        assert _normalize_relpath("journal/note.md") == "journal/note.md"

    @pytest.mark.unit
    def test_strips_leading_slash(self):
        # os.path.normpath keeps leading / — our validator rejects it
        with pytest.raises(ValueError):
            _normalize_relpath("/etc/passwd")

    @pytest.mark.unit
    def test_rejects_traversal(self):
        with pytest.raises(ValueError):
            _normalize_relpath("../../etc/passwd")

    @pytest.mark.unit
    def test_collapses_double_slash(self):
        assert _normalize_relpath("journal//note.md") == "journal/note.md"


# ======================================================================
# Gates
# ======================================================================


class TestGates:
    @pytest.mark.unit
    def test_set_and_get(self, ic):
        ic.set_gate("journal", GATE_READONLY)
        assert ic.get_gates() == {"journal": GATE_READONLY}

    @pytest.mark.unit
    def test_invalid_mode(self, ic):
        with pytest.raises(ValueError):
            ic.set_gate("journal", "admin")

    @pytest.mark.unit
    def test_remove_gate(self, ic):
        ic.set_gate("journal", GATE_READONLY)
        ic.remove_gate("journal")
        assert ic.get_gates() == {}

    @pytest.mark.unit
    def test_gate_for_path_exact(self, ic):
        ic.set_gate("journal", GATE_READONLY)
        assert ic.gate_for_path("journal/note.md") == GATE_READONLY

    @pytest.mark.unit
    def test_gate_for_path_longest_prefix(self, ic):
        ic.set_gate("journal", GATE_READONLY)
        ic.set_gate("journal/private", GATE_READWRITE)
        assert ic.gate_for_path("journal/private/secret.md") == GATE_READWRITE
        assert ic.gate_for_path("journal/public.md") == GATE_READONLY

    @pytest.mark.unit
    def test_ungated_path(self, ic):
        ic.set_gate("journal", GATE_READONLY)
        assert ic.gate_for_path("projects/plan.md") is None

    @pytest.mark.unit
    def test_can_delete_file_readonly(self, ic):
        ic.set_gate("journal", GATE_READONLY)
        assert ic.can_delete_file("journal/note.md") is False

    @pytest.mark.unit
    def test_can_delete_file_readwrite(self, ic):
        ic.set_gate("projects", GATE_READWRITE)
        assert ic.can_delete_file("projects/plan.md") is True

    @pytest.mark.unit
    def test_can_delete_file_ungated(self, ic):
        assert ic.can_delete_file("random/file.md") is True

    @pytest.mark.unit
    def test_persistence(self, control_dir):
        ic1 = IndexControl(data_dir=control_dir)
        ic1.set_gate("journal", GATE_READONLY)

        ic2 = IndexControl(data_dir=control_dir)
        assert ic2.get_gates() == {"journal": GATE_READONLY}


# ======================================================================
# Ignore list
# ======================================================================


class TestIgnoreList:
    @pytest.mark.unit
    def test_ignore_and_check(self, ic):
        ic.ignore_file("journal/note.md", mtime=1000.0, size=500)
        assert ic.is_ignored("journal/note.md", current_signature=(1000.0, 500)) is True

    @pytest.mark.unit
    def test_not_ignored(self, ic):
        assert ic.is_ignored("journal/note.md", current_signature=(1000.0, 500)) is False

    @pytest.mark.unit
    def test_ignore_lifted_on_mtime_change(self, ic):
        ic.ignore_file("journal/note.md", mtime=1000.0, size=500)
        # File was modified (mtime changed)
        assert ic.is_ignored("journal/note.md", current_signature=(2000.0, 500)) is False
        # Entry should be removed
        assert ic.get_ignored_files() == {}

    @pytest.mark.unit
    def test_ignore_lifted_on_size_change(self, ic):
        ic.ignore_file("journal/note.md", mtime=1000.0, size=500)
        # File was modified (size changed)
        assert ic.is_ignored("journal/note.md", current_signature=(1000.0, 999)) is False

    @pytest.mark.unit
    def test_ignore_no_signature_stays_ignored(self, ic):
        ic.ignore_file("journal/note.md", mtime=1000.0, size=500)
        # No current signature → assume still ignored
        assert ic.is_ignored("journal/note.md", current_signature=None) is True

    @pytest.mark.unit
    def test_unignore(self, ic):
        ic.ignore_file("journal/note.md", mtime=1000.0, size=500)
        ic.unignore_file("journal/note.md")
        assert ic.is_ignored("journal/note.md", current_signature=(1000.0, 500)) is False

    @pytest.mark.unit
    def test_persistence(self, control_dir):
        ic1 = IndexControl(data_dir=control_dir)
        ic1.ignore_file("journal/note.md", mtime=1000.0, size=500)

        ic2 = IndexControl(data_dir=control_dir)
        assert ic2.is_ignored("journal/note.md", current_signature=(1000.0, 500)) is True


# ======================================================================
# File Registry
# ======================================================================


class TestFileRegistry:
    @pytest.mark.unit
    def test_register_and_list(self, ic):
        ic.register_file("journal/note.md", chunk_count=3, size=1024)
        ic.persist_registry()

        items, total = ic.get_registered_files()
        assert total == 1
        assert items[0]["path"] == "journal/note.md"
        assert items[0]["chunks"] == 3

    @pytest.mark.unit
    def test_unregister(self, ic):
        ic.register_file("journal/note.md", chunk_count=3, size=1024)
        ic.unregister_file("journal/note.md")
        ic.persist_registry()

        items, total = ic.get_registered_files()
        assert total == 0

    @pytest.mark.unit
    def test_pagination(self, ic):
        for i in range(25):
            ic.register_file(f"docs/file_{i:03d}.md", chunk_count=1, size=100)
        ic.persist_registry()

        page1, total = ic.get_registered_files(offset=0, limit=10)
        assert total == 25
        assert len(page1) == 10

        page2, _ = ic.get_registered_files(offset=10, limit=10)
        assert len(page2) == 10

        page3, _ = ic.get_registered_files(offset=20, limit=10)
        assert len(page3) == 5

    @pytest.mark.unit
    def test_folder_filter(self, ic):
        ic.register_file("journal/note.md", chunk_count=1, size=100)
        ic.register_file("projects/plan.md", chunk_count=2, size=200)
        ic.persist_registry()

        items, total = ic.get_registered_files(folder_filter="journal")
        assert total == 1
        assert items[0]["path"] == "journal/note.md"

    @pytest.mark.unit
    def test_file_info(self, ic):
        ic.register_file("journal/note.md", chunk_count=3, size=1024)
        info = ic.get_file_info("journal/note.md")
        assert info is not None
        assert info["chunks"] == 3
        assert info["size"] == 1024

    @pytest.mark.unit
    def test_file_info_not_found(self, ic):
        assert ic.get_file_info("nonexistent.md") is None

    @pytest.mark.unit
    def test_registry_stats(self, ic):
        ic.register_file("journal/note.md", chunk_count=3, size=1024)
        ic.register_file("projects/plan.md", chunk_count=5, size=2048)
        ic.persist_registry()

        stats = ic.get_registry_stats()
        assert stats["total_files"] == 2
        assert stats["total_chunks"] == 8

    @pytest.mark.unit
    def test_gate_in_file_info(self, ic):
        ic.set_gate("journal", GATE_READONLY)
        ic.register_file("journal/note.md", chunk_count=1, size=100)
        info = ic.get_file_info("journal/note.md")
        assert info["gate"] == GATE_READONLY

    @pytest.mark.unit
    def test_persistence(self, control_dir):
        ic1 = IndexControl(data_dir=control_dir)
        ic1.register_file("journal/note.md", chunk_count=3, size=1024)
        ic1.persist_registry()

        ic2 = IndexControl(data_dir=control_dir)
        items, total = ic2.get_registered_files()
        assert total == 1
