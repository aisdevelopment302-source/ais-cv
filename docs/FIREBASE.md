# Firebase Integration

AIS-CV syncs production analytics to Firebase Firestore for real-time dashboards and historical reporting.

---

## Setup

### 1. Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Create or open the AIS project
3. Enable **Firestore Database** (Native mode)
4. Choose a region close to your deployment location

### 2. Service Account

1. Firebase Console → Project Settings → Service Accounts
2. Click **Generate new private key**
3. Save the JSON file as `config/firebase-service-account.json`

> **Never commit this file.** It grants write access to the entire database.

### 3. Test Connection

```bash
cd /home/adityajain/AIS/ais-cv
source venv/bin/activate
python scripts/test_firebase.py
```

Expected output:
```
Firebase initialized successfully
Connection test passed!
```

### 4. Firestore Security Rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Public read for dashboards (live status only)
    match /live/{doc=**} {
      allow read: if true;
      allow write: if false;  // Only service account writes
    }
    // Authenticated read for analytics
    match /{collection=**} {
      allow read: if request.auth != null;
      allow write: if false;
    }
  }
}
```

---

## Firestore Schema

### Collections Overview

```
Firestore
├── live/
│   └── mill_stand       ← CAM-2 real-time status
│
├── daily/{YYYY-MM-DD_cam2}   ← CAM-2 daily totals (composite doc ID)
│
├── hourly/{YYYY-MM-DD}/hours/{HH}  ← hourly breakdown
│
└── sessions/{id}        ← RUN/BREAK sessions (camera: 'CAM-2')
```

---

## CAM-2 + CAM-3: Mill Stand Counter

The mill stand counter writes session analytics and live status to Firestore.
CAM-3 (channel 3, 1 area) counts the same pieces as CAM-2 from a different angle
and its detections feed into the same quorum-confirmed piece count. All Firebase
writes use `CAM-2` as the camera identifier — there are no separate `CAM-3` keys —
because both cameras collectively produce a single authoritative piece count.

**Piece-level data is stored locally only** — sufficient for dashboards and shift reporting.

### What is NOT written to Firestore

- Individual piece `counts/` documents
- `vote_ratio`, `avg_travel_time`, `stands_detected` per piece
- Entry/exit line pixel data

### `live/mill_stand`

```typescript
{
  today_count: number,
  status: 'RUNNING' | 'BREAK' | 'OFFLINE',
  last_count: Timestamp,
  last_avg_travel_time: number,    // Avg entry→exit travel time of last piece (seconds)
  date: string,
  status_updated: Timestamp,
  current_session: {
    type: 'RUN' | 'BREAK',
    start: Timestamp,
    duration_minutes: number,
    count: number
  }
}
```

### `daily/{YYYY-MM-DD_cam2}`

Uses a composite document ID (`YYYY-MM-DD_cam2`, e.g. `2026-02-27_cam2`). The document carries a `camera` field for query filtering:

```typescript
{
  count: number,
  first_count: Timestamp,
  last_count: Timestamp,
  total_run_minutes: number,
  total_break_minutes: number,
  date: string,                // 'YYYY-MM-DD' (without the _cam2 suffix)
  camera: 'CAM-2'
}
```

### `hourly/{YYYY-MM-DD}/hours/{HH}`

```typescript
{
  count: number,
  run_minutes: number,
  break_minutes: number
}
```

### `sessions/{id}`

```typescript
{
  type: 'RUN' | 'BREAK',
  start: Timestamp,
  end: Timestamp | null,
  date: string,
  hour: string,
  duration_minutes: number,
  count: number,
  average_speed: number,        // Avg entry→exit travel time (RUN sessions)
  camera: 'CAM-2'
}
```

---

## FirebaseClient API

```python
from src.firebase_client import get_firebase_client

firebase = get_firebase_client()
firebase.initialize()  # Call once at startup; returns bool

# Increment live/mill_stand, daily/, hourly/ — does NOT write to counts/
firebase.push_mill_count({
    'timestamp': datetime.now(IST),
}, session_info={'run_minutes_since_last': 0.3})

firebase.update_mill_status('RUNNING', session_info)
firebase.get_mill_today_count()

# Session lifecycle
firebase.create_session(session)   # Called when session STARTS
firebase.update_session(session)   # Called as count increments

# Startup recovery
last = firebase.get_last_session()  # Returns dict or None
```

---

## Querying Data

### Real-Time Dashboard (JavaScript)

```javascript
import { doc, onSnapshot } from 'firebase/firestore';

// CAM-2 live status
onSnapshot(doc(db, 'live', 'mill_stand'), (snap) => {
  const { today_count, status, last_avg_travel_time } = snap.data();
});
```

### Daily Summary

```javascript
import { doc, getDoc } from 'firebase/firestore';

const today = new Date().toISOString().split('T')[0];
const cam2  = await getDoc(doc(db, 'daily', `${today}_cam2`));
// cam2.data().count, .total_run_minutes, .camera === 'CAM-2'
```

### Hourly Breakdown

```javascript
import { collection, getDocs } from 'firebase/firestore';

const hours = await getDocs(
  collection(db, 'hourly', '2026-02-24', 'hours')
);
hours.forEach(doc => {
  console.log(`${doc.id}:00 → ${doc.data().count} pieces`);
});
```

### Session History

```javascript
import { collection, query, where, orderBy, limit, getDocs } from 'firebase/firestore';

// Recent CAM-2 sessions
const q = query(
  collection(db, 'sessions'),
  where('camera', '==', 'CAM-2'),
  where('type', '==', 'RUN'),
  orderBy('start', 'desc'),
  limit(20)
);
const snap = await getDocs(q);
```

---

## Offline Mode

```bash
# Run without Firebase (counts logged locally only)
python scripts/run_mill_counter.py --no-firebase
```

---

## Troubleshooting

### "Failed to initialize Firebase"

```bash
# Check file exists
ls -la config/firebase-service-account.json

# Validate JSON
python -c "import json; json.load(open('config/firebase-service-account.json'))"

# Check project ID
python -c "import json; print(json.load(open('config/firebase-service-account.json'))['project_id'])"
```

### "Permission denied"

1. Check Firestore rules allow service account writes
2. Verify the service account has the **Cloud Datastore User** IAM role
3. Regenerate the service account key in Firebase Console

### Data not appearing

1. Check `live/mill_stand` exists in Firestore Console
2. Verify the `date` field on the document matches today (`YYYY-MM-DD` format)
3. Check `data/logs/mill_counter.log` for Firebase error lines

### High write latency

- Firestore writes are async and fire-and-forget — they do not block counting
- Batch writes are not used (each event is small, latency is acceptable)
- Check quota usage in Firebase Console → Usage tab

---

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Deployment](DEPLOYMENT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
