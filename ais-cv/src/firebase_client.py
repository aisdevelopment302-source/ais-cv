"""
Firebase client for pushing plate counts to Firestore.
Uses service account authentication for server-side access.

Firestore Schema:
-----------------
live/furnace
  - today_count: int
  - status: 'RUNNING' | 'BREAK' | 'OFFLINE'
  - last_count: timestamp
  - last_travel_time: float
  - date: 'YYYY-MM-DD'
  - current_session: {type, start, duration_minutes}

counts/{auto-id}
  - timestamp: datetime
  - travel_time: float
  - confidence: float (0-100)
  - line_pixels: {L1, L2, L3}
  - line_frames: {L1, L2, L3}
  - line_brightness: {L1, L2, L3}
  - camera: 'CAM-1'
  - date: 'YYYY-MM-DD'
  - hour: 'HH'
  - photo_filename: str (optional)
  - flagged: bool (for review)
  - reviewed: bool

daily/{YYYY-MM-DD}
  - count: int
  - first_count: timestamp
  - last_count: timestamp
  - total_run_minutes: float
  - total_break_minutes: float
  - camera: 'CAM-1'

hourly/{YYYY-MM-DD}/hours/{HH}
  - count: int
  - run_minutes: float
  - break_minutes: float

sessions/{auto-id}
  - type: 'RUN' | 'BREAK'
  - start: timestamp
  - end: timestamp
  - date: 'YYYY-MM-DD'
  - hour: 'HH'
  - duration_minutes: float
  - count: int (for RUN sessions)
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, date
from zoneinfo import ZoneInfo
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class FirebaseClient:
    """Handles all Firebase/Firestore operations for the counter."""
    
    def __init__(self, service_account_path: str = None):
        """
        Initialize Firebase client with service account.
        
        Args:
            service_account_path: Path to service account JSON file.
                                  Defaults to config/firebase-service-account.json
        """
        if service_account_path is None:
            # Default path relative to project root
            project_root = Path(__file__).parent.parent
            service_account_path = project_root / "config" / "firebase-service-account.json"
        
        self.service_account_path = Path(service_account_path)
        self._initialized = False
        self.db = None
        
    def initialize(self) -> bool:
        """Initialize Firebase app and Firestore client."""
        if self._initialized:
            return True
            
        try:
            if not self.service_account_path.exists():
                logger.error(f"Service account file not found: {self.service_account_path}")
                return False
            
            cred = credentials.Certificate(str(self.service_account_path))
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            self._initialized = True
            logger.info("Firebase initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            return False
    
    def push_count(self, count_data: dict, session_info: dict = None) -> bool:
        """
        Push a single count event to Firestore.
        
        Args:
            count_data: Dict containing count info:
                - timestamp: datetime of the count
                - travel_time: float seconds from L1 to L3
                - confidence: float (0-100)
                - line_pixels: dict of pixel counts per line
                - line_frames: dict of frame counts per line
                - line_brightness: dict of avg brightness per line
                - photo_filename: optional filename of count photo
            session_info: Optional dict with current session state:
                - run_minutes_since_last: minutes of run time to add
                - session_start: datetime when current session started
                - session_type: 'RUN' or 'BREAK'
                
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            today = datetime.now(IST).date().isoformat()
            timestamp = count_data.get('timestamp', datetime.now(IST))
            # Ensure timestamp is timezone-aware
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=IST)
            
            hour = timestamp.strftime("%H")
            confidence = count_data.get('confidence', 100.0)
            
            # Auto-flag low confidence counts for review
            flagged = confidence < 70
            
            # Get run time increment from session info
            run_minutes_increment = 0
            if session_info:
                run_minutes_increment = session_info.get('run_minutes_since_last', 0)
            
            # Add to counts collection (individual events)
            count_doc = {
                'timestamp': timestamp,
                'travel_time': count_data.get('travel_time', 0),
                'confidence': confidence,
                'line_pixels': count_data.get('line_pixels', {}),
                'line_frames': count_data.get('line_frames', {}),
                'line_brightness': count_data.get('line_brightness', {}),
                'camera': 'CAM-1',
                'date': today,
                'hour': hour,
                'photo_filename': count_data.get('photo_filename', ''),
                'flagged': flagged,
                'reviewed': False
            }
            self.db.collection('counts').add(count_doc)
            
            # Update daily counter document
            daily_ref = self.db.collection('daily').document(today)
            daily_doc = daily_ref.get()
            
            if daily_doc.exists:
                # Increment existing count and run time
                update_data = {
                    'count': firestore.Increment(1),
                    'last_count': timestamp
                }
                if run_minutes_increment > 0:
                    update_data['total_run_minutes'] = firestore.Increment(run_minutes_increment)
                daily_ref.update(update_data)
            else:
                # Create new daily document
                daily_ref.set({
                    'count': 1,
                    'date': today,
                    'first_count': timestamp,
                    'last_count': timestamp,
                    'total_run_minutes': run_minutes_increment,
                    'total_break_minutes': 0,
                    'camera': 'CAM-1'
                })
            
            # Update hourly counter (subcollection)
            hourly_ref = self.db.collection('hourly').document(today).collection('hours').document(hour)
            hourly_doc = hourly_ref.get()
            
            if hourly_doc.exists:
                update_data = {'count': firestore.Increment(1)}
                if run_minutes_increment > 0:
                    update_data['run_minutes'] = firestore.Increment(run_minutes_increment)
                hourly_ref.update(update_data)
            else:
                hourly_ref.set({
                    'count': 1,
                    'run_minutes': run_minutes_increment,
                    'break_minutes': 0
                })
            
            # Update live counter (for real-time dashboard)
            live_ref = self.db.collection('live').document('furnace')
            live_ref.set({
                'today_count': firestore.Increment(1),
                'last_count': timestamp,
                'last_travel_time': count_data.get('travel_time', 0),
                'status': 'RUNNING',
                'date': today
            }, merge=True)
            
            logger.debug(f"Pushed count to Firebase: {timestamp}, run_increment: {run_minutes_increment:.2f}m")
            return True
            
        except Exception as e:
            logger.error(f"Failed to push count: {e}")
            return False
    
    def push_session(self, session_data: dict) -> bool:
        """
        Push a completed session to Firestore.
        
        Args:
            session_data: Dict from Session.to_dict():
                - type: 'RUN' | 'BREAK'
                - start: datetime
                - end: datetime
                - date: 'YYYY-MM-DD'
                - hour: 'HH'
                - duration_minutes: float
                - count: int
                
        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            # Add to sessions collection
            self.db.collection('sessions').add(session_data)
            
            session_type = session_data.get('type', 'UNKNOWN')
            duration = session_data.get('duration_minutes', 0)
            date_str = session_data.get('date', datetime.now(IST).date().isoformat())
            hour = session_data.get('hour', datetime.now(IST).strftime("%H"))
            
            # Update hourly aggregates
            hourly_ref = self.db.collection('hourly').document(date_str).collection('hours').document(hour)
            hourly_doc = hourly_ref.get()
            
            field_name = 'run_minutes' if session_type == 'RUN' else 'break_minutes'
            
            if hourly_doc.exists:
                hourly_ref.update({
                    field_name: firestore.Increment(duration)
                })
            else:
                hourly_ref.set({
                    'count': 0,
                    'run_minutes': duration if session_type == 'RUN' else 0,
                    'break_minutes': duration if session_type == 'BREAK' else 0
                })
            
            # Update daily totals
            daily_ref = self.db.collection('daily').document(date_str)
            daily_doc = daily_ref.get()
            
            daily_field = 'total_run_minutes' if session_type == 'RUN' else 'total_break_minutes'
            
            if daily_doc.exists:
                daily_ref.update({
                    daily_field: firestore.Increment(duration)
                })
            else:
                daily_ref.set({
                    'count': 0,
                    'date': date_str,
                    'total_run_minutes': duration if session_type == 'RUN' else 0,
                    'total_break_minutes': duration if session_type == 'BREAK' else 0,
                    'camera': 'CAM-1'
                })
            
            logger.info(f"Pushed {session_type} session: {duration:.1f} min")
            return True
            
        except Exception as e:
            logger.error(f"Failed to push session: {e}")
            return False
    
    def update_status(self, status: str, session_info: dict = None) -> bool:
        """
        Update mill status (RUNNING, BREAK, OFFLINE).
        
        Args:
            status: Current status string
            session_info: Optional current session info for display
            
        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            live_ref = self.db.collection('live').document('furnace')
            update_data = {
                'status': status,
                'status_updated': datetime.now(IST)
            }
            
            if session_info:
                update_data['current_session'] = session_info
            
            live_ref.set(update_data, merge=True)
            
            logger.info(f"Updated status to: {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            return False
    
    def reset_daily_count(self) -> bool:
        """
        Reset the daily count (call at midnight or shift start).
        
        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            today = datetime.now(IST).date().isoformat()
            live_ref = self.db.collection('live').document('furnace')
            live_ref.set({
                'today_count': 0,
                'date': today,
                'current_session': firestore.DELETE_FIELD
            }, merge=True)
            
            logger.info(f"Reset daily count for {today}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset daily count: {e}")
            return False
    
    def get_today_count(self) -> int:
        """Get current day's count from Firestore."""
        if not self._initialized:
            if not self.initialize():
                return 0
        
        try:
            today = datetime.now(IST).date().isoformat()
            daily_ref = self.db.collection('daily').document(today)
            doc = daily_ref.get()
            
            if doc.exists:
                return doc.to_dict().get('count', 0)
            return 0
            
        except Exception as e:
            logger.error(f"Failed to get today count: {e}")
            return 0


# Singleton instance for easy import
_client = None

def get_firebase_client() -> FirebaseClient:
    """Get or create the Firebase client singleton."""
    global _client
    if _client is None:
        _client = FirebaseClient()
    return _client
