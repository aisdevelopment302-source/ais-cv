#!/usr/bin/env python3
"""
Mill Stand Counter Module
=========================
Counts hot plate pieces passing through the mill stand using bi-directional detection.

Logic:
- Two detection zones: LEFT and RIGHT around the mill stand
- Pieces can travel in either direction (left-to-right or right-to-left)
- Entry zone triggers first, exit zone confirms the count
- Relaxed thresholds compared to conveyor (cleaner detection environment)

Key Differences from PlateCounter:
- Zone-based detection (rectangles) instead of 3-line sequential detection
- Bi-directional counting (pieces can go either way)
- No human filter (workers are far from detection zones)
- Built-in frame downscaling for performance
"""

import cv2
import numpy as np
import time
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class ZoneDetection:
    """Represents a detection event in a zone"""

    zone_id: str  # 'LEFT' or 'RIGHT'
    timestamp: float  # When zone was triggered
    brightness: float  # Average brightness of detected pixels
    pixel_count: int  # Number of bright pixels
    frame_count: int = 1  # Consecutive frames detected


@dataclass
class MillStandPieceCount:
    """Represents a counted piece from mill stand"""

    count_id: int
    timestamp: float
    direction: str  # 'LEFT_TO_RIGHT' or 'RIGHT_TO_LEFT'
    entry_zone: str  # Which zone triggered first ('LEFT' or 'RIGHT')
    exit_zone: str  # Which zone triggered second (completed count)
    entry_time: float
    exit_time: float
    travel_time: float  # Time from entry to exit
    confidence: float
    # Metadata for debugging/analysis
    entry_frames: int = 0
    exit_frames: int = 0
    entry_max_pixels: int = 0
    exit_max_pixels: int = 0
    entry_avg_brightness: float = 0.0
    exit_avg_brightness: float = 0.0


