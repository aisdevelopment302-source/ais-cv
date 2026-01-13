# AIS-CV Deployment Guide

## Overview

This guide covers deploying AIS-CV as a systemd service on Raspberry Pi or Linux servers.

## Prerequisites

- Raspberry Pi 5 (or Linux server)
- Python 3.11+
- Network access to Dahua NVR
- Git (for deployment)

## Initial Setup

### 1. Clone or Copy Project

```bash
# Option A: Clone from git
cd /home/adityajain/AIS
git clone <repository-url> ais-cv

# Option B: Copy existing
# Already at /home/adityajain/AIS/ais-cv
```

### 2. Create Virtual Environment

```bash
cd /home/adityajain/AIS/ais-cv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Application

```bash
# Copy template
cp config/settings.template.yaml config/settings.yaml

# Edit with your values
nano config/settings.yaml
```

Key configuration:
- `camera.rtsp_url` - Your NVR credentials and IP
- `counting_lines` - Calibrated line positions
- `counting` - Detection thresholds

### 4. Configure Firebase (Optional)

```bash
# Place your service account JSON in:
config/firebase-service-account.json

# Test connection
python scripts/test_firebase.py
```

### 5. Create Required Directories

```bash
mkdir -p data/logs data/photos
```

### 6. Test Before Service Installation

```bash
# Quick test (30 seconds)
python scripts/run_counter.py --duration 30

# Verify output
cat data/logs/counter.log
ls data/photos/
```

## Systemd Service Setup

### Counter Service

The main service that runs continuously.

**Service File:** `deploy/ais-counter.service`

```ini
[Unit]
Description=AIS CV Plate Counter
After=network.target

[Service]
Type=simple
User=adityajain
WorkingDirectory=/home/adityajain/AIS/ais-cv
ExecStart=/home/adityajain/AIS/ais-cv/venv/bin/python /home/adityajain/AIS/ais-cv/scripts/run_counter.py
Restart=always
RestartSec=10
StandardOutput=append:/home/adityajain/AIS/ais-cv/data/logs/counter.log
StandardError=append:/home/adityajain/AIS/ais-cv/data/logs/counter-error.log

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Install Service

**Automated Installation:**
```bash
cd /home/adityajain/AIS/ais-cv/deploy
sudo bash install-service.sh
```

**Manual Installation:**
```bash
# Copy service file
sudo cp deploy/ais-counter.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable ais-counter

# Start service
sudo systemctl start ais-counter
```

### Service Management Commands

```bash
# Check status
sudo systemctl status ais-counter

# View logs
sudo journalctl -u ais-counter -f

# Stop service
sudo systemctl stop ais-counter

# Restart service
sudo systemctl restart ais-counter

# Disable auto-start
sudo systemctl disable ais-counter
```

## Photo API Service (Optional)

Serves count photos via HTTP for dashboard viewing.

**Service File:** `deploy/ais-photo-api.service`

```ini
[Unit]
Description=AIS CV Photo API Server
After=network.target

[Service]
Type=simple
User=adityajain
WorkingDirectory=/home/adityajain/AIS/ais-cv
ExecStart=/home/adityajain/AIS/ais-cv/venv/bin/python /home/adityajain/AIS/ais-cv/scripts/photo_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Install:
```bash
sudo cp deploy/ais-photo-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ais-photo-api
sudo systemctl start ais-photo-api
```

## Monitoring

### Log Locations

| Log | Location | Content |
|-----|----------|---------|
| Application | `data/logs/counter.log` | Normal operation logs |
| Errors | `data/logs/counter-error.log` | Python errors, crashes |
| State Changes | `data/logs/state_changes_YYYY-MM-DD.csv` | RUN/BREAK transitions |
| Systemd Journal | `journalctl -u ais-counter` | Service-level logs |

### View Logs

```bash
# Live application logs
tail -f data/logs/counter.log

# Today's state changes
cat data/logs/state_changes_$(date +%Y-%m-%d).csv

# Service journal
sudo journalctl -u ais-counter -f --no-pager

