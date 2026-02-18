# AIS-CV - Rolling Mill Production Monitoring

Computer vision module for monitoring production state and counting plate pieces in a rolling mill.

## Features

- **Piece Counting**: Counts hot plate pieces crossing the conveyor using 3-line detection
- **Mill Stand Counter**: Counts pieces at the mill stand view using dual-zone detection
- **Session Tracking**: Tracks RUN/BREAK production sessions with duration metrics
- **Firebase Sync**: Real-time sync to Firestore for dashboards and analytics
- **Photo Capture**: Saves validation photos for each counted piece
- **Auto-Recovery**: Handles camera disconnects and system restarts gracefully

## Quick Start

### 1. Setup Environment

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
- `counting_lines`: Calibrate based on your camera view (see [Calibration Guide](docs/CALIBRATION.md))

### 3. Calibrate Detection Lines

```bash
python scripts/calibrate_lines.py
```

### 4. Run Counter

```bash
# Run continuously
python scripts/run_counter.py

# Run for testing (60 seconds)
python scripts/run_counter.py --duration 60 --test

# Run without Firebase
python scripts/run_counter.py --no-firebase
```

### 5. Install as Service (Production)

```bash
cd deploy
sudo bash install-service.sh
```

## Mill Stand Counter

For counting pieces at the mill stand view, see the dedicated guide:

```bash
# Quick start - analyze video with 12% ratio threshold
python scripts/analyze_mill_stand.py \
  --video "recordings/mill stand day new.mp4" \
  --min-peak-ratio 0.12 \
  --display
```

**Key scripts:**
| Script | Description |
|--------|-------------|
| `calibrate_mill_stand.py` | Interactive zone positioning tool |
| `log_pixel_data.py` | Collect pixel data for threshold tuning |
| `visualize_pixels.py` | Generate statistics and interactive graphs |
| `analyze_mill_stand.py` | Main piece counter |

### Multi-View Mill Stand Counter (Line-Based)

For live counting using multiple RTSP views with per-view ROI + two-line sequence + majority voting:

```bash
python scripts/calibrate_mill_stand_master.py
python scripts/run_mill_stand_multi.py --display
```

See [Mill Stand Guide](docs/MILL_STAND.md) for details.

See [Mill Stand Guide](docs/MILL_STAND.md) for complete documentation.

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, components, and data flow |
| [Configuration](docs/CONFIGURATION.md) | Complete configuration reference |
| [Calibration](docs/CALIBRATION.md) | Detection line positioning and threshold tuning |
| [Mill Stand](docs/MILL_STAND.md) | Mill stand piece counter guide |
| [Deployment](docs/DEPLOYMENT.md) | Systemd service setup and monitoring |
| [Firebase](docs/FIREBASE.md) | Firestore schema and integration |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |

## Project Structure

```
ais-cv/
├── config/
│   ├── settings.template.yaml  # Template (safe to commit)
│   ├── settings.yaml           # Your config (DO NOT COMMIT)
│   └── firebase-service-account.json  # Firebase credentials
├── src/
│   ├── main.py                 # Production state detection
│   ├── stream.py               # RTSP stream handler
│   ├── detector.py             # Hot stock detection
│   ├── state_machine.py        # RUN/BREAK state logic
│   ├── counter.py              # Plate counting (3-line detection)
│   ├── session_manager.py      # Session tracking
│   └── firebase_client.py      # Firestore integration
├── scripts/
│   ├── run_counter.py          # Main entry point
│   ├── calibrate_lines.py      # Line calibration tool
│   ├── calibrate_mill_stand.py # Mill stand zone calibration
│   ├── analyze_mill_stand.py   # Mill stand piece counter
│   ├── log_pixel_data.py       # Pixel data logger
│   ├── visualize_pixels.py     # Pixel data visualization
│   ├── test_counter.py         # Testing utility
│   └── test_firebase.py        # Firebase connection test
├── deploy/
│   ├── ais-counter.service     # Systemd service file
│   └── install-service.sh      # Service installation
├── data/
│   ├── logs/                   # Application logs
│   └── photos/                 # Captured count photos
├── recordings/                 # Video files for analysis
├── docs/                       # Documentation
└── requirements.txt
```

## Key Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `luminosity_threshold` | 150 | Brightness threshold for hot steel (0-255) |
| `min_bright_pixels` | 80 | Minimum pixels on line to trigger |
| `sequence_timeout` | 4.0s | Max time for piece to travel L1→L3 |
| `break_threshold_seconds` | 120 | Idle time before BREAK state |

See [Configuration Guide](docs/CONFIGURATION.md) for complete reference.

## Output

### Logs
- `data/logs/counter.log` - Application log
- `data/logs/state_changes_YYYY-MM-DD.csv` - State transitions

### Photos
Each counted piece saves a photo:
```
data/photos/count_1_20260112_143215.jpg
data/photos/count_2_20260112_143218.jpg
...
```

### Firebase (Optional)
- Real-time status at `live/furnace`
- Individual counts in `counts/` collection
- Daily/hourly aggregates

## Service Management

```bash
# Check status
sudo systemctl status ais-counter

# View logs
sudo journalctl -u ais-counter -f

# Restart
sudo systemctl restart ais-counter

# Stop
sudo systemctl stop ais-counter
```

## Hardware

- **Compute**: Raspberry Pi 5 (or Linux server)
- **Camera**: Dahua NVR with RTSP (Sub Stream: 704×576, H.265)
- **Network**: Same LAN as NVR

## Support

For issues:
1. Check [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
2. Review logs in `data/logs/`
3. Verify configuration in `settings.yaml`
