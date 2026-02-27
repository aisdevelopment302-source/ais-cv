#!/usr/bin/env python3
"""
Multi-View Mill Stand Counter Runner
====================================
Runs three RTSP views with a two-line order check per view and majority voting.
"""

import cv2
import yaml
import time
import sys
import argparse
import logging
import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mill_stand_multi_view_counter import MultiViewLineCounter


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_env(env_path: Path):
    if not env_path.exists():
        return

    with open(env_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


def open_stream(rtsp_url: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def run_multi_view(
    display: bool = False,
    output_path: Optional[str] = None,
    min_views: Optional[int] = None,
    voting_window: Optional[float] = None,
    duration: Optional[int] = None,
    view_index: Optional[int] = None,
):
    load_env(PROJECT_ROOT / ".env")
    config = load_config()
    mill_config = config.get("mill_stand_lines", {})

    if not mill_config.get("enabled", False):
        logger.warning("mill_stand_lines is not enabled in config, but proceeding")

    views_config_all = mill_config.get("views", [])
    if not views_config_all:
        logger.error("No views configured in mill_stand_lines.views")
        sys.exit(1)

    if view_index is not None:
        if view_index < 1 or view_index > len(views_config_all):
            logger.error(
                f"Invalid view index {view_index}. Must be 1-{len(views_config_all)}"
            )
            sys.exit(1)
        selected_indices = [view_index - 1]
        views_config = [views_config_all[view_index - 1]]
        if min_views is None:
            min_views = 1
            logger.info("Single-view mode: forcing min_views=1")
    else:
        views_config = views_config_all
        selected_indices = list(range(len(views_config_all)))

    counting_config = mill_config.get("counting", {})
    voting_config = mill_config.get("voting", {})
    if voting_window is not None:
        voting_config["window_seconds"] = voting_window
    if min_views is not None:
        voting_config["min_stands_required"] = min_views

    counter = MultiViewLineCounter(
        views_config=views_config,
        counting_config=counting_config,
        voting_config=voting_config,
    )

    caps = []
    for view_cfg, original_idx in zip(views_config, selected_indices):
        camera_cfg = view_cfg.get("camera", {})
        env_key = f"RTSP_VIEW{original_idx + 1}_URL"
        rtsp_url = os.getenv(env_key, camera_cfg.get("rtsp_url"))
        if not rtsp_url:
            logger.error("Missing rtsp_url in view camera config")
            sys.exit(1)

        cap = open_stream(rtsp_url)
        if not cap.isOpened():
            logger.error(f"Failed to open stream: {rtsp_url}")
            sys.exit(1)
        caps.append(cap)

    fps_values = []
    for cap in caps:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        fps_values.append(fps)
    fps_target = min(fps_values) if fps_values else 25

    out_writer = None
    if output_path:
        frame_w = counter.target_resolution[0] * len(counter.views)
        frame_h = counter.target_resolution[1]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out_writer = cv2.VideoWriter(
            output_path, fourcc, fps_target, (frame_w, frame_h)
        )
        logger.info(f"Output video: {output_path}")

    if display:
        cv2.namedWindow("Mill Stand Multi-View", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Mill Stand Multi-View", 1280, 480)

    start_time = time.time()
    last_log_time = start_time

    logger.info("Processing started... (press 'q' to quit)")

    try:
        while True:
            elapsed = time.time() - start_time
            if duration and elapsed >= duration:
                break

            frames = []
            stream_failed = False
            for cap in caps:
                ret, frame = cap.read()
                if not ret:
                    stream_failed = True
                    break
                frames.append(frame)

            if stream_failed:
                logger.warning("Frame read failed, retrying...")
                time.sleep(0.2)
                continue

            counted_piece, status, resized_frames = counter.process_frames(frames)

            overlays = []
            for view, resized in zip(counter.views, resized_frames):
                view_status = status["views"].get(view.view_id, {})
                overlay = view.draw_overlay(resized, view_status)
                overlays.append(overlay)

            combined = counter.draw_combined_overlay(overlays, status)

            if out_writer:
                out_writer.write(combined)

            if display:
                cv2.imshow("Mill Stand Multi-View", combined)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
                    logger.info("User quit")
                    break

            if counted_piece:
                logger.info(
                    f"Counted piece #{counted_piece.count_id} "
                    f"({counted_piece.vote_ratio})"
                )

            now = time.time()
            if now - last_log_time >= 10.0:
                logger.info(
                    f"Status: {counter.total_count} pieces | "
                    f"Active windows: {status.get('active_voting_windows', 0)}"
                )
                last_log_time = now

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        for cap in caps:
            cap.release()
        if out_writer:
            out_writer.release()
        if display:
            cv2.destroyAllWindows()

    stats = counter.get_stats()
    logger.info("=" * 50)
    logger.info(f"FINAL COUNT: {stats['total_count']} pieces")
    if stats["total_count"] > 0:
        logger.info(f"Avg travel time: {stats['avg_travel_time']:.2f}s")
    logger.info("=" * 50)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Run multi-view mill stand counter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="Show real-time visualization window",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save annotated combined video to file",
    )
    parser.add_argument(
        "--min-views",
        type=int,
        help="Minimum views required to count (default: majority)",
    )
    parser.add_argument(
        "--voting-window",
        type=float,
        help="Voting window duration in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--view",
        type=int,
        help="Run a single view by index (1-based)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Run duration in seconds",
    )

    args = parser.parse_args()

    run_multi_view(
        display=args.display,
        output_path=args.output,
        min_views=args.min_views,
        voting_window=args.voting_window,
        duration=args.duration,
        view_index=args.view,
    )


if __name__ == "__main__":
    main()
