#!/usr/bin/env python3
"""
Master Mill Stand Configurator
==============================
Configure per-view settings with a live video preview and right-side control panel.

Controls:
  1/2/3        - Select active view
  Up/Down      - Select field
  Enter        - Edit field (or toggle boolean)
  + / -        - Nudge value
  T            - Toggle live test mode
  V            - Toggle ROI zoom view
  S            - Save to settings.yaml
  Q/ESC        - Quit
"""

import cv2
import numpy as np
import yaml
import sys
import os
import time
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@dataclass
class Field:
    label: str
    getter: Callable[[], Any]
    setter: Optional[Callable[[Any], None]]
    field_type: str
    step: float = 1.0

    @property
    def editable(self) -> bool:
        return self.setter is not None


class ViewState:
    def __init__(self, view_id: str, view_config: dict, default_counting: dict):
        self.view_id = view_id
        self.name = view_config.get("name", view_id)
        self.camera = view_config.get("camera", {})
        self.line1 = view_config.get("line1") or {"start": [0, 0], "end": [0, 0]}
        self.line2 = view_config.get("line2") or {"start": [0, 0], "end": [0, 0]}
        self.roi = view_config.get("roi") or {"start": [0, 0], "end": [0, 0]}
        self.counting = dict(default_counting)
        self.counting.update(view_config.get("counting", {}))
        self.counting["line_thickness"] = 3
        self.cap: Optional[cv2.VideoCapture] = None
        self.last_frame: Optional[np.ndarray] = None

    @property
    def rtsp_url(self) -> str:
        return self.camera.get("rtsp_url", "")


