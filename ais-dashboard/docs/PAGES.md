# AIS Dashboard Pages

## Overview

The dashboard consists of **5 main views**, each serving a specific purpose in the production monitoring workflow.

## Page Navigation

All pages share a consistent navigation bar:

```
┌─────────────────────────────────────────────────────────┐
│  Live  │  History  │  Today  │  Summary  │  Review     │
└─────────────────────────────────────────────────────────┘
```

---

## 1. Live Dashboard (`index.html`)

**Purpose**: Real-time monitoring of current production status

**URL**: `/` or `/index.html`

### Features

| Feature | Description |
|---------|-------------|
| **Piece Counter** | Large display showing today's total count |
| **Status Indicator** | Visual status (RUNNING/BREAK/OFFLINE) with color-coded dot |
| **Last Travel Time** | Duration of most recent piece crossing |
| **Run/Break Times** | Accumulated time in each state today |
| **Recent Counts** | Last 5 counts with timestamps and travel times |
| **Latest Photo** | Most recent count photo (local network only) |

### Real-Time Updates

- Counter updates instantly via Firebase `onSnapshot`
- Status dot pulses green when RUNNING
- Connection status shown in footer

### Screenshot Reference

```
┌─────────────────────────────────┐
│  AIS Production    🟢 Running   │
├─────────────────────────────────┤
│         Pieces Today            │
│            247                  │
│      Last count: 2:34:15 PM     │
├────────────────┬────────────────┤
│  Last Travel   │    Status      │
│     12.3s      │   RUNNING      │
├────────────────┴────────────────┤
│  Run Time: 4h 23m               │
│  Break Time: 45m                │
├─────────────────────────────────┤
│  [Last Count Photo]             │
├─────────────────────────────────┤
│  Recent Counts                  │
│  2:34:15 PM    Travel: 12.3s    │
│  2:33:02 PM    Travel: 11.8s    │
└─────────────────────────────────┘
```

---

## 2. Day Detail (`day.html`)

**Purpose**: Detailed view of a specific day's production with session timeline

**URL**: `/day.html?date=YYYY-MM-DD`

### Features

| Feature | Description |
|---------|-------------|
| **Date Navigation** | Prev/Next day arrows |
| **Daily Totals** | Pieces, run time, break time |
| **Session Timeline** | Visual run/break sessions with proportional heights |
| **Active Session** | Current session shown with pulsing animation |

### Session Timeline

Each session card shows:
- **RUN sessions**: Duration, piece count, avg cycle time
- **BREAK sessions**: Duration, start/end times

### URL Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `date` | No | Date in YYYY-MM-DD format (defaults to today) |

### Visual Design

- Session bar heights proportional to duration (1 hour = 100px)
- Minimum height of 40px for visibility
- Green = RUN, Yellow = BREAK
- Active sessions animate with pulse effect

---

## 3. History (`history.html`)

**Purpose**: Browse last 30 days of production data

**URL**: `/history.html`

### Features

| Feature | Description |
|---------|-------------|
| **Daily Cards** | Each day as clickable card |
| **Production Count** | Prominent piece count display |
| **Efficiency Bar** | Visual run/break ratio |
| **Time Breakdown** | Run and break time shown |

### Card Layout

```
┌─────────────────────────────────┐
│  Mon, Jan 13           247     │
│  2026-01-13           pieces   │
│  ▓▓▓▓▓▓▓▓▓▓░░░░  (run bar)    │
│  Run: 6h 30m    Break: 1h 15m  │
└─────────────────────────────────┘
```

### Interaction

- Tap any card to navigate to Day Detail
- Scrollable list for all 30 days
- Sorted by date (newest first)

---

## 4. Summary (`summary.html`)

**Purpose**: Weekly performance statistics and trends

**URL**: `/summary.html`

### Features

#### Today's Stats
| Metric | Description |
|--------|-------------|
| Pieces | Total count today |
| Run Time | Accumulated run duration |
| Break Time | Accumulated break duration |
| Efficiency | Run time / Total time % |
| Pcs/Hour | Pieces per hour of run time |
| Avg Cycle | Average seconds per piece |

#### Last 7 Days Stats
| Metric | Description |
|--------|-------------|
| Total Pieces | Sum of all pieces |
| Total Run | Combined run time |
| Total Break | Combined break time |
| Efficiency | Overall efficiency % |
| Avg/Day | Average daily production |
| Avg Cycle | Average cycle time |

#### Charts
- **Daily Production**: Bar chart showing 7-day piece counts
- **Efficiency Trend**: Daily efficiency percentages

### Visual Indicators

- Green efficiency: ≥70%
- Yellow efficiency: 50-69%
- Red efficiency: <50%

---

## 5. Review (`review.html`)

**Purpose**: Validate and correct potentially incorrect counts

**URL**: `/review.html?date=YYYY-MM-DD&filter=flagged`

### Features

| Feature | Description |
|---------|-------------|
| **Date Filter** | Select date to review |
| **Type Filter** | Flagged / Low Confidence / All |
| **Count Cards** | Detailed detection information |
| **Photo View** | Count photo with fullscreen |
| **Actions** | Mark as False Positive or Correct |

### URL Parameters

| Parameter | Default | Options |
|-----------|---------|---------|
| `date` | Today | Any date YYYY-MM-DD |
| `filter` | `flagged` | `flagged`, `low`, `all` |

### Count Card Information

```
┌─────────────────────────────────┐
│  2:34:15 PM   92% HIGH          │
│  Travel: 12.3s                  │
├─────────────────────────────────┤
│  L1: 45 frames, 12340 px        │
│  L2: 42 frames, 11890 px        │
│  L3: 38 frames, 10234 px        │
├─────────────────────────────────┤
│  [Count Photo]                  │
├─────────────────────────────────┤
│  [False Positive]  [Correct]    │
└─────────────────────────────────┘
```

### Detection Details Explained

| Field | Description |
|-------|-------------|
| **L1/L2/L3 Frames** | Number of frames hot material was detected on each line |
| **L1/L2/L3 Pixels** | Total pixel count on each detection line |
| **Confidence** | Algorithm confidence (HIGH ≥80%, MED 60-79%, LOW <60%) |
| **Flagged** | Auto-flagged by system for review |

### Review Actions

| Action | Effect |
|--------|--------|
| **False Positive** | Marks as incorrect, sets `flagged: true`, `reviewed: true` |
| **Correct** | Validates count, sets `flagged: false`, `reviewed: true` |

### How to Review

1. Check the photo - is there visible hot material crossing the lines?
2. Compare L1/L2/L3 frame counts - should be sequential
3. Check travel time - typical is 8-15 seconds
4. Mark accordingly

---

## Common Components

### Status Indicator

Color-coded status dot appears in navigation:

| Status | Color | Animation |
|--------|-------|-----------|
| RUNNING | Green | Pulsing |
| BREAK | Yellow | Static |
| OFFLINE | Red | Static |

### Footer

Fixed footer on all pages showing:
- Camera identifier (CAM-1 Furnace)
- Version number (AIS v1.0)

### Loading States

All pages show loading spinners while fetching data:
```
⟳ Loading...
```

### Error States

Connection errors displayed as:
```
┌─────────────────────────────────┐
│  ⚠️ Connection error - retrying │
└─────────────────────────────────┘
```

---

## Mobile Optimization

All pages are optimized for mobile:
- Touch-friendly tap targets (min 44px)
- Horizontal scrolling navigation
- Full-width cards
- Large readable text
- Fixed footer always visible
