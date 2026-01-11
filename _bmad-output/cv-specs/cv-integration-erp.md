# CV-INTEGRATION: ERP Connection Specification

**Module:** CV-INTEGRATION  
**Version:** 1.0  
**Date:** 2026-01-10  
**Author:** Adityajain (via BMad Master)  
**Status:** Draft — Planning Phase

---

## Executive Summary

This specification defines how the Production CV system integrates with the AIS ERP. The CV edge processor (Raspberry Pi) communicates production state events to the AIS server, which aggregates data for dashboards, reports, and the validation workflow.

### Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INTEGRATION OVERVIEW                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐                     ┌──────────────────────────────┐ │
│   │  Raspberry   │                     │         AIS SERVER            │ │
│   │     Pi       │                     │                              │ │
│   │              │    REST API         │  ┌───────────────────────┐   │ │
│   │  CV-CORE     │──────────────────→ │  │   API Gateway          │   │ │
│   │  Detection   │    State Events     │  │   /api/v1/cv/*         │   │ │
│   │              │                     │  └───────────┬───────────┘   │ │
│   │              │    WebSocket        │              │               │ │
│   │              │←─────────────────── │              ▼               │ │
│   │              │    Ack + Config     │  ┌───────────────────────┐   │ │
│   └──────────────┘                     │  │   CV Service           │   │ │
│                                        │  │   - Event processing   │   │ │
│                                        │  │   - State aggregation  │   │ │
│                                        │  │   - Photo storage      │   │ │
│                                        │  └───────────┬───────────┘   │ │
│                                        │              │               │ │
│                                        │              ▼               │ │
│                                        │  ┌───────────────────────┐   │ │
│                                        │  │      Database          │   │ │
│                                        │  │   production_states    │   │ │
│                                        │  │   cv_events            │   │ │
│                                        │  │   validation_photos    │   │ │
│                                        │  └───────────────────────┘   │ │
│                                        │                              │ │
│                                        └──────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Communication Protocols

### 1.1 Protocol Selection

| Direction | Protocol | Use Case |
|-----------|----------|----------|
| **Pi → Server** | REST API (HTTPS) | State events, photo uploads, heartbeats |
| **Server → Pi** | WebSocket | Configuration updates, acknowledgments, commands |
| **Fallback** | Offline queue + batch sync | When connectivity lost |

### 1.2 Why This Architecture

1. **REST for Events:** Stateless, reliable, works with standard retry logic
2. **WebSocket for Commands:** Real-time config pushes, no polling overhead
3. **Offline Queue:** Factory connectivity is unreliable; Pi must operate autonomously

---

## 2. REST API Specification

### 2.1 Base URL

```
Production: https://ais.aadinathindustries.com/api/v1/cv
Development: http://localhost:3000/api/v1/cv
```

### 2.2 Authentication

```yaml
authentication:
  method: API Key + Device Token
  headers:
    X-API-Key: "{tenant_api_key}"
    X-Device-ID: "{device_uuid}"
    X-Device-Token: "{jwt_device_token}"
  token_refresh:
    endpoint: POST /api/v1/cv/auth/refresh
    frequency: Every 24 hours
```

**Device Registration Flow:**
```
1. Pi boots with pre-configured API key
2. POST /api/v1/cv/auth/register with device info
3. Server returns JWT device token
4. Token used for all subsequent requests
5. Token refreshed daily
```

### 2.3 API Endpoints

#### 2.3.1 State Events

**POST `/events`**

Submit a production state change event.

```typescript
// Request
POST /api/v1/cv/events
Content-Type: application/json

{
  "event_id": "uuid-v4",
  "timestamp": "2026-01-10T14:32:15.000Z",
  "event_type": "STATE_CHANGE",
  "previous_state": "RUN",
  "new_state": "BRK",
  "confidence_score": 92,
  "trigger_camera": "CAM-1",
  "camera_states": {
    "CAM-1": {
      "detecting_activity": false,
      "confidence": 95,
      "detection_details": {
        "luminosity_detected": false,
        "motion_detected": false,
        "shape_detected": false,
        "in_roi": true
      }
    },
    "CAM-2": {
      "detecting_activity": false,
      "confidence": 88,
      "detection_details": {
        "luminosity_detected": false,
        "motion_detected": false,
        "shape_detected": false,
        "in_roi": true
      }
    },
    "CAM-3": {
      "detecting_activity": true,
      "confidence": 72,
      "detection_details": {
        "luminosity_detected": true,
        "motion_detected": false,
        "shape_detected": true,
        "in_roi": true
      }
    }
  },
  "duration_in_previous_state_seconds": 1842,
  "shift_id": "shift-uuid",
  "photos_pending": 3
}

// Response: 201 Created
{
  "received": true,
  "event_id": "uuid-v4",
  "server_timestamp": "2026-01-10T14:32:15.123Z",
  "photo_upload_urls": [
    "https://storage.ais.../cv/photos/2026-01-10/shift-uuid/photo1.jpg?token=...",
    "https://storage.ais.../cv/photos/2026-01-10/shift-uuid/photo2.jpg?token=...",
    "https://storage.ais.../cv/photos/2026-01-10/shift-uuid/photo3.jpg?token=..."
  ]
}
```

#### 2.3.2 Photo Upload

**PUT `{photo_upload_url}`**

Upload validation photo to pre-signed URL.

```typescript
// Request
PUT {photo_upload_url from events response}
Content-Type: image/jpeg
Content-Length: {file_size}

{binary image data}

// Response: 200 OK
{
  "uploaded": true,
  "photo_id": "photo-uuid",
  "size_bytes": 245678
}
```

#### 2.3.3 Heartbeat

**POST `/heartbeat`**

Pi health check, sent every 60 seconds.

```typescript
// Request
POST /api/v1/cv/heartbeat
Content-Type: application/json

{
  "device_id": "device-uuid",
  "timestamp": "2026-01-10T14:33:00.000Z",
  "current_state": "BRK",
  "state_since": "2026-01-10T14:32:15.000Z",
  "cameras_online": 3,
  "camera_status": {
    "CAM-1": { "online": true, "fps": 14.8, "last_frame": "2026-01-10T14:32:59.000Z" },
    "CAM-2": { "online": true, "fps": 15.1, "last_frame": "2026-01-10T14:32:59.000Z" },
    "CAM-3": { "online": true, "fps": 9.8, "last_frame": "2026-01-10T14:32:58.000Z" }
  },
  "system_metrics": {
    "cpu_percent": 62,
    "memory_percent": 71,
    "temperature_celsius": 58,
    "disk_percent": 23,
    "uptime_seconds": 345600
  },
  "queue_depth": 0,
  "last_sync": "2026-01-10T14:32:15.000Z"
}

// Response: 200 OK
{
  "ack": true,
  "server_time": "2026-01-10T14:33:00.234Z",
  "config_version": "2026-01-10-001",
  "commands": []
}
```

#### 2.3.4 Batch Sync (Offline Recovery)

**POST `/events/batch`**

Submit multiple queued events after connectivity restored.

```typescript
// Request
POST /api/v1/cv/events/batch
Content-Type: application/json

{
  "batch_id": "batch-uuid",
  "events": [
    { /* event 1 */ },
    { /* event 2 */ },
    { /* event 3 */ }
  ],
  "photos_pending_count": 15
}

