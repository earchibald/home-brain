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
    echo "Error: VAULTWARDEN_TOKEN not set"
    echo "Please set it first:"
    echo "  export VAULTWARDEN_TOKEN='your-token-here'"
    exit 1
fi

# Fetch secrets from VaultWarden
echo "Fetching secrets from VaultWarden..."
python3 fetch_secrets.py > .env.secrets 2>&1

# Check if fetch was successful
if [ $? -ne 0 ]; then
    echo "Error fetching secrets from VaultWarden"
    cat .env.secrets
    rm -f .env.secrets
    exit 1
fi

# Source the secrets (warnings to stderr, exports to stdout)
eval $(grep '^export' .env.secrets)

# Clean up
rm -f .env.secrets

# Start or restart Homepage
echo "Starting Homepage..."
docker compose up -d

echo "Homepage started successfully!"
echo "Accessible at: http://nuc-1.local:3000"
