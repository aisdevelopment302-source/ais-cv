# CV Implementation Plan — Proof of Concept

**Version:** 1.0  
**Date:** 2026-01-10  
**Status:** Ready for Implementation

---

## Hardware Reality (Actual)

### Raspberry Pi
| Spec | Value |
|------|-------|
| **Model** | Raspberry Pi 5 |
| **Location** | Office, near NVR |
| **Network** | Same LAN as NVR |

### NVR & Cameras
| Spec | Value |
|------|-------|
| **NVR Brand** | Dahua |
| **Total Cameras** | 16 |
| **Production-Relevant** | 3 |
| **POC Camera** | 1 (Furnace Opening) |

### Camera Stream Settings (from NVR)

| Stream | Resolution | Codec | FPS | Bitrate |
|--------|------------|-------|-----|---------|
| **Main Stream** | 1920×1080 | H.265 | 25 | 2048 Kb/s |
| **Sub Stream** | 704×576 | H.265 | 25 | 768 Kb/s |

**For CV Processing:** Use **Sub Stream** (704×576) — sufficient for detection, lower CPU load.

### Dahua RTSP URL Format
```
Main Stream: rtsp://{user}:{pass}@{nvr_ip}:554/cam/realmonitor?channel={N}&subtype=0
Sub Stream:  rtsp://{user}:{pass}@{nvr_ip}:554/cam/realmonitor?channel={N}&subtype=1
```

---

## POC Scope: Single Camera (Furnace)

### Goal
Prove that we can reliably detect **RUNNING vs BREAK** from the Furnace Opening camera (CAM-1) alone.

### Success Criteria
| Criteria | Target |
|----------|--------|
| Detect hot stock emergence | ≥95% accuracy |
| Detect break (no stock for 2+ min) | ≥95% accuracy |
| Run continuously for 8 hours | No crashes |
| Log state changes with timestamps | Working |
| Capture sample photos | Working |

### Out of Scope (POC)
- Multi-camera fusion
- Server integration / Firebase
- Dashboard UI
- Validation workflow
- Alerts/notifications

---

## Implementation Phases

### Phase 1: Environment Setup (Day 1)
```
□ Raspberry Pi 5 OS setup (if not done)
□ Install Python 3.11+
□ Install OpenCV, ffmpeg
□ Test RTSP stream access
□ Create project directory structure
```

### Phase 2: Stream Capture (Day 1-2)
```
□ Connect to Furnace camera via RTSP
□ Capture frames reliably
□ Handle stream reconnection
□ Save sample frames for analysis
```

### Phase 3: Detection Logic (Day 2-4)
```
□ Define ROI for furnace opening area
□ Implement luminosity detection (hot stock glow)
□ Implement motion detection
□ Combine into RUNNING/BREAK state
□ Add 2-minute break threshold
□ Test with live feed
```

### Phase 4: Logging & Photos (Day 4-5)
```
□ Log state changes to local file/SQLite
□ Capture photos at state transitions
□ Capture periodic photos during states
□ Store with timestamps and metadata
```

### Phase 5: Validation & Tuning (Day 5-7)
```
□ Run during actual production shift
□ Compare CV detections to manual observations
□ Tune thresholds (luminosity, motion, timing)
□ Document final settings
□ Measure accuracy
```

---

## Project Structure

```
/home/pi/ais-cv/
├── config/
│   └── settings.yaml          # Camera URLs, thresholds, ROI
├── src/
│   ├── __init__.py
│   ├── main.py                # Entry point
│   ├── stream.py              # RTSP stream handler
│   ├── detector.py            # Hot stock detection logic
│   ├── state_machine.py       # RUNNING/BREAK state management
│   ├── logger.py              # Event logging
│   └── photo_capture.py       # Validation photo capture
├── data/
│   ├── logs/                  # State change logs
│   └── photos/                # Captured validation photos
├── tests/
│   └── test_detector.py       # Unit tests with sample frames
├── requirements.txt
└── README.md
```

---

## Configuration File

