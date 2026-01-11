# CV-CORE: Detection Logic Specification

**Module:** CV-CORE  
**Version:** 1.0  
**Date:** 2026-01-10  
**Author:** Adityajain (via BMad Master)  
**Status:** Draft — Planning Phase

---

## Executive Summary

This specification defines the core detection logic for the AIS Production CV system. The system performs **binary state detection** (Running vs Break/Downtime) by analyzing video feeds from three strategically positioned cameras in the rolling mill.

### Key Insight

> "When hot stock moves in the mill from all three cameras, it is said to be running. When the stock is no longer being pulled out of the furnace, it is a break."
> — Adityajain, Owner

---

## 1. Production States

### 1.1 State Definitions

| State | Code | Definition | Visual Indicators |
|-------|------|------------|-------------------|
| **RUNNING** | `RUN` | Hot stock is actively moving through the mill | Glowing material visible, motion detected across cameras |
| **BREAK** | `BRK` | No stock being pulled from furnace; production paused | No new material from furnace, cooling bed may still have residual stock |
| **UNKNOWN** | `UNK` | System cannot determine state (camera issue, obstruction) | Feed unavailable, confidence below threshold |

### 1.2 State Hierarchy

```
PRIMARY INDICATOR: Furnace Opening Camera (CAM-1)
├── Stock being pulled → RUNNING
└── No stock being pulled → Check duration
    ├── < 2 minutes → RUNNING (normal gap between pulls)
    └── ≥ 2 minutes → BREAK

SECONDARY CONFIRMATION: Mill Stands Camera (CAM-2)
├── Hot material moving → Confirms RUNNING
└── No movement + CAM-1 break → Confirms BREAK

TERTIARY INDICATOR: Cooling Bed Camera (CAM-3)
├── New stock arriving → Production recently active
└── Only cooling stock → Does not determine state alone
```

### 1.3 State Transitions

```
┌─────────────────────────────────────────────────────────────┐
│                    STATE MACHINE                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│    ┌───────┐         Stock pulled         ┌───────┐        │
│    │       │ ───────────────────────────→ │       │        │
│    │ BREAK │                              │RUNNING│        │
│    │       │ ←─────────────────────────── │       │        │
│    └───────┘    No pull for ≥2 min        └───────┘        │
│        ↑                                      ↑            │
│        │                                      │            │
│        │    Camera issue / low confidence     │            │
│        └──────────────┬───────────────────────┘            │
│                       │                                    │
│                       ▼                                    │
│                  ┌─────────┐                               │
│                  │ UNKNOWN │                               │
│                  └─────────┘                               │
│                       │                                    │
│                       │ Feed restored / confidence OK      │
│                       ▼                                    │
│              Return to last known state                    │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Detection Logic

### 2.1 Primary Detection: Hot Stock Recognition

The system detects "hot stock" through visual characteristics unique to heated steel:

| Characteristic | Detection Method | Confidence Weight |
|----------------|------------------|-------------------|
| **Glow/Luminosity** | Pixel brightness in orange-red spectrum (RGB analysis) | 40% |
| **Motion** | Frame differencing to detect movement | 30% |
| **Shape** | Elongated form consistent with billets/bars | 20% |
| **Position** | Expected location within camera frame (ROI) | 10% |

### 2.2 Camera-Specific Detection Rules

#### CAM-1: Furnace Opening (Primary Authority)

```yaml
camera_id: CAM-1
name: Furnace Opening
role: PRIMARY - Determines RUNNING/BREAK state
detection_rules:
  - type: hot_stock_emergence
    description: Detect when glowing stock is pulled from furnace door
    triggers_state: RUNNING
    
  - type: no_emergence_timeout
    description: No stock detected for threshold duration
    threshold_seconds: 120  # 2 minutes
    triggers_state: BREAK
    
  - type: furnace_door_state
    description: Optional - detect if furnace door is open/closed
    confidence_boost: true  # Adds confidence, not primary trigger
```

#### CAM-2: Mill Stands (Secondary Confirmation)

```yaml
camera_id: CAM-2
name: Mill Stands
role: SECONDARY - Confirms active production
detection_rules:
  - type: hot_stock_transit
    description: Detect glowing material moving through stand series
    confirms_state: RUNNING
    
  - type: no_transit
    description: No hot material in transit
    confirms_state: BREAK (only if CAM-1 also indicates break)
    
  - type: stand_activity
    description: Visual movement/vibration of stands
    confidence_boost: true
```

#### CAM-3: Cooling Bed (Tertiary Indicator)

```yaml
camera_id: CAM-3
name: Cooling Bed
role: TERTIARY - Production activity indicator
detection_rules:
  - type: new_stock_arrival
    description: Fresh hot stock being stacked on cooling bed
    indicates: Recent production activity
    
  - type: stock_accumulation
    description: Track stock count on cooling bed
    future_use: Piece counting (Phase 2)
    
  - type: bed_empty
    description: Cooling bed cleared
    indicates: End of production run
