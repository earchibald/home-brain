"""
Unit tests for Slack index manager UI builders and parsers.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slack_bot.index_manager import (
    build_index_dashboard,
    build_document_browser,
    build_delete_confirmation,
    build_gate_setup,
    parse_gate_config_text,
    PAGE_SIZE,
    ACTION_BROWSE,
    ACTION_DOC_IGNORE,
    ACTION_DOC_DELETE,
    ACTION_CONFIRM_DELETE,
    ACTION_CANCEL_DELETE,
    ACTION_SHOW_SETUP,
    ACTION_REINDEX,
    ACTION_PAGE_NEXT,
    ACTION_PAGE_PREV,
    ACTION_SETUP_SUBMIT,
)


# ======================================================================
# Dashboard
# ======================================================================


class TestDashboard:
    @pytest.mark.unit
    def test_dashboard_structure(self):
        stats = {
            "total_files": 42,
            "total_chunks": 200,
            "gates": {"journal": "readonly", "projects": "readwrite"},
            "ignored_count": 3,
        }
        blocks = build_index_dashboard(stats)
        assert len(blocks) > 0
        # Must have header, stats section, gates, divider, actions
        types = [b["type"] for b in blocks]
        assert "header" in types
        assert "divider" in types
        assert "actions" in types

    @pytest.mark.unit
    def test_dashboard_empty_stats(self):
        blocks = build_index_dashboard({})
        assert len(blocks) > 0

    @pytest.mark.unit
    def test_dashboard_action_ids(self):
        blocks = build_index_dashboard({"total_files": 0, "total_chunks": 0, "gates": {}, "ignored_count": 0})
        action_block = [b for b in blocks if b["type"] == "actions"][0]
        action_ids = [e["action_id"] for e in action_block["elements"]]
        assert ACTION_BROWSE in action_ids
        assert ACTION_SHOW_SETUP in action_ids
        assert ACTION_REINDEX in action_ids


# ======================================================================
# Document Browser
# ======================================================================


class TestDocumentBrowser:
    @pytest.mark.unit
    def test_browser_with_documents(self):
        items = [
            {"path": "journal/note.md", "chunks": 3, "size": 1024, "gate": "readonly", "indexed_at": "2026-02-15"},
            {"path": "projects/plan.md", "chunks": 5, "size": 2048, "gate": "readwrite", "indexed_at": "2026-02-15"},
        ]
        blocks = build_document_browser(items, total=2, offset=0, limit=10)
        assert len(blocks) > 0

        # Each doc should have a section + actions row
        text_blocks = [b for b in blocks if b["type"] == "section"]
        assert len(text_blocks) >= 2  # at least header + 2 doc sections

    @pytest.mark.unit
    def test_browser_readonly_no_delete(self):
        """Readonly gated documents should NOT have a delete button."""
        items = [{"path": "journal/note.md", "chunks": 1, "size": 100, "gate": "readonly", "indexed_at": ""}]
        blocks = build_document_browser(items, total=1, offset=0, limit=10)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        for ab in action_blocks:
            for el in ab["elements"]:
                assert el.get("action_id") != ACTION_DOC_DELETE, (
                    "Delete button should not appear for readonly documents"
                )

    @pytest.mark.unit
    def test_browser_readwrite_has_delete(self):
        """Readwrite gated documents should have both ignore and delete."""
        items = [{"path": "projects/plan.md", "chunks": 1, "size": 100, "gate": "readwrite", "indexed_at": ""}]
        blocks = build_document_browser(items, total=1, offset=0, limit=10)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        all_action_ids = []
        for ab in action_blocks:
            for el in ab["elements"]:
                all_action_ids.append(el.get("action_id"))
        assert ACTION_DOC_IGNORE in all_action_ids
        assert ACTION_DOC_DELETE in all_action_ids

    @pytest.mark.unit
    def test_browser_empty(self):
        blocks = build_document_browser([], total=0, offset=0, limit=10)
        texts = [b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section"]
        assert any("No documents" in t for t in texts)

    @pytest.mark.unit
    def test_browser_pagination_next(self):
        items = [{"path": f"doc_{i}.md", "chunks": 1, "size": 100, "gate": "ungated", "indexed_at": ""} for i in range(10)]
        blocks = build_document_browser(items, total=25, offset=0, limit=10)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        nav_ids = []
        for ab in action_blocks:
            for el in ab["elements"]:
                nav_ids.append(el.get("action_id"))
        assert ACTION_PAGE_NEXT in nav_ids

    @pytest.mark.unit
    def test_browser_pagination_prev(self):
        items = [{"path": f"doc_{i}.md", "chunks": 1, "size": 100, "gate": "ungated", "indexed_at": ""} for i in range(10)]
        blocks = build_document_browser(items, total=25, offset=10, limit=10)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        nav_ids = []
        for ab in action_blocks:
            for el in ab["elements"]:
                nav_ids.append(el.get("action_id"))
        assert ACTION_PAGE_PREV in nav_ids
        assert ACTION_PAGE_NEXT in nav_ids


# ======================================================================
# Delete confirmation
# ======================================================================


class TestDeleteConfirmation:
    @pytest.mark.unit
    def test_confirmation_structure(self):
        blocks = build_delete_confirmation("journal/note.md", "readwrite")
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) == 1
        ids = [e["action_id"] for e in action_blocks[0]["elements"]]
        assert ACTION_CONFIRM_DELETE in ids
        assert ACTION_CANCEL_DELETE in ids


# ======================================================================
# Gate setup UI
# ======================================================================


class TestGateSetup:
    @pytest.mark.unit
    def test_setup_with_existing_gates(self):
        blocks = build_gate_setup({"journal": "readonly", "projects": "readwrite"})
        input_blocks = [b for b in blocks if b["type"] == "input"]
        assert len(input_blocks) == 1
        initial_value = input_blocks[0]["element"]["initial_value"]
        assert "journal = readonly" in initial_value
        assert "projects = readwrite" in initial_value

    @pytest.mark.unit
    def test_setup_empty(self):
        blocks = build_gate_setup({})
        input_blocks = [b for b in blocks if b["type"] == "input"]
        assert len(input_blocks) == 1
        # Should have example defaults
        assert "readonly" in input_blocks[0]["element"]["initial_value"]


# ======================================================================
# Gate config parser
# ======================================================================


class TestGateConfigParser:
    @pytest.mark.unit
    def test_basic_parse(self):
        text = "journal = readonly\nprojects = readwrite"
        gates = parse_gate_config_text(text)
        assert gates == {"journal": "readonly", "projects": "readwrite"}

    @pytest.mark.unit
    def test_comments_and_blanks(self):
        text = "# This is a comment\n\njournal = readonly\n\n# Another comment"
        gates = parse_gate_config_text(text)
        assert gates == {"journal": "readonly"}

    @pytest.mark.unit
    def test_strips_slashes(self):
        text = "/journal/ = readonly"
        gates = parse_gate_config_text(text)
        assert gates == {"journal": "readonly"}

    @pytest.mark.unit
    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            parse_gate_config_text("journal = admin")

    @pytest.mark.unit
    def test_missing_equals(self):
        with pytest.raises(ValueError, match="Expected"):
            parse_gate_config_text("journal readonly")

    @pytest.mark.unit
    def test_empty_directory(self):
        with pytest.raises(ValueError, match="Empty directory"):
            parse_gate_config_text("= readonly")

    @pytest.mark.unit
    def test_case_insensitive_mode(self):
        text = "journal = ReadOnly"
        gates = parse_gate_config_text(text)
        assert gates == {"journal": "readonly"}