```yaml
# config/settings.yaml

# Camera Configuration
camera:
  name: "Furnace Opening"
  id: "CAM-1"
  role: "primary"
  
  # Dahua NVR RTSP URL (Sub Stream for processing)
  rtsp_url: "rtsp://admin:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=X&subtype=1"
  
  # Stream settings (match NVR config)
  resolution: [704, 576]
  fps: 25
  codec: "h265"
  
  # Reconnection settings
  reconnect_attempts: 5
  reconnect_delay_seconds: 5

# Region of Interest (to be calibrated)
roi:
  furnace_door:
    x: 100
    y: 50
    width: 500
    height: 400
  # Will be refined during calibration

# Detection Thresholds (to be tuned)
detection:
  # Luminosity (0-255) - hot steel glows bright
  luminosity_threshold: 180
  luminosity_min_pixels: 1000  # Minimum bright pixels to count as "hot stock"
  
  # Motion detection
  motion_threshold: 25         # Pixel difference threshold
  motion_min_area: 500         # Minimum changed area
  
  # State timing
  break_threshold_seconds: 120  # 2 minutes without stock = BREAK
  min_run_duration_seconds: 10  # Ignore very brief detections
  
  # Processing
  process_fps: 1               # Analyze 1 frame per second (sufficient)

# Photo Capture
photos:
  output_dir: "/home/pi/ais-cv/data/photos"
  on_state_change: true
  periodic_interval_seconds: 300  # Every 5 minutes during states
  
# Logging
logging:
  output_dir: "/home/pi/ais-cv/data/logs"
  level: "INFO"
  rotation: "daily"
```

---

## Core Code Modules

### 1. Stream Handler (`src/stream.py`)

```python
"""RTSP Stream Handler for Dahua NVR"""

import cv2
import time
import logging
from typing import Optional, Generator
import numpy as np

logger = logging.getLogger(__name__)

class RTSPStream:
    def __init__(self, rtsp_url: str, reconnect_attempts: int = 5, reconnect_delay: float = 5.0):
        self.rtsp_url = rtsp_url
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.cap: Optional[cv2.VideoCapture] = None
        self.connected = False
        
    def connect(self) -> bool:
        """Connect to RTSP stream"""
        for attempt in range(self.reconnect_attempts):
            logger.info(f"Connecting to stream (attempt {attempt + 1}/{self.reconnect_attempts})")
            
            # Use TCP for reliability (Dahua works better with TCP)
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer for real-time
            
            if self.cap.isOpened():
                self.connected = True
                logger.info("Stream connected successfully")
                return True
            
            logger.warning(f"Connection failed, retrying in {self.reconnect_delay}s...")
            time.sleep(self.reconnect_delay)
        
        logger.error("Failed to connect to stream after all attempts")
        return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """Read a single frame from stream"""
        if not self.connected or self.cap is None:
            return None
            
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to read frame, attempting reconnect...")
            self.connected = False
            self.connect()
            return None
            
        return frame
    
    def frames(self, target_fps: float = 1.0) -> Generator[np.ndarray, None, None]:
        """Generator yielding frames at target FPS"""
        frame_interval = 1.0 / target_fps
        last_frame_time = 0
        
        while True:
            current_time = time.time()
            
            # Read frame (even if we skip it, to keep stream flowing)
            frame = self.read_frame()
            
            # Yield at target FPS
            if current_time - last_frame_time >= frame_interval:
                if frame is not None:
                    yield frame
                    last_frame_time = current_time
            
            # Small sleep to prevent CPU spinning
            time.sleep(0.01)
    
    def release(self):
        """Release stream resources"""
        if self.cap:
            self.cap.release()
            self.connected = False
            logger.info("Stream released")
```

### 2. Hot Stock Detector (`src/detector.py`)

