#!/usr/bin/env python3
"""
AIS Mill Stand Counter - Multi-Area Quorum Counting (Firebase-enabled)
=======================================================================
Counts hot steel pieces at the mill stand using multiple independent 2-line
detection areas.  Currently configured areas span CAM-2 (Channel 2, 3 areas)
and CAM-3 (Channel 3, 1 area) — all counting the same pieces from different
angles for redundancy.  Area configurations (RTSP URL, ROI, L1, L2) are
loaded from counting_areas in config/settings.yaml.

Each area runs its own independent counter (L1 → L2).  After every area
detection a QuorumReconciler confirms a piece when at least `quorum` distinct
areas fire within a `piece_window_seconds` sliding window.  Near-simultaneous
triggers (< `min_inter_area_gap_seconds` apart) are rejected as false positives
(e.g. a person walking through two adjacent detection zones on the same camera).

Missed counts when a piece is already occupying a line (dwell suppression) are
recovered via brightness spike re-arm: if the bright-pixel count surges 30%+
above the running peak during dwell, the dwell timer resets and a new L1/L2
rising edge can fire again for the new piece.

Features:
- Multi-area independent 2-line detection (L1 → L2 per area)
- Quorum reconciler: 2-of-N areas must confirm within 5 s window
- Near-simultaneous trigger rejection (< 1.5 s gap = false positive)
- Dwell-spike re-arm for missed counts when piece overlaps a dwelled line
- Divergence warning when max(areas) - min(areas) > threshold
- One cv2.VideoCapture per unique RTSP URL (shared across areas on same camera)
- One cv2.namedWindow per unique camera in display mode
- Tab / number keys cycle which area is focused within a camera window
- S saves focused area; R resets all; H help
- Firebase sync: session analytics, daily/hourly counts, live status
- Auto-resets at midnight, auto-reconnects on stream failure

Usage:
    python run_mill_counter.py              # Run continuously
    python run_mill_counter.py --duration 60
    python run_mill_counter.py --test
    python run_mill_counter.py --no-firebase
    python run_mill_counter.py --display
    python run_mill_counter.py --brightness-threshold 180
    python run_mill_counter.py --min-line-pixels 30
    python run_mill_counter.py --sequence-timeout 4.0
"""

import csv
import cv2
import numpy as np
import yaml
import time
import sys
import argparse
import logging
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


def sd_notify(msg: str) -> None:
    """Send a notification to systemd via the $NOTIFY_SOCKET (no-op if not running under systemd)."""
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return
    try:
        if notify_socket.startswith("@"):
            notify_socket = "\0" + notify_socket[1:]
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(msg.encode(), notify_socket)
        sock.close()
    except Exception:
        pass

IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from session_manager import SessionManager, Session, SessionType

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / 'data' / 'logs' / 'mill-counter.log'),
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PANEL_W = 704
PANEL_H = 576

RECONNECT_DELAY = 5
RECONNECT_MAX = 0   # 0 = retry forever (service mode)

# Colors
COL_LINE1  = (0, 255, 0)      # green
COL_LINE2  = (0, 60, 255)     # red-ish (BGR)
COL_ROI    = (0, 220, 220)    # cyan
COL_COUNT  = (0, 255, 255)    # yellow flash on count
COL_PEAK   = (0, 200, 255)    # ROI active state

# Per-area palette (cycles for up to 8 areas)
AREA_COLORS = [
    (0,   255,  0),    # green
    (0,   60,  255),   # red
    (255, 165,  0),    # orange (BGR order → blue=0, green=165, red=255)
    (255,  0,  255),   # magenta
    (0,   255, 255),   # yellow
    (255, 255,  0),    # cyan
    (128,  0,  128),   # purple
    (0,   128, 255),   # sky blue
]

HANDLE_RADIUS = 8
HANDLE_RADIUS_FOCUSED = 11
FLASH_DUR = 0.4

# ---------------------------------------------------------------------------
# Config helpers
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
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def load_env(env_path: Path):
    if not env_path.exists():
        return
    with open(env_path, 'r') as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            key, value = stripped.split('=', 1)
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


