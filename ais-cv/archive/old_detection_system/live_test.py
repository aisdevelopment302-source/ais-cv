#!/usr/bin/env python3
"""Live Detection Test - Run for 60 seconds and show detection status"""

import cv2
import yaml
import time
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detector import HotStockDetector
from state_machine import ProductionStateMachine, ProductionState

def load_config():
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    
    # Initialize detector
    detector = HotStockDetector(
        roi=config['roi']['furnace_door'],
        luminosity_threshold=config['detection']['luminosity_threshold'],
        luminosity_min_pixels=config['detection']['luminosity_min_pixels'],
        motion_threshold=config['detection']['motion_threshold'],
        motion_min_area=config['detection']['motion_min_area']
    )
    
    # Initialize state machine
    state_machine = ProductionStateMachine(
        break_threshold_seconds=config['detection']['break_threshold_seconds'],
        min_run_duration_seconds=config['detection']['min_run_duration_seconds']
    )
    
    # Connect to stream
    rtsp_url = config['camera']['rtsp_url']
    print(f"Connecting to: {config['camera']['name']}...")
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    if not cap.isOpened():
        print("ERROR: Failed to connect to camera")
        sys.exit(1)
    
    print("Connected! Running live detection test for 60 seconds...")
    print("=" * 70)
    print(f"{'Time':<12} {'State':<8} {'Hot Stock':<10} {'Confidence':<12} {'Bright Px':<10} {'Motion':<10}")
    print("=" * 70)
    
    start_time = time.time()
    test_duration = 60  # seconds
    process_interval = 1.0  # 1 FPS
    last_process_time = 0
    
    frame_count = 0
    detections = []
    
    try:
        while time.time() - start_time < test_duration:
            ret, frame = cap.read()
            if not ret:
                print("Frame read failed, reconnecting...")
                time.sleep(1)
                continue
            
            current_time = time.time()
            
            # Process at 1 FPS
            if current_time - last_process_time >= process_interval:
                last_process_time = current_time
                frame_count += 1
                
                # Run detection
                result = detector.detect(frame)
                
                # Update state machine
                state_change = state_machine.update(result.hot_stock_detected, result.confidence)
                
                # Record detection
                detections.append({
                    'time': datetime.now(),
                    'hot_stock': result.hot_stock_detected,
                    'confidence': result.confidence,
                    'bright_pixels': result.bright_pixels,
                    'motion_area': result.motion_area,
                    'state': state_machine.current_state
                })
                
                # Print status
                timestamp = datetime.now().strftime("%H:%M:%S")
                state = state_machine.current_state.value
                hot_stock = "YES" if result.hot_stock_detected else "no"
                confidence = f"{result.confidence:.1f}%"
                bright = result.bright_pixels
                motion = result.motion_area
                
                # Highlight state changes
                if state_change:
                    print(f"\n>>> STATE CHANGE: {state_change.previous_state.value} -> {state_change.new_state.value} <<<")
                
                print(f"{timestamp:<12} {state:<8} {hot_stock:<10} {confidence:<12} {bright:<10} {motion:<10}")
                
                # Save sample frames
                if frame_count in [1, 30, 60]:  # First, middle, last
                    sample_path = PROJECT_ROOT / "data" / f"live_test_frame_{frame_count}.jpg"
                    cv2.imwrite(str(sample_path), frame)
            
            time.sleep(0.01)  # Prevent CPU spinning
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        cap.release()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    total_detections = len(detections)
    hot_stock_count = sum(1 for d in detections if d['hot_stock'])
    
    print(f"Total frames processed: {total_detections}")
    print(f"Hot stock detected: {hot_stock_count} frames ({100*hot_stock_count/total_detections:.1f}%)")
    print(f"No hot stock: {total_detections - hot_stock_count} frames")
    
    if detections:
        avg_confidence = sum(d['confidence'] for d in detections) / len(detections)
        avg_bright = sum(d['bright_pixels'] for d in detections) / len(detections)
        print(f"Average confidence: {avg_confidence:.1f}%")
        print(f"Average bright pixels: {avg_bright:.0f}")
    
    print(f"\nFinal state: {state_machine.current_state.value}")
    print(f"Sample frames saved to: {PROJECT_ROOT / 'data'}/")

if __name__ == "__main__":
    main()
