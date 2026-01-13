# AIS-CV Calibration Guide

## Overview

Proper calibration is essential for accurate piece counting. This guide covers:
1. Detection line positioning
2. Threshold tuning
3. Validation procedures

## Prerequisites

- Camera connected and streaming
- `settings.yaml` configured with RTSP URL
- Python environment activated

## Line Calibration

### Understanding the 3-Line System

```
                    CONVEYOR FLOW
                        ↓
    ┌─────────────────────────────────────────┐
    │                                         │
    │    L1 (Green) ═══════════════           │  ← First detection
    │                                         │
    │    L2 (Yellow) ═══════════════          │  ← Confirmation
    │                                         │
    │    L3 (Red) ═══════════════             │  ← Final count
    │                                         │
    └─────────────────────────────────────────┘
```

**Counting Logic:**
1. Piece triggers L1 (confirmed after N consecutive frames)
2. Same piece triggers L2 (within timeout window)
3. Same piece triggers L3 (count registered!)

### Interactive Calibration Tool

```bash
cd /home/adityajain/AIS/ais-cv
source venv/bin/activate
python scripts/calibrate_lines.py
```

**Controls:**
| Key | Action |
|-----|--------|
| `1`, `2`, `3` | Select Line 1/2/3 |
| `S` | Select Start point |
| `E` | Select End point |
| `Arrow Keys` | Move point by 1 pixel |
| `W/X/Z/D` | Move point by 10 pixels |
| `A` | Select flow arrow |
| `C` | Capture fresh frame from camera |
| `P` | Print current coordinates |
| `V` | Save to settings.yaml |
| `R` | Reset to defaults |
| `Q/ESC` | Quit |

### Line Positioning Guidelines

1. **Line Orientation**: Lines should be perpendicular to conveyor flow
2. **Line Spacing**: Allow enough space for piece to fully pass one line before reaching next
3. **Line Length**: Span the full width where pieces travel
4. **Avoid Edges**: Stay away from frame edges where lighting varies

**Good Placement:**
```
   Line crosses path where ALL pieces will pass
   ───────────────────────────────
   |                             |
   |      HOT PIECE              |
   |      ▓▓▓▓▓▓▓▓▓▓             |
   |                             |
   ───────────────────────────────
```

**Bad Placement:**
```
   Line too short - some pieces might miss it
   ─────────────
   |                             |
   |      HOT PIECE              |
   |      ▓▓▓▓▓▓▓▓▓▓             |  ← This piece would be missed!
   |                             |
```

### Saving Configuration

After positioning lines:
1. Press `V` to save to `settings.yaml`
2. Verify saved coordinates with `P`

The saved config will look like:
```yaml
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
```

## Threshold Tuning

### Key Thresholds

| Parameter | What It Does | Too Low | Too High |
|-----------|--------------|---------|----------|
| `luminosity_threshold` | Brightness cutoff for "hot" | False positives from ambient light | Misses cooler pieces |
| `min_bright_pixels` | Pixels needed to trigger | Noise triggers detection | Small pieces missed |
| `min_consecutive_frames` | Frames to confirm detection | More noise, less reliability | Slow pieces might not register enough frames |

### Tuning Procedure

1. **Start Conservative**: Begin with higher thresholds
2. **Run Test Mode**: `python run_counter.py --test`
3. **Observe Output**: Watch for false positives/negatives
4. **Adjust Incrementally**: Change one parameter at a time

**Test Mode Output:**
```
14:32:15 | L1:  245px | L2:    -   | L3:    -   | Count:5 | RUN
14:32:15 | L1:  287px | L2:    -   | L3:    -   | Count:5 | RUN
14:32:16 | L1:    -   | L2:  198px | L3:    -   | Count:5 | RUN
14:32:16 | L1:    -   | L2:  210px | L3:    -   | Count:5 | RUN
14:32:17 | L1:    -   | L2:    -   | L3:  189px | Count:5 | RUN
*** PIECE #6 COUNTED | Travel: 1.89s | Conf: 85% (HIGH) ***
```

### Luminosity Threshold

