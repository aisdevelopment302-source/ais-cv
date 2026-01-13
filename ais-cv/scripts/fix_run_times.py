#!/usr/bin/env python3
"""
Recalculate and fix run/break times in Firebase based on counts data.

This script:
1. Reads all counts for a given date
2. Calculates run time between consecutive counts (capped at break_threshold)
3. Updates daily and hourly documents with correct run/break times
4. Optionally rebuilds sessions from scratch

Usage:
    python scripts/fix_run_times.py                    # Fix today
    python scripts/fix_run_times.py --date 2026-01-12  # Fix specific date
    python scripts/fix_run_times.py --date 2026-01-12 --rebuild-sessions  # Also rebuild sessions
    python scripts/fix_run_times.py --dry-run          # Preview without making changes
"""

import argparse
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

import firebase_admin
from firebase_admin import credentials, firestore

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# Configuration
BREAK_THRESHOLD_SECONDS = 120  # 2 minutes - same as session_manager default
SERVICE_ACCOUNT_PATH = PROJECT_ROOT / 'config' / 'firebase-service-account.json'


def init_firebase():
    """Initialize Firebase Admin SDK."""
    if not firebase_admin._apps:
        cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
        firebase_admin.initialize_app(cred)
    return firestore.client()


def get_counts_for_date(db, date_str: str) -> list:
    """Fetch all counts for a given date, sorted by timestamp."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    
    counts_ref = db.collection('counts')
    # Use filter keyword to avoid deprecation warning, and don't order_by to avoid index requirement
    query = counts_ref.where(filter=FieldFilter('date', '==', date_str))
    
    counts = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        counts.append(data)
    
    # Sort client-side by timestamp
    def get_timestamp(c):
        ts = c.get('timestamp')
        if ts is None:
            return 0
        # Firestore DatetimeWithNanoseconds
        if hasattr(ts, 'timestamp'):
            return ts.timestamp()
        if hasattr(ts, 'seconds'):
            return ts.seconds
        return 0
    
    counts.sort(key=get_timestamp)
    
    print(f"Found {len(counts)} counts for {date_str}")
    return counts


def timestamp_to_datetime(ts) -> datetime:
    """Convert Firestore timestamp to datetime (preserving original timezone)."""
    if ts is None:
        return None
    
    # DatetimeWithNanoseconds from Firestore - use as-is
    if hasattr(ts, 'timestamp'):
        # It's already a datetime-like object, just return it
        # Firestore stores these with proper timezone info
        return ts
    elif hasattr(ts, 'seconds'):
        # Old-style Firestore Timestamp with seconds attribute
        return datetime.fromtimestamp(ts.seconds, tz=timezone.utc)
    elif isinstance(ts, datetime):
        return ts
    
    return None


def calculate_run_times(counts: list, break_threshold: float = BREAK_THRESHOLD_SECONDS) -> dict:
    """
    Calculate run times from counts data.
    
    Returns dict with:
        - total_run_minutes: float
        - total_break_minutes: float  
        - hourly: {hour: {run_minutes, break_minutes, count}}
        - sessions: list of session dicts
    """
    if not counts:
        return {
            'total_run_minutes': 0,
            'total_break_minutes': 0,
            'hourly': {},
            'sessions': []
        }
    
    hourly = {}
    sessions = []
    total_run_minutes = 0
    total_break_minutes = 0
    
    # Track current session
    current_session = None
    last_count_time = None
    last_count_dt = None
    
    for i, count in enumerate(counts):
        ts = count.get('timestamp')
        count_dt = timestamp_to_datetime(ts)
        
        if count_dt is None:
            continue
            
        count_time = count_dt.timestamp()
        hour = count_dt.strftime('%H')
        date_str = count_dt.strftime('%Y-%m-%d')
        
        # Initialize hourly bucket
        if hour not in hourly:
            hourly[hour] = {'run_minutes': 0, 'break_minutes': 0, 'count': 0}
        
        hourly[hour]['count'] += 1
        
        if last_count_time is not None:
            elapsed_seconds = count_time - last_count_time
            
            if elapsed_seconds <= break_threshold:
                # This is run time
                run_minutes = elapsed_seconds / 60.0
                hourly[hour]['run_minutes'] += run_minutes
                total_run_minutes += run_minutes
                
                # Continue current RUN session
                if current_session and current_session['type'] == 'RUN':
                    current_session['end'] = count_dt
                    current_session['count'] += 1
                else:
                    # End BREAK session if exists
                    if current_session and current_session['type'] == 'BREAK':
                        current_session['end'] = count_dt
                        current_session['duration_minutes'] = (count_time - current_session['start_ts']) / 60.0
                        sessions.append(current_session)
                    
                    # Start new RUN session
                    current_session = {
                        'type': 'RUN',
                        'start': count_dt,
                        'start_ts': count_time,
                        'end': count_dt,
                        'count': 1,
                        'hour': hour,
                        'date': date_str
                    }
            else:
                # Gap was a break
                break_minutes = elapsed_seconds / 60.0
                total_break_minutes += break_minutes
                
                # Attribute break time to the hour it started
                prev_hour = last_count_dt.strftime('%H')
                if prev_hour not in hourly:
                    hourly[prev_hour] = {'run_minutes': 0, 'break_minutes': 0, 'count': 0}
                hourly[prev_hour]['break_minutes'] += break_minutes
                
                # End current RUN session
                if current_session and current_session['type'] == 'RUN':
                    current_session['end'] = last_count_dt
                    current_session['duration_minutes'] = (last_count_time - current_session['start_ts']) / 60.0
                    sessions.append(current_session)
                    
                    # Create BREAK session
                    break_session = {
                        'type': 'BREAK',
                        'start': last_count_dt,
                        'start_ts': last_count_time,
                        'end': count_dt,
                        'count': 0,
                        'hour': prev_hour,
                        'date': date_str,
                        'duration_minutes': break_minutes
                    }
                    sessions.append(break_session)
                
                # Start new RUN session
                current_session = {
                    'type': 'RUN',
                    'start': count_dt,
                    'start_ts': count_time,
                    'end': count_dt,
                    'count': 1,
                    'hour': hour,
                    'date': date_str
                }
        else:
            # First count - start RUN session
            current_session = {
                'type': 'RUN',
                'start': count_dt,
                'start_ts': count_time,
                'end': count_dt,
                'count': 1,
                'hour': hour,
                'date': date_str
            }
        
        last_count_time = count_time
        last_count_dt = count_dt
    
    # Close final session
    if current_session:
        if current_session['type'] == 'RUN':
            current_session['duration_minutes'] = (last_count_time - current_session['start_ts']) / 60.0
        sessions.append(current_session)
    
    return {
        'total_run_minutes': total_run_minutes,
        'total_break_minutes': total_break_minutes,
        'hourly': hourly,
        'sessions': sessions
    }


def update_firebase(db, date_str: str, results: dict, rebuild_sessions: bool = False, dry_run: bool = False):
    """Update Firebase with corrected data."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Updating Firebase for {date_str}:")
    print(f"  Total run time: {results['total_run_minutes']:.1f} minutes ({results['total_run_minutes']/60:.2f} hours)")
    print(f"  Total break time: {results['total_break_minutes']:.1f} minutes ({results['total_break_minutes']/60:.2f} hours)")
    print(f"  Hourly buckets: {len(results['hourly'])}")
    print(f"  Sessions: {len(results['sessions'])}")
    
    if dry_run:
        print("\n[DRY RUN] Would update:")
        print(f"  - daily/{date_str}")
        for hour in sorted(results['hourly'].keys()):
            h = results['hourly'][hour]
            print(f"  - hourly/{date_str}/hours/{hour}: count={h['count']}, run={h['run_minutes']:.1f}m, break={h['break_minutes']:.1f}m")
        if rebuild_sessions:
            print(f"  - Would delete existing sessions and create {len(results['sessions'])} new ones")
        return
    
    # Update daily document
    daily_ref = db.collection('daily').document(date_str)
    daily_doc = daily_ref.get()
    
    if daily_doc.exists:
        daily_ref.update({
            'total_run_minutes': results['total_run_minutes'],
            'total_break_minutes': results['total_break_minutes']
        })
        print(f"  ✓ Updated daily/{date_str}")
    else:
        print(f"  ⚠ daily/{date_str} does not exist, skipping")
    
    # Update hourly documents
    for hour, data in results['hourly'].items():
        hourly_ref = db.collection('hourly').document(date_str).collection('hours').document(hour)
        hourly_ref.set({
            'count': data['count'],
            'run_minutes': data['run_minutes'],
            'break_minutes': data['break_minutes']
        }, merge=True)
    print(f"  ✓ Updated {len(results['hourly'])} hourly documents")
    
    # Rebuild sessions if requested
    if rebuild_sessions:
        # Delete existing sessions for this date
        sessions_ref = db.collection('sessions')
        existing = sessions_ref.where(filter=FieldFilter('date', '==', date_str)).stream()
        deleted = 0
        for doc in existing:
            doc.reference.delete()
            deleted += 1
        print(f"  ✓ Deleted {deleted} existing sessions")
        
        # Create new sessions
        for session in results['sessions']:
            start_dt = session['start']
            end_dt = session['end']
            
            # Convert to standard Python datetime to avoid Firestore DatetimeWithNanoseconds issues
            # Keep the same time values - Firestore will store them correctly
            if start_dt is not None:
                # Create a standard datetime preserving the exact time
                start_for_db = datetime(
                    start_dt.year, start_dt.month, start_dt.day,
                    start_dt.hour, start_dt.minute, start_dt.second, start_dt.microsecond,
                    tzinfo=start_dt.tzinfo  # Preserve timezone info
                )
            else:
                start_for_db = None
                
            if end_dt is not None:
                end_for_db = datetime(
                    end_dt.year, end_dt.month, end_dt.day,
                    end_dt.hour, end_dt.minute, end_dt.second, end_dt.microsecond,
                    tzinfo=end_dt.tzinfo  # Preserve timezone info
                )
            else:
                end_for_db = None
            
            session_doc = {
                'type': session['type'],
                'start': start_for_db,
                'end': end_for_db,
                'date': session['date'],
                'hour': session['hour'],
                'duration_minutes': session.get('duration_minutes', 0),
                'count': session.get('count', 0)
            }
            sessions_ref.add(session_doc)
        print(f"  ✓ Created {len(results['sessions'])} new sessions")
    
    print("  ✓ Done!")


