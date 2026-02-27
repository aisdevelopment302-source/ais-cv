#!/usr/bin/env python3
"""
Mill Stand Line Calibration Tool
================================
Video-based tool for positioning detection lines for each mill stand.

Each stand has:
- Entry line: First line the piece crosses
- Exit line: Second line the piece crosses (confirms detection)

Controls:
  Stand Selection:
    Tab/Shift+Tab - Cycle through stands (next/previous)
    +/=         - Add new stand
    Delete/Backspace - Remove current stand

  Line Selection:
    E           - Select ENTRY line (green)
    X           - Select EXIT line (red)

  Point Selection:
    R           - Select START point (R for staRt)
    N           - Select END point (N for eNd)

  Point Movement:
    Arrow Keys  - Move point by 1 pixel
    W/A/S/D     - Move point by 10 pixels
    Shift+WASD  - Move point by 50 pixels

  Video Navigation:
    Space       - Play/Pause
    ./>         - Step forward 1 frame / 5 seconds
    ,/<         - Step backward 1 frame / 5 seconds
    0-9         - Jump to 0%-90% of video

  Testing:
    T           - Toggle live detection testing

  Saving:
    V           - Save configuration to settings.yaml
    P           - Print current configuration

  Other:
    H           - Show help
    Q/ESC       - Quit

Usage:
    python scripts/calibrate_mill_stand_lines.py
    python scripts/calibrate_mill_stand_lines.py --video path/to/video.mp4
"""