```python
"""Hot Stock Detection for Furnace Camera"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class DetectionResult:
    hot_stock_detected: bool
    luminosity_score: float      # 0-100
    motion_score: float          # 0-100
    confidence: float            # 0-100 combined
    bright_pixels: int
    motion_area: int
    
class HotStockDetector:
    def __init__(
        self,
        roi: dict,
        luminosity_threshold: int = 180,
        luminosity_min_pixels: int = 1000,
        motion_threshold: int = 25,
        motion_min_area: int = 500
    ):
        self.roi = roi
        self.luminosity_threshold = luminosity_threshold
        self.luminosity_min_pixels = luminosity_min_pixels
        self.motion_threshold = motion_threshold
        self.motion_min_area = motion_min_area
        
        self.previous_frame: Optional[np.ndarray] = None
        
    def _extract_roi(self, frame: np.ndarray) -> np.ndarray:
        """Extract region of interest from frame"""
        x = self.roi['x']
        y = self.roi['y']
        w = self.roi['width']
        h = self.roi['height']
        return frame[y:y+h, x:x+w]
    
    def _detect_luminosity(self, roi_frame: np.ndarray) -> Tuple[bool, float, int]:
        """Detect bright/glowing areas (hot steel)"""
        # Convert to grayscale if needed
        if len(roi_frame.shape) == 3:
            gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi_frame
        
        # Count pixels above luminosity threshold
        bright_mask = gray > self.luminosity_threshold
        bright_pixels = np.sum(bright_mask)
        
        # Calculate score (0-100)
        max_possible = roi_frame.shape[0] * roi_frame.shape[1]
        score = min(100, (bright_pixels / self.luminosity_min_pixels) * 50)
        
        detected = bright_pixels >= self.luminosity_min_pixels
        
        return detected, score, bright_pixels
    
    def _detect_motion(self, roi_frame: np.ndarray) -> Tuple[bool, float, int]:
        """Detect motion between frames"""
        # Convert to grayscale
        if len(roi_frame.shape) == 3:
            gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi_frame
        
        # Apply blur to reduce noise
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        
        if self.previous_frame is None:
            self.previous_frame = gray
            return False, 0.0, 0
        
        # Calculate frame difference
        frame_diff = cv2.absdiff(self.previous_frame, gray)
        self.previous_frame = gray
        
        # Threshold the difference
        _, thresh = cv2.threshold(frame_diff, self.motion_threshold, 255, cv2.THRESH_BINARY)
        
        # Count motion pixels
        motion_pixels = np.sum(thresh > 0)
        
        # Find contours for motion area
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion_area = sum(cv2.contourArea(c) for c in contours)
        
        # Calculate score (0-100)
        score = min(100, (motion_area / self.motion_min_area) * 50)
        
        detected = motion_area >= self.motion_min_area
        
        return detected, score, motion_area
    
    def detect(self, frame: np.ndarray) -> DetectionResult:
        """Main detection method - returns if hot stock is detected"""
        roi_frame = self._extract_roi(frame)
        
        # Detect luminosity (glowing hot steel)
        lum_detected, lum_score, bright_pixels = self._detect_luminosity(roi_frame)
        
        # Detect motion (stock moving)
        motion_detected, motion_score, motion_area = self._detect_motion(roi_frame)
        
        # Combined detection logic:
        # Hot stock = bright glowing area detected
        # Motion adds confidence but isn't required (stock might be stationary briefly)
        hot_stock_detected = lum_detected
        
        # Confidence scoring
        # Luminosity is primary (70%), motion is secondary (30%)
        confidence = (lum_score * 0.7) + (motion_score * 0.3)
        
        # Boost confidence if both agree
        if lum_detected and motion_detected:
            confidence = min(100, confidence * 1.2)
        
        return DetectionResult(
            hot_stock_detected=hot_stock_detected,
            luminosity_score=lum_score,
            motion_score=motion_score,
            confidence=confidence,
            bright_pixels=bright_pixels,
            motion_area=motion_area
        )
```

### 3. State Machine (`src/state_machine.py`)

