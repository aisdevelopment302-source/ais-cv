# AIS CV - Production Detection Module

Computer vision module for detecting production state (RUNNING vs BREAK) in the rolling mill.

## Overview

This module monitors the Furnace Opening camera to detect:
- **RUNNING**: Hot stock being pulled from furnace
- **BREAK**: No stock activity for 2+ minutes

## Quick Start

### 1. Setup (Raspberry Pi)

```bash
cd ais-cv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy template and edit with your credentials
cp config/settings.template.yaml config/settings.yaml
nano config/settings.yaml
```

Update these values:
- `camera.rtsp_url`: Your NVR credentials and IP
- `roi.furnace_door`: Calibrate based on your camera view

### 3. Run

```bash
source venv/bin/activate
python src/main.py
```

### 4. Run as Service (Optional)

```bash
# Create systemd service
sudo cp ais-cv.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ais-cv
sudo systemctl start ais-cv
```

## Project Structure

```
ais-cv/
├── config/
│   ├── settings.template.yaml  # Template (safe to commit)
│   └── settings.yaml           # Your config (DO NOT COMMIT)
├── src/
│   ├── main.py                 # Entry point
│   ├── stream.py               # RTSP stream handler
│   ├── detector.py             # Hot stock detection
│   └── state_machine.py        # RUNNING/BREAK state logic
├── data/
│   ├── logs/                   # State change logs
│   └── photos/                 # Validation photos
├── tests/
└── requirements.txt
```

## Configuration

See `config/settings.template.yaml` for all options.

Key settings:
- `detection.break_threshold_seconds`: Time without stock to trigger BREAK (default: 120)
- `detection.luminosity_threshold`: Brightness threshold for hot stock (default: 180)
- `photos.periodic_interval_seconds`: Photo capture interval (default: 300)

## Logs

- State changes: `data/logs/state_changes_YYYY-MM-DD.csv`
- Application log: `data/logs/cv.log`
- Photos: `data/photos/`

## Hardware

- Raspberry Pi 5
- Dahua NVR (RTSP)
- Camera: Furnace Opening (Channel 1)
