#!/usr/bin/env python3
"""
Mill Stand Line Counter Module
==============================
Counts hot plate pieces passing through mill stands using line-based detection
with majority voting across multiple stands.

Key Features:
- Line-based detection (2 lines per stand: entry + exit)
- Support for N configurable stands
- Majority voting: piece counted only if detected by majority of stands
- Uni-directional counting per stand
- Cross-stand validation to reduce false positives/negatives

Logic:
- Each stand has an entry line and exit line
- A piece is detected at a stand when it crosses entry -> exit in sequence
- Multiple stands track the same piece as it moves through
- Majority voting decides if the piece should be counted
- Example: 2/3 stands detect = counted, 1/3 detect = not counted
"""

import cv2
import numpy as np
import time
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from collections import deque
import math

logger = logging.getLogger(__name__)


@dataclass
class LineConfig:
    """Configuration for a detection line"""

    start: Tuple[int, int]
    end: Tuple[int, int]

    def to_dict(self) -> dict:
        return {"start": list(self.start), "end": list(self.end)}

    @classmethod
    def from_dict(cls, d: dict) -> "LineConfig":
        return cls(start=tuple(d["start"]), end=tuple(d["end"]))


@dataclass
class StandConfig:
    """Configuration for a single mill stand"""

    name: str
    direction: str  # "left_to_right" or "right_to_left"
    entry_line: LineConfig
    exit_line: LineConfig

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "direction": self.direction,
            "entry_line": self.entry_line.to_dict(),
            "exit_line": self.exit_line.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StandConfig":
        return cls(
            name=d["name"],
            direction=d.get("direction", "left_to_right"),
            entry_line=LineConfig.from_dict(d["entry_line"]),
            exit_line=LineConfig.from_dict(d["exit_line"]),
        )


@dataclass
class StandDetection:
    """Represents a piece detection at a single stand"""

    stand_id: str
    stand_index: int
    timestamp: float
    entry_time: float
    exit_time: float
    travel_time: float  # entry -> exit time
    entry_pixels: int
    exit_pixels: int
    entry_brightness: float
    exit_brightness: float
    entry_frames: int
    exit_frames: int
    confidence: float


@dataclass
class VotingWindow:
    """Tracks detections across stands for majority voting"""

    window_id: int
    start_time: float
    detections: List[StandDetection] = field(default_factory=list)
    finalized: bool = False

    def add_detection(self, detection: StandDetection):
        # Don't add duplicate detections from same stand
        existing_stands = {d.stand_id for d in self.detections}
        if detection.stand_id not in existing_stands:
            self.detections.append(detection)

    def get_stands_detected(self) -> List[str]:
        return [d.stand_id for d in self.detections]

    def get_vote_result(
        self, total_stands: int, min_required: Optional[int] = None
    ) -> bool:
        if min_required is None:
            min_required = math.ceil(total_stands / 2)
        return len(self.detections) >= min_required


@dataclass
class PieceCount:
    """Final counted piece after majority voting"""

    count_id: int
    timestamp: float
    stands_detected: List[str]
    total_stands: int
    vote_ratio: str  # e.g., "2/3"
    avg_travel_time: float
    avg_confidence: float
    detections: List[StandDetection] = field(default_factory=list)