**Finding the Right Value:**
```bash
# Capture a frame during production
python -c "
import cv2
import yaml
import numpy as np

with open('config/settings.yaml') as f:
    config = yaml.safe_load(f)

cap = cv2.VideoCapture(config['camera']['rtsp_url'])
for _ in range(10):
    cap.grab()
ret, frame = cap.read()
cap.release()

gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
print(f'Min: {gray.min()}, Max: {gray.max()}, Mean: {gray.mean():.1f}')

# Check brightness distribution
hot_pixels = np.sum(gray > 150)
very_hot = np.sum(gray > 180)
print(f'Pixels > 150: {hot_pixels}')
print(f'Pixels > 180: {very_hot}')

cv2.imwrite('data/calibration_frame.jpg', frame)
"
```

**Typical Values:**
- Hot steel glow: 180-255 brightness
- Warm steel: 140-180 brightness
- Background: 0-100 brightness

**Recommended Starting Points:**
| Condition | `luminosity_threshold` |
|-----------|------------------------|
| Very hot furnace | 180 |
| Normal production | 150 |
| Cooler pieces | 130 |

### Minimum Bright Pixels

This prevents small bright spots (reflections, sparks) from triggering detection.

**Calculation Guide:**
```
Expected piece size on line: ~50-100 pixels wide
Line thickness: 10 pixels (default)
Minimum coverage: 50%

min_bright_pixels = (piece_width × line_thickness × 0.5)
                  = (75 × 10 × 0.5)
                  = 375 pixels (theoretical)

Practical: Start at 80-100, increase if false positives
```

### Sequence Timeout

Maximum time for a piece to travel from L1 to L3.

**Measure Actual Travel Time:**
1. Run in test mode
2. Observe travel times in log: `Travel: 1.89s`
3. Set timeout to 2-3x the maximum observed

**Typical Values:**
| Conveyor Speed | Timeout |
|----------------|---------|
| Fast | 2.0s |
| Normal | 4.0s |
| Slow | 6.0s |

### Minimum Travel Time

Filters out noise that triggers all lines simultaneously.

**Rule of Thumb:**
- Set to 0.2s (200ms) minimum
- Increase if seeing phantom counts with 0.0s travel time

## Validation

### Live Validation Procedure

1. Run counter: `python run_counter.py --test`
2. Manually count pieces for 30+ minutes
3. Compare CV count to manual count
4. Calculate accuracy: `(CV_count / manual_count) × 100%`

### Review Count Photos

Each count saves a photo in `data/photos/`:
```
count_1_20260112_143215.jpg
count_2_20260112_143218.jpg
...
```

Review photos to verify:
- Lines are correctly positioned
- Pieces are being detected at right moment
- No phantom counts from noise

### Accuracy Targets

| Metric | Target |
|--------|--------|
| Detection Rate | ≥98% (pieces counted / actual pieces) |
| False Positive Rate | ≤2% (phantom counts / total counts) |
| Travel Time Consistency | Within expected range |

## Common Calibration Issues

### Issue: Missed Counts

**Symptoms:** CV count is lower than actual
**Causes & Fixes:**
1. **Threshold too high** → Lower `luminosity_threshold`
2. **Lines too short** → Extend line endpoints
3. **Pieces too fast** → Lower `min_consecutive_frames`
4. **Sequence timeout too short** → Increase `sequence_timeout`

### Issue: Double Counts

**Symptoms:** CV count is higher than actual
**Causes & Fixes:**
1. **Lines too close together** → Space lines further apart
2. **Timeout too long** → Decrease `sequence_timeout`
3. **Pieces stopping between lines** → This is physical, not CV issue

### Issue: Phantom Counts

**Symptoms:** Counts when no piece is present
**Causes & Fixes:**
1. **Threshold too low** → Increase `luminosity_threshold`
2. **Ambient light** → Increase `min_bright_pixels`
3. **Reflections** → Reposition lines to avoid reflective surfaces
4. **Sparks/debris** → Increase `min_consecutive_frames`

### Issue: Inconsistent Detection

**Symptoms:** Works sometimes, fails other times
**Causes & Fixes:**
1. **Lighting changes** → May need different thresholds for day/night
2. **Camera position shift** → Re-calibrate lines
3. **Stream quality** → Check network stability

## Advanced: Dual Threshold Profiles

If lighting varies significantly, consider using environment variable for threshold:

```python
# In code
import os
threshold = int(os.getenv('AIS_LUMINOSITY', '150'))
```

```bash
# Day shift
export AIS_LUMINOSITY=150
python run_counter.py

# Night shift (pieces glow brighter against dark background)
export AIS_LUMINOSITY=180
python run_counter.py
```

## Related Documentation

- [Configuration Reference](CONFIGURATION.md)
- [Architecture](ARCHITECTURE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
