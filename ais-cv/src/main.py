"""AIS CV POC - Furnace Camera Production Detection"""

import os
import sys
import time
import logging
import yaml
import signal
from datetime import datetime
from pathlib import Path

from stream import RTSPStream
from detector import HotStockDetector
from state_machine import ProductionStateMachine, StateChange, ProductionState


# Setup logging
def setup_logging(log_dir: str, level: str = "INFO"):
    """Configure logging to console and file"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path / "cv.log")],
    )


logger = logging.getLogger(__name__)


class CVApplication:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.running = False

        # Setup logging
        setup_logging(
            self.config["logging"]["output_dir"], self.config["logging"]["level"]
        )

        # Initialize components
        self.stream = RTSPStream(
            rtsp_url=self.config["camera"]["rtsp_url"],
            reconnect_attempts=self.config["camera"]["reconnect_attempts"],
            reconnect_delay=self.config["camera"]["reconnect_delay_seconds"],
        )

        self.detector = HotStockDetector(
            roi=self.config["roi"]["furnace_door"],
            luminosity_threshold=self.config["detection"]["luminosity_threshold"],
            luminosity_min_pixels=self.config["detection"]["luminosity_min_pixels"],
            motion_threshold=self.config["detection"]["motion_threshold"],
            motion_min_area=self.config["detection"]["motion_min_area"],
        )

        self.state_machine = ProductionStateMachine(
            break_threshold_seconds=self.config["detection"]["break_threshold_seconds"],
            min_run_duration_seconds=self.config["detection"][
                "min_run_duration_seconds"
            ],
            on_state_change=self._on_state_change,
        )

        # Photo capture
        self.photo_dir = Path(self.config["photos"]["output_dir"])
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.last_periodic_photo = 0

        # State log
        self.log_dir = Path(self.config["logging"]["output_dir"])
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Frame storage for photo capture
        self.last_frame = None

    def _load_config(self, config_path: str) -> dict:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)

    def _on_state_change(self, change: StateChange):
        """Called when production state changes"""
        # Log state change
        self._log_state_change(change)

        # Capture photo
        if self.config["photos"]["on_state_change"]:
            self._capture_photo(f"state_change_{change.new_state.value}")

    def _log_state_change(self, change: StateChange):
        """Log state change to file"""
        log_file = (
            self.log_dir / f"state_changes_{datetime.now().strftime('%Y-%m-%d')}.csv"
        )

        # Create header if new file
        if not log_file.exists():
            with open(log_file, "w") as f:
                f.write(
                    "timestamp,previous_state,new_state,confidence,duration_seconds\n"
                )

        with open(log_file, "a") as f:
            f.write(
                f"{change.timestamp.isoformat()},{change.previous_state.value},{change.new_state.value},{change.confidence:.1f},{change.duration_in_previous_seconds:.1f}\n"
            )

    def _capture_photo(self, reason: str):
        """Capture a validation photo"""
        if self.last_frame is not None:
            import cv2

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            state = self.state_machine.current_state.value
            confidence = self.state_machine.last_confidence

            filename = f"{timestamp}_{state}_{reason}_{confidence:.0f}.jpg"
            filepath = self.photo_dir / filename

            cv2.imwrite(str(filepath), self.last_frame)
            logger.info(f"Photo captured: {filename}")

    def _periodic_photo_check(self):
        """Check if periodic photo should be captured"""
        interval = self.config["photos"]["periodic_interval_seconds"]
        current_time = time.time()

        if current_time - self.last_periodic_photo >= interval:
            self._capture_photo("periodic")
            self.last_periodic_photo = current_time

    def run(self):
        """Main processing loop"""
        logger.info("Starting CV Application...")
        logger.info(f"Camera: {self.config['camera']['name']}")

        # Connect to stream
        if not self.stream.connect():
            logger.error("Failed to connect to camera stream. Exiting.")
            return

        self.running = True
        process_fps = self.config["detection"]["process_fps"]

        logger.info(f"Processing at {process_fps} FPS")
        logger.info(
            f"Break threshold: {self.config['detection']['break_threshold_seconds']} seconds"
        )

        last_status_time = 0

        try:
            for frame in self.stream.frames(target_fps=process_fps):
                if not self.running:
                    break

                self.last_frame = frame

                # Run detection
                result = self.detector.detect(frame)

                # Update state machine
                self.state_machine.update(result.hot_stock_detected, result.confidence)

                # Periodic photo
                self._periodic_photo_check()

                # Status output (every 10 seconds)
                current_time = time.time()
                if current_time - last_status_time >= 10:
                    state = self.state_machine.current_state.value
                    time_in_state = self.state_machine.time_in_current_state
                    logger.info(
                        f"State: {state} | "
                        f"Duration: {time_in_state:.0f}s | "
                        f"Confidence: {result.confidence:.1f}% | "
                        f"Hot Stock: {result.hot_stock_detected} | "
                        f"Bright Pixels: {result.bright_pixels}"
                    )
                    last_status_time = current_time

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stream.release()
            logger.info("CV Application stopped")

    def stop(self):
        """Stop the application"""
        self.running = False


def main():
    # Default config path - can be overridden with command line arg
    config_path = os.environ.get(
        "AIS_CV_CONFIG", str(Path(__file__).parent.parent / "config" / "settings.yaml")
    )

    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    if not Path(config_path).exists():
        print(f"ERROR: Config file not found: {config_path}")
        print(
            "Copy config/settings.template.yaml to config/settings.yaml and configure it."
        )
        sys.exit(1)

    app = CVApplication(config_path)

    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        app.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app.run()


if __name__ == "__main__":
    main()
