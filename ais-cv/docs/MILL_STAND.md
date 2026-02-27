# Mill Stand Counter (CAM-2 + CAM-3)

Counts hot steel pieces at the mill stand using Camera 2 (NVR channel 2, 3 areas)
and Camera 3 (NVR channel 3, 1 area). All four areas count the same pieces from
different angles for redundancy.
The production counter is `scripts/run_mill_counter.py` — multi-area independent
2-line detection with Firebase integration and median-based count reconciliation.

---

## How It Works

A single RTSP feed from CAM-2 is processed as three independent **counting areas**,
and a separate RTSP feed from CAM-3 adds a fourth area — all counting the same
physical pieces from different camera angles. Each area is defined by:

- An **ROI** rectangle that masks the frame — only pixels inside this box can trigger
  the area's lines, preventing cross-area false triggers from bright objects elsewhere
- An **entry line** (L1)
- An **exit line** (L2)

A piece is detected at an area when L1 confirms bright pixels for
`min_consecutive_frames`, followed by L2 confirming — in that order — within
`sequence_timeout`.  Each area counts **fully independently** — no ordering or voting
between areas is required.

After every detection, a `CountReconciler` computes:

```
joined_count = median(counts for all areas)
```

This is the authoritative count pushed to Firebase. If `max(counts) - min(counts) >
divergence_warn_threshold` a warning is logged.

```
CAM-2 RTSP frame                         CAM-3 RTSP frame
       │                                         │
       ▼                                         ▼
StreamManager (one VideoCapture per unique URL)
       │  frame                            │  frame
       ├─▶ AreaDetector 1 (CAM-2)  →  count_1   │
       ├─▶ AreaDetector 2 (CAM-2)  →  count_2   │
       ├─▶ AreaDetector 3 (CAM-2)  →  count_3   │
                                                  └─▶ AreaDetector 4 (CAM-3) → count_4
                                                           │
                                                  CountReconciler
                                    joined = median(count_1, count_2, count_3, count_4)
                                                           │
                                                    Firebase push
                                               (only when joined increases)
```

**Why multiple areas across two cameras?**
Different physical positions on the same feed (CAM-2 areas 1–3) give redundancy
within one camera. CAM-3 (area 4) adds a completely independent camera angle,
further protecting against a single camera mis-detecting. The median rejects a
single runaway counter (e.g. an area whose lines catch reflections). If all areas
diverge by more than `divergence_warn_threshold`, the operator is alerted.

**Why ROI masking?**
Without it, a glowing piece in Area 1's field of view can falsely trigger Area 2's
lines (which are just pixel coordinates on the full frame). Each area's ROI zeroes
out everything outside its rectangle before line checking.

---

## Quick Start

```bash
cd /home/adityajain/AIS/ais-cv
source venv/bin/activate
```

### Step 1 — Calibrate (display mode)

```bash
python scripts/run_mill_counter.py --display --no-firebase
```

Controls:

| Key | Action |
|-----|--------|
| `Tab` / `1`-`9` | Cycle / jump to focused area |
| Mouse drag | Move ROI corners and L1/L2 endpoints (filled circles = handles) |
| `S` | Save focused area's ROI + lines to `settings.yaml` |
| `R` | Reset all detectors and area counts |
| `Space` | Pause / resume |
| `H` | Help |
| `Q` / Esc | Quit |

Calibrate each area in turn:
1. Press `Tab` (or `1`, `2`, `3`) to focus the area you want to position
2. Drag the ROI rectangle to enclose **only** the steel bar path for that area
3. Drag L1 to the entry line position; drag L2 to the exit line position
4. Press `S` to save — the log confirms which YAML area was written
5. Repeat for the next area

### Step 2 — Run (production)

```bash
# With Firebase
python scripts/run_mill_counter.py

# Without Firebase (testing)
python scripts/run_mill_counter.py --no-firebase

# With display (monitoring + calibration)
python scripts/run_mill_counter.py --display --no-firebase

# Verbose per-frame state (console)
python scripts/run_mill_counter.py --no-firebase --test

# Limited run
python scripts/run_mill_counter.py --duration 60 --no-firebase
```

### Step 3 — Deploy as systemd service

