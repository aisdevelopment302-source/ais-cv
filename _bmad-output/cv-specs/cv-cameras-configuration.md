# CV-CAMERAS: Camera Configuration Specification

**Module:** CV-CAMERAS  
**Version:** 1.0  
**Date:** 2026-01-10  
**Author:** Adityajain (via BMad Master)  
**Status:** Draft — Planning Phase

---

## Executive Summary

This specification defines the camera infrastructure for the AIS Production CV system. Three cameras are positioned at critical points in the rolling mill to monitor production activity: Furnace Opening, Mill Stands, and Cooling Bed.

### Hardware Overview

| Component | Quantity | Purpose |
|-----------|----------|---------|
| IP Cameras | 3 | Video capture at key positions |
| NVR | 1 | Recording, RTSP/ONVIF access |
| Raspberry Pi | 1-3 | Edge processing |
| Network Switch | 1 | Camera network connectivity |

---

## 1. Camera Positions

### 1.1 Camera Layout Overview

```
                    ROLLING MILL FLOOR PLAN
    ┌─────────────────────────────────────────────────────────┐
    │                                                         │
    │   ┌─────────┐                                          │
    │   │ FURNACE │                                          │
    │   │         │                                          │
    │   │   🔥    │──→ [CAM-1: Furnace Opening]              │
    │   │         │         │                                │
    │   └─────────┘         │                                │
    │                       ▼                                │
    │              ═══════════════════                       │
    │              ║  ROLLING MILL   ║                       │
    │              ║    STANDS       ║──→ [CAM-2: Mill Stands]
    │              ║  ▣ ▣ ▣ ▣ ▣ ▣   ║                       │
    │              ═══════════════════                       │
    │                       │                                │
    │                       ▼                                │
    │   ┌─────────────────────────────────┐                  │
    │   │        COOLING BED              │                  │
    │   │   ════════════════════════      │──→ [CAM-3: Cooling Bed]
    │   │   ════════════════════════      │                  │
    │   │   ════════════════════════      │                  │
    │   └─────────────────────────────────┘                  │
    │                                                         │
    └─────────────────────────────────────────────────────────┘
```

### 1.2 Camera Details

#### CAM-1: Furnace Opening

| Attribute | Specification |
|-----------|---------------|
| **Camera ID** | `CAM-1` |
| **Name** | Furnace Opening |
| **Role** | PRIMARY — Determines RUNNING/BREAK state |
| **Position** | Mounted to capture furnace door and extraction area |
| **Field of View** | Furnace opening + 2-3 meters of extraction path |
| **Key Detection** | Hot stock being pulled from furnace |
| **Environment** | High heat exposure, potential steam/smoke |
| **Mounting Height** | 3-4 meters (above heat zone) |
| **Angle** | 30-45° downward, perpendicular to extraction path |

**Region of Interest (ROI):**
```
┌─────────────────────────────────────┐
│                                     │
│    ┌───────────────────────┐       │
│    │   FURNACE DOOR ROI    │       │
│    │                       │       │
│    │    ░░░░░░░░░░░░░     │       │
│    │    ░ Detection  ░     │       │
│    │    ░   Zone     ░     │       │
│    │    ░░░░░░░░░░░░░     │       │
│    │                       │       │
│    └───────────────────────┘       │
│         │                          │
│         ▼ Extraction path ROI      │
│    ┌───────────────────────┐       │
│    │ ░░░░░░░░░░░░░░░░░░░░ │       │
│    └───────────────────────┘       │
│                                     │
└─────────────────────────────────────┘
```

#### CAM-2: Mill Stands

| Attribute | Specification |
|-----------|---------------|
| **Camera ID** | `CAM-2` |
| **Name** | Mill Stands |
| **Role** | SECONDARY — Confirms active production |
| **Position** | Elevated view of rolling stand series |
| **Field of View** | Multiple stands in sequence (as many as possible) |
| **Key Detection** | Hot material moving through stands |
| **Environment** | High noise, vibration, occasional sparks |
| **Mounting Height** | 4-5 meters (clear view over stands) |
| **Angle** | Side view or angled overhead |