class LiveTestView:
    def __init__(self, view: ViewState):
        self.view = view
        self.stand = self._create_stand()
        self.initialized = False
        self.roi_box: Optional[Tuple[int, int, int, int]] = None
        self.roi_applied = False
        self.status = {}

    def _create_stand(self):
        counter_module = importlib.import_module("mill_stand_line_counter")
        Stand = counter_module.Stand
        StandConfig = counter_module.StandConfig
        LineConfig = counter_module.LineConfig

        stand_config = StandConfig(
            name=self.view.name,
            direction="line1_to_line2",
            entry_line=LineConfig.from_dict(self.view.line1),
            exit_line=LineConfig.from_dict(self.view.line2),
        )
        return Stand(self.view.view_id, 0, stand_config, self.view.counting)

    def _normalize_roi(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        roi = self.view.roi
        if not roi:
            return None
        start = roi.get("start")
        end = roi.get("end")
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
        self.roi_box = self._normalize_roi(frame)
        original_resolution = full_resolution

        if self.roi_box:
            roi_w = self.roi_box[2] - self.roi_box[0]
            roi_h = self.roi_box[3] - self.roi_box[1]
            original_resolution = (roi_w, roi_h)
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

        target_resolution = tuple(
            self.view.counting.get("target_resolution", [704, 576])
        )
        self.stand.scale_lines(original_resolution, target_resolution)
        self.initialized = True

    def process(self, frame: np.ndarray, current_time: float) -> dict:
        self._init_resolution(frame)
        frame_in = frame
        if self.roi_box:
            x1, y1, x2, y2 = self.roi_box
            roi_frame = frame[y1:y2, x1:x2]
            if roi_frame.size > 0:
                frame_in = roi_frame

        target_resolution = tuple(
            self.view.counting.get("target_resolution", [704, 576])
        )
        resized = cv2.resize(frame_in, target_resolution, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        _, status = self.stand.process_frame(gray, resized, current_time)
        self.status = status
        return status


class MasterConfigurator:
    def __init__(self):
        self.config_path = PROJECT_ROOT / "config" / "settings.yaml"
        self.views: List[ViewState] = []
        self.active_view_index = 0
        self.fields: List[Field] = []
        self.selected_field_index = 0
        self.editing = False
        self.edit_buffer = ""
        self.live_test = False
        self.zoom_roi_view = False
        self.panel_width = 420
        self.line_thickness = 3
        self.live_testers: List[LiveTestView] = []
        self.status_message = "Ready"
        self.status_time = time.time()
        self.zoom_active = False
        self.zoom_origin = (0, 0)
        self.zoom_scale = (1.0, 1.0)

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

    def _default_counting(self) -> dict:
        return {
            "luminosity_threshold": 160,
            "min_bright_pixels": 100,
            "sequence_timeout": 3.0,
            "min_travel_time": 0.0,
            "min_consecutive_frames": 2,
            "line_thickness": 3,
            "hot_metal_filter_enabled": True,
            "min_saturation": 20,
            "min_red_dominance": 1.1,
            "min_warmth_ratio": 1.05,
            "target_resolution": [704, 576],
        }

    def _load_config(self):
        if not self.config_path.exists():
            print(f"Config file not found: {self.config_path}")
            sys.exit(1)

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f) or {}

        mill_config = config.get("mill_stand_lines", {})
        views_config = mill_config.get("views", [])
        default_counting = self._default_counting()
        default_counting.update(mill_config.get("counting", {}))

        if not views_config:
            print("No views configured in mill_stand_lines.views")
            sys.exit(1)

        self.views = []
        for i, view_cfg in enumerate(views_config):
            view_id = f"view_{i + 1}"
            self.views.append(ViewState(view_id, view_cfg, default_counting))

        self._build_fields()
        self._init_live_testers()

    def _init_live_testers(self):
        self.live_testers = [LiveTestView(view) for view in self.views]

    def _build_fields(self):
        view = self.views[self.active_view_index]
        counting = view.counting

        def make_int_field(label: str, getter, setter, step=1):
            return Field(label, getter, setter, "int", step)

        def make_float_field(label: str, getter, setter, step=0.1):
            return Field(label, getter, setter, "float", step)

        def make_bool_field(label: str, getter, setter):
            return Field(label, getter, setter, "bool", 1)

        def make_readonly(label: str, getter):
            return Field(label, getter, None, "readonly", 0)

        self.fields = [
            make_readonly("View", lambda: view.name),
            make_int_field(
                "ROI start x",
                lambda: view.roi["start"][0],
                lambda v: self._set_roi(view, 0, v, True),
            ),
            make_int_field(
                "ROI start y",
                lambda: view.roi["start"][1],
                lambda v: self._set_roi(view, 1, v, True),
            ),
            make_int_field(
                "ROI end x",
                lambda: view.roi["end"][0],
                lambda v: self._set_roi(view, 0, v, False),
            ),
            make_int_field(
                "ROI end y",
                lambda: view.roi["end"][1],
                lambda v: self._set_roi(view, 1, v, False),
            ),
            make_int_field(
                "Line1 start x",
                lambda: view.line1["start"][0],
                lambda v: self._set_line(view.line1, 0, v, True),
            ),
            make_int_field(
                "Line1 start y",
                lambda: view.line1["start"][1],
                lambda v: self._set_line(view.line1, 1, v, True),
            ),
            make_int_field(
                "Line1 end x",
                lambda: view.line1["end"][0],
                lambda v: self._set_line(view.line1, 0, v, False),
            ),
            make_int_field(
                "Line1 end y",
                lambda: view.line1["end"][1],
                lambda v: self._set_line(view.line1, 1, v, False),
            ),
            make_int_field(
                "Line2 start x",
                lambda: view.line2["start"][0],
                lambda v: self._set_line(view.line2, 0, v, True),
            ),
            make_int_field(
                "Line2 start y",
                lambda: view.line2["start"][1],
                lambda v: self._set_line(view.line2, 1, v, True),
            ),
            make_int_field(
                "Line2 end x",
                lambda: view.line2["end"][0],
                lambda v: self._set_line(view.line2, 0, v, False),
            ),
            make_int_field(
                "Line2 end y",
                lambda: view.line2["end"][1],
                lambda v: self._set_line(view.line2, 1, v, False),
            ),
            make_int_field(
                "Luminosity",
                lambda: counting["luminosity_threshold"],
                lambda v: self._set_counting(counting, "luminosity_threshold", v),
            ),
            make_int_field(
                "Min bright px",
                lambda: counting["min_bright_pixels"],
                lambda v: self._set_counting(counting, "min_bright_pixels", v),
            ),
            make_float_field(
                "Sequence timeout",
                lambda: counting["sequence_timeout"],
                lambda v: self._set_counting(counting, "sequence_timeout", v),
                0.1,
            ),
            make_float_field(
                "Min travel",
                lambda: counting["min_travel_time"],
                lambda v: self._set_counting(counting, "min_travel_time", v),
                0.1,
            ),
            make_int_field(
                "Min frames",
                lambda: counting["min_consecutive_frames"],
                lambda v: self._set_counting(counting, "min_consecutive_frames", v),
            ),
            make_bool_field(
                "Hot metal filter",
                lambda: counting.get("hot_metal_filter_enabled", True),
                lambda v: self._set_counting(counting, "hot_metal_filter_enabled", v),
            ),
            make_int_field(
                "Min saturation",
                lambda: counting["min_saturation"],
                lambda v: self._set_counting(counting, "min_saturation", v),
            ),
            make_float_field(
                "Min red dominance",
                lambda: counting["min_red_dominance"],
                lambda v: self._set_counting(counting, "min_red_dominance", v),
                0.05,
            ),
            make_float_field(
                "Min warmth ratio",
                lambda: counting["min_warmth_ratio"],
                lambda v: self._set_counting(counting, "min_warmth_ratio", v),
                0.05,
            ),
            make_int_field(
                "Target width",
                lambda: counting["target_resolution"][0],
                lambda v: self._set_target_res(counting, 0, v),
            ),
            make_int_field(
                "Target height",
                lambda: counting["target_resolution"][1],
                lambda v: self._set_target_res(counting, 1, v),
            ),
            make_readonly("Line thickness", lambda: 3),
        ]

        self.selected_field_index = min(self.selected_field_index, len(self.fields) - 1)
        if not self.fields[self.selected_field_index].editable:
            self._move_selection(1)

    def _set_roi(self, view: ViewState, axis: int, value: int, start: bool):
        key = "start" if start else "end"
        view.roi[key][axis] = int(value)
        self._init_live_testers()

    def _set_line(self, line: dict, axis: int, value: int, start: bool):
        key = "start" if start else "end"
        line[key][axis] = int(value)
        self._init_live_testers()

    def _set_counting(self, counting: dict, key: str, value: Any):
        counting[key] = value
        counting["line_thickness"] = 3
        self._init_live_testers()

    def _set_target_res(self, counting: dict, axis: int, value: int):
        res = counting.get("target_resolution", [704, 576])
        res[axis] = int(value)
        counting["target_resolution"] = res
        self._init_live_testers()

    def _open_streams(self):
        for idx, view in enumerate(self.views):
            env_key = f"RTSP_VIEW{idx + 1}_URL"
            rtsp_url = os.getenv(env_key, view.rtsp_url)
            if not rtsp_url:
                print(f"Missing rtsp_url for {view.name}")
                sys.exit(1)
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

    def _read_frames(self):
        for view in self.views:
            if view.cap is None:
                continue
            ret, frame = view.cap.read()
            if ret:
                view.last_frame = frame

    def _move_selection(self, direction: int):
        idx = self.selected_field_index
        for _ in range(len(self.fields)):
            idx = (idx + direction) % len(self.fields)
            if self.fields[idx].editable:
                self.selected_field_index = idx
                self._set_status(f"Selected: {self.fields[idx].label}")
                break

    def _apply_step(self, field: Field, direction: int):
        if not field.editable or field.setter is None:
            return
        current = field.getter()
        if field.field_type == "bool":
            field.setter(not bool(current))
            return
        delta = field.step * direction
        if field.field_type == "int":
            field.setter(int(current + delta))
        elif field.field_type == "float":
            field.setter(float(current + delta))
        self._set_status(f"Adjusted: {field.label}")

    def _draw_panel(self, panel: np.ndarray, view: ViewState, status: Optional[dict]):
        panel[:] = (15, 15, 15)
        cv2.rectangle(
            panel,
            (10, 10),
            (self.panel_width - 10, panel.shape[0] - 10),
            (255, 255, 255),
            1,
        )

        y = 30
        cv2.putText(
            panel,
            f"View {self.active_view_index + 1}: {view.name}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )
        y += 25
        cv2.putText(
            panel,
            f"Live test: {'ON' if self.live_test else 'OFF'}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255) if self.live_test else (160, 160, 160),
            1,
        )
        y += 20
        cv2.putText(
            panel,
            f"Status: {self.status_message}",
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (200, 200, 200),
            1,
        )
        y += 18
        if self.editing:
            cv2.putText(
                panel,
                "Editing...",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 255),
                1,
            )
            y += 18

        if status:
            view_status = status.get(view.view_id, {})
            entry_px = view_status.get("entry_pixels", 0)
            exit_px = view_status.get("exit_pixels", 0)
            entry_on = "ON" if view_status.get("entry_triggered") else "OFF"
            exit_on = "ON" if view_status.get("exit_triggered") else "OFF"
            pending = "YES" if view_status.get("pending") else "NO"

            cv2.putText(
                panel,
                f"Line1: {entry_on} ({entry_px}px)",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 0),
                1,
            )
            y += 16
            cv2.putText(
                panel,
                f"Line2: {exit_on} ({exit_px}px)",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 165, 255),
                1,
            )
            y += 16
            cv2.putText(
                panel,
                f"Pending: {pending}",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (200, 200, 200),
                1,
            )
            y += 20

        max_rows = int((panel.shape[0] - y - 20) / 18)
        start_index = max(0, self.selected_field_index - max_rows + 1)
        end_index = min(len(self.fields), start_index + max_rows)

        for idx in range(start_index, end_index):
            field = self.fields[idx]
            value = field.getter()
            if field.field_type == "bool":
                value_text = "ON" if value else "OFF"
            else:
                value_text = str(value)
            if self.editing and idx == self.selected_field_index:
                value_text = self.edit_buffer

            color = (255, 255, 255) if field.editable else (120, 120, 120)
            if idx == self.selected_field_index:
                color = (0, 255, 255)
                cv2.rectangle(
                    panel,
                    (15, y - 12),
                    (self.panel_width - 15, y + 4),
                    (40, 40, 40),
                    -1,
                )
            label = f"{field.label}: {value_text}"
            cv2.putText(panel, label, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            y += 18

        cv2.putText(
            panel,
            "Up/Down select  Enter edit  +/- nudge",
            (20, panel.shape[0] - 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (160, 160, 160),
            1,
        )
        cv2.putText(
            panel,
            "1/2/3 view  T test  V zoom  S save  Q quit",
            (20, panel.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (160, 160, 160),
            1,
        )

    def _draw_overlay(
        self, frame: np.ndarray, view: ViewState, status: Optional[dict]
    ) -> np.ndarray:
        overlay = frame.copy()

        roi = view.roi
        if roi:
            start = (int(roi["start"][0]), int(roi["start"][1]))
            end = (int(roi["end"][0]), int(roi["end"][1]))
            min_x, min_y, max_x, max_y = self._map_rect(start, end, frame.shape)
            rect_overlay = overlay.copy()
            cv2.rectangle(
                rect_overlay, (min_x, min_y), (max_x, max_y), (255, 120, 0), -1
            )
            cv2.addWeighted(rect_overlay, 0.2, overlay, 0.8, 0, overlay)
            cv2.rectangle(overlay, (min_x, min_y), (max_x, max_y), (255, 120, 0), 2)

        line_thickness = 3
        if status:
            view_status = status.get(view.view_id, {})
        else:
            view_status = {}

        entry_thickness = line_thickness
        exit_thickness = line_thickness
        if self.live_test:
            if view_status.get("entry_triggered"):
                entry_thickness = line_thickness + 2
            if view_status.get("exit_triggered"):
                exit_thickness = line_thickness + 2

        line1_start = self._map_point(view.line1["start"], frame.shape)
        line1_end = self._map_point(view.line1["end"], frame.shape)
        line2_start = self._map_point(view.line2["start"], frame.shape)
        line2_end = self._map_point(view.line2["end"], frame.shape)

        cv2.line(overlay, line1_start, line1_end, (0, 255, 0), entry_thickness)
        cv2.line(overlay, line2_start, line2_end, (0, 165, 255), exit_thickness)

        return overlay

    def _apply_zoom_view(self, frame: np.ndarray, view: ViewState) -> np.ndarray:
        if not self.zoom_roi_view:
            self.zoom_active = False
            return frame
        roi = view.roi
        if not roi:
            self.zoom_active = False
            return frame
        start = tuple(roi["start"])
        end = tuple(roi["end"])
        min_x = max(0, min(start[0], end[0]))
        max_x = min(frame.shape[1], max(start[0], end[0]))
        min_y = max(0, min(start[1], end[1]))
        max_y = min(frame.shape[0], max(start[1], end[1]))
        if max_x - min_x <= 1 or max_y - min_y <= 1:
            self.zoom_active = False
            return frame
        roi_frame = frame[min_y:max_y, min_x:max_x]
        if roi_frame.size == 0:
            self.zoom_active = False
            return frame
        roi_w = max(1, max_x - min_x)
        roi_h = max(1, max_y - min_y)
        self.zoom_active = True
        self.zoom_origin = (min_x, min_y)
        self.zoom_scale = (frame.shape[1] / roi_w, frame.shape[0] / roi_h)
        return cv2.resize(
            roi_frame, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_AREA
        )

    def _map_point(
        self, point: List[int], shape: Tuple[int, int, int]
    ) -> Tuple[int, int]:
        x, y = point
        if self.zoom_active:
            origin_x, origin_y = self.zoom_origin
            scale_x, scale_y = self.zoom_scale
            x = int((x - origin_x) * scale_x)
            y = int((y - origin_y) * scale_y)
        x = max(0, min(shape[1] - 1, x))
        y = max(0, min(shape[0] - 1, y))
        return (x, y)

    def _map_rect(
        self, start: Tuple[int, int], end: Tuple[int, int], shape: Tuple[int, int, int]
    ) -> Tuple[int, int, int, int]:
        if self.zoom_active:
            start_pt = self._map_point(list(start), shape)
            end_pt = self._map_point(list(end), shape)
            min_x = min(start_pt[0], end_pt[0])
            max_x = max(start_pt[0], end_pt[0])
            min_y = min(start_pt[1], end_pt[1])
            max_y = max(start_pt[1], end_pt[1])
        else:
            min_x = max(0, min(start[0], end[0]))
            max_x = min(shape[1] - 1, max(start[0], end[0]))
            min_y = max(0, min(start[1], end[1]))
            max_y = min(shape[0] - 1, max(start[1], end[1]))
        return (min_x, min_y, max_x, max_y)

    def _update_live_test(self) -> Optional[dict]:
        if not self.live_test:
            return None

        status = {}
        current_time = time.time()
        for tester, view in zip(self.live_testers, self.views):
            if view.last_frame is None:
                continue
            status[view.view_id] = tester.process(view.last_frame, current_time)
        return status

    def _set_status(self, message: str):
        self.status_message = message
        self.status_time = time.time()

    def _save_config(self):
        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f) or {}

        mill_config = config.get("mill_stand_lines", {})
        views_config = mill_config.get("views", [])
        if not views_config:
            views_config = [{} for _ in self.views]

        for idx, view in enumerate(self.views):
            if idx >= len(views_config):
                views_config.append({})
            views_config[idx]["name"] = view.name
            views_config[idx]["camera"] = view.camera
            views_config[idx]["line1"] = view.line1
            views_config[idx]["line2"] = view.line2
            views_config[idx]["roi"] = view.roi
            view.counting["line_thickness"] = 3
            views_config[idx]["counting"] = view.counting

        mill_config["views"] = views_config
        mill_config["enabled"] = True
        config["mill_stand_lines"] = mill_config

        with open(self.config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"Saved configuration to {self.config_path}")

    def run(self):
        self._open_streams()
        window_name = "Mill Stand Master Configurator"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)

        print("Master configurator started")
        print("Use 1/2/3 for view, Up/Down for fields, Enter to edit")
        print("Press T to toggle live test, S to save, Q to quit")

        try:
            while True:
                self._read_frames()
                view = self.views[self.active_view_index]
                frame = view.last_frame
                if frame is None:
                    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

                test_status = self._update_live_test()
                zoomed_frame = self._apply_zoom_view(frame, view)
                overlay = self._draw_overlay(zoomed_frame, view, test_status)

                panel = np.zeros(
                    (overlay.shape[0], self.panel_width, 3), dtype=np.uint8
                )
                self._draw_panel(panel, view, test_status)
                combined = np.hstack([overlay, panel])
                cv2.imshow(window_name, combined)

                key = cv2.waitKeyEx(30)
                key_8 = key & 0xFF
                plus_keys = {ord("+"), ord("=")}
                minus_keys = {ord("-"), ord("_")}
                if key_8 == ord("q") or key_8 == 27:
                    break

                if self.editing:
                    if key_8 in (13, 10):
                        field = self.fields[self.selected_field_index]
                        if field.editable:
                            self._apply_buffer(field)
                        self.editing = False
                        self._set_status("Edit applied")
                    elif key_8 == 27:
                        self.editing = False
                        self._set_status("Edit cancelled")
                    elif key_8 in (8, 127):
                        self.edit_buffer = self.edit_buffer[:-1]
                    elif 48 <= key_8 <= 57:
                        self.edit_buffer += chr(key_8)
                    elif key_8 == ord("."):
                        if "." not in self.edit_buffer:
                            self.edit_buffer += "."
                    elif key_8 == ord("-"):
                        if not self.edit_buffer:
                            self.edit_buffer = "-"
                    continue

                if key_8 in (ord("1"), ord("2"), ord("3")):
                    idx = key_8 - ord("1")
                    if 0 <= idx < len(self.views):
                        self.active_view_index = idx
                        self._build_fields()
                        self._set_status(f"Switched to view {idx + 1}")
                        continue
                if key_8 == ord("t"):
                    self.live_test = not self.live_test
                    self._set_status(
                        "Live test ON" if self.live_test else "Live test OFF"
                    )
                elif key_8 == ord("v"):
                    self.zoom_roi_view = not self.zoom_roi_view
                    self._set_status(
                        "ROI zoom ON" if self.zoom_roi_view else "ROI zoom OFF"
                    )
                elif key_8 == ord("s"):
                    self._save_config()
                    self._set_status("Saved configuration")
                elif key in (2490368, 65362, 63232) or key_8 == 82:
                    self._move_selection(-1)
                elif key in (2621440, 65364, 63233) or key_8 == 84:
                    self._move_selection(1)
                elif key_8 in (13, 10):
                    field = self.fields[self.selected_field_index]
                    if field.field_type == "bool" and field.editable and field.setter:
                        field.setter(not bool(field.getter()))
                        self._set_status(f"Toggled: {field.label}")
                    elif field.editable:
                        self.editing = True
                        self.edit_buffer = str(field.getter())
                        self._set_status(f"Editing: {field.label}")
                elif key_8 in plus_keys or key in (171, 61, 43):
                    self._apply_step(self.fields[self.selected_field_index], 1)
                elif key_8 in minus_keys or key in (173, 45, 95):
                    self._apply_step(self.fields[self.selected_field_index], -1)
        finally:
            self._release_streams()
            cv2.destroyAllWindows()

    def _apply_buffer(self, field: Field):
        raw = self.edit_buffer.strip()
        if not raw:
            return
        try:
            if field.field_type == "int":
                value = int(float(raw))
            elif field.field_type == "float":
                value = float(raw)
            elif field.field_type == "bool":
                value = raw.lower() in ("1", "true", "yes", "on")
            else:
                value = raw
        except ValueError:
            return
        if field.editable and field.setter:
            field.setter(value)
            self._set_status(f"Updated: {field.label}")


def main():
    configurator = MasterConfigurator()
    configurator.run()


if __name__ == "__main__":
    main()