```

### 2.3 Confidence Scoring

Each detection event includes a confidence score:

```
CONFIDENCE CALCULATION:

Base Score (per camera):
├── CAM-1 detection weight: 50%
├── CAM-2 detection weight: 30%
└── CAM-3 detection weight: 20%

Adjustments:
├── All 3 cameras agree: +15%
├── 2 of 3 cameras agree: +5%
├── Only 1 camera detecting: -10%
├── Camera feed quality issues: -5% per affected camera
└── Lighting conditions (night/day): ±5%

Final Score Range:
├── ≥ 85%: HIGH confidence — state change recorded immediately
├── 70-84%: MEDIUM confidence — state change recorded with flag
├── 50-69%: LOW confidence — state held, alert to supervisor
└── < 50%: UNKNOWN state — manual verification required
```

---

## 3. Timing & Thresholds

### 3.1 Configurable Thresholds

| Parameter | Default Value | Range | Description |
|-----------|---------------|-------|-------------|
| `break_threshold_seconds` | 120 | 60-300 | Time without furnace pull to trigger BREAK |
| `min_run_duration_seconds` | 30 | 10-60 | Minimum RUNNING duration before recording |
| `confidence_threshold_high` | 85 | 80-95 | Threshold for immediate state change |
| `confidence_threshold_low` | 50 | 40-60 | Below this = UNKNOWN state |
| `sample_rate_fps` | 1 | 0.5-5 | Frames analyzed per second |
| `photo_sample_interval_seconds` | 60 | 30-120 | Interval for validation photo capture |

### 3.2 Debouncing Logic

To prevent rapid state flickering:

```
STATE CHANGE RULES:

1. RUNNING → BREAK transition:
   - Requires: No furnace activity for `break_threshold_seconds`
   - AND: CAM-2 confirms no transit for at least 60 seconds
   - Debounce: State change locks for 30 seconds after transition

2. BREAK → RUNNING transition:
   - Requires: Hot stock detected at CAM-1 (furnace pull)
   - Immediate transition (no debounce on resumption)
   - Confirmation from CAM-2 within 30 seconds expected

3. ANY → UNKNOWN transition:
   - Requires: Confidence drops below threshold for 60 seconds
   - System continues attempting detection
   - Alert generated for operator attention

4. UNKNOWN → ANY transition:
   - Requires: Confidence returns above threshold
   - System returns to last known state if < 5 minutes in UNKNOWN
   - System requires fresh detection if > 5 minutes in UNKNOWN
```

---

## 4. Event Logging

### 4.1 State Change Events

Every state change generates an event record:

```typescript
interface ProductionStateEvent {
  event_id: string;           // UUID
  timestamp: Date;            // ISO 8601
  previous_state: 'RUN' | 'BRK' | 'UNK';
  new_state: 'RUN' | 'BRK' | 'UNK';
  confidence_score: number;   // 0-100
  trigger_camera: 'CAM-1' | 'CAM-2' | 'CAM-3';
  camera_states: {
    cam1: CameraDetection;
    cam2: CameraDetection;
    cam3: CameraDetection;
  };
  sample_photos: string[];    // URLs to captured frames
  duration_in_previous_state_seconds: number;
  shift_id: string;
  tenant_id: string;
}

interface CameraDetection {
  camera_id: string;
  detecting_activity: boolean;
  confidence: number;
  detection_details: {
    luminosity_detected: boolean;
    motion_detected: boolean;
    shape_detected: boolean;
    in_roi: boolean;
  };
  frame_url?: string;
}
```

### 4.2 Continuous Logging

During both RUNNING and BREAK states, the system logs:

```typescript
interface ProductionStateLog {
  log_id: string;
  timestamp: Date;
  current_state: 'RUN' | 'BRK' | 'UNK';
  state_start_time: Date;
  duration_seconds: number;
  confidence_score: number;
  cameras_online: number;     // 0-3
  sample_frame_captured: boolean;
  shift_id: string;
}

// Logged every: 60 seconds during RUNNING, 120 seconds during BREAK
```

---

## 5. Validation Photo Sampling

### 5.1 Photo Capture Rules

For MVP-Plus manual validation:

```yaml
photo_sampling:
  purpose: Manual verification of CV accuracy
  
  capture_rules:
    - trigger: state_change
      description: Capture 3 photos at every state transition
      timing: [0s, +5s, +10s] after transition
      
    - trigger: periodic_during_run
      description: Sample photos during RUNNING state
      interval_seconds: 300  # Every 5 minutes
      target_per_run: 5-7 photos minimum
      
    - trigger: periodic_during_break
      description: Sample photos during BREAK state
      interval_seconds: 180  # Every 3 minutes
      target_per_break: 5-7 photos minimum
      
    - trigger: confidence_drop
      description: Extra photos when confidence fluctuates
      threshold: confidence drops > 10% within 30 seconds
      
  storage:
    location: "{output_folder}/cv-validation/{date}/{shift_id}/"
    naming: "{timestamp}_{camera_id}_{state}_{confidence}.jpg"
    retention_days: 30
    
  metadata_captured:
    - timestamp
    - camera_id
    - detected_state
    - confidence_score
    - detection_details