**Region of Interest (ROI):**
```
┌─────────────────────────────────────────────────┐
│                                                 │
│   Stand 1    Stand 2    Stand 3    Stand 4     │
│   ┌────┐    ┌────┐    ┌────┐    ┌────┐        │
│   │ ▣  │    │ ▣  │    │ ▣  │    │ ▣  │        │
│   └────┘    └────┘    └────┘    └────┘        │
│      │         │         │         │           │
│   ┌──────────────────────────────────┐         │
│   │ ░░░░░░ MATERIAL PATH ROI ░░░░░░░ │         │
│   └──────────────────────────────────┘         │
│                                                 │
└─────────────────────────────────────────────────┘
```

#### CAM-3: Cooling Bed

| Attribute | Specification |
|-----------|---------------|
| **Camera ID** | `CAM-3` |
| **Name** | Cooling Bed |
| **Role** | TERTIARY — Production activity indicator |
| **Position** | Overhead or elevated side view of cooling bed |
| **Field of View** | Full cooling bed surface |
| **Key Detection** | New stock arrival, stock accumulation |
| **Environment** | Residual heat, better visibility than furnace area |
| **Mounting Height** | 5-6 meters (full bed coverage) |
| **Angle** | Overhead preferred, or high side angle |

**Region of Interest (ROI):**
```
┌─────────────────────────────────────────────────┐
│                                                 │
│   ┌─────────────────────────────────────────┐   │
│   │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │   │
│   │ ░░░░░░░░░ COOLING BED ROI ░░░░░░░░░░░░ │   │
│   │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │   │
│   │ ═══════════════════════════════════════ │   │
│   │ ═══════════════════════════════════════ │   │
│   │ ═══════════════════════════════════════ │   │
│   │ ═══════════════════════════════════════ │   │
│   └─────────────────────────────────────────┘   │
│         ↑                                       │
│   Stock arrival zone (entry detection)          │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 2. Camera Hardware Requirements

### 2.1 Camera Specifications

| Specification | Minimum | Recommended |
|---------------|---------|-------------|
| **Resolution** | 1080p (1920×1080) | 2K (2560×1440) |
| **Frame Rate** | 15 fps | 25-30 fps |
| **Sensor** | 1/2.8" CMOS | 1/2.5" CMOS or larger |
| **Low Light** | 0.01 lux (color) | 0.005 lux with IR |
| **Dynamic Range** | 100 dB WDR | 120+ dB WDR |
| **Lens** | Varifocal 2.8-12mm | Motorized zoom |
| **IP Rating** | IP66 | IP67 |
| **Operating Temp** | 0°C to 50°C | -20°C to 60°C |
| **Protocol** | ONVIF Profile S | ONVIF Profile S & T |
| **Compression** | H.264 | H.265 |
| **Connection** | Ethernet (RJ45) | PoE+ (802.3at) |

### 2.2 Special Considerations by Camera

| Camera | Special Requirements |
|--------|---------------------|
| **CAM-1 (Furnace)** | High temperature rating, protective housing, anti-glare coating for bright glow |
| **CAM-2 (Mill Stands)** | Vibration-resistant mount, fast shutter for motion, spark protection |
| **CAM-3 (Cooling Bed)** | Wide angle lens for full coverage, good contrast for metal detection |

### 2.3 Recommended Camera Models

| Budget | Model Examples | Notes |
|--------|----------------|-------|
| **Economy** | Hikvision DS-2CD2T47G2, Dahua IPC-HFW2831E | Good value, reliable |
| **Mid-range** | Axis P3245-V, Hanwha XNV-8080R | Better low-light, WDR |
| **Industrial** | FLIR A400/A700, Bosch DINION IP | Built for harsh environments |

---

## 3. Network & NVR Configuration

### 3.1 NVR Requirements

| Specification | Requirement |
|---------------|-------------|
| **Channels** | 4+ (3 cameras + 1 spare) |
| **Recording Resolution** | 4K capable |
| **Storage** | 4TB minimum (2 weeks @ 1080p continuous) |
| **RAID** | RAID 1 recommended for redundancy |
| **RTSP Output** | Required — main stream and sub-stream |
| **ONVIF Support** | Required — Profile S minimum |
| **Network Port** | Gigabit Ethernet |
| **Remote Access** | Web interface + mobile app |

### 3.2 Network Architecture

```
                    CAMERA NETWORK TOPOLOGY
    
    ┌─────────────────────────────────────────────────────┐
    │                   MILL NETWORK                       │
    ├─────────────────────────────────────────────────────┤
    │                                                     │
    │   ┌─────────┐   ┌─────────┐   ┌─────────┐         │
    │   │  CAM-1  │   │  CAM-2  │   │  CAM-3  │         │
    │   │ Furnace │   │  Stands │   │ Cooling │         │
    │   └────┬────┘   └────┬────┘   └────┬────┘         │
    │        │             │             │               │
    │        └──────────┬──┴─────────────┘               │
    │                   │                                │
    │              ┌────▼────┐                           │
    │              │  PoE    │                           │
    │              │ Switch  │                           │
    │              └────┬────┘                           │
    │                   │                                │
    │         ┌─────────┴─────────┐                      │
    │         │                   │                      │
    │    ┌────▼────┐        ┌────▼────┐                 │
    │    │   NVR   │        │   Pi    │                 │
    │    │         │───────→│  Edge   │                 │
    │    │ Storage │  RTSP  │ Process │                 │
    │    └─────────┘        └────┬────┘                 │
    │                            │                       │
    │                       ┌────▼────┐                  │
    │                       │   AIS   │                  │
    │                       │ Server  │                  │
    │                       └─────────┘                  │
    │                                                     │
    └─────────────────────────────────────────────────────┘
