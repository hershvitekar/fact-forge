#!/bin/bash

# setup_docling.sh - Automates Docling environment for FactForge
set -e

echo "=========================================="
echo "   Docling Engine Setup for FactForge   "
echo "=========================================="

# 1. Install system dependencies
echo "[+] Checking for python3-venv..."
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip

# 2. Create directory structure
echo "[+] Creating project directories..."
mkdir -p ~/fact-forge-server/scripts
mkdir -p ~/fact-forge-server/data/pdfs
mkdir -p ~/fact-forge-server/data/markdown
mkdir -p ~/fact-forge-server/data/outputs
mkdir -p ~/fact-forge-server/data/archive

# 3. Setup Virtual Environment
echo "[+] Setting up Virtual Environment in ~/fact-forge-server/venv..."
if [ ! -d "~/fact-forge-server/venv" ]; then
    python3 -m venv ~/fact-forge-server/venv
fi

# 4. Install Docling
echo "[+] Installing Docling (this may take a minute)..."
source ~/fact-forge-server/venv/bin/activate
pip install --upgrade pip
pip install docling docling-core

# 5. Finalize scripts
echo "[+] Setup complete."
echo "[*] Data folders are ready at ~/fact-forge-server/data/"
echo "[*] You can now run: source ~/fact-forge-server/venv/bin/activate"