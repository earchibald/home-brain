"""
Unit tests for VaultwardenClient.

Tests the Vaultwarden API client with caching. All secrets must come
from Vaultwarden exclusively — no environment variable fallback.
"""

import os
import time
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests


from clients.vaultwarden_client import (
    VaultwardenClient,
    get_client,
    get_secret,
    SecretNotFoundError,
    VaultwardenError,
)


@pytest.mark.unit
class TestVaultwardenClient:
    """Unit tests for VaultwardenClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock requests session."""
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        return session

    @pytest.fixture
    def client(self, mock_session):
        """Create a VaultwardenClient instance for testing."""
        with patch('requests.Session', return_value=mock_session):
            client = VaultwardenClient(
                api_url="https://vault.test/api",
                access_token="test-token-123",
                cache_ttl=300,
            )
        return client

    def test_client_initializes_with_credentials(self):
        """Client requires URL and token."""
        client = VaultwardenClient(
            api_url="https://vault.test/api",
            access_token="test-token"
        )
        assert client.api_url == "https://vault.test/api"
        assert client.access_token == "test-token"
        assert client.cache_ttl == 300  # Default

    def test_client_strips_trailing_slash_from_url(self):
        """URL should be normalized (trailing slash removed)."""
        client = VaultwardenClient(
            api_url="https://vault.test/api/",
            access_token="test-token"
        )
        assert client.api_url == "https://vault.test/api"

    def test_client_sets_authorization_header(self, mock_session):
        """Client should set Bearer token in session headers."""
        headers_dict = {}
        mock_session.headers = headers_dict

        with patch('requests.Session', return_value=mock_session):
            client = VaultwardenClient(
                api_url="https://vault.test/api",
                access_token="test-token-123"
            )

        assert 'Authorization' in headers_dict
        assert headers_dict['Authorization'] == 'Bearer test-token-123'

    def test_get_secret_fetches_from_api(self, client, mock_session):
        """get_secret() calls Vaultwarden API."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [{
                'name': 'TEST_KEY',
                'type': 1,
                'login': {'password': 'secret-value'}
            }]
        }
        mock_session.get.return_value = mock_response

        value = client.get_secret('TEST_KEY')

        assert value == 'secret-value'
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert call_args[0][0] == 'https://vault.test/api/ciphers'
        assert call_args[1]['params'] == {'search': 'TEST_KEY'}

    def test_get_secret_raises_when_not_found(self, client, mock_session):
        """get_secret() raises SecretNotFoundError when secret doesn't exist."""
        mock_response = Mock()
        mock_response.json.return_value = {'data': []}
        mock_session.get.return_value = mock_response

        with pytest.raises(SecretNotFoundError):
            client.get_secret('NONEXISTENT_KEY')

    def test_get_secret_returns_default_when_not_found(self, client, mock_session):
        """get_secret() returns default value when provided."""
        mock_response = Mock()
        mock_response.json.return_value = {'data': []}
        mock_session.get.return_value = mock_response

        value = client.get_secret('NONEXISTENT_KEY', default='fallback-value')

        assert value == 'fallback-value'

    def test_get_secret_caches_values(self, client, mock_session):
        """Cached values don't trigger API calls."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [{
                'name': 'CACHED_KEY',
                'type': 1,
                'login': {'password': 'cached-value'}
            }]
        }
        mock_session.get.return_value = mock_response

        value1 = client.get_secret('CACHED_KEY')
        assert value1 == 'cached-value'
        assert mock_session.get.call_count == 1

        value2 = client.get_secret('CACHED_KEY')
        assert value2 == 'cached-value'
        assert mock_session.get.call_count == 1  # No additional API call

    def test_get_secret_cache_expires(self, client, mock_session):
        """Cache expires after TTL."""
        client.cache_ttl = 0.1  # 100ms

        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [{
                'name': 'EXPIRE_KEY',
                'type': 1,
                'login': {'password': 'expired-value'}
            }]
        }
        mock_session.get.return_value = mock_response

        value1 = client.get_secret('EXPIRE_KEY')
        assert value1 == 'expired-value'
        assert mock_session.get.call_count == 1

        time.sleep(0.15)

        value2 = client.get_secret('EXPIRE_KEY')
        assert value2 == 'expired-value'
        assert mock_session.get.call_count == 2

    def test_get_secret_no_env_fallback(self, client, mock_session):
        """Secrets never fall back to environment variables."""
        mock_response = Mock()
        mock_response.json.return_value = {'data': []}
        mock_session.get.return_value = mock_response

        with patch.dict(os.environ, {'SOME_KEY': 'env-value'}):
            with pytest.raises(SecretNotFoundError):
                client.get_secret('SOME_KEY')

    def test_get_secret_raises_on_api_error(self, client, mock_session):
        """API errors raise VaultwardenError."""
        mock_session.get.side_effect = requests.exceptions.RequestException("API error")

        with pytest.raises(VaultwardenError):
            client.get_secret('ERROR_KEY')

    def test_set_secret_creates_cipher(self, client, mock_session):
        """set_secret() creates Vaultwarden item."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_session.post.return_value = mock_response

        result = client.set_secret('NEW_KEY', 'new-value', notes='Test note')

        assert result is True
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == 'https://vault.test/api/ciphers'

        json_data = call_args[1]['json']
        assert json_data['type'] == 1
        assert json_data['name'] == 'NEW_KEY'
        assert json_data['notes'] == 'Test note'
        assert json_data['login']['password'] == 'new-value'

    def test_set_secret_clears_cache(self, client, mock_session):
        """Setting a secret clears its cache entry."""
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            'data': [{
                'name': 'UPDATE_KEY',
                'type': 1,
                'login': {'password': 'old-value'}
            }]
        }
        mock_session.get.return_value = mock_get_response

        value1 = client.get_secret('UPDATE_KEY')
        assert value1 == 'old-value'
        assert 'UPDATE_KEY' in client._cache

        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_session.post.return_value = mock_post_response

        client.set_secret('UPDATE_KEY', 'new-value')

        assert 'UPDATE_KEY' not in client._cache

    def test_clear_cache(self, client, mock_session):
        """clear_cache() removes all cached secrets."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [{
                'name': 'KEY1',
                'type': 1,
                'login': {'password': 'value1'}
            }]
        }
        mock_session.get.return_value = mock_response

        client.get_secret('KEY1')
        assert len(client._cache) > 0

        client.clear_cache()
        assert len(client._cache) == 0

    def test_get_secret_handles_wrong_item_type(self, client, mock_session):
        """Only type 1 (Login) items should be retrieved."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [{
                'name': 'WRONG_TYPE',
                'type': 2,
                'secureNote': {'text': 'note-value'}
            }]
        }
        mock_session.get.return_value = mock_response

        with pytest.raises(SecretNotFoundError):
            client.get_secret('WRONG_TYPE')

    def test_get_secret_finds_exact_name_match(self, client, mock_session):
        """Should only return exact name matches."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [
                {
                    'name': 'PARTIAL_KEY_MATCH',
                    'type': 1,
                    'login': {'password': 'wrong-value'}
                },
                {
                    'name': 'PARTIAL_KEY',
                    'type': 1,
                    'login': {'password': 'correct-value'}
                }
            ]
        }
        mock_session.get.return_value = mock_response

        value = client.get_secret('PARTIAL_KEY')
        assert value == 'correct-value'


@pytest.mark.unit
class TestGlobalClientSingleton:
    """Test global singleton functions."""

    def test_get_client_creates_singleton(self):
        """get_client() creates and returns singleton instance."""
        import clients.vaultwarden_client as vc_module
        vc_module._client = None

        with patch.dict(os.environ, {
            'VAULTWARDEN_URL': 'https://vault.test/api',
            'VAULTWARDEN_TOKEN': 'test-token'
        }), patch('requests.Session'):
            client1 = get_client()
            client2 = get_client()

            assert client1 is client2

    def test_get_client_requires_token(self):
        """get_client() raises error if VAULTWARDEN_TOKEN not set."""
        import clients.vaultwarden_client as vc_module
        vc_module._client = None

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="VAULTWARDEN_TOKEN not set"):
                get_client()

    def test_get_client_uses_default_url(self):
        """get_client() uses default URL if not set."""
        import clients.vaultwarden_client as vc_module
        vc_module._client = None

        with patch.dict(os.environ, {
            'VAULTWARDEN_TOKEN': 'test-token'
        }), patch('requests.Session'):
            client = get_client()
            assert client.api_url == 'https://vault.nuc-1.local/api'

    def test_get_secret_convenience_function(self):
        """get_secret() convenience function delegates to Vaultwarden client."""
        import clients.vaultwarden_client as vc_module
        vc_module._client = None

        with patch.dict(os.environ, {
            'VAULTWARDEN_URL': 'https://vault.test/api',
            'VAULTWARDEN_TOKEN': 'test-token'
        }), patch('requests.Session') as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = Mock()
            mock_response.json.return_value = {
                'data': [{
                    'name': 'CONVENIENCE_KEY',
                    'type': 1,
                    'login': {'password': 'convenience-value'}
                }]
            }
            mock_session.get.return_value = mock_response

            value = get_secret('CONVENIENCE_KEY')
            assert value == 'convenience-value'

    def test_get_secret_no_env_fallback(self):
        """get_secret() convenience function does NOT fall back to env vars."""
        import clients.vaultwarden_client as vc_module
        vc_module._client = None

        with patch.dict(os.environ, {
            'VAULTWARDEN_URL': 'https://vault.test/api',
            'VAULTWARDEN_TOKEN': 'test-token',
            'SOME_SECRET': 'env-value',
        }), patch('requests.Session') as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = Mock()
            mock_response.json.return_value = {'data': []}
            mock_session.get.return_value = mock_response

            with pytest.raises(SecretNotFoundError):
                get_secret('SOME_SECRET')
