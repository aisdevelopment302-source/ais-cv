#!/usr/bin/env python3
"""
Fix BREAK Session Durations
===========================
BREAK sessions were created with start_time = when break was detected,
but they should start from when the last piece was counted (end of previous RUN).

This script:
1. Finds all BREAK sessions
2. Looks up the previous RUN session
3. Sets BREAK start_time = previous RUN end_time
4. Recalculates duration_minutes

Usage:
    python fix_break_sessions.py              # Dry run
    python fix_break_sessions.py --execute   # Actually fix
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


def get_all_sessions(db):
    """Get all sessions ordered by start time."""
    sessions = db.collection('sessions').order_by('start').get()
    
    result = []
    for doc in sessions:
        data = doc.to_dict()
        data['id'] = doc.id
        result.append(data)
    
    return result


def fix_break_sessions(db, execute=False):
    """Fix BREAK sessions to have proper start times and durations."""
    sessions = get_all_sessions(db)
    
    print(f"Found {len(sessions)} total sessions")
    
    fixed_count = 0
    prev_session = None
    
    for session in sessions:
        session_type = session.get('type')
        
        if session_type == 'BREAK' and prev_session:
            # Get times
            break_start = session.get('start')
            break_end = session.get('end')
            prev_end = prev_session.get('end')
            
            # Handle Firestore timestamps
            if hasattr(break_start, 'astimezone'):
                break_start = break_start.astimezone(IST)
            if break_end and hasattr(break_end, 'astimezone'):
                break_end = break_end.astimezone(IST)
            if prev_end and hasattr(prev_end, 'astimezone'):
                prev_end = prev_end.astimezone(IST)
            
            # If previous session was RUN and ended before this BREAK started,
            # the BREAK should actually start when the RUN ended
            if prev_session.get('type') == 'RUN' and prev_end and break_start:
                gap = (break_start - prev_end).total_seconds()
                
                # If there's a gap > 1 minute, this BREAK needs fixing
                if gap > 60:
                    old_duration = session.get('duration_minutes', 0)
                    
                    # New start time = when previous RUN ended
                    new_start = prev_end
                    
                    # Calculate new duration
                    if break_end:
                        new_duration = (break_end - new_start).total_seconds() / 60
                    else:
                        new_duration = old_duration + (gap / 60)
                    
                    print(f"\nBREAK {session['id']}:")
                    print(f"  Old: start={break_start}, duration={old_duration:.1f}min")
                    print(f"  New: start={new_start}, duration={new_duration:.1f}min")
                    print(f"  Gap fixed: {gap/60:.1f} minutes added")
                    
                    if execute:
                        db.collection('sessions').document(session['id']).update({
                            'start': new_start,
                            'duration_minutes': round(new_duration, 2)
                        })
                        print(f"  FIXED!")
                    
                    fixed_count += 1
        
        prev_session = session
    
    return fixed_count


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fix BREAK session durations')
    parser.add_argument('--execute', action='store_true', help='Actually fix (default is dry run)')
    args = parser.parse_args()
    
    print("=" * 60)
    print("FIX BREAK SESSION DURATIONS")
    print("=" * 60)
    
    if not args.execute:
        print("\n*** DRY RUN - No changes will be made ***\n")
    
    db = init_firebase()
    if not db:
        return
    
    fixed = fix_break_sessions(db, execute=args.execute)
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {fixed} BREAK sessions need fixing")
    if not args.execute and fixed > 0:
        print("\n*** Run with --execute to apply fixes ***")
    print("=" * 60)


if __name__ == "__main__":
    main()
