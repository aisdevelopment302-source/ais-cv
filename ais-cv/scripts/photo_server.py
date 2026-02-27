#!/usr/bin/env python3
"""
AIS Photo API Server
====================
Serves count photos from the Pi over HTTP.

Endpoints:
  GET /api/photos/latest     - Latest count photo
  GET /api/photos/<filename> - Specific photo
  GET /api/photos/list       - List recent photos

Run: python photo_server.py
Access: http://192.168.1.23:5001/api/photos/latest
"""

from flask import Flask, send_file, jsonify, abort
from flask_cors import CORS
from pathlib import Path
import os

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from dashboard

# Photo directory
PHOTO_DIR = Path(__file__).parent.parent / 'data' / 'photos'


@app.route('/api/photos/latest')
def get_latest_photo():
    """Get the most recent count photo."""
    if not PHOTO_DIR.exists():
        abort(404, description="No photos directory")
    
    # Get all jpg files sorted by modification time (newest first)
    photos = sorted(
        PHOTO_DIR.glob('count_*.jpg'),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    if not photos:
        abort(404, description="No photos found")
    
    return send_file(
        photos[0],
        mimetype='image/jpeg',
        as_attachment=False,
        download_name=photos[0].name
    )


@app.route('/api/photos/list')
def list_photos():
    """List recent photos (last 20)."""
    if not PHOTO_DIR.exists():
        return jsonify({'photos': []})
    
    photos = sorted(
        PHOTO_DIR.glob('count_*.jpg'),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )[:20]
    
    photo_list = []
    for p in photos:
        stat = p.stat()
        photo_list.append({
            'filename': p.name,
            'size': stat.st_size,
            'timestamp': stat.st_mtime,
            'url': f'/api/photos/{p.name}'
        })
    
    return jsonify({'photos': photo_list})


@app.route('/api/photos/<filename>')
def get_photo(filename):
    """Get a specific photo by filename."""
    # Security: only allow count_*.jpg files
    if not filename.startswith('count_') or not filename.endswith('.jpg'):
        abort(400, description="Invalid filename")
    
    photo_path = PHOTO_DIR / filename
    
    if not photo_path.exists():
        abort(404, description="Photo not found")
    
    return send_file(
        photo_path,
        mimetype='image/jpeg',
        as_attachment=False
    )


@app.route('/api/status')
def get_status():
    """Quick status check."""
    photo_count = len(list(PHOTO_DIR.glob('count_*.jpg'))) if PHOTO_DIR.exists() else 0
    return jsonify({
        'status': 'ok',
        'photo_count': photo_count,
        'photo_dir': str(PHOTO_DIR)
    })


@app.route('/')
def index():
    """Root endpoint - redirect to latest photo."""
    return '''
    <html>
    <head><title>AIS Photo API</title></head>
    <body style="font-family: sans-serif; padding: 20px;">
        <h1>AIS Photo API</h1>
        <ul>
            <li><a href="/api/photos/latest">Latest Photo</a></li>
            <li><a href="/api/photos/list">Photo List (JSON)</a></li>
            <li><a href="/api/status">Status</a></li>
        </ul>
    </body>
    </html>
    '''


if __name__ == '__main__':
    print(f"Photo directory: {PHOTO_DIR}")
    print("Starting AIS Photo API on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
