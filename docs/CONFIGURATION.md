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

### Mill Stand Counters

AIS-CV supports three mill-stand counting configurations:

1. `counting_areas` — **production**: independent multi-area 2-line detection with Firebase (`run_mill_counter.py`)
2. `mill_stand_lines` — legacy multi-view voting counter, no Firebase (`run_mill_stand_multi.py`)
3. `mill_stand` — zone-based, offline/video analysis only

#### `counting_areas` (production — `run_mill_counter.py`)

Each area is fully independent: it has its own ROI, L1, L2, and running counter.
A piece is confirmed by a `QuorumReconciler` when at least `quorum` distinct areas
fire within `piece_window_seconds`.  Near-simultaneous triggers from adjacent areas
(e.g. a person walking through two CAM-2 zones) are rejected when they arrive less
than `min_inter_area_gap_seconds` apart.

```yaml
counting_areas:
  # Quorum reconciler
  piece_window_seconds: 5.0          # Sliding window — areas must fire within this duration
  min_inter_area_gap_seconds: 1.5    # Reject trigger if previous area fired < this many seconds ago
  quorum: 2                          # Distinct areas needed to confirm a piece
  divergence_warn_threshold: 3       # Log warning when max(counts)-min(counts) exceeds this
  areas:
    - name: Area 1
      order: 1                   # Sort order for display; does not affect YAML index
      camera_rtsp: rtsp://admin:PASS@192.168.1.200:554/cam/realmonitor?channel=2&subtype=1
      roi:
        start: [x1, y1]          # Top-left of masking rectangle (full-frame pixels)
        end:   [x2, y2]          # Bottom-right
      line1:
        start: [x, y]            # L1 start endpoint (full-frame pixels)
        end:   [x, y]
      line2:
        start: [x, y]            # L2 start endpoint (full-frame pixels)
        end:   [x, y]
      min_line_pixels: 20        # Per-area min bright pixels to trigger a line
                                 # (overrides --min-line-pixels CLI default)
      use_bg_subtraction: true   # Replace absolute brightness threshold with
                                 # per-line EMA background subtraction.
                                 # Recommended when sunlight saturates the background.
      bg_delta: 30               # Trigger when pixel brightness exceeds
                                 # (EMA baseline + bg_delta). Active only when
                                 # use_bg_subtraction: true.
                                 # Raise to reduce false positives; lower if missing pieces.
      dwell_spike_factor: 0.3    # Spike re-arm: if bright-pixel count exceeds
                                 # peak * (1 + factor) during dwell suppression,
                                 # the dwell timer resets so a new piece can be detected.
                                 # Default 0.3 = 30% above peak. Lower = more sensitive
                                 # re-arm; raise if spurious re-arms occur.

    - name: Area 2
      order: 2
      # ... same structure

    - name: Area 3
      order: 3
      # ... same structure
```

**Notes:**

- All coordinates are in the **resized frame** (704×576 after `StreamManager` resize).
- L1 and L2 **must lie inside the ROI rectangle** — pixels outside the ROI are zeroed
  before line brightness is checked.
- The `order` field controls sort order in the HUD; it does not change which YAML
  array index is written when you press `S` to save. The internal `yaml_idx` tracks
  the original array position.
- `min_line_pixels` overrides the `--min-line-pixels` CLI default on a per-area basis.
  Adjust interactively with `[` / `]` keys in `--display` mode and save with `S`.
- `use_bg_subtraction` replaces the absolute `--brightness-threshold` check with a
  rolling per-pixel EMA baseline. Set `true` for outdoor or sunlit environments.
  The baseline warms up over ~20 seconds on startup.
- `bg_delta` controls how much above the local background a pixel must be to count
  as "bright". Default 30. Tune per-area; the YAML value overrides `--bg-delta`.
- `dwell_spike_factor` enables spike re-arm during dwell suppression. If the
  bright-pixel count on a dwelled line jumps more than `factor * 100`% above the
  peak seen during that dwell, the dwell timer resets and a new L1/L2 crossing can
  fire. This handles the case where a previous piece is still on the line when the
  next piece arrives. Default `0.3` (30%). Set per-area; omit to use the default.
- Calibrate interactively: `python scripts/run_mill_counter.py --display --no-firebase`
- See [Calibration Guide](CALIBRATION.md#cam-2-mill-stand-calibration-run_mill_counterpy)
  for step-by-step instructions.

---
#### `mill_stand` (zone-based)

```yaml
mill_stand:
  enabled: true
  zones:
    left:
      x: 370
      y: 290
      width: 350
      height: 50
      angle: 23
    right:
      x: 1250
      y: 690
      width: 550
      height: 50
      angle: 25
  counting:
    luminosity_threshold: 160
    min_bright_pixels: 100
    sequence_timeout: 6.0
    min_travel_time: 0.3
```

Notes:

- `zones.*` are rotated rectangles in original frame coordinates.
- Zone calibration is done with `scripts/calibrate_mill_stand.py` (saves into `config/settings.yaml`).

#### `mill_stand_lines` (multi-view line-based)

Configured as a list of `views`, each with its own camera, ROI crop, and two detection lines.

```yaml
mill_stand_lines:
  enabled: true
  views:
  - name: "View 1"
    camera:
      rtsp_url: "rtsp://USER:PASSWORD@NVR_IP:554/cam/realmonitor?channel=2&subtype=1"
      resolution: [1920, 1080]
      fps: 25
    roi:
      start: [0, 0]
      end: [1920, 1080]
    line1:
      start: [0, 0]
      end: [0, 0]
    line2:
      start: [0, 0]
      end: [0, 0]
    # Optional per-view overrides (otherwise inherits mill_stand_lines.counting)
    counting:
      luminosity_threshold: 160
      min_bright_pixels: 100
  voting:
    window_seconds: 5.0
    min_stands_required: null  # null = majority
  counting:
    luminosity_threshold: 160
    min_bright_pixels: 100
    sequence_timeout: 3.0
    min_travel_time: 0.0
    min_consecutive_frames: 2
    line_thickness: 10
    hot_metal_filter_enabled: true
    min_saturation: 20
    min_red_dominance: 1.1
    min_warmth_ratio: 1.05
    target_resolution: [704, 576]
```

Key fields:

- `views[*].roi`: crop applied before resizing; line coordinates are in original frame coordinates (and are shifted when ROI is applied).
- `views[*].line1` / `views[*].line2`: entry/exit lines; per-view order must be line1 -> line2.
- `voting.window_seconds`: how long to wait while collecting per-view detections before voting.
- `voting.min_stands_required`: required number of views to count (null defaults to majority).
- `counting.target_resolution`: frames are resized to this for processing; line coordinates are scaled automatically.

Environment variable overrides:

- For live RTSP runs you can override URLs via `.env`:
  - `RTSP_VIEW1_URL`, `RTSP_VIEW2_URL`, `RTSP_VIEW3_URL`

Related scripts:

- `scripts/calibrate_mill_stand_master.py` (edit ROI/lines/counting with live preview; saves to `config/settings.yaml`)
- `scripts/run_mill_stand_multi.py` (run multi-view counter from RTSP, no Firebase)
- `scripts/run_mill_counter.py` (run multi-view counter with Firebase analytics)

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
# Test Firebase connection
python scripts/test_firebase.py
```

## Example Complete Configuration

```yaml
# AIS CV Configuration
# Copy to settings.yaml and customize

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
