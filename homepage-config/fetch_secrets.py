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
    
    # Check if VAULTWARDEN_TOKEN is set
    if not os.getenv('VAULTWARDEN_TOKEN'):
        print("# Error: VAULTWARDEN_TOKEN not set", file=sys.stderr)
        print("# Set it first: export VAULTWARDEN_TOKEN='your-token-here'", file=sys.stderr)
        sys.exit(1)
    
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
        
        # Track how many secrets were found
        found_count = 0
        
        # Fetch and export each secret
        for key in secrets:
            try:
                value = client.get_secret(key)
                if value:
                    # Escape single quotes in value
                    safe_value = value.replace("'", "'\\''")
                    print(f"export {key}='{safe_value}'")
                    found_count += 1
            except SecretNotFoundError:
                # Secret not found - skip without error (user will populate later)
                print(f"# Note: {key} not found in VaultWarden (add via web UI)", file=sys.stderr)
                continue
            except Exception as e:
                print(f"# Warning: Failed to fetch {key}: {e}", file=sys.stderr)
                continue
        
        if found_count == 0:
            print("# Warning: No secrets found in VaultWarden", file=sys.stderr)
            print("# Add secrets via web UI: https://vault.nuc-1.local", file=sys.stderr)
        else:
            print(f"# Successfully fetched {found_count} secret(s)", file=sys.stderr)
        
    except VaultwardenError as e:
        print(f"# Error: {e}", file=sys.stderr)
        print("# Check that VAULTWARDEN_TOKEN is valid and VaultWarden is accessible", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"# Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
