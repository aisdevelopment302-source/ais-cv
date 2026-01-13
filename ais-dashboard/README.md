# AIS Dashboard

Real-time production monitoring dashboard for the AIS (Automatic Inspection System) steel mill plate scrap counter.

## Overview

The AIS Dashboard provides a web-based interface for monitoring furnace camera production counts in real-time. It reads data from Firebase Firestore and displays:

- **Live count** of pieces processed today
- **Run/Break status** with visual indicators
- **Historical data** for the past 30 days
- **Session timelines** showing run/break periods
- **Performance summaries** with efficiency metrics
- **Review interface** for validating flagged counts

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.x | React framework |
| React | 18.x | UI components |
| Firebase | 10.7.1 | Firestore real-time database |
| Tailwind CSS | 3.4.x | Styling |

## Quick Start

### Prerequisites

- Node.js 18+ 
- npm or yarn
- Access to Firebase project

### Installation

```bash
# Clone the repository (if not already in AIS monorepo)
cd ais-dashboard

# Install dependencies
npm install

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

### Production (Static Files)

The `public/` folder contains production-ready static HTML files that can be served directly:

```bash
# Serve static files with any web server
cd public
python3 -m http.server 8080
```

## Project Structure

```
ais-dashboard/
├── pages/                    # Next.js React pages
│   ├── _app.js              # App wrapper
│   └── index.js             # React dashboard
├── public/                   # Static HTML pages (production)
│   ├── index.html           # Live dashboard
│   ├── day.html             # Day detail view
│   ├── history.html         # 30-day history
│   ├── review.html          # Count validation
│   └── summary.html         # Weekly stats
├── lib/
│   └── firebase.js          # Firebase configuration
├── docs/                     # Documentation
│   ├── ARCHITECTURE.md      # System design
│   ├── PAGES.md             # Page documentation
│   ├── FIREBASE.md          # Database integration
│   └── DEPLOYMENT.md        # Deployment guide
└── package.json
```

## Dashboard Views

| View | URL | Description |
|------|-----|-------------|
| **Live** | `/index.html` | Real-time piece counter and status |
| **Day** | `/day.html?date=YYYY-MM-DD` | Session timeline for a specific day |
| **History** | `/history.html` | Last 30 days of production data |
| **Summary** | `/summary.html` | Weekly performance metrics |
| **Review** | `/review.html` | Validate flagged/low-confidence counts |

## Firebase Collections

The dashboard reads from these Firestore collections:

| Collection | Description |
|------------|-------------|
| `live/furnace` | Real-time status and today's count |
| `counts` | Individual count events with metadata |
| `daily` | Daily aggregated statistics |
| `sessions` | Run/break session records |

See [docs/FIREBASE.md](docs/FIREBASE.md) for detailed schema information.

## Photo Integration

Count photos are served from the Raspberry Pi's local Photo API:

```
http://192.168.1.23:5001/api/photos/latest
```

> Note: Photos are only accessible when connected to the local network.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm start` | Start production server |
| `npm run lint` | Run ESLint |

## Deployment

### Static Hosting (Recommended)

Deploy the `public/` folder to any static host:

- Firebase Hosting
- Vercel
- Netlify
- GitHub Pages
- Local Nginx

```bash
# Firebase Hosting example
firebase deploy --only hosting
```

### Next.js Deployment

For SSR capabilities:

```bash
npm run build
npm start
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment options.

## Configuration

### Firebase Project

The dashboard is configured for the `ais-production-e013c` Firebase project. Configuration is embedded in the source files.

### Photo API

Update the `PHOTO_API` constant in HTML files to change the photo server address:

```javascript
const PHOTO_API = 'http://192.168.1.23:5001';
```

## Related Projects

| Project | Description |
|---------|-------------|
| `ais-cv` | Computer vision module (Raspberry Pi) |
| `ais-photo-api` | Photo serving API |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and data flow
- [Pages](docs/PAGES.md) - Detailed page documentation
- [Firebase](docs/FIREBASE.md) - Database schema and queries
- [Deployment](docs/DEPLOYMENT.md) - Build and deployment guide

## License

Proprietary - Internal use only
