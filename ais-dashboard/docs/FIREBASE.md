# Firebase Integration

## Overview

The AIS Dashboard consumes data from Firebase Firestore in **read-only mode**. All write operations are performed by the `ais-cv` module running on the Raspberry Pi.

## Firebase Configuration

### Project Details

| Property | Value |
|----------|-------|
| Project ID | `ais-production-e013c` |
| Auth Domain | `ais-production-e013c.firebaseapp.com` |
| Region | Default (us-central1) |

### Initialization

**Static HTML Pages** (ESM imports):
```javascript
import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js';
import { getFirestore } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js';

const firebaseConfig = {
  apiKey: "AIzaSyCBXxSsvjnFzGMMFbHCYouokIQydObeElo",
  authDomain: "ais-production-e013c.firebaseapp.com",
  projectId: "ais-production-e013c",
  storageBucket: "ais-production-e013c.firebasestorage.app",
  messagingSenderId: "565647781984",
  appId: "1:565647781984:web:0f05c2436afdcc7a0b1305"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
```

**Next.js Pages** (`lib/firebase.js`):
```javascript
import { initializeApp } from 'firebase/app';
import { getFirestore } from 'firebase/firestore';

// Same config...
const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
```

---

## Firestore Collections

### Collection Overview

```
firestore/
├── live/
│   └── furnace          # Real-time status document
├── counts/              # Individual count events
├── daily/               # Daily aggregations
├── sessions/            # Run/Break sessions
└── hourly/              # Hourly aggregations (optional)
```

---

## Collection: `live`

### Document: `live/furnace`

Real-time status updated by the CV module.

| Field | Type | Description |
|-------|------|-------------|
| `today_count` | number | Total pieces counted today |
| `status` | string | Current status: `RUNNING`, `BREAK`, `OFFLINE` |
| `last_count` | timestamp | When last piece was counted |
| `last_travel_time` | number | Travel time of last piece (seconds) |
| `current_session` | object | Active session info (see below) |

#### `current_session` Object

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | Session date (YYYY-MM-DD) |
| `type` | string | `RUN` or `BREAK` |
| `start` | timestamp | When session started |

### Dashboard Usage

```javascript
// Live Dashboard - Real-time listener
onSnapshot(doc(db, 'live', 'furnace'), (doc) => {
  if (doc.exists()) {
    const data = doc.data();
    countDisplay.textContent = data.today_count || 0;
    statusDisplay.textContent = data.status || 'OFFLINE';
  }
});
```

---

## Collection: `counts`

Individual count events with detection metadata.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When count occurred |
| `date` | string | Date string (YYYY-MM-DD) |
| `travel_time` | number | Time piece took to cross (seconds) |
| `confidence` | number | Detection confidence (0-100) |
| `flagged` | boolean | Auto-flagged for review |
| `reviewed` | boolean | Has been manually reviewed |
| `review_result` | string | `correct` or `false_positive` |
| `reviewed_at` | timestamp | When reviewed |
| `line_frames` | object | Frames detected per line |
| `line_pixels` | object | Pixels detected per line |
| `photo_filename` | string | Filename of saved photo |

#### `line_frames` Object

| Field | Type | Description |
|-------|------|-------------|
| `L1` | number | Frames on line 1 |
| `L2` | number | Frames on line 2 |
| `L3` | number | Frames on line 3 |

### Dashboard Queries

**Recent Counts (Live Page)**:
```javascript
const countsQuery = query(
  collection(db, 'counts'),
  orderBy('timestamp', 'desc'),
  limit(5)
);

onSnapshot(countsQuery, (snapshot) => {
  snapshot.forEach((doc) => {
    const data = doc.data();
    // Display recent count
  });
});
```

**Flagged Counts (Review Page)**:
```javascript
const flaggedQuery = query(
  collection(db, 'counts'),
  where('date', '==', '2026-01-13'),
  where('flagged', '==', true),
  orderBy('timestamp', 'desc'),
  limit(100)
);
```

**Low Confidence Counts**:
```javascript
const lowConfQuery = query(
  collection(db, 'counts'),
  where('date', '==', '2026-01-13'),
  where('confidence', '<', 70),
  orderBy('confidence', 'asc'),
  limit(100)
);
```

---

## Collection: `daily`

Daily aggregated statistics. Document ID = date (YYYY-MM-DD).

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | Date (YYYY-MM-DD) |
| `count` | number | Total pieces for the day |
| `total_run_minutes` | number | Total run time (minutes) |
| `total_break_minutes` | number | Total break time (minutes) |

### Dashboard Queries

