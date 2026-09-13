#!/usr/bin/env bash
# One-click launcher for macOS / Linux.
# Run:  bash start_mac_linux.sh
# Installs dependencies (first run only) and starts the dashboard,
# opening your browser automatically.

cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "python3 not found. Please install Python 3.10+ and try again."
    exit 1
fi

echo "Installing/checking dependencies..."
python3 -m pip install -r requirements.txt --quiet --break-system-packages 2>/dev/null || \
python3 -m pip install -r requirements.txt --quiet

echo "Starting Rig Control dashboard..."
python3 web/app.py
