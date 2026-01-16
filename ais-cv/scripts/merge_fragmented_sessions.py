#!/usr/bin/env python3
"""
Merge Fragmented Sessions
=========================
This script merges fragmented RUN sessions that were created by service restarts.

Logic:
- Find consecutive RUN sessions that are within 5 minutes of each other
- Merge them into a single session with:
  - start = first session's start
  - end = last session's end
  - count = sum of all counts
  - average_speed = weighted average (or recalculated from counts collection)
  - duration_minutes = recalculated from start to end

Usage:
    python merge_fragmented_sessions.py              # Dry run (preview)
    python merge_fragmented_sessions.py --execute   # Actually merge
    python merge_fragmented_sessions.py --date 2026-01-14  # Specific date
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import firebase_admin
from firebase_admin import credentials, firestore

IST = ZoneInfo("Asia/Kolkata")
MERGE_THRESHOLD_SECONDS = 300  # 5 minutes - sessions closer than this get merged


def init_firebase():
    """Initialize Firebase."""
    service_account_path = PROJECT_ROOT / "config" / "firebase-service-account.json"
    
    if not service_account_path.exists():
        print(f"ERROR: Service account file not found: {service_account_path}")
        return None
    
    try:
        cred = credentials.Certificate(str(service_account_path))
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"ERROR: Failed to initialize Firebase: {e}")
        return None


def get_sessions_for_date(db, date_str: str):
    """Get all sessions for a specific date, ordered by start time."""
    # Get sessions without composite index requirement
    sessions = (db.collection('sessions')
               .where('date', '==', date_str)
               .get())
    
    result = []
    for doc in sessions:
        data = doc.to_dict()
        data['id'] = doc.id
        result.append(data)
    
    # Sort by start time in Python
    def get_start(s):
        start = s.get('start')
        if hasattr(start, 'timestamp'):
            return start.timestamp()
        return 0
    
    result.sort(key=get_start)
    return result


def get_travel_times_for_period(db, start_time, end_time):
    """Get travel times from counts collection for a time period."""
    counts = (db.collection('counts')
             .where('timestamp', '>=', start_time)
             .where('timestamp', '<=', end_time)
             .get())
    
    travel_times = []
    for doc in counts:
        data = doc.to_dict()
        tt = data.get('travel_time', 0)
        if tt > 0:
            travel_times.append(tt)
    
    return travel_times


def find_merge_groups(sessions):
    """
    Find groups of sessions that should be merged.
    Returns list of groups, where each group is a list of sessions to merge.
    """
    if not sessions:
        return []
    
    groups = []
    current_group = []
    
    for session in sessions:
        # Only merge RUN sessions
        if session.get('type') != 'RUN':
            # Save current group if any
            if len(current_group) > 1:
                groups.append(current_group)
            current_group = []
            continue
        
        # Get session times
        start = session.get('start')
        end = session.get('end')
        
        # Handle Firestore timestamps
        if hasattr(start, 'astimezone'):
            start = start.astimezone(IST)
        if end and hasattr(end, 'astimezone'):
            end = end.astimezone(IST)
        
        session['_start'] = start
        session['_end'] = end
        
        if not current_group:
            # Start new group
            current_group = [session]
        else:
            # Check if this session is close enough to previous
            prev_session = current_group[-1]
            prev_end = prev_session.get('_end')
            
            if prev_end is None:
                # Previous session has no end - can't merge
                if len(current_group) > 1:
                    groups.append(current_group)
                current_group = [session]
            else:
                gap_seconds = (start - prev_end).total_seconds()
                
                if gap_seconds <= MERGE_THRESHOLD_SECONDS:
                    # Close enough - add to group
                    current_group.append(session)
                else:
                    # Too far apart - save current group and start new one
                    if len(current_group) > 1:
                        groups.append(current_group)
                    current_group = [session]
    
    # Don't forget the last group
    if len(current_group) > 1:
        groups.append(current_group)
    
    return groups


def merge_sessions(db, group, execute=False):
    """
    Merge a group of sessions into one.
    Returns the merged session data.
    """
    if len(group) < 2:
        return None
    
    first = group[0]
    last = group[-1]
    
    # Calculate merged values
    start_time = first['_start']
    end_time = last['_end']
    total_count = sum(s.get('count', 0) for s in group)
    
    # Calculate duration
    if end_time:
        duration_minutes = (end_time - start_time).total_seconds() / 60
    else:
        duration_minutes = 0
    
    # Get travel times from counts collection for accurate average_speed
    travel_times = []
    if end_time:
        travel_times = get_travel_times_for_period(db, start_time, end_time)
    
    avg_speed = None
    if travel_times:
        avg_speed = sum(travel_times) / len(travel_times)
    
    merged = {
        'type': 'RUN',
        'start': start_time,
        'end': end_time,
        'date': first.get('date'),
        'hour': first.get('hour'),
        'count': total_count,
        'duration_minutes': round(duration_minutes, 2),
        'average_speed': round(avg_speed, 3) if avg_speed else None,
        'merged_from': [s['id'] for s in group]
    }
    
    print(f"\n  Merging {len(group)} sessions:")
    for s in group:
        print(f"    - {s['id']}: {s.get('count', 0)} pieces, {s.get('duration_minutes', 0):.1f}min")
    print(f"  Into: {total_count} pieces, {duration_minutes:.1f}min, avg_speed={avg_speed:.2f}s" if avg_speed else f"  Into: {total_count} pieces, {duration_minutes:.1f}min")
    
    if execute:
        # Keep the first session and update it with merged data
        keep_id = first['id']
        delete_ids = [s['id'] for s in group[1:]]
        
        # Update the first session
        update_data = {
            'end': end_time,
            'count': total_count,
            'duration_minutes': round(duration_minutes, 2),
        }
        if avg_speed:
            update_data['average_speed'] = round(avg_speed, 3)
        
        db.collection('sessions').document(keep_id).update(update_data)
        print(f"  Updated session {keep_id}")
        
        # Delete the other sessions
        for del_id in delete_ids:
            db.collection('sessions').document(del_id).delete()
            print(f"  Deleted session {del_id}")
    
    return merged


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Merge fragmented sessions')
    parser.add_argument('--execute', action='store_true', help='Actually perform the merge (default is dry run)')
    parser.add_argument('--date', type=str, help='Specific date to process (YYYY-MM-DD). Default: today')
    parser.add_argument('--all-dates', action='store_true', help='Process all dates with sessions')
    args = parser.parse_args()
    
    print("=" * 60)
    print("MERGE FRAGMENTED SESSIONS")
    print("=" * 60)
    
    if not args.execute:
        print("\n*** DRY RUN - No changes will be made ***")
        print("*** Run with --execute to actually merge ***\n")
    
    db = init_firebase()
    if not db:
        return
    
    # Determine which dates to process
    if args.all_dates:
        # Get all unique dates from sessions
        all_sessions = db.collection('sessions').get()
        dates = set()
        for doc in all_sessions:
            data = doc.to_dict()
            if data.get('date'):
                dates.add(data['date'])
        dates = sorted(dates)
        print(f"Found {len(dates)} dates with sessions")
    elif args.date:
        dates = [args.date]
    else:
        dates = [datetime.now(IST).date().isoformat()]
    
    total_merged = 0
    total_deleted = 0
    
    for date_str in dates:
        print(f"\n--- Processing {date_str} ---")
        
        sessions = get_sessions_for_date(db, date_str)
        print(f"Found {len(sessions)} sessions")
        
        # Find groups to merge
        merge_groups = find_merge_groups(sessions)
        
        if not merge_groups:
            print("No fragmented sessions to merge")
            continue
        
        print(f"Found {len(merge_groups)} groups to merge")
        
        for group in merge_groups:
            merged = merge_sessions(db, group, execute=args.execute)
            if merged:
                total_merged += 1
                total_deleted += len(group) - 1
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {total_merged} merges, {total_deleted} sessions deleted")
    if not args.execute:
        print("\n*** This was a DRY RUN - no changes were made ***")
        print("*** Run with --execute to actually merge ***")
    print("=" * 60)


if __name__ == "__main__":
    main()