```

### 3.3 RTSP Stream Configuration

| Stream | Purpose | Settings |
|--------|---------|----------|
| **Main Stream** | Recording, archival | 1080p+, 15-25 fps, H.265, 4-8 Mbps |
| **Sub Stream** | CV processing | 720p, 10-15 fps, H.264, 1-2 Mbps |

**RTSP URL Format:**
```
Main Stream: rtsp://{username}:{password}@{nvr_ip}:{port}/cam/realmonitor?channel={1-3}&subtype=0
Sub Stream:  rtsp://{username}:{password}@{nvr_ip}:{port}/cam/realmonitor?channel={1-3}&subtype=1
```

**ONVIF Discovery:**
```
Device URL: http://{camera_ip}/onvif/device_service
Media URL:  http://{camera_ip}/onvif/media_service
```

---

## 4. Raspberry Pi Edge Processing

### 4.1 Hardware Configuration

| Component | Specification |
|-----------|---------------|
| **Model** | Raspberry Pi 4 Model B |
| **RAM** | 4GB minimum, 8GB recommended |
| **Storage** | 64GB+ microSD (Class 10 / A2) |
| **Power** | Official 5.1V 3A USB-C power supply |
| **Cooling** | Active cooling (fan + heatsink) required |
| **Enclosure** | Industrial enclosure with ventilation |
| **Network** | Gigabit Ethernet (not WiFi for reliability) |

### 4.2 Deployment Options

#### Option A: Single Pi (Recommended for MVP)

```
┌───────────────────────────────────────────────────────┐
│                  SINGLE PI DEPLOYMENT                  │
├───────────────────────────────────────────────────────┤
│                                                       │
│   CAM-1 ──┐                                          │
│           │      ┌──────────────┐                    │
│   CAM-2 ──┼─────→│ Raspberry Pi │─────→ AIS Server  │
│           │      │   (8GB RAM)  │                    │
│   CAM-3 ──┘      └──────────────┘                    │
│                                                       │
│   Pros: Simple setup, single point of management     │
│   Cons: Single point of failure, limited scalability │
│                                                       │
└───────────────────────────────────────────────────────┘
```

#### Option B: Distributed Pi (Future Scaling)

```
┌───────────────────────────────────────────────────────┐
│               DISTRIBUTED PI DEPLOYMENT               │
├───────────────────────────────────────────────────────┤
│                                                       │
│   CAM-1 ─────→ Pi-1 (Furnace) ───┐                   │
│                                   │                   │
│   CAM-2 ─────→ Pi-2 (Stands) ────┼───→ AIS Server   │
│                                   │                   │
│   CAM-3 ─────→ Pi-3 (Cooling) ───┘                   │
│                                                       │
│   Pros: Redundancy, parallel processing, near-camera │
│   Cons: More hardware, complex coordination          │
│                                                       │
└───────────────────────────────────────────────────────┘
```

**Recommendation:** Start with Option A (single Pi) for MVP-Plus. Scale to Option B if processing bottlenecks occur.

### 4.3 Software Stack

```yaml
operating_system: Raspberry Pi OS Lite (64-bit)
python_version: 3.11+

