# AIS-CV Architecture

## System Overview

AIS-CV counts hot steel pieces at the mill stand from a Dahua NVR using CAM-2 (channel 2, 3 areas) and CAM-3 (channel 3, 1 area), with Firebase sync for real-time dashboards and session analytics. All four areas count the same pieces from different angles for redundancy.

```
Dahua NVR (192.168.1.200)
├── Channel 2 (CAM-2) ──▶ AreaDetectors 1-3 ──┐
└── Channel 3 (CAM-3) ──▶ AreaDetector 4   ──┴──▶ QuorumReconciler ──▶ Firebase (live)
```

---

## Counter — Mill Stand (CAM-2 + CAM-3)

### Pipeline

```
RTSP (channel 2) — shared across CAM-2 areas     RTSP (channel 3) — CAM-3 area
       │                                                  │
       ▼                                                  ▼
  StreamManager                                    StreamManager
  (one cv2.VideoCapture per unique RTSP URL)
       │  frame (resized to 704×576)               │  frame (resized to 704×576)
       ├──▶ AreaDetector 1 (CAM-2)                 └──▶ AreaDetector 4 (CAM-3)
       │     ├── ROI mask: zero pixels outside roi rectangle                │
       │     └── TwoLineDetector.update(masked_frame, l1, l2, t)            │
       │         └── L1→L2 sequence within sequence_timeout → count_1++    │
       │                                                                     │
       ├──▶ AreaDetector 2 (CAM-2)  → count_2++                            │
       └──▶ AreaDetector 3 (CAM-2)  → count_3++                            │ count_4++
                                     │                                       │
                            QuorumReconciler ◀─────────────────────────────┘
              piece confirmed when ≥ quorum areas fire within piece_window_seconds
              near-simultaneous triggers (< min_inter_area_gap_s) rejected as false positive
                                     │
                             piece_confirmed()?
                                     │ YES
                                SessionManager.on_piece_counted()
                                     │
                                FirebaseClient
                                ├── push_mill_count()
                                ├── create/update/end sessions/
                                └── update live/mill_stand
```

### Entry Point

`scripts/run_mill_counter.py` — runs continuously, deployed as `ais-mill-counter.service`.

### Key Design Decisions

**ROI masking (not cropping):** Each `AreaDetector` zeroes pixels outside its ROI
rectangle before passing the frame to `TwoLineDetector`. Line coordinates stay in
full-frame space — no remapping is needed. This prevents a bright piece at one area's
position from falsely triggering another area's lines.

**`yaml_idx` field on `AreaConfig`:** The `counting_areas.areas[]` list is sorted by
`order` at load time. To ensure `S` (save) always writes to the correct YAML slot,
each `AreaConfig` stores `yaml_idx` — its original 0-based position in the YAML
array before sorting. `save_area_positions(adet.cfg.yaml_idx, ...)` is called
instead of the sorted list index.

**Quorum reconciliation:** `QuorumReconciler` confirms a piece only when `≥ quorum`
distinct areas fire within a `piece_window_seconds` sliding window.  Replacing the
old median approach eliminates false positives where a person walking through two
adjacent CAM-2 zones triggered both nearly simultaneously and was counted as 2 pieces.

**`piece_confirmed()`:** Firebase is only pushed when `piece_count > _last_piece_count`.
This prevents duplicate pushes when the same piece triggers multiple areas — the first
trigger to complete the quorum confirms the piece; subsequent area fires for the same
piece are absorbed into the next window (which clears on confirmation).

---

## Source Modules

### `scripts/run_mill_counter.py` — Self-Contained Mill Stand Counter

All CAM-2 detection and counting logic lives directly in this script (no separate
`src/` module). Key classes:

**`TwoLineDetector`** — single-area 2-line detection:
- Builds L1/L2 pixel masks once per unique line position; rebuilds on change
- **Detection mode A (absolute):** counts pixels `> brightness_threshold` on each mask
- **Detection mode B (background subtraction):** when `use_bg_subtraction=True`,
  maintains a per-pixel float32 EMA baseline per line; triggers when
  `sum(pixels > baseline + bg_delta) >= min_line_pixels`. Baseline updates only
  while the line is **not** triggered (prevents steel from corrupting the model).
  Baseline is re-seeded if its shape changes (line moved during calibration).
- Dwell suppression: continuous trigger `> max_dwell_time` is suppressed
- **Dwell spike re-arm:** if bright-pixel count surges `> peak * (1 + dwell_spike_factor)`
  during dwell suppression, the dwell timer resets and a new L1/L2 rising edge fires — handles
  a second piece arriving while the previous piece is still on the line
- Consecutive-frame confirmation before committing a line as "on"
- L1 → L2 sequence must complete within `sequence_timeout`
- Per-frame CSV logging to `data/logs/line_brightness_areaN.csv`

