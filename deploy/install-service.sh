#!/bin/bash
# AIS Counter Service Installation Script
# Run with: sudo bash install-service.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/ais-counter.service"

echo "=== AIS Counter Service Installer ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo bash install-service.sh"
    exit 1
fi

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: Service file not found at $SERVICE_FILE"
    exit 1
fi

# Create log directory if needed
LOG_DIR="/home/adityajain/AIS/ais-cv/data/logs"
mkdir -p "$LOG_DIR"
chown adityajain:adityajain "$LOG_DIR"

# Copy service file
echo "1. Copying service file..."
cp "$SERVICE_FILE" /etc/systemd/system/ais-counter.service

# Reload systemd
echo "2. Reloading systemd..."
systemctl daemon-reload

# Enable service (start on boot)
echo "3. Enabling service..."
systemctl enable ais-counter

# Start service
echo "4. Starting service..."
systemctl start ais-counter

# Check status
echo ""
echo "=== Service Status ==="
systemctl status ais-counter --no-pager

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Useful commands:"
echo "  sudo systemctl status ais-counter   - Check status"
echo "  sudo systemctl stop ais-counter     - Stop service"
echo "  sudo systemctl start ais-counter    - Start service"
echo "  sudo systemctl restart ais-counter  - Restart service"
echo "  sudo journalctl -u ais-counter -f   - View live logs"
echo ""
