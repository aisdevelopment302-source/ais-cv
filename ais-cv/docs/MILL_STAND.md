# Mill Stand Piece Counter

Computer vision tools for counting hot metal pieces at the mill stand.

This repo currently supports two approaches:

- Zone-based (single view): bright-pixel peaks in LEFT/RIGHT zones.
- Line-based (multi-view): two-line sequence per camera view + majority voting.

## Overview

### A) Zone-Based Counter (single view)

Two-zone detection:

- RIGHT zone: piece enters (upstream)
- LEFT zone: piece exits (downstream)
- Counting logic: RIGHT peak followed by LEFT peak within timeout = 1 piece counted

Flow direction:

```
RIGHT (entry)  ------------------>  LEFT (exit)
```

### B) Line-Based Multi-View Counter (recommended for live)

Per view:

- Line1 must trigger before Line2 (entry -> exit)
- Reverse order (Line2 before Line1) is ignored until Line2 clears

Across views:

- Detections are grouped into a voting window (default 5s)
- A piece is counted only if enough views detect it within the window (default: majority)

## Quick Start

All scripts below assume you use the repo venv (system python may not have OpenCV):

```bash
cd ais-cv
source venv/bin/activate
```

### A) Zone-Based: Calibrate Zones

```bash
python scripts/calibrate_mill_stand.py --video "recordings/mill stand day new.mp4"
```

Keyboard controls (from `scripts/calibrate_mill_stand.py`):

- Select zone: `L` (LEFT), `R` (RIGHT)
- Move: Arrow keys (1px), `W/A/S/D` (10px)
- Resize: `+`/`=` and `-` (width), `]`/`}` and `[`/`{` (height)
- Rotate: `E`/`F` (1 deg), `Shift+E`/`Shift+F` (5 deg)
- Video: `Space` play/pause, `.` / `,` frame step, `>` / `<` jump 5s, `0-9` jump 0%-90%
- Test mode: `T` toggle live detection testing
- Save: `V` save to `config/settings.yaml`, `P` print coordinates
- Help/Quit: `H` help, `Q`/`ESC` quit

### 2. Analyze Pixel Data (Optional)

Collect pixel statistics to determine optimal threshold:

```bash
# Log pixel data
python scripts/log_pixel_data.py \
  --video "recordings/mill stand day new.mp4" \
  --start 0 --end 100 \
  --output "data/pixel_log.csv"

# Visualize with statistics
python scripts/visualize_pixels.py \
  --input "data/pixel_log.csv" \
  --threshold 3000 \
  --ratio-threshold 0.12
```

### 3. Run the Counter

```bash
# Using ratio-based threshold (recommended)
python scripts/analyze_mill_stand.py \
  --video "recordings/mill stand day new.mp4" \
  --min-peak-ratio 0.12

# Using absolute pixel threshold
python scripts/analyze_mill_stand.py \
  --video "recordings/mill stand day new.mp4" \
  --min-peak-pixels 3500

# With visual display
python scripts/analyze_mill_stand.py \
  --video "recordings/mill stand day new.mp4" \
  --min-peak-ratio 0.12 \
  --display
```

## Scripts Reference

### analyze_mill_stand.py

Main analysis script for counting pieces.

```bash
python scripts/analyze_mill_stand.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--video` | mill stand view.mp4 | Path to video file |
| `--config` | config/settings.yaml | Path to configuration file |
| `--start` | 20 | Start position (% of video) |
| `--end` | 50 | End position (% of video) |
| `--min-peak-pixels` | 10000 | Absolute pixel threshold |
| `--min-peak-ratio` | None | Ratio threshold (e.g., 0.12 = 12%). If set, overrides pixel threshold |
| `--min-peak-duration` | 0.2 | Minimum peak duration in seconds |
| `--timeout` | 6.0 | Seconds to wait for LEFT after RIGHT peak |
| `--min-travel-time` | 0.3 | Minimum R→L travel time (filters noise) |
| `--brightness-threshold` | 160 | Minimum brightness for white-hot detection (0-255) |
| `--saturation-threshold` | 120 | Maximum saturation for white-hot detection (0-255) |
| `--display` | False | Show visual output window |
| `--output` | data/mill_stand_analysis.csv | Output CSV path |

**Example output:**
```
[00:16.0] LEFT  PEAK:   4,479px, ratio: 18.3% (dur: 3.44s, bright: 223)
          *** PIECE #1 COUNTED (R→L time: 1.48s) ***
```

### log_pixel_data.py

Logs pixel values for analysis and threshold tuning.