// Response: 200 OK
{
  "received_count": 3,
  "accepted": ["event-1-uuid", "event-2-uuid", "event-3-uuid"],
  "rejected": [],
  "photo_upload_urls": {
    "event-1-uuid": ["url1", "url2", "url3"],
    "event-2-uuid": ["url4", "url5"],
    "event-3-uuid": ["url6", "url7", "url8"]
  }
}
```

#### 2.3.5 Configuration Fetch

**GET `/config`**

Fetch current CV configuration from server.

```typescript
// Request
GET /api/v1/cv/config?device_id={device_uuid}

// Response: 200 OK
{
  "config_version": "2026-01-10-001",
  "detection": {
    "break_threshold_seconds": 120,
    "min_run_duration_seconds": 30,
    "confidence_threshold_high": 85,
    "confidence_threshold_low": 50,
    "sample_rate_fps": 1
  },
  "cameras": {
    "CAM-1": {
      "luminosity_threshold": 180,
      "motion_threshold": 25,
      "roi": { /* ROI config */ }
    },
    "CAM-2": { /* ... */ },
    "CAM-3": { /* ... */ }
  },
  "photo_sampling": {
    "interval_seconds": 60,
    "per_state_change": 3,
    "min_per_period": 5,
    "max_per_period": 10
  },
  "reporting": {
    "heartbeat_interval_seconds": 60,
    "event_retry_max": 5,
    "event_retry_delay_seconds": 30
  }
}
```

---

## 3. WebSocket Connection

### 3.1 Connection Setup

```typescript
// WebSocket URL
wss://ais.aadinathindustries.com/api/v1/cv/ws?device_id={device_uuid}&token={jwt}