core_packages:
  - opencv-python: 4.8+      # Image processing
  - numpy: 1.24+             # Array operations
  - picamera2: latest        # If using Pi camera (not applicable here)
  
streaming:
  - ffmpeg: 6.0+             # RTSP stream handling
  - gstreamer: 1.22+         # Alternative streaming pipeline
  
networking:
  - requests: 2.31+          # API calls to AIS server
  - aiohttp: 3.8+            # Async HTTP client
  - websockets: 11.0+        # Real-time updates
  
storage:
  - sqlite3: built-in        # Local event buffer
  - pillow: 10.0+            # Image saving
  
monitoring:
  - psutil: 5.9+             # System monitoring
  - prometheus_client: 0.17+ # Metrics export (optional)
```

### 4.4 Processing Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│              EDGE PROCESSING PIPELINE                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RTSP Stream ──→ Frame Grab ──→ Preprocess ──→ Detect      │
│       │              │              │             │         │
│       │              │              │             │         │
│       ▼              ▼              ▼             ▼         │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐    │
│  │ ffmpeg  │   │ Decode  │   │ Resize  │   │   CV    │    │
│  │ connect │   │ H.264/5 │   │ to 640  │   │ Analyze │    │
│  │ to NVR  │   │ frames  │   │   ×480  │   │  ROI    │    │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘    │
│                                                  │          │
│                    ┌─────────────────────────────┘          │
│                    │                                        │
│                    ▼                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  STATE MACHINE                       │   │
│  │  ┌────────┐   ┌────────┐   ┌────────┐              │   │
│  │  │ CAM-1  │   │ CAM-2  │   │ CAM-3  │              │   │
│  │  │ Result │ + │ Result │ + │ Result │ → State      │   │
│  │  └────────┘   └────────┘   └────────┘              │   │
│  └─────────────────────────────────────────────────────┘   │
│                    │                                        │
│         ┌─────────┴──────────┐                             │
│         │                    │                             │
│         ▼                    ▼                             │
│  ┌─────────────┐     ┌─────────────┐                      │
│  │ Local Buffer│     │ Send to AIS │                      │
│  │  (SQLite)   │     │   Server    │                      │
│  └─────────────┘     └─────────────┘                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.5 Resource Allocation

| Resource | Allocation | Notes |
|----------|------------|-------|
| **CPU** | 3 cores for CV, 1 core for system | Pi 4 has 4 cores |
| **RAM** | 1GB per camera stream + 1GB buffer | 4GB total minimum |
| **Network** | ~6 Mbps inbound (3 sub-streams) | Gigabit headroom |
| **Storage** | 10GB for OS, 50GB for local buffer | 64GB card |
| **Temperature** | Keep below 70°C | Active cooling required |

---

## 5. Camera Configuration

### 5.1 Per-Camera Settings

```yaml
# Camera Configuration Template
cameras:
  - id: CAM-1
    name: Furnace Opening
    role: primary
    connection:
      type: rtsp
      url: "rtsp://admin:password@192.168.1.101:554/stream1"
      substream_url: "rtsp://admin:password@192.168.1.101:554/stream2"
      protocol: tcp  # tcp more reliable than udp
      timeout_seconds: 10
      reconnect_attempts: 3
      reconnect_delay_seconds: 5
    
    image_settings:
      resolution: [1920, 1080]  # Main stream
      process_resolution: [640, 480]  # Downscaled for CV
      fps: 15
      exposure: auto
      gain: auto
      wdr: enabled
      
    roi:
      furnace_door:
        x: 200
        y: 100
        width: 400
        height: 300
      extraction_path:
        x: 200
        y: 400
        width: 400
        height: 200
        
    detection:
      luminosity_threshold: 180  # 0-255, bright = hot stock
      motion_threshold: 25       # Pixel difference threshold
      min_area_pixels: 5000      # Minimum detected object size
      
  - id: CAM-2
    name: Mill Stands
    role: secondary
    connection:
      type: rtsp
      url: "rtsp://admin:password@192.168.1.102:554/stream1"
      substream_url: "rtsp://admin:password@192.168.1.102:554/stream2"
      protocol: tcp
      timeout_seconds: 10
      reconnect_attempts: 3
      reconnect_delay_seconds: 5
    
    image_settings:
      resolution: [1920, 1080]
      process_resolution: [640, 480]
      fps: 15
      exposure: auto
      gain: auto
      wdr: enabled
      
    roi:
      material_path:
        x: 100
        y: 200
        width: 800
        height: 200
        
    detection:
      luminosity_threshold: 160
      motion_threshold: 30
      min_area_pixels: 3000
      
  - id: CAM-3
    name: Cooling Bed
    role: tertiary
    connection:
      type: rtsp
      url: "rtsp://admin:password@192.168.1.103:554/stream1"
      substream_url: "rtsp://admin:password@192.168.1.103:554/stream2"
      protocol: tcp
      timeout_seconds: 10
      reconnect_attempts: 3
      reconnect_delay_seconds: 5
    
    image_settings:
      resolution: [1920, 1080]
      process_resolution: [640, 480]
      fps: 10  # Lower fps acceptable for cooling bed
      exposure: auto
      gain: auto
      wdr: enabled
      
    roi:
      entry_zone:
        x: 50
        y: 50
        width: 200
        height: 400
      bed_surface:
        x: 50
        y: 50
        width: 900
        height: 500
        
    detection:
      luminosity_threshold: 140  # Lower threshold, stock is cooling
      motion_threshold: 20
      min_area_pixels: 4000