```bash
sudo systemctl start ais-mill-counter
sudo systemctl status ais-mill-counter
sudo journalctl -u ais-mill-counter -f
```

---

## Scripts Reference

### `run_mill_counter.py` — Production Runner

```
python scripts/run_mill_counter.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--display` | off | Show live annotated video + calibration UI |
| `--no-firebase` | off | Run without Firebase sync |
| `--test` | off | Print per-frame line state to console |
| `--duration SECS` | forever | Stop after N seconds |
| `--brightness-threshold N` | 160 | Min pixel brightness to count as "bright" (0-255); ignored per-area when `use_bg_subtraction: true` |
| `--bg-delta N` | 30 | Global fallback: min brightness above per-line EMA baseline to trigger (used when `use_bg_subtraction: true`); per-area `bg_delta` in YAML takes precedence |
| `--min-line-pixels N` | 30 | Min bright pixels on a line to trigger it |
| `--min-consecutive-frames N` | 2 | Consecutive frames required to confirm a line |
| `--sequence-timeout SECS` | 4.0 | Max L1→L2 wait time per area |
| `--max-dwell-time SECS` | 2.0 | Suppress continuous trigger longer than this |

### `run_mill_stand_multi.py` — Legacy No-Firebase Runner

Runs the older multi-view voting counter. No Firebase. Kept for reference/comparison.

```bash
python scripts/run_mill_stand_multi.py --display
```

### `run_mill_stand_compare_cam2.py` — Comparison Tool

Side-by-side Peak Detection vs 2-Line Detection on CAM-2. Use for threshold analysis.

```bash
python scripts/run_mill_stand_compare_cam2.py
```

---

## Configuration Reference

`config/settings.yaml` section: `counting_areas`

```yaml
counting_areas:
  divergence_warn_threshold: 3   # Warn when max(areas) - min(areas) exceeds this
  areas:
    - name: Area 1
      order: 1
      camera_rtsp: rtsp://admin:PASS@192.168.1.200:554/cam/realmonitor?channel=2&subtype=1
      roi:
        start: [x1, y1]          # Top-left corner (full-frame coordinates)
        end:   [x2, y2]          # Bottom-right corner
      line1:
        start: [x, y]            # L1 start — full-frame coordinates
        end:   [x, y]
      line2:
        start: [x, y]            # L2 start — full-frame coordinates
        end:   [x, y]
      min_line_pixels: 20        # Per-area override of --min-line-pixels
      use_bg_subtraction: true   # Enable EMA background subtraction (recommended in sunlight)
      bg_delta: 30               # Trigger when pixel > baseline + bg_delta

    - name: Area 2
      order: 2
      # ... same structure (channel=2)

    - name: Area 3
      order: 3
      # ... same structure (channel=2)

    - name: CAM3 Area 1
      order: 4
      camera_rtsp: rtsp://admin:PASS@192.168.1.200:554/cam/realmonitor?channel=3&subtype=1
      # ... same ROI/line structure — coordinates are in CAM-3's 704×576 frame space
      min_line_pixels: 10
      use_bg_subtraction: true
      bg_delta: 30
```

**Coordinate system:** All coordinates (ROI and lines) are in the **full frame** space
after `StreamManager` resizes frames to `PANEL_W × PANEL_H` (704×576). Lines do not
need to be remapped when ROI changes — the ROI only masks what pixels are visible to
that area's lines.

**`yaml_idx` note:** When the `S` key saves an area, it uses the area's original
position in the `counting_areas.areas[]` array (not its sorted position), so
saving always writes to the correct YAML entry even if `order` values are
non-sequential.

---

## Detection Logic

### Per-Area Sequence (`TwoLineDetector`)

```
Masked frame (pixels outside ROI = 0)
        │
        ▼
Grayscale conversion
        │
        ├── Check L1 mask: count pixels > brightness_threshold
        │       ≥ min_bright_pixels?
        │           → increment l1_consec
        │       ≥ min_consecutive_frames AND debounce OK?
        │           → L1 CONFIRMED  →  start pending timer
        │
        └── Check L2 mask (only after L1 confirmed)
                ≥ min_bright_pixels?
                    → increment l2_consec
                ≥ min_consecutive_frames AND within sequence_timeout?
                    → PIECE COUNTED  (area count++)
```

