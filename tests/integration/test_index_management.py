"""
Integration tests for SemanticSearchClient index management methods.

Mocks the HTTP layer to test client-side logic without a running service.
"""

import pytest
import httpx
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clients.semantic_search_client import (
    SemanticSearchClient,
    DocumentInfo,
    DocumentListPage,
)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def client():
    """SemanticSearchClient pointed at a fake URL."""
    return SemanticSearchClient(base_url="http://fake-search:42110", timeout=5)


def _mock_response(status_code=200, json_data=None, text=""):
    """Build an httpx.Response mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


# ======================================================================
# list_documents
# ======================================================================


class TestListDocuments:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_documents_success(self, client):
        payload = {
            "items": [
                {"path": "journal/note.md", "chunks": 3, "indexed_at": "2026-02-15", "size": 1024, "gate": "readonly"},
            ],
            "total": 1,
            "offset": 0,
            "limit": 50,
        }
        client.client = AsyncMock()
        client.client.get = AsyncMock(return_value=_mock_response(200, payload))

        page = await client.list_documents()
        assert isinstance(page, DocumentListPage)
        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].path == "journal/note.md"
        assert page.items[0].gate == "readonly"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_documents_with_folder(self, client):
        payload = {"items": [], "total": 0, "offset": 0, "limit": 50}
        client.client = AsyncMock()
        client.client.get = AsyncMock(return_value=_mock_response(200, payload))

        page = await client.list_documents(folder="journal")
        # Verify query params were passed
        call_args = client.client.get.call_args
        assert call_args.kwargs.get("params", {}).get("folder") == "journal"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_documents_error(self, client):
        client.client = AsyncMock()
        client.client.get = AsyncMock(side_effect=Exception("connection refused"))

        page = await client.list_documents()
        assert page.total == 0
        assert page.items == []


# ======================================================================
# ignore_document
# ======================================================================


class TestIgnoreDocument:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_ignore_success(self, client):
        client.client = AsyncMock()
        client.client.post = AsyncMock(
            return_value=_mock_response(200, {"status": "ignored", "file": "journal/note.md"})
        )
        result = await client.ignore_document("journal/note.md")
        assert result is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_ignore_not_found(self, client):
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=_mock_response(404))
        result = await client.ignore_document("nonexistent.md")
        assert result is False


# ======================================================================
# delete_document
# ======================================================================


class TestDeleteDocument:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_delete_success(self, client):
        client.client = AsyncMock()
        client.client.post = AsyncMock(
            return_value=_mock_response(200, {"status": "deleted", "file": "projects/plan.md"})
        )
        result = await client.delete_document("projects/plan.md")
        assert result is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_delete_readonly_rejected(self, client):
        client.client = AsyncMock()
        client.client.post = AsyncMock(return_value=_mock_response(403))
        result = await client.delete_document("journal/note.md")
        assert result is False


# ======================================================================
# get_gates / set_gate / replace_gates
# ======================================================================


class TestGates:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_gates(self, client):
        client.client = AsyncMock()
        client.client.get = AsyncMock(
            return_value=_mock_response(200, {"gates": {"journal": "readonly"}})
        )
        gates = await client.get_gates()
        assert gates == {"journal": "readonly"}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_set_gate(self, client):
        client.client = AsyncMock()
        client.client.post = AsyncMock(
            return_value=_mock_response(200, {"status": "ok"})
        )
        result = await client.set_gate("journal", "readonly")
        assert result is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_replace_gates(self, client):
        client.client = AsyncMock()
        client.client.put = AsyncMock(
            return_value=_mock_response(200, {"status": "ok", "gates": {"journal": "readonly"}})
        )
        result = await client.replace_gates({"journal": "readonly"})
        assert result is True


# ======================================================================
# get_registry_stats
# ======================================================================


class TestRegistryStats:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_stats(self, client):
        client.client = AsyncMock()
        client.client.get = AsyncMock(
            return_value=_mock_response(200, {
                "total_files": 42, "total_chunks": 200,
                "gates": {"journal": "readonly"}, "ignored_count": 3,
            })
        )
        stats = await client.get_registry_stats()
        assert stats["total_files"] == 42
        assert stats["ignored_count"] == 3
