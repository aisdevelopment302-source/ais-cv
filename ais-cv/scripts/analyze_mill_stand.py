#!/usr/bin/env python3
"""
Mill Stand Analysis Script - Dynamic Peak Detection
====================================================
Analyzes mill stand video using dynamic peak detection with rolling baseline.
Counts pieces based on RIGHT→LEFT sequence detection.

Peak Detection Logic:
- Track rolling baseline (average when no peak active)
- Detect peak start: pixels > baseline + rise_threshold
- Track peak maximum
- Detect peak end: pixels < baseline + fall_threshold
- Log peak event with all metrics

Counting Logic:
- RIGHT peak detected → wait for LEFT peak (metal travels R→L)
- LEFT peak within timeout → COUNT +1
- No LEFT peak within timeout → reset (no count)

Output:
- Console: Real-time peak and count logging
- CSV: Detailed event log for analysis

Usage:
    python scripts/analyze_mill_stand.py --display          # With visual output
    python scripts/analyze_mill_stand.py --start 20 --end 50  # Custom range
    python scripts/analyze_mill_stand.py --rise-threshold 8000  # Custom threshold
"""

import cv2
import numpy as np
import yaml
import csv
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@dataclass
class PeakEvent:
    """Represents a detected peak event in a zone."""

    timestamp_sec: float
    timestamp_str: str
    zone: str
    peak_pixels: int
    avg_pixels: float
    baseline_pixels: float
    duration_sec: float
    start_frame: int
    end_frame: int
    peak_brightness: float = 0.0
    avg_brightness: float = 0.0
    peak_ratio: float = 0.0  # peak_pixels / total_zone_pixels
    avg_ratio: float = 0.0  # avg_pixels / total_zone_pixels
    total_zone_pixels: int = 0


@dataclass
class CountEvent:
    """Represents a counted piece (RIGHT followed by LEFT)."""

    count_id: int
    timestamp_sec: float
    timestamp_str: str
    right_peak: PeakEvent
    left_peak: PeakEvent
    travel_time_sec: float  # Time between RIGHT and LEFT peaks