**Today's Stats (Live Page)**:
```javascript
const today = new Date().toISOString().split('T')[0];

onSnapshot(doc(db, 'daily', today), (doc) => {
  if (doc.exists()) {
    const data = doc.data();
    runTimeDisplay.textContent = formatDuration(data.total_run_minutes);
    breakTimeDisplay.textContent = formatDuration(data.total_break_minutes);
  }
});
```

**History (Last 30 Days)**:
```javascript
const historyQuery = query(
  collection(db, 'daily'),
  orderBy('date', 'desc'),
  limit(30)
);

const snapshot = await getDocs(historyQuery);
```

---

## Collection: `sessions`

Individual run and break sessions.

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | Date (YYYY-MM-DD) |
| `type` | string | `RUN` or `BREAK` |
| `start` | timestamp | Session start time |
| `end` | timestamp | Session end time |
| `duration_minutes` | number | Session duration (minutes) |
| `count` | number | Pieces during session (RUN only) |

### Dashboard Queries

**Day Sessions (Day Detail Page)**:
```javascript
const sessionsQuery = query(
  collection(db, 'sessions'),
  where('date', '==', '2026-01-13')
);

const snapshot = await getDocs(sessionsQuery);
// Sort client-side by start time (descending)
```

---

## Query Patterns

### Real-Time Listeners vs One-Time Fetches

| Pattern | Use Case | Method |
|---------|----------|--------|
| **Real-time** | Live dashboard | `onSnapshot()` |
| **One-time** | Historical data | `getDocs()` |

### Real-Time Pattern

```javascript
// Returns unsubscribe function for cleanup
const unsubscribe = onSnapshot(
  doc(db, 'live', 'furnace'),
  (doc) => {
    // Handle update
  },
  (error) => {
    // Handle error
    console.error('Firestore error:', error);
  }
);

// Cleanup on page unload
window.addEventListener('beforeunload', () => unsubscribe());
```

### One-Time Pattern

```javascript
try {
  const snapshot = await getDocs(query(...));
  snapshot.forEach((doc) => {
    // Process document
  });
} catch (error) {
  console.error('Query failed:', error);
}
```

---

## Write Operations

The dashboard performs **one write operation** - updating review status:

```javascript
// Review Page - Mark count reviewed
import { updateDoc, Timestamp } from 'firebase/firestore';

await updateDoc(doc(db, 'counts', countId), {
  flagged: false,  // or true for false positive
  reviewed: true,
  review_result: 'correct',  // or 'false_positive'
  reviewed_at: Timestamp.now()
});
```

---

## Composite Indexes

Some queries require Firestore composite indexes:

### Required Indexes

| Collection | Fields | Order |
|------------|--------|-------|
| `counts` | `date`, `flagged`, `timestamp` | asc, asc, desc |
| `counts` | `date`, `confidence` | asc, asc |
| `counts` | `date`, `timestamp` | asc, desc |
| `sessions` | `date`, `start` | asc, desc |

### Creating Indexes

When a query fails due to missing index, Firestore provides a link:
```
Error: The query requires an index. 
You can create it here: https://console.firebase.google.com/...
```

Click the link to create the index in Firebase Console.

---

## Error Handling

### Connection Errors

```javascript
onSnapshot(docRef, 
  (doc) => {
    connectionStatus.classList.add('hidden');
    // Process data
  },
  (error) => {
    console.error('Firestore error:', error);
    connectionStatus.classList.remove('hidden');
  }
);
```

### Query Errors

```javascript
try {
  const snapshot = await getDocs(query);
} catch (error) {
  if (error.code === 'failed-precondition') {
    // Missing index - show setup message
  } else if (error.code === 'permission-denied') {
    // Security rules blocking access
  } else {
    // General error
  }
}
```

---

## Security Rules

Current Firestore rules (applied in Firebase Console):

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Read access for all authenticated and unauthenticated users
    match /{document=**} {
      allow read: if true;
    }
    
    // Write access only from Raspberry Pi (server-side)
    match /live/{doc} {
      allow write: if request.auth != null;
    }
    match /counts/{doc} {
      allow write: if request.auth != null;
      // Allow dashboard to update review fields only
      allow update: if request.resource.data.diff(resource.data)
        .affectedKeys().hasOnly(['flagged', 'reviewed', 'review_result', 'reviewed_at']);
    }
    match /daily/{doc} {
      allow write: if request.auth != null;
    }
    match /sessions/{doc} {
      allow write: if request.auth != null;
    }
  }
}
```

---

## Performance Tips

1. **Always use `limit()`** - Prevent fetching entire collections
2. **Index queries** - Create composite indexes for filtered queries
3. **Unsubscribe listeners** - Clean up when components unmount
4. **Use timestamps** - Not date strings for range queries
5. **Batch reads** - Combine multiple `getDocs()` with `Promise.all()`
