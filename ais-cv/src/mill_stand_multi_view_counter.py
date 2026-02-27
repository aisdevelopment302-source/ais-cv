#!/usr/bin/env python3
"""
Multi-View Mill Stand Counter
=============================
Counts pieces using three camera views with a two-line order check per view
and majority voting across views.

Logic per view:
- Line1 must confirm before Line2
- Reverse order (Line2 before Line1) is ignored until Line2 clears
"""

import cv2
import numpy as np
import time
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from collections import deque
import math

from mill_stand_line_counter import (
    Stand,
    StandConfig,
    LineConfig,
    StandDetection,
    VotingWindow,
    PieceCount,
)

logger = logging.getLogger(__name__)


@dataclass
class ViewState:
    view_id: str
    name: str
    index: int
    rtsp_url: str
    resolution: Optional[Tuple[int, int]]
    stand: Stand
    target_resolution: Tuple[int, int]
    roi: Optional[Dict[str, List[int]]] = None
    initialized: bool = False
    original_resolution: Optional[Tuple[int, int]] = None
    roi_box: Optional[Tuple[int, int, int, int]] = None
    roi_applied: bool = False

    def _normalize_roi(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        if not self.roi:
            return None

        start = self.roi.get("start")
        end = self.roi.get("end")
        if not start or not end:
            return None

        x1, y1 = start
        x2, y2 = end
        min_x = max(0, min(x1, x2))
        max_x = min(frame.shape[1], max(x1, x2))
        min_y = max(0, min(y1, y2))
        max_y = min(frame.shape[0], max(y1, y2))

        if max_x - min_x <= 1 or max_y - min_y <= 1:
            return None

        return (min_x, min_y, max_x, max_y)

    def _init_resolution(self, frame: np.ndarray):
        if self.initialized:
            return

        orig_h, orig_w = frame.shape[:2]
        full_resolution = (orig_w, orig_h)
        self.original_resolution = full_resolution
        self.roi_box = self._normalize_roi(frame)

        if self.roi_box:
            roi_w = self.roi_box[2] - self.roi_box[0]
            roi_h = self.roi_box[3] - self.roi_box[1]
            self.original_resolution = (roi_w, roi_h)
            if not self.roi_applied:
                offset_x, offset_y = self.roi_box[0], self.roi_box[1]

                def shift(line: Tuple[Tuple[int, int], Tuple[int, int]]):
                    return (
                        (line[0][0] - offset_x, line[0][1] - offset_y),
                        (line[1][0] - offset_x, line[1][1] - offset_y),
                    )

                self.stand.original_entry_line = shift(self.stand.original_entry_line)
                self.stand.original_exit_line = shift(self.stand.original_exit_line)
                self.roi_applied = True

        if self.resolution and tuple(self.resolution) != full_resolution:
            logger.warning(
                f"View '{self.name}' resolution mismatch: "
                f"config={self.resolution}, stream={full_resolution}"
            )

        self.stand.scale_lines(self.original_resolution, self.target_resolution)
        self.initialized = True

        logger.info(
            f"View '{self.name}' initialized: {self.original_resolution} -> {self.target_resolution}"
        )

    def process_frame(
        self, frame: np.ndarray, current_time: float
    ) -> Tuple[Optional[StandDetection], Dict, np.ndarray]:
        self._init_resolution(frame)

        frame_in = frame
        if self.roi_box:
            x1, y1, x2, y2 = self.roi_box
            roi_frame = frame[y1:y2, x1:x2]
            if roi_frame.size > 0:
                frame_in = roi_frame

        resized = cv2.resize(
            frame_in, self.target_resolution, interpolation=cv2.INTER_AREA
        )
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        detection, status = self.stand.process_frame(gray, resized, current_time)
        return detection, status, resized

    def draw_overlay(self, frame: np.ndarray, status: Dict) -> np.ndarray:
        overlay = frame.copy()

        if self.stand.entry_line is None or self.stand.exit_line is None:
            return overlay

        line1_color = (0, 255, 0)
        line2_color = (0, 165, 255)

        line1_thickness = 3 if status.get("entry_triggered") else 2
        line2_thickness = 3 if status.get("exit_triggered") else 2

        if status.get("entry_triggered"):
            line1_color = tuple(min(255, c + 80) for c in line1_color)
        if status.get("exit_triggered"):
            line2_color = tuple(min(255, c + 80) for c in line2_color)

        cv2.line(
            overlay,
            self.stand.entry_line[0],
            self.stand.entry_line[1],
            line1_color,
            line1_thickness,
        )
        cv2.line(
            overlay,
            self.stand.exit_line[0],
            self.stand.exit_line[1],
            line2_color,
            line2_thickness,
        )

        label = self.name
        if status.get("pending"):
            label += " [PENDING]"
        if status.get("reverse_blocked"):
            label += " [REVERSE]"

        label_pos = (
            min(self.stand.entry_line[0][0], self.stand.exit_line[0][0]),
            min(self.stand.entry_line[0][1], self.stand.exit_line[0][1]) - 10,
        )
        cv2.putText(
            overlay, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
        )

        count_text = f"#{status.get('detection_count', 0)}"
        count_pos = (
            max(self.stand.entry_line[1][0], self.stand.exit_line[1][0]) + 5,
            max(self.stand.entry_line[1][1], self.stand.exit_line[1][1]),
        )
        cv2.putText(
            overlay,
            count_text,
            count_pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
        )

        return overlay


class MultiViewLineCounter:
    def __init__(
        self,
        views_config: List[dict],
        counting_config: Optional[dict] = None,
        voting_config: Optional[dict] = None,
        target_resolution: Optional[Tuple[int, int]] = None,
    ):
        counting_config = counting_config or {}
        voting_config = voting_config or {}

        self.target_resolution = target_resolution or tuple(
            counting_config.get("target_resolution", [704, 576])
        )

        self.views: List[ViewState] = []
        for i, view_cfg in enumerate(views_config):
            view_name = view_cfg.get("name", f"View {i + 1}")
            camera_cfg = view_cfg.get("camera", {})
            rtsp_url = camera_cfg.get("rtsp_url", "")
            resolution = camera_cfg.get("resolution")
            resolution_tuple = tuple(resolution) if resolution else None
            roi = view_cfg.get("roi")

            stand_config = StandConfig(
                name=view_name,
                direction="line1_to_line2",
                entry_line=LineConfig.from_dict(view_cfg["line1"]),
                exit_line=LineConfig.from_dict(view_cfg["line2"]),
            )

            view_id = f"view_{i + 1}"
            stand = Stand(view_id, i, stand_config, counting_config)
            self.views.append(
                ViewState(
                    view_id=view_id,
                    name=view_name,
                    index=i,
                    rtsp_url=rtsp_url,
                    resolution=resolution_tuple,
                    stand=stand,
                    target_resolution=self.target_resolution,
                    roi=roi,
                )
            )

        self.num_views = len(self.views)

        self.voting_window_seconds = voting_config.get("window_seconds", 5.0)
        self.min_views_required = voting_config.get("min_stands_required", None)
        if self.min_views_required is None:
            self.min_views_required = math.ceil(self.num_views / 2)

        self.voting_windows: deque = deque(maxlen=50)
        self.next_window_id = 1

        self.total_count = 0
        self.counted_pieces: List[PieceCount] = []

        logger.info("MultiViewLineCounter initialized:")
        logger.info(f"  Views: {self.num_views}")
        for view in self.views:
            logger.info(f"    - {view.name}")
        logger.info(f"  Voting: {self.min_views_required}/{self.num_views} required")
        logger.info(f"  Voting window: {self.voting_window_seconds}s")
        logger.info(f"  Target resolution: {self.target_resolution}")

    def _find_or_create_voting_window(
        self, detection: StandDetection, current_time: float
    ) -> VotingWindow:
        for window in self.voting_windows:
            if window.finalized:
                continue

            window_age = current_time - window.start_time
            if window_age > self.voting_window_seconds:
                continue

            existing_views = {d.stand_id for d in window.detections}
            if detection.stand_id in existing_views:
                continue

            return window

        window = VotingWindow(
            window_id=self.next_window_id,
            start_time=current_time,
            detections=[],
        )
        self.next_window_id += 1
        self.voting_windows.append(window)
        return window

    def _process_voting_windows(self, current_time: float) -> Optional[PieceCount]:
        counted_piece = None

        for window in list(self.voting_windows):
            if window.finalized:
                continue

            window_age = current_time - window.start_time
            if window_age < self.voting_window_seconds:
                continue

            window.finalized = True
            vote_passed = window.get_vote_result(
                self.num_views, self.min_views_required
            )

            views_detected = window.get_stands_detected()
            vote_ratio = f"{len(views_detected)}/{self.num_views}"

            if vote_passed:
                self.total_count += 1

                avg_travel = np.mean([d.travel_time for d in window.detections])
                avg_confidence = np.mean([d.confidence for d in window.detections])

                counted_piece = PieceCount(
                    count_id=self.total_count,
                    timestamp=current_time,
                    stands_detected=views_detected,
                    total_stands=self.num_views,
                    vote_ratio=vote_ratio,
                    avg_travel_time=float(avg_travel),
                    avg_confidence=float(avg_confidence),
                    detections=list(window.detections),
                )
                self.counted_pieces.append(counted_piece)

                logger.info(
                    f"*** PIECE #{self.total_count} COUNTED | "
                    f"Vote: {vote_ratio} | "
                    f"Views: {', '.join(views_detected)} | "
                    f"Avg travel: {avg_travel:.2f}s ***"
                )
            else:
                logger.debug(
                    f"Voting window {window.window_id} failed: {vote_ratio} "
                    f"(need {self.min_views_required})"
                )

        while self.voting_windows and self.voting_windows[0].finalized:
            old_window = self.voting_windows[0]
            window_age = current_time - old_window.start_time
            if window_age > self.voting_window_seconds * 2:
                self.voting_windows.popleft()
            else:
                break

        return counted_piece

    def process_frames(
        self, frames: List[np.ndarray]
    ) -> Tuple[Optional[PieceCount], Dict, List[np.ndarray]]:
        current_time = time.time()

        status: Dict[str, Any] = {"views": {}}
        resized_frames: List[np.ndarray] = []

        for view, frame in zip(self.views, frames):
            detection, view_status, resized = view.process_frame(frame, current_time)
            status["views"][view.view_id] = view_status
            resized_frames.append(resized)

            if detection is not None:
                window = self._find_or_create_voting_window(detection, current_time)
                window.add_detection(detection)

        counted_piece = self._process_voting_windows(current_time)

        status["total_count"] = self.total_count
        status["active_voting_windows"] = sum(
            1 for w in self.voting_windows if not w.finalized
        )

        return counted_piece, status, resized_frames

    def draw_combined_overlay(
        self, overlays: List[np.ndarray], status: Dict
    ) -> np.ndarray:
        combined = np.hstack(overlays)
        frame_w = combined.shape[1]

        box_width = 240
        box_x = frame_w - box_width - 5
        cv2.rectangle(combined, (box_x, 5), (frame_w - 5, 90), (0, 0, 0), -1)
        cv2.putText(
            combined,
            f"COUNT: {self.total_count}",
            (box_x + 5, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            combined,
            f"Voting: {self.min_views_required}/{self.num_views}",
            (box_x + 5, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        cv2.putText(
            combined,
            f"Active windows: {status.get('active_voting_windows', 0)}",
            (box_x + 5, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )

        return combined

    def get_stats(self) -> Dict:
        if not self.counted_pieces:
            return {
                "total_count": 0,
                "avg_travel_time": 0,
                "avg_confidence": 0,
                "view_detection_counts": {v.view_id: 0 for v in self.views},
            }

        travel_times = [p.avg_travel_time for p in self.counted_pieces]
        confidences = [p.avg_confidence for p in self.counted_pieces]

        view_counts = {v.view_id: 0 for v in self.views}
        for piece in self.counted_pieces:
            for view_id in piece.stands_detected:
                view_counts[view_id] += 1

        return {
            "total_count": self.total_count,
            "avg_travel_time": float(np.mean(travel_times)),
            "min_travel_time": float(np.min(travel_times)),
            "max_travel_time": float(np.max(travel_times)),
            "avg_confidence": float(np.mean(confidences)),
            "view_detection_counts": view_counts,
        }

    def reset(self):
        self.total_count = 0
        self.counted_pieces = []
        self.voting_windows.clear()
        self.next_window_id = 1

        for view in self.views:
            view.stand.reset()

        logger.info("MultiViewLineCounter reset")
