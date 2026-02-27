# Deployment Guide

AIS-CV runs as a systemd service on a Linux server or Raspberry Pi 5.

| Service | Script | Camera | Status |
|---------|--------|--------|--------|
| `ais-mill-counter` | `scripts/run_mill_counter.py` | CAM-2 (mill stand) | Deployed |

---

## Initial Setup

### 1. Clone / Copy Project

```bash
cd /home/adityajain/AIS
# Already present at ais-cv/
```

### 2. Virtual Environment

```bash
cd /home/adityajain/AIS/ais-cv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp config/settings.template.yaml config/settings.yaml
nano config/settings.yaml
```

Key values to set:
- `mill_stand_lines.views[*].camera.rtsp_url` — NVR channel 2 URL (CAM-2)

### 4. Firebase Credentials

```bash
# Place your service account JSON at:
config/firebase-service-account.json

# Test connection
python scripts/test_firebase.py
```

### 5. Create Required Directories

```bash
mkdir -p data/logs data/photos
```

### 6. Test Before Installing Services

```bash
# CAM-2 mill counter (30 second test)
python scripts/run_mill_counter.py --duration 30 --test

# Review logs
tail data/logs/mill_counter.log
```

---

## Service: `ais-mill-counter` (CAM-2 Mill Stand)

### Service File

`deploy/ais-mill-counter.service`:

```ini
[Unit]
Description=AIS Mill Stand Counter Service
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=adityajain
Group=adityajain
WorkingDirectory=/home/adityajain/AIS/ais-cv
Environment=PATH=/home/adityajain/AIS/ais-cv/venv/bin:/usr/bin:/bin
ExecStart=/home/adityajain/AIS/ais-cv/venv/bin/python scripts/run_mill_counter.py
Restart=always
RestartSec=10
StandardOutput=append:/home/adityajain/AIS/ais-cv/data/logs/mill_counter.log
StandardError=append:/home/adityajain/AIS/ais-cv/data/logs/mill_counter-error.log
TimeoutStartSec=60
WatchdogSec=300

[Install]
WantedBy=multi-user.target
```

### Install

```bash
sudo cp deploy/ais-mill-counter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ais-mill-counter
sudo systemctl start ais-mill-counter
```

### Manage

```bash
sudo systemctl status ais-mill-counter
sudo systemctl restart ais-mill-counter
sudo journalctl -u ais-mill-counter -f
```

---

## Service: `ais-photo-api` (Optional)

Serves captured count photos via HTTP for dashboard viewing.

```bash
sudo cp deploy/ais-photo-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ais-photo-api
sudo systemctl start ais-photo-api
```

---

## Log Locations

| Log | Location | Service |
|-----|----------|---------|
| Mill counter | `data/logs/mill_counter.log` | `ais-mill-counter` |
| Mill errors | `data/logs/mill_counter-error.log` | `ais-mill-counter` |
| Systemd journal | `journalctl -u <service>` | — |

```bash
# Live logs
tail -f data/logs/mill_counter.log

# Service journal
sudo journalctl -u ais-mill-counter -f --no-pager

# Last 100 lines
sudo journalctl -u ais-mill-counter -n 100
```

---

## Auto-Recovery

The service uses `Restart=always` with `RestartSec=10`. Recovery behaviour:

| Failure | Recovery |
|---------|----------|
| Python crash | systemd restarts process after 10s |
| Firebase timeout | Firebase writes are non-blocking; counter continues offline |
| System reboot | Service starts automatically (enabled with `systemctl enable`) |

**Session crash recovery:** On startup, the counter reads the last Firebase session. If it has no end time, counting continues in the same session.

---

## Health Checks

```bash
# Is service active?
systemctl is-active ais-mill-counter

# Recent activity (log modified in last 5 minutes?)
find data/logs/mill_counter.log -mmin -5 -print

# Recent photos
ls -lt data/photos/ | head -10
```

---

## Updating Code

```bash
# Stop service
sudo systemctl stop ais-mill-counter

# Pull updates
cd /home/adityajain/AIS/ais-cv
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Restart service
sudo systemctl start ais-mill-counter
```

---

## Updating Configuration

Config changes take effect on restart. The service can stay running during file edits:

```bash
nano config/settings.yaml
sudo systemctl restart ais-mill-counter
```

---

## Backup

| Item | Location | Notes |
|------|----------|-------|
| Config | `config/settings.yaml` | Back up on change |
| Firebase credentials | `config/firebase-service-account.json` | One-time, store securely |
| Count photos | `data/photos/` | Optional — also accessible via photo API |
| Application logs | `data/logs/` | Rotate weekly |

```bash
# Example backup script
DATE=$(date +%Y%m%d)
BACKUP=/home/adityajain/backups/ais-cv/$DATE
mkdir -p $BACKUP

cp config/settings.yaml $BACKUP/
find data/photos -mtime -7 -type f -exec cp {} $BACKUP/ \;
cp data/logs/*.log $BACKUP/ 2>/dev/null
echo "Backup complete: $BACKUP"
```

---

## Performance Tuning (Raspberry Pi 5)

```bash
# Set CPU governor to performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Disable unused services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon

# Add swap if needed
sudo dphys-swapfile install
```

**Memory management:**
```bash
# Auto-delete photos older than 7 days
crontab -e
# Add: 0 0 * * * find /home/adityajain/AIS/ais-cv/data/photos -mtime +7 -delete
```

---

## Security

```bash
# Restrict credentials
chmod 600 config/settings.yaml
chmod 600 config/firebase-service-account.json
chown adityajain:adityajain config/

# Verify NVR is on isolated network segment
# Firebase credentials grant full database write access — protect them
```

---

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Configuration](CONFIGURATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
