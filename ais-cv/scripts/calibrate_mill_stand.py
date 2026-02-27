#!/usr/bin/env python3
"""
Mill Stand Zone Calibration Tool
=================================
Video-based tool for positioning detection zones around the mill stand.

Controls:
  Zone Selection:
    L           - Select LEFT zone
    R           - Select RIGHT zone

  Zone Movement:
    Arrow Keys  - Move zone by 1 pixel
    W/A/S/D     - Move zone by 10 pixels

  Zone Resize:
    +/=         - Increase width by 10px
    -           - Decrease width by 10px
    ]/}         - Increase height by 10px
    [/{         - Decrease height by 10px

  Zone Rotation:
    E           - Rotate clockwise by 1 degree
    F           - Rotate counter-clockwise by 1 degree
    Shift+E     - Rotate clockwise by 5 degrees
    Shift+F     - Rotate counter-clockwise by 5 degrees

  Video Navigation:
    Space       - Play/Pause
    ./>         - Step forward 1 frame / 5 seconds
    ,/<         - Step backward 1 frame / 5 seconds
    0-9         - Jump to 0%-90% of video

  Testing:
    T           - Toggle live detection testing

  Saving:
    V           - Save zones to settings.yaml
    P           - Print current zone coordinates

  Other:
    H           - Show help
    Q/ESC       - Quit

Usage:
    python scripts/calibrate_mill_stand.py
    python scripts/calibrate_mill_stand.py --video path/to/video.mp4
"""

