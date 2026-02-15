# VaultWarden Secrets Setup for Homepage

This guide explains how to migrate from SOPS to VaultWarden for Homepage secrets management.

## Prerequisites

1. VaultWarden running at https://vault.nuc-1.local
2. VaultWarden account created
3. Python 3 with requests library

## Step 1: Create VaultWarden API Token

1. Log in to VaultWarden: https://vault.nuc-1.local
2. Go to **Settings** → **Account Security** → **Keys**
3. Under **API Key**, click **View API Key**
4. Enter your master password
5. Copy the displayed token (starts with `ey...`)
6. Save this token - you'll need it for Homepage

## Step 2: Add Secrets to VaultWarden

For each secret that Homepage needs, create a "Login" item in VaultWarden:

### Unifi Credentials

1. Click **New Item** (+ button)
2. Select type: **Login**
3. Fill in:
   - **Name:** `UNIFI_USERNAME` (exact match required)
   - **Username:** `UNIFI_USERNAME` (same as name)
   - **Password:** Your Unifi controller username
   - **Notes:** "Unifi Controller username for Homepage monitoring"
4. Click **Save**

Repeat for password:
1. Click **New Item**
2. Select type: **Login**
3. Fill in:
   - **Name:** `UNIFI_PASSWORD` (exact match required)
   - **Username:** `UNIFI_PASSWORD` (same as name)
   - **Password:** Your Unifi controller password
   - **Notes:** "Unifi Controller password for Homepage monitoring"
4. Click **Save**

**Important:** The "Name" field must match exactly what Homepage expects (e.g., `UNIFI_USERNAME`, `UNIFI_PASSWORD`).

## Step 3: Configure Environment on nuc-1

SSH to nuc-1 and set up the VaultWarden token:

```bash
ssh nuc-1.local

# Add to your shell profile (~/.bashrc or ~/.zshrc)
echo 'export VAULTWARDEN_TOKEN="your-token-from-step-1"' >> ~/.bashrc
echo 'export VAULTWARDEN_URL="https://vault.nuc-1.local/api"' >> ~/.bashrc

# Reload shell
source ~/.bashrc

# Verify it's set
echo $VAULTWARDEN_TOKEN
```

## Step 4: Deploy Homepage Files

From your local machine:

```bash
# Make scripts executable
chmod +x homepage-config/start_homepage.sh
chmod +x homepage-config/fetch_secrets.py

# Deploy to nuc-1
scp homepage-config/start_homepage.sh nuc-1.local:/home/earchibald/homepage-config/
scp homepage-config/fetch_secrets.py nuc-1.local:/home/earchibald/homepage-config/
scp homepage-config/config/* nuc-1.local:/home/earchibald/homepage-config/config/

# Copy clients directory (needed for VaultWarden client)
scp -r clients nuc-1.local:/home/earchibald/homepage-config/
```

## Step 5: Install Dependencies on nuc-1

```bash
ssh nuc-1.local

# Install Python requests if not already installed
python3 -m pip install requests

# Or use system package
sudo apt install python3-requests  # Debian/Ubuntu
```

## Step 6: Test Secret Retrieval

```bash
ssh nuc-1.local
cd ~/homepage-config

# Test fetching secrets
python3 fetch_secrets.py

# Should output:
# export UNIFI_USERNAME='your-username'
# export UNIFI_PASSWORD='your-password'
```

If you see warnings about missing secrets, add them to VaultWarden (see Step 2).

## Step 7: Start Homepage with VaultWarden

```bash
ssh nuc-1.local
cd ~/homepage-config

# Start Homepage (will fetch secrets from VaultWarden)
./start_homepage.sh
```

The script will:
1. Check that VAULTWARDEN_TOKEN is set
2. Fetch secrets from VaultWarden
3. Start Homepage with those secrets as environment variables

## Step 8: Verify Homepage Works

1. Open http://nuc-1.local:3000
2. Check that services show correct status
3. If Unifi widget is configured, verify it displays data

## Troubleshooting

### "VAULTWARDEN_TOKEN not set"

```bash
# Check if token is set
echo $VAULTWARDEN_TOKEN

# If empty, set it
export VAULTWARDEN_TOKEN="your-token-here"

# Add to shell profile to persist
echo 'export VAULTWARDEN_TOKEN="..."' >> ~/.bashrc
```

### "Secret not found in VaultWarden"

The secret name in VaultWarden must match exactly. Check:
1. Log in to VaultWarden
2. Go to your vault
3. Find the item
4. Verify the **Name** field matches exactly (case-sensitive)

### Permission denied on fetch_secrets.py

```bash
chmod +x ~/homepage-config/fetch_secrets.py
```

### SSL certificate errors

The VaultwardenClient automatically disables SSL verification for `.local` domains. If you still have issues:

```bash
export VAULTWARDEN_VERIFY_SSL=false
```

## Adding More Secrets

To add more secrets that Homepage needs:

1. Add to VaultWarden (see Step 2)
2. Edit `fetch_secrets.py` and add the key to the `secrets` list:
   ```python
   secrets = [
       'UNIFI_USERNAME',
       'UNIFI_PASSWORD',
       'NEW_SECRET_NAME',  # Add here
   ]
   ```
3. Update docker-compose.yml to use the environment variable
4. Restart Homepage: `./start_homepage.sh`

## Migration from SOPS

If you have secrets in SOPS, migrate them:

```bash
# On your local machine
sops -d secrets.env | grep -v '^#' | while IFS='=' read -r key value; do
    echo "Add to VaultWarden: $key"
done
```

Then manually add each to VaultWarden using the web UI.

## Security Notes

- The VaultWarden token is like a password - keep it secure
- Store the token in your shell profile (not in git)
- Use client credentials for token auto-refresh in production
- Homepage fetches secrets at startup, not on every request
- Secrets are loaded as environment variables in the container

## Automatic Startup (Optional)

To automatically start Homepage on boot with VaultWarden:

```bash
# Create systemd service on nuc-1
sudo nano /etc/systemd/system/homepage.service
```

```ini
[Unit]
Description=Homepage Dashboard with VaultWarden
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=earchibald
WorkingDirectory=/home/earchibald/homepage-config
Environment="VAULTWARDEN_TOKEN=your-token-here"
Environment="VAULTWARDEN_URL=https://vault.nuc-1.local/api"
ExecStart=/home/earchibald/homepage-config/start_homepage.sh
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable homepage.service
sudo systemctl start homepage.service
```

**Note:** Storing the token in a systemd service file requires appropriate file permissions. For better security, use environment files with restricted permissions or client credentials for token refresh.