**`AreaConfig`** dataclass:
```python
name: str
order: int                    # display/sort order
camera_rtsp: str
roi: ROI                      # masking rectangle (full-frame coords)
l1: LineSeg                   # entry line
l2: LineSeg                   # exit line
yaml_idx: int                 # original position in counting_areas.areas[] (pre-sort)
use_bg_subtraction: bool      # use EMA background subtraction instead of absolute threshold
bg_delta: int                 # brightness above baseline required to trigger (default 30)
dwell_spike_factor: float     # re-arm threshold: spike > peak * (1+factor) restarts dwell (default 0.3)
```

**`AreaDetector`** — wraps `TwoLineDetector` + `AreaConfig`:
- `update(frame, timestamp)`: applies ROI mask then calls `det.update()`

**`QuorumReconciler`**:
```python
counts: List[int]             # per-area running totals
piece_count: int              # confirmed pieces (quorum-based)
on_area_triggered(idx, ts)    # → (confirmed_piece, diverged)
piece_confirmed()             # True once per upward move of piece_count
pending_area_count()          # distinct areas fired in current open window
reset()
status_text()                 # "pieces=N  [A1:n  A2:n ...]  window=k/Q"
```

A piece is confirmed when `≥ quorum` distinct areas fire within `piece_window_seconds`.
Near-simultaneous triggers (`< min_inter_area_gap_seconds` apart) are rejected as false
positives — typically a person walking through two adjacent detection zones on CAM-2.

**`StreamManager`** — one `cv2.VideoCapture` per unique RTSP URL; handles
reconnection and frame buffering.

**`ROI`** / **`LineSeg`** — draggable geometry objects with `handles()` /
`move_handle()` / `draw()` methods used by the calibration UI.

**`DragManager`** — mouse event handler for dragging `ROI` / `LineSeg` handles in
display mode.

---

### `src/mill_stand_line_counter.py` — Legacy Voting Counter (CAM-2)

Core detection logic for the older multi-view voting counter. Still used by
`run_mill_stand_multi.py`. Not used by `run_mill_counter.py`.

**`Stand`** — single view entry/exit line detector (emits `StandDetection`)
**`VotingWindow`** — cross-view majority voting (emits `PieceCount`)

---

### `src/mill_stand_multi_view_counter.py` — `MultiViewLineCounter`, `ViewState`

Orchestrates multiple RTSP views for the mill stand counter.

**`ViewState`** — per-view state container:
- Stores ROI box, original resolution, target resolution, `Stand` instance
- Applies ROI crop before resize; scales line coordinates automatically
- Initialized lazily on first frame

**`MultiViewLineCounter`**:
- Accepts `views_config` (list of view dicts from `settings.yaml`)
- Manages one `ViewState` per view, one shared `VotingWindow` queue
- `process_frames(frames)` → `(PieceCount | None, status_dict, resized_frames)`
- `draw_combined_overlay(overlays, status)` → side-by-side annotated frame

---

### `src/mill_stand_counter.py` — `MillStandCounter`

Zone-based bi-directional counter — used for offline video analysis and tuning. Not used in live RTSP deployment.

- Two rotated rectangular zones: LEFT (exit/downstream) and RIGHT (entry/upstream)
- Peak detection in each zone (pixel count exceeds threshold)
- RIGHT peak → AWAITING_LEFT → LEFT peak within timeout = 1 piece counted
- Supports both L→R and R→L directions

---

### `src/cooling_bed_counter.py` — `CoolingBedCounter`

HSV blob-based detection for the cooling bed. Standalone, not integrated into the main pipeline.

- White-hot metal filter: brightness > threshold AND saturation < threshold
- Rising-edge count: counts when blob appears, not when it disappears
- Used for a third camera position (channel 3 in NVR)

---

### `src/session_manager.py` — `SessionManager`, `Session`

Tracks RUN/BREAK production sessions for both counters.

**Session types:**
- `RUN` — mill is actively producing (pieces being counted)
- `BREAK` — mill is idle (no pieces for `break_threshold_seconds`, default 300s)

**Key methods:**
```python
on_piece_counted(travel_time)  → dict   # Notify of new piece; handles RUN start
check_for_break()              → dict   # Call periodically; triggers BREAK if idle
check_daily_reset()            → bool   # True at midnight; resets daily state
restore_session(last_session)  → bool   # Crash recovery from Firebase
shutdown()                     → Session  # Gracefully end active session
get_daily_totals()             → dict   # run_minutes, break_minutes, counts
```

**Return dicts** from `on_piece_counted` and `check_for_break` contain:
- `session_to_end` — Session to finalize in Firebase (or `None`)
- `session_to_create` — New Session to write to Firebase (or `None`)
- `session_to_update` — Existing RUN Session with updated count (or `None`)
- `run_minutes_since_last` — Minutes of run time to credit to this count

---

### `src/firebase_client.py` — `FirebaseClient`

All Firestore read/write operations. Singleton via `get_firebase_client()`.

