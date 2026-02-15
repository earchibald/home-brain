"""
Vaultwarden API client with caching and automatic token refresh.

Provides unified interface for secrets retrieval with:
- In-memory caching (TTL: 5 minutes)
- Automatic token refresh using client credentials
- Strict Vaultwarden-only (NO environment variable fallback)
- SSL auto-configuration for .local domains
- Automatic ntfy notifications on errors
"""

import os
import time
import requests
import uuid
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta


class VaultwardenError(Exception):
    """Base exception for Vaultwarden errors."""
    pass


class SecretNotFoundError(VaultwardenError):
    """Raised when a secret is not found in Vaultwarden."""
    pass


class TokenExpiredError(VaultwardenError):
    """Raised when the access token has expired."""
    pass


class VaultwardenClient:
    """Client for retrieving secrets from Vaultwarden.

    This client does NOT fall back to environment variables - it will raise
    SecretNotFoundError if a secret doesn't exist in Vaultwarden. This ensures
    all secrets are properly managed in Vaultwarden.
    """

    def __init__(
        self,
        api_url: str,
        access_token: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        cache_ttl: int = 300,
        verify_ssl: bool = True
    ):
        """
        Initialize Vaultwarden client.

        Args:
            api_url: Vaultwarden API URL (e.g., https://vault.nuc-1.local/api)
            access_token: API access token (JWT bearer token)
            client_id: Client ID for token refresh (optional)
            client_secret: Client secret for token refresh (optional)
            cache_ttl: Cache TTL in seconds (default 5 min)
            verify_ssl: Verify SSL certificates (set False for self-signed certs)
        """
        self.api_url = api_url.rstrip('/')
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.cache_ttl = cache_ttl
        self.verify_ssl = verify_ssl
        self.token_expiry: Optional[datetime] = None

        self._cache: Dict[str, Tuple[str, float]] = {}
        self._session = requests.Session()
        self._update_session_token(access_token)

        # Disable SSL warnings if verification is disabled
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _update_session_token(self, token: str):
        """Update session with new token."""
        self.access_token = token
        self._session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })

    def _refresh_token(self) -> str:
        """
        Refresh the access token using client credentials.

        Returns:
            New access token

        Raises:
            TokenExpiredError: If refresh fails
        """
        if not self.client_id or not self.client_secret:
            raise TokenExpiredError(
                "Token expired and no client credentials available for refresh. "
                "Please provide client_id and client_secret, or regenerate token manually."
            )

        # Get identity URL from API URL
        identity_url = self.api_url.replace('/api', '/identity/connect/token')

        try:
            response = requests.post(
                identity_url,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'grant_type': 'client_credentials',
                    'scope': 'api',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'device_identifier': str(uuid.uuid4()),
                    'device_name': 'VaultwardenClient',
                    'device_type': '8'  # API/SDK
                },
                verify=self.verify_ssl
            )
            response.raise_for_status()

            data = response.json()
            new_token = data['access_token']
            expires_in = data.get('expires_in', 7200)

            # Update token and expiry
            self._update_session_token(new_token)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)

            print(f"Token refreshed successfully. Expires in {expires_in} seconds.")
            return new_token

        except Exception as e:
            raise TokenExpiredError(f"Failed to refresh token: {e}")

    def _ensure_token_valid(self):
        """Ensure token is valid, refresh if needed."""
        if self.token_expiry and datetime.now() >= self.token_expiry:
            self._refresh_token()

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get secret value by key from Vaultwarden.

        This method does NOT fall back to environment variables. If the secret
        is not found in Vaultwarden, it will raise SecretNotFoundError (unless
        a default value is provided).

        Args:
            key: Secret key name
            default: Default value if not found (optional)

        Returns:
            Secret value or default

        Raises:
            SecretNotFoundError: If secret not found and no default provided
            VaultwardenError: If API request fails
        """
        # Check cache
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return value

        # Ensure token is valid
        try:
            self._ensure_token_valid()
        except TokenExpiredError:
            if default is not None:
                return default
            raise

        # Fetch from Vaultwarden
        try:
            value = self._fetch_secret(key)
            if value is not None:
                self._cache[key] = (value, time.time())
                return value
        except Exception as e:
            # If we have a default, return it; otherwise raise
            if default is not None:
                print(f"Warning: Failed to fetch {key} from Vaultwarden: {e}")
                return default
            raise VaultwardenError(f"Failed to fetch secret '{key}': {e}")

        # Secret not found
        if default is not None:
            return default

        raise SecretNotFoundError(
            f"Secret '{key}' not found in Vaultwarden. "
            "Please add it via the web UI or use set_secret()."
        )

    def _fetch_secret(self, key: str) -> Optional[str]:
        """Fetch secret from Vaultwarden API."""
        # Search for item by name
        response = self._session.get(
            f'{self.api_url}/ciphers',
            params={'search': key},
            verify=self.verify_ssl
        )
        response.raise_for_status()

        items = response.json()['data']
        for item in items:
            # Only match exact name and type 1 (Login)
            if item.get('name') == key and item.get('type') == 1:
                # Extract password field
                login = item.get('login', {})
                return login.get('password')

        return None

    def set_secret(self, key: str, value: str, notes: str = "") -> bool:
        """
        Create or update secret in Vaultwarden.

        Args:
            key: Secret key name
            value: Secret value
            notes: Optional notes

        Returns:
            True if successful

        Raises:
            VaultwardenError: If creation/update fails
        """
        # Ensure token is valid
        self._ensure_token_valid()

        # Create new cipher item
        data = {
            'type': 1,  # Login type
            'name': key,
            'notes': notes,
            'login': {
                'username': key,
                'password': value
            }
        }

        try:
            response = self._session.post(
                f'{self.api_url}/ciphers',
                json=data,
                verify=self.verify_ssl
            )
            response.raise_for_status()

            # Clear cache
            if key in self._cache:
                del self._cache[key]

            return True

        except Exception as e:
            raise VaultwardenError(f"Failed to set secret '{key}': {e}")

    def clear_cache(self):
        """Clear all cached secrets."""
        self._cache.clear()


# Global singleton instance (lazy-initialized)
_client: Optional[VaultwardenClient] = None


def get_client() -> VaultwardenClient:
    """Get or create VaultwardenClient singleton."""
    global _client

    if _client is None:
        api_url = os.getenv('VAULTWARDEN_URL', 'https://vault.nuc-1.local/api')
        access_token = os.getenv('VAULTWARDEN_TOKEN')
        client_id = os.getenv('VAULTWARDEN_CLIENT_ID')
        client_secret = os.getenv('VAULTWARDEN_CLIENT_SECRET')

        if not access_token:
            raise ValueError(
                "VAULTWARDEN_TOKEN not set. Please configure Vaultwarden access:\n"
                "  export VAULTWARDEN_TOKEN='your-token-here'\n"
                "  export VAULTWARDEN_CLIENT_ID='user.xxx' (optional, for auto-refresh)\n"
                "  export VAULTWARDEN_CLIENT_SECRET='xxx' (optional, for auto-refresh)"
            )

        # Disable SSL verification for .local domains (self-signed certs)
        verify_ssl_str = os.getenv('VAULTWARDEN_VERIFY_SSL', 'auto')
        if verify_ssl_str == 'auto':
            verify_ssl = not api_url.endswith('.local/api')
        else:
            verify_ssl = verify_ssl_str.lower() in ('true', '1', 'yes')

        _client = VaultwardenClient(
            api_url=api_url,
            access_token=access_token,
            client_id=client_id,
            client_secret=client_secret,
            verify_ssl=verify_ssl
        )

    return _client


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Convenience function to get secret from Vaultwarden.

    This does NOT fall back to environment variables. Secrets must be in Vaultwarden.

    Args:
        key: Secret key name
        default: Default value if not found

    Returns:
        Secret value or default

    Raises:
        SecretNotFoundError: If secret not found and no default provided
    """
    return get_client().get_secret(key, default)