**Dwell suppression:** If a line stays triggered continuously for
`> max_dwell_time` seconds (person standing on line, debris) the trigger is
suppressed until it clears.

### Background Subtraction (`use_bg_subtraction`)

When `use_bg_subtraction: true` is set on an area, the absolute brightness
threshold (`pixel > brightness_threshold`) is replaced with a **per-line EMA
baseline** comparison:

```
trigger_condition = sum(pixels > baseline + bg_delta) >= min_line_pixels
```

Each line (`L1`, `L2`) maintains its own per-pixel float32 baseline array.
Every frame where the line is **not** triggered, the baseline updates via EMA:

```
baseline = (1 - bg_alpha) * baseline + bg_alpha * current_pixels
```

`bg_alpha` defaults to `0.05` — the baseline converges in ~20 seconds of idle
frames. While the line is triggered (piece present), the baseline is frozen to
prevent the passing steel from corrupting the background model.

**Why this matters:** In bright sunlight the background itself can exceed an
absolute threshold of 160. This permanently triggers the line → dwell
suppression kicks in after 2s → the line goes dead. With background
subtraction, only pixels that are brighter *than normal background* for that
line trigger detection.

**Tuning `bg_delta`:**

| Environment | Suggested `bg_delta` |
|-------------|----------------------|
| Sunlit outdoor scene, high background brightness | 20–30 |
| Indoor / sheltered, low background brightness | 30–50 |
| Very dark background | 50+ |

Raise `bg_delta` to reduce false positives; lower it if pieces are missed.
Tune per-area in `settings.yaml` — the YAML value takes precedence over
`--bg-delta`.

**Warm-up note:** On startup the baseline is seeded from the first frame seen
on each line. It reaches a stable background estimate after ~20 seconds
(at `bg_alpha=0.05`). Counts during the first 20s may be slightly less
reliable if the camera is pointed at a bright scene.



```
Any area triggers
        │
        ▼
counts[area_idx] += 1
joined_count = int(statistics.median(counts))
diverged = (max(counts) - min(counts)) > divergence_warn_threshold
        │
        ├── diverged? → log WARNING with counts
        └── joined_count increased? → push Firebase + flash HUD
```

