"""
Unit tests for Slack index manager UI builders and parsers.

All builder functions now return full modal view payloads (dicts with
"type": "modal" and "blocks": [...]).  Tests extract the blocks list from
the returned view where needed.
"""

import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slack_bot.index_manager import (
    build_index_dashboard,
    build_document_browser,
    build_delete_confirmation,
    build_gate_setup,
    build_loading_view,
    build_status_view,
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
    ACTION_BACK_DASHBOARD,
    CALLBACK_GATE_SETUP,
    CALLBACK_CONFIRM_DELETE,
)


def _blocks(view):
    """Extract blocks list from a modal view payload."""
    assert isinstance(view, dict), f"Expected dict view, got {type(view)}"
    assert view.get("type") == "modal", f"Expected modal view, got {view.get('type')}"
    return view["blocks"]


# ======================================================================
# Loading view
# ======================================================================


class TestLoadingView:
    @pytest.mark.unit
    def test_loading_default(self):
        view = build_loading_view()
        assert view["type"] == "modal"
        blocks = view["blocks"]
        assert any("Loading" in b.get("text", {}).get("text", "") for b in blocks)

    @pytest.mark.unit
    def test_loading_custom_message(self):
        view = build_loading_view("Fetching documents...")
        text = view["blocks"][0]["text"]["text"]
        assert "Fetching documents" in text


# ======================================================================
# Status view
# ======================================================================


class TestStatusView:
    @pytest.mark.unit
    def test_status_with_back(self):
        view = build_status_view("Done", "All done!")
        blocks = _blocks(view)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) >= 1
        ids = [e["action_id"] for e in action_blocks[0]["elements"]]
        assert ACTION_BACK_DASHBOARD in ids

    @pytest.mark.unit
    def test_status_no_back(self):
        view = build_status_view("Done", "All done!", show_back=False)
        blocks = _blocks(view)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) == 0


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
        view = build_index_dashboard(stats)
        blocks = _blocks(view)
        assert len(blocks) > 0
        types = [b["type"] for b in blocks]
        assert "divider" in types
        assert "actions" in types

    @pytest.mark.unit
    def test_dashboard_empty_stats(self):
        view = build_index_dashboard({})
        blocks = _blocks(view)
        assert len(blocks) > 0

    @pytest.mark.unit
    def test_dashboard_action_ids(self):
        view = build_index_dashboard({"total_files": 0, "total_chunks": 0, "gates": {}, "ignored_count": 0})
        blocks = _blocks(view)
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
        view = build_document_browser(items, total=2, offset=0, limit=10)
        blocks = _blocks(view)
        assert len(blocks) > 0

        text_blocks = [b for b in blocks if b["type"] == "section"]
        assert len(text_blocks) >= 2  # at least 2 doc sections

    @pytest.mark.unit
    def test_browser_readonly_no_delete(self):
        """Readonly gated documents should NOT have a delete button."""
        items = [{"path": "journal/note.md", "chunks": 1, "size": 100, "gate": "readonly", "indexed_at": ""}]
        view = build_document_browser(items, total=1, offset=0, limit=10)
        blocks = _blocks(view)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        for ab in action_blocks:
            for el in ab["elements"]:
                aid = el.get("action_id", "")
                assert not aid.startswith(ACTION_DOC_DELETE), (
                    "Delete button should not appear for readonly documents"
                )

    @pytest.mark.unit
    def test_browser_readwrite_has_delete(self):
        """Readwrite gated documents should have both ignore and delete."""
        items = [{"path": "projects/plan.md", "chunks": 1, "size": 100, "gate": "readwrite", "indexed_at": ""}]
        view = build_document_browser(items, total=1, offset=0, limit=10)
        blocks = _blocks(view)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        all_action_ids = []
        for ab in action_blocks:
            for el in ab["elements"]:
                all_action_ids.append(el.get("action_id", ""))
        assert any(aid.startswith(ACTION_DOC_IGNORE) for aid in all_action_ids)
        assert any(aid.startswith(ACTION_DOC_DELETE) for aid in all_action_ids)

    @pytest.mark.unit
    def test_browser_empty(self):
        view = build_document_browser([], total=0, offset=0, limit=10)
        blocks = _blocks(view)
        texts = [b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section"]
        assert any("No documents" in t for t in texts)

    @pytest.mark.unit
    def test_browser_pagination_next(self):
        items = [{"path": f"doc_{i}.md", "chunks": 1, "size": 100, "gate": "ungated", "indexed_at": ""} for i in range(10)]
        view = build_document_browser(items, total=25, offset=0, limit=10)
        blocks = _blocks(view)
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        nav_ids = []
        for ab in action_blocks:
            for el in ab["elements"]:
                nav_ids.append(el.get("action_id"))
        assert ACTION_PAGE_NEXT in nav_ids

    @pytest.mark.unit
    def test_browser_pagination_prev(self):
        items = [{"path": f"doc_{i}.md", "chunks": 1, "size": 100, "gate": "ungated", "indexed_at": ""} for i in range(10)]
        view = build_document_browser(items, total=25, offset=10, limit=10)
        blocks = _blocks(view)
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
        view = build_delete_confirmation("journal/note.md")
        assert view["type"] == "modal"
        assert view.get("callback_id") == CALLBACK_CONFIRM_DELETE
        # Has submit button (the "Yes, Delete" action)
        assert "submit" in view
        # private_metadata carries file_path
        metadata = json.loads(view.get("private_metadata", "{}"))
        assert metadata["file_path"] == "journal/note.md"


# ======================================================================
# Gate setup UI
# ======================================================================


class TestGateSetup:
    @pytest.mark.unit
    def test_setup_with_existing_gates(self):
        view = build_gate_setup({"journal": "readonly", "projects": "readwrite"})
        blocks = _blocks(view)
        assert view.get("callback_id") == CALLBACK_GATE_SETUP
        input_blocks = [b for b in blocks if b["type"] == "input"]
        assert len(input_blocks) == 1
        initial_value = input_blocks[0]["element"]["initial_value"]
        assert "journal = readonly" in initial_value
        assert "projects = readwrite" in initial_value

    @pytest.mark.unit
    def test_setup_empty(self):
        view = build_gate_setup({})
        blocks = _blocks(view)
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