def main():
    parser = argparse.ArgumentParser(description='Fix run/break times in Firebase')
    parser.add_argument('--date', type=str, help='Date to fix (YYYY-MM-DD), defaults to today')
    parser.add_argument('--rebuild-sessions', action='store_true', help='Also rebuild sessions from counts')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--break-threshold', type=int, default=BREAK_THRESHOLD_SECONDS,
                       help=f'Break threshold in seconds (default: {BREAK_THRESHOLD_SECONDS})')
    
    args = parser.parse_args()
    
    # Determine date
    if args.date:
        date_str = args.date
    else:
        date_str = date.today().isoformat()
    
    print(f"=== Fix Run Times for {date_str} ===")
    print(f"Break threshold: {args.break_threshold} seconds")
    print(f"Timezone: IST (UTC+5:30)")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)")
    if args.rebuild_sessions:
        print("Will rebuild sessions from counts")
    
    # Initialize Firebase
    print("\nConnecting to Firebase...")
    db = init_firebase()
    
    # Get counts
    print(f"\nFetching counts for {date_str}...")
    counts = get_counts_for_date(db, date_str)
    
    if not counts:
        print("No counts found for this date. Nothing to fix.")
        return
    
    # Show first and last count times
    first_ts = timestamp_to_datetime(counts[0].get('timestamp'))
    last_ts = timestamp_to_datetime(counts[-1].get('timestamp'))
    print(f"First count: {first_ts.strftime('%H:%M:%S') if first_ts else 'N/A'}")
    print(f"Last count: {last_ts.strftime('%H:%M:%S') if last_ts else 'N/A'}")
    
    # Calculate correct run times
    print("\nCalculating run times...")
    results = calculate_run_times(counts, args.break_threshold)
    
    # Show summary
    print(f"\n=== Calculated Results ===")
    print(f"Total counts: {len(counts)}")
    print(f"Total run time: {results['total_run_minutes']:.1f} minutes ({results['total_run_minutes']/60:.2f} hours)")
    print(f"Total break time: {results['total_break_minutes']:.1f} minutes ({results['total_break_minutes']/60:.2f} hours)")
    print(f"Sessions found: {len(results['sessions'])}")
    
    # Show hourly breakdown
    print(f"\n=== Hourly Breakdown ===")
    for hour in sorted(results['hourly'].keys()):
        h = results['hourly'][hour]
        print(f"  {hour}:00 - Count: {h['count']:3d}, Run: {h['run_minutes']:5.1f}m, Break: {h['break_minutes']:5.1f}m")
    
    # Show sessions
    if results['sessions']:
        print(f"\n=== Sessions ===")
        for i, s in enumerate(results['sessions'][:20]):  # Limit to first 20
            start_str = s['start'].strftime('%H:%M:%S') if s['start'] else '--:--:--'
            end_str = s['end'].strftime('%H:%M:%S') if s['end'] else '--:--:--'
            duration = s.get('duration_minutes', 0)
            pieces = s.get('count', 0)
            print(f"  #{i+1:2d} {s['type']:5s} {start_str} - {end_str} ({duration:5.1f}m, {pieces} pcs)")
        if len(results['sessions']) > 20:
            print(f"  ... and {len(results['sessions']) - 20} more sessions")
    
    # Update Firebase
    print("\n" + "="*50)
    update_firebase(db, date_str, results, args.rebuild_sessions, args.dry_run)


if __name__ == '__main__':
    main()