// Connection established
{
  "type": "CONNECTED",
  "session_id": "ws-session-uuid",
  "server_time": "2026-01-10T14:32:00.000Z"
}
```

### 3.2 Message Types

#### Server → Pi Messages

```typescript
// Configuration Update
{
  "type": "CONFIG_UPDATE",
  "config_version": "2026-01-10-002",
  "changes": {
    "detection.break_threshold_seconds": 150
  }
}

// Command: Capture Photo
{
  "type": "COMMAND",
  "command": "CAPTURE_PHOTO",
  "camera_id": "CAM-1",
  "reason": "Manual validation request"
}

// Command: Restart Detection
{
  "type": "COMMAND",
  "command": "RESTART_DETECTION"
}

// Acknowledgment
{
  "type": "EVENT_ACK",
  "event_id": "event-uuid",
  "stored": true
}
```

#### Pi → Server Messages

```typescript
// State Update (real-time)
{
  "type": "STATE_UPDATE",
  "current_state": "RUN",
  "confidence": 91,
  "timestamp": "2026-01-10T14:35:00.000Z"
}

// Command Response
{
  "type": "COMMAND_RESPONSE",
  "command": "CAPTURE_PHOTO",
  "success": true,
  "photo_id": "photo-uuid"
}

// Ping (keepalive)
{
  "type": "PING",
  "timestamp": "2026-01-10T14:35:30.000Z"
}
```

### 3.3 Connection Management

```yaml
websocket:
  reconnect:
    initial_delay_ms: 1000
    max_delay_ms: 30000
    backoff_multiplier: 2
    max_retries: unlimited
    
  keepalive:
    ping_interval_seconds: 30
    pong_timeout_seconds: 10
    
  fallback:
    if_disconnected_seconds: 60
    action: Switch to REST-only mode
```

---

## 4. Data Models

### 4.1 Database Schema

```sql
-- Production state events from CV system
CREATE TABLE cv_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  device_id UUID NOT NULL,
  event_id UUID UNIQUE NOT NULL,  -- Client-generated for idempotency
  event_type VARCHAR(50) NOT NULL,
  previous_state VARCHAR(10),
  new_state VARCHAR(10) NOT NULL,
  confidence_score INTEGER NOT NULL,
  trigger_camera VARCHAR(10),
  camera_states JSONB NOT NULL,
  duration_previous_seconds INTEGER,
  shift_id UUID REFERENCES shifts(id),
  client_timestamp TIMESTAMPTZ NOT NULL,
  server_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_cv_events_tenant_shift (tenant_id, shift_id),
  INDEX idx_cv_events_timestamp (client_timestamp)
);

-- Aggregated production state periods
CREATE TABLE cv_production_periods (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  shift_id UUID NOT NULL REFERENCES shifts(id),
  state VARCHAR(10) NOT NULL,  -- RUN, BRK, UNK
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ,
  duration_seconds INTEGER,
  avg_confidence NUMERIC(5,2),
  validation_status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING, VALIDATED, DISPUTED
  validated_by UUID REFERENCES users(id),
  validated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_cv_periods_shift (shift_id),
  INDEX idx_cv_periods_validation (validation_status)
);

-- Validation photos
CREATE TABLE cv_validation_photos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  event_id UUID REFERENCES cv_events(id),
  period_id UUID REFERENCES cv_production_periods(id),
  camera_id VARCHAR(10) NOT NULL,
  detected_state VARCHAR(10) NOT NULL,
  confidence_score INTEGER NOT NULL,
  photo_url TEXT NOT NULL,
  thumbnail_url TEXT,
  captured_at TIMESTAMPTZ NOT NULL,
  validation_result VARCHAR(20),  -- NULL, CORRECT, INCORRECT
  validated_by UUID REFERENCES users(id),
  validated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_cv_photos_period (period_id),
  INDEX idx_cv_photos_validation (validation_result)
);

