#!/usr/bin/env python3
"""
Mill Stand - Peak vs 2-Line Comparison (Camera 2)
==================================================
Side-by-side live comparison of two counting methods on the same RTSP stream.

  LEFT PANEL  - Method A: ROI Peak Detection
                A single ROI box. Count bright pixels per frame.
                When pixels rise above threshold and fall back = peak = 1 piece.

  RIGHT PANEL - Method B: 2-Line Sequential Detection
                Two lines (L1 entry, L2 exit). Piece must cross L1 then L2
                within a timeout window to count as 1 piece.

Both panels show the same live frame with overlays.
Drag ROI corners and line endpoints with the mouse to calibrate in real time.
Press S to save positions to settings.yaml (mill_stand_lines.views[1] = View 2).

Controls:
  Q / ESC    - Quit
  Space      - Pause / resume
  R          - Reset both counts
  S          - Save ROI + line positions to config/settings.yaml
  H          - Print help to terminal

Mouse (on the COMBINED window):
  Left-click + drag near a handle point to move it.
  Handles:  ROI (4 corners), Line1 (2 endpoints), Line2 (2 endpoints)

Usage:
  python scripts/run_mill_stand_compare_cam2.py
  python scripts/run_mill_stand_compare_cam2.py --channel 2
  python scripts/run_mill_stand_compare_cam2.py --brightness-threshold 160
  python scripts/run_mill_stand_compare_cam2.py --min-peak-pixels 500
  python scripts/run_mill_stand_compare_cam2.py --min-peak-duration 0.2
  python scripts/run_mill_stand_compare_cam2.py --min-travel-time 0.3
  python scripts/run_mill_stand_compare_cam2.py --sequence-timeout 4.0
"""