import cv2
import numpy as np
import yaml
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class MillStandLineCalibrator:
    def __init__(self, video_path: str = None):
        # Default stands (for 1920x1080 video)
        self.stands: List[Dict] = [
            {
                "name": "Stand 1",
                "direction": "left_to_right",
                "entry_line": {"start": [200, 400], "end": [200, 600]},
                "exit_line": {"start": [350, 400], "end": [350, 600]},
            },
            {
                "name": "Stand 2",
                "direction": "left_to_right",
                "entry_line": {"start": [600, 400], "end": [600, 600]},
                "exit_line": {"start": [750, 400], "end": [750, 600]},
            },
        ]

        # Colors for visualization
        self.entry_color = (0, 255, 0)  # Green
        self.exit_color = (0, 0, 255)  # Red
        self.selected_color = (255, 255, 0)  # Cyan for selected

        # Try to load existing config
        self.load_config()

        # Selection state
        self.selected_stand_index = 0
        self.selected_line = "entry"  # "entry" or "exit"
        self.selected_point = "start"  # "start" or "end"

        # Video state
        self.video_path = video_path or self.get_default_video_path()
        self.cap = None
        self.current_frame = None
        self.frame_num = 0
        self.total_frames = 0
        self.fps = 25
        self.playing = False

        # Testing state
        self.test_mode = False
        self.luminosity_threshold = 160
        self.min_bright_pixels = 30
        self.line_thickness = 15
        self.sequence_timeout = 2.0
        self.debounce_time = 0.3

        # Window
        self.window_name = "Mill Stand Line Calibration - Press H for Help"

    def get_default_video_path(self) -> str:
        """Get default video path from config or fallback."""
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            video_file = config.get("mill_stand", {}).get(
                "video_file", "recordings/mill stand view.mp4"
            )
            return str(PROJECT_ROOT / video_file)
        return str(PROJECT_ROOT / "recordings" / "mill stand view.mp4")

    def load_config(self):
        """Load configuration from settings.yaml if available."""
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
        if not config_path.exists():
            print("No settings.yaml found, using defaults")
            return

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            mill_stand_lines = config.get("mill_stand_lines", {})
            stands = mill_stand_lines.get("stands", [])

            if stands:
                self.stands = stands
                print(f"Loaded {len(stands)} stand(s) from settings.yaml")

            # Load counting config for testing
            counting = mill_stand_lines.get("counting", {})
            self.luminosity_threshold = counting.get("luminosity_threshold", 160)
            self.min_bright_pixels = counting.get("min_bright_pixels", 30)
            self.line_thickness = counting.get("line_thickness", 15)
            self.sequence_timeout = counting.get("sequence_timeout", 2.0)
            self.debounce_time = counting.get("debounce_time", 0.3)

        except Exception as e:
            print(f"Error loading config: {e}")

    def open_video(self) -> bool:
        """Open video file."""
        if not Path(self.video_path).exists():
            print(f"Video file not found: {self.video_path}")
            return False

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            print(f"Failed to open video: {self.video_path}")
            return False

        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        duration = self.total_frames / self.fps
        print(f"Video: {width}x{height} @ {self.fps:.1f} FPS")
        print(
            f"Duration: {int(duration // 60)}:{int(duration % 60):02d} ({self.total_frames} frames)"
        )

        # Read first frame
        ret, self.current_frame = self.cap.read()
        if not ret:
            print("Failed to read first frame")
            return False

        self.frame_num = 0
        return True

    def read_frame(self, frame_num: int = None) -> bool:
        """Read a specific frame or next frame."""
        if frame_num is not None:
            frame_num = max(0, min(frame_num, self.total_frames - 1))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            self.frame_num = frame_num

        ret, self.current_frame = self.cap.read()
        if ret:
            self.frame_num = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        return ret

    @property
    def current_stand(self) -> Dict:
        """Get currently selected stand."""
        if 0 <= self.selected_stand_index < len(self.stands):
            return self.stands[self.selected_stand_index]
        return None

    @property
    def current_line(self) -> Dict:
        """Get currently selected line."""
        stand = self.current_stand
        if stand:
            return stand[f"{self.selected_line}_line"]
        return None

    def get_point_coords(self) -> Tuple[int, int]:
        """Get coordinates of currently selected point."""
        line = self.current_line
        if line:
            return tuple(line[self.selected_point])
        return (0, 0)

    def set_point_coords(self, x: int, y: int):
        """Set coordinates of currently selected point."""
        line = self.current_line
        if line:
            line[self.selected_point] = [x, y]

    def move_point(self, dx: int, dy: int):
        """Move selected point."""
        x, y = self.get_point_coords()
        if self.current_frame is not None:
            h, w = self.current_frame.shape[:2]
            x = max(0, min(w - 1, x + dx))
            y = max(0, min(h - 1, y + dy))
        else:
            x += dx
            y += dy
        self.set_point_coords(x, y)

    def add_stand(self):
        """Add a new stand."""
        # Get reference position from last stand or use default
        if self.stands:
            last = self.stands[-1]
            offset_x = 200
            new_stand = {
                "name": f"Stand {len(self.stands) + 1}",
                "direction": "left_to_right",
                "entry_line": {
                    "start": [
                        last["exit_line"]["start"][0] + offset_x,
                        last["entry_line"]["start"][1],
                    ],
                    "end": [
                        last["exit_line"]["end"][0] + offset_x,
                        last["entry_line"]["end"][1],
                    ],
                },
                "exit_line": {
                    "start": [
                        last["exit_line"]["start"][0] + offset_x + 150,
                        last["exit_line"]["start"][1],
                    ],
                    "end": [
                        last["exit_line"]["end"][0] + offset_x + 150,
                        last["exit_line"]["end"][1],
                    ],
                },
            }
        else:
            new_stand = {
                "name": "Stand 1",
                "direction": "left_to_right",
                "entry_line": {"start": [200, 400], "end": [200, 600]},
                "exit_line": {"start": [350, 400], "end": [350, 600]},
            }

        self.stands.append(new_stand)
        self.selected_stand_index = len(self.stands) - 1
        print(f"Added {new_stand['name']} (total: {len(self.stands)} stands)")

    def remove_stand(self):
        """Remove current stand."""
        if len(self.stands) <= 1:
            print("Cannot remove last stand - need at least 1")
            return

        removed = self.stands.pop(self.selected_stand_index)
        print(f"Removed {removed['name']} (remaining: {len(self.stands)} stands)")

        # Adjust selection
        if self.selected_stand_index >= len(self.stands):
            self.selected_stand_index = len(self.stands) - 1

        # Rename remaining stands
        for i, stand in enumerate(self.stands):
            stand["name"] = f"Stand {i + 1}"

    def check_line_detection(self, line: Dict) -> Tuple[bool, int, float]:
        """Check if a line is detecting hot metal."""
        if self.current_frame is None:
            return False, 0, 0.0

        gray = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2GRAY)

        # Create line mask
        mask = np.zeros(gray.shape, dtype=np.uint8)
        start = tuple(line["start"])
        end = tuple(line["end"])
        cv2.line(mask, start, end, 255, self.line_thickness)

        # Get pixels on line
        line_pixels = gray[mask > 0]
        if len(line_pixels) == 0:
            return False, 0, 0.0

        # Count bright pixels
        bright_mask = line_pixels > self.luminosity_threshold
        bright_pixels = int(np.sum(bright_mask))
        avg_brightness = (
            float(np.mean(line_pixels[bright_mask])) if bright_pixels > 0 else 0.0
        )

        is_triggered = bright_pixels >= self.min_bright_pixels
        return is_triggered, bright_pixels, avg_brightness

    def draw_frame(self) -> np.ndarray:
        """Draw lines and info on current frame."""
        if self.current_frame is None:
            return np.zeros((720, 1280, 3), dtype=np.uint8)

        frame = self.current_frame.copy()

        # Draw all stands
        for i, stand in enumerate(self.stands):
            is_selected_stand = i == self.selected_stand_index

            # Entry line
            entry = stand["entry_line"]
            entry_start = tuple(entry["start"])
            entry_end = tuple(entry["end"])

            entry_color = self.entry_color
            entry_thickness = 2

            if is_selected_stand and self.selected_line == "entry":
                entry_color = self.selected_color
                entry_thickness = 3

            # Test mode - check detection
            if self.test_mode:
                triggered, pixels, _ = self.check_line_detection(entry)
                if triggered:
                    entry_color = (0, 255, 255)  # Yellow when triggered
                    entry_thickness = 4

            cv2.line(frame, entry_start, entry_end, entry_color, entry_thickness)

            # Draw points for selected line
            if is_selected_stand and self.selected_line == "entry":
                self._draw_point(
                    frame, entry_start, "S", self.selected_point == "start"
                )
                self._draw_point(frame, entry_end, "E", self.selected_point == "end")

            # Exit line
            exit_line = stand["exit_line"]
            exit_start = tuple(exit_line["start"])
            exit_end = tuple(exit_line["end"])

            exit_color = self.exit_color
            exit_thickness = 2

            if is_selected_stand and self.selected_line == "exit":
                exit_color = self.selected_color
                exit_thickness = 3

            # Test mode - check detection
            if self.test_mode:
                triggered, pixels, _ = self.check_line_detection(exit_line)
                if triggered:
                    exit_color = (0, 255, 255)  # Yellow when triggered
                    exit_thickness = 4

            cv2.line(frame, exit_start, exit_end, exit_color, exit_thickness)

            # Draw points for selected line
            if is_selected_stand and self.selected_line == "exit":
                self._draw_point(frame, exit_start, "S", self.selected_point == "start")
                self._draw_point(frame, exit_end, "E", self.selected_point == "end")

            # Stand label
            label_x = min(entry_start[0], exit_start[0])
            label_y = min(entry_start[1], exit_start[1]) - 15
            label_color = self.selected_color if is_selected_stand else (200, 200, 200)
            cv2.putText(
                frame,
                stand["name"],
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                label_color,
                2,
            )

        # Draw info panel
        self._draw_info_panel(frame)

        # Draw timeline
        self._draw_timeline(frame)

        return frame

    def _draw_point(
        self, frame: np.ndarray, point: Tuple[int, int], label: str, is_selected: bool
    ):
        """Draw a point marker."""
        color = (255, 255, 255) if is_selected else (150, 150, 150)
        radius = 8 if is_selected else 5
        cv2.circle(frame, point, radius, color, -1)
        cv2.circle(frame, point, radius, (0, 0, 0), 1)
        cv2.putText(
            frame,
            label,
            (point[0] + 10, point[1] + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
        )

    def _draw_info_panel(self, frame: np.ndarray):
        """Draw information panel."""
        # Background
        cv2.rectangle(frame, (5, 5), (380, 180), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, 5), (380, 180), (255, 255, 255), 1)

        y = 25
        stand = self.current_stand

        # Stand info
        cv2.putText(
            frame,
            f"Stand: {stand['name']} ({self.selected_stand_index + 1}/{len(self.stands)})",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            self.selected_color,
            2,
        )
        y += 22

        # Line info
        line_name = "ENTRY" if self.selected_line == "entry" else "EXIT"
        line_color = (
            self.entry_color if self.selected_line == "entry" else self.exit_color
        )
        cv2.putText(
            frame,
            f"Line: {line_name}",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            line_color,
            2,
        )
        y += 20

        # Point info
        point_label = "START" if self.selected_point == "start" else "END"
        coords = self.get_point_coords()
        cv2.putText(
            frame,
            f"Point: {point_label} ({coords[0]}, {coords[1]})",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        y += 20

        # Line coordinates
        line = self.current_line
        if line:
            cv2.putText(
                frame,
                f"Start: {line['start']} -> End: {line['end']}",
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (150, 150, 150),
                1,
            )
        y += 22

        # Test mode
        if self.test_mode:
            cv2.putText(
                frame,
                "TEST MODE: ON",
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                2,
            )
            y += 18

            # Show detection status for current stand
            entry_triggered, entry_px, _ = self.check_line_detection(
                stand["entry_line"]
            )
            exit_triggered, exit_px, _ = self.check_line_detection(stand["exit_line"])

            entry_status = f"Entry: {entry_px}px" + (" [ON]" if entry_triggered else "")
            exit_status = f"Exit: {exit_px}px" + (" [ON]" if exit_triggered else "")

            cv2.putText(
                frame,
                entry_status,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                self.entry_color,
                1,
            )
            y += 16
            cv2.putText(
                frame,
                exit_status,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                self.exit_color,
                1,
            )
        else:
            cv2.putText(
                frame,
                "Test mode: off (T to toggle)",
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (150, 150, 150),
                1,
            )
        y += 20

        # Controls hint
        cv2.putText(
            frame,
            "Tab=stand  E/X=line  R/N=point  Arrows=move",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (150, 150, 150),
            1,
        )
        y += 15
        cv2.putText(
            frame,
            "Space=play  V=save  H=help  Q=quit",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (150, 150, 150),
            1,
        )

    def _draw_timeline(self, frame: np.ndarray):
        """Draw video timeline."""
        frame_h, frame_w = frame.shape[:2]
        bar_height = 30
        bar_y = frame_h - bar_height - 5

        # Background
        cv2.rectangle(frame, (5, bar_y), (frame_w - 5, frame_h - 5), (0, 0, 0), -1)

        # Progress bar
        bar_width = frame_w - 100
        progress = self.frame_num / max(1, self.total_frames - 1)
        progress_width = int(bar_width * progress)

        cv2.rectangle(
            frame, (50, bar_y + 8), (50 + bar_width, bar_y + 22), (50, 50, 50), -1
        )
        cv2.rectangle(
            frame, (50, bar_y + 8), (50 + progress_width, bar_y + 22), (0, 200, 0), -1
        )

        # Time text
        current_time = self.frame_num / self.fps
        total_time = self.total_frames / self.fps
        time_text = f"{int(current_time // 60)}:{int(current_time % 60):02d} / {int(total_time // 60)}:{int(total_time % 60):02d}"
        cv2.putText(
            frame,
            time_text,
            (50, bar_y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (200, 200, 200),
            1,
        )

        # Frame number
        frame_text = f"Frame: {self.frame_num}/{self.total_frames}"
        cv2.putText(
            frame,
            frame_text,
            (frame_w - 150, bar_y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (150, 150, 150),
            1,
        )

        # Play/Pause
        status = "PLAY" if self.playing else "PAUSE"
        cv2.putText(
            frame,
            status,
            (10, bar_y + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (200, 200, 200),
            1,
        )

    def print_config(self):
        """Print current configuration."""
        print("\n" + "=" * 60)
        print("CURRENT CONFIGURATION")
        print("=" * 60)
        for i, stand in enumerate(self.stands):
            print(f"\n{stand['name']}:")
            print(f"  Direction: {stand['direction']}")
            print(
                f"  Entry line: {stand['entry_line']['start']} -> {stand['entry_line']['end']}"
            )
            print(
                f"  Exit line:  {stand['exit_line']['start']} -> {stand['exit_line']['end']}"
            )
        print("=" * 60 + "\n")

    def save_config(self):
        """Save configuration to settings.yaml."""
        config_path = PROJECT_ROOT / "config" / "settings.yaml"

        try:
            # Load existing config
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            # Build mill_stand_lines section
            config["mill_stand_lines"] = {
                "enabled": True,
                "stands": self.stands,
                "voting": {
                    "window_seconds": 5.0,
                    "min_stands_required": None,  # null = majority
                },
                "counting": {
                    "luminosity_threshold": self.luminosity_threshold,
                    "min_bright_pixels": self.min_bright_pixels,
                    "sequence_timeout": self.sequence_timeout,
                    "min_travel_time": 0.2,
                    "min_consecutive_frames": 2,
                    "line_thickness": self.line_thickness,
                    "debounce_time": self.debounce_time,
                    "target_resolution": [704, 576],
                },
            }

            # Save
            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            print(f"\nConfiguration saved to: {config_path}")
            self.print_config()

        except Exception as e:
            print(f"Error saving config: {e}")

    def show_help(self):
        """Print help text."""
        print("""
+================================================================+
|           MILL STAND LINE CALIBRATION CONTROLS                 |
+================================================================+
|  STAND SELECTION                                               |
|    Tab           - Cycle to next stand                         |
|    +/=           - Add new stand                               |
|    Delete/Backspace - Remove current stand                     |
|                                                                |
|  LINE SELECTION                                                |
|    E             - Select ENTRY line (green)                   |
|    X             - Select EXIT line (red)                      |
|                                                                |
|  POINT SELECTION                                               |
|    R             - Select START point (R for staRt)            |
|    N             - Select END point (N for eNd)                |
|                                                                |
|  POINT MOVEMENT                                                |
|    Arrow Keys    - Move point by 1 pixel                       |
|    W/A/S/D       - Move point by 10 pixels                     |
|    Shift+WASD    - Move point by 50 pixels                     |
|                                                                |
|  VIDEO NAVIGATION                                              |
|    Space         - Play/Pause                                  |
|    .             - Step forward 1 frame                        |
|    ,             - Step backward 1 frame                       |
|    >             - Jump forward 5 seconds                      |
|    <             - Jump backward 5 seconds                     |
|    0-9           - Jump to 0%-90% of video                     |
|                                                                |
|  TESTING & SAVING                                              |
|    T             - Toggle live detection testing               |
|    V             - Save configuration to settings.yaml         |
|    P             - Print current configuration                 |
|                                                                |
|  OTHER                                                         |
|    H             - Show this help                              |
|    Q/ESC         - Quit                                        |
+================================================================+
        """)

    def run(self):
        """Main calibration loop."""
        if not self.open_video():
            print("Failed to open video. Exiting.")
            return

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1280, 720)

        print("\n" + "=" * 60)
        print("MILL STAND LINE CALIBRATION TOOL")
        print("=" * 60)
        print(f"Loaded {len(self.stands)} stand(s)")
        print("Position entry/exit lines for each stand")
        print("Press 'H' for help, 'V' to save, 'Q' to quit")
        print("=" * 60 + "\n")

        while True:
            # Handle playback
            if self.playing:
                if not self.read_frame():
                    self.playing = False
                    self.read_frame(self.total_frames - 1)

            # Draw and display
            display_frame = self.draw_frame()
            cv2.imshow(self.window_name, display_frame)

            # Handle input
            wait_time = int(1000 / self.fps) if self.playing else 30
            key = cv2.waitKey(wait_time) & 0xFF

            # Quit
            if key == ord("q") or key == 27:  # Q or ESC
                break

            # Stand selection - Tab to cycle
            elif key == 9:  # Tab - next stand
                self.selected_stand_index = (self.selected_stand_index + 1) % len(
                    self.stands
                )
                print(f"Selected: {self.current_stand['name']}")
            elif key == ord("\t"):  # Also tab
                self.selected_stand_index = (self.selected_stand_index + 1) % len(
                    self.stands
                )
                print(f"Selected: {self.current_stand['name']}")

            # Add/remove stands
            elif key == ord("+") or key == ord("="):
                self.add_stand()
            elif key == 127 or key == 8:  # Delete or Backspace
                self.remove_stand()

            # Line selection
            elif key == ord("e"):
                self.selected_line = "entry"
                print(f"Selected: ENTRY line")
            elif key == ord("x"):
                self.selected_line = "exit"
                print(f"Selected: EXIT line")

            # Point selection - using 's' for start and 'n' for end
            elif key == ord("r"):  # R for staRt point (S conflicts with movement)
                self.selected_point = "start"
                print("Selected: START point")
            elif key == ord("n"):  # N for eNd point
                self.selected_point = "end"
                print("Selected: END point")

            # Movement - arrow keys (1 pixel)
            elif key == 82:  # Up
                self.move_point(0, -1)
            elif key == 84:  # Down
                self.move_point(0, 1)
            elif key == 81:  # Left
                self.move_point(-1, 0)
            elif key == 83:  # Right
                self.move_point(1, 0)

            # Movement - WASD (10 pixels)
            elif key == ord("w"):
                self.move_point(0, -10)
            elif key == ord("s"):
                self.move_point(0, 10)
            elif key == ord("a"):
                self.move_point(-10, 0)
            elif key == ord("d"):
                self.move_point(10, 0)

            # Movement - Shift+WASD (50 pixels)
            elif key == ord("W"):
                self.move_point(0, -50)
            elif key == ord("S"):
                self.move_point(0, 50)
            elif key == ord("A"):
                self.move_point(-50, 0)
            elif key == ord("D"):
                self.move_point(50, 0)

            # Video navigation
            elif key == ord(" "):  # Space
                self.playing = not self.playing
                print("Playing" if self.playing else "Paused")
            elif key == ord("."):
                self.playing = False
                self.read_frame(self.frame_num + 1)
            elif key == ord(","):
                self.playing = False
                self.read_frame(self.frame_num - 1)
            elif key == ord(">"):
                self.playing = False
                self.read_frame(self.frame_num + int(5 * self.fps))
            elif key == ord("<"):
                self.playing = False
                self.read_frame(self.frame_num - int(5 * self.fps))

            # Number keys for quick video navigation (0-9 = 0%-90%)
            elif ord("0") <= key <= ord("9"):
                percent = (key - ord("0")) / 10
                target_frame = int(self.total_frames * percent)
                self.playing = False
                self.read_frame(target_frame)
                print(f"Jumped to {int(percent * 100)}%")

            # Testing
            elif key == ord("t"):
                self.test_mode = not self.test_mode
                print(f"Test mode: {'ON' if self.test_mode else 'OFF'}")

            # Config
            elif key == ord("p"):
                self.print_config()
            elif key == ord("v"):
                self.save_config()

            # Help
            elif key == ord("h"):
                self.show_help()

        # Cleanup
        self.cap.release()
        cv2.destroyAllWindows()

        print("\nFinal configuration:")
        self.print_config()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Mill Stand Line Calibration Tool")
    parser.add_argument("--video", type=str, help="Path to video file")
    args = parser.parse_args()

    calibrator = MillStandLineCalibrator(video_path=args.video)
    calibrator.run()


if __name__ == "__main__":
    main()
