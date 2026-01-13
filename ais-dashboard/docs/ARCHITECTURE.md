# AIS Dashboard Architecture

## Overview

The AIS Dashboard is a **hybrid web application** that combines Next.js React components with static HTML pages to provide real-time production monitoring for the steel mill plate scrap counting system.

## Architectural Decisions

### Why Hybrid Approach?

The dashboard uses **two rendering strategies** for different use cases:

| Approach | Use Case | Benefits |
|----------|----------|----------|
| **Static HTML** (`public/`) | Production displays, mobile access | Zero JavaScript build, CDN Tailwind, instant load |
| **Next.js React** (`pages/`) | Development, future enhancements | Component reusability, SSR capabilities |

### Current Implementation

```
ais-dashboard/
├── pages/                    # Next.js React pages
│   ├── _app.js              # App wrapper with global CSS
│   └── index.js             # React dashboard (development)
├── public/                   # Static HTML pages (production)
│   ├── index.html           # Live dashboard
│   ├── day.html             # Day detail with session timeline
│   ├── history.html         # 30-day production history
│   ├── review.html          # Count validation interface
│   ├── summary.html         # Weekly performance stats
│   └── js/                  # Shared utilities
│       ├── firebase-init.js # Firebase initialization
│       └── utils.js         # Helper functions
├── lib/
│   └── firebase.js          # Firebase config (Next.js)
└── styles/
    └── globals.css          # Tailwind CSS
```

## Technology Stack

### Core Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| **Next.js** | 14.x | React framework with SSR/SSG |
| **React** | 18.x | UI component library |
| **Firebase** | 10.7.1 | Firestore real-time database |
| **Tailwind CSS** | 3.4.x | Utility-first styling |

### Static Pages Stack

- **Tailwind CDN** - No build required for styling
- **Firebase ESM** - Direct browser imports from gstatic.com
- **Vanilla JavaScript** - No framework overhead

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AIS CV MODULE                            │
│              (Raspberry Pi + Camera)                         │
│                        │                                     │
│            Writes to Firestore                               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   FIREBASE FIRESTORE                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │   live   │ │  counts  │ │  daily   │ │ sessions │       │
│  │ /furnace │ │          │ │          │ │          │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└────────────────────────┬────────────────────────────────────┘
                         │
           Real-time listeners (onSnapshot)
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   AIS DASHBOARD                              │
│  ┌────────────────┐  ┌────────────────┐                     │
│  │  Static HTML   │  │   Next.js      │                     │
│  │  (Production)  │  │   (Dev/Future) │                     │
│  └────────────────┘  └────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

## Real-Time Updates

### Live Dashboard Pattern

The dashboard uses Firebase `onSnapshot` listeners for real-time updates:

```javascript
// Real-time listener pattern
onSnapshot(doc(db, 'live', 'furnace'), (doc) => {
  if (doc.exists()) {
    const data = doc.data();
    // Update UI immediately
    updateDisplay(data.today_count);
    updateStatus(data.status);
  }
});
```

### Subscription Management

- **Live Page**: Persistent listeners (auto-reconnect)
- **Historical Pages**: One-time fetches with `getDocs()`
- **Cleanup**: Listeners unsubscribed on page unload

## Photo Integration

Photos are served from the Raspberry Pi's local API:

```
┌─────────────────┐     HTTP GET     ┌──────────────────┐
│   Dashboard     │ ───────────────► │  Photo API       │
│   (Browser)     │                  │  192.168.1.23    │
│                 │ ◄─────────────── │  :5001           │
│                 │     JPEG Image   │                  │
└─────────────────┘                  └──────────────────┘
```

**Note**: Photos only accessible on local network. Dashboard gracefully handles unavailability.

## State Management

### Static Pages
- No state library - DOM manipulation only
- State stored in DOM elements
- URL parameters for page configuration

### Next.js Pages
- React `useState` for component state
- React `useEffect` for side effects
- Firebase listeners manage real-time state

## Responsive Design

- **Mobile-first** approach with Tailwind
- Dark theme optimized for shop floor visibility
- Touch-friendly controls for mobile devices
- Fixed footer navigation on all pages

## Security Considerations

### Firebase Security
- Client-side Firebase SDK (read-only access)
- Firestore security rules control write access
- API keys are public (client-side) but restricted by rules

### Network Security
- Photo API on isolated local network (192.168.1.23)
- Dashboard can be deployed anywhere (reads from Firebase)
- No authentication required for read access (intentional for shop floor)

## Performance Optimizations

1. **CDN Tailwind** - No CSS build for static pages
2. **ES Module Imports** - Tree-shaken Firebase SDK
3. **Lazy Photo Loading** - User-triggered photo fetch
4. **Query Limits** - All queries use `limit()` to prevent over-fetching
5. **Minimal Re-renders** - DOM updates only on data change

## Future Architecture Considerations

### Potential Enhancements
- Convert static pages to Next.js for unified codebase
- Add Server-Side Rendering for SEO
- Implement React Query for data fetching
- Add offline support with Service Workers
- Multi-camera support with camera selector

### Scaling Considerations
- Current architecture supports single camera
- Firebase scales automatically
- Dashboard is stateless (horizontal scaling)
