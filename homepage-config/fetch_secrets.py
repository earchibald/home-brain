#!/usr/bin/env python3
"""
Fetch secrets from VaultWarden and export as environment variables.

This script is used by Homepage to fetch secrets without SOPS.
It retrieves credentials from VaultWarden and outputs them in shell format.

Usage:
    python3 fetch_secrets.py
    # Output: export KEY=value

    # In shell script:
    eval $(python3 fetch_secrets.py)
"""

import sys
import os

# Add parent directory to path to import clients
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from clients.vaultwarden_client import get_client, SecretNotFoundError, VaultwardenError


def main():
    """Fetch secrets from VaultWarden and output as shell exports."""
    try:
        # Initialize client from environment variables
        # Requires: VAULTWARDEN_TOKEN, optionally VAULTWARDEN_URL
        client = get_client()
        
        # List of secrets to fetch for Homepage
        secrets = [
            'UNIFI_USERNAME',
            'UNIFI_PASSWORD',
            # Add more secrets here as needed
        ]
        
        # Fetch and export each secret
        for key in secrets:
            try:
                value = client.get_secret(key)
                if value:
                    # Escape single quotes in value
                    safe_value = value.replace("'", "'\\''")
                    print(f"export {key}='{safe_value}'")
            except SecretNotFoundError:
                # Secret not found - skip without error (user will populate later)
                print(f"# Warning: {key} not found in VaultWarden", file=sys.stderr)
                continue
        
    except VaultwardenError as e:
        print(f"# Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"# Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