```

### 5.2 Validation Workflow

```
MANUAL VALIDATION PROCESS (Phase 1):

1. CV System captures 5-7 photos per break/run period
2. Photos stored with metadata (state, confidence, timestamp)
3. Supervisor/Manager reviews photos in AIS dashboard
4. For each photo, reviewer confirms: "Correct" or "Incorrect"
5. System calculates agreement rate:
   
   Agreement Rate = (Correct detections / Total photos reviewed) × 100%
   
6. Target: ≥95% agreement before CV becomes primary data source
7. Disagreements logged for algorithm improvement
```

---

## 6. Edge Cases & Handling

### 6.1 Known Edge Cases

| Scenario | Detection Challenge | Handling |
|----------|---------------------|----------|
| **Furnace reheating** | No pulls, but not a break | Track furnace door; if closed + internal activity, maintain context |
| **Roll change** | Brief stop at mill stands | CAM-1 is authority; CAM-2 pause doesn't trigger break |
| **Night lighting** | Visibility changes | Hot stock glow actually MORE visible at night; adjust thresholds |
| **Steam/smoke obstruction** | Temporary visibility loss | Short obstruction (<30s) maintains state; longer triggers confidence drop |
| **Power outage** | All cameras offline | UNKNOWN state; log gap; manual entry required for period |
| **Single camera failure** | Partial visibility | Reduce confidence; continue with remaining cameras; alert maintenance |
| **End of shift** | Natural production stop | Normal BREAK state; shift handover logged separately |

### 6.2 Graceful Degradation

```
DEGRADATION HIERARCHY:

3 cameras online → Full confidence, normal operation
2 cameras online → Reduced confidence (-15%), alert generated
1 camera online  → Minimum operation, CAM-1 required for state changes
0 cameras online → UNKNOWN state, manual logging required

If CAM-1 (Furnace) offline:
├── CAM-2 + CAM-3 can infer state with reduced confidence
├── Alert: "Primary camera offline — accuracy may be affected"
└── Manual confirmation required for state changes

If CAM-2 (Mill Stands) offline:
├── CAM-1 + CAM-3 continue operation
├── Confidence reduced by 15%
└── No alerts unless duration > 1 hour

If CAM-3 (Cooling Bed) offline:
├── CAM-1 + CAM-2 continue operation
├── Confidence reduced by 10%
├── Piece counting (Phase 2) unavailable
└── No alerts unless duration > 2 hours
```

---

## 7. Integration Points

This module provides data to:

| Consumer | Data Provided | Frequency |
|----------|---------------|-----------|
| **CV-INTEGRATION** | State events, confidence scores | Real-time |
| **Supervisor Dashboard** | Current state, shift timeline | Real-time |
| **Owner Dashboard** | Runtime/break summary | Aggregated |
| **Shift Reports** | Total runtime, break count, durations | End of shift |
| **Validation UI** | Sample photos for review | On demand |

---

## 8. Future Enhancements (Phase 2)

### 8.1 Piece Counting

```yaml
phase_2_capability: Piece Counting
cameras_involved: [CAM-1, CAM-3]
description: |
  Count individual pieces/billets pulled from furnace and 
  stacked on cooling bed. Cross-validate counts between cameras.
  
validation_against: Hydra production weights (next-day reconciliation)

calculation: |
  CV Piece Count × Expected Weight Per Piece ≈ Hydra Total Weight
  Variance threshold: ±5% acceptable
  
benefits:
  - Precise throughput measurement
  - Scale loss calculation
  - Quality/reject tracking
```

### 8.2 Advanced Analytics

- Cycle time analysis (time between pulls)
- Break pattern recognition (scheduled vs unscheduled)
- Predictive maintenance triggers (unusual patterns)
- Shift performance comparisons

---

## 9. Dependencies

| Dependency | Module | Required For |
|------------|--------|--------------|
| Camera feeds | CV-CAMERAS | Video input |
| RTSP streaming | CV-CAMERAS | Feed access |
| Raspberry Pi | CV-CAMERAS | Edge processing |
| State event API | CV-INTEGRATION | Data export |
| Photo storage | CV-INTEGRATION | Validation samples |
| Supervisor UI | AIS Web App | Photo review |

---

## 10. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| **State detection accuracy** | ≥95% | Photo sampling validation |
| **State change latency** | <10 seconds | Time from actual change to system detection |
| **Uptime** | ≥99% during shifts | Camera + processing availability |
| **False positive rate** | <3% | Incorrect RUNNING detections |
| **False negative rate** | <2% | Missed RUNNING detections |
| **Photo sample coverage** | 5-7 per period | Validation completeness |

---

*This specification is part of the AIS Production CV module suite.*
*Related specs: CV-CAMERAS, CV-INTEGRATION, CV-VALIDATION*
