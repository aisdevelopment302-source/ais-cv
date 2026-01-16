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
  - current_session: {type, start, duration_minutes, count}

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

sessions/{session_id}
  - type: 'RUN' | 'BREAK'
  - start: timestamp
  - end: timestamp (null while active)
  - date: 'YYYY-MM-DD'
  - hour: 'HH'
  - duration_minutes: float
  - count: int (for RUN sessions, increments live)
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
            service_account_path = str(project_root / "config" / "firebase-service-account.json")
        
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
    
    def create_session(self, session) -> bool:
        """
        Create a new session in Firestore (called when session STARTS).
        Uses session.session_id as document ID for later updates.
        
        Args:
            session: Session object with:
                - session_id: unique ID for this session
                - session_type: RUN or BREAK
                - start_time: when session started
                - count: initial count (1 for RUN, 0 for BREAK)
                
        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            session_data = session.to_dict()
            session_id = session.session_id
            
            # Create session document with specific ID (for later updates)
            self.db.collection('sessions').document(session_id).set(session_data)
            
            logger.info(f"Created {session.session_type.value} session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return False
    
    def update_session(self, session) -> bool:
        """
        Update an existing session in Firestore (called as session progresses).
        Only updates count (not duration - that's calculated at end).
        
        Args:
            session: Session object with updated count
                
        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            session_id = session.session_id
            
            # Update session document - only count, not duration
            self.db.collection('sessions').document(session_id).update({
                'count': session.count
            })
            
            logger.debug(f"Updated session {session_id}: count={session.count}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            return False
    
    def end_session(self, session) -> bool:
        """
        Mark a session as ended in Firestore.
        Sets end_time, final duration_minutes, and average_speed (for RUN sessions).
        Also updates hourly/daily aggregates.
        
        Args:
            session: Session object with end_time set
                
        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            session_id = session.session_id
            session_data = session.to_dict()
            
            # Build update data
            update_data = {
                'end': session.end_time,
                'duration_minutes': round(session.duration_minutes, 2),
                'count': session.count
            }
            
            # Add average_speed for RUN sessions
            if session.session_type.value == 'RUN' and session.average_speed is not None:
                update_data['average_speed'] = round(session.average_speed, 3)
            
            # Update session document with end time
            self.db.collection('sessions').document(session_id).update(update_data)
            
            # Update hourly aggregates
            session_type = session.session_type.value
            duration = session.duration_minutes
            date_str = session.date_str
            hour = session.hour
            
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
            
            logger.info(f"Ended {session_type} session {session_id}: {duration:.1f} min")
            return True
            
        except Exception as e:
            logger.error(f"Failed to end session: {e}")
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
            
            logger.debug(f"Updated status to: {status}")
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
    
    def get_last_session(self) -> dict:
        """
        Get the most recent session from Firestore.
        Used for session recovery on startup.
        
        Returns:
            Dict with session data or None if no sessions found:
                - session_id: document ID
                - type: 'RUN' | 'BREAK'
                - start: datetime
                - end: datetime or None (if still active)
                - count: int
                - date: 'YYYY-MM-DD'
        """
        if not self._initialized:
            if not self.initialize():
                return None
        
        try:
            # Get most recent session by start time
            sessions = (self.db.collection('sessions')
                       .order_by('start', direction=firestore.Query.DESCENDING)
                       .limit(1)
                       .get())
            
            for doc in sessions:
                data = doc.to_dict()
                data['session_id'] = doc.id
                logger.info(f"Found last session: {data.get('type')} from {data.get('start')}, end={data.get('end')}")
                return data
            
            logger.info("No sessions found in Firestore")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get last session: {e}")
            return None


# Singleton instance for easy import
_client = None

def get_firebase_client() -> FirebaseClient:
    """Get or create the Firebase client singleton."""
    global _client
    if _client is None:
        _client = FirebaseClient()
    return _client
