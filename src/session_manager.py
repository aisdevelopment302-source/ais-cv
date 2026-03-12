"""
Session Manager Module
======================
Tracks RUN/BREAK sessions for production analytics.

A session is a continuous period of either:
- RUN: Mill is producing pieces (detected by counts)
- BREAK: Mill is idle (no counts for break_threshold seconds)

Sessions are stored in Firebase for historical analysis.
Sessions are pushed when they START and updated as they progress.
"""

import logging
import uuid
from datetime import datetime, date
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class SessionType(Enum):
    RUN = "RUN"
    BREAK = "BREAK"


@dataclass
class Session:
    """Represents a single RUN or BREAK session."""
    session_type: SessionType
    start_time: datetime
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:20])
    end_time: Optional[datetime] = None
    count: int = 0  # For RUN: pieces counted during this session
    travel_times: List[float] = field(default_factory=list)  # Travel times for speed calc
    
    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        if self.end_time is None:
            return (datetime.now(IST) - self.start_time).total_seconds()
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def duration_minutes(self) -> float:
        """Duration in minutes."""
        return self.duration_seconds / 60
    
    @property
    def average_speed(self) -> Optional[float]:
        """Average travel time (speed) for RUN sessions. None if no pieces."""
        if self.session_type != SessionType.RUN or not self.travel_times:
            return None
        return sum(self.travel_times) / len(self.travel_times)
    
    @property
    def hour(self) -> str:
        """Hour when session started (HH format)."""
        return self.start_time.strftime("%H")
    
    @property
    def date_str(self) -> str:
        """Date when session started (YYYY-MM-DD format)."""
        return self.start_time.strftime("%Y-%m-%d")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Firebase."""
        data = {
            'type': self.session_type.value,
            'start': self.start_time,
            'end': self.end_time,
            'date': self.date_str,
            'hour': self.hour,
            'duration_minutes': round(self.duration_minutes, 2),
            'count': self.count
        }
        # Add average_speed only for RUN sessions with pieces
        if self.session_type == SessionType.RUN and self.average_speed is not None:
            data['average_speed'] = round(self.average_speed, 3)
        return data


class SessionManager:
    """
    Manages RUN/BREAK session tracking.
    
    Sessions are pushed to Firebase when they START:
    - RUN session: starts when first piece is counted after a BREAK/OFFLINE
    - BREAK session: starts after 5 minutes of no pieces
    
    Sessions are updated as they progress:
    - RUN session count increments with each piece
    - Duration updates periodically
    
    Sessions end when the opposite type starts:
    - RUN ends when BREAK starts (after 5 min idle)
    - BREAK ends when RUN starts (new piece counted)
    
    Usage:
        manager = SessionManager(break_threshold=300)
        
        # When a piece is counted:
        result = manager.on_piece_counted(current_count)
        # Returns session to create, update, or end
        
        # Periodically check for break (in main loop):
        result = manager.check_for_break()
    """
    
    def __init__(self, break_threshold_seconds: float = 300.0):
        """
        Initialize session manager.
        
        Args:
            break_threshold_seconds: Seconds of idle before BREAK status (default 5 min)
        """
        self.break_threshold = break_threshold_seconds
        
        # Current session
        self.current_session: Optional[Session] = None
        
        # Track last count time for break detection
        self.last_count_time: Optional[datetime] = None
        
        # Completed sessions (for current day)
        self.completed_sessions: List[Session] = []
        
        # Hourly aggregates: {hour: {run_minutes, break_minutes, count}}
        self.hourly_stats: Dict[str, Dict] = {}
        
        # Current status
        self._status: str = "OFFLINE"
        
        # Track current date for daily reset
        self._current_date: date = datetime.now(IST).date()
        
        logger.info(f"SessionManager initialized (break threshold: {break_threshold_seconds}s)")
    
    def restore_session(self, session_data: dict) -> bool:
        """
        Restore session state from Firebase data (for crash recovery).
        
        Args:
            session_data: Dict from Firebase with:
                - session_id: document ID
                - type: 'RUN' | 'BREAK'
                - start: datetime
                - end: datetime or None
                - count: int
                - date: 'YYYY-MM-DD'
        
        Returns:
            True if session was restored, False if should start fresh
        """
        if session_data is None:
            logger.info("No session to restore - starting fresh")
            return False
        
        # Check if session ended
        if session_data.get('end') is not None:
            logger.info("Last session already ended - starting fresh")
            return False
        
        # Get session start time (handle Firestore timestamp)
        start_time = session_data.get('start')
        if hasattr(start_time, 'astimezone'):
            start_time = start_time.astimezone(IST)
        elif hasattr(start_time, 'replace'):
            start_time = start_time.replace(tzinfo=IST)
        else:
            logger.warning(f"Cannot parse start time: {start_time}")
            return False
        
        # Check if session is too old (beyond break threshold = stale)
        idle_seconds = (datetime.now(IST) - start_time).total_seconds()
        last_activity = session_data.get('last_count', start_time)
        if hasattr(last_activity, 'astimezone'):
            last_activity = last_activity.astimezone(IST)
            idle_seconds = (datetime.now(IST) - last_activity).total_seconds()
        
        session_type_str = session_data.get('type', 'BREAK')
        
        # For RUN sessions, check if we've been idle too long
        if session_type_str == 'RUN' and idle_seconds > self.break_threshold:
            logger.info(f"Last RUN session idle for {idle_seconds:.0f}s (>{self.break_threshold}s) - will start BREAK")
            return False
        
        # Restore the session
        session_type = SessionType.RUN if session_type_str == 'RUN' else SessionType.BREAK
        
        self.current_session = Session(
            session_type=session_type,
            start_time=start_time,
            count=session_data.get('count', 0)
        )
        # Restore the session_id so updates go to same Firebase doc
        self.current_session.session_id = session_data.get('session_id', self.current_session.session_id)
        
        self._status = "RUNNING" if session_type == SessionType.RUN else "BREAK"
        self.last_count_time = datetime.now(IST)  # Assume recent activity
        
        logger.info(f"Restored {session_type_str} session {self.current_session.session_id} "
                   f"(count={self.current_session.count}, started {start_time})")
        return True
    
    @property
    def status(self) -> str:
        """Current status: RUNNING, BREAK, or OFFLINE."""
        return self._status
    
    def start_run_session(self, initial_count: int = 1) -> Tuple[Optional[Session], Session]:
        """
        Start a new RUN session.
        Called when a piece is counted after a BREAK or at startup.
        
        Args:
            initial_count: The count to start with (minimum 1 as piece triggered this)
        
        Returns:
            Tuple of:
                - Session to END (the previous BREAK session, if any)
                - Session to CREATE (the new RUN session)
        """
        session_to_end = None
        
        # End current BREAK session if exists
        if self.current_session is not None and self.current_session.session_type == SessionType.BREAK:
            self.current_session.end_time = datetime.now(IST)
            session_to_end = self.current_session
            self._update_hourly_stats(self.current_session)
            self.completed_sessions.append(self.current_session)
            logger.info(f"Ended BREAK session: {self.current_session.duration_minutes:.1f} min")
        
        # Start new RUN session with count=1 (first piece triggered it)
        self.current_session = Session(
            session_type=SessionType.RUN,
            start_time=datetime.now(IST),
            count=max(1, initial_count)  # Minimum 1 since a piece triggered this
        )
        self._status = "RUNNING"
        self.last_count_time = datetime.now(IST)
        
        logger.info(f"Started RUN session {self.current_session.session_id} at {self.current_session.start_time}")
        return session_to_end, self.current_session
    
    def start_break_session(self) -> Tuple[Optional[Session], Session]:
        """
        Start a new BREAK session.
        Called when idle time exceeds break_threshold.
        
        The BREAK session starts from when the last piece was counted (last_count_time),
        not from when we detected the break. This gives accurate break duration.
        
        Returns:
            Tuple of:
                - Session to END (the previous RUN session, if any)
                - Session to CREATE (the new BREAK session)
        """
        session_to_end = None
        
        # The break actually started when the last piece was counted
        # (we just didn't know it was a break until 5 min passed)
        break_start_time = self.last_count_time if self.last_count_time else datetime.now(IST)
        
        # End current RUN session if exists - it ended when the break started
        if self.current_session is not None and self.current_session.session_type == SessionType.RUN:
            self.current_session.end_time = break_start_time
            session_to_end = self.current_session
            self._update_hourly_stats(self.current_session)
            self.completed_sessions.append(self.current_session)
            logger.info(f"Ended RUN session: {self.current_session.duration_minutes:.1f} min, {self.current_session.count} pieces")
        
        # Start new BREAK session from when the break actually started
        self.current_session = Session(
            session_type=SessionType.BREAK,
            start_time=break_start_time,
            count=0
        )
        self._status = "BREAK"
        
        logger.info(f"Started BREAK session {self.current_session.session_id} at {self.current_session.start_time}")
        return session_to_end, self.current_session
    
    def _update_hourly_stats(self, session: Session):
        """Update hourly aggregates for a completed session."""
        hour = session.hour
        
        if hour not in self.hourly_stats:
            self.hourly_stats[hour] = {
                'run_minutes': 0,
                'break_minutes': 0,
                'count': 0
            }
        
        if session.session_type == SessionType.RUN:
            self.hourly_stats[hour]['run_minutes'] += session.duration_minutes
            self.hourly_stats[hour]['count'] += session.count
        else:
            self.hourly_stats[hour]['break_minutes'] += session.duration_minutes
    
    def on_piece_counted(self, travel_time: float = 0.0) -> Dict:
        """
        Called when a piece is counted.
        
        Args:
            travel_time: Travel time for this piece (for speed tracking)
        
        Returns:
            Dict with action info:
                - 'action': 'create_run' | 'update_run' | 'none'
                - 'session_to_end': Session to mark as ended (BREAK) or None
                - 'session_to_create': New RUN session to create or None
                - 'session_to_update': Current RUN session with updated count or None
                - 'run_minutes_since_last': minutes of run time since last count
        """
        now = datetime.now(IST)
        run_minutes_since_last = 0.0
        
        # Calculate time since last count (for incremental run time)
        if self.last_count_time is not None and self._status == "RUNNING":
            elapsed_seconds = (now - self.last_count_time).total_seconds()
            # Cap at break_threshold to avoid counting break time as run time
            elapsed_seconds = min(elapsed_seconds, self.break_threshold)
            run_minutes_since_last = elapsed_seconds / 60.0
        
        self.last_count_time = now
        
        result = {
            'action': 'none',
            'session_to_end': None,
            'session_to_create': None,
            'session_to_update': None,
            'run_minutes_since_last': run_minutes_since_last
        }
        
        # If in BREAK or OFFLINE, transition to RUN
        if self._status != "RUNNING":
            session_to_end, new_session = self.start_run_session(initial_count=1)
            # Add travel time to the new session
            if travel_time > 0:
                new_session.travel_times.append(travel_time)
            result['action'] = 'create_run'
            result['session_to_end'] = session_to_end
            result['session_to_create'] = new_session
        else:
            # Already in RUN - increment count and track travel time
            if self.current_session and self.current_session.session_type == SessionType.RUN:
                self.current_session.count += 1
                if travel_time > 0:
                    self.current_session.travel_times.append(travel_time)
                result['action'] = 'update_run'
                result['session_to_update'] = self.current_session
        
        return result
    
    def check_for_break(self) -> Optional[Dict]:
        """
        Check if we should transition to BREAK.
        Call this periodically in the main loop.
        
        Returns:
            Dict with action info if transitioning, None otherwise:
                - 'action': 'create_break'
                - 'session_to_end': RUN session to mark as ended
                - 'session_to_create': New BREAK session to create
        """
        # Can't transition if no last count time
        if self.last_count_time is None:
            return None
        
        # Already in BREAK or OFFLINE
        if self._status != "RUNNING":
            return None
        
        # Check if idle time exceeds threshold
        idle_seconds = (datetime.now(IST) - self.last_count_time).total_seconds()
        
        if idle_seconds >= self.break_threshold:
            session_to_end, new_session = self.start_break_session()
            return {
                'action': 'create_break',
                'session_to_end': session_to_end,
                'session_to_create': new_session
            }
        
        return None
    
    def check_daily_reset(self) -> bool:
        """
        Check if date changed and reset if needed.
        Call this periodically in the main loop.
        
        Returns:
            True if reset occurred
        """
        current_date = datetime.now(IST).date()
        
        if current_date != self._current_date:
            logger.info(f"Date changed: {self._current_date} -> {current_date}")
            
            # Reset for new day
            self._current_date = current_date
            self.completed_sessions = []
            self.hourly_stats = {}
            
            return True
        
        return False
    
    def get_hourly_stats(self, hour: Optional[str] = None) -> Dict:
        """
        Get hourly statistics.
        
        Args:
            hour: Specific hour (HH format) or None for all hours
            
        Returns:
            Dict with run_minutes, break_minutes, count
        """
        if hour is not None:
            return self.hourly_stats.get(hour, {
                'run_minutes': 0,
                'break_minutes': 0,
                'count': 0
            })
        
        return self.hourly_stats.copy()
    
    def get_daily_totals(self) -> Dict:
        """Get daily totals for all completed sessions."""
        total_run = 0
        total_break = 0
        total_count = 0
        
        for stats in self.hourly_stats.values():
            total_run += stats.get('run_minutes', 0)
            total_break += stats.get('break_minutes', 0)
            total_count += stats.get('count', 0)
        
        # Include current session if active
        if self.current_session is not None:
            if self.current_session.session_type == SessionType.RUN:
                total_run += self.current_session.duration_minutes
                total_count += self.current_session.count
            else:
                total_break += self.current_session.duration_minutes
        
        return {
            'total_run_minutes': round(total_run, 2),
            'total_break_minutes': round(total_break, 2),
            'total_count': total_count
        }
    
    def get_current_session(self) -> Optional[Session]:
        """Get the current active session."""
        return self.current_session
    
    def get_current_session_dict(self) -> Optional[Dict]:
        """
        Get current session data for Firebase status updates.
        """
        if self.current_session is None:
            return None
        
        return self.current_session.to_dict()
    
    def shutdown(self) -> Optional[Session]:
        """
        Gracefully shutdown - end current session.
        
        Returns:
            The ended session for Firebase update
        """
        ended_session = None
        
        if self.current_session is not None:
            self.current_session.end_time = datetime.now(IST)
            ended_session = self.current_session
            self._update_hourly_stats(self.current_session)
            self.completed_sessions.append(self.current_session)
            logger.info(f"Shutdown: Ended {self.current_session.session_type.value} session")
        
        self._status = "OFFLINE"
        logger.info("SessionManager shutdown complete")
        
        return ended_session