# ---------------------------------------------------------------------------
# Draggable geometry
# ---------------------------------------------------------------------------
class ROI:
    """Axis-aligned rectangle defined by two corners."""
    def __init__(self, x1: int, y1: int, x2: int, y2: int):
        self.x1 = x1; self.y1 = y1
        self.x2 = x2; self.y2 = y2

    def handles(self) -> List[Tuple[int, int]]:
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
        if self.x1 > self.x2: self.x1, self.x2 = self.x2, self.x1
        if self.y1 > self.y2: self.y1, self.y2 = self.y2, self.y1

    def draw(self, frame: np.ndarray, color, focused: bool = False):
        thick = 3 if focused else 2
        cv2.rectangle(frame, (self.x1, self.y1), (self.x2, self.y2), color, thick)
        cv2.putText(frame, "ROI", (self.x1 + 4, self.y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        r = HANDLE_RADIUS_FOCUSED if focused else HANDLE_RADIUS
        for h in self.handles():
            cv2.circle(frame, h, r, color, -1)


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

    def draw(self, frame: np.ndarray, triggered: bool = False,
             flash: bool = False, focused: bool = False):
        col = COL_COUNT if flash else (
            tuple(min(255, c + 80) for c in self.color) if triggered else self.color
        )
        thick = 3 if triggered or flash or focused else 2
        cv2.line(frame, self.p1, self.p2, col, thick)
        mid = ((self.p1[0] + self.p2[0]) // 2, (self.p1[1] + self.p2[1]) // 2)
        cv2.putText(frame, self.label, (mid[0] + 4, mid[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        r = HANDLE_RADIUS_FOCUSED if focused else HANDLE_RADIUS
        for h in self.handles():
            cv2.circle(frame, h, r, col, -1)


# ---------------------------------------------------------------------------
# Drag manager
# ---------------------------------------------------------------------------
class DragManager:
    def __init__(self):
        self.active_obj = None  # (object, handle_idx)

    def find_handle(self, mx: int, my: int, objects: List,
                    panel_x_offset: int = 0) -> bool:
        lx = mx - panel_x_offset
        for obj in objects:
            for i, (hx, hy) in enumerate(obj.handles()):
                if abs(lx - hx) <= HANDLE_RADIUS_FOCUSED + 2 and \
                   abs(my - hy) <= HANDLE_RADIUS_FOCUSED + 2:
                    self.active_obj = (obj, i)
                    return True
        return False

    def drag(self, mx: int, my: int, panel_x_offset: int = 0):
        if self.active_obj is None:
            return
        obj, idx = self.active_obj
        lx = mx - panel_x_offset
        lx = max(0, min(lx, PANEL_W - 1))
        ly = max(0, min(my, PANEL_H - 1))
        obj.move_handle(idx, lx, ly)

    def release(self):
        self.active_obj = None


# ---------------------------------------------------------------------------
# 2-Line Detector (LineState + TwoLineDetector)
# ---------------------------------------------------------------------------
@dataclass
class LineState:
    # Line 1
    l1_consec: int = 0
    l1_confirmed: bool = False
    l1_time: float = 0.0
    # Line 2
    l2_consec: int = 0
    l2_confirmed: bool = False
    # Sequence
    pending_entry_time: Optional[float] = None
    pending: bool = False
    just_counted: bool = False
    last_travel_time: float = 0.0
    count: int = 0


class TwoLineDetector:
    """
    Piece detected when it crosses L1 → L2 within sequence_timeout.
    Each line needs min_consecutive_frames to confirm.
    max_dwell_time: continuous trigger longer than this → suppressed (person/debris).
    csv_path: if set, logs per-frame brightness data.

    Background subtraction mode (use_bg_subtraction=True):
        Instead of triggering on pixels > brightness_threshold (absolute),
        triggers on pixels > rolling_baseline + bg_delta (relative).
        The per-line EMA baseline adapts slowly to ambient light (alpha=bg_alpha).
        Baseline is only updated when the line is NOT currently triggered, so a
        passing hot piece does not corrupt the reference level.
        Effective in bright sunlight where absolute thresholds saturate.
    """
    def __init__(
        self,
        brightness_threshold: int = 160,
        min_bright_pixels: int = 30,
        min_consecutive_frames: int = 2,
        sequence_timeout: float = 4.0,
        line_thickness: int = 8,
        debounce: float = 0.3,
        max_dwell_time: float = 2.0,
        dwell_spike_factor: float = 0.3,
        csv_path: Optional[Path] = None,
        use_bg_subtraction: bool = False,
        bg_delta: int = 30,
        bg_alpha: float = 0.05,
    ):
        self.brightness_threshold = brightness_threshold
        self.min_bright_pixels = min_bright_pixels
        self.min_consecutive_frames = min_consecutive_frames
        self.sequence_timeout = sequence_timeout
        self.line_thickness = line_thickness
        self.debounce = debounce
        self.max_dwell_time = max_dwell_time
        self.dwell_spike_factor = dwell_spike_factor
        self.use_bg_subtraction = use_bg_subtraction
        self.bg_delta = bg_delta
        self.bg_alpha = bg_alpha

        self.state = LineState()

        # Per-line masks (rebuilt on line/shape change)
        self._mask_shape: Optional[Tuple] = None
        self._l1_mask: Optional[np.ndarray] = None
        self._l2_mask: Optional[np.ndarray] = None
        self._last_l1: Optional[Tuple] = None
        self._last_l2: Optional[Tuple] = None

        # Dwell tracking
        self._l1_dwell_start: Optional[float] = None
        self._l2_dwell_start: Optional[float] = None
        # Peak bright-pixel count seen during each ongoing dwell period (for spike re-arm)
        self._l1_bright_peak: int = 0
        self._l2_bright_peak: int = 0

        # Background subtraction baselines (EMA, float32, per-pixel on mask)
        # Initialised lazily on first frame.
        self._l1_bg: Optional[np.ndarray] = None  # shape: (n_mask_pixels,)
        self._l2_bg: Optional[np.ndarray] = None

        # CSV logging
        self._csv_file = None
        self._csv_writer = None
        if csv_path is not None:
            csv_path = Path(csv_path)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._csv_file = open(csv_path, "w", newline="")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow([
                "timestamp",
                "l1_bright_px", "l2_bright_px",
                "l1_triggered", "l2_triggered",
                "l1_confirmed", "l2_confirmed",
                "l1_dwell_s", "l2_dwell_s",
                "pending", "count", "event",
            ])
            logger.info(f"Logging brightness data to {csv_path}")

    def _build_masks(self, shape, l1: LineSeg, l2: LineSeg):
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

    def _check_line(
        self,
        gray: np.ndarray,
        mask: np.ndarray,
        baseline: Optional[np.ndarray],
    ) -> Tuple[bool, int]:
        """
        Returns (triggered, bright_pixel_count).

        Normal mode:   triggered when pixels > brightness_threshold
        BG-sub mode:   triggered when pixels > baseline + bg_delta
                       baseline is a per-pixel float32 EMA array (same length as mask pixels).
        """
        pixels = gray[mask > 0]
        if len(pixels) == 0:
            return False, 0
        if self.use_bg_subtraction and baseline is not None and baseline.shape == pixels.shape:
            bright = int(np.sum(pixels.astype(np.float32) > baseline + self.bg_delta))
        else:
            bright = int(np.sum(pixels > self.brightness_threshold))
        return bright >= self.min_bright_pixels, bright

    def _update_baseline(
        self,
        baseline: Optional[np.ndarray],
        gray: np.ndarray,
        mask: np.ndarray,
        triggered: bool,
    ) -> np.ndarray:
        """Update the EMA baseline for one line.  Only updates when NOT triggered
        so a passing piece does not raise the reference level.
        Re-seeds if the mask pixel count changed (e.g. line was moved during calibration)."""
        pixels = gray[mask > 0].astype(np.float32)
        if baseline is None or baseline.shape != pixels.shape:
            # First frame or line moved: seed with actual pixel values
            return pixels.copy()
        if not triggered:
            baseline += self.bg_alpha * (pixels - baseline)
        return baseline

    def update(self, frame_bgr: np.ndarray, l1: LineSeg, l2: LineSeg,
               timestamp: float) -> bool:
        """Process one frame. Returns True if a piece was counted."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        self._build_masks(gray.shape, l1, l2)

        l1_trig, l1_bright = self._check_line(gray, self._l1_mask, self._l1_bg)
        l2_trig, l2_bright = self._check_line(gray, self._l2_mask, self._l2_bg)

        # Update background baselines (only when not triggered to protect baseline)
        if self.use_bg_subtraction:
            self._l1_bg = self._update_baseline(self._l1_bg, gray, self._l1_mask, l1_trig)
            self._l2_bg = self._update_baseline(self._l2_bg, gray, self._l2_mask, l2_trig)

        self.state.just_counted = False
        event = ""

        # --- Dwell-time gate ---
        if l1_trig:
            if self._l1_dwell_start is None:
                self._l1_dwell_start = timestamp
                self._l1_bright_peak = l1_bright
            else:
                # Track peak while continuously triggered
                if l1_bright > self._l1_bright_peak:
                    self._l1_bright_peak = l1_bright
                if timestamp - self._l1_dwell_start > self.max_dwell_time:
                    # Spike re-arm: a new piece arrived while an old one is still
                    # holding the line.  If brightness jumps significantly above the
                    # peak seen so far, reset dwell and re-arm a fresh L1 crossing.
                    spike_threshold = self._l1_bright_peak * (1 + self.dwell_spike_factor)
                    if l1_bright > spike_threshold:
                        self._l1_dwell_start = timestamp
                        self._l1_bright_peak = l1_bright
                        # Re-arm: clear confirmed state so rising-edge fires again
                        self.state.l1_confirmed = False
                        event = "L1_DWELL_SPIKE_REARM"
                    else:
                        l1_trig = False
                        event = "L1_DWELL_SUPPRESSED"
        else:
            self._l1_dwell_start = None
            self._l1_bright_peak = 0

        if l2_trig:
            if self._l2_dwell_start is None:
                self._l2_dwell_start = timestamp
                self._l2_bright_peak = l2_bright
            else:
                if l2_bright > self._l2_bright_peak:
                    self._l2_bright_peak = l2_bright
                if timestamp - self._l2_dwell_start > self.max_dwell_time:
                    spike_threshold = self._l2_bright_peak * (1 + self.dwell_spike_factor)
                    if l2_bright > spike_threshold:
                        self._l2_dwell_start = timestamp
                        self._l2_bright_peak = l2_bright
                        self.state.l2_confirmed = False
                        event = "L2_DWELL_SPIKE_REARM"
                    else:
                        l2_trig = False
                        event = "L2_DWELL_SUPPRESSED"
        else:
            self._l2_dwell_start = None
            self._l2_bright_peak = 0

        # --- Line 1 consecutive tracking ---
        if l1_trig:
            self.state.l1_consec += 1
        else:
            if self.state.l1_consec > 0:
                self.state.l1_consec = 0
                self.state.l1_confirmed = False

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

        l2_rising = (
            self.state.l2_consec >= self.min_consecutive_frames
            and not self.state.l2_confirmed
            and self.state.pending_entry_time is not None
        )
        if l2_rising:
            self.state.l2_confirmed = True
            entry_time = self.state.pending_entry_time or timestamp
            travel = timestamp - entry_time
            if travel <= self.sequence_timeout:
                self.state.count += 1
                self.state.just_counted = True
                self.state.last_travel_time = travel
                self.state.pending = False
                self.state.pending_entry_time = None
                event = "COUNTED"
                logger.debug(
                    f"Area triggered | travel={travel:.2f}s"
                )
            else:
                logger.debug(f"Sequence rejected (timeout) travel={travel:.2f}s")
                event = "REJECTED_TIMEOUT"
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
        self._last_l1 = None
        self._last_l2 = None
        self._l1_dwell_start = None
        self._l2_dwell_start = None
        self._l1_bright_peak = 0
        self._l2_bright_peak = 0
        self._l1_bg = None
        self._l2_bg = None

    def close(self):
        if self._csv_file is not None:
            self._csv_file.flush()
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None


# ---------------------------------------------------------------------------
# AreaConfig dataclass
# ---------------------------------------------------------------------------
@dataclass
class AreaConfig:
    name: str
    order: int
    camera_rtsp: str
    roi: ROI
    l1: LineSeg
    l2: LineSeg
    yaml_idx: int = 0        # index into counting_areas.areas[] in settings.yaml (pre-sort)
    min_line_pixels: int = 30  # per-area brightness pixel threshold
    use_bg_subtraction: bool = False  # relative-brightness mode for bright-sun environments
    bg_delta: int = 30        # pixels must be this many units above EMA baseline to count
    dwell_spike_factor: float = 0.3   # re-arm threshold: spike must be > peak * (1 + factor)


# ---------------------------------------------------------------------------
# AreaDetector
# ---------------------------------------------------------------------------
class AreaDetector:
    """Wraps one TwoLineDetector + one AreaConfig."""

    def __init__(
        self,
        cfg: AreaConfig,
        brightness_threshold: int,
        min_bright_pixels: int,
        min_consecutive_frames: int,
        sequence_timeout: float,
        max_dwell_time: float,
        csv_path: Optional[Path] = None,
    ):
        self.cfg = cfg
        self.det = TwoLineDetector(
            brightness_threshold=brightness_threshold,
            min_bright_pixels=min_bright_pixels,
            min_consecutive_frames=min_consecutive_frames,
            sequence_timeout=sequence_timeout,
            line_thickness=8,
            max_dwell_time=max_dwell_time,
            dwell_spike_factor=cfg.dwell_spike_factor,
            csv_path=csv_path,
            use_bg_subtraction=cfg.use_bg_subtraction,
            bg_delta=cfg.bg_delta,
        )

    def update(self, frame: np.ndarray, timestamp: float) -> bool:
        """
        Mask pixels outside the ROI so bright objects elsewhere in the frame
        cannot trigger this area's lines.  Line coordinates remain in full-frame
        space — no remapping needed.
        """
        roi = self.cfg.roi
        x1, y1 = min(roi.x1, roi.x2), min(roi.y1, roi.y2)
        x2, y2 = max(roi.x1, roi.x2), max(roi.y1, roi.y2)
        masked = frame.copy()
        masked[:y1, :]  = 0
        masked[y2:, :]  = 0
        masked[:, :x1]  = 0
        masked[:, x2:]  = 0
        return self.det.update(masked, self.cfg.l1, self.cfg.l2, timestamp)

    @property
    def state(self) -> LineState:
        return self.det.state

    def reset(self):
        self.det.reset()

    def close(self):
        self.det.close()


# ---------------------------------------------------------------------------
# QuorumReconciler  (sliding-window quorum → confirmed piece count)
# ---------------------------------------------------------------------------
class QuorumReconciler:
    """
    Replaces the old median-based CountReconciler.

    A piece is confirmed only when at least `quorum` distinct areas fire
    within a `piece_window_seconds` sliding window.  Near-simultaneous
    triggers (< `min_inter_area_gap_seconds` apart) are treated as a single
    false-positive event (e.g. a person walking through adjacent areas on
    the same camera) and the duplicate is discarded.

    Per-area running totals are still maintained for HUD display and
    divergence logging.

    YAML keys (under counting_areas):
        piece_window_seconds: 5.0
        min_inter_area_gap_seconds: 1.5
        quorum: 2
    """

    def __init__(
        self,
        n_areas: int,
        piece_window_seconds: float = 5.0,
        min_inter_area_gap_seconds: float = 1.5,
        quorum: int = 2,
        divergence_warn_threshold: int = 3,
    ):
        self.n_areas = n_areas
        self.piece_window = piece_window_seconds
        self.min_gap = min_inter_area_gap_seconds
        self.quorum = quorum
        self.divergence_warn_threshold = divergence_warn_threshold

        self.counts: List[int] = [0] * n_areas
        self.piece_count: int = 0           # authoritative confirmed-piece counter
        self._last_piece_count: int = 0     # snapshot at last Firebase push

        # Triggers accepted into the current window: List of (area_idx, timestamp)
        self._pending_triggers: List[Tuple[int, float]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_area_triggered(self, area_idx: int, timestamp: float) -> Tuple[bool, bool]:
        """
        Record a trigger from *area_idx* at *timestamp*.

        Returns (confirmed_piece, diverged).
          confirmed_piece – True when this trigger pushed the window to quorum.
          diverged        – True when max(counts) - min(counts) > threshold.
        """
        self.counts[area_idx] += 1

        # Prune triggers older than the piece window
        self._pending_triggers = [
            (idx, ts) for (idx, ts) in self._pending_triggers
            if timestamp - ts <= self.piece_window
        ]

        # Reject near-simultaneous trigger (different area fired < min_gap ago)
        if self._pending_triggers:
            last_ts = self._pending_triggers[-1][1]
            if timestamp - last_ts < self.min_gap:
                # Near-simultaneous – discard as false positive (person / debris)
                diverged = (max(self.counts) - min(self.counts)) > self.divergence_warn_threshold
                return False, diverged

        # Accept this trigger into the window
        self._pending_triggers.append((area_idx, timestamp))

        # Count distinct areas that have fired in the window
        areas_in_window = {idx for (idx, _) in self._pending_triggers}
        confirmed_piece = len(areas_in_window) >= self.quorum

        if confirmed_piece:
            self.piece_count += 1
            # Clear the window so the next piece starts fresh
            self._pending_triggers = []

        diverged = (max(self.counts) - min(self.counts)) > self.divergence_warn_threshold
        return confirmed_piece, diverged

    def piece_confirmed(self) -> bool:
        """True if piece_count moved up since last call to this method."""
        if self.piece_count > self._last_piece_count:
            self._last_piece_count = self.piece_count
            return True
        return False

    def reset(self):
        self.counts = [0] * self.n_areas
        self.piece_count = 0
        self._last_piece_count = 0
        self._pending_triggers = []

    def pending_area_count(self) -> int:
        """Number of distinct areas that have fired in the current open window."""
        return len({idx for (idx, _) in self._pending_triggers})

    def status_text(self) -> str:
        parts = "  ".join(
            f"A{i+1}:{c}" for i, c in enumerate(self.counts)
        )
        return (
            f"pieces={self.piece_count}  [{parts}]  "
            f"window={self.pending_area_count()}/{self.quorum}"
        )


# ---------------------------------------------------------------------------
# StreamManager
# ---------------------------------------------------------------------------
class StreamManager:
    """One cv2.VideoCapture per unique RTSP URL."""

    def __init__(self, rtsp_urls: List[str]):
        unique = list(dict.fromkeys(rtsp_urls))  # deduplicate, preserve order
        self._caps: Dict[str, Optional[cv2.VideoCapture]] = {}
        self._fail_counts: Dict[str, int] = {}
        for url in unique:
            self._caps[url] = None
            self._fail_counts[url] = 0
            self._open(url)

    def _open(self, url: str):
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            self._caps[url] = cap
            self._fail_counts[url] = 0
            logger.info(f"Stream connected: {url}")
        else:
            cap.release()
            self._caps[url] = None
            self._fail_counts[url] += 1
            logger.warning(f"Stream open failed ({self._fail_counts[url]}): {url}")

    def read_all(self) -> Dict[str, Optional[np.ndarray]]:
        result: Dict[str, Optional[np.ndarray]] = {}
        for url, cap in self._caps.items():
            if cap is None or not cap.isOpened():
                result[url] = None
                continue
            ret, frame = cap.read()
            if ret and frame is not None:
                self._fail_counts[url] = 0
                result[url] = cv2.resize(
                    frame, (PANEL_W, PANEL_H), interpolation=cv2.INTER_AREA
                )
            else:
                logger.warning(f"Frame read failed: {url}")
                cap.release()
                self._caps[url] = None
                self._fail_counts[url] += 1
                result[url] = None
        return result

    def reconnect(self, url: str):
        if url not in self._caps:
            return
        cap = self._caps[url]
        if cap is not None:
            cap.release()
            self._caps[url] = None
        time.sleep(RECONNECT_DELAY)
        self._open(url)

    def any_down(self) -> List[str]:
        return [url for url, cap in self._caps.items()
                if cap is None or not cap.isOpened()]

    def release_all(self):
        for cap in self._caps.values():
            if cap is not None:
                cap.release()
        self._caps = {}


# ---------------------------------------------------------------------------
# HUD drawing
# ---------------------------------------------------------------------------
def _cam_label(rtsp_url: str) -> str:
    """Extract a short camera label from an RTSP URL or file path.
    e.g. 'CAM-2', 'CAM-3', or the filename stem for local files."""
    import re
    m = re.search(r'channel=(\d+)', rtsp_url)
    if m:
        return f"CAM-{m.group(1)}"
    # Local file path — return the filename without extension
    from pathlib import Path as _Path
    stem = _Path(rtsp_url).stem
    return stem[:14] if stem else rtsp_url[-12:]


def draw_area_hud(
    panel: np.ndarray,
    area_detectors: List[AreaDetector],
    focused_idx: int,
    reconciler: QuorumReconciler,
    flash: bool,
):
    """
    Draw HUD overlay showing:
    - Joined (median) count prominently
    - Per-area count table with match/diverge indicators
    - Focused area L1/L2 state
    - Divergence warning if active
    """
    h, w = panel.shape[:2]
    fdet = area_detectors[focused_idx]
    fstate = fdet.state
    color = AREA_COLORS[focused_idx % len(AREA_COLORS)]

    # Title bar
    cv2.rectangle(panel, (0, 0), (w, 28), (30, 60, 30), -1)
    title = (f"FOCUSED: {fdet.cfg.name}  "
             f"[Tab/1-9=cycle  S=save  R=reset  H=help]")
    cv2.putText(panel, title, (6, 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 255, 200), 1)

    # Status box background
    bx = 4
    box_h = 36 + reconciler.n_areas * 18 + 30
    cv2.rectangle(panel, (bx, 32), (bx + 280, 32 + box_h), (0, 0, 0), -1)

    # Joined count (large)
    count_col = COL_COUNT if flash else (0, 255, 0)
    cv2.putText(panel, f"COUNT: {reconciler.piece_count}", (bx + 6, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, count_col, 2)

    pending_n = reconciler.pending_area_count()
    quorum_tag = f"window: {pending_n}/{reconciler.quorum} areas"
    cv2.putText(panel, quorum_tag, (bx + 6, 74),
                cv2.FONT_HERSHEY_SIMPLEX, 0.30, (120, 160, 120), 1)

    # Separator
    cv2.line(panel, (bx + 4, 78), (bx + 274, 78), (60, 60, 60), 1)

    # Per-area count table
    diverged = (max(reconciler.counts) - min(reconciler.counts)
                ) > reconciler.divergence_warn_threshold
    for i, adet in enumerate(area_detectors):
        y = 92 + i * 18
        area_color = AREA_COLORS[i % len(AREA_COLORS)]
        cnt = reconciler.counts[i]
        matches = (cnt == reconciler.piece_count)
        marker = "[*]" if matches else "[ ]"
        # Dimmed if not focused
        draw_color = tuple(min(255, c + 40) for c in area_color) if i == focused_idx else area_color
        cam_lbl = _cam_label(adet.cfg.camera_rtsp)
        label = f"{marker} {adet.cfg.name} [{cam_lbl}]: {cnt}"
        cv2.putText(panel, label, (bx + 6, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, draw_color, 1)

    # Divergence warning
    warn_y = 92 + reconciler.n_areas * 18 + 4
    if diverged:
        cv2.putText(panel, "! DIVERGENCE WARNING",
                    (bx + 6, warn_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 255), 1)
    else:
        cv2.putText(panel, "divergence: OK",
                    (bx + 6, warn_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.33, (80, 160, 80), 1)

    # Focused area L1/L2 state + min_px (below box)
    l1_col = tuple(min(255, c + 60) for c in color) if fstate.l1_confirmed else (80, 80, 80)
    l2_col = tuple(min(255, c + 60) for c in color) if fstate.l2_confirmed else (80, 80, 80)
    state_y = 32 + box_h + 14
    cv2.putText(panel, f"L1: {'ON' if fstate.l1_confirmed else 'off'}",
                (bx + 6, state_y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, l1_col, 1)
    cv2.putText(panel, f"L2: {'ON' if fstate.l2_confirmed else 'off'}",
                (bx + 80, state_y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, l2_col, 1)
    bg_tag = f"  bg+{fdet.cfg.bg_delta}" if fdet.cfg.use_bg_subtraction else ""
    cv2.putText(panel, f"min_px={fdet.cfg.min_line_pixels}{bg_tag}  [/]",
                (bx + 6, state_y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (160, 160, 160), 1)
    if fstate.last_travel_time > 0:
        cv2.putText(panel, f"travel={fstate.last_travel_time:.2f}s",
                    (bx + 154, state_y), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (160, 160, 160), 1)

    # Flash banner
    if flash:
        cv2.putText(panel, "*** PIECE COUNTED ***",
                    (w // 2 - 130, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, COL_COUNT, 3)


def draw_all_areas(
    panel: np.ndarray,
    area_detectors: List[AreaDetector],
    focused_idx: int,
    flash: bool,
):
    """Draw ROI + lines for all areas on a shared camera panel."""
    for i, adet in enumerate(area_detectors):
        focused = (i == focused_idx)
        color = AREA_COLORS[i % len(AREA_COLORS)]
        s = adet.state
        # Use brighter color for focused area
        draw_color = tuple(min(255, c + 60) for c in color) if focused else color
        adet.cfg.roi.draw(panel, draw_color, focused=focused)
        adet.cfg.l1.draw(panel, triggered=s.l1_confirmed, flash=flash and focused,
                         focused=focused)
        adet.cfg.l2.draw(panel, triggered=s.l2_confirmed, flash=flash and focused,
                         focused=focused)


# ---------------------------------------------------------------------------
# Save area positions to settings.yaml
# ---------------------------------------------------------------------------
def save_area_positions(area_idx: int, roi: ROI, l1: LineSeg, l2: LineSeg,
                        min_line_pixels: int, use_bg_subtraction: bool = False,
                        bg_delta: int = 30):
    config = load_config()
    areas = config.get("counting_areas", {}).get("areas", [])
    if area_idx >= len(areas):
        logger.error(f"save_area_positions: area_idx {area_idx} out of range")
        return
    a = areas[area_idx]
    a["roi"]                 = {"start": [roi.x1, roi.y1], "end": [roi.x2, roi.y2]}
    a["line1"]               = {"start": list(l1.p1),       "end": list(l1.p2)}
    a["line2"]               = {"start": list(l2.p1),       "end": list(l2.p2)}
    a["min_line_pixels"]     = min_line_pixels
    a["use_bg_subtraction"]  = use_bg_subtraction
    a["bg_delta"]            = bg_delta
    config["counting_areas"]["areas"] = areas
    save_config(config)
    logger.info(
        f"Saved area {area_idx} ({a.get('name', '')}): "
        f"ROI=({roi.x1},{roi.y1})-({roi.x2},{roi.y2})  "
        f"L1={l1.p1}-{l1.p2}  L2={l2.p1}-{l2.p2}  "
        f"min_line_pixels={min_line_pixels}  "
        f"use_bg_subtraction={use_bg_subtraction}  bg_delta={bg_delta}"
    )


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
def print_help():
    print("""
Mill Stand Counter (CAM-2) - Multi-Area Independent Counting
-------------------------------------------------------------
  V              Cycle to next camera view (single window)
  Tab / 1-9      Cycle / jump to focused area within current camera view
  [  /  ]        Decrease / increase focused area min_line_pixels by 1 (auto-saves)
  S              Save focused area ROI + lines + min_line_pixels to settings.yaml
  R              Reset all detectors + all area counts
  Space          Pause / resume
  Q / ESC        Quit
  H              This help

Mouse (--display mode):
  Click + drag handles (filled circles) to move ROI corners and line endpoints.
  Focused area has larger handles and brighter colors.
  L1 = area color  |  L2 = darker area color  |  ROI = area color

Counting:
  Each area counts independently (L1 → L2 per area).
  A piece is confirmed when >= quorum distinct areas fire within piece_window_seconds.
  Near-simultaneous triggers (< min_inter_area_gap_seconds) are rejected as false positives.
  Dwell spike re-arm: if brightness surges 30%+ above peak during dwell, detector re-arms.
  Divergence warning logged when max(areas) - min(areas) > threshold.
""")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def run_mill_counter(
    duration: Optional[int] = None,
    test_mode: bool = False,
    display: bool = False,
    use_firebase: bool = True,
    brightness_threshold: int = 160,
    min_line_pixels: int = 30,
    min_consecutive_frames: int = 2,
    sequence_timeout: float = 4.0,
    max_dwell_time: float = 2.0,
    bg_delta: int = 30,
    video_cam2: Optional[str] = None,
    video_cam3: Optional[str] = None,
):
    load_env(PROJECT_ROOT / ".env")
    config = load_config()

    ca_cfg = config.get("counting_areas", {})
    divergence_warn_threshold = int(ca_cfg.get("divergence_warn_threshold", 3))
    piece_window_seconds      = float(ca_cfg.get("piece_window_seconds", 5.0))
    min_inter_area_gap        = float(ca_cfg.get("min_inter_area_gap_seconds", 1.5))
    quorum                    = int(ca_cfg.get("quorum", 2))

    # --- Build area detectors ---
    area_detectors = load_area_detectors(
        config,
        brightness_threshold=brightness_threshold,
        min_bright_pixels=min_line_pixels,
        min_consecutive_frames=min_consecutive_frames,
        sequence_timeout=sequence_timeout,
        max_dwell_time=max_dwell_time,
    )
    n_areas = len(area_detectors)
    logger.info(f"Loaded {n_areas} counting areas")

    # --- Reconciler ---
    reconciler = QuorumReconciler(
        n_areas=n_areas,
        piece_window_seconds=piece_window_seconds,
        min_inter_area_gap_seconds=min_inter_area_gap,
        quorum=quorum,
        divergence_warn_threshold=divergence_warn_threshold,
    )

    # --- Override RTSP URLs with local video files for testing ---
    CAM2_RTSP_MARKER = "channel=2"
    CAM3_RTSP_MARKER = "channel=3"
    if video_cam2 or video_cam3:
        kept = []
        for adet in area_detectors:
            url = adet.cfg.camera_rtsp
            if video_cam2 and CAM2_RTSP_MARKER in url:
                adet.cfg.camera_rtsp = video_cam2
                logger.info(f"[replay] {adet.cfg.name}: using local file {video_cam2}")
                kept.append(adet)
            elif video_cam3 and CAM3_RTSP_MARKER in url:
                adet.cfg.camera_rtsp = video_cam3
                logger.info(f"[replay] {adet.cfg.name}: using local file {video_cam3}")
                kept.append(adet)
            else:
                logger.info(f"[replay] {adet.cfg.name}: skipping (no video file provided for its camera)")
        area_detectors = kept
        n_areas = len(area_detectors)
        # Rebuild reconciler with the reduced area count
        reconciler = QuorumReconciler(
            n_areas=n_areas,
            piece_window_seconds=piece_window_seconds,
            min_inter_area_gap_seconds=min_inter_area_gap,
            quorum=min(quorum, n_areas),
            divergence_warn_threshold=divergence_warn_threshold,
        )

    # --- Stream manager ---
    all_rtsp = [d.cfg.camera_rtsp for d in area_detectors]
    stream_mgr = StreamManager(all_rtsp)

    # --- Group area detectors by camera RTSP URL (for display) ---
    cam_area_map: Dict[str, List[int]] = {}
    for i, adet in enumerate(area_detectors):
        cam_area_map.setdefault(adet.cfg.camera_rtsp, []).append(i)

    # --- Session manager ---
    break_threshold = config.get('detection', {}).get('break_threshold_seconds', 300)
    session_manager = SessionManager(break_threshold_seconds=break_threshold)

    # --- Firebase ---
    firebase = None
    if use_firebase:
        try:
            from firebase_client import get_firebase_client
            firebase = get_firebase_client()
            if firebase.initialize():
                logger.info("Firebase connected")
                last_session = firebase.get_last_session()
                if session_manager.restore_session(last_session):
                    logger.info(f"Continuing existing {session_manager.status} session")
                else:
                    logger.info("Starting fresh session")
                today_count = firebase.get_mill_today_count()
                if today_count > 0:
                    # Seed each area counter with today's count so reconciler
                    # starts from the right baseline.
                    for i in range(n_areas):
                        reconciler.counts[i] = today_count
                    reconciler.piece_count = today_count
                    reconciler._last_piece_count = today_count
                    logger.info(f"Restored today's mill count: {today_count}")
            else:
                logger.warning("Firebase init failed - offline mode")
                firebase = None
        except ImportError as e:
            logger.warning(f"Firebase module not available: {e}")
            firebase = None
        except Exception as e:
            logger.warning(f"Firebase error: {e}")
            firebase = None

    logger.info(
        f"Mill stand counter started | {n_areas} independent areas | "
        f"divergence_threshold={divergence_warn_threshold} | break={break_threshold}s"
    )

    start_time = time.time()
    last_status_time = 0.0
    last_firebase_status_time = 0.0
    flash_until = 0.0
    paused = False
    deferred_break_start: Optional[datetime] = None  # start time of pending BREAK session (not yet pushed)
    last_reset_time: float = 0.0                      # epoch time of last area count reset

    # --- Display setup ---
    WIN_NAME = "Mill Counter"
    cam_urls: List[str] = list(cam_area_map.keys())   # ordered list of unique cameras
    cam_drag: Dict[str, DragManager] = {url: DragManager() for url in cam_urls}
    cam_focused: Dict[str, int] = {
        url: indices[0] for url, indices in cam_area_map.items()
    }
    cam_last_frame: Dict[str, Optional[np.ndarray]] = {url: None for url in cam_urls}
    active_cam_idx: int = 0   # index into cam_urls — which camera is shown

    def _bind_mouse(url: str) -> None:
        """Attach mouse callback for the given camera to the single window."""
        def on_mouse(event, mx, my, flags, param):
            fi = cam_focused[url]
            fdet = area_detectors[fi]
            draggables = [fdet.cfg.roi, fdet.cfg.l1, fdet.cfg.l2]
            drag = cam_drag[url]
            if event == cv2.EVENT_LBUTTONDOWN:
                drag.find_handle(mx, my, draggables, 0)
            elif event == cv2.EVENT_MOUSEMOVE and (flags & cv2.EVENT_FLAG_LBUTTON):
                drag.drag(mx, my, 0)
            elif event == cv2.EVENT_LBUTTONUP:
                drag.release()
        cv2.setMouseCallback(WIN_NAME, on_mouse)

    if display:
        cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN_NAME, PANEL_W, PANEL_H)
        _bind_mouse(cam_urls[active_cam_idx])
        print_help()

    try:
        while True:
            now = time.time()

            if duration and (now - start_time) >= duration:
                break

            # Midnight reset
            if session_manager.check_daily_reset():
                logger.info("Midnight reset")
                reconciler.reset()
                if firebase:
                    today = datetime.now(IST).date().isoformat()
                    live_ref = firebase.db.collection('live').document('mill_stand')
                    live_ref.set({'today_count': 0, 'date': today}, merge=True)

            # Paused
            if paused:
                if display:
                    key = cv2.waitKey(100) & 0xFF
                    if key in (ord('q'), 27):
                        break
                    elif key == ord(' '):
                        paused = False
                        logger.info("Resumed")
                    elif key == ord('h'):
                        print_help()
                continue

            # Reconnect any down streams (skip if replaying local files — EOF = done)
            replay_mode = bool(video_cam2 or video_cam3)
            down = stream_mgr.any_down()
            if down:
                if replay_mode:
                    logger.info("[replay] Stream ended (EOF) — stopping.")
                    break
                for url in down:
                    stream_mgr.reconnect(url)

            # Read all frames
            frames = stream_mgr.read_all()
            for url, frame in frames.items():
                if frame is not None:
                    cam_last_frame[url] = frame

            # --- Run detectors ---
            for area_idx, adet in enumerate(area_detectors):
                frame = frames.get(adet.cfg.camera_rtsp)
                if frame is None:
                    continue
                triggered = adet.update(frame, now)
                if triggered:
                    confirmed, diverged = reconciler.on_area_triggered(area_idx, now)
                    logger.info(
                        f"Area '{adet.cfg.name}' triggered | "
                        f"area_count={reconciler.counts[area_idx]} | "
                        f"{reconciler.status_text()}"
                    )
                    if diverged:
                        area_detail = "  ".join(
                            f"{d.cfg.name}={reconciler.counts[j]}"
                            for j, d in enumerate(area_detectors)
                        )
                        logger.warning(
                            f"DIVERGENCE: {area_detail} "
                            f"(max-min > {divergence_warn_threshold})"
                        )

                    # Push to Firebase only when a piece is confirmed by quorum
                    if reconciler.piece_confirmed():
                        flash_until = now + FLASH_DUR
                        travel = adet.state.last_travel_time
                        logger.info(
                            f"*** PIECE #{reconciler.piece_count} COUNTED (quorum) | "
                            f"travel={travel:.2f}s | areas={reconciler.counts} ***"
                        )

                        result = session_manager.on_piece_counted(travel_time=travel)

                        if firebase:
                            if result['session_to_end']:
                                firebase.end_mill_session(result['session_to_end'])
                            if result['session_to_create']:
                                # BREAK→RUN transition: flush the deferred BREAK session first
                                if deferred_break_start is not None:
                                    break_sess = Session(
                                        session_type=SessionType.BREAK,
                                        start_time=deferred_break_start,
                                    )
                                    break_sess.end_time = datetime.now(IST)
                                    firebase.create_session(break_sess, camera='CAM-2')
                                    firebase.end_mill_session(break_sess)
                                    logger.info(
                                        f"Pushed deferred BREAK: "
                                        f"{deferred_break_start.strftime('%H:%M:%S')} → "
                                        f"{break_sess.end_time.strftime('%H:%M:%S')} "
                                        f"({break_sess.duration_minutes:.1f} min)"
                                    )
                                    deferred_break_start = None
                                firebase.create_session(
                                    result['session_to_create'], camera='CAM-2'
                                )
                            if result['session_to_update']:
                                firebase.update_session(result['session_to_update'])

                            firebase.push_mill_count(
                                {
                                    'timestamp': datetime.now(IST),
                                    'avg_travel_time': travel,
                                    'vote_ratio': f"1/{n_areas}",
                                    'stands_detected': 1,
                                },
                                {'run_minutes_since_last': result['run_minutes_since_last']}
                            )
                            firebase.update_mill_status(
                                'RUNNING', session_manager.get_current_session_dict()
                            )

            # Break detection
            break_result = session_manager.check_for_break()
            if break_result:
                logger.info(f"Break detected - no counts for {break_threshold}s")
                if firebase:
                    # End the RUN session immediately
                    if break_result['session_to_end']:
                        firebase.end_mill_session(break_result['session_to_end'])
                    firebase.update_mill_status(
                        'BREAK', session_manager.get_current_session_dict()
                    )
                # Defer the BREAK session — record start time but don't push to Firebase yet
                # (consecutive breaks will be merged into one doc when the next piece arrives)
                if deferred_break_start is None:
                    deferred_break_start = break_result['session_to_create'].start_time
                    logger.info(
                        f"Deferred BREAK session start: "
                        f"{deferred_break_start.strftime('%H:%M:%S')}"
                    )
                # Reset all area counts so divergence clears at start of next session
                for adet in area_detectors:
                    adet.reset()
                reconciler.reset()
                last_reset_time = now
                logger.info("Break reset: all area counts cleared")

            # Periodic re-reset while already in BREAK (consecutive idle windows)
            # check_for_break() returns None once status==BREAK, so we handle it here
            if (session_manager.status == "BREAK"
                    and now - last_reset_time >= break_threshold):
                for adet in area_detectors:
                    adet.reset()
                reconciler.reset()
                last_reset_time = now
                logger.info("Consecutive break reset: area counts cleared")

            # --- Display ---
            if display:
                flash = now < flash_until
                quit_requested = False

                # Render only the active camera into the single window
                active_url = cam_urls[active_cam_idx]
                panel_base = cam_last_frame.get(active_url)
                if panel_base is None:
                    panel = np.zeros((PANEL_H, PANEL_W, 3), np.uint8)
                    cv2.putText(panel, "NO SIGNAL",
                                (PANEL_W // 2 - 60, PANEL_H // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 200), 2)
                else:
                    panel = panel_base.copy()

                area_indices = cam_area_map[active_url]
                cam_area_dets = [area_detectors[i] for i in area_indices]
                focused_global = cam_focused[active_url]
                try:
                    focused_local = area_indices.index(focused_global)
                except ValueError:
                    focused_local = 0

                # Camera label when multiple cameras exist
                if len(cam_urls) > 1:
                    cv2.putText(panel,
                                f"CAM {active_cam_idx + 1}/{len(cam_urls)}  [V=next cam]",
                                (4, PANEL_H - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

                draw_all_areas(panel, cam_area_dets, focused_local, flash)
                draw_area_hud(panel, cam_area_dets, focused_local, reconciler, flash)
                cv2.imshow(WIN_NAME, panel)

                key = cv2.waitKey(1) & 0xFF

                if key in (ord('q'), 27):
                    logger.info("User quit")
                    quit_requested = True

                elif key == ord(' '):
                    paused = True
                    logger.info("Paused")

                elif key == ord('r'):
                    for adet in area_detectors:
                        adet.reset()
                    reconciler.reset()
                    logger.info("Reset: all detectors + all area counts cleared")

                elif key == ord('s'):
                    fi = cam_focused[active_url]
                    adet = area_detectors[fi]
                    save_area_positions(adet.cfg.yaml_idx, adet.cfg.roi, adet.cfg.l1, adet.cfg.l2,
                                        adet.cfg.min_line_pixels,
                                        adet.cfg.use_bg_subtraction, adet.cfg.bg_delta)

                elif key == ord('h'):
                    print_help()

                elif key == ord('v'):
                    active_cam_idx = (active_cam_idx + 1) % len(cam_urls)
                    active_url = cam_urls[active_cam_idx]
                    _bind_mouse(active_url)
                    logger.info(f"Camera view: {active_cam_idx + 1}/{len(cam_urls)} ({active_url})")

                elif key == ord(']'):
                    fi = cam_focused[active_url]
                    adet = area_detectors[fi]
                    adet.cfg.min_line_pixels = min(200, adet.cfg.min_line_pixels + 1)
                    adet.det.min_bright_pixels = adet.cfg.min_line_pixels
                    save_area_positions(adet.cfg.yaml_idx, adet.cfg.roi, adet.cfg.l1, adet.cfg.l2,
                                        adet.cfg.min_line_pixels,
                                        adet.cfg.use_bg_subtraction, adet.cfg.bg_delta)
                    logger.info(f"{adet.cfg.name} min_line_pixels={adet.cfg.min_line_pixels}")

                elif key == ord('['):
                    fi = cam_focused[active_url]
                    adet = area_detectors[fi]
                    adet.cfg.min_line_pixels = max(1, adet.cfg.min_line_pixels - 1)
                    adet.det.min_bright_pixels = adet.cfg.min_line_pixels
                    save_area_positions(adet.cfg.yaml_idx, adet.cfg.roi, adet.cfg.l1, adet.cfg.l2,
                                        adet.cfg.min_line_pixels,
                                        adet.cfg.use_bg_subtraction, adet.cfg.bg_delta)
                    logger.info(f"{adet.cfg.name} min_line_pixels={adet.cfg.min_line_pixels}")

                elif key == ord('\t'):
                    area_indices = cam_area_map[active_url]
                    cur = cam_focused[active_url]
                    try:
                        cur_local = area_indices.index(cur)
                    except ValueError:
                        cur_local = 0
                    cam_focused[active_url] = area_indices[
                        (cur_local + 1) % len(area_indices)
                    ]
                    logger.info(
                        f"Focused: {area_detectors[cam_focused[active_url]].cfg.name}"
                    )

                elif ord('1') <= key <= ord('9'):
                    target_local = key - ord('1')
                    area_indices = cam_area_map[active_url]
                    if target_local < len(area_indices):
                        cam_focused[active_url] = area_indices[target_local]

                if quit_requested:
                    break

            # Periodic console status + systemd watchdog keepalive
            if now - last_status_time >= 30:
                last_status_time = now
                daily_totals = session_manager.get_daily_totals()
                logger.info(
                    f"Status: {reconciler.status_text()} | "
                    f"Run: {daily_totals['total_run_minutes']:.1f}min | "
                    f"Break: {daily_totals['total_break_minutes']:.1f}min | "
                    f"State: {session_manager.status}"
                )
                sd_notify("WATCHDOG=1")

            # Periodic Firebase heartbeat
            if firebase and now - last_firebase_status_time >= 60:
                last_firebase_status_time = now
                firebase.update_mill_status(
                    session_manager.status,
                    session_manager.get_current_session_dict()
                )

            # Test mode
            if test_mode:
                for adet in area_detectors:
                    s = adet.state
                    if s.l1_confirmed or s.l2_confirmed or s.pending:
                        ts = datetime.now(IST).strftime("%H:%M:%S")
                        print(
                            f"{ts} | {adet.cfg.name} | "
                            f"L1={'ON' if s.l1_confirmed else 'off'} "
                            f"L2={'ON' if s.l2_confirmed else 'off'} | "
                            f"{'PENDING' if s.pending else '       '} | "
                            f"{reconciler.status_text()}"
                        )

    except KeyboardInterrupt:
        logger.info("Stopped by user")

    finally:
        for adet in area_detectors:
            adet.close()
        stream_mgr.release_all()
        if display:
            cv2.destroyAllWindows()

        ended_session = session_manager.shutdown()
        if firebase:
            # If there is a deferred BREAK that was never followed by a piece,
            # push it now (create + end) before going OFFLINE.
            # In this case ended_session IS that same BREAK object from session_manager,
            # so we skip end_mill_session on it to avoid updating a non-existent doc.
            if deferred_break_start is not None:
                break_sess = Session(
                    session_type=SessionType.BREAK,
                    start_time=deferred_break_start,
                )
                break_sess.end_time = datetime.now(IST)
                firebase.create_session(break_sess, camera='CAM-2')
                firebase.end_mill_session(break_sess)
                logger.info(
                    f"Shutdown: pushed deferred BREAK "
                    f"{deferred_break_start.strftime('%H:%M:%S')} → "
                    f"{break_sess.end_time.strftime('%H:%M:%S')} "
                    f"({break_sess.duration_minutes:.1f} min)"
                )
                # ended_session is the same BREAK — already pushed above, skip it
            elif ended_session:
                firebase.end_mill_session(ended_session)
            firebase.update_mill_status('OFFLINE')

    daily_totals = session_manager.get_daily_totals()
    logger.info("=" * 50)
    logger.info(f"FINAL COUNT (quorum): {reconciler.piece_count} pieces")
    logger.info(f"Area counts: {reconciler.counts}")
    logger.info(f"Total run time: {daily_totals['total_run_minutes']:.1f} minutes")
    logger.info(f"Total break time: {daily_totals['total_break_minutes']:.1f} minutes")
    logger.info(f"Runtime: {(time.time() - start_time) / 60:.1f} minutes")
    logger.info("=" * 50)


def load_area_detectors(
    config: dict,
    brightness_threshold: int,
    min_bright_pixels: int,
    min_consecutive_frames: int,
    sequence_timeout: float,
    max_dwell_time: float,
) -> List[AreaDetector]:
    ca = config.get("counting_areas", {})
    areas_raw = ca.get("areas", [])
    if not areas_raw:
        logger.error("No counting_areas.areas found in settings.yaml")
        sys.exit(1)

    detectors: List[AreaDetector] = []
    for i, a in enumerate(areas_raw):
        r = a.get("roi", {})
        roi = ROI(
            r["start"][0], r["start"][1],
            r["end"][0],   r["end"][1],
        )
        lc1 = a.get("line1", {})
        lc2 = a.get("line2", {})
        color = AREA_COLORS[i % len(AREA_COLORS)]
        l1 = LineSeg(
            tuple(lc1["start"]), tuple(lc1["end"]), f"L1", color
        )
        l2 = LineSeg(
            tuple(lc2["start"]), tuple(lc2["end"]), f"L2",
            tuple(max(0, c - 80) for c in color)  # slightly darker for L2
        )

        cfg = AreaConfig(
            name=a.get("name", f"Area {i+1}"),
            order=a.get("order", i + 1),
            camera_rtsp=a["camera_rtsp"],
            roi=roi,
            l1=l1,
            l2=l2,
            yaml_idx=i,
            min_line_pixels=int(a.get("min_line_pixels", min_bright_pixels)),
            use_bg_subtraction=bool(a.get("use_bg_subtraction", False)),
            bg_delta=int(a.get("bg_delta", 30)),
            dwell_spike_factor=float(a.get("dwell_spike_factor", 0.3)),
        )

        csv_path = (PROJECT_ROOT / "data" / "logs" /
                    f"line_brightness_area{i+1}.csv")

        det = AreaDetector(
            cfg=cfg,
            brightness_threshold=brightness_threshold,
            min_bright_pixels=cfg.min_line_pixels,
            min_consecutive_frames=min_consecutive_frames,
            sequence_timeout=sequence_timeout,
            max_dwell_time=max_dwell_time,
            csv_path=csv_path,
        )
        detectors.append(det)

    # Sort by order
    detectors.sort(key=lambda d: d.cfg.order)
    return detectors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='AIS Mill Stand Counter - Multi-Area Ordered-Sequence Voting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--duration', type=int,
                        help='Run duration in seconds (default: run forever)')
    parser.add_argument('--test', action='store_true',
                        help='Test mode: print per-frame area trigger state')
    parser.add_argument('--display', action='store_true',
                        help='Show live annotated video + calibration UI')
    parser.add_argument('--no-firebase', action='store_true',
                        help='Run without Firebase sync')
    parser.add_argument('--brightness-threshold', type=int, default=160,
                        help='Min pixel brightness to trigger a line (default: 160)')
    parser.add_argument('--min-line-pixels', type=int, default=30,
                        help='Min bright pixels on a line to trigger (default: 30)')
    parser.add_argument('--min-consecutive-frames', type=int, default=2,
                        help='Consecutive frames needed to confirm a line (default: 2)')
    parser.add_argument('--sequence-timeout', type=float, default=4.0,
                        help='Max L1→L2 wait time per area in seconds (default: 4.0)')
    parser.add_argument('--max-dwell-time', type=float, default=2.0,
                        help='Max continuous line trigger before suppression (default: 2.0)')
    parser.add_argument('--bg-delta', type=int, default=30,
                        help='BG subtraction delta: pixels must be this many units above EMA baseline (default: 30, overridden per-area by settings.yaml)')
    parser.add_argument('--video-cam2', type=str, default=None,
                        help='Local video file to use instead of CAM-2 RTSP stream (for testing/replay)')
    parser.add_argument('--video-cam3', type=str, default=None,
                        help='Local video file to use instead of CAM-3 RTSP stream (for testing/replay)')
    args = parser.parse_args()

    run_mill_counter(
        duration=args.duration,
        test_mode=args.test,
        display=args.display,
        use_firebase=not args.no_firebase,
        brightness_threshold=args.brightness_threshold,
        min_line_pixels=args.min_line_pixels,
        min_consecutive_frames=args.min_consecutive_frames,
        sequence_timeout=args.sequence_timeout,
        max_dwell_time=args.max_dwell_time,
        bg_delta=args.bg_delta,
        video_cam2=args.video_cam2,
        video_cam3=args.video_cam3,
    )


if __name__ == "__main__":
    main()
