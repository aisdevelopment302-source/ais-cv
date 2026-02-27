#!/usr/bin/env python3
"""
Fix Sessions Script
===================
Fixes past session data by reconstructing from counts collection.

For each session with end=null or duration_minutes=0:
1. Find all counts that fall within the session's time range
2. Set end time based on last count in session
3. Calculate duration_minutes
4. Calculate average_speed from travel_times
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

IST = ZoneInfo("Asia/Kolkata")

# Initialize Firebase
PROJECT_ROOT = Path(__file__).parent.parent
cred = credentials.Certificate(str(PROJECT_ROOT / "config" / "firebase-service-account.json"))

try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

db = firestore.client()

def get_all_sessions():
    """Get all sessions ordered by start time."""
    sessions = db.collection('sessions').order_by('start').get()
    return [(doc.id, doc.to_dict()) for doc in sessions]

def get_counts_in_range(start_time, end_time):
    """Get all counts between start and end time."""
    counts = db.collection('counts') \
        .where('timestamp', '>=', start_time) \
        .where('timestamp', '<=', end_time) \
        .order_by('timestamp') \
        .get()
    return [doc.to_dict() for doc in counts]

def fix_sessions():
    """Fix all sessions with missing end/duration data."""
    
    # Get all sessions sorted by start time
    sessions = get_all_sessions()
    print(f"Found {len(sessions)} total sessions")
    
    # Filter sessions that need fixing (end=null or duration=0)
    sessions_to_fix = [(sid, data) for sid, data in sessions 
                       if data.get('end') is None or data.get('duration_minutes', 0) == 0]
    
    print(f"Sessions needing fix: {len(sessions_to_fix)}")
    
    if not sessions_to_fix:
        print("No sessions to fix!")
        return
    
    # Create a list of all session start times for determining end boundaries
    all_starts = [(data.get('start'), sid) for sid, data in sessions]
    all_starts.sort(key=lambda x: x[0] if x[0] else datetime.min.replace(tzinfo=IST))
    
    fixed_count = 0
    
    for session_id, session_data in sessions_to_fix:
        session_type = session_data.get('type', 'UNKNOWN')
        start_time = session_data.get('start')
        current_count = session_data.get('count', 0)
        
        if not start_time:
            print(f"  Skipping {session_id} - no start time")
            continue
        
        # Find the next session's start time to bound our search
        next_start = None
        for i, (s_time, s_id) in enumerate(all_starts):
            if s_id == session_id and i + 1 < len(all_starts):
                next_start = all_starts[i + 1][0]
                break
        
        # If no next session, use start + 10 minutes as max bound for search
        if next_start is None:
            search_end = start_time + timedelta(minutes=30)
        else:
            search_end = next_start
        
        # Get counts in this session's range
        counts = get_counts_in_range(start_time, search_end)
        
        if session_type == 'RUN':
            if not counts:
                # No counts found - use 5 second duration as minimum
                end_time = start_time + timedelta(seconds=5)
                travel_times = []
                actual_count = current_count  # Keep existing count
            else:
                # End time is last count timestamp
                end_time = counts[-1]['timestamp']
                travel_times = [c.get('travel_time', 0) for c in counts if c.get('travel_time')]
                actual_count = len(counts)
            
            # Calculate duration
            duration_minutes = (end_time - start_time).total_seconds() / 60
            
            # Calculate average speed
            avg_speed = sum(travel_times) / len(travel_times) if travel_times else None
            
            # Prepare update
            update_data = {
                'end': end_time,
                'duration_minutes': round(duration_minutes, 2),
                'count': max(actual_count, current_count)  # Use higher of calculated or stored
            }
            
            if avg_speed is not None:
                update_data['average_speed'] = round(avg_speed, 3)
            
            print(f"  Fixing RUN {session_id[:20]}:")
            print(f"    start: {start_time}")
            print(f"    end: {end_time}")
            print(f"    duration: {duration_minutes:.2f} min")
            print(f"    count: {update_data['count']} (from {len(counts)} counts found)")
            if avg_speed:
                print(f"    avg_speed: {avg_speed:.3f}s")
        
        else:  # BREAK session
            # For BREAK, end time is the next session start or start + break_threshold
            if next_start:
                end_time = next_start
            else:
                end_time = start_time + timedelta(minutes=5)  # Default 5 min break
            
            duration_minutes = (end_time - start_time).total_seconds() / 60
            
            update_data = {
                'end': end_time,
                'duration_minutes': round(duration_minutes, 2),
                'count': 0
            }
            
            print(f"  Fixing BREAK {session_id[:20]}:")
            print(f"    start: {start_time}")
            print(f"    end: {end_time}")
            print(f"    duration: {duration_minutes:.2f} min")
        
        # Update in Firebase
        db.collection('sessions').document(session_id).update(update_data)
        fixed_count += 1
        print(f"    ✓ Updated!")
    
    print(f"\n=== COMPLETE ===")
    print(f"Fixed {fixed_count} sessions")

if __name__ == "__main__":
    print("=== SESSION FIX SCRIPT ===\n")
    fix_sessions()