class Stand:
    """
    Represents a single mill stand with entry/exit line detection.

    Detection logic:
    1. Entry line triggers first (with consecutive frame confirmation)
    2. Exit line triggers second (completes the detection)
    3. Sequence must complete within timeout
    """

    def __init__(
        self,
        stand_id: str,
        index: int,
        config: StandConfig,
        counting_config: dict,
    ):
        self.stand_id = stand_id
        self.index = index
        self.config = config
        self.name = config.name
        self.direction = config.direction

        # Store ORIGINAL line coordinates (will be scaled later)
        self.original_entry_line = (config.entry_line.start, config.entry_line.end)
        self.original_exit_line = (config.exit_line.start, config.exit_line.end)

        # Scaled line coordinates (set after resolution is known)
        self.entry_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
        self.exit_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None

        # Detection parameters from counting config
        self.luminosity_threshold = counting_config.get("luminosity_threshold", 160)
        self.min_bright_pixels = counting_config.get("min_bright_pixels", 100)
        self.sequence_timeout = counting_config.get("sequence_timeout", 3.0)
        self.min_travel_time = counting_config.get("min_travel_time", 0.2)
        self.min_consecutive_frames = counting_config.get("min_consecutive_frames", 2)
        self.line_thickness = counting_config.get("line_thickness", 10)
        self.debounce_time = counting_config.get("debounce_time", 0.3)

        # Hot metal color filter (disabled by default)
        self.hot_metal_filter_enabled = counting_config.get(
            "hot_metal_filter_enabled", False
        )
        self.min_saturation = counting_config.get("min_saturation", 20)
        self.min_red_dominance = counting_config.get("min_red_dominance", 1.1)
        self.min_warmth_ratio = counting_config.get("min_warmth_ratio", 1.05)

        # Line masks (created on first frame)
        self.entry_mask: Optional[np.ndarray] = None
        self.exit_mask: Optional[np.ndarray] = None
        self.frame_shape: Optional[Tuple[int, int]] = None
        self.lines_scaled = False

        # Detection state
        self.entry_consecutive_frames = 0
        self.exit_consecutive_frames = 0
        self.entry_confirmed = False
        self.exit_confirmed = False
        self.entry_last_trigger = 0.0
        self.exit_last_trigger = 0.0

        # Stats for current detection
        self.entry_stats = {"max_pixels": 0, "brightness_sum": 0.0, "frame_count": 0}
        self.exit_stats = {"max_pixels": 0, "brightness_sum": 0.0, "frame_count": 0}

        # Pending sequence (entry confirmed, waiting for exit)
        self.pending_entry: Optional[dict] = None

        # Reverse-order guard (exit confirmed before entry)
        self.reverse_blocked = False
        self.reverse_blocked_time = 0.0

        # Count for this stand (internal tracking)
        self.detection_count = 0

    def scale_lines(
        self,
        original_resolution: Tuple[int, int],
        target_resolution: Tuple[int, int],
    ):
        """Scale line coordinates from original to target resolution."""
        if self.lines_scaled:
            return

        orig_w, orig_h = original_resolution
        target_w, target_h = target_resolution

        scale_x = target_w / orig_w
        scale_y = target_h / orig_h

        def scale_point(p: Tuple[int, int]) -> Tuple[int, int]:
            return (int(p[0] * scale_x), int(p[1] * scale_y))

        self.entry_line = (
            scale_point(self.original_entry_line[0]),
            scale_point(self.original_entry_line[1]),
        )
        self.exit_line = (
            scale_point(self.original_exit_line[0]),
            scale_point(self.original_exit_line[1]),
        )

        self.lines_scaled = True
        logger.debug(
            f"Stand '{self.name}' lines scaled: "
            f"entry {self.original_entry_line} -> {self.entry_line}, "
            f"exit {self.original_exit_line} -> {self.exit_line}"
        )

    def _create_line_mask(
        self, line: Tuple[Tuple[int, int], Tuple[int, int]], shape: Tuple[int, int]
    ) -> np.ndarray:
        """Create a mask for pixels along a line"""
        mask = np.zeros(shape[:2], dtype=np.uint8)
        start, end = line
        cv2.line(mask, start, end, 255, self.line_thickness)
        return mask

    def _init_masks(self, frame_shape: Tuple[int, int]):
        """Initialize line masks based on frame size (must call scale_lines first)"""
        if not self.lines_scaled:
            logger.warning(
                f"Stand '{self.name}': scale_lines() must be called before _init_masks()"
            )
            return

        if self.frame_shape != frame_shape:
            self.frame_shape = frame_shape
            self.entry_mask = self._create_line_mask(self.entry_line, frame_shape)
            self.exit_mask = self._create_line_mask(self.exit_line, frame_shape)
            logger.debug(
                f"Stand '{self.name}': initialized masks for {frame_shape[1]}x{frame_shape[0]}"
            )

    def _check_line(
        self,
        gray: np.ndarray,
        mask: np.ndarray,
        line: Tuple[Tuple[int, int], Tuple[int, int]],
        frame_bgr: Optional[np.ndarray] = None,
    ) -> Tuple[bool, int, float]:
        """
        Check if hot material is crossing a line.

        Returns:
            (is_triggered, pixel_count, avg_brightness)
        """
        # Get pixels on the line
        line_pixels = gray[mask > 0]

        if len(line_pixels) == 0:
            return False, 0, 0.0

        # Count bright pixels
        bright_mask = line_pixels > self.luminosity_threshold
        bright_pixels = int(np.sum(bright_mask))
        avg_brightness = (
            float(np.mean(line_pixels[bright_mask])) if bright_pixels > 0 else 0.0
        )

        # Basic trigger check
        if bright_pixels < self.min_bright_pixels:
            return False, bright_pixels, avg_brightness

        # Hot metal color filter
        if frame_bgr is not None and self.hot_metal_filter_enabled:
            is_hot_metal = self._check_hot_metal_color(frame_bgr, line)
            if not is_hot_metal:
                return False, bright_pixels, avg_brightness

        return True, bright_pixels, avg_brightness

    def _check_hot_metal_color(
        self,
        frame_bgr: np.ndarray,
        line: Tuple[Tuple[int, int], Tuple[int, int]],
    ) -> bool:
        """Check if the bright region has hot metal color characteristics"""
        start, end = line
        padding = 30

        min_x = max(0, min(start[0], end[0]) - padding)
        max_x = min(frame_bgr.shape[1], max(start[0], end[0]) + padding)
        min_y = max(0, min(start[1], end[1]) - padding)
        max_y = min(frame_bgr.shape[0], max(start[1], end[1]) + padding)

        roi_bgr = frame_bgr[min_y:max_y, min_x:max_x]
        if roi_bgr.size == 0:
            return True

        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        bright_mask = roi_gray > self.luminosity_threshold

        if np.sum(bright_mask) < 10:
            return True

        bright_pixels_bgr = roi_bgr[bright_mask]

        avg_b = float(np.mean(bright_pixels_bgr[:, 0]))
        avg_g = float(np.mean(bright_pixels_bgr[:, 1]))
        avg_r = float(np.mean(bright_pixels_bgr[:, 2]))

        red_dominance = avg_r / max(avg_b, 1.0)
        warmth_ratio = (avg_r + avg_g) / max(2.0 * avg_b, 1.0)

        roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        bright_pixels_hsv = roi_hsv[bright_mask]
        avg_saturation = float(np.mean(bright_pixels_hsv[:, 1]))

        is_hot_metal = (
            red_dominance >= self.min_red_dominance
            and avg_saturation >= self.min_saturation
            and warmth_ratio >= self.min_warmth_ratio
        )

        if not is_hot_metal:
            logger.debug(
                f"Stand '{self.name}' COLOR FILTERED: R/B={red_dominance:.2f}, "
                f"sat={avg_saturation:.1f}, warmth={warmth_ratio:.2f}"
            )

        return is_hot_metal

    def process_frame(
        self,
        gray: np.ndarray,
        frame_bgr: np.ndarray,
        current_time: float,
    ) -> Tuple[Optional[StandDetection], Dict]:
        """
        Process a frame for this stand.

        Returns:
            (detection or None, status_dict)
        """
        self._init_masks(gray.shape)

        # Check entry line
        entry_triggered, entry_pixels, entry_brightness = self._check_line(
            gray, self.entry_mask, self.entry_line, frame_bgr
        )

        # Check exit line
        exit_triggered, exit_pixels, exit_brightness = self._check_line(
            gray, self.exit_mask, self.exit_line, frame_bgr
        )

        detection = None

        # Track entry line consecutive frames
        if entry_triggered:
            self.entry_consecutive_frames += 1
            self.entry_stats["max_pixels"] = max(
                self.entry_stats["max_pixels"], entry_pixels
            )
            self.entry_stats["brightness_sum"] += entry_brightness
            self.entry_stats["frame_count"] += 1
        else:
            if self.entry_consecutive_frames > 0:
                self.entry_consecutive_frames = 0
                self.entry_confirmed = False
                self.entry_stats = {
                    "max_pixels": 0,
                    "brightness_sum": 0.0,
                    "frame_count": 0,
                }

        # Track exit line consecutive frames
        if exit_triggered:
            self.exit_consecutive_frames += 1
            self.exit_stats["max_pixels"] = max(
                self.exit_stats["max_pixels"], exit_pixels
            )
            self.exit_stats["brightness_sum"] += exit_brightness
            self.exit_stats["frame_count"] += 1
        else:
            if self.exit_consecutive_frames > 0:
                self.exit_consecutive_frames = 0
                self.exit_confirmed = False
                self.exit_stats = {
                    "max_pixels": 0,
                    "brightness_sum": 0.0,
                    "frame_count": 0,
                }

        # Check entry confirmation (rising edge)
        entry_is_confirmed = (
            self.entry_consecutive_frames >= self.min_consecutive_frames
        )
        entry_time_since_last = current_time - self.entry_last_trigger

        if (
            entry_is_confirmed
            and not self.entry_confirmed
            and entry_time_since_last > self.debounce_time
        ):
            if self.reverse_blocked:
                logger.debug(
                    f"Stand '{self.name}' entry ignored (exit confirmed first)"
                )
            else:
                self.entry_confirmed = True
                self.entry_last_trigger = current_time

                avg_brightness = (
                    self.entry_stats["brightness_sum"] / self.entry_stats["frame_count"]
                    if self.entry_stats["frame_count"] > 0
                    else 0
                )

                # Start pending sequence
                self.pending_entry = {
                    "entry_time": current_time,
                    "entry_frames": self.entry_consecutive_frames,
                    "entry_pixels": self.entry_stats["max_pixels"],
                    "entry_brightness": avg_brightness,
                }
                logger.debug(
                    f"Stand '{self.name}' ENTRY confirmed "
                    f"({self.entry_consecutive_frames} frames, {self.entry_stats['max_pixels']} px)"
                )

        # Check exit confirmation (rising edge) - only if we have pending entry
        exit_is_confirmed = self.exit_consecutive_frames >= self.min_consecutive_frames
        exit_time_since_last = current_time - self.exit_last_trigger

        if (
            exit_is_confirmed
            and not self.exit_confirmed
            and exit_time_since_last > self.debounce_time
        ):
            if self.pending_entry is None:
                self.exit_confirmed = True
                self.exit_last_trigger = current_time
                self.reverse_blocked = True
                self.reverse_blocked_time = current_time
                logger.debug(
                    f"Stand '{self.name}' exit confirmed before entry - blocking reverse"
                )
            else:
                self.exit_confirmed = True
                self.exit_last_trigger = current_time

                entry_time = self.pending_entry["entry_time"]
                travel_time = current_time - entry_time

                # Validate timing
                if (
                    travel_time >= self.min_travel_time
                    and travel_time <= self.sequence_timeout
                ):
                    self.detection_count += 1

                    avg_exit_brightness = (
                        self.exit_stats["brightness_sum"]
                        / self.exit_stats["frame_count"]
                        if self.exit_stats["frame_count"] > 0
                        else 0
                    )

                    # Calculate confidence
                    confidence = self._calculate_confidence(
                        self.pending_entry["entry_frames"],
                        self.exit_consecutive_frames,
                        self.pending_entry["entry_pixels"],
                        self.exit_stats["max_pixels"],
                    )

                    detection = StandDetection(
                        stand_id=self.stand_id,
                        stand_index=self.index,
                        timestamp=current_time,
                        entry_time=entry_time,
                        exit_time=current_time,
                        travel_time=travel_time,
                        entry_pixels=self.pending_entry["entry_pixels"],
                        exit_pixels=self.exit_stats["max_pixels"],
                        entry_brightness=self.pending_entry["entry_brightness"],
                        exit_brightness=avg_exit_brightness,
                        entry_frames=self.pending_entry["entry_frames"],
                        exit_frames=self.exit_consecutive_frames,
                        confidence=confidence,
                    )

                    logger.info(
                        f"Stand '{self.name}' DETECTION #{self.detection_count} | "
                        f"Travel: {travel_time:.2f}s | Conf: {confidence:.0f}%"
                    )
                else:
                    reason = (
                        "too fast" if travel_time < self.min_travel_time else "timeout"
                    )
                    logger.debug(
                        f"Stand '{self.name}' sequence rejected - {reason}: {travel_time:.2f}s"
                    )

                # Clear pending entry
                self.pending_entry = None

        # Clear stale pending entries
        if self.pending_entry is not None:
            age = current_time - self.pending_entry["entry_time"]
            if age > self.sequence_timeout:
                logger.debug(
                    f"Stand '{self.name}' pending entry expired (age={age:.1f}s)"
                )
                self.pending_entry = None

        # Clear reverse block once exit is no longer active
        if not exit_triggered and self.reverse_blocked:
            self.reverse_blocked = False

        status = {
            "entry_triggered": entry_triggered,
            "exit_triggered": exit_triggered,
            "entry_pixels": entry_pixels,
            "exit_pixels": exit_pixels,
            "entry_confirmed": self.entry_confirmed,
            "exit_confirmed": self.exit_confirmed,
            "entry_consecutive": self.entry_consecutive_frames,
            "exit_consecutive": self.exit_consecutive_frames,
            "pending": self.pending_entry is not None,
            "reverse_blocked": self.reverse_blocked,
            "detection_count": self.detection_count,
        }

        return detection, status

    def _calculate_confidence(
        self,
        entry_frames: int,
        exit_frames: int,
        entry_pixels: int,
        exit_pixels: int,
    ) -> float:
        """Calculate detection confidence score"""
        confidence = 50.0

        min_frames = min(entry_frames, exit_frames)
        if min_frames >= 4:
            confidence += 25.0
        elif min_frames >= 3:
            confidence += 20.0
        elif min_frames >= 2:
            confidence += 10.0

        avg_pixels = (entry_pixels + exit_pixels) / 2
        if avg_pixels > 200:
            confidence += 25.0
        elif avg_pixels > 150:
            confidence += 15.0
        elif avg_pixels > 100:
            confidence += 10.0

        return min(100.0, confidence)

    def reset(self):
        """Reset stand state"""
        self.entry_consecutive_frames = 0
        self.exit_consecutive_frames = 0
        self.entry_confirmed = False
        self.exit_confirmed = False
        self.entry_stats = {"max_pixels": 0, "brightness_sum": 0.0, "frame_count": 0}
        self.exit_stats = {"max_pixels": 0, "brightness_sum": 0.0, "frame_count": 0}
        self.pending_entry = None
        self.detection_count = 0


