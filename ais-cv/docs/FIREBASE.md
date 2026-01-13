# AIS-CV Firebase Integration

## Overview

AIS-CV syncs production data to Firebase Firestore for real-time dashboards and historical analytics.

## Firestore Schema

### Collections Overview

```
Firestore Database
├── live/
│   └── furnace          # Real-time dashboard data
├── counts/
│   └── {auto-id}        # Individual count events
├── daily/
│   └── {YYYY-MM-DD}     # Daily aggregates
├── hourly/
│   └── {YYYY-MM-DD}/
│       └── hours/
│           └── {HH}     # Hourly breakdown
└── sessions/
    └── {auto-id}        # Completed RUN/BREAK sessions
```

### Document Schemas

#### `live/furnace` - Real-time Dashboard

```typescript
{
  today_count: number,        // Current day's piece count
  status: 'RUNNING' | 'BREAK' | 'OFFLINE',
  last_count: Timestamp,      // When last piece was counted
  last_travel_time: number,   // Travel time of last piece (seconds)
  date: string,               // Current date (YYYY-MM-DD)
  status_updated: Timestamp,  // Last status update time
  current_session: {          // Active session info
    type: 'RUN' | 'BREAK',
    start: Timestamp,
    duration_minutes: number
  }
}
```

#### `counts/{auto-id}` - Individual Count Events

```typescript
{
  timestamp: Timestamp,
  travel_time: number,        // Seconds from L1 to L3
  confidence: number,         // 0-100 confidence score
  line_pixels: {
    L1: number,
    L2: number,
    L3: number
  },
  line_frames: {
    L1: number,
    L2: number,
    L3: number
  },
  line_brightness: {
    L1: number,
    L2: number,
    L3: number
  },
  camera: string,             // 'CAM-1'
  date: string,               // 'YYYY-MM-DD'
  hour: string,               // 'HH'
  photo_filename: string,     // Filename of captured photo
  flagged: boolean,           // Auto-flagged for review (confidence < 70)
  reviewed: boolean           // Has been manually reviewed
}
```

#### `daily/{YYYY-MM-DD}` - Daily Aggregates

```typescript
{
  count: number,              // Total pieces counted
  first_count: Timestamp,     // First count of the day
  last_count: Timestamp,      // Most recent count
  total_run_minutes: number,  // Total production time
  total_break_minutes: number,// Total idle time
  date: string,               // 'YYYY-MM-DD'
  camera: string              // 'CAM-1'
}
```

#### `hourly/{YYYY-MM-DD}/hours/{HH}` - Hourly Breakdown

```typescript
{
  count: number,              // Pieces this hour
  run_minutes: number,        // Production time this hour
  break_minutes: number       // Idle time this hour
}
```

#### `sessions/{auto-id}` - Completed Sessions

```typescript
{
  type: 'RUN' | 'BREAK',
  start: Timestamp,
  end: Timestamp,
  date: string,               // 'YYYY-MM-DD'
  hour: string,               // Hour when session started
  duration_minutes: number,
  count: number               // Pieces during RUN sessions
}
```

## Setup

### 1. Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Create new project (or use existing AIS project)
3. Enable Firestore Database
4. Select region closest to your location

### 2. Create Service Account

1. Firebase Console → Project Settings → Service Accounts
2. Click "Generate new private key"
3. Save JSON file as `config/firebase-service-account.json`

**Important:** Never commit this file! It grants write access to your database.

### 3. Firestore Security Rules

Set these rules in Firebase Console → Firestore → Rules:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // AIS CV has full write access via service account
    // Dashboard users have read-only access
    
    match /live/{document=**} {
      allow read: if true;  // Public read for dashboard
      allow write: if false; // Only service account writes
    }
    
    match /counts/{document=**} {
      allow read: if request.auth != null;
      allow write: if false;
    }
    
    match /daily/{document=**} {
      allow read: if request.auth != null;
      allow write: if false;
    }
    
    match /hourly/{document=**} {
      allow read: if request.auth != null;
      allow write: if false;
    }
    
    match /sessions/{document=**} {
      allow read: if request.auth != null;
      allow write: if false;
    }
  }
}
```

### 4. Test Connection

```bash
cd /home/adityajain/AIS/ais-cv
source venv/bin/activate
python scripts/test_firebase.py
```

Expected output:
```
Firebase initialized successfully
Today's count: 0
Connection test passed!
```

## Usage

### FirebaseClient API

```python
from src.firebase_client import get_firebase_client