import cv2
import numpy as np
import yaml
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class MillStandCalibrator:
    def __init__(self, video_path: str = None):
        # Default zone positions (for 1920x1080 video)
        # Default angle is -15 degrees (counter-clockwise) for tilted camera
        self.zones = {
            "LEFT": {
                "x": 200,
                "y": 400,
                "width": 150,
                "height": 250,
                "angle": -15,
                "color": (0, 255, 0),
                "name": "Left Zone",
            },
            "RIGHT": {
                "x": 1600,
                "y": 400,
                "width": 150,
                "height": 250,
                "angle": -15,
                "color": (0, 0, 255),
                "name": "Right Zone",
            },
        }

        # Try to load existing config
        self.load_config()

        # Selection state
        self.selected_zone = "LEFT"

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
        self.min_bright_pixels = 100

        # Window
        self.window_name = "Mill Stand Calibration - Press H for Help"

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
        """Load zone positions from settings.yaml if available."""
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
        if not config_path.exists():
            print("No settings.yaml found, using defaults")
            return

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            mill_stand = config.get("mill_stand", {})
            zones = mill_stand.get("zones", {})

            if "left" in zones:
                self.zones["LEFT"].update(
                    {
                        "x": zones["left"].get("x", self.zones["LEFT"]["x"]),
                        "y": zones["left"].get("y", self.zones["LEFT"]["y"]),
                        "width": zones["left"].get(
                            "width", self.zones["LEFT"]["width"]
                        ),
                        "height": zones["left"].get(
                            "height", self.zones["LEFT"]["height"]
                        ),
                        "angle": zones["left"].get(
                            "angle", self.zones["LEFT"]["angle"]
                        ),
                    }
                )

            if "right" in zones:
                self.zones["RIGHT"].update(
                    {
                        "x": zones["right"].get("x", self.zones["RIGHT"]["x"]),
                        "y": zones["right"].get("y", self.zones["RIGHT"]["y"]),
                        "width": zones["right"].get(
                            "width", self.zones["RIGHT"]["width"]
                        ),
                        "height": zones["right"].get(
                            "height", self.zones["RIGHT"]["height"]
                        ),
                        "angle": zones["right"].get(
                            "angle", self.zones["RIGHT"]["angle"]
                        ),
                    }
                )

            # Load counting config for testing
            counting = mill_stand.get("counting", {})
            self.luminosity_threshold = counting.get("luminosity_threshold", 160)
            self.min_bright_pixels = counting.get("min_bright_pixels", 100)

            print("Loaded zone positions from settings.yaml")

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

    def get_rotated_box(self, zone: dict) -> np.ndarray:
        """Get the 4 corner points of a rotated rectangle zone."""
        x, y, w, h = zone["x"], zone["y"], zone["width"], zone["height"]
        angle = zone.get("angle", 0)

        # Calculate center of the rectangle
        center_x = x + w / 2
        center_y = y + h / 2

        # Create rotated rectangle and get box points
        rect = ((center_x, center_y), (w, h), angle)
        box = cv2.boxPoints(rect)
        box = np.intp(box)  # np.int0 deprecated in NumPy 2.0
        return box

    def check_zone_detection(self, zone_id: str) -> tuple:
        """Check if zone is detecting hot metal (for testing). Supports rotated rectangles."""
        if self.current_frame is None:
            return False, 0, 0.0

        zone = self.zones[zone_id]

        # Get rotated rectangle mask
        frame_h, frame_w = self.current_frame.shape[:2]
        box = self.get_rotated_box(zone)

        mask = np.zeros((frame_h, frame_w), dtype=np.uint8)
        cv2.fillPoly(mask, [box], 255)

        # Get pixels within the rotated zone
        gray = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2GRAY)
        zone_pixels = gray[mask > 0]

        if zone_pixels.size == 0:
            return False, 0, 0.0

        # Count bright pixels
        bright_mask = zone_pixels > self.luminosity_threshold
        bright_pixels = int(np.sum(bright_mask))
        avg_brightness = (
            float(np.mean(zone_pixels[bright_mask])) if bright_pixels > 0 else 0
        )

        is_triggered = bright_pixels >= self.min_bright_pixels

        return is_triggered, bright_pixels, avg_brightness

    def draw_frame(self) -> np.ndarray:
        """Draw zones (rotated rectangles) and info on current frame."""
        if self.current_frame is None:
            return np.zeros((576, 1024, 3), dtype=np.uint8)

        frame = self.current_frame.copy()
        frame_h, frame_w = frame.shape[:2]

        # Draw zones as rotated rectangles
        for zone_id, zone in self.zones.items():
            color = zone["color"]
            box = self.get_rotated_box(zone)

            # Selection highlight
            is_selected = zone_id == self.selected_zone
            thickness = 3 if is_selected else 2

            # Test mode: check detection
            if self.test_mode:
                is_triggered, pixels, brightness = self.check_zone_detection(zone_id)
                if is_triggered:
                    # Semi-transparent fill overlay when triggered
                    overlay = frame.copy()
                    cv2.fillPoly(overlay, [box], color)
                    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                    thickness = 4

            # Draw rotated rectangle outline
            cv2.polylines(frame, [box], isClosed=True, color=color, thickness=thickness)

            # Draw selection indicator (outer white border)
            if is_selected:
                cv2.polylines(
                    frame, [box], isClosed=True, color=(255, 255, 255), thickness=1
                )

            # Draw label at the top-most point
            top_point = box[np.argmin(box[:, 1])]
            label = zone_id
            if self.test_mode:
                is_triggered, pixels, _ = self.check_zone_detection(zone_id)
                label += f" [{pixels}px]" if is_triggered else " [-]"

            cv2.putText(
                frame,
                label,
                (top_point[0], top_point[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

        # Draw info panel (top-left)
        self._draw_info_panel(frame)

        # Draw video timeline (bottom)
        self._draw_timeline(frame)

        return frame

    def _draw_info_panel(self, frame: np.ndarray):
        """Draw information panel on frame."""
        # Background
        cv2.rectangle(frame, (5, 5), (350, 165), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, 5), (350, 165), (255, 255, 255), 1)

        y = 25
        zone = self.zones[self.selected_zone]

        # Selection info
        cv2.putText(
            frame,
            f"Selected: {self.selected_zone}",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            zone["color"],
            2,
        )
        y += 22

        cv2.putText(
            frame,
            f"Position: x={zone['x']}, y={zone['y']}",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        y += 18

        cv2.putText(
            frame,
            f"Size: {zone['width']} x {zone['height']}",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        y += 18

        cv2.putText(
            frame,
            f"Angle: {zone.get('angle', 0)} deg",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 200, 200),
            1,
        )
        y += 22

        # Test mode indicator
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
        y += 22

        # Controls hint
        cv2.putText(
            frame,
            "L/R=zone  Arrows=move  +/-=size  E/F=rotate",
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
        """Draw video timeline at bottom of frame."""
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

        # Play/Pause indicator
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

    def move_zone(self, dx: int, dy: int):
        """Move selected zone."""
        zone = self.zones[self.selected_zone]
        zone["x"] = max(0, zone["x"] + dx)
        zone["y"] = max(0, zone["y"] + dy)

    def resize_zone(self, dw: int, dh: int):
        """Resize selected zone."""
        zone = self.zones[self.selected_zone]
        zone["width"] = max(20, zone["width"] + dw)
        zone["height"] = max(20, zone["height"] + dh)

    def rotate_zone(self, delta_angle: float):
        """Rotate selected zone by delta_angle degrees."""
        zone = self.zones[self.selected_zone]
        current_angle = zone.get("angle", 0)
        # Clamp angle to -180 to 180 range
        new_angle = current_angle + delta_angle
        if new_angle > 180:
            new_angle -= 360
        elif new_angle < -180:
            new_angle += 360
        zone["angle"] = new_angle

    def print_coordinates(self):
        """Print current zone coordinates."""
        print("\n" + "=" * 50)
        print("CURRENT ZONE COORDINATES")
        print("=" * 50)
        for zone_id, zone in self.zones.items():
            print(
                f"{zone_id}: x={zone['x']}, y={zone['y']}, "
                f"width={zone['width']}, height={zone['height']}, "
                f"angle={zone.get('angle', 0)}"
            )
        print("=" * 50 + "\n")

    def save_config(self):
        """Save zone configuration to settings.yaml."""
        config_path = PROJECT_ROOT / "config" / "settings.yaml"

        try:
            # Load existing config
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)
            else:
                config = {}

            # Ensure mill_stand section exists
            if "mill_stand" not in config:
                config["mill_stand"] = {}

            # Update zones (including angle)
            config["mill_stand"]["zones"] = {
                "left": {
                    "x": self.zones["LEFT"]["x"],
                    "y": self.zones["LEFT"]["y"],
                    "width": self.zones["LEFT"]["width"],
                    "height": self.zones["LEFT"]["height"],
                    "angle": self.zones["LEFT"].get("angle", -15),
                },
                "right": {
                    "x": self.zones["RIGHT"]["x"],
                    "y": self.zones["RIGHT"]["y"],
                    "width": self.zones["RIGHT"]["width"],
                    "height": self.zones["RIGHT"]["height"],
                    "angle": self.zones["RIGHT"].get("angle", -15),
                },
            }

            # Enable mill stand
            config["mill_stand"]["enabled"] = True

            # Save config
            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            print(f"\nConfiguration saved to: {config_path}")
            self.print_coordinates()

        except Exception as e:
            print(f"Error saving config: {e}")

    def show_help(self):
        """Print help text."""
        print("""
╔═══════════════════════════════════════════════════════════════╗
║              MILL STAND CALIBRATION CONTROLS                  ║
╠═══════════════════════════════════════════════════════════════╣
║  ZONE SELECTION                                               ║
║    L           - Select LEFT zone (green)                     ║
║    R           - Select RIGHT zone (red)                      ║
║                                                               ║
║  ZONE MOVEMENT                                                ║
║    Arrow Keys  - Move zone by 1 pixel                         ║
║    W/A/S/D     - Move zone by 10 pixels                       ║
║                                                               ║
║  ZONE RESIZE                                                  ║
║    +/=         - Increase width by 10px                       ║
║    -           - Decrease width by 10px                       ║
║    ]/}         - Increase height by 10px                      ║
║    [/{         - Decrease height by 10px                      ║
║                                                               ║
║  ZONE ROTATION                                                ║
║    E           - Rotate clockwise by 1 degree                 ║
║    F           - Rotate counter-clockwise by 1 degree         ║
║    Shift+E     - Rotate clockwise by 5 degrees                ║
║    Shift+F     - Rotate counter-clockwise by 5 degrees        ║
║                                                               ║
║  VIDEO NAVIGATION                                             ║
║    Space       - Play/Pause video                             ║
║    .           - Step forward 1 frame                         ║
║    ,           - Step backward 1 frame                        ║
║    >           - Jump forward 5 seconds                       ║
║    <           - Jump backward 5 seconds                      ║
║    0-9         - Jump to 0%-90% of video                      ║
║                                                               ║
║  TESTING & SAVING                                             ║
║    T           - Toggle live detection testing                ║
║    V           - Save zones to settings.yaml                  ║
║    P           - Print current coordinates                    ║
║                                                               ║
║  OTHER                                                        ║
║    H           - Show this help                               ║
║    Q/ESC       - Quit                                         ║
╚═══════════════════════════════════════════════════════════════╝
        """)

    def run(self):
        """Main calibration loop."""
        # Open video
        if not self.open_video():
            print("Failed to open video. Exiting.")
            return

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1280, 720)

        print("\n" + "=" * 50)
        print("MILL STAND CALIBRATION TOOL")
        print("=" * 50)
        print("Position the LEFT and RIGHT detection zones")
        print("around the mill stand entry/exit points.")
        print("Press 'H' for help, 'V' to save, 'Q' to quit")
        print("=" * 50 + "\n")

        while True:
            # Handle playback
            if self.playing:
                if not self.read_frame():
                    self.playing = False
                    self.read_frame(self.total_frames - 1)

            # Draw and display frame
            display_frame = self.draw_frame()
            cv2.imshow(self.window_name, display_frame)

            # Handle keyboard input
            wait_time = int(1000 / self.fps) if self.playing else 30
            key = cv2.waitKey(wait_time) & 0xFF

            # Quit
            if key == ord("q") or key == 27:  # Q or ESC
                break

            # Zone selection
            elif key == ord("l"):
                self.selected_zone = "LEFT"
                print("Selected: LEFT zone")
            elif key == ord("r"):
                self.selected_zone = "RIGHT"
                print("Selected: RIGHT zone")

            # Movement - arrow keys (1 pixel)
            elif key == 82:  # Up
                self.move_zone(0, -1)
            elif key == 84:  # Down
                self.move_zone(0, 1)
            elif key == 81:  # Left
                self.move_zone(-1, 0)
            elif key == 83:  # Right
                self.move_zone(1, 0)

            # Movement - WASD (10 pixels)
            elif key == ord("w"):
                self.move_zone(0, -10)
            elif key == ord("s"):
                self.move_zone(0, 10)
            elif key == ord("a"):
                self.move_zone(-10, 0)
            elif key == ord("d"):
                self.move_zone(10, 0)

            # Resize width
            elif key == ord("+") or key == ord("="):
                self.resize_zone(10, 0)
            elif key == ord("-"):
                self.resize_zone(-10, 0)

            # Resize height
            elif key == ord("]") or key == ord("}"):
                self.resize_zone(0, 10)
            elif key == ord("[") or key == ord("{"):
                self.resize_zone(0, -10)

            # Rotation - E/F (1 degree), Shift+E/Shift+F (5 degrees)
            elif key == ord("e"):  # Rotate clockwise 1 degree
                self.rotate_zone(1)
            elif key == ord("E"):  # Shift+E - Rotate clockwise 5 degrees
                self.rotate_zone(5)
            elif key == ord("f"):  # Rotate counter-clockwise 1 degree
                self.rotate_zone(-1)
            elif key == ord("F"):  # Shift+F - Rotate counter-clockwise 5 degrees
                self.rotate_zone(-5)

            # Video navigation
            elif key == ord(" "):  # Space - play/pause
                self.playing = not self.playing
                print("Playing" if self.playing else "Paused")
            elif key == ord("."):  # Step forward
                self.playing = False
                self.read_frame(self.frame_num + 1)
            elif key == ord(","):  # Step backward
                self.playing = False
                self.read_frame(self.frame_num - 1)
            elif key == ord(">"):  # Jump forward 5s
                self.playing = False
                self.read_frame(self.frame_num + int(5 * self.fps))
            elif key == ord("<"):  # Jump backward 5s
                self.playing = False
                self.read_frame(self.frame_num - int(5 * self.fps))

            # Number keys for quick navigation (0-9 = 0%-90%)
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

            # Print coordinates
            elif key == ord("p"):
                self.print_coordinates()

            # Save config
            elif key == ord("v"):
                self.save_config()

            # Help
            elif key == ord("h"):
                self.show_help()

        # Cleanup
        self.cap.release()
        cv2.destroyAllWindows()

        print("\nFinal zone positions:")
        self.print_coordinates()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Mill Stand Zone Calibration Tool")
    parser.add_argument("--video", type=str, help="Path to video file")
    args = parser.parse_args()

    calibrator = MillStandCalibrator(video_path=args.video)
    calibrator.run()


if __name__ == "__main__":
    main()
