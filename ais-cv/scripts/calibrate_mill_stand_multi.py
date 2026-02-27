#!/usr/bin/env python3
"""
Multi-View Mill Stand Line Calibration Tool
===========================================
Calibrate line1/line2 per view using RTSP inputs in a single window.

Controls:
  1/2/3        - Select active view
  L            - Select Line1 (green)
  K            - Select Line2 (orange)
  A            - Select START point (lines)
  D            - Select END point (lines)
  O            - Toggle ROI edit mode
  Z            - Select ROI START point
  X            - Select ROI END point
  Drag         - Draw ROI rectangle
  Click        - Place selected point
  T            - Toggle live test mode
  R            - Reset lines for active view
  S            - Save to settings.yaml
  Q/ESC        - Quit
"""

import cv2
import numpy as np
import yaml
import sys
import os
from pathlib import Path
from typing import List, Optional, Tuple


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mill_stand_multi_view_counter import MultiViewLineCounter


class ViewCalState:
    def __init__(self, view_id: str, view_config: dict):
        self.view_id = view_id
        self.name = view_config.get("name", view_id)
        self.camera = view_config.get("camera", {})
        self.line1 = view_config.get("line1", {"start": [0, 0], "end": [0, 0]})
        self.line2 = view_config.get("line2", {"start": [0, 0], "end": [0, 0]})
        self.roi = view_config.get("roi")
        self.cap: Optional[cv2.VideoCapture] = None
        self.last_frame: Optional[np.ndarray] = None

    @property
    def rtsp_url(self) -> str:
        return self.camera.get("rtsp_url", "")


