#!/usr/bin/env python3
"""
Mill Stand Counter Test Script
==============================
Test the MillStandCounter on recorded video file.

Usage:
    python scripts/test_mill_stand.py                     # Run with defaults
    python scripts/test_mill_stand.py --display           # Show visual output
    python scripts/test_mill_stand.py --output counts.csv # Save to CSV
    python scripts/test_mill_stand.py --start 00:10:00    # Start at timestamp
    python scripts/test_mill_stand.py --end 00:20:00      # End at timestamp
    python scripts/test_mill_stand.py --test              # Verbose output
"""

import cv2
import yaml
import time
import sys
import argparse
import logging
import csv
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mill_stand_counter import MillStandCounter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def parse_timestamp(ts_str: str) -> float:
    """Parse timestamp string (HH:MM:SS or MM:SS) to seconds."""
    if not ts_str:
        return 0.0

    parts = ts_str.split(":")
    if len(parts) == 3:
        h, m, s = map(float, parts)
        return h * 3600 + m * 60 + s
    elif len(parts) == 2:
        m, s = map(float, parts)
        return m * 60 + s
    else:
        return float(parts[0])


def format_timestamp(seconds: float) -> str:
    """Format seconds to HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def load_config():
    """Load configuration from settings.yaml."""
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    if not config_path.exists():
        # Try template if settings.yaml doesn't exist
        config_path = PROJECT_ROOT / "config" / "settings.template.yaml"
        logger.warning(f"settings.yaml not found, using template")

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_test(
    video_path: str = None,
    display: bool = False,
    output_csv: str = None,
    start_time: str = None,
    end_time: str = None,
    test_mode: bool = False,
    speed: float = 1.0,
):
    """Run the mill stand counter on a video file."""

    # Load config
    config = load_config()

    # Get mill stand config (with defaults if not present)
    mill_stand_config = config.get("mill_stand", {})

    # Default zones if not configured (will need calibration)
    zones_config = mill_stand_config.get(
        "zones",
        {
            "left": {"x": 200, "y": 300, "width": 150, "height": 250},
            "right": {"x": 1550, "y": 300, "width": 150, "height": 250},
        },
    )

    counting_config = mill_stand_config.get("counting", {})

    # Video path
    if not video_path:
        video_path = mill_stand_config.get(
            "video_file", "recordings/mill stand view.mp4"
        )

    video_full_path = PROJECT_ROOT / video_path
    if not video_full_path.exists():
        logger.error(f"Video file not found: {video_full_path}")
        return None

    logger.info(f"Loading video: {video_full_path}")

    # Initialize counter
    counter = MillStandCounter(
        zones_config=zones_config, counting_config=counting_config
    )

    # Open video
    cap = cv2.VideoCapture(str(video_full_path))
    if not cap.isOpened():
        logger.error("Failed to open video file")
        return None

    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    logger.info(
        f"Video: {width}x{height} @ {fps:.1f} FPS, Duration: {format_timestamp(duration)}"
    )

    # Parse time range
    start_sec = parse_timestamp(start_time) if start_time else 0
    end_sec = parse_timestamp(end_time) if end_time else duration

    if start_sec > 0:
        start_frame = int(start_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        logger.info(f"Starting at {format_timestamp(start_sec)} (frame {start_frame})")

    logger.info(
        f"Processing: {format_timestamp(start_sec)} to {format_timestamp(end_sec)}"
    )

    # Setup CSV output
    csv_file = None
    csv_writer = None
    if output_csv:
        csv_file = open(output_csv, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(
            [
                "count_id",
                "video_time",
                "direction",
                "travel_time",
                "confidence",
                "entry_zone",
                "exit_zone",
                "entry_pixels",
                "exit_pixels",
            ]
        )

    # Setup display window
    if display:
        cv2.namedWindow("Mill Stand Counter", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Mill Stand Counter", 1024, 576)

    # Processing loop
    frame_num = int(start_sec * fps)
    last_log_time = time.time()
    processing_start = time.time()

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_num += 1
            video_time = frame_num / fps if fps > 0 else 0

            # Check end time
            if video_time > end_sec:
                break

            # Process frame
            counted_piece, status = counter.process_frame(frame)

            # Handle counted piece
            if counted_piece:
                ts = format_timestamp(video_time)
                direction_arrow = (
                    "->" if counted_piece.direction == "LEFT_TO_RIGHT" else "<-"
                )

                logger.info(
                    f"[{ts}] PIECE #{counted_piece.count_id} | "
                    f"Dir: {direction_arrow} | "
                    f"Travel: {counted_piece.travel_time:.2f}s | "
                    f"Conf: {counted_piece.confidence:.0f}%"
                )

                if csv_writer:
                    csv_writer.writerow(
                        [
                            counted_piece.count_id,
                            ts,
                            counted_piece.direction,
                            f"{counted_piece.travel_time:.2f}",
                            f"{counted_piece.confidence:.0f}",
                            counted_piece.entry_zone,
                            counted_piece.exit_zone,
                            counted_piece.entry_max_pixels,
                            counted_piece.exit_max_pixels,
                        ]
                    )

            # Test mode: print detection status
            if test_mode:
                if status["LEFT"]["triggered"] or status["RIGHT"]["triggered"]:
                    ts = format_timestamp(video_time)
                    left_px = (
                        f"{status['LEFT']['pixels']}px"
                        if status["LEFT"]["triggered"]
                        else "-"
                    )
                    right_px = (
                        f"{status['RIGHT']['pixels']}px"
                        if status["RIGHT"]["triggered"]
                        else "-"
                    )
                    print(
                        f"{ts} | L:{left_px:>6} | R:{right_px:>6} | Count:{status['total_count']}"
                    )

            # Display
            if display:
                overlay = counter.draw_overlay(frame, status)

                # Add video timestamp
                ts_text = f"Video: {format_timestamp(video_time)} / {format_timestamp(duration)}"
                cv2.putText(
                    overlay,
                    ts_text,
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                )

                cv2.imshow("Mill Stand Counter", overlay)

                # Handle keyboard
                wait_ms = max(1, int(1000 / fps / speed)) if speed > 0 else 1
                key = cv2.waitKey(wait_ms) & 0xFF

                if key == ord("q") or key == 27:  # Q or ESC
                    logger.info("Stopped by user")
                    break
                elif key == ord(" "):  # Space - pause
                    logger.info("Paused - press any key to continue")
                    cv2.waitKey(0)
                elif key == ord("+") or key == ord("="):
                    speed = min(speed * 1.5, 10.0)
                    logger.info(f"Speed: {speed:.1f}x")
                elif key == ord("-"):
                    speed = max(speed / 1.5, 0.1)
                    logger.info(f"Speed: {speed:.1f}x")

            # Periodic status log (every 30 seconds of video)
            if video_time - (start_sec + (time.time() - processing_start) * 0) > 0:
                current_time = time.time()
                if current_time - last_log_time >= 10:  # Log every 10 seconds real time
                    progress = (video_time - start_sec) / (end_sec - start_sec) * 100
                    logger.info(
                        f"Progress: {progress:.1f}% | "
                        f"Video: {format_timestamp(video_time)} | "
                        f"Count: {counter.total_count}"
                    )
                    last_log_time = current_time

    except KeyboardInterrupt:
        logger.info("Interrupted by user")

    finally:
        cap.release()
        if display:
            cv2.destroyAllWindows()
        if csv_file:
            csv_file.close()
            logger.info(f"Counts saved to: {output_csv}")

    # Final statistics
    stats = counter.get_stats()
    elapsed = time.time() - processing_start
    processed_duration = min(video_time, end_sec) - start_sec

    logger.info("=" * 60)
    logger.info("FINAL RESULTS")
    logger.info("=" * 60)
    logger.info(f"Total pieces counted: {stats['total_count']}")
    logger.info(f"  Left-to-Right (->): {stats['left_to_right']}")
    logger.info(f"  Right-to-Left (<-): {stats['right_to_left']}")

    if stats["total_count"] > 0:
        logger.info(
            f"Travel time: avg={stats['avg_travel_time']:.2f}s, "
            f"min={stats['min_travel_time']:.2f}s, max={stats['max_travel_time']:.2f}s"
        )
        logger.info(f"Avg confidence: {stats['avg_confidence']:.1f}%")

        # Calculate rate
        if processed_duration > 0:
            pieces_per_minute = stats["total_count"] / (processed_duration / 60)
            logger.info(f"Rate: {pieces_per_minute:.1f} pieces/minute")

    logger.info(
        f"Processed {format_timestamp(processed_duration)} of video in {elapsed:.1f}s real time"
    )
    logger.info(f"Processing speed: {processed_duration / elapsed:.1f}x real-time")
    logger.info("=" * 60)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Test Mill Stand Counter on video file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_mill_stand.py                        # Process entire video
  python test_mill_stand.py --display              # Show visual output
  python test_mill_stand.py --start 00:10:00       # Start at 10 minutes
  python test_mill_stand.py --output counts.csv   # Save counts to CSV
  python test_mill_stand.py --test                 # Verbose detection output
        """,
    )

    parser.add_argument(
        "--video", type=str, help="Path to video file (relative to project root)"
    )
    parser.add_argument("--display", action="store_true", help="Show visual output")
    parser.add_argument("--output", type=str, help="Output CSV file for counts")
    parser.add_argument("--start", type=str, help="Start timestamp (HH:MM:SS or MM:SS)")
    parser.add_argument("--end", type=str, help="End timestamp (HH:MM:SS or MM:SS)")
    parser.add_argument("--test", action="store_true", help="Verbose detection output")
    parser.add_argument(
        "--speed", type=float, default=1.0, help="Playback speed for display mode"
    )

    args = parser.parse_args()

    run_test(
        video_path=args.video,
        display=args.display,
        output_csv=args.output,
        start_time=args.start,
        end_time=args.end,
        test_mode=args.test,
        speed=args.speed,
    )


if __name__ == "__main__":
    main()