class ZoneTracker:
    """
    Tracks peaks in a zone using threshold-based detection.

    Supports two threshold modes:
    1. Absolute pixel count: pixels >= min_peak_pixels
    2. Ratio-based: (pixels / total_zone_pixels) >= min_peak_ratio

    Algorithm:
    - Detect peak start when threshold condition is met
    - Track peak maximum during peak
    - Detect peak end when below threshold
    - Only emit peak event if duration >= min_peak_duration
    """

    def __init__(
        self,
        zone_id: str,
        min_peak_pixels: int = 10000,
        min_peak_ratio: float = None,
        total_zone_pixels: int = 0,
        min_peak_duration: float = 0.2,
        fps: float = 25.0,
    ):
        self.zone_id = zone_id
        self.min_peak_pixels = min_peak_pixels  # Absolute threshold
        self.min_peak_ratio = min_peak_ratio  # Ratio threshold (if set, takes priority)
        self.total_zone_pixels = total_zone_pixels  # For ratio calculation
        self.min_peak_duration = min_peak_duration
        self.fps = fps

        # Peak tracking state
        self.is_in_peak = False
        self.peak_start_frame = 0
        self.peak_start_time = 0.0
        self.peak_pixels = 0
        self.pixel_sum = 0
        self.frame_count = 0
        self.peak_brightness = 0.0
        self.brightness_sum = 0.0

        # Results
        self.events: List[PeakEvent] = []

    def _is_above_threshold(self, pixel_count: int) -> bool:
        """Check if pixel count exceeds the configured threshold."""
        if self.min_peak_ratio is not None and self.total_zone_pixels > 0:
            # Use ratio-based threshold
            ratio = pixel_count / self.total_zone_pixels
            return ratio >= self.min_peak_ratio
        else:
            # Use absolute pixel threshold
            return pixel_count >= self.min_peak_pixels

    def _get_threshold_display(self) -> str:
        """Get a display string for the current threshold."""
        if self.min_peak_ratio is not None:
            return f"{self.min_peak_ratio * 100:.1f}%"
        else:
            return f"{self.min_peak_pixels:,}px"

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as MM:SS.s"""
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:02d}:{secs:04.1f}"

    def update(
        self, pixel_count: int, avg_brightness: float, frame_num: int, timestamp: float
    ) -> Optional[PeakEvent]:
        """
        Update tracker with new frame data.

        Args:
            pixel_count: Number of bright pixels in zone
            avg_brightness: Average brightness of bright pixels
            frame_num: Current frame number
            timestamp: Current timestamp in seconds

        Returns:
            PeakEvent if a peak just completed, None otherwise.
        """
        event = None
        above_threshold = self._is_above_threshold(pixel_count)

        if not self.is_in_peak:
            # Check for peak start - above threshold
            if above_threshold:
                self.is_in_peak = True
                self.peak_start_frame = frame_num
                self.peak_start_time = timestamp
                self.peak_pixels = pixel_count
                self.pixel_sum = pixel_count
                self.frame_count = 1
                self.peak_brightness = avg_brightness
                self.brightness_sum = avg_brightness
        else:
            # Currently in peak
            # Check for peak end - below threshold
            if not above_threshold:
                # Peak ended - create event only if duration meets minimum
                duration = timestamp - self.peak_start_time
                avg_pixels = (
                    self.pixel_sum / self.frame_count if self.frame_count > 0 else 0
                )
                avg_bright = (
                    self.brightness_sum / self.frame_count
                    if self.frame_count > 0
                    else 0
                )

                # Calculate ratios
                peak_ratio = (
                    self.peak_pixels / self.total_zone_pixels
                    if self.total_zone_pixels > 0
                    else 0.0
                )
                avg_ratio = (
                    avg_pixels / self.total_zone_pixels
                    if self.total_zone_pixels > 0
                    else 0.0
                )

                # Determine threshold value for logging
                if self.min_peak_ratio is not None:
                    threshold_value = (
                        self.min_peak_ratio * self.total_zone_pixels
                        if self.total_zone_pixels > 0
                        else 0
                    )
                else:
                    threshold_value = float(self.min_peak_pixels)

                # Only emit event if peak duration meets minimum threshold
                if duration >= self.min_peak_duration:
                    event = PeakEvent(
                        timestamp_sec=self.peak_start_time,
                        timestamp_str=self._format_timestamp(self.peak_start_time),
                        zone=self.zone_id,
                        peak_pixels=self.peak_pixels,
                        avg_pixels=round(avg_pixels, 1),
                        baseline_pixels=threshold_value,
                        duration_sec=round(duration, 2),
                        start_frame=self.peak_start_frame,
                        end_frame=frame_num,
                        peak_brightness=round(self.peak_brightness, 1),
                        avg_brightness=round(avg_bright, 1),
                        peak_ratio=round(peak_ratio, 4),
                        avg_ratio=round(avg_ratio, 4),
                        total_zone_pixels=self.total_zone_pixels,
                    )
                    self.events.append(event)

                # Reset state (regardless of whether event was emitted)
                self.is_in_peak = False
                self.peak_pixels = 0
                self.pixel_sum = 0
                self.frame_count = 0
                self.peak_brightness = 0.0
                self.brightness_sum = 0.0
            else:
                # Still in peak - track maximum
                self.peak_pixels = max(self.peak_pixels, pixel_count)
                self.pixel_sum += pixel_count
                self.frame_count += 1
                self.peak_brightness = max(self.peak_brightness, avg_brightness)
                self.brightness_sum += avg_brightness

        return event


class MillStandAnalyzer:
    """
    Analyzes mill stand video for peak detection and R→L counting.
    """

    # Counting states
    STATE_IDLE = "IDLE"
    STATE_AWAITING_LEFT = "AWAITING_LEFT"  # Metal travels R→L

    def __init__(
        self,
        video_path: str,
        config_path: str,
        sequence_timeout: float = 6.0,
        min_travel_time: float = 0.3,
        min_peak_pixels: int = 10000,
        min_peak_ratio: float = None,
        min_peak_duration: float = 0.2,
        brightness_threshold: int = 160,
        saturation_threshold: int = 120,
    ):
        self.video_path = video_path
        self.config = self._load_config(config_path)
        self.sequence_timeout = sequence_timeout
        self.min_travel_time = min_travel_time
        self.min_peak_pixels = min_peak_pixels
        self.min_peak_ratio = min_peak_ratio
        self.min_peak_duration = min_peak_duration
        self.brightness_threshold = brightness_threshold
        self.saturation_threshold = saturation_threshold

        # Zone trackers (initialized after video open with zone pixel totals)
        self.trackers: Dict[str, ZoneTracker] = {}

        # Zone pixel totals (computed from config)
        self.zone_pixel_totals: Dict[str, int] = {}

        # Counting state machine
        self.state = self.STATE_IDLE
        self.pending_right_peak: Optional[PeakEvent] = None
        self.right_peak_end_time: float = 0.0

        # Results
        self.count = 0
        self.count_events: List[CountEvent] = []
        self.timeout_events: List[PeakEvent] = []  # RIGHT peaks that timed out

        # Video properties
        self.cap = None
        self.fps = 25
        self.total_frames = 0
        self.width = 0
        self.height = 0

        # Current frame data (for display)
        self.current_pixels: Dict[str, int] = {"LEFT": 0, "RIGHT": 0}
        self.current_brightness: Dict[str, float] = {"LEFT": 0.0, "RIGHT": 0.0}

    def _load_config(self, config_path: str) -> dict:
        """Load zone configuration from settings.yaml."""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return config.get("mill_stand", {})

    def _get_rotated_box(self, zone: dict) -> np.ndarray:
        """Get the 4 corner points of a rotated rectangle zone."""
        x, y, w, h = zone["x"], zone["y"], zone["width"], zone["height"]
        angle = zone.get("angle", 0)

        center_x = x + w / 2
        center_y = y + h / 2

        rect = ((center_x, center_y), (w, h), angle)
        box = cv2.boxPoints(rect)
        box = np.intp(box)
        return box

    def _analyze_zone(
        self, frame: np.ndarray, zone_config: dict
    ) -> Tuple[int, float, int]:
        """
        Analyze a zone and return pixel count, average brightness, and total zone pixels.

        Uses combined filtering to detect white-hot metal and reject red/orange glare:
        1. High brightness threshold (200+) - white-hot metal is very bright
        2. Low saturation filter - white-hot metal is desaturated, glare is colored

        Returns:
            (bright_pixel_count, avg_brightness_of_bright_pixels, total_zone_pixels)
        """
        # Get zone mask
        box = self._get_rotated_box(zone_config)
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [box], 255)

        # Get pixels within zone
        zone_indices = mask > 0
        total_zone_pixels = int(np.sum(zone_indices))

        if not np.any(zone_indices):
            return 0, 0.0, 0

        # Convert to HSV for saturation analysis
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Get grayscale for brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Extract zone pixels
        zone_brightness = gray[zone_indices]
        zone_saturation = hsv[:, :, 1][zone_indices]

        # Combined filter for white-hot metal:
        # 1. High brightness (> threshold) - white-hot metal is bright
        # 2. Low saturation (< threshold) - white-hot metal is desaturated, red glare is saturated
        white_hot_mask = (zone_brightness > self.brightness_threshold) & (
            zone_saturation < self.saturation_threshold
        )
        bright_pixel_count = int(np.sum(white_hot_mask))

        # Calculate average brightness of white-hot pixels
        if bright_pixel_count > 0:
            avg_brightness = float(np.mean(zone_brightness[white_hot_mask]))
        else:
            avg_brightness = 0.0

        return bright_pixel_count, avg_brightness, total_zone_pixels

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as MM:SS.s"""
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:02d}:{secs:04.1f}"

    def _handle_peak_event(
        self, event: PeakEvent, current_time: float
    ) -> Optional[CountEvent]:
        """
        Handle a peak event and update counting state machine.
        Direction: RIGHT → LEFT (metal travels from right zone to left zone)

        Returns:
            CountEvent if a piece was counted, None otherwise.
        """
        count_event = None

        if event.zone == "RIGHT":
            if self.state == self.STATE_IDLE:
                # RIGHT peak detected - wait for LEFT
                self.state = self.STATE_AWAITING_LEFT
                self.pending_right_peak = event
                self.right_peak_end_time = current_time
            elif self.state == self.STATE_AWAITING_LEFT:
                # Another RIGHT peak while waiting for LEFT - replace pending
                # (This shouldn't happen often, but handle it)
                self.pending_right_peak = event
                self.right_peak_end_time = current_time

        elif event.zone == "LEFT":
            if self.state == self.STATE_AWAITING_LEFT:
                # LEFT peak after RIGHT - check if travel time is valid
                travel_time = (
                    event.timestamp_sec - self.pending_right_peak.timestamp_sec
                )

                if travel_time >= self.min_travel_time:
                    # Valid travel time - count the piece!
                    self.count += 1

                    count_event = CountEvent(
                        count_id=self.count,
                        timestamp_sec=event.timestamp_sec,
                        timestamp_str=event.timestamp_str,
                        right_peak=self.pending_right_peak,
                        left_peak=event,
                        travel_time_sec=round(travel_time, 2),
                    )
                    self.count_events.append(count_event)

                    # Reset state
                    self.state = self.STATE_IDLE
                    self.pending_right_peak = None
                else:
                    # Invalid travel time (too short or negative)
                    # Don't count, but reset state to avoid false matches
                    self.state = self.STATE_IDLE
                    self.pending_right_peak = None

        return count_event

    def _check_timeout(self, current_time: float) -> bool:
        """
        Check if pending RIGHT peak has timed out.

        Returns:
            True if timeout occurred, False otherwise.
        """
        if self.state == self.STATE_AWAITING_LEFT:
            if current_time - self.right_peak_end_time > self.sequence_timeout:
                # Timeout - log and reset
                self.timeout_events.append(self.pending_right_peak)
                self.state = self.STATE_IDLE
                self.pending_right_peak = None
                return True
        return False

    def open_video(self) -> bool:
        """Open video file and get properties."""
        if not Path(self.video_path).exists():
            print(f"Video not found: {self.video_path}")
            return False

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            print(f"Failed to open video: {self.video_path}")
            return False

        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Compute zone pixel totals from config
        zones_config = self.config.get("zones", {})
        for zone_id, zone_key in [("LEFT", "left"), ("RIGHT", "right")]:
            if zone_key in zones_config:
                zone = zones_config[zone_key]
                # Use width * height as approximation (actual rotated rect area)
                self.zone_pixel_totals[zone_id] = zone["width"] * zone["height"]
            else:
                self.zone_pixel_totals[zone_id] = 0

        # Initialize zone trackers now that we know the FPS and zone sizes
        self.trackers = {
            "LEFT": ZoneTracker(
                "LEFT",
                min_peak_pixels=self.min_peak_pixels,
                min_peak_ratio=self.min_peak_ratio,
                total_zone_pixels=self.zone_pixel_totals.get("LEFT", 0),
                min_peak_duration=self.min_peak_duration,
                fps=self.fps,
            ),
            "RIGHT": ZoneTracker(
                "RIGHT",
                min_peak_pixels=self.min_peak_pixels,
                min_peak_ratio=self.min_peak_ratio,
                total_zone_pixels=self.zone_pixel_totals.get("RIGHT", 0),
                min_peak_duration=self.min_peak_duration,
                fps=self.fps,
            ),
        }

        return True

    def draw_overlay(
        self,
        frame: np.ndarray,
        events_this_frame: List,
        count_this_frame: bool,
        timeout_this_frame: bool,
    ) -> np.ndarray:
        """Draw zone overlays and info on frame."""
        zones_config = self.config.get("zones", {})

        # Colors
        colors = {
            "LEFT": (0, 255, 0),  # Green
            "RIGHT": (0, 0, 255),  # Red
        }

        # Draw zones
        for zone_id in ["LEFT", "RIGHT"]:
            zone_key = zone_id.lower()
            if zone_key not in zones_config:
                continue

            zone = zones_config[zone_key]
            box = self._get_rotated_box(zone)
            color = colors[zone_id]
            tracker = self.trackers[zone_id]

            # Check if this zone just had an event
            zone_event = any(
                e.zone == zone_id for e in events_this_frame if isinstance(e, PeakEvent)
            )

            if zone_event:
                # Flash yellow on peak end
                overlay = frame.copy()
                cv2.fillPoly(overlay, [box], (0, 255, 255))
                cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
                thickness = 4
            elif tracker.is_in_peak:
                # Semi-transparent fill while in peak
                overlay = frame.copy()
                cv2.fillPoly(overlay, [box], color)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                thickness = 3
            else:
                thickness = 2

            # Draw outline
            cv2.polylines(frame, [box], True, color, thickness)

            # Draw info label
            top_point = box[np.argmin(box[:, 1])]
            pixels = self.current_pixels[zone_id]

            # Show pixel count and state
            if tracker.is_in_peak:
                label = f"{zone_id} [{pixels:,}px] ACTIVE"
            else:
                label = f"{zone_id} [{pixels:,}px]"
            thresh_label = f"thresh: {tracker._get_threshold_display()}"

            cv2.putText(
                frame,
                label,
                (top_point[0], top_point[1] - 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )
            cv2.putText(
                frame,
                thresh_label,
                (top_point[0], top_point[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (200, 200, 200),
                1,
            )

        # Draw count and state (top right)
        cv2.rectangle(
            frame, (self.width - 300, 10), (self.width - 10, 100), (0, 0, 0), -1
        )

        # Count
        count_color = (0, 255, 255) if count_this_frame else (0, 255, 0)
        cv2.putText(
            frame,
            f"COUNT: {self.count}",
            (self.width - 290, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            count_color,
            2,
        )

        # State
        state_text = self.state
        state_color = (
            (0, 255, 255) if self.state == self.STATE_AWAITING_LEFT else (200, 200, 200)
        )
        cv2.putText(
            frame,
            f"State: {state_text}",
            (self.width - 290, 65),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            state_color,
            1,
        )

        # Timeouts
        cv2.putText(
            frame,
            f"Timeouts: {len(self.timeout_events)}",
            (self.width - 290, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (150, 150, 150),
            1,
        )

        # Flash message if count just happened
        if count_this_frame:
            cv2.putText(
                frame,
                "*** PIECE COUNTED ***",
                (self.width // 2 - 150, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 255),
                3,
            )

        # Flash message if timeout
        if timeout_this_frame:
            cv2.putText(
                frame,
                "[TIMEOUT]",
                (self.width // 2 - 80, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )

        return frame

    def analyze(
        self,
        start_percent: float = 20,
        end_percent: float = 50,
        display: bool = False,
        output_path: str = None,
    ) -> Tuple[List[PeakEvent], List[CountEvent]]:
        """
        Analyze video segment for peaks and counts.

        Args:
            start_percent: Start position as percentage of video (0-100)
            end_percent: End position as percentage of video (0-100)
            display: Show visual output
            output_path: Path to save CSV output

        Returns:
            (all_peak_events, all_count_events)
        """
        if not self.open_video():
            return [], []

        # Calculate frame range
        start_frame = int(self.total_frames * start_percent / 100)
        end_frame = int(self.total_frames * end_percent / 100)

        # Time calculations
        start_time = start_frame / self.fps
        end_time = end_frame / self.fps
        duration = end_time - start_time

        def format_time(seconds):
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins:02d}:{secs:02d}"

        print("=" * 70)
        print("MILL STAND ANALYSIS - Threshold-Based Detection")
        print("=" * 70)
        print(f"Video: {self.video_path}")
        print(f"Resolution: {self.width}x{self.height} @ {self.fps:.1f} FPS")
        print(
            f"Range: {start_percent}% - {end_percent}% ({format_time(start_time)} - {format_time(end_time)})"
        )
        print(
            f"Frames: {start_frame:,} - {end_frame:,} ({end_frame - start_frame:,} frames)"
        )
        print(f"Duration: {format_time(duration)}")

        # Print threshold info
        if self.min_peak_ratio is not None:
            print(
                f"Peak threshold: {self.min_peak_ratio * 100:.1f}% ratio (bright_pixels / total_zone_pixels)"
            )
            print(
                f"  LEFT zone:  {self.zone_pixel_totals.get('LEFT', 0):,} total pixels -> thresh = {int(self.min_peak_ratio * self.zone_pixel_totals.get('LEFT', 0)):,} bright pixels"
            )
            print(
                f"  RIGHT zone: {self.zone_pixel_totals.get('RIGHT', 0):,} total pixels -> thresh = {int(self.min_peak_ratio * self.zone_pixel_totals.get('RIGHT', 0)):,} bright pixels"
            )
        else:
            print(f"Peak threshold: {self.min_peak_pixels:,} pixels (absolute)")

        print(f"Min peak duration: {self.min_peak_duration}s (reject short noise)")
        print(
            f"Color filter: brightness > {self.brightness_threshold} AND saturation < {self.saturation_threshold} (white-hot only)"
        )
        print(f"Sequence timeout: {self.sequence_timeout}s")
        print(f"Min travel time: {self.min_travel_time}s")
        print("=" * 70)
        print()
        print("Starting analysis...")

        # Seek to start
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        # Load zone config
        zones_config = self.config.get("zones", {})

        # Setup display window
        if display:
            cv2.namedWindow("Mill Stand Analysis", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Mill Stand Analysis", 1280, 720)

        # Process frames
        frame_num = start_frame
        all_peak_events = []

        try:
            while frame_num < end_frame:
                ret, frame = self.cap.read()
                if not ret:
                    break

                timestamp = frame_num / self.fps
                events_this_frame = []
                count_this_frame = False
                timeout_this_frame = False

                # Check each zone
                for zone_id in [
                    "RIGHT",
                    "LEFT",
                ]:  # Process RIGHT first for proper state machine flow
                    zone_key = zone_id.lower()
                    if zone_key not in zones_config:
                        continue

                    zone = zones_config[zone_key]
                    pixel_count, avg_brightness, _ = self._analyze_zone(frame, zone)
                    self.current_pixels[zone_id] = pixel_count
                    self.current_brightness[zone_id] = avg_brightness

                    # Update tracker
                    peak_event = self.trackers[zone_id].update(
                        pixel_count, avg_brightness, frame_num, timestamp
                    )

                    if peak_event:
                        events_this_frame.append(peak_event)
                        all_peak_events.append(peak_event)

                        # Print peak event with threshold info
                        ratio_str = (
                            f", ratio: {peak_event.peak_ratio * 100:.1f}%"
                            if peak_event.total_zone_pixels > 0
                            else ""
                        )
                        print(
                            f"[{peak_event.timestamp_str}] {peak_event.zone:5} PEAK: "
                            f"{peak_event.peak_pixels:>7,}px{ratio_str} (dur: {peak_event.duration_sec:.2f}s, "
                            f"bright: {peak_event.peak_brightness:.0f})"
                        )

                        # Handle counting state machine
                        count_event = self._handle_peak_event(peak_event, timestamp)
                        if count_event:
                            count_this_frame = True
                            print(
                                f"          *** PIECE #{count_event.count_id} COUNTED "
                                f"(R→L time: {count_event.travel_time_sec:.2f}s) ***"
                            )

                # Check for timeout
                if self._check_timeout(timestamp):
                    timeout_this_frame = True
                    print(
                        f"          [TIMEOUT] RIGHT peak not followed by LEFT within {self.sequence_timeout}s"
                    )

                # Display
                if display:
                    display_frame = self.draw_overlay(
                        frame.copy(),
                        events_this_frame,
                        count_this_frame,
                        timeout_this_frame,
                    )

                    # Add progress bar
                    progress = (frame_num - start_frame) / (end_frame - start_frame)
                    bar_width = int(self.width * progress)
                    cv2.rectangle(
                        display_frame,
                        (0, self.height - 10),
                        (bar_width, self.height),
                        (0, 255, 0),
                        -1,
                    )

                    # Add timestamp
                    cv2.putText(
                        display_frame,
                        format_time(timestamp),
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (255, 255, 255),
                        2,
                    )

                    cv2.imshow("Mill Stand Analysis", display_frame)

                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        print("\nAnalysis stopped by user")
                        break
                    elif key == ord(" "):
                        print("Paused - press any key to continue")
                        cv2.waitKey(0)

                frame_num += 1

                # Progress update every 10 seconds of video
                if not display and frame_num % (int(self.fps) * 10) == 0:
                    progress_pct = (
                        (frame_num - start_frame) / (end_frame - start_frame) * 100
                    )
                    print(f"  Progress: {progress_pct:.0f}% ({format_time(timestamp)})")

        finally:
            self.cap.release()
            if display:
                cv2.destroyAllWindows()

        # Print summary
        self._print_summary(all_peak_events, duration)

        # Save CSV
        if output_path:
            self._save_csv(all_peak_events, output_path)

        return all_peak_events, self.count_events

    def _print_summary(self, events: List[PeakEvent], duration: float):
        """Print analysis summary."""
        print()
        print("=" * 70)
        print("ANALYSIS SUMMARY")
        print("=" * 70)
        mins = int(duration // 60)
        secs = int(duration % 60)
        print(f"Duration analyzed: {mins}:{secs:02d}")
        print()

        # Peak stats per zone
        for zone_id in ["RIGHT", "LEFT"]:
            zone_events = [e for e in events if e.zone == zone_id]

            print(f"{zone_id} zone peaks: {len(zone_events)}")

            if zone_events:
                peaks = [e.peak_pixels for e in zone_events]
                durations = [e.duration_sec for e in zone_events]
                brightnesses = [e.peak_brightness for e in zone_events]

                print(
                    f"  Peak pixels: min={min(peaks):,}  max={max(peaks):,}  avg={sum(peaks) // len(peaks):,}"
                )
                print(
                    f"  Duration:    min={min(durations):.2f}s  max={max(durations):.2f}s  avg={sum(durations) / len(durations):.2f}s"
                )
                print(
                    f"  Brightness:  min={min(brightnesses):.0f}  max={max(brightnesses):.0f}  avg={sum(brightnesses) / len(brightnesses):.0f}"
                )
            print()

        # Counting stats
        print("-" * 70)
        print(f"PIECES COUNTED: {self.count}")
        print(f"TIMEOUTS (LEFT not followed by RIGHT): {len(self.timeout_events)}")
        print()

        if self.count_events:
            travel_times = [e.travel_time_sec for e in self.count_events]
            print(
                f"R→L travel time: min={min(travel_times):.2f}s  max={max(travel_times):.2f}s  avg={sum(travel_times) / len(travel_times):.2f}s"
            )

        print("=" * 70)

    def _save_csv(self, events: List[PeakEvent], output_path: str):
        """Save events to CSV file."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(
                [
                    "event_type",
                    "timestamp_sec",
                    "timestamp_str",
                    "zone",
                    "peak_pixels",
                    "avg_pixels",
                    "baseline_pixels",
                    "duration_sec",
                    "peak_brightness",
                    "avg_brightness",
                    "start_frame",
                    "end_frame",
                    "count_id",
                    "travel_time_sec",
                ]
            )

            # Combine and sort all events by timestamp
            all_events = []

            # Add peak events
            for e in events:
                all_events.append(("PEAK", e.timestamp_sec, e))

            # Add count events
            for e in self.count_events:
                all_events.append(("COUNT", e.timestamp_sec, e))

            # Add timeout events
            for e in self.timeout_events:
                all_events.append(
                    ("TIMEOUT", e.timestamp_sec + self.sequence_timeout, e)
                )

            # Sort by timestamp
            all_events.sort(key=lambda x: x[1])

            # Write rows
            for event_type, ts, event in all_events:
                if event_type == "PEAK":
                    writer.writerow(
                        [
                            "PEAK",
                            f"{event.timestamp_sec:.2f}",
                            event.timestamp_str,
                            event.zone,
                            event.peak_pixels,
                            event.avg_pixels,
                            event.baseline_pixels,
                            event.duration_sec,
                            event.peak_brightness,
                            event.avg_brightness,
                            event.start_frame,
                            event.end_frame,
                            "",
                            "",
                        ]
                    )
                elif event_type == "COUNT":
                    writer.writerow(
                        [
                            "COUNT",
                            f"{event.timestamp_sec:.2f}",
                            event.timestamp_str,
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            event.count_id,
                            event.travel_time_sec,
                        ]
                    )
                elif event_type == "TIMEOUT":
                    writer.writerow(
                        [
                            "TIMEOUT",
                            f"{event.timestamp_sec:.2f}",
                            event.timestamp_str,
                            "LEFT",
                            event.peak_pixels,
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                        ]
                    )

        print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze mill stand video with dynamic peak detection"
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(PROJECT_ROOT / "recordings" / "mill stand view.mp4"),
        help="Path to video file",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(PROJECT_ROOT / "config" / "settings.yaml"),
        help="Path to config file",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=20,
        help="Start position as percentage (default: 20)",
    )
    parser.add_argument(
        "--end", type=float, default=50, help="End position as percentage (default: 50)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=6.0,
        help="Seconds to wait for RIGHT after LEFT peak (default: 6.0)",
    )
    parser.add_argument(
        "--min-travel-time",
        type=float,
        default=0.3,
        help="Minimum R→L travel time to count as valid piece (default: 0.3)",
    )
    parser.add_argument(
        "--min-peak-pixels",
        type=int,
        default=10000,
        help="Minimum bright pixels to activate peak detection (default: 10000). Ignored if --min-peak-ratio is set.",
    )
    parser.add_argument(
        "--min-peak-ratio",
        type=float,
        default=None,
        help="Minimum ratio (bright_pixels / total_zone_pixels) for peak detection. E.g. 0.12 = 12%%. If set, takes priority over --min-peak-pixels.",
    )
    parser.add_argument(
        "--min-peak-duration",
        type=float,
        default=0.2,
        help="Minimum peak duration in seconds to filter noise (default: 0.2)",
    )
    parser.add_argument(
        "--brightness-threshold",
        type=int,
        default=160,
        help="Minimum brightness for white-hot detection (default: 160)",
    )
    parser.add_argument(
        "--saturation-threshold",
        type=int,
        default=120,
        help="Maximum saturation for white-hot detection (default: 120)",
    )
    parser.add_argument("--display", action="store_true", help="Show visual output")
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "data" / "mill_stand_analysis.csv"),
        help="Output CSV path",
    )

    args = parser.parse_args()

    analyzer = MillStandAnalyzer(
        video_path=args.video,
        config_path=args.config,
        sequence_timeout=args.timeout,
        min_travel_time=args.min_travel_time,
        min_peak_pixels=args.min_peak_pixels,
        min_peak_ratio=args.min_peak_ratio,
        min_peak_duration=args.min_peak_duration,
        brightness_threshold=args.brightness_threshold,
        saturation_threshold=args.saturation_threshold,
    )

    analyzer.analyze(
        start_percent=args.start,
        end_percent=args.end,
        display=args.display,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
