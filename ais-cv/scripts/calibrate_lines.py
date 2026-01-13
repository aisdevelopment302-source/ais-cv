#!/usr/bin/env python3
"""
Interactive Line Calibration Tool
=================================
Adjust counting lines on conveyor using keyboard.

Controls:
  1, 2, 3    - Select Line 1 (Green), Line 2 (Yellow), Line 3 (Red)
  S, E       - Select Start point or End point of current line
  Arrow Keys - Move selected point (Up/Down/Left/Right)
  Shift+Arrow- Move by 10 pixels instead of 1
  A          - Select flow Arrow
  R          - Reset to default positions
  P          - Print current coordinates
  C          - Capture new frame from camera
  V          - Save configuration to settings.yaml
  Q/ESC      - Quit and save

"""

import cv2
import numpy as np
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

class LineCalibrator:
    def __init__(self):
        # Default line positions
        self.lines = {
            'L1': {'start': [480, 225], 'end': [540, 215], 'color': (0, 255, 0), 'name': 'Line 1 (Green)'},
            'L2': {'start': [525, 280], 'end': [585, 270], 'color': (0, 255, 255), 'name': 'Line 2 (Yellow)'},
            'L3': {'start': [565, 335], 'end': [630, 325], 'color': (0, 0, 255), 'name': 'Line 3 (Red)'},
        }
        
        # Flow arrow
        self.arrow = {'start': [530, 215], 'end': [620, 330]}
        
        # Selection state
        self.selected_line = 'L1'
        self.selected_point = 'start'  # 'start' or 'end'
        self.selected_arrow = False
        
        # Load image
        self.image_path = PROJECT_ROOT / "data" / "plate_seq_3.jpg"
        self.original_frame = None
        self.load_image()
        
        # Window
        self.window_name = "Line Calibrator - Press H for Help"
        
    def load_image(self):
        """Load the calibration image"""
        if self.image_path.exists():
            self.original_frame = cv2.imread(str(self.image_path))
            print(f"Loaded: {self.image_path}")
        else:
            print(f"Image not found: {self.image_path}")
            # Create blank frame
            self.original_frame = np.zeros((576, 704, 3), dtype=np.uint8)
    
    def capture_new_frame(self):
        """Capture fresh frame from camera"""
        try:
            config_path = PROJECT_ROOT / "config" / "settings.yaml"
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            rtsp_url = config['camera']['rtsp_url']
            print(f"Capturing from camera...")
            
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            for _ in range(10):
                cap.grab()
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                self.original_frame = frame
                cv2.imwrite(str(self.image_path), frame)
                print("New frame captured!")
            else:
                print("Failed to capture frame")
        except Exception as e:
            print(f"Error capturing: {e}")
    
    def draw_frame(self):
        """Draw lines on frame"""
        frame = self.original_frame.copy()
        
        # Draw all lines
        for key, line in self.lines.items():
            start = tuple(line['start'])
            end = tuple(line['end'])
            color = line['color']
            thickness = 3 if key == self.selected_line and not self.selected_arrow else 2
            
            cv2.line(frame, start, end, color, thickness)
            
            # Draw points
            point_radius = 6 if key == self.selected_line else 4
            cv2.circle(frame, start, point_radius, color, -1)
            cv2.circle(frame, end, point_radius, color, -1)
            
            # Highlight selected point
            if key == self.selected_line and not self.selected_arrow:
                sel_point = start if self.selected_point == 'start' else end
                cv2.circle(frame, sel_point, 10, (255, 255, 255), 2)
            
            # Label
            cv2.putText(frame, key, (end[0] + 5, end[1] + 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Draw flow arrow
        arrow_color = (255, 255, 255) if not self.selected_arrow else (255, 0, 255)
        arrow_thickness = 3 if self.selected_arrow else 2
        cv2.arrowedLine(frame, tuple(self.arrow['start']), tuple(self.arrow['end']), 
                       arrow_color, arrow_thickness, tipLength=0.2)
        
        if self.selected_arrow:
            sel_point = self.arrow['start'] if self.selected_point == 'start' else self.arrow['end']
            cv2.circle(frame, tuple(sel_point), 10, (255, 0, 255), 2)
        
        # Info panel
        self.draw_info_panel(frame)
        
        return frame
    
    def draw_info_panel(self, frame):
        """Draw info panel on frame"""
        # Background
        cv2.rectangle(frame, (5, 5), (250, 130), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, 5), (250, 130), (255, 255, 255), 1)
        
        y = 22
        # Selection info
        if self.selected_arrow:
            sel_text = f"Selected: ARROW ({self.selected_point})"
            point = self.arrow[self.selected_point]
        else:
            sel_text = f"Selected: {self.selected_line} ({self.selected_point})"
            point = self.lines[self.selected_line][self.selected_point]
        
        cv2.putText(frame, sel_text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        y += 20
        cv2.putText(frame, f"Position: ({point[0]}, {point[1]})", (10, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        y += 25
        
        # Controls hint
        cv2.putText(frame, "1/2/3: Select line  S/E: point", (10, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        y += 15
        cv2.putText(frame, "Arrows: Move  Shift+Arrow: x10", (10, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        y += 15
        cv2.putText(frame, "A: Arrow  C: Capture  V: Save", (10, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        y += 15
        cv2.putText(frame, "P: Print coords  Q: Quit", (10, y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
    
    def move_point(self, dx, dy):
        """Move selected point"""
        if self.selected_arrow:
            self.arrow[self.selected_point][0] += dx
            self.arrow[self.selected_point][1] += dy
        else:
            self.lines[self.selected_line][self.selected_point][0] += dx
            self.lines[self.selected_line][self.selected_point][1] += dy
    
    def print_coordinates(self):
        """Print current coordinates"""
        print("\n" + "="*50)
        print("CURRENT LINE COORDINATES")
        print("="*50)
        for key, line in self.lines.items():
            print(f"{key}: start={tuple(line['start'])}, end={tuple(line['end'])}")
        print(f"Arrow: start={tuple(self.arrow['start'])}, end={tuple(self.arrow['end'])}")
        print("="*50 + "\n")
    
    def save_config(self):
        """Save line configuration to settings.yaml"""
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Add/update counting lines section
            config['counting_lines'] = {
                'line1': {
                    'start': self.lines['L1']['start'],
                    'end': self.lines['L1']['end']
                },
                'line2': {
                    'start': self.lines['L2']['start'],
                    'end': self.lines['L2']['end']
                },
                'line3': {
                    'start': self.lines['L3']['start'],
                    'end': self.lines['L3']['end']
                },
                'flow_direction': {
                    'start': self.arrow['start'],
                    'end': self.arrow['end']
                }
            }
            
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            print(f"\nConfiguration saved to: {config_path}")
            self.print_coordinates()
            
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def run(self):
        """Main loop"""
        cv2.namedWindow(self.window_name)
        
        print("\n" + "="*50)
        print("LINE CALIBRATION TOOL")
        print("="*50)
        print("Use keyboard to adjust lines on the conveyor")
        print("Press 'H' in window for help")
        print("="*50 + "\n")
        
        while True:
            frame = self.draw_frame()
            cv2.imshow(self.window_name, frame)
            
            key = cv2.waitKey(30) & 0xFF
            
            # Quit
            if key == ord('q') or key == 27:  # Q or ESC
                print("Exiting...")
                break
            
            # Select line
            elif key == ord('1'):
                self.selected_line = 'L1'
                self.selected_arrow = False
                print("Selected: Line 1 (Green)")
            elif key == ord('2'):
                self.selected_line = 'L2'
                self.selected_arrow = False
                print("Selected: Line 2 (Yellow)")
            elif key == ord('3'):
                self.selected_line = 'L3'
                self.selected_arrow = False
                print("Selected: Line 3 (Red)")
            
            # Select arrow
            elif key == ord('a'):
                self.selected_arrow = True
                print("Selected: Flow Arrow")
            
            # Select point
            elif key == ord('s'):
                self.selected_point = 'start'
                print("Selected: Start point")
            elif key == ord('e'):
                self.selected_point = 'end'
                print("Selected: End point")
            
            # Movement - check for shift modifier using special key codes
            # Arrow keys with no modifier
            elif key == 82:  # Up
                self.move_point(0, -1)
            elif key == 84:  # Down
                self.move_point(0, 1)
            elif key == 81:  # Left
                self.move_point(-1, 0)
            elif key == 83:  # Right
                self.move_point(1, 0)
            
            # Shift+Arrow for faster movement (capital letters as alternative)
            elif key == ord('w') or key == ord('W'):  # Up fast
                self.move_point(0, -10)
            elif key == ord('x') or key == ord('X'):  # Down fast
                self.move_point(0, 10)
            elif key == ord('z') or key == ord('Z'):  # Left fast
                self.move_point(-10, 0)
            elif key == ord('c') and False:  # Reserved for capture
                pass
            elif key == ord('d') or key == ord('D'):  # Right fast
                self.move_point(10, 0)
            
            # Print coordinates
            elif key == ord('p'):
                self.print_coordinates()
            
            # Capture new frame
            elif key == ord('c'):
                self.capture_new_frame()
            
            # Save config
            elif key == ord('v'):
                self.save_config()
            
            # Reset
            elif key == ord('r'):
                self.lines = {
                    'L1': {'start': [480, 225], 'end': [540, 215], 'color': (0, 255, 0), 'name': 'Line 1'},
                    'L2': {'start': [525, 280], 'end': [585, 270], 'color': (0, 255, 255), 'name': 'Line 2'},
                    'L3': {'start': [565, 335], 'end': [630, 325], 'color': (0, 0, 255), 'name': 'Line 3'},
                }
                self.arrow = {'start': [530, 215], 'end': [620, 330]}
                print("Reset to defaults")
            
            # Help
            elif key == ord('h'):
                print("""
CONTROLS:
  1, 2, 3     - Select Line 1/2/3
  A           - Select flow Arrow
  S           - Select Start point
  E           - Select End point
  Arrow Keys  - Move point by 1 pixel
  W/X/Z/D     - Move point by 10 pixels (Up/Down/Left/Right)
  P           - Print current coordinates
  C           - Capture new frame from camera
  V           - Save to settings.yaml
  R           - Reset to defaults
  Q/ESC       - Quit
                """)
        
        cv2.destroyAllWindows()
        
        # Final save prompt
        print("\nFinal coordinates:")
        self.print_coordinates()

if __name__ == "__main__":
    calibrator = LineCalibrator()
    calibrator.run()
