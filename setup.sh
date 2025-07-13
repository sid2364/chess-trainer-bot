#!/usr/bin/env bash
set -e

# Install Stockfish 16 via apt-get
sudo apt-get update
sudo apt-get install -y stockfish

# Verify installation
if stockfish -? 2>/dev/null | head -n 1 | grep -q "Stockfish 16"; then
    echo "Stockfish 16 installed successfully."
else
    echo "Warning: Stockfish 16 was not detected."
fi

# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies and build the frontend
if command -v npm >/dev/null 2>&1; then
    npm install
    npm run build
else
    echo "Error: npm is not installed or not found in PATH" >&2
    exit 1
fi