class MillStandLineCounter:
    """
    Line-based piece counter with majority voting across multiple mill stands.

    Detection Logic:
    - Each stand has entry/exit lines
    - A piece is detected at a stand when entry->exit sequence completes
    - Majority voting: piece counted only if detected by majority of stands
    - Example: 2/3 stands detect = COUNT, 1/3 detect = IGNORE

    This approach handles:
    - False positives: noise on one stand won't count (needs majority)
    - False negatives: one stand missing won't prevent count (majority still passes)
    """

    def __init__(
        self,
        stands_config: List[dict],
        counting_config: Optional[dict] = None,
        voting_config: Optional[dict] = None,
        target_resolution: Optional[Tuple[int, int]] = None,
    ):
        """
        Initialize mill stand line counter.

        Args:
            stands_config: List of stand configurations
            counting_config: Detection thresholds and parameters
            voting_config: Majority voting parameters
            target_resolution: Resolution to downscale frames to (width, height)
        """
        counting_config = counting_config or {}
        voting_config = voting_config or {}

        # Target resolution for processing
        self.target_resolution = target_resolution or tuple(
            counting_config.get("target_resolution", [704, 576])
        )
        self.original_resolution: Optional[Tuple[int, int]] = None

        # Initialize stands
        self.stands: List[Stand] = []
        for i, stand_cfg in enumerate(stands_config):
            stand_config = StandConfig.from_dict(stand_cfg)
            stand_id = f"stand_{i + 1}"
            stand = Stand(stand_id, i, stand_config, counting_config)
            self.stands.append(stand)

        self.num_stands = len(self.stands)

        # Voting configuration
        self.voting_window_seconds = voting_config.get("window_seconds", 5.0)
        self.min_stands_required = voting_config.get("min_stands_required", None)
        if self.min_stands_required is None:
            self.min_stands_required = math.ceil(self.num_stands / 2)

        # Voting windows (active voting sessions)
        self.voting_windows: deque = deque(maxlen=50)
        self.next_window_id = 1

        # Counting
        self.total_count = 0
        self.counted_pieces: List[PieceCount] = []

        # Frame tracking
        self.frame_count = 0
        self.initialized = False

        logger.info(f"MillStandLineCounter initialized:")
        logger.info(f"  Stands: {self.num_stands}")
        for stand in self.stands:
            logger.info(f"    - {stand.name} ({stand.direction})")
        logger.info(f"  Voting: {self.min_stands_required}/{self.num_stands} required")
        logger.info(f"  Voting window: {self.voting_window_seconds}s")
        logger.info(f"  Target resolution: {self.target_resolution}")

    def _init_resolution(self, frame: np.ndarray):
        """Initialize based on frame resolution"""
        if self.initialized:
            return

        orig_h, orig_w = frame.shape[:2]
        self.original_resolution = (orig_w, orig_h)

        # Scale line coordinates for all stands from original to target resolution
        for stand in self.stands:
            stand.scale_lines(self.original_resolution, self.target_resolution)

        self.initialized = True

        logger.info(
            f"Initialized for resolution {orig_w}x{orig_h} -> {self.target_resolution}"
        )

    def _find_or_create_voting_window(
        self,
        detection: StandDetection,
        current_time: float,
    ) -> VotingWindow:
        """
        Find an existing voting window for this detection or create a new one.

        A detection belongs to an existing window if:
        - The window is not finalized
        - The detection time is within the voting window duration
        - The stand hasn't already been recorded in this window
        """
        # Look for existing compatible window
        for window in self.voting_windows:
            if window.finalized:
                continue

            window_age = current_time - window.start_time
            if window_age > self.voting_window_seconds:
                continue

            # Check if this stand already voted
            existing_stands = {d.stand_id for d in window.detections}
            if detection.stand_id in existing_stands:
                continue

            # Compatible window found
            return window

        # Create new window
        window = VotingWindow(
            window_id=self.next_window_id,
            start_time=current_time,
            detections=[],
        )
        self.next_window_id += 1
        self.voting_windows.append(window)

        return window

    def _process_voting_windows(self, current_time: float) -> Optional[PieceCount]:
        """
        Process voting windows and finalize counts.

        Returns the most recent counted piece if any.
        """
        counted_piece = None

        for window in list(self.voting_windows):
            if window.finalized:
                continue

            window_age = current_time - window.start_time

            # Window expired - time to vote
            if window_age >= self.voting_window_seconds:
                window.finalized = True

                vote_passed = window.get_vote_result(
                    self.num_stands, self.min_stands_required
                )

                stands_detected = window.get_stands_detected()
                vote_ratio = f"{len(stands_detected)}/{self.num_stands}"

                if vote_passed:
                    self.total_count += 1

                    # Calculate averages from detections
                    avg_travel = np.mean([d.travel_time for d in window.detections])
                    avg_confidence = np.mean([d.confidence for d in window.detections])

                    counted_piece = PieceCount(
                        count_id=self.total_count,
                        timestamp=current_time,
                        stands_detected=stands_detected,
                        total_stands=self.num_stands,
                        vote_ratio=vote_ratio,
                        avg_travel_time=float(avg_travel),
                        avg_confidence=float(avg_confidence),
                        detections=list(window.detections),
                    )
                    self.counted_pieces.append(counted_piece)

                    logger.info(
                        f"*** PIECE #{self.total_count} COUNTED | "
                        f"Vote: {vote_ratio} | "
                        f"Stands: {', '.join(stands_detected)} | "
                        f"Avg travel: {avg_travel:.2f}s ***"
                    )
                else:
                    logger.debug(
                        f"Voting window {window.window_id} failed: {vote_ratio} "
                        f"(need {self.min_stands_required})"
                    )

        # Clean up old finalized windows
        while self.voting_windows and self.voting_windows[0].finalized:
            old_window = self.voting_windows[0]
            window_age = current_time - old_window.start_time
            if window_age > self.voting_window_seconds * 2:
                self.voting_windows.popleft()
            else:
                break

        return counted_piece

    def process_frame(
        self,
        frame: np.ndarray,
    ) -> Tuple[Optional[PieceCount], Dict]:
        """
        Process a frame and check for piece crossings.

        Args:
            frame: BGR frame from camera/video (original resolution)

        Returns:
            (counted_piece or None, status dict)
        """
        self.frame_count += 1
        self._init_resolution(frame)

        current_time = time.time()

        # Downscale frame to target resolution
        resized = cv2.resize(
            frame, self.target_resolution, interpolation=cv2.INTER_AREA
        )
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        # Process each stand
        status = {"stands": {}}

        for stand in self.stands:
            detection, stand_status = stand.process_frame(gray, resized, current_time)
            status["stands"][stand.stand_id] = stand_status

            if detection is not None:
                # Find or create voting window and add detection
                window = self._find_or_create_voting_window(detection, current_time)
                window.add_detection(detection)
                logger.debug(
                    f"Added detection from '{stand.name}' to voting window {window.window_id}"
                )

        # Process voting windows
        counted_piece = self._process_voting_windows(current_time)

        # Build overall status
        status["total_count"] = self.total_count
        status["active_voting_windows"] = sum(
            1 for w in self.voting_windows if not w.finalized
        )
        status["frame_count"] = self.frame_count

        return counted_piece, status

    def draw_overlay(self, frame: np.ndarray, status: Dict) -> np.ndarray:
        """Draw detection lines and status on frame."""
        # Work on downscaled frame
        overlay = cv2.resize(
            frame, self.target_resolution, interpolation=cv2.INTER_AREA
        )

        # Colors for different stands
        stand_colors = [
            (0, 255, 0),  # Green
            (0, 255, 255),  # Yellow
            (0, 165, 255),  # Orange
            (255, 0, 255),  # Magenta
            (255, 255, 0),  # Cyan
        ]

        # Draw lines for each stand
        for i, stand in enumerate(self.stands):
            color = stand_colors[i % len(stand_colors)]
            stand_status = status.get("stands", {}).get(stand.stand_id, {})

            # Entry line
            entry_thickness = 3 if stand_status.get("entry_triggered") else 2
            entry_color = (
                tuple(min(255, c + 100) for c in color)
                if stand_status.get("entry_triggered")
                else color
            )
            cv2.line(
                overlay,
                stand.entry_line[0],
                stand.entry_line[1],
                entry_color,
                entry_thickness,
            )

            # Exit line
            exit_thickness = 3 if stand_status.get("exit_triggered") else 2
            exit_color = (
                tuple(min(255, c + 100) for c in color)
                if stand_status.get("exit_triggered")
                else color
            )
            cv2.line(
                overlay,
                stand.exit_line[0],
                stand.exit_line[1],
                exit_color,
                exit_thickness,
            )

            # Stand label
            label_pos = (
                min(stand.entry_line[0][0], stand.exit_line[0][0]),
                min(stand.entry_line[0][1], stand.exit_line[0][1]) - 10,
            )
            label = f"{stand.name}"
            if stand_status.get("pending"):
                label += " [PENDING]"
            cv2.putText(
                overlay, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
            )

            # Detection count for this stand
            count_text = f"#{stand_status.get('detection_count', 0)}"
            count_pos = (
                max(stand.entry_line[1][0], stand.exit_line[1][0]) + 5,
                max(stand.entry_line[1][1], stand.exit_line[1][1]),
            )
            cv2.putText(
                overlay, count_text, count_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1
            )

        # Draw count info (top right)
        frame_w = overlay.shape[1]
        box_width = 220
        box_x = frame_w - box_width - 5
        cv2.rectangle(overlay, (box_x, 5), (frame_w - 5, 105), (0, 0, 0), -1)

        cv2.putText(
            overlay,
            f"COUNT: {self.total_count}",
            (box_x + 5, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            overlay,
            f"Voting: {self.min_stands_required}/{self.num_stands} required",
            (box_x + 5, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (200, 200, 200),
            1,
        )
        cv2.putText(
            overlay,
            f"Active windows: {status.get('active_voting_windows', 0)}",
            (box_x + 5, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (200, 200, 200),
            1,
        )
        cv2.putText(
            overlay,
            f"Frame: {status.get('frame_count', 0)}",
            (box_x + 5, 95),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (150, 150, 150),
            1,
        )

        return overlay

    def get_stats(self) -> Dict:
        """Get counting statistics"""
        if not self.counted_pieces:
            return {
                "total_count": 0,
                "avg_travel_time": 0,
                "avg_confidence": 0,
                "stand_detection_counts": {s.stand_id: 0 for s in self.stands},
            }

        travel_times = [p.avg_travel_time for p in self.counted_pieces]
        confidences = [p.avg_confidence for p in self.counted_pieces]

        # Count per-stand detections
        stand_counts = {s.stand_id: 0 for s in self.stands}
        for piece in self.counted_pieces:
            for stand_id in piece.stands_detected:
                stand_counts[stand_id] += 1

        return {
            "total_count": self.total_count,
            "avg_travel_time": float(np.mean(travel_times)),
            "min_travel_time": float(np.min(travel_times)),
            "max_travel_time": float(np.max(travel_times)),
            "avg_confidence": float(np.mean(confidences)),
            "stand_detection_counts": stand_counts,
        }

    def reset(self):
        """Reset counter state"""
        self.total_count = 0
        self.counted_pieces = []
        self.voting_windows.clear()
        self.next_window_id = 1
        self.frame_count = 0

        for stand in self.stands:
            stand.reset()

        logger.info("MillStandLineCounter reset")