```bash
python scripts/log_pixel_data.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--video` | mill stand view.mp4 | Path to video file |
| `--start` | 20 | Start position (% of video) |
| `--end` | 28 | End position (% of video) |
| `--interval` | 0.5 | Sample interval in seconds |
| `--brightness-threshold` | 160 | Minimum brightness for detection |
| `--saturation-threshold` | 120 | Maximum saturation for detection |
| `--output` | data/pixel_log.csv | Output CSV path |

**Output CSV columns:**
- `frame`, `timestamp_sec`, `timestamp_str`
- `left_pixels`, `right_pixels` - Bright pixel counts
- `left_total`, `right_total` - Total zone pixels
- `left_ratio`, `right_ratio` - Ratio (bright/total)
- `left_brightness`, `right_brightness` - Average brightness

### visualize_pixels.py

Creates interactive HTML visualization of pixel data.

```bash
python scripts/visualize_pixels.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--input` | data/pixel_log.csv | Input CSV from log_pixel_data.py |
| `--threshold` | 5000 | Pixel count threshold line |
| `--ratio-threshold` | 0.15 | Ratio threshold line (e.g., 0.15 = 15%) |
| `--output` | data/pixel_visualization.html | Output HTML path |

**Output includes:**
- Interactive time-series graph (Plotly)
- Statistics tables (min, max, mean, P75, P85, P95)
- Threshold recommendations

### calibrate_mill_stand.py

Interactive tool for positioning detection zones.

```bash
python scripts/calibrate_mill_stand.py --video "path/to/video.mp4"
```

**Keyboard controls:**

See Quick Start (Zone-Based) section for the up-to-date key bindings.

## Configuration

Zone configuration in `config/settings.yaml`:

```yaml
mill_stand:
  zones:
    left:
      x: 370        # Top-left X coordinate
      y: 290        # Top-left Y coordinate
      width: 350    # Zone width in pixels
      height: 50    # Zone height in pixels
      angle: 23     # Rotation angle in degrees
    right:
      x: 1250
      y: 690
      width: 550
      height: 50
      angle: 25
```

## Multi-View Line Counter (Live)

This mode is configured under `mill_stand_lines:` and is designed for running from RTSP streams.

### 1. Configure `mill_stand_lines`

Start from the template:

```bash
cp config/settings.template.yaml config/settings.yaml
```

Fill in `mill_stand_lines.views[*].camera.rtsp_url`, and set `mill_stand_lines.enabled: true`.

Tip: you can keep RTSP URLs out of YAML by using env vars instead:

- `RTSP_VIEW1_URL`
- `RTSP_VIEW2_URL`
- `RTSP_VIEW3_URL`

Both `scripts/run_mill_stand_multi.py` and `scripts/calibrate_mill_stand_master.py` load `.env` if present.

### 2. Calibrate ROI + Lines with the Master Configurator

```bash
python scripts/calibrate_mill_stand_master.py
```

Controls (from `scripts/calibrate_mill_stand_master.py`):

- `1/2/3`: select active view
- Up/Down: select field
- Enter: edit field (or toggle boolean)
- `+` / `-`: nudge value
- `T`: toggle live test mode
- `V`: toggle ROI zoom view
- `S`: save to `config/settings.yaml`
- `Q`/`ESC`: quit

### 3. Run the Multi-View Counter

```bash
python scripts/run_mill_stand_multi.py --display
```

Useful options:

- Require a specific number of views to agree:

```bash
python scripts/run_mill_stand_multi.py --display --min-views 2
```

- Adjust voting window:

```bash
python scripts/run_mill_stand_multi.py --display --voting-window 5
```

- Debug a single view (1-based index):

```bash
python scripts/run_mill_stand_multi.py --display --view 1
```

- Save an annotated combined video:

```bash
python scripts/run_mill_stand_multi.py --display --output data/mill_stand_multi_annotated.mp4
```

### How It Counts

- Per view, Line1 must confirm before Line2 within `sequence_timeout`.
- The detection is confirmed only after `min_consecutive_frames` frames.
- Detections are collected into voting windows of length `voting.window_seconds`.
- A piece is counted when the number of views with detections in the window meets `voting.min_stands_required` (or majority if null).

## Single-View Multi-Stand Line Mode (legacy/experimental)

There is also a line calibrator and analyzer that operate on a single video frame and treat multiple stands as independent entry/exit line pairs within that same frame:

- `scripts/calibrate_mill_stand_lines.py`
- `scripts/analyze_mill_stand_lines.py`

These scripts currently use `mill_stand_lines.stands` in `config/settings.yaml` (different from the `views` schema used by the multi-view runner).

## Threshold Selection

### Ratio-Based Threshold (Recommended)

The ratio threshold normalizes for zone size differences:
```
ratio = bright_pixels / total_zone_pixels
```

**Advantages:**
- Consistent between different zone sizes
- More robust to camera/lighting changes
- Easier to tune (percentage-based)

