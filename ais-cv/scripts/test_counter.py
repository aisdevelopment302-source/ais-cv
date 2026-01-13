#!/usr/bin/env python3
"""
Live Plate Counter Test
=======================
Run the plate counter on live camera feed and display results.
"""

import cv2
import yaml
import time
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from counter import PlateCounter


def load_config():
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    
    # Initialize counter with calibrated lines
    counter = PlateCounter(
        lines_config=config['counting_lines'],
        luminosity_threshold=180,  # Hot metal brightness
        min_bright_pixels=25,      # Minimum pixels to trigger
        sequence_timeout=4.0,      # Max 4 seconds L1->L3
        min_travel_time=0.3,       # At least 0.3s travel
        line_thickness=10,         # Check 10px around line
    )
    
    # Connect to camera
    rtsp_url = config['camera']['rtsp_url']
    print(f"Connecting to: {config['camera']['name']}...")
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    if not cap.isOpened():
        print("ERROR: Failed to connect to camera")
        sys.exit(1)
    
    print("Connected! Running plate counter...")
    print("=" * 70)
    print(f"{'Time':<12} {'L1':<12} {'L2':<12} {'L3':<12} {'Count':<8} {'Event':<15}")
    print("=" * 70)
    
    start_time = time.time()
    test_duration = 120  # Run for 2 minutes
    frame_count = 0
    last_print_time = 0
    
    try:
        while time.time() - start_time < test_duration:
            ret, frame = cap.read()
            if not ret:
                print("Frame read failed, retrying...")
                time.sleep(0.5)
                continue
            
            frame_count += 1
            
            # Process frame
            counted_piece, status = counter.process_frame(frame)
            
            current_time = time.time()
            
            # Print status every second or on count
            if counted_piece or (current_time - last_print_time >= 1.0):
                last_print_time = current_time
                
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                l1_status = f"{status['L1']['pixels']}px" if status['L1']['triggered'] else "-"
                l2_status = f"{status['L2']['pixels']}px" if status['L2']['triggered'] else "-"
                l3_status = f"{status['L3']['pixels']}px" if status['L3']['triggered'] else "-"
                
                event = ""
                if counted_piece:
                    event = f"*** PIECE #{counted_piece.count_id} ***"
                elif status['L1']['triggered']:
                    event = "L1 active"
                elif status['L2']['triggered']:
                    event = "L2 active"
                elif status['L3']['triggered']:
                    event = "L3 active"
                
                print(f"{timestamp:<12} {l1_status:<12} {l2_status:<12} {l3_status:<12} {status['total_count']:<8} {event:<15}")
            
            # Save frame on count
            if counted_piece:
                overlay_frame = counter.draw_overlay(frame, status)
                filename = f"data/photos/count_{counted_piece.count_id}_{datetime.now().strftime('%H%M%S')}.jpg"
                cv2.imwrite(str(PROJECT_ROOT / filename), overlay_frame)
                print(f"         Photo saved: {filename}")
            
            # Small delay to reduce CPU usage (process at ~10 FPS)
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        cap.release()
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    stats = counter.get_stats()
    print(f"Total pieces counted: {stats['total_count']}")
    
    if stats['total_count'] > 0:
        print(f"Average travel time (L1->L3): {stats['avg_travel_time']:.2f}s")
        print(f"Min travel time: {stats['min_travel_time']:.2f}s")
        print(f"Max travel time: {stats['max_travel_time']:.2f}s")
    
    print(f"\nFrames processed: {frame_count}")
    print(f"Duration: {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
