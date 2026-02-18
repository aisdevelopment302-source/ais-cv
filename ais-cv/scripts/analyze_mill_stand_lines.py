#!/usr/bin/env python3
"""
Mill Stand Line Counter - Video Analysis Script
================================================
Analyzes video footage using the line-based mill stand counter with majority voting.

Features:
- Multi-stand line detection (2 lines per stand: entry + exit)
- Majority voting across stands (e.g., 2/3 = count, 1/3 = ignore)
- Real-time visualization with detection overlays
- Detailed statistics and logging

Usage:
    # Basic usage with default settings
    python scripts/analyze_mill_stand_lines.py --video "recordings/mill stand view.mp4"
    
    # With display window
    python scripts/analyze_mill_stand_lines.py --video "path/to/video.mp4" --display
    
    # Adjust voting threshold
    python scripts/analyze_mill_stand_lines.py --video "path/to/video.mp4" --min-stands 2
    
    # Adjust detection parameters
    python scripts/analyze_mill_stand_lines.py --video "path/to/video.mp4" \\
        --luminosity-threshold 160 --min-bright-pixels 100
    
    # Save output video
    python scripts/analyze_mill_stand_lines.py --video "path/to/video.mp4" \\
        --output "output_counted.mp4"

Arguments:
    --video             Path to input video file (required)
    --display           Show real-time visualization window
    --output            Save annotated video to file
    --min-stands        Minimum stands required to count (default: majority)
    --voting-window     Voting window duration in seconds (default: 5.0)
    --luminosity-threshold  Brightness threshold (0-255, default: from config)
    --min-bright-pixels     Minimum bright pixels to trigger (default: from config)
    --start-frame       Start processing from this frame
    --end-frame         Stop processing at this frame
    --speed             Playback speed multiplier (default: 1.0)
"""

