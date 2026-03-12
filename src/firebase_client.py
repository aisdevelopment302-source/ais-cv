"""
Firebase client for pushing mill stand counts to Firestore.
Uses service account authentication for server-side access.

Firestore Schema:
-----------------
CAM-2 (mill stand) documents
------------------------------
live/mill_stand
  - today_count: int
  - status: 'RUNNING' | 'BREAK' | 'OFFLINE'
  - last_count: timestamp
  - last_avg_travel_time: float
  - date: 'YYYY-MM-DD'
  - current_session: {type, start, duration_minutes, count}

NOTE: CAM-2 does NOT write to the counts/ collection.
      Piece-level detail stays local only.

daily/{YYYY-MM-DD_cam2}
  - count: int
  - first_count: timestamp
  - last_count: timestamp
  - total_run_minutes: float
  - total_break_minutes: float
  - camera: 'CAM-2'
  - date: 'YYYY-MM-DD'

hourly/{YYYY-MM-DD_cam2}/hours/{HH}
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
  - count: int (for RUN sessions)
  - camera: 'CAM-2'
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
    
    def create_session(self, session, camera: str = 'CAM-2') -> bool:
        """
        Create a new session in Firestore (called when session STARTS).
        Uses session.session_id as document ID for later updates.
        
        Args:
            session: Session object with:
                - session_id: unique ID for this session
                - session_type: RUN or BREAK
                - start_time: when session started
                - count: initial count (1 for RUN, 0 for BREAK)
            camera: Camera identifier ('CAM-1' or 'CAM-2'). Default 'CAM-1'.
                
        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        try:
            session_data = session.to_dict()
            session_id = session.session_id

            # Tag session with camera so queries can filter by source
            if camera != 'CAM-1':
                session_data['camera'] = camera
            
            # Create session document with specific ID (for later updates)
            self.db.collection('sessions').document(session_id).set(session_data)
            
            logger.info(f"Created {session.session_type.value} session: {session_id} ({camera})")
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

    def push_mill_count(self, count_data: dict, session_info: dict = None) -> bool:
        """
        Push a mill stand count event to Firestore (CAM-2).

        Unlike push_count() for CAM-1, this method does NOT write to the
        counts/ collection. Only session-level analytics are recorded:
        live/mill_stand, daily/{date}_cam2, hourly/{date}_cam2/hours/{HH}.

        Args:
            count_data: Dict containing count info:
                - timestamp: datetime of the count
                - avg_travel_time: float average travel time across stands
                - vote_ratio: float fraction of views that agreed
                - stands_detected: int number of stands that voted
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
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=IST)

            hour = timestamp.strftime("%H")

            run_minutes_increment = 0
            if session_info:
                run_minutes_increment = session_info.get('run_minutes_since_last', 0)

            # daily document uses composite ID to avoid clash with CAM-1
            daily_doc_id = f"{today}_cam2"
            daily_ref = self.db.collection('daily').document(daily_doc_id)
            daily_doc = daily_ref.get()

            if daily_doc.exists:
                update_data = {
                    'count': firestore.Increment(1),
                    'last_count': timestamp
                }
                if run_minutes_increment > 0:
                    update_data['total_run_minutes'] = firestore.Increment(run_minutes_increment)
                daily_ref.update(update_data)
            else:
                daily_ref.set({
                    'count': 1,
                    'date': today,
                    'first_count': timestamp,
                    'last_count': timestamp,
                    'total_run_minutes': run_minutes_increment,
                    'total_break_minutes': 0,
                    'camera': 'CAM-2'
                })

            # hourly subcollection also uses composite parent ID
            hourly_ref = (self.db.collection('hourly')
                          .document(daily_doc_id)
                          .collection('hours')
                          .document(hour))
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

            # Update live/mill_stand (real-time dashboard)
            live_ref = self.db.collection('live').document('mill_stand')
            live_ref.set({
                'today_count': firestore.Increment(1),
                'last_count': timestamp,
                'last_avg_travel_time': count_data.get('avg_travel_time', 0),
                'status': 'RUNNING',
                'date': today
            }, merge=True)

            logger.debug(f"Pushed mill count to Firebase: {timestamp}, run_increment: {run_minutes_increment:.2f}m")
            return True

        except Exception as e:
            logger.error(f"Failed to push mill count: {e}")
            return False

    def update_mill_status(self, status: str, session_info: dict = None) -> bool:
        """
        Update mill stand status in live/mill_stand (CAM-2 equivalent of update_status).

        Args:
            status: 'RUNNING' | 'BREAK' | 'OFFLINE'
            session_info: Optional current session dict for dashboard display

        Returns:
            True if successful
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            live_ref = self.db.collection('live').document('mill_stand')
            update_data = {
                'status': status,
                'status_updated': datetime.now(IST)
            }

            if session_info:
                update_data['current_session'] = session_info

            live_ref.set(update_data, merge=True)

            logger.debug(f"Updated mill stand status to: {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update mill stand status: {e}")
            return False

    def get_mill_today_count(self) -> int:
        """
        Get today's mill stand count from Firestore (CAM-2).

        Reads from daily/{today}_cam2.

        Returns:
            int count, or 0 on error / no document
        """
        if not self._initialized:
            if not self.initialize():
                return 0

        try:
            today = datetime.now(IST).date().isoformat()
            daily_doc_id = f"{today}_cam2"
            daily_ref = self.db.collection('daily').document(daily_doc_id)
            doc = daily_ref.get()

            if doc.exists:
                return doc.to_dict().get('count', 0)
            return 0

        except Exception as e:
            logger.error(f"Failed to get mill today count: {e}")
            return 0

    def end_mill_session(self, session) -> bool:
        """
        Mark a mill stand session as ended in Firestore (CAM-2).

        Identical to end_session() but updates daily/{date}_cam2 and
        hourly/{date}_cam2 documents so CAM-2 break/run minutes are
        tracked separately from CAM-1.

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

            update_data = {
                'end': session.end_time,
                'duration_minutes': round(session.duration_minutes, 2),
                'count': session.count,
                'camera': 'CAM-2'
            }

            if session.session_type.value == 'RUN' and session.average_speed is not None:
                update_data['average_speed'] = round(session.average_speed, 3)

            self.db.collection('sessions').document(session_id).update(update_data)

            session_type = session.session_type.value
            duration = session.duration_minutes
            date_str = session.date_str
            hour = session.hour
            daily_doc_id = f"{date_str}_cam2"

            # Update hourly aggregates (CAM-2 composite ID)
            hourly_ref = (self.db.collection('hourly')
                          .document(daily_doc_id)
                          .collection('hours')
                          .document(hour))
            hourly_doc = hourly_ref.get()
            field_name = 'run_minutes' if session_type == 'RUN' else 'break_minutes'

            if hourly_doc.exists:
                hourly_ref.update({field_name: firestore.Increment(duration)})
            else:
                hourly_ref.set({
                    'count': 0,
                    'run_minutes': duration if session_type == 'RUN' else 0,
                    'break_minutes': duration if session_type == 'BREAK' else 0
                })

            # Update daily totals (CAM-2 composite ID)
            daily_ref = self.db.collection('daily').document(daily_doc_id)
            daily_doc = daily_ref.get()
            daily_field = 'total_run_minutes' if session_type == 'RUN' else 'total_break_minutes'

            if daily_doc.exists:
                daily_ref.update({daily_field: firestore.Increment(duration)})
            else:
                daily_ref.set({
                    'count': 0,
                    'date': date_str,
                    'total_run_minutes': duration if session_type == 'RUN' else 0,
                    'total_break_minutes': duration if session_type == 'BREAK' else 0,
                    'camera': 'CAM-2'
                })

            logger.info(f"Ended mill {session_type} session {session_id}: {duration:.1f} min")
            return True

        except Exception as e:
            logger.error(f"Failed to end mill session: {e}")
            return False


# Singleton instance for easy import
_client = None

def get_firebase_client() -> FirebaseClient:
    """Get or create the Firebase client singleton."""
    global _client
    if _client is None:
        _client = FirebaseClient()
    return _client
