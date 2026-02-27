# AIS-CV — Rolling Mill Production Monitor

Computer vision system for counting hot steel pieces and tracking production sessions in a rolling mill. Runs from a Dahua NVR:

| Counter | Camera | Location | Status |
|---------|--------|----------|--------|
| **Mill Stand** | CAM-2 (channel 2) — 3 areas | Mill stand | Live, deployed as systemd service |
| **Mill Stand** | CAM-3 (channel 3) — 1 area | Mill stand (alternate angle) | Live, included in same service |

---

## How It Works

### Mill Stand Counter (CAM-2 + CAM-3)
Counts pieces at the mill stand using **multi-area independent 2-line detection**. Four counting areas are defined across two cameras (3 on CAM-2, 1 on CAM-3), each with its own ROI, entry line (L1), and exit line (L2). A piece is detected per area when it crosses L1 → L2 in order within a configurable timeout. The authoritative count is the **median** across all areas, making the system resilient to a single misbehaving area. CAM-3 counts the same pieces from a different angle, adding a fourth redundant vote. Sessions (RUN/BREAK) and daily/hourly counts are synced to Firebase in real time.

---

## Quick Start

### 1. Environment Setup

```bash
cd /home/adityajain/AIS/ais-cv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config/settings.template.yaml config/settings.yaml
nano config/settings.yaml
```

Fill in:
- `counting_areas.areas[*].camera_rtsp` — NVR credentials + channel 2 URL

### 3. Calibrate

```bash
# Mill stand areas/lines (CAM-2)
python scripts/run_mill_counter.py --display --no-firebase
```

### 4. Run

```bash
# Mill stand counter (CAM-2) with Firebase
python scripts/run_mill_counter.py

# Without Firebase (testing)
python scripts/run_mill_counter.py --no-firebase

# With display overlay
python scripts/run_mill_counter.py --display --no-firebase
```

### 5. Deploy as Service

```bash
sudo cp deploy/ais-mill-counter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ais-mill-counter
sudo systemctl start ais-mill-counter
```

---

## Project Structure

```
ais-cv/
├── config/
│   ├── settings.template.yaml        # Template — safe to commit
│   ├── settings.yaml                 # Live config — DO NOT COMMIT
│   └── firebase-service-account.json # Firebase credentials — DO NOT COMMIT
│
├── src/                              # Core library modules
│   ├── mill_stand_counter.py         # MillStandCounter — zone-based (legacy/offline)
│   ├── mill_stand_line_counter.py    # Stand + VotingWindow — per-view line logic
│   ├── mill_stand_multi_view_counter.py  # MultiViewLineCounter — orchestrates views
│   ├── cooling_bed_counter.py        # CoolingBedCounter — HSV blob detection
│   ├── session_manager.py            # SessionManager — RUN/BREAK session tracking
│   ├── firebase_client.py            # FirebaseClient — Firestore integration
│   ├── detector.py                   # HotStockDetector — luminosity/motion (legacy)
│   └── state_machine.py              # ProductionStateMachine (legacy)
│
├── scripts/                          # Entry points and tools
│   ├── run_mill_counter.py           # CAM-2 mill counter — production entry point
│   ├── run_mill_stand_multi.py       # CAM-2 mill counter — no Firebase (legacy)
│   ├── run_mill_stand_compare_cam2.py# Camera 2 calibration comparison tool
│   ├── calibrate_mill_stand_master.py# Interactive view/line calibrator (CAM-2)
│   ├── calibrate_mill_stand.py       # Zone calibrator (zone-based, offline)
│   ├── test_firebase.py              # Firebase connection test
│   └── photo_server.py               # HTTP server for count photos
│
├── deploy/
│   ├── ais-mill-counter.service      # Systemd service — CAM-2 mill counter
│   ├── ais-photo-api.service         # Systemd service — photo API server
│   └── install-service.sh            # Service installation script
│
├── data/
│   ├── logs/
│   │   ├── mill_counter.log          # Mill counter application log
│   │   └── state_changes_YYYY-MM-DD.csv
│   └── photos/                       # Count validation photos
│
├── logs/
│   └── line_brightness_cam2.csv      # CAM-2 per-frame line brightness log
│
├── docs/                             # Documentation (you are here)
├── archive/                          # Superseded detection system
└── requirements.txt
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, all components, data flow |
| [Configuration](docs/CONFIGURATION.md) | Complete `settings.yaml` reference |
| [Calibration](docs/CALIBRATION.md) | Line positioning and threshold tuning |
| [Mill Stand](docs/MILL_STAND.md) | Mill stand counter guide (CAM-2) |
| [Firebase](docs/FIREBASE.md) | Firestore schema and integration |
| [Deployment](docs/DEPLOYMENT.md) | Systemd service setup and monitoring |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and diagnostics |

---

## Service Management

```bash
# Mill counter (CAM-2)
sudo systemctl status ais-mill-counter
sudo systemctl restart ais-mill-counter
sudo journalctl -u ais-mill-counter -f
```

---

## Firebase Data

### CAM-2 (Mill Stand)
- `live/mill_stand` — real-time status (count, RUN/BREAK/OFFLINE)
- `daily/{YYYY-MM-DD_cam2}` — daily totals (`camera: 'CAM-2'`)
- `hourly/{YYYY-MM-DD}/hours/{HH}` — hourly breakdown
- `sessions/{id}` — RUN/BREAK sessions (`camera: 'CAM-2'`)
- *Piece-level detail stored locally only (not pushed to Firestore)*

---

## Hardware

- **Compute**: Linux server or Raspberry Pi 5
- **Camera**: Dahua NVR — sub stream recommended (704×576, H.265)
  - Channel 2 → Mill stand (CAM-2)
- **Network**: Same LAN as NVR
- **NVR IP**: `192.168.1.200` (configured in `settings.yaml`)
