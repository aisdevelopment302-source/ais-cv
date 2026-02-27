#!/usr/bin/env python3
"""Test Firebase connection and push a test count."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from firebase_client import get_firebase_client
from datetime import datetime

def test_firebase():
    print("Testing Firebase connection...")
    
    client = get_firebase_client()
    
    if not client.initialize():
        print("❌ Failed to initialize Firebase")
        return False
    
    print("✅ Firebase initialized!")
    
    # Test status update
    print("\nSetting status to RUNNING...")
    if client.update_status('RUNNING'):
        print("✅ Status updated!")
    else:
        print("❌ Status update failed")
        return False
    
    # Test pushing a count
    print("\nPushing test count...")
    test_data = {
        'timestamp': datetime.now(),
        'travel_time': 1.25,
        'line_pixels': {'L1': 120, 'L2': 135, 'L3': 110}
    }
    
    if client.push_count(test_data):
        print("✅ Test count pushed!")
    else:
        print("❌ Count push failed")
        return False
    
    # Get today's count
    count = client.get_today_count()
    print(f"\n📊 Today's count: {count}")
    
    print("\n" + "="*50)
    print("✅ Firebase test PASSED!")
    print("Check your dashboard - you should see the count update")
    print("="*50)
    
    return True

if __name__ == "__main__":
    test_firebase()