import cv2
import yaml
import sys
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mill_stand_line_counter import MillStandLineCounter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load configuration from settings.yaml"""
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def analyze_video(
    video_path: str,
    display: bool = False,
    output_path: str = None,
    min_stands: int = None,
    voting_window: float = None,
    luminosity_threshold: int = None,
    min_bright_pixels: int = None,
    start_frame: int = 0,
    end_frame: int = None,
    speed: float = 1.0,
):
    """
    Analyze video using line-based mill stand counter.
    """
    # Load config
    config = load_config()
    mill_config = config.get("mill_stand_lines", {})

    if not mill_config.get("enabled", False):
        logger.warning(
            "mill_stand_lines is not enabled in config, but proceeding anyway"
        )

    # Get stands configuration
    stands_config = mill_config.get("stands", [])
    if not stands_config:
        logger.error("No stands configured in mill_stand_lines.stands")
        sys.exit(1)

    # Get counting configuration
    counting_config = mill_config.get("counting", {})

    # Override with command-line arguments
    if luminosity_threshold is not None:
        counting_config["luminosity_threshold"] = luminosity_threshold
    if min_bright_pixels is not None:
        counting_config["min_bright_pixels"] = min_bright_pixels

    # Get voting configuration
    voting_config = mill_config.get("voting", {})
    if voting_window is not None:
        voting_config["window_seconds"] = voting_window
    if min_stands is not None:
        voting_config["min_stands_required"] = min_stands

    # Initialize counter
    counter = MillStandLineCounter(
        stands_config=stands_config,
        counting_config=counting_config,
        voting_config=voting_config,
    )

    # Open video
    video_path = Path(video_path)
    if not video_path.exists():
        # Try relative to project root
        video_path = PROJECT_ROOT / video_path
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            sys.exit(1)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error(f"Failed to open video: {video_path}")
        sys.exit(1)

    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps

    logger.info(f"Video: {video_path.name}")
    logger.info(f"  Resolution: {width}x{height} @ {fps:.1f} FPS")
    logger.info(
        f"  Duration: {int(duration // 60)}:{int(duration % 60):02d} ({total_frames} frames)"
    )
    logger.info(f"  Stands: {len(stands_config)}")
    logger.info(
        f"  Voting: {voting_config.get('min_stands_required', 'majority')}/{len(stands_config)} required"
    )

    # Setup output video writer
    out_writer = None
    if output_path:
        target_res = counting_config.get("target_resolution", [704, 576])
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out_writer = cv2.VideoWriter(output_path, fourcc, fps, tuple(target_res))
        logger.info(f"Output video: {output_path}")

    # Setup display window
    if display:
        cv2.namedWindow("Mill Stand Line Counter", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Mill Stand Line Counter", 1280, 720)

    # Set start position
    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        logger.info(f"Starting from frame {start_frame}")

    if end_frame is None:
        end_frame = total_frames

    # Processing loop
    frame_num = start_frame
    start_time = time.time()
    last_log_time = start_time
    paused = False

    logger.info("Processing started... (press 'q' to quit, 'space' to pause)")

    while frame_num < end_frame:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break

            # Process frame
            counted_piece, status = counter.process_frame(frame)

            # Draw overlay
            overlay = counter.draw_overlay(frame, status)

            # Save to output video
            if out_writer:
                out_writer.write(overlay)

            frame_num += 1

        # Display
        if display:
            cv2.imshow("Mill Stand Line Counter", overlay)

            # Calculate wait time based on speed
            wait_time = max(1, int((1000 / fps) / speed)) if not paused else 30
            key = cv2.waitKey(wait_time) & 0xFF

            if key == ord("q") or key == 27:  # Q or ESC
                logger.info("User quit")
                break
            elif key == ord(" "):  # Space to pause
                paused = not paused
                logger.info("Paused" if paused else "Resumed")
            elif key == ord("+") or key == ord("="):
                speed = min(10.0, speed * 1.5)
                logger.info(f"Speed: {speed:.1f}x")
            elif key == ord("-"):
                speed = max(0.1, speed / 1.5)
                logger.info(f"Speed: {speed:.1f}x")

        # Periodic logging
        current_time = time.time()
        if current_time - last_log_time >= 10.0:
            progress = (frame_num - start_frame) / (end_frame - start_frame) * 100
            elapsed = current_time - start_time
            fps_actual = (frame_num - start_frame) / elapsed if elapsed > 0 else 0

            logger.info(
                f"Progress: {progress:.1f}% | Frame: {frame_num}/{end_frame} | "
                f"Count: {counter.total_count} | FPS: {fps_actual:.1f}"
            )
            last_log_time = current_time

    # Cleanup
    cap.release()
    if out_writer:
        out_writer.release()
    if display:
        cv2.destroyAllWindows()

    # Final statistics
    elapsed = time.time() - start_time
    stats = counter.get_stats()

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"  Video: {video_path.name}")
    print(f"  Frames processed: {frame_num - start_frame}")
    print(
        f"  Processing time: {elapsed:.1f}s ({(frame_num - start_frame) / elapsed:.1f} FPS)"
    )
    print()
    print(f"  TOTAL COUNT: {stats['total_count']}")
    print()
    if stats["total_count"] > 0:
        print(f"  Average travel time: {stats['avg_travel_time']:.2f}s")
        print(
            f"  Travel time range: {stats['min_travel_time']:.2f}s - {stats['max_travel_time']:.2f}s"
        )
        print(f"  Average confidence: {stats['avg_confidence']:.1f}%")
        print()
        print("  Per-stand detection counts:")
        for stand_id, count in stats["stand_detection_counts"].items():
            stand_name = next(
                (
                    s["name"]
                    for i, s in enumerate(stands_config)
                    if f"stand_{i + 1}" == stand_id
                ),
                stand_id,
            )
            print(f"    {stand_name}: {count}")
    print("=" * 60)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Analyze video using line-based mill stand counter with majority voting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --video "recordings/mill stand view.mp4" --display
  %(prog)s --video "path/to/video.mp4" --min-stands 2 --output "counted.mp4"
        """,
    )

    parser.add_argument(
        "--video",
        type=str,
        required=True,
        help="Path to input video file",
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="Show real-time visualization window",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save annotated video to file",
    )
    parser.add_argument(
        "--min-stands",
        type=int,
        help="Minimum stands required to count (default: majority)",
    )
    parser.add_argument(
        "--voting-window",
        type=float,
        help="Voting window duration in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--luminosity-threshold",
        type=int,
        help="Brightness threshold 0-255 (default: from config)",
    )
    parser.add_argument(
        "--min-bright-pixels",
        type=int,
        help="Minimum bright pixels to trigger (default: from config)",
    )
    parser.add_argument(
        "--start-frame",
        type=int,
        default=0,
        help="Start processing from this frame",
    )
    parser.add_argument(
        "--end-frame",
        type=int,
        help="Stop processing at this frame",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed multiplier (default: 1.0)",
    )

    args = parser.parse_args()

    analyze_video(
        video_path=args.video,
        display=args.display,
        output_path=args.output,
        min_stands=args.min_stands,
        voting_window=args.voting_window,
        luminosity_threshold=args.luminosity_threshold,
        min_bright_pixels=args.min_bright_pixels,
        start_frame=args.start_frame,
        end_frame=args.end_frame,
        speed=args.speed,
    )


if __name__ == "__main__":
    main()
