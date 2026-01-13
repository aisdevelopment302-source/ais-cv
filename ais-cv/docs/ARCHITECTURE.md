# AIS-CV Architecture

## Overview

AIS-CV is a computer vision system for monitoring production state in a rolling mill. It analyzes video feeds from RTSP cameras to:

1. **Detect hot stock** using luminosity-based detection
2. **Count plate pieces** crossing detection lines on the conveyor
3. **Track RUN/BREAK sessions** for production analytics
4. **Sync data to Firebase** for real-time dashboards

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AIS-CV System                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐ │
│   │   Dahua NVR  │───▶│ RTSPStream   │───▶│     PlateCounter         │ │
│   │  (RTSP Feed) │    │ (stream.py)  │    │     (counter.py)         │ │
│   └──────────────┘    └──────────────┘    │  - Line detection        │ │
│                                           │  - 3-line sequence       │ │
│                                           │  - Consecutive frames    │ │
│                                           └───────────┬──────────────┘ │
│                                                       │                │
│                                                       ▼                │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │                    SessionManager                                 │ │
│   │                   (session_manager.py)                           │ │
│   │  - RUN/BREAK session tracking                                    │ │
│   │  - Hourly/daily aggregates                                       │ │
│   │  - Automatic midnight reset                                      │ │
│   └───────────────────────────────┬──────────────────────────────────┘ │
│                                   │                                    │
│                                   ▼                                    │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │                    FirebaseClient                                 │ │
│   │                   (firebase_client.py)                           │ │
│   │  - Push individual counts                                        │ │
│   │  - Push completed sessions                                       │ │
│   │  - Update live status                                            │ │
│   │  - Daily/hourly aggregates                                       │ │
│   └──────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. RTSPStream (`src/stream.py`)

Handles camera video stream connection and frame capture.

**Responsibilities:**
- Connect to Dahua NVR via RTSP protocol
- Handle reconnection on stream failure
- Yield frames at target FPS for processing
- Minimize buffer for real-time processing

**Key Configuration:**
- `rtsp_url`: RTSP stream URL with credentials
- `reconnect_attempts`: Number of retry attempts (default: 5)
- `reconnect_delay_seconds`: Wait between retries (default: 5s)

### 2. PlateCounter (`src/counter.py`)

The main detection engine for counting hot plate pieces.

**Detection Logic:**
1. Convert frame to grayscale
2. Check 3 detection lines for bright pixels above threshold
3. Track consecutive frames for each line (reduces false positives)
4. When a piece crosses L1 → L2 → L3 in sequence, count it
5. Calculate confidence based on frame counts and pixel consistency

**Key Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `luminosity_threshold` | 150 | Brightness threshold (0-255) |
| `min_bright_pixels` | 80 | Minimum bright pixels on line |
| `sequence_timeout` | 4.0s | Max time for L1→L3 sequence |
| `min_travel_time` | 0.2s | Min time for L1→L3 (filters noise) |
| `min_consecutive_frames` | 2 | Frames to confirm detection |

**Confidence Scoring:**
```
Base: 50% for completing L1→L2→L3 sequence
+20%  if 3+ frames per line
+15%  if consistent pixel counts across lines
+15%  if high pixel counts (>200 avg)
```

### 3. SessionManager (`src/session_manager.py`)

Tracks production sessions for analytics.

**Session Types:**
- **RUN**: Active production (pieces being counted)
- **BREAK**: Idle period (no counts for `break_threshold` seconds)
- **OFFLINE**: System not running

**Features:**
- Automatic RUN→BREAK transition after idle threshold
- Immediate BREAK→RUN transition on piece counted
- Hourly aggregation (run_minutes, break_minutes, count)
- Daily totals tracking
- Automatic midnight reset

### 4. FirebaseClient (`src/firebase_client.py`)

Syncs data to Firebase/Firestore for dashboards.

**Collections:**
| Collection | Purpose |
|------------|---------|
| `live/furnace` | Real-time dashboard status |
| `counts/{id}` | Individual count events |
| `daily/{date}` | Daily totals |
| `hourly/{date}/hours/{HH}` | Hourly breakdown |
| `sessions/{id}` | Completed RUN/BREAK sessions |

### 5. HotStockDetector (`src/detector.py`)

Original detection module for RUNNING/BREAK state based on luminosity + motion.

