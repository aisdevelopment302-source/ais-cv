#!/usr/bin/env python3
"""
Plate Counter Module
====================
Counts hot plate pieces crossing the conveyor detection lines.

Logic:
- Detect bright (hot) pixels crossing each line
- A piece is counted when it crosses ALL 3 lines in sequence
- Sequence must complete within time window (prevents stale detections)
- Requires minimum brightness and size to filter scale/glow
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
class LineDetection:
    """Represents a detection event on a single line"""
    line_id: str
    timestamp: float
    brightness: float
    pixel_count: int
    frame_count: int = 1  # Consecutive frames detected


@dataclass
class PieceCount:
    """Represents a counted piece"""
    count_id: int
    timestamp: float
    l1_time: float
    l2_time: float
    l3_time: float
    travel_time: float  # L1 to L3
    confidence: float
    # Additional metadata for review
    l1_frames: int = 0  # Consecutive frames on L1
    l2_frames: int = 0  # Consecutive frames on L2
    l3_frames: int = 0  # Consecutive frames on L3
    l1_max_pixels: int = 0
    l2_max_pixels: int = 0
    l3_max_pixels: int = 0
    l1_avg_brightness: float = 0.0
    l2_avg_brightness: float = 0.0
    l3_avg_brightness: float = 0.0


class PlateCounter:
    def __init__(
        self,
        lines_config: dict,
        counting_config: Optional[dict] = None,
        luminosity_threshold: int = 150,
        min_bright_pixels: int = 80,
        sequence_timeout: float = 4.0,  # Max time from L1 to L3
        min_travel_time: float = 0.2,   # Min time L1 to L3 (filter instantaneous noise)
        line_thickness: int = 10,       # Pixels around line to check
        min_consecutive_frames: int = 2,  # Min frames to confirm detection
        human_filter_enabled: bool = True,  # Enable human/vertical object filtering
        max_aspect_ratio: float = 1.5,  # Max height/width ratio (plates are horizontal)
        min_blob_width: int = 30,       # Minimum width of bright region (plates are wide)
        # Hot metal color filter parameters
        hot_metal_filter_enabled: bool = True,  # Enable color-based hot metal detection
        min_red_dominance: float = 1.15,  # Min ratio of red channel to blue channel
        min_saturation: float = 30,       # Min saturation in HSV (white clothing has low saturation)
        min_warmth_ratio: float = 1.1,    # Min (R+G)/(2*B) ratio for warm colors
    ):
        """
        Initialize plate counter.
        
        Args:
            lines_config: Dict with line1, line2, line3 each having start/end coordinates
            counting_config: Optional dict with threshold overrides from settings.yaml
            luminosity_threshold: Brightness threshold for hot metal (0-255)
            min_bright_pixels: Minimum bright pixels on line to count as detection
            sequence_timeout: Maximum seconds for piece to travel L1->L3
            min_travel_time: Minimum seconds for L1->L3 (filters noise)
            line_thickness: Pixel width to check around each line
            min_consecutive_frames: Minimum consecutive frames to confirm a line detection
            hot_metal_filter_enabled: Enable color-based filtering for hot metal vs clothing
            min_red_dominance: Minimum R/B ratio (hot metal is red/orange dominant)
            min_saturation: Minimum HSV saturation (white clothing has near-zero saturation)
            min_warmth_ratio: Minimum warmth ratio (R+G)/(2*B) for hot colors
        """
        # Override defaults with counting_config if provided
        if counting_config:
            luminosity_threshold = counting_config.get('luminosity_threshold', luminosity_threshold)
            min_bright_pixels = counting_config.get('min_bright_pixels', min_bright_pixels)
            sequence_timeout = counting_config.get('sequence_timeout', sequence_timeout)
            min_travel_time = counting_config.get('min_travel_time', min_travel_time)
            line_thickness = counting_config.get('line_thickness', line_thickness)
            min_consecutive_frames = counting_config.get('min_consecutive_frames', min_consecutive_frames)
            human_filter_enabled = counting_config.get('human_filter_enabled', human_filter_enabled)
            max_aspect_ratio = counting_config.get('max_aspect_ratio', max_aspect_ratio)
            min_blob_width = counting_config.get('min_blob_width', min_blob_width)
            # Hot metal color filter config
            hot_metal_filter_enabled = counting_config.get('hot_metal_filter_enabled', hot_metal_filter_enabled)
            min_red_dominance = counting_config.get('min_red_dominance', min_red_dominance)
            min_saturation = counting_config.get('min_saturation', min_saturation)
            min_warmth_ratio = counting_config.get('min_warmth_ratio', min_warmth_ratio)
        
        self.lines = {
            'L1': (tuple(lines_config['line1']['start']), tuple(lines_config['line1']['end'])),
            'L2': (tuple(lines_config['line2']['start']), tuple(lines_config['line2']['end'])),
            'L3': (tuple(lines_config['line3']['start']), tuple(lines_config['line3']['end'])),
        }
        
        self.luminosity_threshold = luminosity_threshold
        self.min_bright_pixels = min_bright_pixels
        self.sequence_timeout = sequence_timeout
        self.min_travel_time = min_travel_time
        self.line_thickness = line_thickness
        self.min_consecutive_frames = min_consecutive_frames
        self.human_filter_enabled = human_filter_enabled
        self.max_aspect_ratio = max_aspect_ratio
        self.min_blob_width = min_blob_width
        
        # Hot metal color filter settings
        self.hot_metal_filter_enabled = hot_metal_filter_enabled
        self.min_red_dominance = min_red_dominance
        self.min_saturation = min_saturation
        self.min_warmth_ratio = min_warmth_ratio
        
        # Line masks (created on first frame)
        self.line_masks: Dict[str, np.ndarray] = {}
        self.frame_shape: Optional[Tuple[int, int]] = None
        
        # Detection state for each line
        self.line_active: Dict[str, bool] = {'L1': False, 'L2': False, 'L3': False}
        self.line_last_trigger: Dict[str, float] = {'L1': 0, 'L2': 0, 'L3': 0}
        
        # Consecutive frame tracking for each line
        self.line_consecutive_frames: Dict[str, int] = {'L1': 0, 'L2': 0, 'L3': 0}
        self.line_confirmed: Dict[str, bool] = {'L1': False, 'L2': False, 'L3': False}
        self.line_stats: Dict[str, Dict] = {
            'L1': {'max_pixels': 0, 'brightness_sum': 0.0, 'frame_count': 0},
            'L2': {'max_pixels': 0, 'brightness_sum': 0.0, 'frame_count': 0},
            'L3': {'max_pixels': 0, 'brightness_sum': 0.0, 'frame_count': 0},
        }
        
        # Pending sequences (pieces that triggered L1, waiting for L2, L3)
        self.pending_sequences: deque = deque(maxlen=50)
        
        # Counting
        self.total_count: int = 0
        self.counted_pieces: List[PieceCount] = []
        
        # Debounce - prevent rapid re-triggers on same line
        self.debounce_time: float = 0.3  # seconds
        
    def _create_line_mask(self, line_id: str, shape: Tuple[int, int]) -> np.ndarray:
        """Create a mask for pixels along a line"""
        mask = np.zeros(shape[:2], dtype=np.uint8)
        start, end = self.lines[line_id]
        cv2.line(mask, start, end, 255, self.line_thickness)
        return mask
    
    def _analyze_bright_region(self, gray: np.ndarray, line_id: str) -> Tuple[bool, float, int]:
        """
        Analyze the shape of bright regions near the line to filter out humans.
        
        Hot plates: Horizontal, wide, uniform brightness
        Humans: Vertical, narrow relative to height, variable brightness
        
        Returns:
            (is_plate_like, aspect_ratio, blob_width)
        """
        if not self.human_filter_enabled:
            return True, 0.0, 0
        
        # Get the line region with some padding for analysis
        start, end = self.lines[line_id]
        
        # Calculate bounding box around line with padding
        padding = 40  # pixels to look around the line
        min_x = max(0, min(start[0], end[0]) - padding)
        max_x = min(gray.shape[1], max(start[0], end[0]) + padding)
        min_y = max(0, min(start[1], end[1]) - padding * 2)  # More vertical padding
        max_y = min(gray.shape[0], max(start[1], end[1]) + padding * 2)
        
        # Extract region of interest
        roi = gray[min_y:max_y, min_x:max_x]
        
        if roi.size == 0:
            return True, 0.0, 0
        
        # Threshold to get bright pixels
        _, binary = cv2.threshold(roi, self.luminosity_threshold, 255, cv2.THRESH_BINARY)
        
        # Find contours of bright regions
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return True, 0.0, 0
        
        # Get the largest contour (main bright object)
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        if area < 50:  # Too small to analyze
            return True, 0.0, 0
        
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # Calculate aspect ratio (height / width)
        # Plates should have aspect_ratio < 1.5 (wider than tall)
        # Humans typically have aspect_ratio > 2.0 (taller than wide)
        aspect_ratio = h / w if w > 0 else 999
        
        # Check if this looks like a plate (horizontal) vs human (vertical)
        is_plate_like = (aspect_ratio <= self.max_aspect_ratio) and (w >= self.min_blob_width)
        
        if not is_plate_like:
            logger.info(f"{line_id} FILTERED: aspect_ratio={aspect_ratio:.2f} (max={self.max_aspect_ratio}), "
                        f"width={w}px (min={self.min_blob_width}) - likely human/vertical object")
        
        return is_plate_like, aspect_ratio, w
    
    def _analyze_hot_metal_color(self, frame_bgr: np.ndarray, line_id: str) -> Tuple[bool, Dict]:
        """
        Analyze the color characteristics of bright regions to distinguish hot metal from white clothing.
        
        Hot metal characteristics:
        - Red/orange/yellow dominant (high R, medium-high G, low B)
        - Has color saturation (not pure white)
        - Warm color temperature
        
        White clothing characteristics:
        - Equal R, G, B values (appears white/gray)
        - Very low saturation
        - Neutral color temperature
        
        Returns:
            (is_hot_metal, color_stats_dict)
        """
        if not self.hot_metal_filter_enabled:
            return True, {}
        
        # Get the line region with padding
        start, end = self.lines[line_id]
        padding = 40
        min_x = max(0, min(start[0], end[0]) - padding)
        max_x = min(frame_bgr.shape[1], max(start[0], end[0]) + padding)
        min_y = max(0, min(start[1], end[1]) - padding)
        max_y = min(frame_bgr.shape[0], max(start[1], end[1]) + padding)
        
        # Extract region of interest
        roi_bgr = frame_bgr[min_y:max_y, min_x:max_x]
        
        if roi_bgr.size == 0:
            return True, {}
        
        # Convert to grayscale to find bright pixels
        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        
        # Create mask for bright pixels only
        bright_mask = roi_gray > self.luminosity_threshold
        
        if np.sum(bright_mask) < 10:  # Not enough bright pixels to analyze
            return True, {}
        
        # Extract color values of bright pixels
        bright_pixels_bgr = roi_bgr[bright_mask]
        
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
        roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        bright_pixels_hsv = roi_hsv[bright_mask]
        avg_saturation = float(np.mean(bright_pixels_hsv[:, 1]))
        avg_hue = float(np.mean(bright_pixels_hsv[:, 0]))
        
        # 4. Color variance (white has low variance between R,G,B)
        color_variance = float(np.std([avg_r, avg_g, avg_b]))
        
        color_stats = {
            'avg_r': avg_r,
            'avg_g': avg_g,
            'avg_b': avg_b,
            'red_dominance': red_dominance,
            'warmth_ratio': warmth_ratio,
            'saturation': avg_saturation,
            'hue': avg_hue,
            'color_variance': color_variance,
        }
        
        # Decision logic:
        # Hot metal: red dominant, warm, has saturation
        # White clothing: neutral colors, low saturation
        is_hot_metal = bool(
            red_dominance >= self.min_red_dominance and
            avg_saturation >= self.min_saturation and
            warmth_ratio >= self.min_warmth_ratio
        )
        
        if not is_hot_metal:
            logger.info(
                f"{line_id} COLOR FILTERED: R/B={red_dominance:.2f} (min={self.min_red_dominance}), "
                f"sat={avg_saturation:.1f} (min={self.min_saturation}), "
                f"warmth={warmth_ratio:.2f} (min={self.min_warmth_ratio}) - likely white clothing/reflection"
            )
            logger.debug(f"    Color values: R={avg_r:.1f}, G={avg_g:.1f}, B={avg_b:.1f}, variance={color_variance:.1f}")
        
        return is_hot_metal, color_stats
    
    def _init_masks(self, frame: np.ndarray):
        """Initialize line masks based on frame size"""
        if self.frame_shape is None or self.frame_shape != frame.shape[:2]:
            self.frame_shape = frame.shape[:2]
            for line_id in self.lines:
                self.line_masks[line_id] = self._create_line_mask(line_id, frame.shape)
            logger.info(f"Initialized line masks for frame {frame.shape[1]}x{frame.shape[0]}")
    
    def _check_line(self, gray: np.ndarray, line_id: str, frame_bgr: Optional[np.ndarray] = None) -> Tuple[bool, int, float]:
        """
        Check if hot material is crossing a line.
        
        Returns:
            (is_triggered, pixel_count, avg_brightness)
        """
        mask = self.line_masks[line_id]
        
        # Get pixels on the line
        line_pixels = gray[mask > 0]
        
        if len(line_pixels) == 0:
            return False, 0, 0.0
        
        # Count bright pixels
        bright_pixels = np.sum(line_pixels > self.luminosity_threshold)
        avg_brightness = np.mean(line_pixels[line_pixels > self.luminosity_threshold]) if bright_pixels > 0 else 0
        
        # Basic trigger check: enough bright pixels
        basic_triggered = bool(bright_pixels >= self.min_bright_pixels)
        
        if not basic_triggered:
            return False, int(bright_pixels), float(avg_brightness)
        
        # Human filter: analyze shape of bright region
        is_plate_like, aspect_ratio, blob_width = self._analyze_bright_region(gray, line_id)
        
        # Hot metal color filter: distinguish from white clothing
        is_hot_metal = True
        if frame_bgr is not None and is_plate_like:
            is_hot_metal, color_stats = self._analyze_hot_metal_color(frame_bgr, line_id)
        
        # Only trigger if it looks like a plate AND has hot metal color signature
        is_triggered = basic_triggered and is_plate_like and is_hot_metal
        
        return is_triggered, int(bright_pixels), float(avg_brightness)
    
    def _process_sequence(self, current_time: float) -> Optional[PieceCount]:
        """
        Check pending sequences for completed counts.
        A piece is counted when L1->L2->L3 all CONFIRMED (consecutive frames) within timeout.
        """
        completed = None
        
        # Clean up expired sequences
        while self.pending_sequences:
            seq = self.pending_sequences[0]
            if current_time - seq['l1_time'] > self.sequence_timeout:
                self.pending_sequences.popleft()
                logger.debug(f"Sequence expired (started at L1: {seq['l1_time']:.2f})")
            else:
                break
        
        # Check for completed sequences (all 3 lines confirmed)
        for seq in list(self.pending_sequences):
            if seq.get('l1_confirmed') and seq.get('l2_confirmed') and seq.get('l3_confirmed'):
                # All 3 lines confirmed with consecutive frames!
                travel_time = seq['l3_time'] - seq['l1_time']
                
                # Validate travel time
                if travel_time >= self.min_travel_time:
                    self.total_count += 1
                    
                    # Calculate confidence based on frame counts and consistency
                    total_frames = seq['l1_frames'] + seq['l2_frames'] + seq['l3_frames']
                    min_frames = min(seq['l1_frames'], seq['l2_frames'], seq['l3_frames'])
                    avg_pixels = (seq['l1_max_pixels'] + seq['l2_max_pixels'] + seq['l3_max_pixels']) / 3
                    
                    # Confidence scoring:
                    # - Base 50% for completing sequence
                    # - +20% for having 3+ frames per line
                    # - +15% for consistent pixel counts (all lines similar)
                    # - +15% for high pixel counts (>200 avg)
                    confidence = 50.0
                    if min_frames >= 3:
                        confidence += 20.0
                    elif min_frames >= 2:
                        confidence += 10.0
                    
                    pixel_variance = max(seq['l1_max_pixels'], seq['l2_max_pixels'], seq['l3_max_pixels']) - \
                                    min(seq['l1_max_pixels'], seq['l2_max_pixels'], seq['l3_max_pixels'])
                    if pixel_variance < 50:
                        confidence += 15.0
                    elif pixel_variance < 100:
                        confidence += 7.0
                    
                    if avg_pixels > 200:
                        confidence += 15.0
                    elif avg_pixels > 150:
                        confidence += 10.0
                    elif avg_pixels > 100:
                        confidence += 5.0
                    
                    piece = PieceCount(
                        count_id=self.total_count,
                        timestamp=current_time,
                        l1_time=seq['l1_time'],
                        l2_time=seq['l2_time'],
                        l3_time=seq['l3_time'],
                        travel_time=travel_time,
                        confidence=min(100.0, confidence),
                        l1_frames=seq['l1_frames'],
                        l2_frames=seq['l2_frames'],
                        l3_frames=seq['l3_frames'],
                        l1_max_pixels=seq['l1_max_pixels'],
                        l2_max_pixels=seq['l2_max_pixels'],
                        l3_max_pixels=seq['l3_max_pixels'],
                        l1_avg_brightness=seq.get('l1_avg_brightness', 0),
                        l2_avg_brightness=seq.get('l2_avg_brightness', 0),
                        l3_avg_brightness=seq.get('l3_avg_brightness', 0),
                    )
                    self.counted_pieces.append(piece)
                    completed = piece
                    
                    confidence_str = "HIGH" if confidence >= 80 else "MEDIUM" if confidence >= 60 else "LOW"
                    logger.info(f"*** PIECE #{self.total_count} COUNTED | Travel: {travel_time:.2f}s | Conf: {confidence:.0f}% ({confidence_str}) ***")
                    logger.info(f"    Frames: L1={seq['l1_frames']}, L2={seq['l2_frames']}, L3={seq['l3_frames']} | Pixels: L1={seq['l1_max_pixels']}, L2={seq['l2_max_pixels']}, L3={seq['l3_max_pixels']}")
                else:
                    logger.debug(f"Sequence rejected - travel time too fast: {travel_time:.3f}s")
                
                self.pending_sequences.remove(seq)
                break
        
        return completed
    
    def process_frame(self, frame: np.ndarray) -> Tuple[Optional[PieceCount], Dict]:
        """
        Process a frame and check for plate crossings.
        Uses consecutive frame confirmation to reduce false positives.
        
        Args:
            frame: BGR frame from camera
            
        Returns:
            (counted_piece or None, detection_status dict)
        """
        self._init_masks(frame)
        current_time = time.time()
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Check each line
        status = {}
        for line_id in ['L1', 'L2', 'L3']:
            triggered, pixel_count, brightness = self._check_line(gray, line_id, frame)
            
            status[line_id] = {
                'triggered': triggered,
                'pixels': pixel_count,
                'brightness': brightness,
                'consecutive_frames': self.line_consecutive_frames[line_id],
                'confirmed': self.line_confirmed[line_id]
            }
            
            # Track consecutive frames
            if triggered:
                self.line_consecutive_frames[line_id] += 1
                # Track stats for this detection
                self.line_stats[line_id]['max_pixels'] = max(
                    self.line_stats[line_id]['max_pixels'], pixel_count
                )
                self.line_stats[line_id]['brightness_sum'] += brightness
                self.line_stats[line_id]['frame_count'] += 1
            else:
                # Reset if no longer triggered
                if self.line_consecutive_frames[line_id] > 0:
                    self.line_consecutive_frames[line_id] = 0
                    self.line_confirmed[line_id] = False
                    # Reset stats
                    self.line_stats[line_id] = {'max_pixels': 0, 'brightness_sum': 0.0, 'frame_count': 0}
            
            # Check if line is now CONFIRMED (enough consecutive frames)
            was_confirmed = self.line_confirmed[line_id]
            is_confirmed = self.line_consecutive_frames[line_id] >= self.min_consecutive_frames
            
            # Check debounce
            time_since_last = current_time - self.line_last_trigger[line_id]
            
            # Rising edge: line just became CONFIRMED
            if is_confirmed and not was_confirmed and time_since_last > self.debounce_time:
                self.line_confirmed[line_id] = True
                self.line_last_trigger[line_id] = current_time
                
                # Get stats for this confirmed detection
                stats = self.line_stats[line_id]
                avg_brightness = stats['brightness_sum'] / stats['frame_count'] if stats['frame_count'] > 0 else 0
                
                if line_id == 'L1':
                    # Start new sequence
                    self.pending_sequences.append({
                        'l1_time': current_time,
                        'l1_confirmed': True,
                        'l1_frames': self.line_consecutive_frames[line_id],
                        'l1_max_pixels': stats['max_pixels'],
                        'l1_avg_brightness': avg_brightness,
                        'l2_time': None, 'l2_confirmed': False, 'l2_frames': 0, 'l2_max_pixels': 0, 'l2_avg_brightness': 0,
                        'l3_time': None, 'l3_confirmed': False, 'l3_frames': 0, 'l3_max_pixels': 0, 'l3_avg_brightness': 0,
                    })
                    logger.debug(f"L1 CONFIRMED ({self.line_consecutive_frames[line_id]} frames, {stats['max_pixels']} px)")
                    
                elif line_id == 'L2':
                    # Update pending sequences that have L1 confirmed but not L2
                    for seq in self.pending_sequences:
                        if seq['l1_confirmed'] and not seq['l2_confirmed']:
                            seq['l2_time'] = current_time
                            seq['l2_confirmed'] = True
                            seq['l2_frames'] = self.line_consecutive_frames[line_id]
                            seq['l2_max_pixels'] = stats['max_pixels']
                            seq['l2_avg_brightness'] = avg_brightness
                            logger.debug(f"L2 CONFIRMED ({self.line_consecutive_frames[line_id]} frames, {stats['max_pixels']} px)")
                            break
                            
                elif line_id == 'L3':
                    # Update pending sequences that have L1, L2 confirmed but not L3
                    for seq in self.pending_sequences:
                        if seq['l1_confirmed'] and seq['l2_confirmed'] and not seq['l3_confirmed']:
                            seq['l3_time'] = current_time
                            seq['l3_confirmed'] = True
                            seq['l3_frames'] = self.line_consecutive_frames[line_id]
                            seq['l3_max_pixels'] = stats['max_pixels']
                            seq['l3_avg_brightness'] = avg_brightness
                            logger.debug(f"L3 CONFIRMED ({self.line_consecutive_frames[line_id]} frames, {stats['max_pixels']} px)")
                            break
            
            self.line_active[line_id] = triggered
        
        # Check for completed counts
        counted_piece = self._process_sequence(current_time)
        
        status['total_count'] = self.total_count
        status['pending_sequences'] = len(self.pending_sequences)
        
        return counted_piece, status
    
    def draw_overlay(self, frame: np.ndarray, status: Dict) -> np.ndarray:
        """Draw counting lines and status on frame"""
        overlay = frame.copy()
        frame_width = frame.shape[1]
        
        # Draw lines with status color
        colors = {
            'L1': (0, 255, 0),    # Green
            'L2': (0, 255, 255),  # Yellow
            'L3': (0, 0, 255),    # Red
        }
        
        for line_id, (start, end) in self.lines.items():
            color = colors[line_id]
            thickness = 4 if status.get(line_id, {}).get('triggered', False) else 2
            
            # Brighten color if triggered
            if status.get(line_id, {}).get('triggered', False):
                color = (min(255, color[0]+100), min(255, color[1]+100), min(255, color[2]+100))
            
            cv2.line(overlay, start, end, color, thickness)
            cv2.putText(overlay, line_id, (end[0]+5, end[1]), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Draw count on TOP RIGHT (not top left to avoid covering timestamp)
        box_width = 200
        box_x = frame_width - box_width - 5
        cv2.rectangle(overlay, (box_x, 5), (frame_width - 5, 80), (0, 0, 0), -1)
        cv2.putText(overlay, f"COUNT: {self.total_count}", (box_x + 5, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        cv2.putText(overlay, f"Pending: {status.get('pending_sequences', 0)}", (box_x + 5, 65),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        return overlay
    
    def get_stats(self) -> Dict:
        """Get counting statistics"""
        if not self.counted_pieces:
            return {
                'total_count': 0,
                'avg_travel_time': 0,
                'min_travel_time': 0,
                'max_travel_time': 0,
            }
        
        travel_times = [p.travel_time for p in self.counted_pieces]
        return {
            'total_count': self.total_count,
            'avg_travel_time': np.mean(travel_times),
            'min_travel_time': np.min(travel_times),
            'max_travel_time': np.max(travel_times),
        }