```python
"""Production State Machine - RUNNING vs BREAK"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

class ProductionState(Enum):
    RUNNING = "RUN"
    BREAK = "BRK"
    UNKNOWN = "UNK"

@dataclass
class StateChange:
    timestamp: datetime
    previous_state: ProductionState
    new_state: ProductionState
    confidence: float
    duration_in_previous_seconds: float

class ProductionStateMachine:
    def __init__(
        self,
        break_threshold_seconds: float = 120.0,
        min_run_duration_seconds: float = 10.0,
        on_state_change: Optional[Callable[[StateChange], None]] = None
    ):
        self.break_threshold_seconds = break_threshold_seconds
        self.min_run_duration_seconds = min_run_duration_seconds
        self.on_state_change = on_state_change
        
        # Current state
        self.current_state = ProductionState.UNKNOWN
        self.state_start_time: Optional[float] = None
        
        # Last detection tracking
        self.last_hot_stock_time: Optional[float] = None
        self.last_confidence: float = 0.0
        
        # Debouncing
        self.pending_state: Optional[ProductionState] = None
        self.pending_state_start: Optional[float] = None
        
    def update(self, hot_stock_detected: bool, confidence: float) -> Optional[StateChange]:
        """Update state machine with new detection result"""
        current_time = time.time()
        self.last_confidence = confidence
        
        if hot_stock_detected:
            self.last_hot_stock_time = current_time
        
        # Determine target state
        if hot_stock_detected:
            target_state = ProductionState.RUNNING
        elif self.last_hot_stock_time is None:
            target_state = ProductionState.UNKNOWN
        elif current_time - self.last_hot_stock_time >= self.break_threshold_seconds:
            target_state = ProductionState.BREAK
        else:
            # Within break threshold - maintain current state or RUNNING
            target_state = ProductionState.RUNNING if self.current_state == ProductionState.RUNNING else self.current_state
        
        # Handle state transition
        if target_state != self.current_state:
            return self._transition_to(target_state, current_time, confidence)
        
        return None
    
    def _transition_to(self, new_state: ProductionState, current_time: float, confidence: float) -> Optional[StateChange]:
        """Handle state transition with debouncing"""
        
        # Special case: UNKNOWN -> anything is immediate
        if self.current_state == ProductionState.UNKNOWN:
            return self._commit_transition(new_state, current_time, confidence)
        
        # BREAK -> RUNNING is immediate (production resumed)
        if self.current_state == ProductionState.BREAK and new_state == ProductionState.RUNNING:
            return self._commit_transition(new_state, current_time, confidence)
        
        # RUNNING -> BREAK requires sustained (handled by break_threshold_seconds in update())
        if self.current_state == ProductionState.RUNNING and new_state == ProductionState.BREAK:
            return self._commit_transition(new_state, current_time, confidence)
        
        return None
    
    def _commit_transition(self, new_state: ProductionState, current_time: float, confidence: float) -> StateChange:
        """Commit a state transition"""
        previous_state = self.current_state
        duration = current_time - self.state_start_time if self.state_start_time else 0
        
        self.current_state = new_state
        self.state_start_time = current_time
        
        state_change = StateChange(
            timestamp=datetime.now(),
            previous_state=previous_state,
            new_state=new_state,
            confidence=confidence,
            duration_in_previous_seconds=duration
        )
        
        logger.info(f"State change: {previous_state.value} -> {new_state.value} (confidence: {confidence:.1f}%)")
        
        if self.on_state_change:
            self.on_state_change(state_change)
        
        return state_change
    
    @property
    def time_in_current_state(self) -> float:
        """Seconds in current state"""
        if self.state_start_time is None:
            return 0
        return time.time() - self.state_start_time
    
    @property
    def time_since_last_stock(self) -> Optional[float]:
        """Seconds since hot stock was last detected"""
        if self.last_hot_stock_time is None:
            return None
        return time.time() - self.last_hot_stock_time
```

### 4. Main Application (`src/main.py`)