# Get singleton client
firebase = get_firebase_client()

# Initialize (call once at startup)
if firebase.initialize():
    print("Connected!")

# Push a count
firebase.push_count({
    'timestamp': datetime.now(),
    'travel_time': 1.85,
    'confidence': 87.5,
    'line_pixels': {'L1': 245, 'L2': 230, 'L3': 218},
    'line_frames': {'L1': 3, 'L2': 3, 'L3': 2},
    'line_brightness': {'L1': 185.2, 'L2': 182.1, 'L3': 179.8},
    'photo_filename': 'count_42_20260112_143215.jpg'
}, session_info={'run_minutes_since_last': 0.5})

# Push completed session
firebase.push_session({
    'type': 'RUN',
    'start': start_time,
    'end': end_time,
    'date': '2026-01-12',
    'hour': '14',
    'duration_minutes': 45.5,
    'count': 127
})

# Update status
firebase.update_status('RUNNING', {
    'type': 'RUN',
    'start': session_start,
    'duration_minutes': 12.3
})

# Reset daily count (call at midnight)
firebase.reset_daily_count()

# Get current count
count = firebase.get_today_count()
```

### Session Info for Run Time Tracking

When pushing counts, include `session_info` to track run time:

```python
# When a piece is counted
session_info = {
    'run_minutes_since_last': elapsed_minutes  # Time since last count
}
firebase.push_count(count_data, session_info)
```

This enables accurate run time tracking even when pieces are counted irregularly.

## Querying Data

### From Web Dashboard

```javascript
// Real-time listener for live status
import { doc, onSnapshot } from 'firebase/firestore';

const liveRef = doc(db, 'live', 'furnace');
onSnapshot(liveRef, (doc) => {
  const data = doc.data();
  console.log(`Count: ${data.today_count}, Status: ${data.status}`);
});
```

### Historical Queries

```javascript
// Get today's hourly breakdown
const today = new Date().toISOString().split('T')[0];
const hourlyRef = collection(db, 'hourly', today, 'hours');
const snapshot = await getDocs(hourlyRef);

snapshot.forEach(doc => {
  console.log(`Hour ${doc.id}: ${doc.data().count} pieces`);
});

// Get counts needing review
const countsRef = collection(db, 'counts');
const q = query(countsRef, 
  where('flagged', '==', true),
  where('reviewed', '==', false),
  orderBy('timestamp', 'desc'),
  limit(50)
);
```

## Offline Mode

Run counter without Firebase sync:

```bash
python scripts/run_counter.py --no-firebase
```

Data is still logged locally. Later sync can be implemented if needed.

## Data Retention

### Recommended Cleanup

```javascript
// Cloud Function to delete old counts (optional)
exports.cleanupOldCounts = functions.pubsub
  .schedule('0 0 * * *')  // Daily at midnight
  .onRun(async (context) => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 90);  // 90 days retention
    
    const snapshot = await db.collection('counts')
      .where('timestamp', '<', cutoff)
      .limit(500)
      .get();
    
    const batch = db.batch();
    snapshot.docs.forEach(doc => batch.delete(doc.ref));
    await batch.commit();
  });
```

## Troubleshooting

### "Failed to initialize Firebase"

1. Check service account file exists:
   ```bash
   ls -la config/firebase-service-account.json
   ```

2. Verify file is valid JSON:
   ```bash
   python -c "import json; json.load(open('config/firebase-service-account.json'))"
   ```

3. Check project ID matches:
   ```bash
   cat config/firebase-service-account.json | grep project_id
   ```

### "Permission denied"

1. Check Firestore rules allow writes from service account
2. Verify service account has "Cloud Datastore User" role
3. Regenerate service account key if corrupted

### "Network unreachable"

1. Check internet connectivity:
   ```bash
   ping google.com
   ```

2. Check firewall allows HTTPS:
   ```bash
   curl https://firestore.googleapis.com
   ```

### High Latency

1. Use batch writes for multiple operations
2. Consider regional Firestore location
3. Monitor quota usage in Firebase Console

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Configuration](CONFIGURATION.md)
- [Deployment](DEPLOYMENT.md)