# Last 100 lines
sudo journalctl -u ais-counter -n 100
```

### Health Checks

```bash
# Check service is running
systemctl is-active ais-counter

# Check recent activity (last 5 minutes)
find data/logs/counter.log -mmin -5 -print

# Check recent photos
ls -lt data/photos/ | head -5

# Check Firebase sync (if enabled)
python -c "
from src.firebase_client import get_firebase_client
fb = get_firebase_client()
if fb.initialize():
    print(f\"Today's count: {fb.get_today_count()}\")
"
```

## Auto-Recovery

The systemd service is configured to auto-restart on failure:

```ini
Restart=always
RestartSec=10
```

This means:
- If the Python process crashes, it restarts after 10 seconds
- If camera disconnects, the app's reconnection logic handles it
- If both fail, systemd restarts the whole process

### Failure Notification (Advanced)

To receive notifications on failure, add to service file:

```ini
[Unit]
# ... existing ...
OnFailure=notify-admin@%n.service
```

Then create `/etc/systemd/system/notify-admin@.service`:
```ini
[Unit]
Description=Send failure notification

[Service]
Type=oneshot
ExecStart=/usr/bin/curl -X POST https://your-webhook.com/alert -d "Service %i failed"
```

## Updates

### Updating Code

```bash
# Stop service
sudo systemctl stop ais-counter

# Pull updates (if using git)
cd /home/adityajain/AIS/ais-cv
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Restart service
sudo systemctl start ais-counter
```

### Updating Configuration

```bash
# Edit config (service can stay running during edit)
nano config/settings.yaml

# Restart to apply changes
sudo systemctl restart ais-counter
```

## Backup

### What to Backup

| Item | Location | Frequency |
|------|----------|-----------|
| Configuration | `config/settings.yaml` | On change |
| Firebase Credentials | `config/firebase-service-account.json` | One-time |
| Photos | `data/photos/` | Daily (optional) |
| Logs | `data/logs/` | Weekly rotation |

### Backup Script

```bash
#!/bin/bash
# backup-ais-cv.sh

BACKUP_DIR="/home/adityajain/backups/ais-cv"
DATE=$(date +%Y%m%d)

mkdir -p "$BACKUP_DIR"

# Backup config (excluding credentials)
cp config/settings.yaml "$BACKUP_DIR/settings_$DATE.yaml"

# Backup recent photos (last 7 days)
find data/photos -mtime -7 -type f -exec cp {} "$BACKUP_DIR/photos/" \;

# Backup logs
cp data/logs/*.csv "$BACKUP_DIR/logs/"

echo "Backup complete: $BACKUP_DIR"
```

## Performance Tuning

### Raspberry Pi 5 Optimization

```bash
# Increase GPU memory (if using video decoding)
sudo raspi-config
# → Performance Options → GPU Memory → 256

# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon

# Set CPU governor to performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### Memory Management

If running low on memory:
```bash
# Check memory usage
free -h

# Reduce photo retention
find data/photos -mtime +7 -delete  # Delete photos older than 7 days

# Add to crontab for automatic cleanup
crontab -e
# Add: 0 0 * * * find /home/adityajain/AIS/ais-cv/data/photos -mtime +7 -delete
```

## Security Considerations

### File Permissions

```bash
# Restrict config access
chmod 600 config/settings.yaml
chmod 600 config/firebase-service-account.json

# Ensure service user can read
chown adityajain:adityajain config/*
```

### Network Security

- NVR should be on isolated network segment
- Firebase credentials grant write access - protect them
- Consider firewall rules if Pi is exposed

## Troubleshooting

See [Troubleshooting Guide](TROUBLESHOOTING.md) for common issues.

### Quick Diagnostics

```bash
# Is service running?
systemctl is-active ais-counter

# Recent errors?
sudo journalctl -u ais-counter --since "10 minutes ago" | grep -i error

# Camera accessible?
ffprobe -rtsp_transport tcp "rtsp://admin:pass@192.168.1.100:554/cam/realmonitor?channel=1&subtype=1" 2>&1 | head -5

# Firebase connected?
python scripts/test_firebase.py
```

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Configuration](CONFIGURATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