class MillStandCounter:
    """
    Bi-directional piece counter for mill stand camera view.

    Detection Logic:
    - Two detection zones: LEFT and RIGHT
    - Pieces can travel either direction through the mill stand
    - When LEFT zone triggers first -> piece moving left-to-right
    - When RIGHT zone triggers first -> piece moving right-to-left
    - Count is recorded when the opposite zone triggers (exit)

    vs PlateCounter differences:
    - Zone-based (rectangles) instead of line-based
    - Bi-directional tracking
    - No human filter (workers far from detection zones)
    - Relaxed color filter thresholds
    - Built-in frame downscaling
    """

    def __init__(
        self,
        zones_config: dict,
        counting_config: Optional[dict] = None,
        luminosity_threshold: int = 160,
        min_bright_pixels: int = 100,
        sequence_timeout: float = 6.0,
        min_travel_time: float = 0.3,
        min_consecutive_frames: int = 2,
        hot_metal_filter_enabled: bool = True,
        min_saturation: float = 20,
        min_red_dominance: float = 1.1,
        min_warmth_ratio: float = 1.05,
        target_resolution: tuple = (704, 576),
    ):
        """
        Initialize mill stand counter.

        Args:
            zones_config: Dict with 'left' and 'right' zone definitions
                          Each zone has: x, y, width, height
            counting_config: Optional dict with threshold overrides from settings.yaml
            luminosity_threshold: Brightness threshold for hot metal (0-255)
            min_bright_pixels: Minimum bright pixels in zone to count as detection
            sequence_timeout: Maximum seconds for piece to travel entry->exit
            min_travel_time: Minimum seconds for entry->exit (filters noise)
            min_consecutive_frames: Minimum consecutive frames to confirm detection
            hot_metal_filter_enabled: Enable color-based filtering
            min_saturation: Minimum HSV saturation for hot metal
            min_red_dominance: Minimum R/B ratio for hot metal
            min_warmth_ratio: Minimum warmth ratio for hot colors
            target_resolution: Resolution to downscale frames to (width, height)
        """
        # Override defaults with counting_config if provided
        if counting_config:
            luminosity_threshold = counting_config.get(
                "luminosity_threshold", luminosity_threshold
            )
            min_bright_pixels = counting_config.get(
                "min_bright_pixels", min_bright_pixels
            )
            sequence_timeout = counting_config.get("sequence_timeout", sequence_timeout)
            min_travel_time = counting_config.get("min_travel_time", min_travel_time)
            min_consecutive_frames = counting_config.get(
                "min_consecutive_frames", min_consecutive_frames
            )
            hot_metal_filter_enabled = counting_config.get(
                "hot_metal_filter_enabled", hot_metal_filter_enabled
            )
            min_saturation = counting_config.get("min_saturation", min_saturation)
            min_red_dominance = counting_config.get(
                "min_red_dominance", min_red_dominance
            )
            min_warmth_ratio = counting_config.get("min_warmth_ratio", min_warmth_ratio)
            # Handle target_resolution as list or tuple
            target_res = counting_config.get("target_resolution", target_resolution)
            if isinstance(target_res, list):
                target_resolution = tuple(target_res)
            else:
                target_resolution = target_res

        # Store original zone config (in original video resolution)
        self.original_zones_config = zones_config
        self.target_resolution = target_resolution
        self.original_resolution: Optional[Tuple[int, int]] = None

        # Zone coordinates will be set on first frame (after knowing original resolution)
        self.zones: Dict[str, Dict] = {}

        # Detection parameters
        self.luminosity_threshold = luminosity_threshold
        self.min_bright_pixels = min_bright_pixels
        self.sequence_timeout = sequence_timeout
        self.min_travel_time = min_travel_time
        self.min_consecutive_frames = min_consecutive_frames

        # Hot metal color filter settings
        self.hot_metal_filter_enabled = hot_metal_filter_enabled
        self.min_saturation = min_saturation
        self.min_red_dominance = min_red_dominance
        self.min_warmth_ratio = min_warmth_ratio

        # Detection state for each zone
        self.zone_consecutive_frames: Dict[str, int] = {"LEFT": 0, "RIGHT": 0}
        self.zone_confirmed: Dict[str, bool] = {"LEFT": False, "RIGHT": False}
        self.zone_last_trigger: Dict[str, float] = {"LEFT": 0, "RIGHT": 0}
        self.zone_stats: Dict[str, Dict] = {
            "LEFT": {"max_pixels": 0, "brightness_sum": 0.0, "frame_count": 0},
            "RIGHT": {"max_pixels": 0, "brightness_sum": 0.0, "frame_count": 0},
        }

        # Pending sequences (pieces that entered one zone, waiting for exit)
        self.pending_sequences: deque = deque(maxlen=20)

        # Counting
        self.total_count: int = 0
        self.counted_pieces: List[MillStandPieceCount] = []

        # Direction counts
        self.left_to_right_count: int = 0
        self.right_to_left_count: int = 0

        # Debounce - prevent rapid re-triggers on same zone
        self.debounce_time: float = 0.5  # seconds

        # Frame tracking
        self.frame_count: int = 0
        self.initialized: bool = False

        logger.info(f"MillStandCounter initialized:")
        logger.info(f"  Target resolution: {target_resolution}")
        logger.info(
            f"  Thresholds: brightness>{luminosity_threshold}, min_pixels>{min_bright_pixels}"
        )
        logger.info(
            f"  Timing: timeout={sequence_timeout}s, min_travel={min_travel_time}s"
        )
        logger.info(
            f"  Color filter: {'enabled' if hot_metal_filter_enabled else 'disabled'}"
        )

    def _init_zones(self, frame: np.ndarray):
        """Initialize zone coordinates based on frame size."""
        if self.initialized:
            return

        # Get original frame resolution
        orig_h, orig_w = frame.shape[:2]
        self.original_resolution = (orig_w, orig_h)

        # Calculate scale factors
        target_w, target_h = self.target_resolution
        scale_x = target_w / orig_w
        scale_y = target_h / orig_h

        # Scale zone coordinates
        for zone_name in ["left", "right"]:
            zone_key = zone_name.upper()
            orig_zone = self.original_zones_config[zone_name]

            self.zones[zone_key] = {
                "x": int(orig_zone["x"] * scale_x),
                "y": int(orig_zone["y"] * scale_y),
                "width": int(orig_zone["width"] * scale_x),
                "height": int(orig_zone["height"] * scale_y),
                "angle": orig_zone.get(
                    "angle", -15
                ),  # Default -15 degrees for tilted camera
            }

        self.initialized = True

        logger.info(
            f"Zones initialized for {orig_w}x{orig_h} -> {target_w}x{target_h}:"
        )
        logger.info(f"  LEFT zone: {self.zones['LEFT']}")
        logger.info(f"  RIGHT zone: {self.zones['RIGHT']}")

    def _get_rotated_rect_mask(
        self, frame_shape: Tuple[int, int], zone: Dict
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create a mask for a rotated rectangle zone.

        Args:
            frame_shape: (height, width) of the frame
            zone: Zone dict with x, y, width, height, angle

        Returns:
            (mask, box_points) - binary mask and the 4 corner points
        """
        x, y, w, h = zone["x"], zone["y"], zone["width"], zone["height"]
        angle = zone.get("angle", 0)

        # Calculate center of the rectangle
        center_x = x + w / 2
        center_y = y + h / 2

        # Create rotated rectangle
        # cv2.boxPoints expects ((cx, cy), (w, h), angle)
        rect = ((center_x, center_y), (w, h), angle)
        box = cv2.boxPoints(rect)
        box = np.intp(box)  # np.int0 deprecated in NumPy 2.0

        # Create mask
        mask = np.zeros(frame_shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [box], 255)

        return mask, box

    def _check_zone(
        self, gray: np.ndarray, zone_id: str, frame_bgr: Optional[np.ndarray] = None
    ) -> Tuple[bool, int, float]:
        """
        Check if hot metal is detected in a zone (supports rotated rectangles).

        Args:
            gray: Grayscale frame (already downscaled)
            zone_id: 'LEFT' or 'RIGHT'
            frame_bgr: Optional BGR frame for color analysis

        Returns:
            (is_triggered, pixel_count, avg_brightness)
        """
        zone = self.zones[zone_id]

        # Get rotated rectangle mask
        mask, _ = self._get_rotated_rect_mask(gray.shape, zone)

        # Get pixels within the rotated zone
        zone_pixels = gray[mask > 0]

        if zone_pixels.size == 0:
            return False, 0, 0.0

        # Count bright pixels within the zone
        bright_mask_zone = zone_pixels > self.luminosity_threshold
        bright_pixels = int(np.sum(bright_mask_zone))

        if bright_pixels == 0:
            return False, 0, 0.0

        avg_brightness = float(np.mean(zone_pixels[bright_mask_zone]))

        # Basic trigger check: enough bright pixels
        basic_triggered = bright_pixels >= self.min_bright_pixels

        if not basic_triggered:
            return False, bright_pixels, avg_brightness

        # Hot metal color filter (if enabled and color frame provided)
        is_hot_metal = True
        if frame_bgr is not None and self.hot_metal_filter_enabled:
            is_hot_metal, color_stats = self._analyze_hot_metal_color(
                frame_bgr, zone_id
            )

        is_triggered = basic_triggered and is_hot_metal

        return is_triggered, bright_pixels, avg_brightness

    def _analyze_hot_metal_color(
        self, frame_bgr: np.ndarray, zone_id: str
    ) -> Tuple[bool, Dict]:
        """
        Analyze the color characteristics of bright regions in a zone.
        Supports rotated rectangles.

        Hot metal: Red/orange dominant, has saturation
        Reflections/noise: Neutral colors, low saturation

        Returns:
            (is_hot_metal, color_stats_dict)
        """
        zone = self.zones[zone_id]

        # Get rotated rectangle mask
        mask, _ = self._get_rotated_rect_mask(frame_bgr.shape[:2], zone)

        # Get pixels within the rotated zone
        zone_pixels_bgr = frame_bgr[mask > 0]

        if zone_pixels_bgr.size == 0:
            return True, {}

        # Convert zone to grayscale to find bright pixels
        zone_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        zone_gray_pixels = zone_gray[mask > 0]

        # Create mask for bright pixels only (within the rotated zone)
        bright_pixel_indices = zone_gray_pixels > self.luminosity_threshold

        if np.sum(bright_pixel_indices) < 10:  # Not enough bright pixels to analyze
            return True, {}

        # Extract color values of bright pixels
        bright_pixels_bgr = zone_pixels_bgr[bright_pixel_indices]

        # Calculate average BGR values
        avg_b = float(np.mean(bright_pixels_bgr[:, 0]))
        avg_g = float(np.mean(bright_pixels_bgr[:, 1]))
        avg_r = float(np.mean(bright_pixels_bgr[:, 2]))

        # Calculate color metrics
        # 1. Red dominance: R/B ratio (hot metal has R >> B)
        red_dominance = avg_r / max(avg_b, 1.0)

        # 2. Warmth ratio: (R+G)/(2*B) - hot colors have high warmth
        warmth_ratio = (avg_r + avg_g) / max(2.0 * avg_b, 1.0)

        # 3. Saturation analysis using HSV
        # Convert bright pixels to HSV
        bright_pixels_bgr_reshaped = bright_pixels_bgr.reshape(-1, 1, 3)
        bright_pixels_hsv = cv2.cvtColor(bright_pixels_bgr_reshaped, cv2.COLOR_BGR2HSV)
        bright_pixels_hsv = bright_pixels_hsv.reshape(-1, 3)
        avg_saturation = float(np.mean(bright_pixels_hsv[:, 1]))
        avg_hue = float(np.mean(bright_pixels_hsv[:, 0]))

        color_stats = {
            "avg_r": avg_r,
            "avg_g": avg_g,
            "avg_b": avg_b,
            "red_dominance": red_dominance,
            "warmth_ratio": warmth_ratio,
            "saturation": avg_saturation,
            "hue": avg_hue,
        }

        # Decision logic (relaxed thresholds for mill stand)
        is_hot_metal = bool(
            red_dominance >= self.min_red_dominance
            and avg_saturation >= self.min_saturation
            and warmth_ratio >= self.min_warmth_ratio
        )

        if not is_hot_metal:
            logger.debug(
                f"{zone_id} COLOR FILTERED: R/B={red_dominance:.2f} (min={self.min_red_dominance}), "
                f"sat={avg_saturation:.1f} (min={self.min_saturation}), "
                f"warmth={warmth_ratio:.2f} (min={self.min_warmth_ratio})"
            )

        return is_hot_metal, color_stats

    def _process_pending_pieces(
        self, current_time: float
    ) -> Optional[MillStandPieceCount]:
        """
        Check pending sequences for completed counts.

        A piece is counted when:
        1. Entry zone is confirmed
        2. Exit zone (opposite) is confirmed
        3. Travel time is within valid range
        """
        completed = None

        # Clean up expired sequences
        while self.pending_sequences:
            seq = self.pending_sequences[0]
            age = current_time - seq["entry_time"]
            if age > self.sequence_timeout:
                self.pending_sequences.popleft()
                logger.debug(
                    f"Sequence expired (entry at {seq['entry_zone']}, age={age:.1f}s)"
                )
            else:
                break

        # Check for completed sequences
        for seq in list(self.pending_sequences):
            if seq.get("entry_confirmed") and seq.get("exit_confirmed"):
                # Both zones confirmed - piece counted!
                travel_time = seq["exit_time"] - seq["entry_time"]

                # Validate travel time
                if travel_time >= self.min_travel_time:
                    self.total_count += 1

                    # Track direction
                    if seq["direction"] == "LEFT_TO_RIGHT":
                        self.left_to_right_count += 1
                    else:
                        self.right_to_left_count += 1

                    # Calculate confidence
                    total_frames = seq["entry_frames"] + seq["exit_frames"]
                    min_frames = min(seq["entry_frames"], seq["exit_frames"])
                    avg_pixels = (seq["entry_max_pixels"] + seq["exit_max_pixels"]) / 2

                    # Confidence scoring
                    confidence = 50.0
                    if min_frames >= 3:
                        confidence += 25.0
                    elif min_frames >= 2:
                        confidence += 15.0

                    if avg_pixels > 200:
                        confidence += 25.0
                    elif avg_pixels > 150:
                        confidence += 15.0
                    elif avg_pixels > 100:
                        confidence += 10.0

                    piece = MillStandPieceCount(
                        count_id=self.total_count,
                        timestamp=current_time,
                        direction=seq["direction"],
                        entry_zone=seq["entry_zone"],
                        exit_zone=seq["exit_zone"],
                        entry_time=seq["entry_time"],
                        exit_time=seq["exit_time"],
                        travel_time=travel_time,
                        confidence=min(100.0, confidence),
                        entry_frames=seq["entry_frames"],
                        exit_frames=seq["exit_frames"],
                        entry_max_pixels=seq["entry_max_pixels"],
                        exit_max_pixels=seq["exit_max_pixels"],
                        entry_avg_brightness=seq.get("entry_avg_brightness", 0),
                        exit_avg_brightness=seq.get("exit_avg_brightness", 0),
                    )
                    self.counted_pieces.append(piece)
                    completed = piece

                    direction_arrow = (
                        "->" if seq["direction"] == "LEFT_TO_RIGHT" else "<-"
                    )
                    confidence_str = (
                        "HIGH"
                        if confidence >= 80
                        else "MEDIUM"
                        if confidence >= 60
                        else "LOW"
                    )
                    logger.info(
                        f"*** PIECE #{self.total_count} COUNTED | "
                        f"Dir: {direction_arrow} | Travel: {travel_time:.2f}s | "
                        f"Conf: {confidence:.0f}% ({confidence_str}) ***"
                    )
                else:
                    logger.debug(
                        f"Sequence rejected - travel time too fast: {travel_time:.3f}s"
                    )

                self.pending_sequences.remove(seq)
                break

        return completed

    def process_frame(
        self, frame: np.ndarray
    ) -> Tuple[Optional[MillStandPieceCount], Dict]:
        """
        Process a frame and check for piece crossings.

        Args:
            frame: BGR frame from camera/video (original resolution)

        Returns:
            (counted_piece or None, detection_status dict)
        """
        self.frame_count += 1

        # Initialize zones on first frame
        self._init_zones(frame)

        current_time = time.time()

        # Downscale frame to target resolution
        resized = cv2.resize(
            frame, self.target_resolution, interpolation=cv2.INTER_AREA
        )

        # Convert to grayscale
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        # Check each zone
        status = {}
        for zone_id in ["LEFT", "RIGHT"]:
            triggered, pixel_count, brightness = self._check_zone(
                gray, zone_id, resized
            )

            status[zone_id] = {
                "triggered": triggered,
                "pixels": pixel_count,
                "brightness": brightness,
                "consecutive_frames": self.zone_consecutive_frames[zone_id],
                "confirmed": self.zone_confirmed[zone_id],
            }

            # Track consecutive frames
            if triggered:
                self.zone_consecutive_frames[zone_id] += 1
                # Track stats for this detection
                self.zone_stats[zone_id]["max_pixels"] = max(
                    self.zone_stats[zone_id]["max_pixels"], pixel_count
                )
                self.zone_stats[zone_id]["brightness_sum"] += brightness
                self.zone_stats[zone_id]["frame_count"] += 1
            else:
                # Reset if no longer triggered
                if self.zone_consecutive_frames[zone_id] > 0:
                    self.zone_consecutive_frames[zone_id] = 0
                    self.zone_confirmed[zone_id] = False
                    # Reset stats
                    self.zone_stats[zone_id] = {
                        "max_pixels": 0,
                        "brightness_sum": 0.0,
                        "frame_count": 0,
                    }

            # Check if zone is now CONFIRMED (enough consecutive frames)
            was_confirmed = self.zone_confirmed[zone_id]
            is_confirmed = (
                self.zone_consecutive_frames[zone_id] >= self.min_consecutive_frames
            )

            # Check debounce
            time_since_last = current_time - self.zone_last_trigger[zone_id]

            # Rising edge: zone just became CONFIRMED
            if (
                is_confirmed
                and not was_confirmed
                and time_since_last > self.debounce_time
            ):
                self.zone_confirmed[zone_id] = True
                self.zone_last_trigger[zone_id] = current_time

                # Get stats for this confirmed detection
                stats = self.zone_stats[zone_id]
                avg_brightness = (
                    stats["brightness_sum"] / stats["frame_count"]
                    if stats["frame_count"] > 0
                    else 0
                )

                opposite_zone = "RIGHT" if zone_id == "LEFT" else "LEFT"

                # Check if this completes a pending sequence (exit zone)
                found_pending = False
                for seq in self.pending_sequences:
                    if seq["entry_zone"] == opposite_zone and not seq.get(
                        "exit_confirmed"
                    ):
                        # This zone is the EXIT - update sequence
                        seq["exit_zone"] = zone_id
                        seq["exit_time"] = current_time
                        seq["exit_confirmed"] = True
                        seq["exit_frames"] = self.zone_consecutive_frames[zone_id]
                        seq["exit_max_pixels"] = stats["max_pixels"]
                        seq["exit_avg_brightness"] = avg_brightness
                        logger.debug(
                            f"{zone_id} EXIT confirmed ({self.zone_consecutive_frames[zone_id]} frames, "
                            f"{stats['max_pixels']} px) - completing {seq['direction']}"
                        )
                        found_pending = True
                        break

                if not found_pending:
                    # No matching pending sequence - this is a new ENTRY
                    direction = (
                        "LEFT_TO_RIGHT" if zone_id == "LEFT" else "RIGHT_TO_LEFT"
                    )
                    self.pending_sequences.append(
                        {
                            "entry_zone": zone_id,
                            "entry_time": current_time,
                            "entry_confirmed": True,
                            "entry_frames": self.zone_consecutive_frames[zone_id],
                            "entry_max_pixels": stats["max_pixels"],
                            "entry_avg_brightness": avg_brightness,
                            "direction": direction,
                            "exit_zone": None,
                            "exit_time": None,
                            "exit_confirmed": False,
                            "exit_frames": 0,
                            "exit_max_pixels": 0,
                            "exit_avg_brightness": 0,
                        }
                    )
                    logger.debug(
                        f"{zone_id} ENTRY confirmed ({self.zone_consecutive_frames[zone_id]} frames, "
                        f"{stats['max_pixels']} px) - starting {direction}"
                    )

        # Check for completed counts
        counted_piece = self._process_pending_pieces(current_time)

        # Build status dict
        status["total_count"] = self.total_count
        status["pending_sequences"] = len(self.pending_sequences)
        status["left_to_right"] = self.left_to_right_count
        status["right_to_left"] = self.right_to_left_count
        status["frame_count"] = self.frame_count

        return counted_piece, status

    def draw_overlay(self, frame: np.ndarray, status: Dict) -> np.ndarray:
        """Draw detection zones (rotated rectangles) and status on frame."""
        # Work on downscaled frame for consistency
        overlay = cv2.resize(
            frame, self.target_resolution, interpolation=cv2.INTER_AREA
        )

        # Zone colors
        colors = {
            "LEFT": (0, 255, 0),  # Green
            "RIGHT": (0, 0, 255),  # Red
        }

        # Draw zones (rotated rectangles)
        for zone_id, zone in self.zones.items():
            color = colors[zone_id]

            # Get rotated rectangle box points
            _, box = self._get_rotated_rect_mask(overlay.shape[:2], zone)

            # Brighten if triggered
            if status.get(zone_id, {}).get("triggered", False):
                color = (
                    min(255, color[0] + 100),
                    min(255, color[1] + 100),
                    min(255, color[2] + 100),
                )
                thickness = 3
            else:
                thickness = 2

            # Draw rotated rectangle
            cv2.polylines(
                overlay, [box], isClosed=True, color=color, thickness=thickness
            )

            # Draw label at the top-left corner of the rotated box
            # Find the top-most point for label placement
            top_point = box[np.argmin(box[:, 1])]
            label = f"{zone_id}"
            if status.get(zone_id, {}).get("confirmed", False):
                label += " [ON]"
            cv2.putText(
                overlay,
                label,
                (top_point[0], top_point[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )

            # Draw pixel count if triggered
            if status.get(zone_id, {}).get("triggered", False):
                px_text = f"{status[zone_id]['pixels']}px"
                # Find bottom-most point
                bottom_point = box[np.argmax(box[:, 1])]
                cv2.putText(
                    overlay,
                    px_text,
                    (bottom_point[0], bottom_point[1] + 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    color,
                    1,
                )

        # Draw count info (top right)
        frame_w = overlay.shape[1]
        box_width = 220
        box_x = frame_w - box_width - 5
        cv2.rectangle(overlay, (box_x, 5), (frame_w - 5, 95), (0, 0, 0), -1)
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
            f"L->R: {self.left_to_right_count}  R->L: {self.right_to_left_count}",
            (box_x + 5, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        cv2.putText(
            overlay,
            f"Pending: {status.get('pending_sequences', 0)}",
            (box_x + 5, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        cv2.putText(
            overlay,
            f"Frame: {status.get('frame_count', 0)}",
            (box_x + 5, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (150, 150, 150),
            1,
        )

        return overlay

    def get_stats(self) -> Dict:
        """Get counting statistics."""
        if not self.counted_pieces:
            return {
                "total_count": 0,
                "left_to_right": 0,
                "right_to_left": 0,
                "avg_travel_time": 0,
                "min_travel_time": 0,
                "max_travel_time": 0,
                "avg_confidence": 0,
            }

        travel_times = [p.travel_time for p in self.counted_pieces]
        confidences = [p.confidence for p in self.counted_pieces]

        return {
            "total_count": self.total_count,
            "left_to_right": self.left_to_right_count,
            "right_to_left": self.right_to_left_count,
            "avg_travel_time": float(np.mean(travel_times)),
            "min_travel_time": float(np.min(travel_times)),
            "max_travel_time": float(np.max(travel_times)),
            "avg_confidence": float(np.mean(confidences)),
        }

    def reset(self):
        """Reset counter state (for new session or day)."""
        self.total_count = 0
        self.left_to_right_count = 0
        self.right_to_left_count = 0
        self.counted_pieces = []
        self.pending_sequences.clear()
        self.frame_count = 0

        for zone_id in ["LEFT", "RIGHT"]:
            self.zone_consecutive_frames[zone_id] = 0
            self.zone_confirmed[zone_id] = False
            self.zone_last_trigger[zone_id] = 0
            self.zone_stats[zone_id] = {
                "max_pixels": 0,
                "brightness_sum": 0.0,
                "frame_count": 0,
            }

        logger.info("MillStandCounter reset")
