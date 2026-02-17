#!/usr/bin/env python3
"""
Migrate secrets from SOPS to Vaultwarden.

Prerequisites:
1. Vaultwarden must be running on NUC-1
2. You must have created a user account via web UI
3. You must have a VAULTWARDEN_TOKEN set in environment

Usage:
    export VAULTWARDEN_TOKEN="your-api-token"
    python scripts/migrate_secrets_to_vaultwarden.py
"""

import os
import sys
import subprocess
from clients.vaultwarden_client import VaultwardenClient

# Secrets to migrate (key -> description)
SECRETS_TO_MIGRATE = {
    # Slack credentials
    "SLACK_BOT_TOKEN": "Slack bot OAuth token for Brain Assistant",
    "SLACK_APP_TOKEN": "Slack app-level token for Socket Mode",

    # API keys
    "ANTHROPIC_API_KEY": "Anthropic API key for Claude",
    "GOOGLE_API_KEY": "Google API key for Gemini",

    # Service URLs (optional, but good to centralize)
    "SEARCH_URL": "Semantic search service URL (default: http://nuc-1.local:9514)",
    "OLLAMA_URL": "Ollama server URL (default: http://m1-mini.local:11434)",
}


def load_secret_from_sops(key: str) -> str | None:
    """Load a secret from SOPS-encrypted secrets.env."""
    try:
        # Source the Age key and decrypt
        result = subprocess.run(
            f"source .env && sops -d secrets.env | grep '^{key}=' | cut -d= -f2-",
            shell=True,
            capture_output=True,
            text=True,
            executable="/bin/bash"
        )

        if result.returncode == 0:
            value = result.stdout.strip()
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            return value if value else None
        return None
    except Exception as e:
        print(f"  ⚠️  Error loading {key} from SOPS: {e}")
        return None


def migrate_secrets():
    """Migrate secrets from SOPS to Vaultwarden."""

    # Check for Vaultwarden token
    token = os.getenv("VAULTWARDEN_TOKEN")
    if not token:
        print("❌ VAULTWARDEN_TOKEN not set!")
        print("\nTo get a token:")
        print("  1. Visit https://vault.nuc-1.local")
        print("  2. Create an account or log in")
        print("  3. Go to Settings → Security → API Key")
        print("  4. Create a new API key")
        print("  5. export VAULTWARDEN_TOKEN='your-token-here'")
        sys.exit(1)

    # Initialize Vaultwarden client
    print("🔐 Connecting to Vaultwarden...")
    client = VaultwardenClient(
        api_url="https://vault.nuc-1.local/api",
        access_token=token,
        verify_ssl=False  # Self-signed cert
    )

    print(f"✅ Connected to Vaultwarden\n")

    # Migrate each secret
    migrated = 0
    skipped = 0
    failed = 0

    for key, description in SECRETS_TO_MIGRATE.items():
        print(f"📦 Migrating {key}...")

        # Load from SOPS
        value = load_secret_from_sops(key)

        if not value:
            # Try environment variable as fallback
            value = os.getenv(key)

        if not value:
            print(f"  ⚠️  Skipped (not found in SOPS or environment)")
            skipped += 1
            continue

        # Upload to Vaultwarden
        try:
            client.set_secret(key, value, notes=description)
            print(f"  ✅ Migrated successfully")
            migrated += 1
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            failed += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"Migration Summary:")
    print(f"  ✅ Migrated: {migrated}")
    print(f"  ⚠️  Skipped:  {skipped}")
    print(f"  ❌ Failed:   {failed}")
    print(f"{'='*60}\n")

    if migrated > 0:
        print("🎉 Secrets successfully migrated to Vaultwarden!")
        print("\nNext steps:")
        print("  1. Verify secrets in Vaultwarden web UI")
        print("  2. Update services to use VaultwardenClient")
        print("  3. Deploy to NUCs with VAULTWARDEN_TOKEN")
        print("  4. Test services")
        print("  5. Remove secrets.env after 30-day grace period")

    return migrated > 0


if __name__ == "__main__":
    try:
        success = migrate_secrets()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
