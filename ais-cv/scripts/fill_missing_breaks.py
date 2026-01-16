#!/usr/bin/env python3
"""
Fill Missing BREAK Sessions
============================
Due to service restarts, there are gaps between RUN sessions where BREAK 
sessions should exist but don't.

This script:
1. Finds gaps > 5 minutes between RUN sessions
2. Creates BREAK sessions to fill those gaps
3. BREAK start = previous RUN end, BREAK end = next RUN start

Usage:
    python fill_missing_breaks.py              # Dry run
    python fill_missing_breaks.py --execute   # Actually create
    python fill_missing_breaks.py --date 2026-01-14  # Specific date
"""

import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import firebase_admin
from firebase_admin import credentials, firestore

IST = ZoneInfo("Asia/Kolkata")
MIN_BREAK_DURATION_SECONDS = 300  # 5 minutes - gaps shorter than this are not breaks


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
    """Get all sessions for a specific date, sorted by start time."""
    sessions = db.collection('sessions').where('date', '==', date_str).get()
    
    result = []
    for doc in sessions:
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Parse timestamps
        start = data.get('start')
        end = data.get('end')
        if hasattr(start, 'astimezone'):
            data['_start'] = start.astimezone(IST)
        if end and hasattr(end, 'astimezone'):
            data['_end'] = end.astimezone(IST)
        
        result.append(data)
    
    # Sort by start time
    result.sort(key=lambda s: s.get('_start', datetime.min.replace(tzinfo=IST)))
    return result


def find_missing_breaks(sessions):
    """Find gaps between sessions where BREAK sessions should exist."""
    missing_breaks = []
    
    for i in range(len(sessions) - 1):
        current = sessions[i]
        next_session = sessions[i + 1]
        
        current_end = current.get('_end')
        next_start = next_session.get('_start')
        
        if not current_end or not next_start:
            continue
        
        # Calculate gap
        gap_seconds = (next_start - current_end).total_seconds()
        
        # If gap is > 5 minutes and both sessions are RUN, we need a BREAK
        if gap_seconds >= MIN_BREAK_DURATION_SECONDS:
            # Check if there's already a BREAK session in this gap
            # (there shouldn't be since we're iterating in order)
            if current.get('type') == 'RUN' and next_session.get('type') == 'RUN':
                missing_breaks.append({
                    'start': current_end,
                    'end': next_start,
                    'duration_minutes': gap_seconds / 60,
                    'date': current.get('date'),
                    'hour': current_end.strftime('%H'),
                    'after_session': current['id'],
                    'before_session': next_session['id']
                })
    
    return missing_breaks


def create_break_session(db, break_info, execute=False):
    """Create a BREAK session in Firebase."""
    session_id = str(uuid.uuid4())[:20]
    
    session_data = {
        'type': 'BREAK',
        'start': break_info['start'],
        'end': break_info['end'],
        'date': break_info['date'],
        'hour': break_info['hour'],
        'duration_minutes': round(break_info['duration_minutes'], 2),
        'count': 0,
        'filled_gap': True  # Mark as auto-generated
    }
    
    print(f"\n  Creating BREAK session:")
    print(f"    Start: {break_info['start'].strftime('%H:%M:%S')}")
    print(f"    End: {break_info['end'].strftime('%H:%M:%S')}")
    print(f"    Duration: {break_info['duration_minutes']:.1f} min")
    
    if execute:
        db.collection('sessions').document(session_id).set(session_data)
        print(f"    Created: {session_id}")
    
    return session_id


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fill missing BREAK sessions')
    parser.add_argument('--execute', action='store_true', help='Actually create (default is dry run)')
    parser.add_argument('--date', type=str, help='Specific date (YYYY-MM-DD). Default: today')
    parser.add_argument('--all-dates', action='store_true', help='Process all dates')
    args = parser.parse_args()
    
    print("=" * 60)
    print("FILL MISSING BREAK SESSIONS")
    print("=" * 60)
    
    if not args.execute:
        print("\n*** DRY RUN - No changes will be made ***\n")
    
    db = init_firebase()
    if not db:
        return
    
    # Determine dates to process
    if args.all_dates:
        all_sessions = db.collection('sessions').get()
        dates = set()
        for doc in all_sessions:
            data = doc.to_dict()
            if data.get('date'):
                dates.add(data['date'])
        dates = sorted(dates)
    elif args.date:
        dates = [args.date]
    else:
        dates = [datetime.now(IST).date().isoformat()]
    
    total_created = 0
    total_break_minutes = 0
    
    for date_str in dates:
        print(f"\n--- Processing {date_str} ---")
        
        sessions = get_sessions_for_date(db, date_str)
        print(f"Found {len(sessions)} sessions")
        
        missing_breaks = find_missing_breaks(sessions)
        
        if not missing_breaks:
            print("No missing BREAK sessions")
            continue
        
        print(f"Found {len(missing_breaks)} missing BREAK sessions")
        
        for break_info in missing_breaks:
            create_break_session(db, break_info, execute=args.execute)
            total_created += 1
            total_break_minutes += break_info['duration_minutes']
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {total_created} BREAK sessions to create")
    print(f"         {total_break_minutes:.1f} total break minutes")
    if not args.execute and total_created > 0:
        print("\n*** Run with --execute to create them ***")
    print("=" * 60)


if __name__ == "__main__":
    main()