import csv
import cv2
import numpy as np
import yaml
import time
import sys
import re
import argparse
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("compare")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.error(f"Config not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    logger.info(f"Config saved to {CONFIG_PATH}")

def build_rtsp_url(config: dict, channel: int) -> str:
    primary_url = config.get("camera", {}).get("rtsp_url", "")
    if "channel=" in primary_url:
        url = re.sub(r"channel=\d+", f"channel={channel}", primary_url)
        url = re.sub(r"subtype=\d+", "subtype=1", url)
        return url
    return (
        f"rtsp://admin:bhoothnath123@192.168.1.200:554"
        f"/cam/realmonitor?channel={channel}&subtype=1"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PANEL_W = 704
PANEL_H = 576
GRAPH_H = 80        # height of brightness waveform at bottom of left panel
GRAPH_HISTORY = PANEL_W  # one pixel per frame

HANDLE_RADIUS = 8   # px - click target for draggable handles
RECONNECT_DELAY = 5
RECONNECT_MAX = 10

# Colors
COL_ROI     = (0, 220, 220)   # cyan
COL_LINE1   = (0, 255, 0)     # green
COL_LINE2   = (0, 60, 255)    # red
COL_PEAK    = (0, 200, 255)   # orange-ish when active
COL_COUNT   = (0, 255, 255)   # yellow flash on count
COL_GRAPH   = (0, 180, 255)   # graph bars
COL_THRESH  = (80, 80, 255)   # threshold line on graph

# ---------------------------------------------------------------------------
# Peak Detector (Method A)
# ---------------------------------------------------------------------------
@dataclass
class PeakState:
    in_peak: bool = False
    peak_start: float = 0.0
    peak_max_px: int = 0
    count: int = 0
    just_counted: bool = False   # True for one frame after a count

class PeakDetector:
    """
    Stateful ROI peak detector.
    Each time bright_pixel_count crosses above threshold and comes back down
    (and duration >= min_peak_duration) it counts +1 piece.
    """
    def __init__(
        self,
        min_peak_pixels: int = 500,
        min_peak_duration: float = 0.2,
        brightness_threshold: int = 160,
        saturation_threshold: int = 120,
    ):
        self.min_peak_pixels = min_peak_pixels
        self.min_peak_duration = min_peak_duration
        self.brightness_threshold = brightness_threshold
        self.saturation_threshold = saturation_threshold

        self.state = PeakState()
        self.pixel_history: deque = deque(maxlen=GRAPH_HISTORY)

    def analyze_roi(self, frame_bgr: np.ndarray, roi: "ROI") -> Tuple[int, float]:
        """Return (bright_pixel_count, avg_brightness) inside the ROI."""
        x1, y1, x2, y2 = roi.x1, roi.y1, roi.x2, roi.y2
        x1 = max(0, min(x1, frame_bgr.shape[1]-1))
        x2 = max(0, min(x2, frame_bgr.shape[1]-1))
        y1 = max(0, min(y1, frame_bgr.shape[0]-1))
        y2 = max(0, min(y2, frame_bgr.shape[0]-1))
        if x2 <= x1 or y2 <= y1:
            return 0, 0.0

        crop = frame_bgr[y1:y2, x1:x2]
        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        hsv_crop  = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        bright_mask = (
            (gray_crop > self.brightness_threshold) &
            (hsv_crop[:, :, 1] < self.saturation_threshold)
        )
        n = int(np.sum(bright_mask))
        avg = float(np.mean(gray_crop[bright_mask])) if n > 0 else 0.0
        return n, avg

    def update(self, frame_bgr: np.ndarray, roi: "ROI", timestamp: float) -> bool:
        """
        Update detector with a new frame.
        Returns True if a piece was just counted this frame.
        """
        px_count, _ = self.analyze_roi(frame_bgr, roi)
        self.pixel_history.append(px_count)
        self.state.just_counted = False

        above = px_count >= self.min_peak_pixels

        if not self.state.in_peak:
            if above:
                self.state.in_peak = True
                self.state.peak_start = timestamp
                self.state.peak_max_px = px_count
        else:
            if above:
                self.state.peak_max_px = max(self.state.peak_max_px, px_count)
            else:
                # Peak ended
                duration = timestamp - self.state.peak_start
                if duration >= self.min_peak_duration:
                    self.state.count += 1
                    self.state.just_counted = True
                    logger.info(
                        f"[PEAK] Piece #{self.state.count} | "
                        f"dur={duration:.2f}s  max_px={self.state.peak_max_px}"
                    )
                self.state.in_peak = False
                self.state.peak_max_px = 0

        return self.state.just_counted

    def reset(self):
        self.state = PeakState()
        self.pixel_history.clear()

# ---------------------------------------------------------------------------
# 2-Line Detector (Method B)
# ---------------------------------------------------------------------------
@dataclass
class LineState:
    # Line 1 (entry)
    l1_consec: int = 0
    l1_confirmed: bool = False
    l1_time: float = 0.0
    # Line 2 (exit)
    l2_consec: int = 0
    l2_confirmed: bool = False
    # Sequence
    pending_entry_time: Optional[float] = None
    count: int = 0
    just_counted: bool = False
    pending: bool = False

class TwoLineDetector:
    """
    Piece detected when it crosses Line1 then Line2 within sequence_timeout.
    Each line needs min_consecutive_frames to confirm.

    max_dwell_time: if L1 or L2 stays continuously triggered longer than this,
                    the activation is ignored (human / debris walking through).
    csv_path:       if set, logs per-frame brightness data to a CSV file.
    """
    def __init__(
        self,
        brightness_threshold: int = 160,
        min_bright_pixels: int = 30,
        min_consecutive_frames: int = 2,
        min_travel_time: float = 0.1,
        sequence_timeout: float = 4.0,
        line_thickness: int = 6,
        debounce: float = 0.3,
        max_dwell_time: float = 2.0,
        csv_path: Optional[Path] = None,
    ):
        self.brightness_threshold = brightness_threshold
        self.min_bright_pixels = min_bright_pixels
        self.min_consecutive_frames = min_consecutive_frames
        self.min_travel_time = min_travel_time
        self.sequence_timeout = sequence_timeout
        self.line_thickness = line_thickness
        self.debounce = debounce
        self.max_dwell_time = max_dwell_time

        self.state = LineState()
        # Per-line masks (rebuilt if frame shape changes)
        self._mask_shape: Optional[Tuple] = None
        self._l1_mask: Optional[np.ndarray] = None
        self._l2_mask: Optional[np.ndarray] = None
        self._last_l1: Optional[Tuple] = None
        self._last_l2: Optional[Tuple] = None

        # Dwell tracking — time when each line first became continuously triggered
        self._l1_dwell_start: Optional[float] = None
        self._l2_dwell_start: Optional[float] = None

        # CSV logging
        self._csv_file = None
        self._csv_writer = None
        if csv_path is not None:
            csv_path = Path(csv_path)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._csv_file = open(csv_path, "w", newline="")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "timestamp", "l1_bright_px", "l2_bright_px",
                "l1_triggered", "l2_triggered",
                "l1_confirmed", "l2_confirmed",
                "l1_dwell_s", "l2_dwell_s",
                "pending", "count", "event",
            ])
            logger.info(f"[LINE] Logging brightness data to {csv_path}")

    def _build_masks(self, shape, l1: "LineSeg", l2: "LineSeg"):
        if (self._mask_shape == shape and
                self._last_l1 == (l1.p1, l1.p2) and
                self._last_l2 == (l2.p1, l2.p2)):
            return
        self._mask_shape = shape
        self._last_l1 = (l1.p1, l1.p2)
        self._last_l2 = (l2.p1, l2.p2)
        h, w = shape[:2]
        self._l1_mask = np.zeros((h, w), np.uint8)
        self._l2_mask = np.zeros((h, w), np.uint8)
        cv2.line(self._l1_mask, l1.p1, l1.p2, 255, self.line_thickness)
        cv2.line(self._l2_mask, l2.p1, l2.p2, 255, self.line_thickness)

    def _check_line(self, gray: np.ndarray, mask: np.ndarray) -> Tuple[bool, int]:
        pixels = gray[mask > 0]
        if len(pixels) == 0:
            return False, 0
        bright = int(np.sum(pixels > self.brightness_threshold))
        return bright >= self.min_bright_pixels, bright

    def update(
        self,
        frame_bgr: np.ndarray,
        l1: "LineSeg",
        l2: "LineSeg",
        timestamp: float,
    ) -> bool:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        self._build_masks(gray.shape, l1, l2)

        l1_trig, l1_bright = self._check_line(gray, self._l1_mask)
        l2_trig, l2_bright = self._check_line(gray, self._l2_mask)

        self.state.just_counted = False
        event = ""

        # --- Max dwell-time gate ---
        if l1_trig:
            if self._l1_dwell_start is None:
                self._l1_dwell_start = timestamp
            elif timestamp - self._l1_dwell_start > self.max_dwell_time:
                l1_trig = False
                event = "L1_DWELL_SUPPRESSED"
        else:
            self._l1_dwell_start = None

        if l2_trig:
            if self._l2_dwell_start is None:
                self._l2_dwell_start = timestamp
            elif timestamp - self._l2_dwell_start > self.max_dwell_time:
                l2_trig = False
                event = "L2_DWELL_SUPPRESSED"
        else:
            self._l2_dwell_start = None

        # --- Line 1 consecutive tracking ---
        if l1_trig:
            self.state.l1_consec += 1
        else:
            if self.state.l1_consec > 0:
                self.state.l1_consec = 0
                self.state.l1_confirmed = False

        # Rising edge on L1
        l1_rising = (
            self.state.l1_consec >= self.min_consecutive_frames
            and not self.state.l1_confirmed
            and (timestamp - self.state.l1_time) > self.debounce
        )
        if l1_rising:
            self.state.l1_confirmed = True
            self.state.l1_time = timestamp
            self.state.pending_entry_time = timestamp
            self.state.pending = True
            self.state.l2_consec = 0
            self.state.l2_confirmed = False
            event = "L1_CONFIRMED"

        # --- Line 2 consecutive tracking ---
        if l2_trig:
            self.state.l2_consec += 1
        else:
            if self.state.l2_consec > 0:
                self.state.l2_consec = 0
                self.state.l2_confirmed = False

        # Rising edge on L2
        l2_rising = (
            self.state.l2_consec >= self.min_consecutive_frames
            and not self.state.l2_confirmed
            and self.state.pending_entry_time is not None
        )
        if l2_rising:
            self.state.l2_confirmed = True
            travel = timestamp - self.state.pending_entry_time
            if self.min_travel_time <= travel <= self.sequence_timeout:
                self.state.count += 1
                self.state.just_counted = True
                self.state.pending = False
                self.state.pending_entry_time = None
                event = "COUNTED"
                logger.info(
                    f"[LINE] Piece #{self.state.count} | travel={travel:.2f}s"
                )
            else:
                reason = "too fast" if travel < self.min_travel_time else "timeout"
                logger.debug(f"[LINE] Sequence rejected ({reason}) travel={travel:.2f}s")
                event = f"REJECTED_{reason.upper().replace(' ', '_')}"
                self.state.pending = False
                self.state.pending_entry_time = None

        # Expire stale pending
        if (self.state.pending_entry_time is not None and
                timestamp - self.state.pending_entry_time > self.sequence_timeout):
            self.state.pending = False
            self.state.pending_entry_time = None
            self.state.l1_confirmed = False
            event = "PENDING_EXPIRED"

        # --- CSV logging ---
        if self._csv_writer is not None:
            l1_dwell = (timestamp - self._l1_dwell_start) if self._l1_dwell_start else 0.0
            l2_dwell = (timestamp - self._l2_dwell_start) if self._l2_dwell_start else 0.0
            self._csv_writer.writerow([
                f"{timestamp:.4f}",
                l1_bright, l2_bright,
                int(l1_trig), int(l2_trig),
                int(self.state.l1_confirmed), int(self.state.l2_confirmed),
                f"{l1_dwell:.3f}", f"{l2_dwell:.3f}",
                int(self.state.pending),
                self.state.count,
                event,
            ])

        return self.state.just_counted

    def reset(self):
        self.state = LineState()
        self._mask_shape = None
        self._l1_mask = None
        self._l2_mask = None
        self._l1_dwell_start = None
        self._l2_dwell_start = None

    def close(self):
        """Flush and close the CSV log file if open."""
        if self._csv_file is not None:
            self._csv_file.flush()
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None