The median means:
- 1 area of 4 running ahead: `[7, 5, 5, 5]` → joined = 5 (correct)
- All areas agree: `[5, 5, 5, 5]` → joined = 5
- CAM-3 lagging: `[5, 5, 5, 3]` → joined = 5 (CAM-3 doesn't pull median down)
- 2 areas ahead, 2 behind: `[6, 6, 5, 5]` → joined = 5 (floor of avg of middle values)

---

## HUD (display mode)

The overlay drawn on each camera window shows:

```
FOCUSED: Area 1  [Tab/1-9=cycle  S=save  R=reset  H=help]
┌──────────────────────────────────────┐
│ COUNT: 42                            │   ← joined (median) count; flashes yellow on hit
│ (median of all areas)                │
│ ───────────────────────────────────  │
│ [*] Area 1 [CAM-2]: 42              │   ← [*] = matches joined count
│ [ ] Area 2 [CAM-2]: 41              │   ← [ ] = diverged from joined
│ [*] Area 3 [CAM-2]: 42              │
│ [*] CAM3 Area 1 [CAM-3]: 42        │   ← CAM-3's independent vote
│ divergence: OK                       │   ← red "! DIVERGENCE WARNING" if triggered
└──────────────────────────────────────┘
L1: ON   L2: off   travel=1.23s     ← focused area live state
min_px=20  bg+30  [/]               ← shown when use_bg_subtraction: true; [/] = adjust min_line_pixels
```

---

## Threshold Tuning

Use CSV logs for data-driven tuning:

```bash
# Per-frame brightness log per area (created automatically when running)
cat data/logs/line_brightness_area1.csv
cat data/logs/line_brightness_area2.csv
cat data/logs/line_brightness_area3.csv
```

Columns: `timestamp, l1_bright_px, l2_bright_px, l1_triggered, l2_triggered,
l1_confirmed, l2_confirmed, l1_dwell_s, l2_dwell_s, pending, count, event`

**Key events to look for:**

| Event | Meaning |
|-------|---------|
| `L1_CONFIRMED` | Entry line confirmed — piece entered area |
| `COUNTED` | L1→L2 sequence complete — piece counted |
| `REJECTED_TIMEOUT` | L2 confirmed too late — increase `--sequence-timeout` |
| `PENDING_EXPIRED` | L1 fired but L2 never did within timeout |
| `L1_DWELL_SUPPRESSED` | L1 stayed triggered too long — adjust ROI or `--max-dwell-time` |

**Starting values:**

| Condition | `--brightness-threshold` | `--min-line-pixels` |
|-----------|--------------------------|----------------------|
| Very bright white-hot steel | 180 | 40 |
| Normal hot steel | 160 | 30 |
| Cooler / dimmer pieces | 130 | 20 |

When `use_bg_subtraction: true`, `--brightness-threshold` is not used for that
area — tune `bg_delta` instead (see [Background Subtraction](#background-subtraction-use_bg_subtraction)).

---

## Troubleshooting

### Lines stop triggering in bright sunlight

**Root cause:** Absolute brightness threshold (`pixel > brightness_threshold`)
is permanently exceeded by the sunlit background. The line stays continuously
triggered → dwell suppression fires after `max_dwell_time` → line goes silent.

**Fix:** Enable per-line EMA background subtraction:
1. In `config/settings.yaml`, set `use_bg_subtraction: true` and `bg_delta: 30`
   on the affected area(s).
2. Restart the counter. The baseline will warm up over ~20 seconds.
3. If still triggering spuriously, raise `bg_delta` (try 40–50).
4. If pieces are being missed, lower `bg_delta` (try 20).

See [Background Subtraction](#background-subtraction-use_bg_subtraction) for
full details.

### Area never detects

1. Run `--display --no-firebase` — visually confirm L1/L2 lines cross the actual piece path
2. Lower `--brightness-threshold` (try 130)
3. Lower `--min-line-pixels` (try 15)
4. Check ROI: the ROI rectangle must **contain** the L1 and L2 lines, otherwise the
   masked frame will have zero pixels on those lines and they can never trigger
5. Run `--test` and watch console output — if no L1/L2 state changes print, the lines
   are not being hit

### Area double-counts

1. Increase `--max-dwell-time` (default 2.0s) — dwell suppression kicks in sooner
2. Increase `--min-consecutive-frames` (try 3)
3. Reduce `--sequence-timeout` to prevent stale L1 state from pairing with a later L2

### Joined count not increasing even when areas trigger

The joined count is the **median** — a single area firing repeatedly won't raise the
joined count if the other areas haven't caught up. With 4 areas, examples:
`counts=[1,0,0,0]` → `median=0`, `counts=[1,1,0,0]` → `median=0`,
`counts=[1,1,1,0]` → `median=1`. This is by design. If only one area is
reliably detecting, consider removing the non-detecting areas from the config.

### Divergence warning constantly firing

Areas are diverging by more than `divergence_warn_threshold` (default 3). Either:
- One area has a miscalibrated ROI and is double-counting — recalibrate it
- One area is partially obstructed — check camera feed
- Increase `divergence_warn_threshold` in `settings.yaml` if the gap is expected

### Save (S key) doesn't seem to persist

Check the log output after pressing S — it prints `Saved area N (Area X): ROI=...`
with the YAML index. If you see index 0 when you expected 2, your `order` values in
`settings.yaml` may not match the array positions — the log will show which index
was actually written.

---

## Firebase Integration

| Firebase write | Trigger |
|----------------|---------|
| `live/mill_stand` status | Every 60s heartbeat + on piece counted + on break |
| `sessions/{id}` create | When mill starts running after a break |
| `sessions/{id}` update | Every time joined count increases |
| `sessions/{id}` end | When break detected (idle > 300s) or shutdown |
| `daily/{date}` increment | Every time joined count increases |
| `hourly/{date}/hours/{HH}` | Every time joined count increases |

On startup, `get_mill_today_count()` is read from Firebase and used to seed all area
counters so the reconciler starts from the correct daily baseline.

---

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Configuration](CONFIGURATION.md)
- [Calibration](CALIBRATION.md)
- [Firebase Integration](FIREBASE.md)
- [Deployment](DEPLOYMENT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