```python
"""AIS CV POC - Furnace Camera Production Detection"""

import os
import sys
import time
import logging
import yaml
import signal
from datetime import datetime
from pathlib import Path

from stream import RTSPStream
from detector import HotStockDetector
from state_machine import ProductionStateMachine, StateChange, ProductionState

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/pi/ais-cv/data/logs/cv.log')
    ]
)
logger = logging.getLogger(__name__)

class CVApplication:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.running = False
        
        # Initialize components
        self.stream = RTSPStream(
            rtsp_url=self.config['camera']['rtsp_url'],
            reconnect_attempts=self.config['camera']['reconnect_attempts'],
            reconnect_delay=self.config['camera']['reconnect_delay_seconds']
        )
        
        self.detector = HotStockDetector(
            roi=self.config['roi']['furnace_door'],
            luminosity_threshold=self.config['detection']['luminosity_threshold'],
            luminosity_min_pixels=self.config['detection']['luminosity_min_pixels'],
            motion_threshold=self.config['detection']['motion_threshold'],
            motion_min_area=self.config['detection']['motion_min_area']
        )
        
        self.state_machine = ProductionStateMachine(
            break_threshold_seconds=self.config['detection']['break_threshold_seconds'],
            min_run_duration_seconds=self.config['detection']['min_run_duration_seconds'],
            on_state_change=self._on_state_change
        )
        
        # Photo capture
        self.photo_dir = Path(self.config['photos']['output_dir'])
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.last_periodic_photo = 0
        
        # State log
        self.log_dir = Path(self.config['logging']['output_dir'])
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def _load_config(self, config_path: str) -> dict:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _on_state_change(self, change: StateChange):
        """Called when production state changes"""
        # Log state change
        self._log_state_change(change)
        
        # Capture photo
        if self.config['photos']['on_state_change']:
            self._capture_photo(f"state_change_{change.new_state.value}")
    
    def _log_state_change(self, change: StateChange):
        """Log state change to file"""
        log_file = self.log_dir / f"state_changes_{datetime.now().strftime('%Y-%m-%d')}.csv"
        
        # Create header if new file
        if not log_file.exists():
            with open(log_file, 'w') as f:
                f.write("timestamp,previous_state,new_state,confidence,duration_seconds\n")
        
        with open(log_file, 'a') as f:
            f.write(f"{change.timestamp.isoformat()},{change.previous_state.value},{change.new_state.value},{change.confidence:.1f},{change.duration_in_previous_seconds:.1f}\n")
    
    def _capture_photo(self, reason: str):
        """Capture a validation photo"""
        if hasattr(self, 'last_frame') and self.last_frame is not None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            state = self.state_machine.current_state.value
            confidence = self.state_machine.last_confidence
            
            filename = f"{timestamp}_{state}_{reason}_{confidence:.0f}.jpg"
            filepath = self.photo_dir / filename
            
            import cv2
            cv2.imwrite(str(filepath), self.last_frame)
            logger.info(f"Photo captured: {filename}")
    
    def _periodic_photo_check(self):
        """Check if periodic photo should be captured"""
        interval = self.config['photos']['periodic_interval_seconds']
        current_time = time.time()
        
        if current_time - self.last_periodic_photo >= interval:
            self._capture_photo("periodic")
            self.last_periodic_photo = current_time
    
    def run(self):
        """Main processing loop"""
        logger.info("Starting CV Application...")
        
        # Connect to stream
        if not self.stream.connect():
            logger.error("Failed to connect to camera stream. Exiting.")
            return
        
        self.running = True
        process_fps = self.config['detection']['process_fps']
        
        logger.info(f"Processing at {process_fps} FPS")
        logger.info(f"Break threshold: {self.config['detection']['break_threshold_seconds']} seconds")
        
        try:
            for frame in self.stream.frames(target_fps=process_fps):
                if not self.running:
                    break
                
                self.last_frame = frame
                
                # Run detection
                result = self.detector.detect(frame)
                
                # Update state machine
                self.state_machine.update(result.hot_stock_detected, result.confidence)
                
                # Periodic photo
                self._periodic_photo_check()
                
                # Status output (every 10 seconds)
                if int(time.time()) % 10 == 0:
                    state = self.state_machine.current_state.value
                    time_in_state = self.state_machine.time_in_current_state
                    logger.info(f"State: {state} | Duration: {time_in_state:.0f}s | Confidence: {result.confidence:.1f}% | Hot Stock: {result.hot_stock_detected}")
                    
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stream.release()
            logger.info("CV Application stopped")
    
    def stop(self):
        """Stop the application"""
        self.running = False

def main():
    config_path = "/home/pi/ais-cv/config/settings.yaml"
    
    app = CVApplication(config_path)
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        app.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    app.run()

if __name__ == "__main__":
    main()
```

---

## Setup Commands (Raspberry Pi 5)

### Day 1: Environment Setup

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Python and dependencies
sudo apt install -y python3-pip python3-venv python3-opencv ffmpeg

# 3. Create project directory
mkdir -p /home/pi/ais-cv/{config,src,data/logs,data/photos,tests}
cd /home/pi/ais-cv

# 4. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 5. Install Python packages
pip install opencv-python-headless numpy pyyaml

# 6. Create requirements.txt
cat > requirements.txt << EOF
opencv-python-headless>=4.8.0
numpy>=1.24.0
pyyaml>=6.0
EOF

# 7. Test RTSP stream access (replace with your values)
ffplay -rtsp_transport tcp "rtsp://admin:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=X&subtype=1"
# Press 'q' to quit after confirming video works
```

### Test Script (Verify Stream)

```bash
# Create test script
cat > /home/pi/ais-cv/test_stream.py << 'EOF'
import cv2
import sys