# ---------------------------------------------------------------------------
# Draggable geometry
# ---------------------------------------------------------------------------
class ROI:
    """Axis-aligned rectangle defined by two corners."""
    def __init__(self, x1: int, y1: int, x2: int, y2: int):
        self.x1 = x1; self.y1 = y1
        self.x2 = x2; self.y2 = y2

    def handles(self) -> List[Tuple[int, int]]:
        """4 corner handles: TL, TR, BR, BL"""
        return [
            (self.x1, self.y1),
            (self.x2, self.y1),
            (self.x2, self.y2),
            (self.x1, self.y2),
        ]

    def move_handle(self, idx: int, nx: int, ny: int):
        if idx == 0:   self.x1, self.y1 = nx, ny
        elif idx == 1: self.x2, self.y1 = nx, ny
        elif idx == 2: self.x2, self.y2 = nx, ny
        elif idx == 3: self.x1, self.y2 = nx, ny
        # Keep x1<x2, y1<y2
        if self.x1 > self.x2: self.x1, self.x2 = self.x2, self.x1
        if self.y1 > self.y2: self.y1, self.y2 = self.y2, self.y1

    def draw(self, frame: np.ndarray, active: bool = False, flash: bool = False):
        col = COL_PEAK if flash else COL_ROI
        thick = 3 if active or flash else 2
        cv2.rectangle(frame, (self.x1, self.y1), (self.x2, self.y2), col, thick)
        cv2.putText(frame, "ROI", (self.x1 + 4, self.y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        for h in self.handles():
            cv2.circle(frame, h, HANDLE_RADIUS, col, -1)


class LineSeg:
    """A line segment with two draggable endpoints."""
    def __init__(self, p1: Tuple[int, int], p2: Tuple[int, int], label: str, color):
        self.p1 = p1
        self.p2 = p2
        self.label = label
        self.color = color

    def handles(self) -> List[Tuple[int, int]]:
        return [self.p1, self.p2]

    def move_handle(self, idx: int, nx: int, ny: int):
        if idx == 0: self.p1 = (nx, ny)
        else:        self.p2 = (nx, ny)

    def draw(self, frame: np.ndarray, triggered: bool = False, flash: bool = False):
        col = COL_COUNT if flash else (
            tuple(min(255, c + 80) for c in self.color) if triggered else self.color
        )
        thick = 3 if triggered or flash else 2
        cv2.line(frame, self.p1, self.p2, col, thick)
        mid = ((self.p1[0]+self.p2[0])//2, (self.p1[1]+self.p2[1])//2)
        cv2.putText(frame, self.label, (mid[0]+4, mid[1]-4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        for h in self.handles():
            cv2.circle(frame, h, HANDLE_RADIUS, col, -1)


# ---------------------------------------------------------------------------
# Drag manager
# ---------------------------------------------------------------------------
class DragManager:
    """Tracks which handle is being dragged across both panels."""

    def __init__(self):
        self.active_obj = None   # (object, handle_idx)
        self.panel_offset_x = 0  # x offset of the panel being dragged in

    def find_handle(
        self,
        mx: int, my: int,
        objects: List,
        panel_x_offset: int,
    ) -> bool:
        """Try to start a drag. Returns True if a handle was found."""
        lx = mx - panel_x_offset   # local x within the panel
        for obj in objects:
            for i, (hx, hy) in enumerate(obj.handles()):
                if abs(lx - hx) <= HANDLE_RADIUS + 2 and abs(my - hy) <= HANDLE_RADIUS + 2:
                    self.active_obj = (obj, i)
                    self.panel_offset_x = panel_x_offset
                    return True
        return False

    def drag(self, mx: int, my: int):
        if self.active_obj is None:
            return
        obj, idx = self.active_obj
        lx = mx - self.panel_offset_x
        lx = max(0, min(lx, PANEL_W - 1))
        ly = max(0, min(my, PANEL_H - 1))
        obj.move_handle(idx, lx, ly)

    def release(self):
        self.active_obj = None


# ---------------------------------------------------------------------------
# Waveform graph drawer
# ---------------------------------------------------------------------------
def draw_waveform(
    canvas: np.ndarray,
    history: deque,
    threshold: int,
    in_peak: bool,
    y_offset: int,
    height: int,
    width: int,
):
    """Draw scrolling brightness waveform at the bottom of a panel."""
    # Background
    cv2.rectangle(canvas, (0, y_offset), (width, y_offset + height), (20, 20, 20), -1)
    cv2.line(canvas, (0, y_offset), (width, y_offset), (60, 60, 60), 1)

    if not history:
        return

    max_val = max(max(history), threshold * 2, 1)
    thresh_y = y_offset + height - int(threshold / max_val * height)
    cv2.line(canvas, (0, thresh_y), (width, thresh_y), COL_THRESH, 1)
    cv2.putText(canvas, f"thresh={threshold}", (4, thresh_y - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, COL_THRESH, 1)

    hist = list(history)
    bar_w = max(1, width // GRAPH_HISTORY)

    for i, val in enumerate(hist):
        bar_h = int(val / max_val * height)
        bx = int(i * width / GRAPH_HISTORY)
        col = COL_PEAK if in_peak else COL_GRAPH
        cv2.rectangle(
            canvas,
            (bx, y_offset + height - bar_h),
            (bx + bar_w, y_offset + height),
            col, -1
        )

    # Label
    label = f"px: {hist[-1] if hist else 0}"
    cv2.putText(canvas, label, (width - 80, y_offset + height - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)


# ---------------------------------------------------------------------------
# HUD panel drawers
# ---------------------------------------------------------------------------
def draw_panel_a_hud(panel: np.ndarray, detector: PeakDetector, flash: bool):
    h, w = panel.shape[:2]

    # Title bar
    cv2.rectangle(panel, (0, 0), (w, 28), (30, 30, 60), -1)
    cv2.putText(panel, "METHOD A: PEAK DETECTION", (6, 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 255), 1)

    # Status box top-left
    bx = 4
    cv2.rectangle(panel, (bx, 32), (bx + 181, 100), (0, 0, 0), -1)
    count_col = COL_COUNT if flash else (0, 255, 0)
    cv2.putText(panel, f"COUNT: {detector.state.count}", (bx + 6, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, count_col, 2)

    state_text = "PEAK ACTIVE" if detector.state.in_peak else "waiting..."
    state_col  = (0, 200, 255) if detector.state.in_peak else (120, 120, 120)
    cv2.putText(panel, state_text, (bx + 6, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, state_col, 1)

    px_now = list(detector.pixel_history)[-1] if detector.pixel_history else 0
    cv2.putText(panel, f"px={px_now}  thr={detector.min_peak_pixels}",
                (bx + 6, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (160, 160, 160), 1)

    # Flash banner
    if flash:
        cv2.putText(panel, "*** PIECE COUNTED ***",
                    (w // 2 - 110, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, COL_COUNT, 3)


def draw_panel_b_hud(panel: np.ndarray, detector: TwoLineDetector, flash: bool):
    h, w = panel.shape[:2]

    # Title bar
    cv2.rectangle(panel, (0, 0), (w, 28), (30, 60, 30), -1)
    cv2.putText(panel, "METHOD B: 2-LINE DETECTION", (6, 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 255, 200), 1)

    # Status box top-left
    bx = 4
    cv2.rectangle(panel, (bx, 32), (bx + 181, 115), (0, 0, 0), -1)
    count_col = COL_COUNT if flash else (0, 255, 0)
    cv2.putText(panel, f"COUNT: {detector.state.count}", (bx + 6, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, count_col, 2)

    pending_col = (0, 200, 255) if detector.state.pending else (120, 120, 120)
    pending_txt = "L1 CONFIRMED" if detector.state.pending else "waiting L1..."
    if detector.state.l2_confirmed:
        pending_txt = "L2 CONFIRMED"
    cv2.putText(panel, pending_txt, (bx + 6, 78),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, pending_col, 1)

    l1_col = (0, 255, 0)   if detector.state.l1_confirmed else (80, 80, 80)
    l2_col = (0, 100, 255) if detector.state.l2_confirmed else (80, 80, 80)
    cv2.putText(panel, f"L1: {'ON' if detector.state.l1_confirmed else 'off'}",
                (bx + 6, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.38, l1_col, 1)
    cv2.putText(panel, f"L2: {'ON' if detector.state.l2_confirmed else 'off'}",
                (bx + 70, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.38, l2_col, 1)
    cv2.putText(panel,
                f"thr={detector.brightness_threshold}  "
                f"min_px={detector.min_bright_pixels}",
                (bx + 6, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (120, 120, 120), 1)

    # Flash banner
    if flash:
        cv2.putText(panel, "*** PIECE COUNTED ***",
                    (w // 2 - 110, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, COL_COUNT, 3)


# ---------------------------------------------------------------------------
# Save positions to settings.yaml  (View 2 = views[1])
# ---------------------------------------------------------------------------
def save_positions(roi: ROI, l1: LineSeg, l2: LineSeg):
    config = load_config()

    views = config.get("mill_stand_lines", {}).get("views", [])
    # Ensure at least 2 views exist
    while len(views) < 2:
        views.append({})

    # View index 1 = View 2 = camera 2
    v = views[1]
    v["roi"] = {
        "start": [roi.x1, roi.y1],
        "end":   [roi.x2, roi.y2],
    }
    v["line1"] = {
        "start": list(l1.p1),
        "end":   list(l1.p2),
    }
    v["line2"] = {
        "start": list(l2.p1),
        "end":   list(l2.p2),
    }

    config["mill_stand_lines"]["views"] = views

    # Save peak ROI under a camera-2-specific key to avoid clobbering cam3
    if "mill_stand" not in config:
        config["mill_stand"] = {}
    config["mill_stand"]["peak_roi_cam2"] = {
        "x1": roi.x1, "y1": roi.y1, "x2": roi.x2, "y2": roi.y2,
    }

    save_config(config)
    logger.info(
        f"Saved: ROI=({roi.x1},{roi.y1})-({roi.x2},{roi.y2})  "
        f"L1={l1.p1}-{l1.p2}  L2={l2.p1}-{l2.p2}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def print_help():
    print("""
Mill Stand Compare (Camera 2) - Controls
-----------------------------------------
  Q / ESC      Quit
  Space        Pause / resume
  R            Reset both counts
  S            Save ROI + line positions to settings.yaml (views[1])
  H            This help

Mouse:
  Click + drag handles (filled circles) to move ROI corners and line endpoints.
  Handles are active in BOTH panels (left = panel A, right = panel B).
""")


def run(args):
    config = load_config()

    # --- Build RTSP URL ---
    rtsp_url = args.rtsp or build_rtsp_url(config, args.channel)
    logger.info(f"RTSP: {rtsp_url}")

    # --- Load saved positions from settings.yaml (View 2 = views[1]) ---
    views = config.get("mill_stand_lines", {}).get("views", [])
    v2 = views[1] if len(views) >= 2 else {}

    # ROI: prefer dedicated cam2 peak_roi key, then fall back to View 2 roi
    saved_roi = config.get("mill_stand", {}).get("peak_roi_cam2", None)
    if saved_roi:
        roi = ROI(saved_roi["x1"], saved_roi["y1"], saved_roi["x2"], saved_roi["y2"])
    elif v2.get("roi"):
        r = v2["roi"]
        roi = ROI(r["start"][0], r["start"][1], r["end"][0], r["end"][1])
    else:
        roi = ROI(
            PANEL_W // 4, PANEL_H // 4,
            3 * PANEL_W // 4, 3 * PANEL_H // 4,
        )

    # Line 1
    if v2.get("line1"):
        lc = v2["line1"]
        l1 = LineSeg(tuple(lc["start"]), tuple(lc["end"]), "L1", COL_LINE1)
    else:
        lx = roi.x1 + (roi.x2 - roi.x1) // 3
        l1 = LineSeg((lx, roi.y1), (lx, roi.y2), "L1", COL_LINE1)

    # Line 2
    if v2.get("line2"):
        lc = v2["line2"]
        l2 = LineSeg(tuple(lc["start"]), tuple(lc["end"]), "L2", COL_LINE2)
    else:
        lx = roi.x1 + 2 * (roi.x2 - roi.x1) // 3
        l2 = LineSeg((lx, roi.y1), (lx, roi.y2), "L2", COL_LINE2)

    # --- Detectors ---
    peak_det = PeakDetector(
        min_peak_pixels=args.min_peak_pixels,
        min_peak_duration=args.min_peak_duration,
        brightness_threshold=args.brightness_threshold,
        saturation_threshold=args.saturation_threshold,
    )
    line_det = TwoLineDetector(
        brightness_threshold=args.brightness_threshold,
        min_bright_pixels=args.min_line_pixels,
        min_consecutive_frames=args.min_consecutive_frames,
        min_travel_time=args.min_travel_time,
        sequence_timeout=args.sequence_timeout,
        line_thickness=8,
        max_dwell_time=args.max_dwell_time,
        csv_path=PROJECT_ROOT / "logs" / "line_brightness_cam2.csv",
    )

    # --- Drag manager ---
    drag = DragManager()

    # --- Flash timers ---
    flash_a_until = 0.0
    flash_b_until = 0.0
    FLASH_DUR = 0.4  # seconds

    # --- Window ---
    WIN = "Mill Stand Compare - Camera 2  |  A: Peak  |  B: 2-Line"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    win_w = PANEL_W * 2
    win_h = PANEL_H
    cv2.resizeWindow(WIN, win_w, win_h)

    # Mouse callback
    def on_mouse(event, mx, my, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if mx < PANEL_W:
                # Panel A — only ROI handles
                drag.find_handle(mx, my, [roi], 0)
            else:
                # Panel B — ROI + line handles
                drag.find_handle(mx, my, [roi, l1, l2], PANEL_W)
        elif event == cv2.EVENT_MOUSEMOVE and (flags & cv2.EVENT_FLAG_LBUTTON):
            drag.drag(mx, my)
        elif event == cv2.EVENT_LBUTTONUP:
            drag.release()

    cv2.setMouseCallback(WIN, on_mouse)

    # --- Stream ---
    cap = None
    fail_count = 0
    paused = False

    logger.info(f"Window: {WIN}")
    logger.info("Press H for help.")
    print_help()

    try:
        while True:
            now = time.time()

            # --- Reconnect ---
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                if RECONNECT_MAX and fail_count >= RECONNECT_MAX:
                    logger.error("Max reconnect attempts reached. Exiting.")
                    break
                if fail_count > 0:
                    logger.info(f"Reconnecting (attempt {fail_count})...")
                    time.sleep(RECONNECT_DELAY)
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if cap.isOpened():
                    fail_count = 0
                    logger.info("Stream connected.")
                else:
                    fail_count += 1
                    continue

            # --- Pause ---
            if paused:
                key = cv2.waitKey(100) & 0xFF
                if key in (ord('q'), 27):
                    break
                if key == ord(' '):
                    paused = False
                    logger.info("Resumed.")
                continue

            # --- Read frame ---
            ret, raw = cap.read()
            if not ret or raw is None:
                logger.warning("Frame read failed.")
                cap.release()
                cap = None
                fail_count += 1
                continue

            fail_count = 0
            # Resize to our working resolution
            frame = cv2.resize(raw, (PANEL_W, PANEL_H), interpolation=cv2.INTER_AREA)

            # --- Run detectors ---
            counted_a = peak_det.update(frame, roi, now)
            counted_b = line_det.update(frame, l1, l2, now)

            if counted_a:
                flash_a_until = now + FLASH_DUR
            if counted_b:
                flash_b_until = now + FLASH_DUR

            flash_a = now < flash_a_until
            flash_b = now < flash_b_until

            # --- Build Panel A ---
            panel_a = frame.copy()
            roi.draw(panel_a, active=drag.active_obj is not None and drag.active_obj[0] is roi,
                     flash=flash_a)
            graph_y = PANEL_H - GRAPH_H
            draw_waveform(
                panel_a,
                peak_det.pixel_history,
                peak_det.min_peak_pixels,
                peak_det.state.in_peak,
                graph_y, GRAPH_H, PANEL_W,
            )
            draw_panel_a_hud(panel_a, peak_det, flash_a)

            # --- Build Panel B ---
            panel_b = frame.copy()
            roi.draw(panel_b, flash=flash_b)
            l1_trig = line_det.state.l1_confirmed
            l2_trig = line_det.state.l2_confirmed
            l1.draw(panel_b, triggered=l1_trig, flash=flash_b and l2_trig)
            l2.draw(panel_b, triggered=l2_trig, flash=flash_b)
            draw_panel_b_hud(panel_b, line_det, flash_b)

            # --- Combine side by side ---
            combined = np.hstack([panel_a, panel_b])
            cv2.line(combined, (PANEL_W, 0), (PANEL_W, PANEL_H), (80, 80, 80), 2)
            cv2.imshow(WIN, combined)

            # --- Keys ---
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            elif key == ord(' '):
                paused = True
                logger.info("Paused.")
            elif key == ord('r'):
                peak_det.reset()
                line_det.reset()
                logger.info("Counts reset.")
            elif key == ord('s'):
                save_positions(roi, l1, l2)
            elif key == ord('h'):
                print_help()

    except KeyboardInterrupt:
        logger.info("Interrupted.")

    finally:
        if cap is not None:
            cap.release()
        line_det.close()
        cv2.destroyAllWindows()

        print()
        print("=" * 50)
        print("SESSION SUMMARY")
        print("=" * 50)
        print(f"  Peak detection count  : {peak_det.state.count}")
        print(f"  2-Line detection count: {line_det.state.count}")
        print("=" * 50)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(
        description="Side-by-side Peak vs 2-Line mill stand counter (Camera 2)"
    )
    p.add_argument("--channel",         type=int,   default=2,
                   help="NVR channel number (default: 2)")
    p.add_argument("--rtsp",            type=str,   default=None,
                   help="Override full RTSP URL")
    p.add_argument("--brightness-threshold", type=int, default=160,
                   help="Min brightness for white-hot pixel (default: 160)")
    p.add_argument("--saturation-threshold", type=int, default=120,
                   help="Max HSV saturation for white-hot filter (default: 120)")
    p.add_argument("--min-peak-pixels", type=int,   default=500,
                   help="[Peak] Min bright pixels in ROI to start a peak (default: 500)")
    p.add_argument("--min-peak-duration", type=float, default=0.2,
                   help="[Peak] Min peak duration in seconds (default: 0.2)")
    p.add_argument("--min-line-pixels", type=int,   default=30,
                   help="[Line] Min bright pixels on a line to trigger (default: 30)")
    p.add_argument("--min-consecutive-frames", type=int, default=2,
                   help="[Line] Consecutive frames to confirm a line trigger (default: 2)")
    p.add_argument("--min-travel-time", type=float, default=0.1,
                   help="[Line] Min L1->L2 travel time in seconds (default: 0.1)")
    p.add_argument("--sequence-timeout", type=float, default=4.0,
                   help="[Line] Max L1->L2 wait time in seconds (default: 4.0)")
    p.add_argument("--max-dwell-time", type=float, default=2.0,
                   help="[Line] Max continuous trigger time before suppression (default: 2.0)")
    args = p.parse_args()

    run(args)


if __name__ == "__main__":
    main()
