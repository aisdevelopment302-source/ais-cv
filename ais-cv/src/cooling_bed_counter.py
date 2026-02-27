#!/usr/bin/env python3
"""
Cooling Bed Piece Counter
=========================
Counts hot pieces arriving at the top of the cooling bed.

Logic:
- Monitor arrival zone at top of cooling bed
- Detect hot metal using brightness + color filter
- Count when zone transitions from EMPTY to OCCUPIED
- Track blobs to handle multiple pieces
"""

import cv2
import numpy as np
import time
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class CountEvent:
    """Represents a counted piece"""
    count_id: int
    timestamp: float
    blob_count: int  # How many blobs detected (usually 1)
    max_pixels: int
    avg_brightness: float


class CoolingBedCounter:
    """
    Counts pieces arriving at the cooling bed.
    
    Uses rising-edge detection: counts when zone goes from
    empty (few hot pixels) to occupied (many hot pixels).
    """
    
    def __init__(
        self,
        zone: dict,  # {'x': int, 'y': int, 'w': int, 'h': int}
        min_hot_pixels: int = 300,
        empty_threshold: int = 50,
        min_blob_area: int = 100,
        debounce_seconds: float = 1.0,
        # HSV thresholds for hot metal
        hue_range: Tuple[int, int] = (0, 35),
        sat_min: int = 60,
        val_min: int = 140,
    ):
        self.zone = zone
        self.min_hot_pixels = min_hot_pixels
        self.empty_threshold = empty_threshold
        self.min_blob_area = min_blob_area
        self.debounce_seconds = debounce_seconds
        
        # HSV thresholds
        self.lower_hot = np.array([hue_range[0], sat_min, val_min])
        self.upper_hot = np.array([hue_range[1], 255, 255])
        
        # State
        self.is_occupied = False
        self.last_count_time = 0.0
        self.total_count = 0
        self.count_history: List[CountEvent] = []
        
        # Rolling stats
        self.pixel_history = deque(maxlen=30)  # ~1 second at 30fps
        
    def process_frame(self, frame: np.ndarray) -> Tuple[int, dict]:
        """
        Process a frame and return (new_counts, debug_info).
        
        Returns:
            new_counts: Number of new pieces counted (usually 0 or 1)
            debug_info: Dict with detection details
        """
        # Extract zone
        roi = frame[
            self.zone['y']:self.zone['y']+self.zone['h'],
            self.zone['x']:self.zone['x']+self.zone['w']
        ]
        
        # Convert to HSV
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # Create hot metal mask
        mask = cv2.inRange(hsv, self.lower_hot, self.upper_hot)
        
        # Count hot pixels
        hot_pixels = np.sum(mask > 0)
        self.pixel_history.append(hot_pixels)
        
        # Find blobs
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        big_blobs = [c for c in contours if cv2.contourArea(c) >= self.min_blob_area]
        blob_count = len(big_blobs)
        
        # Calculate average brightness of hot pixels
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray[mask > 0]) if hot_pixels > 0 else 0
        
        debug_info = {
            'hot_pixels': hot_pixels,
            'blob_count': blob_count,
            'avg_brightness': avg_brightness,
            'is_occupied': self.is_occupied,
            'mask': mask,
        }
        
        new_counts = 0
        now = time.time()
        
        # State machine: detect rising edge (empty -> occupied)
        if not self.is_occupied:
            # Check if zone became occupied
            if hot_pixels >= self.min_hot_pixels and blob_count >= 1:
                # Debounce check
                if now - self.last_count_time >= self.debounce_seconds:
                    self.is_occupied = True
                    self.last_count_time = now
                    
                    # Count pieces (usually 1, but could be more if blobs detected)
                    pieces = max(1, blob_count)
                    self.total_count += pieces
                    new_counts = pieces
                    
                    event = CountEvent(
                        count_id=self.total_count,
                        timestamp=now,
                        blob_count=blob_count,
                        max_pixels=hot_pixels,
                        avg_brightness=avg_brightness,
                    )
                    self.count_history.append(event)
                    
                    logger.info(
                        f"COUNTED: +{pieces} (total={self.total_count}) | "
                        f"pixels={hot_pixels}, blobs={blob_count}"
                    )
        else:
            # Check if zone became empty
            if hot_pixels <= self.empty_threshold:
                self.is_occupied = False
                logger.debug(f"Zone cleared (pixels={hot_pixels})")
        
        debug_info['new_counts'] = new_counts
        debug_info['total_count'] = self.total_count
        
        return new_counts, debug_info
    
    def draw_debug(self, frame: np.ndarray, debug_info: dict) -> np.ndarray:
        """Draw debug overlay on frame"""
        viz = frame.copy()
        
        # Draw zone
        color = (0, 255, 0) if debug_info.get('is_occupied') else (0, 255, 255)
        cv2.rectangle(
            viz,
            (self.zone['x'], self.zone['y']),
            (self.zone['x'] + self.zone['w'], self.zone['y'] + self.zone['h']),
            color, 2
        )
        
        # Draw stats
        y_offset = 30
        texts = [
            f"Count: {debug_info.get('total_count', 0)}",
            f"Pixels: {debug_info.get('hot_pixels', 0)}",
            f"Blobs: {debug_info.get('blob_count', 0)}",
            f"State: {'OCCUPIED' if debug_info.get('is_occupied') else 'EMPTY'}",
        ]
        
        for i, text in enumerate(texts):
            cv2.putText(
                viz, text,
                (10, y_offset + i * 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2
            )
        
        return viz


def run_counter(
    rtsp_url: str,
    zone: dict,
    duration_seconds: Optional[float] = None,
    show_video: bool = False,
    **counter_kwargs
):
    """Run the counter on an RTSP stream"""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        logger.error(f"Failed to connect to {rtsp_url}")
        return
    
    logger.info(f"Connected to stream")
    logger.info(f"Zone: x={zone['x']}-{zone['x']+zone['w']}, y={zone['y']}-{zone['y']+zone['h']}")
    
    counter = CoolingBedCounter(zone=zone, **counter_kwargs)
    
    start_time = time.time()
    frame_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read frame, reconnecting...")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(rtsp_url)
                continue
            
            new_counts, debug_info = counter.process_frame(frame)
            frame_count += 1
            
            # Log periodically
            if frame_count % 100 == 0:
                elapsed = time.time() - start_time
                logger.info(
                    f"Status: {counter.total_count} pieces | "
                    f"Running {elapsed/60:.1f}min | "
                    f"Current: {debug_info['hot_pixels']}px, {debug_info['blob_count']} blobs"
                )
            
            if show_video:
                viz = counter.draw_debug(frame, debug_info)
                cv2.imshow('Cooling Bed Counter', viz)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            
            # Check duration
            if duration_seconds and (time.time() - start_time) >= duration_seconds:
                break
                
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        cap.release()
        if show_video:
            cv2.destroyAllWindows()
        
        elapsed = time.time() - start_time
        logger.info(f"Final count: {counter.total_count} pieces in {elapsed/60:.1f} minutes")
        
        return counter


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Cooling Bed Piece Counter')
    parser.add_argument('--rtsp', required=True, help='RTSP URL')
    parser.add_argument('--duration', type=float, help='Duration in seconds')
    parser.add_argument('--show', action='store_true', help='Show video')
    parser.add_argument('--min-pixels', type=int, default=300, help='Min hot pixels to trigger')
    parser.add_argument('--debounce', type=float, default=1.0, help='Debounce seconds')
    
    args = parser.parse_args()
    
    # Default zone for cooling bed (camera 3)
    zone = {'x': 350, 'y': 70, 'w': 350, 'h': 120}
    
    run_counter(
        rtsp_url=args.rtsp,
        zone=zone,
        duration_seconds=args.duration,
        show_video=args.show,
        min_hot_pixels=args.min_pixels,
        debounce_seconds=args.debounce,
    )