**Recommended values:**
- Start with 10-15% ratio
- Use P85 values from `visualize_pixels.py` as guide

### Absolute Pixel Threshold

Fixed number of bright pixels required:
```
threshold = 3500  # pixels
```

**When to use:**
- When zone sizes are equal
- For backward compatibility

## Detection Algorithm

### White-Hot Metal Filter

The system uses combined filtering to detect white-hot metal and reject red/orange glare:

1. **Brightness filter**: `brightness > 160` (default)
   - White-hot metal is very bright
   
2. **Saturation filter**: `saturation < 120` (default)
   - White-hot metal is desaturated (whitish)
   - Red/orange glare is saturated (colorful)

### Peak Detection

1. **Peak start**: When pixel count/ratio exceeds threshold
2. **Peak tracking**: Track maximum value during peak
3. **Peak end**: When pixel count/ratio drops below threshold
4. **Validation**: Peak must last >= `min_peak_duration` (default 0.2s)

### Counting State Machine

```
States: IDLE → AWAITING_LEFT → IDLE

IDLE:
  - RIGHT peak detected → transition to AWAITING_LEFT, store RIGHT peak
  
AWAITING_LEFT:
  - LEFT peak detected within timeout → COUNT +1, transition to IDLE
  - Timeout exceeded → log timeout, transition to IDLE
  - Another RIGHT peak → replace pending RIGHT peak
```

## Output Files

### Analysis CSV (`data/mill_stand_analysis.csv`)

| Column | Description |
|--------|-------------|
| `event_type` | PEAK, COUNT, or TIMEOUT |
| `timestamp_sec` | Event time in seconds |
| `timestamp_str` | Event time as MM:SS.s |
| `zone` | LEFT or RIGHT |
| `peak_pixels` | Maximum bright pixels during peak |
| `avg_pixels` | Average pixels during peak |
| `duration_sec` | Peak duration |
| `peak_brightness` | Maximum brightness value |
| `count_id` | Piece number (for COUNT events) |
| `travel_time_sec` | R→L travel time (for COUNT events) |

### Pixel Log CSV (`data/pixel_log.csv`)

Time-series data for threshold analysis (see log_pixel_data.py section).

### Visualization HTML (`data/pixel_visualization.html`)

Interactive Plotly graph showing:
- Pixel counts over time (both zones)
- Ratio values over time (both zones)
- Threshold lines
- Statistics tables

## Troubleshooting

### No pieces counted

1. **Check zone positions**: Run `scripts/calibrate_mill_stand.py` and toggle test mode with `T`
2. **Threshold too high**: Lower `--min-peak-ratio` or `--min-peak-pixels`
3. **Review pixel data**: Run `log_pixel_data.py` and check max values

### Too many false counts

1. **Threshold too low**: Raise `--min-peak-ratio` or `--min-peak-pixels`
2. **Increase min duration**: Use `--min-peak-duration 0.3` or higher
3. **Check for glare**: Adjust `--saturation-threshold` lower

### Many timeouts (RIGHT without LEFT)

1. **Pieces not reaching LEFT zone**: Check zone positioning
2. **Timeout too short**: Increase `--timeout` value
3. **Metal moving too fast**: Decrease `--min-travel-time`

### Pixel values too low

1. **Camera exposure**: Check camera settings
2. **Different lighting**: Day vs night may need different thresholds
3. **Use ratio-based threshold**: More robust to lighting changes

## Example Workflow

```bash
# 1. Calibrate zones for new camera angle
python scripts/calibrate_mill_stand.py --video "recordings/new_video.mp4"

# 2. Collect pixel data
python scripts/log_pixel_data.py \
  --video "recordings/new_video.mp4" \
  --start 0 --end 100 \
  --output "data/pixel_log_new.csv"

# 3. Analyze statistics and determine threshold
python scripts/visualize_pixels.py \
  --input "data/pixel_log_new.csv" \
  --ratio-threshold 0.12

# 4. Run counter with determined threshold
python scripts/analyze_mill_stand.py \
  --video "recordings/new_video.mp4" \
  --min-peak-ratio 0.12 \
  --display

# 5. Review results and adjust threshold if needed
```

## Technical Details

### Zone Pixel Calculation

Total zone pixels = width × height (rotated rectangle approximation)

Example:
- LEFT zone: 350 × 50 = 17,500 pixels
- RIGHT zone: 550 × 50 = 27,500 pixels

With 12% ratio threshold:
- LEFT threshold: 0.12 × 17,500 = 2,100 bright pixels
- RIGHT threshold: 0.12 × 27,500 = 3,300 bright pixels

### Performance

- Processing: ~25 FPS (real-time on 1920×1080 video)
- Memory: ~200-300 MB
- CPU: Single-threaded, moderate load
