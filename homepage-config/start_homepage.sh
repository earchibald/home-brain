#!/bin/bash
#
# Start Homepage with secrets from VaultWarden
#
# This script fetches secrets from VaultWarden before starting Homepage.
# Requires VAULTWARDEN_TOKEN to be set in the environment.
#

set -e

cd "$(dirname "$0")"

# Check if VAULTWARDEN_TOKEN is set
if [ -z "$VAULTWARDEN_TOKEN" ]; then
    echo "⚠️  Warning: VAULTWARDEN_TOKEN not set"
    echo ""
    echo "Homepage will start without VaultWarden secrets."
    echo "This means service widgets (like Unifi) won't work."
    echo ""
    echo "To enable VaultWarden integration:"
    echo "  1. Get API token from https://vault.nuc-1.local (Settings → Keys)"
    echo "  2. export VAULTWARDEN_TOKEN='your-token-here'"
    echo "  3. Run this script again"
    echo ""
    echo "Continuing with basic Homepage setup..."
    echo ""
else
    # Fetch secrets from VaultWarden
    echo "🔐 Fetching secrets from VaultWarden..."
    
    # Create temporary file for secrets (will be deleted)
    SECRETS_FILE=$(mktemp)
    trap "rm -f $SECRETS_FILE" EXIT
    
    # Fetch secrets (errors go to stderr, exports to stdout)
    if python3 fetch_secrets.py > "$SECRETS_FILE" 2>&1; then
        # Check if any exports were generated
        if grep -q '^export' "$SECRETS_FILE"; then
            # Source the secrets
            eval $(grep '^export' "$SECRETS_FILE")
            echo "✅ Secrets loaded from VaultWarden"
        else
            echo "⚠️  No secrets found in VaultWarden (this is OK for basic usage)"
            cat "$SECRETS_FILE" | grep '^#' || true
        fi
    else
        echo "❌ Error fetching secrets from VaultWarden:"
        cat "$SECRETS_FILE"
        echo ""
        echo "Homepage will start without secrets."
    fi
fi

# Start or restart Homepage
echo "🚀 Starting Homepage..."
docker compose up -d

# Wait a moment for container to start
sleep 2

# Check if container is running
if docker ps --filter name=homepage --filter status=running | grep -q homepage; then
    echo "✅ Homepage started successfully!"
    echo "📍 Accessible at: http://nuc-1.local:3000"
else
    echo "❌ Homepage container failed to start"
    echo "Check logs: docker logs homepage"
    exit 1
fi
