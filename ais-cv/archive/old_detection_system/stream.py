"""RTSP Stream Handler for Dahua NVR"""

import cv2
import time
import logging
from typing import Optional, Generator
import numpy as np

logger = logging.getLogger(__name__)


class RTSPStream:
    def __init__(
        self, rtsp_url: str, reconnect_attempts: int = 5, reconnect_delay: float = 5.0
    ):
        self.rtsp_url = rtsp_url
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.cap: Optional[cv2.VideoCapture] = None
        self.connected = False

    def connect(self) -> bool:
        """Connect to RTSP stream"""
        for attempt in range(self.reconnect_attempts):
            logger.info(
                f"Connecting to stream (attempt {attempt + 1}/{self.reconnect_attempts})"
            )

            # Use TCP for reliability (Dahua works better with TCP)
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer for real-time

            if self.cap.isOpened():
                self.connected = True
                logger.info("Stream connected successfully")
                return True

            logger.warning(f"Connection failed, retrying in {self.reconnect_delay}s...")
            time.sleep(self.reconnect_delay)

        logger.error("Failed to connect to stream after all attempts")
        return False

    def read_frame(self) -> Optional[np.ndarray]:
        """Read a single frame from stream"""
        if not self.connected or self.cap is None:
            return None

        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to read frame, attempting reconnect...")
            self.connected = False
            self.connect()
            return None

        return frame

    def frames(self, target_fps: float = 1.0) -> Generator[np.ndarray, None, None]:
        """Generator yielding frames at target FPS"""
        frame_interval = 1.0 / target_fps
        last_frame_time = 0

        while True:
            current_time = time.time()

            # Read frame (even if we skip it, to keep stream flowing)
            frame = self.read_frame()

            # Yield at target FPS
            if current_time - last_frame_time >= frame_interval:
                if frame is not None:
                    yield frame
                    last_frame_time = current_time

            # Small sleep to prevent CPU spinning
            time.sleep(0.01)

    def release(self):
        """Release stream resources"""
        if self.cap:
            self.cap.release()
            self.connected = False
            logger.info("Stream released")