-- Device health logs
CREATE TABLE cv_device_health (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  device_id UUID NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  cameras_online INTEGER NOT NULL,
  camera_status JSONB NOT NULL,
  cpu_percent NUMERIC(5,2),
  memory_percent NUMERIC(5,2),
  temperature_celsius NUMERIC(5,2),
  disk_percent NUMERIC(5,2),
  queue_depth INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  INDEX idx_cv_health_device (device_id, timestamp)
);
```

### 4.2 TypeScript Interfaces

```typescript
// Shared types between Pi and Server
interface CVEvent {
  event_id: string;
  timestamp: Date;
  event_type: 'STATE_CHANGE' | 'CONFIDENCE_DROP' | 'CAMERA_OFFLINE' | 'CAMERA_ONLINE';
  previous_state?: ProductionState;
  new_state: ProductionState;
  confidence_score: number;
  trigger_camera?: CameraId;
  camera_states: Record<CameraId, CameraDetection>;
  duration_in_previous_state_seconds?: number;
  shift_id: string;
  photos_pending: number;
}

type ProductionState = 'RUN' | 'BRK' | 'UNK';
type CameraId = 'CAM-1' | 'CAM-2' | 'CAM-3';

interface CameraDetection {
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

interface ProductionPeriod {
  id: string;
  shift_id: string;
  state: ProductionState;
  start_time: Date;
  end_time?: Date;
  duration_seconds?: number;
  avg_confidence: number;
  validation_status: 'PENDING' | 'VALIDATED' | 'DISPUTED';
  photo_count: number;
}

interface ValidationPhoto {
  id: string;
  period_id: string;
  camera_id: CameraId;
  detected_state: ProductionState;
  confidence_score: number;
  photo_url: string;
  thumbnail_url?: string;
  captured_at: Date;
  validation_result?: 'CORRECT' | 'INCORRECT';
  validated_by?: string;
  validated_at?: Date;
}
```

---

## 5. Dashboard Integration

### 5.1 Supervisor Dashboard

**Real-time Production Status Card:**

```
┌─────────────────────────────────────────────────────────────────┐
│ 🔥 PRODUCTION STATUS                            Last: 2 sec ago │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌───────────────────────────────────────────────────────┐    │
│   │                    🟢 RUNNING                          │    │
│   │                 Confidence: 94%                       │    │
│   │                                                       │    │
│   │   Running since: 14:32:15 (32 min 45 sec)            │    │
│   └───────────────────────────────────────────────────────┘    │
│                                                                 │
│   TODAY'S SUMMARY:                                              │
│   ├─ Total Runtime: 5h 42m                                     │
│   ├─ Total Breaks: 1h 18m                                      │
│   ├─ Break Count: 4                                            │
│   └─ Utilization: 81%                                          │
│                                                                 │
│   CAMERAS:                                                      │
│   ├─ CAM-1 (Furnace): 🟢 Online • 14.9 fps                    │
│   ├─ CAM-2 (Stands):  🟢 Online • 15.1 fps                    │
│   └─ CAM-3 (Cooling): 🟢 Online • 9.8 fps                     │
│                                                                 │
│   [View Timeline]  [View Photos]                               │
└─────────────────────────────────────────────────────────────────┘
```

**API Endpoint for Supervisor Dashboard:**

```typescript
// GET /api/v1/cv/dashboard/supervisor
{
  "current_state": {
    "state": "RUN",
    "confidence": 94,
    "since": "2026-01-10T14:32:15.000Z",
    "duration_seconds": 1965
  },
  "today_summary": {
    "total_runtime_seconds": 20520,
    "total_break_seconds": 4680,
    "break_count": 4,
    "utilization_percent": 81
  },
  "cameras": {
    "CAM-1": { "online": true, "fps": 14.9, "last_update": "..." },
    "CAM-2": { "online": true, "fps": 15.1, "last_update": "..." },
    "CAM-3": { "online": true, "fps": 9.8, "last_update": "..." }
  },
  "shift_id": "shift-uuid",
  "last_update": "2026-01-10T15:05:00.000Z"
}
```

### 5.2 Owner Dashboard

**Production Efficiency Widget:**

```
┌─────────────────────────────────────────────────────────────────┐
│ 📊 PRODUCTION EFFICIENCY                        Yesterday       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   SHIFT 1 (06:00 - 14:00)                                      │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ █████████████████████████████░░░░░░░░░░│ 78%          │    │
│   └───────────────────────────────────────────────────────┘    │
│   Runtime: 6h 14m │ Breaks: 1h 46m │ Breaks: 5                 │
│                                                                 │
│   SHIFT 2 (14:00 - 22:00)                                      │
│   ┌───────────────────────────────────────────────────────┐    │
│   │ █████████████████████████████████████░░│ 85%          │    │
│   └───────────────────────────────────────────────────────┘    │
│   Runtime: 6h 48m │ Breaks: 1h 12m │ Breaks: 3                 │
│                                                                 │
│   📈 Trend: +4% vs last week                                   │
│                                                                 │
│   [View Details]  [Compare Shifts]                             │
└─────────────────────────────────────────────────────────────────┘
```

**API Endpoint for Owner Dashboard:**

```typescript
// GET /api/v1/cv/dashboard/owner?date=2026-01-09
{
  "date": "2026-01-09",
  "shifts": [
    {
      "shift_id": "shift-1-uuid",
      "shift_number": 1,
      "start_time": "06:00",
      "end_time": "14:00",
      "runtime_seconds": 22440,
      "break_seconds": 6360,
      "break_count": 5,
      "utilization_percent": 78,
      "validation_status": "VALIDATED",
      "confidence_avg": 91
    },
    {
      "shift_id": "shift-2-uuid",
      "shift_number": 2,
      "start_time": "14:00",
      "end_time": "22:00",
      "runtime_seconds": 24480,
      "break_seconds": 4320,
      "break_count": 3,
      "utilization_percent": 85,
      "validation_status": "PENDING",
      "confidence_avg": 93
    }
  ],
  "weekly_trend": {
    "current_avg_utilization": 82,
    "previous_avg_utilization": 78,
    "change_percent": 4
  }
}
```

### 5.3 Real-time Updates (WebSocket to Dashboard)

```typescript
// Dashboard WebSocket subscription
ws://ais.aadinathindustries.com/api/v1/ws?topics=cv.state,cv.summary

// State change message
{
  "topic": "cv.state",
  "data": {
    "state": "BRK",
    "confidence": 89,
    "since": "2026-01-10T15:10:00.000Z",
    "trigger_camera": "CAM-1"
  }
}

// Summary update message (every 5 minutes)
{
  "topic": "cv.summary",
  "data": {
    "runtime_today_seconds": 21600,
    "break_today_seconds": 5400,
    "utilization_percent": 80
  }
}
```

---

## 6. Shift Report Integration

### 6.1 Report Data Aggregation

CV data is aggregated into shift reports:

```typescript
interface CVShiftReportSection {
  shift_id: string;
  production_time: {
    total_runtime_seconds: number;
    total_break_seconds: number;
    total_unknown_seconds: number;
    utilization_percent: number;
  };
  breaks: Array<{
    start_time: Date;
    end_time: Date;
    duration_seconds: number;
    confidence: number;
  }>;
  runs: Array<{
    start_time: Date;
    end_time: Date;
    duration_seconds: number;
    confidence: number;
  }>;
  validation_summary: {
    total_periods: number;
    validated_correct: number;
    validated_incorrect: number;
    pending: number;
    accuracy_percent: number;
  };
  camera_health: {
    uptime_percent: number;
    offline_incidents: number;
  };
}
```

### 6.2 Report Generation API

```typescript
// GET /api/v1/reports/shift/{shift_id}/cv-section
{
  "shift_id": "shift-uuid",
  "production_time": {
    "total_runtime_seconds": 24480,
    "total_break_seconds": 4320,
    "total_unknown_seconds": 0,
    "utilization_percent": 85
  },
  "breaks": [
    {
      "start_time": "2026-01-09T15:30:00.000Z",
      "end_time": "2026-01-09T15:45:00.000Z",
      "duration_seconds": 900,
      "confidence": 94
    },
    // ... more breaks
  ],
  "validation_summary": {
    "total_periods": 7,
    "validated_correct": 6,
    "validated_incorrect": 0,
    "pending": 1,
    "accuracy_percent": 100
  },
  "camera_health": {
    "uptime_percent": 99.8,
    "offline_incidents": 0
  }
}
```

---

## 7. Photo Storage & Management

### 7.1 Storage Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHOTO STORAGE FLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Raspberry Pi                                                  │
│   ├── Captures photo                                           │
│   ├── Saves locally: /var/ais/photos/pending/{uuid}.jpg        │
│   ├── Sends event to server                                    │
│   └── Receives pre-signed upload URLs                          │
│                                                                 │
│   Photo Upload                                                  │
│   ├── PUT to pre-signed URL (S3-compatible)                    │
│   ├── Server generates thumbnail (400px width)                 │
│   └── Mark local file for cleanup                              │
│                                                                 │
│   Cloud Storage (S3/R2)                                        │
│   └── /cv-photos/{tenant_id}/{date}/{shift_id}/                │
│       ├── {photo_uuid}.jpg        (Original, max 2MB)          │
│       └── {photo_uuid}_thumb.jpg  (Thumbnail, ~50KB)           │
│                                                                 │
│   Retention                                                     │
│   ├── Full resolution: 30 days                                 │
│   ├── Thumbnails: 90 days                                      │
│   └── Metadata: Permanent                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Photo URL Generation

```typescript
// Server generates pre-signed upload URLs
function generatePhotoUploadUrls(eventId: string, count: number): string[] {
  const urls = [];
  for (let i = 0; i < count; i++) {
    const photoId = generateUUID();
    const path = `cv-photos/${tenantId}/${date}/${shiftId}/${photoId}.jpg`;
    const url = s3Client.getSignedUrl('putObject', {
      Bucket: CV_PHOTOS_BUCKET,
      Key: path,
      ContentType: 'image/jpeg',
      Expires: 3600  // 1 hour
    });
    urls.push(url);
  }
  return urls;
}
```

### 7.3 Local Pi Storage

```yaml
local_storage:
  base_path: /var/ais/cv
  directories:
    pending: /var/ais/cv/photos/pending    # Awaiting upload
    uploaded: /var/ais/cv/photos/uploaded  # Uploaded, awaiting cleanup
    failed: /var/ais/cv/photos/failed      # Upload failed, retry queue
    