# Replace with your actual RTSP URL
RTSP_URL = "rtsp://admin:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=X&subtype=1"

print(f"Connecting to: {RTSP_URL}")
cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("ERROR: Could not open stream")
    sys.exit(1)

print("SUCCESS: Stream connected!")
print(f"Resolution: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
print(f"FPS: {cap.get(cv2.CAP_PROP_FPS)}")

# Capture and save a test frame
ret, frame = cap.read()
if ret:
    cv2.imwrite("/home/pi/ais-cv/data/test_frame.jpg", frame)
    print("Test frame saved to: /home/pi/ais-cv/data/test_frame.jpg")
else:
    print("ERROR: Could not read frame")

cap.release()
EOF

# Run test
python3 /home/pi/ais-cv/test_stream.py
```

---

## ROI Calibration Tool

Before running detection, you need to define the Region of Interest. Run this to capture a reference frame and manually note coordinates:

```python
# /home/pi/ais-cv/calibrate_roi.py
"""ROI Calibration Helper - Capture frame and display coordinates on click"""

import cv2
import sys

RTSP_URL = "rtsp://admin:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=X&subtype=1"

def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"Clicked: x={x}, y={y}")

# Connect and grab frame
cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
ret, frame = cap.read()
cap.release()

if not ret:
    print("Failed to capture frame")
    sys.exit(1)

# Save frame for reference
cv2.imwrite("/home/pi/ais-cv/data/calibration_frame.jpg", frame)
print("Calibration frame saved. Transfer to your computer to view.")
print(f"Frame size: {frame.shape[1]}x{frame.shape[0]}")
print("\nTo define ROI:")
print("1. Open calibration_frame.jpg in an image editor")
print("2. Note the top-left corner (x, y) of the furnace door area")
print("3. Note the width and height of the detection zone")
print("4. Update config/settings.yaml with these values")
```

---

## Running the POC

```bash
# Activate virtual environment
cd /home/pi/ais-cv
source venv/bin/activate

# First: Edit config with your RTSP URL and ROI
nano config/settings.yaml

# Run the application
python src/main.py

# Or run in background with logging
nohup python src/main.py > /home/pi/ais-cv/data/logs/output.log 2>&1 &

# Check logs
tail -f /home/pi/ais-cv/data/logs/cv.log

# View captured photos
ls -la /home/pi/ais-cv/data/photos/

# View state change log
cat /home/pi/ais-cv/data/logs/state_changes_$(date +%Y-%m-%d).csv
```

---

## Systemd Service (Auto-start)

```bash
# Create service file
sudo cat > /etc/systemd/system/ais-cv.service << EOF
[Unit]
Description=AIS CV Production Detection
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/ais-cv
ExecStart=/home/pi/ais-cv/venv/bin/python /home/pi/ais-cv/src/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable ais-cv
sudo systemctl start ais-cv

# Check status
sudo systemctl status ais-cv

# View logs
journalctl -u ais-cv -f
```

---

## Validation Checklist (Day 5-7)

```markdown
## Manual Validation During Live Production

### Setup
- [ ] CV system running
- [ ] Manual stopwatch/notepad ready
- [ ] Positioned to observe furnace

### Record for 4+ hours:

| Time | Actual State | CV State | Match? | Notes |
|------|--------------|----------|--------|-------|
| 06:00 | RUNNING | RUNNING | ✓ | |
| 06:12 | BREAK (roll change) | | | |
| ... | | | | |

### After shift:
1. Export CV state_changes CSV
2. Compare to manual observations
3. Calculate accuracy: Matches / Total observations
4. Note any patterns in misdetections
5. Adjust thresholds if needed
```

---

## Next Steps After POC Success

1. **Share Results** — Send accuracy data and sample photos
2. **Add CAM-2 & CAM-3** — Extend to multi-camera
3. **Server Integration** — Connect to AIS/Firebase (Architect decision)
4. **Validation UI** — Photo review workflow
5. **Dashboard** — Real-time production status

---

## Questions Before Starting

1. **Which channel number is the Furnace camera on your NVR?** (channel=?)
2. **What are your NVR credentials?** (Just need format confirmation - don't share password here)
3. **Is Raspberry Pi 5 OS already installed?** (Raspbian/Debian?)
4. **Do you want me to help you SSH in and set this up?**