class MultiViewLineCalibrator:
    def __init__(self):
        self.config_path = PROJECT_ROOT / "config" / "settings.yaml"
        self.views: List[ViewCalState] = []
        self.active_view_index = 0
        self.active_line = "line1"
        self.selected_point = "start"
        self.selected_roi_point = "start"
        self.active_target = "line"
        self.roi_dragging = False
        self.roi_drag_start: Optional[Tuple[int, int]] = None
        self.zoom_active = False
        self.zoom_origin = (0, 0)
        self.zoom_scale = (1.0, 1.0)
        self.window_name = "Mill Stand Multi-View Calibration"

        self.line_colors = {
            "line1": (0, 255, 0),
            "line2": (0, 165, 255),
        }
        self.roi_color = (255, 120, 0)
        self.line_thickness = 2
        self.live_test = False
        self.counter: Optional[MultiViewLineCounter] = None
        self.counter_views = []

        self._load_env(PROJECT_ROOT / ".env")
        self._load_config()

    def _load_env(self, env_path: Path):
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

    def _load_config(self):
        if not self.config_path.exists():
            print(f"Config file not found: {self.config_path}")
            sys.exit(1)

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f) or {}

        mill_config = config.get("mill_stand_lines", {})
        counting_config = mill_config.get("counting", {})
        self.counting_config = counting_config
        self.line_thickness = int(counting_config.get("line_thickness", 2))
        views_config = mill_config.get("views", [])
        if not views_config:
            print("No views configured in mill_stand_lines.views")
            sys.exit(1)

        self.views = []
        for i, view_cfg in enumerate(views_config):
            view_id = f"view_{i + 1}"
            self.views.append(ViewCalState(view_id, view_cfg))
        self._sync_counter()

    def _sync_counter(self):
        mill_views = []
        for view in self.views:
            mill_views.append(
                {
                    "name": view.name,
                    "camera": view.camera,
                    "line1": view.line1,
                    "line2": view.line2,
                    "roi": view.roi,
                }
            )

        counting_config = dict(self.counting_config)
        counting_config["line_thickness"] = self.line_thickness
        self.counter = MultiViewLineCounter(
            views_config=mill_views,
            counting_config=counting_config,
            voting_config={"min_stands_required": 1},
        )
        self.counter_views = self.counter.views if self.counter else []

    def _apply_live_test(self):
        if not self.live_test or not self.counter:
            return None

        frames = []
        for view in self.views:
            if view.last_frame is None:
                return None
            frames.append(view.last_frame)

        counted_piece, status, _ = self.counter.process_frames(frames)
        if counted_piece:
            print(
                f"Counted piece #{counted_piece.count_id} ({counted_piece.vote_ratio})"
            )
        return status

    def _open_streams(self):
        for idx, view in enumerate(self.views):
            if not view.rtsp_url:
                env_key = f"RTSP_VIEW{idx + 1}_URL"
                env_url = os.getenv(env_key)
                if not env_url:
                    print(f"Missing rtsp_url for {view.name}")
                    sys.exit(1)
                rtsp_url = env_url
            else:
                rtsp_url = view.rtsp_url
                env_key = f"RTSP_VIEW{idx + 1}_URL"
                rtsp_url = os.getenv(env_key, rtsp_url)

            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                print(f"Failed to open stream for {view.name}: {rtsp_url}")
                sys.exit(1)
            view.cap = cap

    def _release_streams(self):
        for view in self.views:
            if view.cap:
                view.cap.release()
                view.cap = None

    def _get_active_view(self) -> ViewCalState:
        return self.views[self.active_view_index]

    def _read_frames(self):
        for view in self.views:
            if view.cap is None:
                continue
            ret, frame = view.cap.read()
            if ret:
                view.last_frame = frame

    def _draw_overlay(
        self,
        frame: np.ndarray,
        view: ViewCalState,
        draw_lines: bool = True,
        draw_roi: bool = True,
    ) -> np.ndarray:
        overlay = frame.copy()
        base_thickness = self.line_thickness

        if draw_roi and view.roi:
            start = tuple(view.roi["start"])
            end = tuple(view.roi["end"])
            min_x = min(start[0], end[0])
            max_x = max(start[0], end[0])
            min_y = min(start[1], end[1])
            max_y = max(start[1], end[1])
            rect_overlay = overlay.copy()
            cv2.rectangle(
                rect_overlay,
                (min_x, min_y),
                (max_x, max_y),
                self.roi_color,
                -1,
            )
            cv2.addWeighted(rect_overlay, 0.2, overlay, 0.8, 0, overlay)
            cv2.rectangle(overlay, (min_x, min_y), (max_x, max_y), self.roi_color, 2)

        if not draw_lines:
            return overlay

        for line_key in ["line1", "line2"]:
            line = view.line1 if line_key == "line1" else view.line2
            start = tuple(line["start"])
            end = tuple(line["end"])
            color = self.line_colors[line_key]
            if line_key == self.active_line and self.active_target == "line":
                thickness = base_thickness
            else:
                thickness = base_thickness

            cv2.line(overlay, start, end, color, thickness)
            cv2.circle(overlay, start, 6, color, -1)
            cv2.circle(overlay, end, 6, color, -1)
            cv2.putText(
                overlay,
                "L1" if line_key == "line1" else "L2",
                (end[0] + 5, end[1] + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )

        return overlay

    def _draw_info_panel(self, panel: np.ndarray, view: ViewCalState):
        panel[:] = (15, 15, 15)
        cv2.rectangle(panel, (10, 10), (300, 280), (255, 255, 255), 1)

        y = 30
        cv2.putText(
            panel,
            f"View: {view.name} ({self.active_view_index + 1}/{len(self.views)})",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )
        y += 25
        mode_label = "ROI" if self.active_target == "roi" else "Line"
        cv2.putText(
            panel,
            f"Mode: {mode_label}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
        )
        y += 20
        if self.active_target == "line":
            cv2.putText(
                panel,
                f"Line: {'Line1' if self.active_line == 'line1' else 'Line2'}",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                self.line_colors[self.active_line],
                2,
            )
            y += 20
        cv2.putText(
            panel,
            f"Point: {self._active_point_label()}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        y += 20

        if self.active_target == "line":
            line = view.line1 if self.active_line == "line1" else view.line2
            cv2.putText(
                panel,
                f"Start: {line['start']} End: {line['end']}",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (180, 180, 180),
                1,
            )
        else:
            roi_text = "None"
            if view.roi:
                roi_text = f"{view.roi['start']} -> {view.roi['end']}"
            cv2.putText(
                panel,
                f"ROI: {roi_text}",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (180, 180, 180),
                1,
            )
        y += 22
        test_label = "ON" if self.live_test else "OFF"
        cv2.putText(
            panel,
            f"Live test: {test_label}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255) if self.live_test else (160, 160, 160),
            1,
        )
        y += 18
        cv2.putText(
            panel,
            "Keys: 1/2/3 view  L line1  K line2  O ROI",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (160, 160, 160),
            1,
        )
        y += 15
        cv2.putText(
            panel,
            "A/D line point  Z/X ROI point  T test",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (160, 160, 160),
            1,
        )

    def _draw_test_panel(
        self, panel: np.ndarray, test_status: dict, view: ViewCalState
    ):
        view_status = test_status.get("views", {}).get(view.view_id, {})
        if not view_status:
            return

        y = 200
        cv2.putText(
            panel,
            "Live detection",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
        )
        y += 18

        entry_px = view_status.get("entry_pixels", 0)
        exit_px = view_status.get("exit_pixels", 0)
        entry_on = "ON" if view_status.get("entry_triggered") else "OFF"
        exit_on = "ON" if view_status.get("exit_triggered") else "OFF"

        cv2.putText(
            panel,
            f"Line1: {entry_on} ({entry_px}px)",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            self.line_colors["line1"],
            1,
        )
        y += 16
        cv2.putText(
            panel,
            f"Line2: {exit_on} ({exit_px}px)",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            self.line_colors["line2"],
            1,
        )
        y += 16

        pending = "YES" if view_status.get("pending") else "NO"
        count = view_status.get("detection_count", 0)
        cv2.putText(
            panel,
            f"Pending: {pending}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (200, 200, 200),
            1,
        )
        y += 16
        cv2.putText(
            panel,
            f"Detections: {count}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (200, 200, 200),
            1,
        )

    def _set_line_point(self, x: int, y: int):
        view = self._get_active_view()
        if self.active_target == "line":
            line = view.line1 if self.active_line == "line1" else view.line2
            line[self.selected_point] = [x, y]
        else:
            if view.roi is None:
                view.roi = {"start": [0, 0], "end": [0, 0]}
            view.roi[self.selected_roi_point] = [x, y]
        self._sync_counter()

    def _normalize_roi(self, view: ViewCalState) -> Optional[Tuple[int, int, int, int]]:
        if view.roi is None:
            return None
        start = view.roi.get("start")
        end = view.roi.get("end")
        if not start or not end:
            return None
        x1, y1 = start
        x2, y2 = end
        min_x = min(x1, x2)
        max_x = max(x1, x2)
        min_y = min(y1, y2)
        max_y = max(y1, y2)
        if max_x - min_x <= 1 or max_y - min_y <= 1:
            return None
        return (min_x, min_y, max_x, max_y)

    def _active_point_label(self) -> str:
        if self.active_target == "roi":
            return f"ROI {self.selected_roi_point.upper()}"
        return self.selected_point.upper()

    def _reset_view_lines(self):
        view = self._get_active_view()
        if view.last_frame is None:
            view.line1 = {"start": [0, 0], "end": [0, 0]}
            view.line2 = {"start": [0, 0], "end": [0, 0]}
            return

        h, w = view.last_frame.shape[:2]
        mid_y = int(h * 0.5)
        view.line1 = {
            "start": [int(w * 0.6), int(mid_y - 40)],
            "end": [int(w * 0.6), int(mid_y + 40)],
        }
        view.line2 = {
            "start": [int(w * 0.4), int(mid_y - 40)],
            "end": [int(w * 0.4), int(mid_y + 40)],
        }

    def _reset_view_roi(self):
        view = self._get_active_view()
        if view.last_frame is None:
            view.roi = None
            return
        h, w = view.last_frame.shape[:2]
        view.roi = {"start": [0, 0], "end": [w, h]}

    def _save_config(self):
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        mill_config = config.get("mill_stand_lines", {})
        views_config = mill_config.get("views", [])

        if not views_config:
            views_config = [{} for _ in self.views]

        for idx, view_state in enumerate(self.views):
            if idx >= len(views_config):
                views_config.append({})
            views_config[idx]["name"] = view_state.name
            views_config[idx]["camera"] = view_state.camera
            views_config[idx]["line1"] = view_state.line1
            views_config[idx]["line2"] = view_state.line2
            if view_state.roi is not None:
                views_config[idx]["roi"] = view_state.roi

        mill_config["views"] = views_config
        mill_config["enabled"] = True
        config["mill_stand_lines"] = mill_config

        with open(self.config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"Saved configuration to {self.config_path}")

    def _on_mouse(self, event, x, y, flags, param):
        view = self._get_active_view()
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.active_target == "roi":
                self.roi_dragging = True
                self.roi_drag_start = (x, y)
                if view.roi is None:
                    view.roi = {"start": [x, y], "end": [x, y]}
                view.roi["start"] = [x, y]
                view.roi["end"] = [x, y]
            else:
                if self.zoom_active:
                    origin_x, origin_y = self.zoom_origin
                    scale_x, scale_y = self.zoom_scale
                    mapped_x = int(origin_x + (x / scale_x))
                    mapped_y = int(origin_y + (y / scale_y))
                    self._set_line_point(mapped_x, mapped_y)
                else:
                    self._set_line_point(x, y)
        elif event == cv2.EVENT_MOUSEMOVE:
            if (
                self.roi_dragging
                and self.active_target == "roi"
                and view.roi is not None
            ):
                view.roi["end"] = [x, y]
        elif event == cv2.EVENT_LBUTTONUP:
            if (
                self.roi_dragging
                and self.active_target == "roi"
                and view.roi is not None
            ):
                view.roi["end"] = [x, y]
            self.roi_dragging = False
            self.roi_drag_start = None
            self._sync_counter()

    def run(self):
        self._open_streams()

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._on_mouse)
        cv2.resizeWindow(self.window_name, 1280, 720)

        print("Multi-view calibration tool started")
        print("Use 1/2/3 to select view, L/K to choose line")
        print("Use A/D for line points, Z/X for ROI points, O to toggle ROI")
        print("Press T to toggle test, S to save, Q to quit")

        try:
            while True:
                self._read_frames()
                view = self._get_active_view()
                if view.last_frame is None:
                    frame = cv2.imread(str(PROJECT_ROOT / "data" / "blank.jpg"))
                    if frame is None:
                        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                else:
                    frame = view.last_frame

                test_status = self._apply_live_test() if self.live_test else None

                roi_box = self._normalize_roi(view)
                if self.active_target == "line" and roi_box and not self.roi_dragging:
                    x1, y1, x2, y2 = roi_box
                    overlay_full = self._draw_overlay(
                        frame, view, draw_lines=True, draw_roi=False
                    )
                    roi_frame = overlay_full[y1:y2, x1:x2]
                    if roi_frame.size > 0:
                        display_frame = cv2.resize(
                            roi_frame,
                            (frame.shape[1], frame.shape[0]),
                            interpolation=cv2.INTER_AREA,
                        )
                        roi_w = max(1, x2 - x1)
                        roi_h = max(1, y2 - y1)
                        self.zoom_active = True
                        self.zoom_origin = (x1, y1)
                        self.zoom_scale = (
                            frame.shape[1] / roi_w,
                            frame.shape[0] / roi_h,
                        )
                    else:
                        display_frame = overlay_full
                        self.zoom_active = False
                else:
                    display_frame = self._draw_overlay(frame, view)
                    self.zoom_active = False
                panel_width = 320
                panel = np.zeros(
                    (display_frame.shape[0], panel_width, 3), dtype=np.uint8
                )
                self._draw_info_panel(panel, view)
                if test_status:
                    self._draw_test_panel(panel, test_status, view)
                combined = np.hstack([display_frame, panel])
                cv2.imshow(self.window_name, combined)

                key = cv2.waitKey(30) & 0xFF
                if key == ord("q") or key == 27:
                    break
                if key in (ord("1"), ord("2"), ord("3")):
                    index = key - ord("1")
                    if 0 <= index < len(self.views):
                        self.active_view_index = index
                        self.selected_point = "start"
                        self.selected_roi_point = "start"
                elif key == ord("l"):
                    self.active_line = "line1"
                    self.selected_point = "start"
                    self.active_target = "line"
                    self._sync_counter()
                elif key == ord("k"):
                    self.active_line = "line2"
                    self.selected_point = "start"
                    self.active_target = "line"
                    self._sync_counter()
                elif key == ord("o"):
                    self.active_target = "roi"
                    self._sync_counter()
                elif key == ord("a"):
                    self.selected_point = "start"
                    self.active_target = "line"
                    self._sync_counter()
                elif key == ord("d"):
                    self.selected_point = "end"
                    self.active_target = "line"
                    self._sync_counter()
                elif key == ord("z"):
                    self.selected_roi_point = "start"
                    self.active_target = "roi"
                    self._sync_counter()
                elif key == ord("x"):
                    self.selected_roi_point = "end"
                    self.active_target = "roi"
                    self._sync_counter()
                elif key == ord("r"):
                    if self.active_target == "roi":
                        self._reset_view_roi()
                    else:
                        self._reset_view_lines()
                    self._sync_counter()
                elif key == ord("s"):
                    self._save_config()
                elif key == ord("t"):
                    self.live_test = not self.live_test

        finally:
            self._release_streams()
            cv2.destroyAllWindows()


def main():
    calibrator = MultiViewLineCalibrator()
    calibrator.run()


if __name__ == "__main__":
    main()