  retention:
    pending_max_age_hours: 24
    uploaded_cleanup_delay_hours: 1
    failed_max_retries: 5
    
  limits:
    max_pending_photos: 500
    max_storage_gb: 10
    cleanup_trigger_percent: 80
```

---

## 8. Offline Operation

### 8.1 Event Queue

When server connectivity is lost, the Pi queues events locally:

```typescript
interface OfflineEventQueue {
  queue_path: '/var/ais/cv/queue/events.db';  // SQLite
  max_queue_size: 10000;
  max_queue_age_hours: 72;
  
  operations: {
    enqueue(event: CVEvent): void;
    dequeue(count: number): CVEvent[];
    markSynced(eventIds: string[]): void;
    getQueueDepth(): number;
  };
}
```

### 8.2 Sync Recovery

```
OFFLINE → ONLINE RECOVERY SEQUENCE:

1. WebSocket reconnects
2. Pi checks queue depth
3. If queue > 0:
   a. Fetch oldest 50 events
   b. POST to /events/batch
   c. Upload associated photos
   d. Mark synced, repeat until queue empty
4. Resume real-time event streaming
5. Alert: "CV system recovered — {X} events synced"
```

### 8.3 Conflict Resolution

Since CV events are append-only and generated by a single device, conflicts are rare. Resolution:

| Scenario | Resolution |
|----------|------------|
| **Duplicate event_id** | Server ignores (idempotent) |
| **Gap in timestamps** | Logged but accepted (connectivity gap) |
| **Out-of-order events** | Accepted, sorted by client_timestamp |
| **Photo upload fails** | Retry queue, event still valid |

---

## 9. Validation UI Integration

### 9.1 Validation Workflow API

```typescript
// GET /api/v1/cv/validation/pending?shift_id={shift_id}
{
  "periods": [
    {
      "period_id": "period-uuid",
      "state": "RUN",
      "start_time": "2026-01-09T14:32:15.000Z",
      "end_time": "2026-01-09T15:05:00.000Z",
      "duration_seconds": 1965,
      "confidence": 91,
      "photo_count": 7,
      "validation_status": "PENDING"
    },
    // ... more periods
  ],
  "total_pending": 3
}

// GET /api/v1/cv/validation/period/{period_id}/photos
{
  "period_id": "period-uuid",
  "state": "RUN",
  "photos": [
    {
      "photo_id": "photo-uuid-1",
      "camera_id": "CAM-1",
      "captured_at": "2026-01-09T14:32:15.000Z",
      "confidence": 95,
      "thumbnail_url": "https://...",
      "full_url": "https://...",
      "validation_result": null
    },
    // ... more photos
  ]
}

// POST /api/v1/cv/validation/photo/{photo_id}/validate
{
  "result": "CORRECT"  // or "INCORRECT"
}

// Response: 200 OK
{
  "photo_id": "photo-uuid-1",
  "validation_result": "CORRECT",
  "validated_by": "user-uuid",
  "validated_at": "2026-01-10T10:30:00.000Z"
}

// POST /api/v1/cv/validation/period/{period_id}/complete
// Mark entire period as validated after reviewing photos
{
  "result": "VALIDATED"  // or "DISPUTED"
}
```

### 9.2 Validation UI Wireframe

```
┌─────────────────────────────────────────────────────────────────┐
│ CV VALIDATION — Shift 2 (14:00 - 22:00)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Period: RUNNING • 14:32 - 15:05 (32 min 45 sec)                │
│ System Confidence: 91%                                          │
│                                                                 │
│ Review Photos (7 total):                                        │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │ │
│ │  │ 📷 CAM1 │  │ 📷 CAM2 │  │ 📷 CAM1 │  │ 📷 CAM3 │        │ │
│ │  │ 14:32   │  │ 14:37   │  │ 14:42   │  │ 14:47   │        │ │
│ │  │ 95% ✓   │  │ 88% ✓   │  │ 92% ✓   │  │ 78%     │        │ │
│ │  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │ │
│ │                                                             │ │
│ │  ┌─────────┐  ┌─────────┐  ┌─────────┐                     │ │
│ │  │ 📷 CAM1 │  │ 📷 CAM2 │  │ 📷 CAM1 │                     │ │
│ │  │ 14:52   │  │ 14:57   │  │ 15:02   │                     │ │
│ │  │ 94% ✓   │  │ 90%     │  │ 89%     │                     │ │
│ │  └─────────┘  └─────────┘  └─────────┘                     │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ Tap photo to enlarge • ✓ = Marked correct                      │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ All photos show RUNNING state?                              │ │
│ │                                                             │ │
│ │   [ ✓ YES — Validate as Correct ]                          │ │
│ │   [ ✗ NO — Flag for Review ]                               │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ Progress: 4/7 periods validated                                │
│ [← Previous Period]                    [Next Period →]         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. Alerting Integration

### 10.1 CV-Generated Alerts

| Alert Type | Trigger | Recipient | Severity |
|------------|---------|-----------|----------|
| **Camera Offline** | Any camera offline > 5 minutes | Production Manager | Warning |
| **All Cameras Offline** | All 3 cameras offline | Owner + Production Manager | Critical |
| **Extended Break** | Break > 30 minutes | Supervisor | Info |
| **Unusual Break Pattern** | > 3 breaks/hour | Production Manager | Warning |
| **Low Confidence** | Avg confidence < 70% for 10+ min | System Admin | Warning |
| **Sync Failure** | Event queue > 100 or > 1 hour old | System Admin | Warning |

### 10.2 Alert API

```typescript
// Alerts generated by CV Service
interface CVAlert {
  alert_id: string;
  alert_type: CVAlertType;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  title: string;
  message: string;
  data: Record<string, any>;
  created_at: Date;
  acknowledged_at?: Date;
  acknowledged_by?: string;
}

// Example alert
{
  "alert_id": "alert-uuid",
  "alert_type": "CAMERA_OFFLINE",
  "severity": "WARNING",
  "title": "Camera Offline: CAM-2 (Mill Stands)",
  "message": "CAM-2 has been offline for 7 minutes. Production detection may be affected.",
  "data": {
    "camera_id": "CAM-2",
    "offline_since": "2026-01-10T15:23:00.000Z",
    "duration_minutes": 7
  },
  "created_at": "2026-01-10T15:30:00.000Z"
}
```

---

## 11. Security Considerations

### 11.1 API Security

```yaml
security:
  transport:
    - TLS 1.3 required for all connections
    - Certificate pinning on Pi (optional but recommended)
    
  authentication:
    - API key identifies tenant
    - Device token (JWT) identifies specific device
    - Token rotation every 24 hours
    - Revocation list checked on each request
    
  authorization:
    - Device can only write events for its tenant
    - Device cannot access other devices' data
    - Dashboard access requires user authentication
    
  rate_limiting:
    events: 10/second per device
    photos: 5/second per device
    heartbeat: 1/minute per device
    
  validation:
    - All inputs sanitized
    - Event timestamps validated (not future, not > 72h past)
    - Photo size limited to 5MB
```

### 11.2 Data Privacy

```yaml
data_handling:
  photos:
    - Stored in tenant-isolated buckets
    - Pre-signed URLs expire after 1 hour
    - No public access to photo storage
    
  retention:
    - Events: Permanent (audit trail)
    - Photos: 30 days full, 90 days thumbnails
    - Health logs: 30 days
    
  access_logging:
    - All API calls logged with user/device ID
    - Photo access logged
    - Validation actions logged
```

---

## 12. Error Handling

### 12.1 API Error Responses

```typescript
// Standard error response
{
  "error": {
    "code": "CV_EVENT_INVALID",
    "message": "Event timestamp is in the future",
    "details": {
      "event_timestamp": "2026-01-11T15:00:00.000Z",
      "server_timestamp": "2026-01-10T15:00:00.000Z"
    }
  }
}

// Error codes
const CV_ERROR_CODES = {
  CV_AUTH_FAILED: 'Device authentication failed',
  CV_DEVICE_NOT_FOUND: 'Device not registered',
  CV_EVENT_INVALID: 'Event validation failed',
  CV_EVENT_DUPLICATE: 'Event already processed',
  CV_PHOTO_TOO_LARGE: 'Photo exceeds size limit',
  CV_QUEUE_FULL: 'Server queue at capacity',
  CV_RATE_LIMITED: 'Too many requests',
};
```

### 12.2 Pi Error Recovery

```yaml
error_recovery:
  api_failure:
    - Retry with exponential backoff (1s, 2s, 4s, 8s, 16s, 30s max)
    - Queue event locally after 5 retries
    - Continue processing, don't block on API
    
  photo_upload_failure:
    - Retry 3 times immediately
    - Move to retry queue
    - Background job retries every 5 minutes
    - Discard after 24 hours (with log)
    
  websocket_disconnect:
    - Reconnect with backoff
    - Switch to REST-only mode after 60 seconds
    - Restore WebSocket when available
    
  camera_failure:
    - Log camera offline event
    - Continue with remaining cameras
    - Alert if all cameras offline
```

---

## 13. Monitoring & Observability

### 13.1 Metrics

```yaml
metrics:
  pi_side:
    - cv_events_sent_total (counter)
    - cv_events_queued (gauge)
    - cv_photos_uploaded_total (counter)
    - cv_api_latency_seconds (histogram)
    - cv_camera_fps (gauge, per camera)
    - cv_detection_confidence (gauge)
    
  server_side:
    - cv_events_received_total (counter)
    - cv_events_processed_total (counter)
    - cv_events_failed_total (counter)
    - cv_photos_stored_total (counter)
    - cv_photos_storage_bytes (gauge)
    - cv_websocket_connections (gauge)
    - cv_api_request_duration_seconds (histogram)
```

### 13.2 Logging

```yaml
logging:
  pi_side:
    level: INFO (DEBUG in development)
    format: JSON
    fields: [timestamp, level, component, message, event_id, camera_id]
    rotation: Daily, 7 days retention
    
  server_side:
    level: INFO
    format: JSON
    fields: [timestamp, level, tenant_id, device_id, request_id, message]
    destination: CloudWatch / ELK
```

---

## 14. Dependencies

| Dependency | Module | Required For |
|------------|--------|--------------|
| CV-CORE | Detection Logic | Event generation |
| CV-CAMERAS | Camera Config | Camera status |
| AIS Server | API | Event storage, dashboards |
| Cloud Storage | S3/R2 | Photo storage |
| PostgreSQL | Database | Event/photo metadata |
| Redis | Cache | Real-time state, sessions |

---

## 15. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Event delivery rate** | ≥99.5% | Events received / events generated |
| **Event latency** | <5 seconds | Time from Pi detection to server receipt |
| **Photo upload success** | ≥99% | Photos uploaded / photos captured |
| **Dashboard freshness** | <10 seconds | Time from state change to dashboard update |
| **Offline recovery** | 100% | Queued events synced after connectivity |
| **API availability** | ≥99.9% | Uptime during production hours |

---

*This specification is part of the AIS Production CV module suite.*
*Related specs: CV-CORE, CV-CAMERAS, CV-VALIDATION*
