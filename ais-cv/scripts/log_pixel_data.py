#!/usr/bin/env python3
"""
Pixel Data Logger for Mill Stand Analysis
==========================================
Logs pixel values for both LEFT and RIGHT zones at configurable intervals.
Outputs CSV data for visualization and analysis.

Usage:
    python scripts/log_pixel_data.py --start 20 --end 28  # 5 minutes (~8% of 61min)
    python scripts/log_pixel_data.py --interval 0.5       # Sample every 0.5 seconds
    python scripts/log_pixel_data.py --output data/pixel_log.csv
"""

import cv2
import numpy as np
import yaml
import csv
import sys
import argparse
from pathlib import Path
from typing import Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class PixelDataLogger:
    """Logs pixel values for mill stand zones."""

    def __init__(
        self,
        video_path: str,
        config_path: str,
        brightness_threshold: int = 160,
        saturation_threshold: int = 120,
    ):
        self.video_path = video_path
        self.config = self._load_config(config_path)
        self.brightness_threshold = brightness_threshold
        self.saturation_threshold = saturation_threshold

        # Video properties
        self.cap = None
        self.fps = 25
        self.total_frames = 0
        self.width = 0
        self.height = 0

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
        Analyze a zone and return pixel count, average brightness, and total pixels.

        Uses combined filtering to detect white-hot metal and reject red/orange glare:
        1. High brightness threshold - white-hot metal is very bright
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
        # 2. Low saturation (< threshold) - white-hot metal is desaturated
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

        return True

    def log_data(
        self,
        start_percent: float = 20,
        end_percent: float = 28,
        interval: float = 0.5,
        output_path: str = None,
    ) -> list:
        """
        Log pixel data for specified video segment.

        Args:
            start_percent: Start position as percentage of video (0-100)
            end_percent: End position as percentage of video (0-100)
            interval: Sample interval in seconds
            output_path: Path to save CSV output

        Returns:
            List of data rows
        """
        if not self.open_video():
            return []

        # Calculate frame range
        start_frame = int(self.total_frames * start_percent / 100)
        end_frame = int(self.total_frames * end_percent / 100)

        # Calculate frame interval (how many frames to skip)
        frame_interval = int(self.fps * interval)

        # Time calculations
        start_time = start_frame / self.fps
        end_time = end_frame / self.fps
        duration = end_time - start_time

        def format_time(seconds):
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins:02d}:{secs:02d}"

        print("=" * 70)
        print("PIXEL DATA LOGGER")
        print("=" * 70)
        print(f"Video: {self.video_path}")
        print(f"Resolution: {self.width}x{self.height} @ {self.fps:.1f} FPS")
        print(
            f"Range: {start_percent}% - {end_percent}% ({format_time(start_time)} - {format_time(end_time)})"
        )
        print(f"Duration: {format_time(duration)}")
        print(f"Sample interval: {interval}s ({frame_interval} frames)")
        print(
            f"Color filter: brightness > {self.brightness_threshold} AND saturation < {self.saturation_threshold}"
        )
        print(f"Output: {output_path}")
        print("=" * 70)
        print()

        # Seek to start
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        # Load zone config
        zones_config = self.config.get("zones", {})

        # Collect data
        data_rows = []
        frame_num = start_frame

        print("Logging data...")
        try:
            while frame_num < end_frame:
                ret, frame = self.cap.read()
                if not ret:
                    break

                timestamp = frame_num / self.fps
                timestamp_str = f"{int(timestamp // 60):02d}:{timestamp % 60:05.2f}"

                # Analyze each zone
                left_pixels, left_brightness, left_total = 0, 0.0, 0
                right_pixels, right_brightness, right_total = 0, 0.0, 0

                if "left" in zones_config:
                    left_pixels, left_brightness, left_total = self._analyze_zone(
                        frame, zones_config["left"]
                    )
                if "right" in zones_config:
                    right_pixels, right_brightness, right_total = self._analyze_zone(
                        frame, zones_config["right"]
                    )

                # Calculate ratios (bright_pixels / total_pixels)
                left_ratio = left_pixels / left_total if left_total > 0 else 0.0
                right_ratio = right_pixels / right_total if right_total > 0 else 0.0

                # Store row
                row = {
                    "frame": frame_num,
                    "timestamp_sec": round(timestamp, 2),
                    "timestamp_str": timestamp_str,
                    "left_pixels": left_pixels,
                    "right_pixels": right_pixels,
                    "left_total": left_total,
                    "right_total": right_total,
                    "left_ratio": round(left_ratio, 4),
                    "right_ratio": round(right_ratio, 4),
                    "left_brightness": round(left_brightness, 1),
                    "right_brightness": round(right_brightness, 1),
                }
                data_rows.append(row)

                # Skip to next sample
                frame_num += frame_interval
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)

                # Progress update
                if len(data_rows) % 100 == 0:
                    progress = (
                        (frame_num - start_frame) / (end_frame - start_frame) * 100
                    )
                    print(f"  Progress: {progress:.0f}% ({len(data_rows)} samples)")

        finally:
            self.cap.release()

        print(f"\nCollected {len(data_rows)} samples")

        # Save to CSV
        if output_path and data_rows:
            self._save_csv(data_rows, output_path)

        return data_rows

    def _save_csv(self, data_rows: list, output_path: str):
        """Save data to CSV file."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "frame",
                    "timestamp_sec",
                    "timestamp_str",
                    "left_pixels",
                    "right_pixels",
                    "left_total",
                    "right_total",
                    "left_ratio",
                    "right_ratio",
                    "left_brightness",
                    "right_brightness",
                ],
            )
            writer.writeheader()
            writer.writerows(data_rows)

        print(f"Data saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Log pixel values for mill stand zones"
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
        "--end",
        type=float,
        default=28,
        help="End position as percentage (default: 28, ~5 min)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Sample interval in seconds (default: 0.5)",
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
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "data" / "pixel_log.csv"),
        help="Output CSV path",
    )

    args = parser.parse_args()

    logger = PixelDataLogger(
        video_path=args.video,
        config_path=args.config,
        brightness_threshold=args.brightness_threshold,
        saturation_threshold=args.saturation_threshold,
    )

    logger.log_data(
        start_percent=args.start,
        end_percent=args.end,
        interval=args.interval,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
