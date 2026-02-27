#!/usr/bin/env python3
"""
Mill Stand Zone Counter - Live RTSP Runner (Camera 3)
=====================================================
Runs MillStandCounter on camera 3 (channel=3) with live OpenCV display.

Detection:
  - Two rotated rectangle zones: LEFT and RIGHT
  - Bi-directional counting (L->R and R->L)
  - Zone coordinates loaded from config/settings.yaml (mill_stand.zones)

Display:
  - Live frame with LEFT (green) / RIGHT (red) zone overlays
  - Zones highlight when triggered
  - Count, direction totals, pending sequences shown top-right

Controls:
  Q / ESC   - Quit
  Space     - Pause / resume

Usage:
    python scripts/run_mill_stand_zone.py
    python scripts/run_mill_stand_zone.py --channel 3
    python scripts/run_mill_stand_zone.py --rtsp rtsp://...custom_url...
    python scripts/run_mill_stand_zone.py --no-display   (console only)
"""

import cv2
import yaml
import time
import sys
import argparse
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mill_stand_counter import MillStandCounter

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_mill_stand_zone")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config() -> dict:
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def build_rtsp_url(config: dict, channel: int) -> str:
    """Build RTSP URL using NVR base from existing camera config, override channel."""
    # Pull the NVR host/credentials from the primary camera URL as a base
    primary_url = config.get("camera", {}).get("rtsp_url", "")
    # Base: rtsp://admin:bhoothnath123@192.168.1.200:554/cam/realmonitor
    # Replace channel param
    if "channel=" in primary_url:
        import re
        url = re.sub(r"channel=\d+", f"channel={channel}", primary_url)
        # Ensure subtype=1 (sub-stream)
        url = re.sub(r"subtype=\d+", "subtype=1", url)
        return url
    # Fallback: construct from scratch
    return (
        f"rtsp://admin:bhoothnath123@192.168.1.200:554"
        f"/cam/realmonitor?channel={channel}&subtype=1"
    )


# ---------------------------------------------------------------------------
# Stream helpers
# ---------------------------------------------------------------------------
RECONNECT_DELAY = 5   # seconds between reconnect attempts
RECONNECT_MAX   = 10  # max consecutive failures before giving up (0 = infinite)


def open_stream(rtsp_url: str) -> cv2.VideoCapture:
    logger.info(f"Connecting to: {rtsp_url}")
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def is_stream_ok(cap: cv2.VideoCapture) -> bool:
    return cap is not None and cap.isOpened()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run(rtsp_url: str, zones_config: dict, counting_config: dict, display: bool):
    counter = MillStandCounter(
        zones_config=zones_config,
        counting_config=counting_config,
    )

    logger.info("MillStandCounter ready.")
    logger.info(f"  Zones: LEFT={zones_config.get('left')}  RIGHT={zones_config.get('right')}")
    logger.info(f"  Counting config: {counting_config}")
    logger.info(f"  Display: {'OpenCV window' if display else 'console only'}")
    logger.info("Press Q or ESC in the window to quit.")

    if display:
        cv2.namedWindow("Mill Stand - Camera 3", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Mill Stand - Camera 3", 1280, 720)

    cap = None
    fail_count = 0
    paused = False
    last_status = {}

    try:
        while True:
            # --- Connect / reconnect ---
            if not is_stream_ok(cap):
                if cap is not None:
                    cap.release()
                if RECONNECT_MAX and fail_count >= RECONNECT_MAX:
                    logger.error(f"Failed to reconnect after {RECONNECT_MAX} attempts. Exiting.")
                    break
                if fail_count > 0:
                    logger.info(f"Reconnect attempt {fail_count} in {RECONNECT_DELAY}s...")
                    time.sleep(RECONNECT_DELAY)
                cap = open_stream(rtsp_url)
                if not is_stream_ok(cap):
                    fail_count += 1
                    continue
                fail_count = 0
                logger.info("Stream connected.")

            # --- Handle pause ---
            if paused:
                if display:
                    key = cv2.waitKey(100) & 0xFF
                    if key in (ord('q'), 27):
                        break
                    if key == ord(' '):
                        paused = False
                        logger.info("Resumed.")
                continue

            # --- Read frame ---
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Frame read failed - reconnecting...")
                cap.release()
                cap = None
                fail_count += 1
                continue

            fail_count = 0  # reset on successful read

            # --- Process ---
            counted_piece, status = counter.process_frame(frame)
            last_status = status

            # --- Log counts ---
            if counted_piece is not None:
                arrow = "->" if counted_piece.direction == "LEFT_TO_RIGHT" else "<-"
                conf_label = (
                    "HIGH" if counted_piece.confidence >= 80 else
                    "MED"  if counted_piece.confidence >= 60 else "LOW"
                )
                logger.info(
                    f"*** PIECE #{counted_piece.count_id} | {arrow} | "
                    f"travel={counted_piece.travel_time:.2f}s | "
                    f"conf={counted_piece.confidence:.0f}% ({conf_label}) | "
                    f"total={counter.total_count}"
                )

            # --- Display ---
            if display:
                overlay = counter.draw_overlay(frame, status)
                cv2.imshow("Mill Stand - Camera 3", overlay)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), 27):  # Q or ESC
                    logger.info("Quit requested.")
                    break
                elif key == ord(' '):
                    paused = True
                    logger.info("Paused. Press Space to resume.")

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C).")

    finally:
        if cap is not None:
            cap.release()
        if display:
            cv2.destroyAllWindows()

        # --- Final stats ---
        stats = counter.get_stats()
        print()
        print("=" * 50)
        print("SESSION SUMMARY")
        print("=" * 50)
        print(f"  Total pieces   : {stats['total_count']}")
        print(f"  Left -> Right  : {stats['left_to_right']}")
        print(f"  Right -> Left  : {stats['right_to_left']}")
        if stats['total_count'] > 0:
            print(f"  Avg travel time: {stats['avg_travel_time']:.2f}s")
            print(f"  Avg confidence : {stats['avg_confidence']:.1f}%")
        print("=" * 50)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Live mill stand zone counter on camera 3 (channel=3)"
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=3,
        help="NVR channel number (default: 3)",
    )
    parser.add_argument(
        "--rtsp",
        type=str,
        default=None,
        help="Override full RTSP URL (ignores --channel)",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable OpenCV window (console output only)",
    )
    args = parser.parse_args()

    config = load_config()
    mill_cfg = config.get("mill_stand", {})

    zones_config = mill_cfg.get("zones", {})
    if not zones_config or "left" not in zones_config or "right" not in zones_config:
        logger.error("mill_stand.zones (left/right) not found in config/settings.yaml")
        sys.exit(1)

    counting_config = mill_cfg.get("counting", {})

    # Build RTSP URL
    if args.rtsp:
        rtsp_url = args.rtsp
    else:
        rtsp_url = build_rtsp_url(config, args.channel)

    logger.info(f"RTSP URL: {rtsp_url}")

    run(
        rtsp_url=rtsp_url,
        zones_config=zones_config,
        counting_config=counting_config,
        display=not args.no_display,
    )


if __name__ == "__main__":
    main()