```

### 5.2 ROI Calibration Process

```
ROI CALIBRATION STEPS:

1. CAPTURE REFERENCE FRAMES
   - Take 10 frames during active production
   - Take 10 frames during break
   - Note positions of key elements

2. DEFINE ROI BOUNDARIES
   - Mark the area where detection should occur
   - Exclude static elements (machinery, walls)
   - Include buffer zone around expected material path

3. TEST DETECTION
   - Run detection on reference frames
   - Adjust thresholds until:
     • All "hot stock present" frames detect correctly
     • All "no stock" frames show no detection

4. VALIDATE LIVE
   - Monitor for 1 shift with manual verification
   - Adjust ROI/thresholds if needed

5. DOCUMENT FINAL SETTINGS
   - Save calibration photos with ROI overlay
   - Record threshold values
   - Note any environmental factors
```

---

## 6. Installation & Setup

### 6.1 Physical Installation Checklist

```markdown
## Camera Installation Checklist

### Pre-Installation
- [ ] Survey mounting locations for each camera
- [ ] Verify power availability (PoE or local outlet)
- [ ] Verify network cable routing paths
- [ ] Check for environmental hazards (heat, water, dust)
- [ ] Confirm mounting hardware compatibility

### CAM-1: Furnace Opening
- [ ] Mount at 3-4m height, away from direct heat
- [ ] Install protective housing if needed
- [ ] Verify clear view of furnace door
- [ ] Verify clear view of extraction path
- [ ] Run Cat6 cable to network switch
- [ ] Test video feed quality

### CAM-2: Mill Stands
- [ ] Mount at 4-5m height with vibration dampening
- [ ] Position for side or angled overhead view
- [ ] Verify multiple stands visible in frame
- [ ] Install spark shield if needed
- [ ] Run Cat6 cable to network switch
- [ ] Test video feed quality

### CAM-3: Cooling Bed
- [ ] Mount at 5-6m height (overhead preferred)
- [ ] Position for full bed coverage
- [ ] Verify entry zone visible
- [ ] Run Cat6 cable to network switch
- [ ] Test video feed quality

### Network Setup
- [ ] Connect all cameras to PoE switch
- [ ] Connect NVR to switch
- [ ] Configure static IPs for cameras
- [ ] Configure NVR recording settings
- [ ] Test RTSP streams accessible
- [ ] Test ONVIF discovery

### Raspberry Pi Setup
- [ ] Install Raspberry Pi OS
- [ ] Connect to network
- [ ] Install required packages
- [ ] Configure camera connections
- [ ] Test frame capture from all cameras
- [ ] Configure auto-start on boot
```

### 6.2 Network Configuration

```yaml
# Recommended IP Scheme
network:
  subnet: 192.168.1.0/24
  gateway: 192.168.1.1
  
  devices:
    nvr:
      ip: 192.168.1.100
      hostname: ais-nvr
      
    cameras:
      cam1:
        ip: 192.168.1.101
        hostname: ais-cam-furnace
      cam2:
        ip: 192.168.1.102
        hostname: ais-cam-stands
      cam3:
        ip: 192.168.1.103
        hostname: ais-cam-cooling
        
    raspberry_pi:
      ip: 192.168.1.110
      hostname: ais-cv-edge
      
    ais_server:
      ip: 192.168.1.200
      hostname: ais-server

