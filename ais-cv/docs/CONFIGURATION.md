# AIS-CV Configuration Guide

## Overview

AIS-CV uses YAML configuration files located in the `config/` directory.

**Important:** Never commit `settings.yaml` or `firebase-service-account.json` - they contain credentials!

## Quick Start

```bash
# Copy template to create your config
cp config/settings.template.yaml config/settings.yaml

# Edit with your values
nano config/settings.yaml
```

## Configuration Reference

### Camera Settings

```yaml
camera:
  name: "Furnace Opening"     # Display name
  id: "CAM-1"                 # Unique identifier
  role: "primary"             # primary | secondary | tertiary
  
  # RTSP URL format for Dahua NVR:
  # Main Stream: rtsp://USER:PASS@IP:554/cam/realmonitor?channel=N&subtype=0
  # Sub Stream:  rtsp://USER:PASS@IP:554/cam/realmonitor?channel=N&subtype=1
  rtsp_url: "rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=1"
  
  resolution: [704, 576]      # Expected resolution [width, height]
  fps: 25                     # Stream FPS
  codec: "h265"               # h264 | h265
  
  reconnect_attempts: 5       # Retry attempts on disconnect
  reconnect_delay_seconds: 5  # Seconds between retries
```

**Notes:**
- Use **Sub Stream** (subtype=1) for CV processing - lower bandwidth, sufficient quality
- Replace `USER:PASS@IP` with your NVR credentials
- Channel number corresponds to camera position in NVR

### Region of Interest (ROI)

```yaml
roi:
  furnace_door:
    x: 100          # Top-left X coordinate
    y: 50           # Top-left Y coordinate
    width: 500      # ROI width in pixels
    height: 400     # ROI height in pixels
```

ROI defines the area of the frame to analyze. Use `scripts/visualize_roi.py` to preview.

### Counting Lines Configuration

```yaml
counting_lines:
  line1:
    start: [480, 225]   # [x, y] start point
    end: [540, 215]     # [x, y] end point
  line2:
    start: [525, 280]
    end: [585, 270]
  line3:
    start: [565, 335]
    end: [630, 325]
  flow_direction:
    start: [530, 215]   # Arrow start (visual only)
    end: [620, 330]     # Arrow end (visual only)
```

**Calibration:**
- Lines should be perpendicular to conveyor flow
- L1 → L2 → L3 in direction of travel
- Use `scripts/calibrate_lines.py` for interactive adjustment
- See [Calibration Guide](CALIBRATION.md) for details

### Counting Thresholds

```yaml
counting:
  luminosity_threshold: 150    # Brightness threshold (0-255)
  min_bright_pixels: 80        # Minimum bright pixels to trigger
  sequence_timeout: 4.0        # Max seconds for L1→L3 sequence
  min_travel_time: 0.2         # Min seconds for L1→L3 (noise filter)
  line_thickness: 10           # Pixels around line to check
  min_consecutive_frames: 2    # Frames to confirm detection
```

| Parameter | Tuning Guide |
|-----------|--------------|
| `luminosity_threshold` | Lower = more sensitive, higher = only bright hot steel |
| `min_bright_pixels` | Increase if getting false positives from ambient light |
| `sequence_timeout` | Based on max piece travel time across lines |
| `min_travel_time` | Increase if noise triggers all 3 lines instantly |
| `min_consecutive_frames` | Increase for more reliability, decrease if missing pieces |

### Detection Settings (State Detection)

```yaml
detection:
  luminosity_threshold: 180    # Brightness for hot stock (0-255)
  luminosity_min_pixels: 1000  # Min bright pixels for detection
  
  motion_threshold: 25         # Pixel difference threshold
  motion_min_area: 500         # Min motion area in pixels
  
  break_threshold_seconds: 120 # Seconds without activity = BREAK
  min_run_duration_seconds: 10 # Min RUNNING duration before logging
  
  process_fps: 1               # Analysis rate (frames per second)
```

### Photo Capture

```yaml
photos:
  output_dir: "data/photos"           # Photo storage directory
  on_state_change: true               # Capture on state transitions
  periodic_interval_seconds: 300      # Capture every N seconds
```

Photos are saved as: `count_N_YYYYMMDD_HHMMSS.jpg`

### Logging

```yaml
logging:
  output_dir: "data/logs"    # Log directory
  level: "INFO"              # DEBUG | INFO | WARNING | ERROR
  rotation: "daily"          # Log rotation policy
```

**Log Files:**
- `counter.log` - Main application log
- `counter-error.log` - Error-only log
- `state_changes_YYYY-MM-DD.csv` - State transition log

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AIS_CV_CONFIG` | `config/settings.yaml` | Config file path |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | Firebase service account path |

## Firebase Configuration

See [Firebase Integration Guide](FIREBASE.md) for Firestore setup.

```yaml
# Firebase is configured via service account JSON, not YAML
# Place your service account file at:
# config/firebase-service-account.json
```

## Configuration Validation

Test your configuration:

```bash
# Test camera connection
python -c "
import yaml
import cv2

with open('config/settings.yaml') as f:
    config = yaml.safe_load(f)

cap = cv2.VideoCapture(config['camera']['rtsp_url'])
print('Connected!' if cap.isOpened() else 'Failed!')
cap.release()
"

# Test Firebase connection
python scripts/test_firebase.py
```

## Example Complete Configuration

```yaml
# AIS CV Configuration
# Copy to settings.yaml and customize

camera:
  name: "Furnace Opening"
  id: "CAM-1"
  role: "primary"
  rtsp_url: "rtsp://admin:mypassword@192.168.1.108:554/cam/realmonitor?channel=1&subtype=1"
  resolution: [704, 576]
  fps: 25
  codec: "h265"
  reconnect_attempts: 5
  reconnect_delay_seconds: 5

roi:
  furnace_door:
    x: 100
    y: 50
    width: 500
    height: 400

counting_lines:
  line1:
    start: [480, 225]
    end: [540, 215]
  line2:
    start: [525, 280]
    end: [585, 270]
  line3:
    start: [565, 335]
    end: [630, 325]
  flow_direction:
    start: [530, 215]
    end: [620, 330]

counting:
  luminosity_threshold: 150
  min_bright_pixels: 80
  sequence_timeout: 4.0
  min_travel_time: 0.2
  line_thickness: 10
  min_consecutive_frames: 2

detection:
  luminosity_threshold: 180
  luminosity_min_pixels: 1000
  motion_threshold: 25
  motion_min_area: 500
  break_threshold_seconds: 120
  min_run_duration_seconds: 10
  process_fps: 1

photos:
  output_dir: "data/photos"
  on_state_change: true
  periodic_interval_seconds: 300

logging:
  output_dir: "data/logs"
  level: "INFO"
  rotation: "daily"
```

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Calibration Guide](CALIBRATION.md)
- [Deployment Guide](DEPLOYMENT.md)