| Method | Firestore writes |
|--------|-----------------|
| `create_session(session)` | `sessions/{id}` |
| `update_session(session)` | `sessions/{id}.count` |
| `push_mill_count(count_data, session_info)` | `daily/` (camera='CAM-2'), `hourly/`, `live/mill_stand` |
| `update_mill_status(status, session_info)` | `live/mill_stand` |
| `get_mill_today_count()` | read `daily/{today}_cam2.count` |
| `end_mill_session(session)` | `sessions/{id}` end fields + `hourly/` + `daily/` |
| `get_last_session()` | read most recent `sessions/` doc |

*Note: mill stand counter does **not** write piece-level documents to `counts/`. Only session analytics and daily/hourly aggregates are pushed to Firestore.*

---

### `src/detector.py` — `HotStockDetector` (legacy)

Original luminosity + motion detector for RUNNING/BREAK state. Superseded by `SessionManager` for all production use. Kept for reference.

### `src/state_machine.py` — `ProductionStateMachine` (legacy)

Original RUNNING/BREAK/UNKNOWN state machine. Superseded by `SessionManager`. Kept for reference.

---

## Scripts Reference

### Production Scripts

| Script | Camera | Firebase | Purpose |
|--------|--------|----------|---------|
| `run_mill_counter.py` | CAM-2 | Yes | Mill stand counter — production entry point |
| `run_mill_stand_multi.py` | CAM-2 | No | Legacy multi-view voting counter (no Firebase) |

### Calibration Scripts

| Script | Purpose |
|--------|---------|
| `calibrate_mill_stand_master.py` | Interactive ROI + line calibrator for CAM-2 multi-view |
| `calibrate_mill_stand.py` | Zone calibrator for offline zone-based analysis |
| `run_mill_stand_compare_cam2.py` | Side-by-side Peak vs 2-Line comparison on CAM-2 with mouse drag UI |

### Utility Scripts

| Script | Purpose |
|--------|---------|
| `test_firebase.py` | Verify Firebase connection and read today's count |
| `photo_server.py` | HTTP API to serve count photos for dashboard viewing |

---

## Data Flow — Session Lifecycle

```
System start
    │
    ▼
restore_session() ── Firebase ──▶ last session end=null? → continue as RUN
    │                               else → start fresh
    ▼
Piece counted
    │
    ├── Currently BREAK/NONE?
    │       └── Create new RUN session in Firebase
    │           End previous BREAK session
    │
    └── Update RUN session count in Firebase
        Track run_minutes_since_last

No piece for break_threshold (300s)
    │
    ├── End current RUN session in Firebase
    └── Create new BREAK session in Firebase

Midnight
    │
    └── counter.total_count = 0

System shutdown
    └── end_mill_session() for active session in Firebase
        update_mill_status('OFFLINE')
```

---

## Firestore Schema Summary

```
live/
└── mill_stand       ← CAM-2 real-time status

daily/{YYYY-MM-DD_cam2}   ← CAM-2 daily totals

hourly/{YYYY-MM-DD_cam2}/hours/{HH}  ← hourly breakdown

sessions/{id}        ← RUN/BREAK sessions (camera: 'CAM-2')
```

---

## Configuration File

`config/settings.yaml` — single YAML file for all settings. Sections:

| Section | Used by |
|---------|---------|
| `counting` | `PlateCounter` thresholds (legacy reference) |
| `detection` | `break_threshold_seconds` used by `SessionManager` |
| `counting_areas` | `run_mill_counter.py` — area configs for CAM-2 (3 areas, channel 2) and CAM-3 (1 area, channel 3): ROI, L1, L2, quorum settings, `use_bg_subtraction`, `bg_delta`, `dwell_spike_factor` |
| `mill_stand` | `MillStandCounter` zone coordinates (offline use) |
| `mill_stand_lines` | `MultiViewLineCounter` — legacy views, ROIs, lines, voting config |

See [Configuration Guide](CONFIGURATION.md) for the complete reference.

---

## Performance

| Counter | Resolution | FPS | CPU (Pi 5) |
|---------|-----------|-----|-----------|
| CAM-1 furnace | 704×576 sub-stream | ~20 FPS | Low |
| CAM-2 mill (3 views) | 704×576 per view | ~20 FPS | Moderate |

- Use sub-stream (`subtype=1`) — sufficient quality, lower bandwidth
- `CAP_PROP_BUFFERSIZE=1` minimizes latency
- No frame history kept in memory; photos written to disk immediately

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `opencv-python-headless` | Video capture, image processing |
| `numpy` | Array operations, line mask generation |
| `pyyaml` | Configuration file parsing |
| `firebase-admin` | Firestore read/write via service account |
| `zoneinfo` (stdlib) | Asia/Kolkata timezone (IST) |

---

## Related Documentation

- [Configuration](CONFIGURATION.md)
- [Calibration](CALIBRATION.md)
- [Mill Stand Counter](MILL_STAND.md)
- [Firebase Integration](FIREBASE.md)
- [Deployment](DEPLOYMENT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
