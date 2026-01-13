#!/usr/bin/env python3
"""ROI Visualization Tool - Draw ROI boundaries on test frame"""

import cv2
import yaml
import sys
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent

def load_config():
    """Load settings.yaml"""
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def draw_roi(frame, roi_config, name, color):
    """Draw ROI rectangle with label"""
    x = roi_config['x']
    y = roi_config['y']
    w = roi_config['width']
    h = roi_config['height']
    
    # Draw rectangle
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    
    # Draw label background
    label = f"{name} ({w}x{h})"
    (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x, y - 20), (x + text_w + 4, y), color, -1)
    
    # Draw label text
    cv2.putText(frame, label, (x + 2, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    return frame

def analyze_roi(frame, roi_config, name, threshold):
    """Analyze luminosity within ROI"""
    x = roi_config['x']
    y = roi_config['y']
    w = roi_config['width']
    h = roi_config['height']
    
    # Extract ROI
    roi_frame = frame[y:y+h, x:x+w]
    
    # Convert to grayscale
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    
    # Count bright pixels
    bright_mask = gray > threshold
    bright_pixels = bright_mask.sum()
    total_pixels = w * h
    bright_percent = (bright_pixels / total_pixels) * 100
    
    # Get max/mean brightness
    max_brightness = gray.max()
    mean_brightness = gray.mean()
    
    print(f"\n{name} ROI Analysis:")
    print(f"  Area: {w}x{h} = {total_pixels} pixels")
    print(f"  Brightness threshold: {threshold}")
    print(f"  Bright pixels (>{threshold}): {bright_pixels} ({bright_percent:.1f}%)")
    print(f"  Max brightness: {max_brightness}")
    print(f"  Mean brightness: {mean_brightness:.1f}")
    
    return bright_pixels, bright_percent

def main():
    config = load_config()
    
    # Load test frame
    frame_path = PROJECT_ROOT / "data" / "test_frame.jpg"
    if not frame_path.exists():
        print(f"ERROR: Test frame not found at {frame_path}")
        sys.exit(1)
    
    frame = cv2.imread(str(frame_path))
    print(f"Loaded frame: {frame.shape[1]}x{frame.shape[0]}")
    
    # Get detection threshold
    threshold = config['detection']['luminosity_threshold']
    min_pixels = config['detection']['luminosity_min_pixels']
    
    print(f"\nDetection settings:")
    print(f"  Luminosity threshold: {threshold}")
    print(f"  Min bright pixels required: {min_pixels}")
    
    # Draw primary ROI (furnace_door) - GREEN
    if 'furnace_door' in config['roi']:
        roi = config['roi']['furnace_door']
        frame = draw_roi(frame, roi, "furnace_door", (0, 255, 0))
        bright_pixels, bright_pct = analyze_roi(frame, roi, "furnace_door", threshold)
        
        if bright_pixels >= min_pixels:
            print(f"  >> HOT STOCK DETECTED! ({bright_pixels} >= {min_pixels})")
        else:
            print(f"  >> No hot stock ({bright_pixels} < {min_pixels})")
    
    # Draw secondary ROI (furnace_glow) - YELLOW
    if 'furnace_glow' in config['roi']:
        roi = config['roi']['furnace_glow']
        frame = draw_roi(frame, roi, "furnace_glow", (0, 255, 255))
        analyze_roi(frame, roi, "furnace_glow", threshold)
    
    # Save annotated frame
    output_path = PROJECT_ROOT / "data" / "roi_visualization.jpg"
    cv2.imwrite(str(output_path), frame)
    print(f"\nAnnotated frame saved to: {output_path}")

if __name__ == "__main__":
    main()
