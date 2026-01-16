"""Hot Stock Detection for Furnace Camera"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    hot_stock_detected: bool
    luminosity_score: float  # 0-100
    motion_score: float  # 0-100
    confidence: float  # 0-100 combined
    bright_pixels: int
    motion_area: int


class HotStockDetector:
    def __init__(
        self,
        roi: dict,
        luminosity_threshold: int = 180,
        luminosity_min_pixels: int = 1000,
        motion_threshold: int = 25,
        motion_min_area: int = 500,
    ):
        self.roi = roi
        self.luminosity_threshold = luminosity_threshold
        self.luminosity_min_pixels = luminosity_min_pixels
        self.motion_threshold = motion_threshold
        self.motion_min_area = motion_min_area

        self.previous_frame: Optional[np.ndarray] = None

    def _extract_roi(self, frame: np.ndarray) -> np.ndarray:
        """Extract region of interest from frame"""
        x = self.roi["x"]
        y = self.roi["y"]
        w = self.roi["width"]
        h = self.roi["height"]
        return frame[y : y + h, x : x + w]

    def _detect_luminosity(self, roi_frame: np.ndarray) -> Tuple[bool, float, int]:
        """Detect bright/glowing areas (hot steel)"""
        # Convert to grayscale if needed
        if len(roi_frame.shape) == 3:
            gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi_frame

        # Count pixels above luminosity threshold
        bright_mask = gray > self.luminosity_threshold
        bright_pixels = np.sum(bright_mask)

        # Calculate score (0-100)
        max_possible = roi_frame.shape[0] * roi_frame.shape[1]
        score = min(100, (bright_pixels / self.luminosity_min_pixels) * 50)

        detected = bright_pixels >= self.luminosity_min_pixels

        return detected, score, bright_pixels

    def _detect_motion(self, roi_frame: np.ndarray) -> Tuple[bool, float, int]:
        """Detect motion between frames"""
        # Convert to grayscale
        if len(roi_frame.shape) == 3:
            gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi_frame

        # Apply blur to reduce noise
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.previous_frame is None:
            self.previous_frame = gray
            return False, 0.0, 0

        # Calculate frame difference
        frame_diff = cv2.absdiff(self.previous_frame, gray)
        self.previous_frame = gray

        # Threshold the difference
        _, thresh = cv2.threshold(
            frame_diff, self.motion_threshold, 255, cv2.THRESH_BINARY
        )

        # Count motion pixels
        motion_pixels = np.sum(thresh > 0)

        # Find contours for motion area
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        motion_area = sum(cv2.contourArea(c) for c in contours)

        # Calculate score (0-100)
        score = min(100, (motion_area / self.motion_min_area) * 50)

        detected = motion_area >= self.motion_min_area

        return detected, score, motion_area

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """Main detection method - returns if hot stock is detected"""
        roi_frame = self._extract_roi(frame)

        # Detect luminosity (glowing hot steel)
        lum_detected, lum_score, bright_pixels = self._detect_luminosity(roi_frame)

        # Detect motion (stock moving)
        motion_detected, motion_score, motion_area = self._detect_motion(roi_frame)

        # Combined detection logic:
        # Hot stock = bright glowing area detected
        # Motion adds confidence but isn't required (stock might be stationary briefly)
        hot_stock_detected = lum_detected

        # Confidence scoring
        # Luminosity is primary (70%), motion is secondary (30%)
        confidence = (lum_score * 0.7) + (motion_score * 0.3)

        # Boost confidence if both agree
        if lum_detected and motion_detected:
            confidence = min(100, confidence * 1.2)

        return DetectionResult(
            hot_stock_detected=hot_stock_detected,
            luminosity_score=lum_score,
            motion_score=motion_score,
            confidence=confidence,
            bright_pixels=bright_pixels,
            motion_area=motion_area,
        )