# Firewall Rules
firewall:
  allow:
    - from: ais-cv-edge
      to: [cam1, cam2, cam3]
      ports: [554, 80, 8080]  # RTSP, HTTP, ONVIF
      
    - from: ais-cv-edge
      to: ais-server
      ports: [443, 8443]  # HTTPS API
      
    - from: nvr
      to: [cam1, cam2, cam3]
      ports: [554, 80]
```

---

## 7. Maintenance & Monitoring

### 7.1 Health Checks

```yaml
health_checks:
  camera_connectivity:
    interval_seconds: 30
    timeout_seconds: 5
    action_on_failure: alert + retry
    
  stream_quality:
    check: frame_rate_actual >= frame_rate_expected * 0.8
    interval_seconds: 60
    action_on_failure: log + alert if persists > 5 minutes
    
  pi_resources:
    cpu_threshold_percent: 85
    memory_threshold_percent: 80
    temperature_threshold_celsius: 70
    disk_threshold_percent: 90
    interval_seconds: 60
    
  nvr_storage:
    threshold_percent: 80
    interval_seconds: 3600  # Hourly
    action_on_threshold: alert
```

### 7.2 Maintenance Schedule

| Task | Frequency | Responsibility |
|------|-----------|----------------|
| Clean camera lenses | Weekly | Maintenance team |
| Check cable connections | Monthly | IT/Maintenance |
| Verify ROI calibration | Monthly | CV system admin |
| Review detection accuracy | Weekly | Supervisor + System |
| Backup NVR footage | Daily (auto) | System |
| Update Pi software | Monthly | IT |
| Replace microSD card | Yearly | IT |

### 7.3 Troubleshooting Guide

| Symptom | Possible Cause | Resolution |
|---------|----------------|------------|
| No video from camera | Network issue, camera offline | Check cable, ping camera, restart camera |
| Low frame rate | Network congestion, NVR overload | Check bandwidth, reduce resolution |
| False detections | Lighting change, obstruction | Recalibrate ROI, adjust thresholds |
| Missed detections | Dirty lens, threshold too high | Clean lens, lower detection threshold |
| Pi overheating | Poor ventilation, high load | Improve cooling, check process load |
| RTSP timeout | Network instability | Switch to TCP, increase timeout |
| NVR full | Retention too long | Reduce retention period, add storage |

---

## 8. Security Considerations

### 8.1 Network Security

```yaml
security_measures:
  network:
    - Cameras on isolated VLAN (not accessible from general network)
    - No direct internet access for cameras/NVR
    - Firewall restricts traffic to necessary ports only
    
  authentication:
    - Change default passwords on all cameras
    - Use strong passwords (12+ characters)
    - Disable unused protocols (telnet, FTP)
    - RTSP authentication required
    
  encryption:
    - HTTPS for NVR web interface
    - Consider RTSP over TLS if supported
    - Encrypt Pi storage for validation photos
    
  access_control:
    - Limit NVR access to authorized personnel
    - Audit log for configuration changes
    - Disable remote access if not needed
```

### 8.2 Physical Security

- Cameras mounted out of easy reach
- Tamper-resistant enclosures
- Cable conduits to prevent cutting
- Pi enclosure locked

---

## 9. Dependencies

| Dependency | Module | Required For |
|------------|--------|--------------|
| Camera feeds | This module | Video input |
| NVR | This module | Recording, RTSP |
| Network infrastructure | IT | Connectivity |
| Power (PoE) | Facilities | Camera power |
| CV-CORE | Detection Logic | Processing rules |
| CV-INTEGRATION | ERP Connection | Data export |

---

## 10. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Camera uptime** | ≥99% per shift | Monitoring system |
| **Stream quality** | ≥90% of expected frame rate | Frame rate logging |
| **Pi processing latency** | <500ms per frame | Performance metrics |
| **Network reliability** | <1% packet loss | Network monitoring |
| **ROI accuracy** | Detection in correct zones | Manual verification |
| **Storage availability** | ≥2 weeks retention | NVR capacity |

---

*This specification is part of the AIS Production CV module suite.*
*Related specs: CV-CORE, CV-INTEGRATION, CV-VALIDATION*
