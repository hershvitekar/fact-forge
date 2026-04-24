#!/bin/bash

# setup_samba.sh - Automates Samba NAS setup for FactForge
# Designed for Ubuntu 22.04/24.04
# Workflow: Git pull and run

set -e

# Configuration
SHARE_NAME="FactForgeNAS"
DATA_DIR="/home/$(whoami)/fact-forge-server/data"
SMB_CONF="/etc/samba/smb.conf"
SNIPPET_FILE="smb_share.conf"

echo "=========================================="
echo "   Samba NAS Automation for FactForge   "
echo "=========================================="

# 1. Install Samba if not present
if ! dpkg -s samba >/dev/null 2>&1; then
    echo "[+] Installing Samba..."
    sudo apt-get update -y
    sudo apt-get install -y samba
else
    echo "[*] Samba is already installed."
fi

# 2. Ensure data directory exists
echo "[+] Ensuring directory exists: $DATA_DIR"
mkdir -p "$DATA_DIR"

# 3. Set ownership and permissions
echo "[+] Setting ownership to $(whoami) and permissions to 755"
sudo chown -R "$(whoami):$(whoami)" "$DATA_DIR"
chmod 755 "$DATA_DIR"

# 4. Append configuration if not already present
if grep -q "\[$SHARE_NAME\]" "$SMB_CONF"; then
    echo "[!] Share [$SHARE_NAME] already exists in $SMB_CONF. Skipping configuration append."
else
    if [ ! -f "$SNIPPET_FILE" ]; then
        echo "[ERROR] $SNIPPET_FILE not found in the current directory."
        exit 1
    fi

    echo "[+] Appending configuration from $SNIPPET_FILE to $SMB_CONF"
    
    # Ensure current user is exported for potential envsubst use
    export USER=$(whoami)
    
    # Prepare the append
    echo -e "\n# --- FactForge NAS Share ---" | sudo tee -a "$SMB_CONF" > /dev/null
    
    # Use envsubst if available, otherwise fallback to sed for $USER replacement
    # This ensures the $USER in smb_share.conf is replaced by the actual username
    if command -v envsubst >/dev/null 2>&1; then
        envsubst < "$SNIPPET_FILE" | sudo tee -a "$SMB_CONF" > /dev/null
    else
        sed "s/\$USER/$USER/g" "$SNIPPET_FILE" | sudo tee -a "$SMB_CONF" > /dev/null
    fi
    echo "[*] Configuration appended successfully."
fi

# 5. Prompt for Samba password
echo "[+] Setting Samba password for user: $(whoami)"
echo "--- ACTION REQUIRED: Please enter a password for the Samba user ---"
sudo smbpasswd -a "$(whoami)"

# 6. Restart services
echo "[+] Restarting smbd and nmbd services..."
sudo systemctl restart smbd nmbd

echo "=========================================="
echo "   Setup Complete! NAS is ready.        "
echo "   Access via: \\\\$(hostname -I | awk '{print $1}')\\$SHARE_NAME"
echo "=========================================="
