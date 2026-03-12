# AIS-CV Calibration Guide

## CAM-2 Mill Stand Calibration (`run_mill_counter.py`)

The mill stand counter has a built-in calibration UI accessible via `--display`.
No separate calibration script is needed.

### Launch Calibration Mode

```bash
cd /home/adityajain/AIS/ais-cv
source venv/bin/activate
python scripts/run_mill_counter.py --display --no-firebase
```

The live CAM-2 feed appears in a window with all configured areas drawn on top.

### Controls

| Key / Action | Effect |
|---|---|
| `Tab` | Cycle focus to next area (within this camera window) |
| `1` – `9` | Jump directly to area N (1-indexed) |
| **Left-click + drag** handle | Move ROI corner or L1/L2 endpoint |
| `S` | Save focused area's current ROI + lines to `config/settings.yaml` |
| `R` | Reset all detectors and all area counts |
| `Space` | Pause / resume detection |
| `H` | Print key help to console |
| `Q` / Esc | Quit |

Handles (filled circles) are larger and brighter for the focused area.
Unfocused areas are drawn dimmer.

### Per-Area Calibration Workflow

Repeat these steps for each area (Area 1, Area 2, Area 3):

1. **Focus the area** — press `Tab` or the corresponding number key.
   The title bar shows `FOCUSED: Area N`.

2. **Position the ROI rectangle** — drag the four corner handles so the rectangle
   tightly encloses the section of the steel bar path that belongs to this area.
   - The ROI is the **detection gate**: only pixels inside it can trigger this area's
     lines. A bright piece outside the ROI will not affect this area.
   - Make the ROI as small as possible while still fully containing L1 and L2.

3. **Position L1 (entry line)** — drag its two endpoints so the line crosses the
   bar path **before** the piece enters the measurement zone.
   L1 is drawn in the area's primary color.

4. **Position L2 (exit line)** — drag its endpoints so the line crosses the bar
   path **after** L1. L2 is drawn slightly darker than L1.
   - L1 and L2 must both lie **inside** the ROI rectangle, otherwise the masked
     frame will have no pixels on those lines and detection will never fire.

5. **Verify** — watch the HUD while a piece passes. You should see:
   - `L1: ON` flash briefly as the piece crosses L1
   - `L2: ON` flash shortly after
   - Area count increment and the flash banner appear

6. **Save** — press `S`. The log output confirms:
   ```
   INFO  Saved area 0 (Area 1): ROI=(110,192)-(267,295)  L1=(239,242)-(215,288)  L2=(172,276)-(202,224)
   ```
   The number after "area" is the YAML array index (0-based). If it's wrong,
   check that `order` values in `settings.yaml` match the expected sort order.

### What Gets Saved

Pressing `S` writes to `config/settings.yaml` under
`counting_areas.areas[yaml_idx]`:

```yaml
roi:
  start: [x1, y1]
  end:   [x2, y2]
line1:
  start: [x, y]
  end:   [x, y]
line2:
  start: [x, y]
  end:   [x, y]
min_line_pixels: N
```

The `name`, `order`, `camera_rtsp`, `use_bg_subtraction`, and `bg_delta` fields
are not modified by the `S` key save — edit those directly in `settings.yaml`.

### `min_line_pixels` Quick Tuning (`[` / `]` Keys)

In `--display` mode, with an area focused:

| Key | Effect |
|-----|--------|
| `[` | Decrease focused area's `min_line_pixels` by 1 and auto-save |
| `]` | Increase focused area's `min_line_pixels` by 1 and auto-save |

The current value is shown in the HUD: `min_px=N`. Use this while pieces are
passing to find the smallest value that reliably triggers without false positives.

### Background Subtraction Tuning (`bg_delta`)

When `use_bg_subtraction: true` is set for an area, the detection threshold is
**relative** to the local background, not an absolute pixel value. The HUD
shows `bg+N` for the focused area when this mode is active.

**`bg_delta` tuning procedure:**

1. Run `--display --no-firebase` during production.
2. Watch the HUD line state (`L1: ON / off`) as pieces pass and between passes.
3. If lines trigger spuriously between pieces: **raise** `bg_delta` (e.g. 30 → 40).
4. If pieces are not triggering lines: **lower** `bg_delta` (e.g. 30 → 20).
5. Edit `config/settings.yaml` directly under the area's `bg_delta:` field.
6. Restart the counter — changes take effect immediately on next run.

**Baseline warm-up:** On startup the EMA baseline is seeded from the first
frame seen on each line. At `bg_alpha=0.05` the baseline stabilises after
approximately **20 seconds** of idle frames. During this warm-up window,
detection sensitivity may be slightly reduced if the camera starts pointed at
a bright scene. This is expected behaviour.

### Verifying Detection After Calibration

Use `--test` mode to print per-frame state to the console:

```bash
python scripts/run_mill_counter.py --no-firebase --test
```

Expected output when a piece passes Area 1:

```
14:32:15 | Area 1 | L1=ON  L2=off | PENDING  | joined=0  [A1:0  A2:0  A3:0]
14:32:15 | Area 1 | L1=ON  L2=off | PENDING  | joined=0  [A1:0  A2:0  A3:0]
14:32:16 | Area 1 | L1=ON  L2=ON  |          | joined=0  [A1:1  A2:0  A3:0]
```

If nothing prints, the lines are not being hit — recalibrate ROI and line positions.

### CSV Brightness Logs

Each area writes a per-frame CSV to `data/logs/line_brightness_areaN.csv`.
Use it to find the actual brightness values your pieces produce:

```bash
# Sort by l1_bright_px descending to find peak brightness during a piece pass
sort -t, -k2 -rn data/logs/line_brightness_area1.csv | head -20
```

**Absolute mode (`use_bg_subtraction: false`):**
Set `--brightness-threshold` below the observed peak but above the ambient
noise floor.

**Background subtraction mode (`use_bg_subtraction: true`):**
The logged `l1_bright_px` / `l2_bright_px` values reflect pixels above the
EMA baseline (i.e. the delta count). Set `bg_delta` so that piece-pass values
reliably exceed `min_line_pixels`, while idle frames stay below it.

---

## Related Documentation

- [Configuration Reference](CONFIGURATION.md)
- [Architecture](ARCHITECTURE.md)
- [Mill Stand Counter](MILL_STAND.md)
- [Troubleshooting](TROUBLESHOOTING.md)