**Detection Methods:**
- **Luminosity**: Count bright pixels in ROI (hot steel glows)
- **Motion**: Frame differencing for movement detection
- **Combined**: Luminosity primary (70%), motion secondary (30%)

*Note: This module is used for state detection, while PlateCounter handles piece counting.*

### 6. ProductionStateMachine (`src/state_machine.py`)

Manages RUNNING/BREAK state transitions.

**State Transitions:**
```
UNKNOWN → RUNNING (hot stock detected)
RUNNING → BREAK (no detection for break_threshold)
BREAK → RUNNING (hot stock detected - immediate)
ANY → UNKNOWN (camera failure, low confidence)
```

## Data Flow

### Counting Flow
```
Frame → Grayscale → Check L1,L2,L3 → Track consecutive frames
                                            ↓
                              L1+L2+L3 confirmed?
                                    ↓ YES
                        Validate travel time (0.2-4s)
                                    ↓ PASS
                            Increment count
                                    ↓
              SessionManager.on_piece_counted()
                                    ↓
                FirebaseClient.push_count() + update_status()
```

### Session Flow
```
Piece counted → SessionManager.on_piece_counted()
                         ↓
              Currently BREAK? → Start RUN session → Push ended BREAK to Firebase
                         ↓ NO
              Update last_count_time, track run_minutes_since_last
                         
                         
Periodic check → SessionManager.check_for_break()
                         ↓
              idle > break_threshold? → Start BREAK session → Push ended RUN to Firebase
```

## File Structure

```
ais-cv/
├── config/
│   ├── settings.template.yaml    # Template (commit this)
│   ├── settings.yaml             # Your config (DO NOT commit)
│   └── firebase-service-account.json  # Firebase credentials
├── src/
│   ├── __init__.py
│   ├── main.py                   # Production state detection entry
│   ├── stream.py                 # RTSP stream handler
│   ├── detector.py               # Hot stock detection (luminosity/motion)
│   ├── state_machine.py          # RUNNING/BREAK state logic
│   ├── counter.py                # Plate counting (3-line detection)
│   ├── session_manager.py        # RUN/BREAK session tracking
│   └── firebase_client.py        # Firestore integration
├── scripts/
│   ├── run_counter.py            # Main entry point for counter
│   ├── calibrate_lines.py        # Interactive line calibration tool
│   ├── calibrate_web.py          # Web-based calibration (alternative)
│   ├── test_counter.py           # Counter testing utility
│   ├── test_firebase.py          # Firebase connection test
│   ├── live_test.py              # Live camera test
│   ├── visualize_roi.py          # ROI visualization tool
│   └── photo_server.py           # Photo serving API
├── deploy/
│   ├── ais-counter.service       # Systemd service for counter
│   ├── ais-photo-api.service     # Systemd service for photo server
│   └── install-service.sh        # Service installation script
├── data/
│   ├── logs/                     # Application logs
│   │   ├── counter.log
│   │   └── state_changes_YYYY-MM-DD.csv
│   └── photos/                   # Captured count photos
│       └── count_N_YYYYMMDD_HHMMSS.jpg
├── tests/
├── docs/                         # Documentation
└── requirements.txt
```

## Performance Considerations

### Processing FPS
- Stream runs at 25 FPS (NVR native)
- Detection processes ~20 FPS (sleep 0.05s between frames)
- Lower FPS = less CPU, but might miss fast-moving pieces

### Memory Usage
- Single frame buffer (CAP_PROP_BUFFERSIZE=1)
- No historical frames stored in memory
- Photos saved to disk immediately

### Network
- Sub-stream (704x576) recommended over main stream (1920x1080)
- TCP transport for reliability
- Reconnection handling built-in

## Entry Points

### Main Counter (`scripts/run_counter.py`)
```bash
python run_counter.py              # Run continuously
python run_counter.py --duration 60  # Run for 60 seconds
python run_counter.py --test       # Verbose test mode
python run_counter.py --no-firebase  # Offline mode
```

### Production State Detection (`src/main.py`)
```bash
python src/main.py                 # Run with default config
python src/main.py /path/to/config.yaml  # Custom config
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| opencv-python-headless | >=4.8.0 | Video processing |
| numpy | >=1.24.0 | Array operations |
| pyyaml | >=6.0 | Configuration files |
| firebase-admin | >=6.0.0 | Firestore integration |

## Related Documentation

- [Configuration Guide](CONFIGURATION.md)
- [Calibration Guide](CALIBRATION.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Firebase Integration](FIREBASE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
