# Deployment Guide

## Overview

The AIS Dashboard can be deployed using **two different strategies** depending on requirements:

| Strategy | Best For | Complexity |
|----------|----------|------------|
| **Static Hosting** | Production, shop floor | Simple |
| **Next.js Build** | Development, SSR needs | Moderate |

---

## Quick Start (Development)

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Open in browser
open http://localhost:3000
```

---

## Option 1: Static Hosting (Recommended for Production)

### Why Static Hosting?

- No server-side runtime required
- Instant global deployment via CDN
- Zero build step for HTML files
- Lower cost, higher availability

### Deploy to Any Static Host

The `public/` folder contains production-ready HTML files:

```
public/
├── index.html      # Live dashboard
├── day.html        # Day detail
├── history.html    # 30-day history
├── review.html     # Count review
├── summary.html    # Weekly summary
└── js/             # Shared utilities
```

### Option 1A: Firebase Hosting

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Login to Firebase
firebase login

# Initialize hosting (one-time)
firebase init hosting
# Select: ais-production-e013c
# Public directory: public
# Single-page app: No

# Deploy
firebase deploy --only hosting
```

**Result**: Dashboard available at `https://ais-production-e013c.web.app`

### Option 1B: Nginx on Local Server

```nginx
# /etc/nginx/sites-available/ais-dashboard
server {
    listen 80;
    server_name dashboard.local;
    
    root /var/www/ais-dashboard/public;
    index index.html;
    
    location / {
        try_files $uri $uri/ =404;
    }
}
```

```bash
# Copy files
sudo cp -r public/* /var/www/ais-dashboard/public/

# Enable site
sudo ln -s /etc/nginx/sites-available/ais-dashboard /etc/nginx/sites-enabled/

# Reload Nginx
sudo nginx -s reload
```

### Option 1C: Python Simple Server

For quick local testing:

```bash
cd public
python3 -m http.server 8080
```

**Result**: Dashboard at `http://localhost:8080`

---

## Option 2: Next.js Build

### When to Use Next.js

- Need server-side rendering
- Using React components beyond current scope
- Want unified build pipeline
- Need API routes

### Build Process

```bash
# Install dependencies
npm install

# Production build
npm run build

# Start production server
npm start
```

### Build Output

```
.next/
├── server/         # SSR pages
├── static/         # Static assets
└── cache/          # Build cache
```

### Deploy Next.js to Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel

# Production deployment
vercel --prod
```

### Deploy Next.js to Docker

```dockerfile
# Dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
```

```bash
# Build image
docker build -t ais-dashboard .

# Run container
docker run -p 3000:3000 ais-dashboard
```

---

## Environment Configuration

### Photo API URL

The photo API endpoint is hardcoded for local network:

```javascript
// In public/*.html files
const PHOTO_API = 'http://192.168.1.23:5001';
```

**To change**: Update the constant in each HTML file or move to a config file.

### Firebase Configuration

Firebase config is embedded in each page. To change projects:

1. Update `firebaseConfig` object in each file
2. Or create `public/js/firebase-config.js` shared module

---

## Production Checklist

### Before Deployment

- [ ] Test all pages load correctly
- [ ] Verify Firebase connection works
- [ ] Check photo API accessibility (if local network)
- [ ] Test on mobile devices
- [ ] Verify date/time formatting

### Security Review

- [ ] Firebase security rules configured
- [ ] No sensitive data in client code
- [ ] HTTPS enabled (if public deployment)

### Performance

- [ ] Tailwind CSS loads from CDN
- [ ] Firebase SDK loads from CDN
- [ ] Images optimized (if any added)

---

## Hosting Comparison

| Platform | Cost | SSL | Custom Domain | CDN |
|----------|------|-----|---------------|-----|
| Firebase Hosting | Free tier | ✅ | ✅ | ✅ |
| Vercel | Free tier | ✅ | ✅ | ✅ |
| Netlify | Free tier | ✅ | ✅ | ✅ |
| GitHub Pages | Free | ✅ | ✅ | ✅ |
| Local Nginx | Free | Manual | N/A | No |

---

## Local Network Deployment

For shop floor access without internet:

### Raspberry Pi as Host

```bash
# On Raspberry Pi
cd ~/ais-dashboard

# Install Python server
sudo apt install python3

# Serve dashboard
cd public
python3 -m http.server 80

# Access from any device on network
# http://192.168.1.23/
```

### Combined with Photo API

If running on same Pi as CV module:

```bash
# Photo API already running on :5001
# Dashboard can run on :80

# Using supervisor to manage both
sudo apt install supervisor

# /etc/supervisor/conf.d/ais-dashboard.conf
[program:ais-dashboard]
command=python3 -m http.server 80
directory=/home/pi/ais-dashboard/public
autostart=true
autorestart=true
```

---

## Monitoring & Logs

### Firebase Hosting

```bash
# View deployment history
firebase hosting:channel:list

# View logs
firebase functions:log  # If using functions
```

### Nginx Logs

```bash
# Access logs
tail -f /var/log/nginx/access.log

# Error logs
tail -f /var/log/nginx/error.log
```

---

## Updating the Dashboard

### Static Files Update

```bash
# Copy new files to server
scp -r public/* user@server:/var/www/ais-dashboard/public/

# Or with Firebase
firebase deploy --only hosting
```

### Next.js Update

```bash
# Pull latest code
git pull

# Install any new dependencies
npm install

# Rebuild
npm run build

# Restart server
pm2 restart ais-dashboard  # If using PM2
```

---

## Troubleshooting

### Dashboard Shows "Connecting..."

- Check Firebase project is accessible
- Verify internet connection
- Check browser console for errors

### Photos Not Loading

- Photos only work on local network (192.168.1.23)
- Check Photo API is running on Raspberry Pi
- Verify network connectivity to Pi

### Firestore Permission Errors

```
Error: Missing or insufficient permissions
```

- Check Firestore security rules
- Verify composite indexes exist
- Check Firebase Console for rule errors

### Build Failures (Next.js)

```bash
# Clear cache and rebuild
rm -rf .next node_modules
npm install
npm run build
```
