"""
Session Manager Module
======================
Tracks RUN/BREAK sessions for production analytics.

A session is a continuous period of either:
- RUN: Mill is producing pieces (detected by counts)
- BREAK: Mill is idle (no counts for break_threshold seconds)

Sessions are stored in Firebase for historical analysis.
"""

import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field
from typing import Optional, List, Dict
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
    end_time: Optional[datetime] = None
    count_at_start: int = 0
    count_at_end: int = 0
    
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
    def pieces_counted(self) -> int:
        """Number of pieces counted during this session (RUN only)."""
        return self.count_at_end - self.count_at_start
    
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
        return {
            'type': self.session_type.value,
            'start': self.start_time,
            'end': self.end_time,
            'date': self.date_str,
            'hour': self.hour,
            'duration_minutes': round(self.duration_minutes, 2),
            'count': self.pieces_counted if self.session_type == SessionType.RUN else 0
        }


class SessionManager:
    """
    Manages RUN/BREAK session tracking.
    
    Usage:
        manager = SessionManager(break_threshold=120)
        
        # When a piece is counted:
        manager.on_piece_counted(current_count)
        
        # Periodically check for break (in main loop):
        manager.check_for_break(current_count)
        
        # Get stats for Firebase:
        hourly_stats = manager.get_hourly_stats()
    """
    
    def __init__(self, break_threshold_seconds: float = 120.0):
        """
        Initialize session manager.
        
        Args:
            break_threshold_seconds: Seconds of idle before BREAK status
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
    
    @property
    def status(self) -> str:
        """Current status: RUNNING, BREAK, or OFFLINE."""
        return self._status
    
    def start_run_session(self, current_count: int = 0) -> Optional[Session]:
        """
        Start a new RUN session.
        Called when a piece is counted after a BREAK or at startup.
        
        Returns:
            The ended BREAK session (if any) for Firebase push
        """
        ended_session = None
        
        # End current session if exists
        if self.current_session is not None:
            ended_session = self._end_current_session(current_count)
        
        # Start new RUN session
        self.current_session = Session(
            session_type=SessionType.RUN,
            start_time=datetime.now(IST),
            count_at_start=current_count
        )
        self._status = "RUNNING"
        self.last_count_time = datetime.now(IST)
        
        logger.info(f"Started RUN session at {self.current_session.start_time}")
        return ended_session
    
    def start_break_session(self, current_count: int = 0) -> Optional[Session]:
        """
        Start a new BREAK session.
        Called when idle time exceeds break_threshold.
        
        Returns:
            The ended RUN session (if any) for Firebase push
        """
        ended_session = None
        
        # End current session if exists
        if self.current_session is not None:
            ended_session = self._end_current_session(current_count)
        
        # Start new BREAK session
        self.current_session = Session(
            session_type=SessionType.BREAK,
            start_time=datetime.now(IST),
            count_at_start=current_count
        )
        self._status = "BREAK"
        
        logger.info(f"Started BREAK session at {self.current_session.start_time}")
        return ended_session
    
    def _end_current_session(self, current_count: int) -> Session:
        """End the current session and add to completed list."""
        session = self.current_session
        if session is None:
            # Should not happen if logic is correct, but safe guard
            raise ValueError("No active session to end")

        session.end_time = datetime.now(IST)
        session.count_at_end = current_count
        
        # Update hourly stats
        self._update_hourly_stats(session)
        
        # Add to completed sessions
        self.completed_sessions.append(session)
        
        logger.info(f"Ended {session.session_type.value} session: "
                   f"{session.duration_minutes:.1f} min, "
                   f"{session.pieces_counted} pieces")
        
        return session
    
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
            self.hourly_stats[hour]['count'] += session.pieces_counted
        else:
            self.hourly_stats[hour]['break_minutes'] += session.duration_minutes
    
    def on_piece_counted(self, current_count: int) -> tuple[Optional[Session], dict]:
        """
        Called when a piece is counted.
        Starts RUN session if currently in BREAK.
        
        Returns:
            Tuple of:
                - Ended BREAK session (if transitioned) for Firebase push
                - Dict with run_minutes_since_last for incremental update
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
        
        session_info = {
            'run_minutes_since_last': run_minutes_since_last
        }
        
        # If in BREAK or OFFLINE, transition to RUN
        if self._status != "RUNNING":
            return self.start_run_session(current_count), session_info
        
        return None, session_info
    
    def check_for_break(self, current_count: int) -> Optional[Session]:
        """
        Check if we should transition to BREAK.
        Call this periodically in the main loop.
        
        Returns:
            Ended RUN session (if transitioned) for Firebase push
        """
        # Can't transition if no last count time
        if self.last_count_time is None:
            return None
        
        # Already in BREAK
        if self._status == "BREAK":
            return None
        
        # Check if idle time exceeds threshold
        idle_seconds = (datetime.now(IST) - self.last_count_time).total_seconds()
        
        if idle_seconds >= self.break_threshold:
            return self.start_break_session(current_count)
        
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
            else:
                total_break += self.current_session.duration_minutes
        
        return {
            'total_run_minutes': round(total_run, 2),
            'total_break_minutes': round(total_break, 2),
            'total_count': total_count
        }
    
    def get_pending_session(self) -> Optional[Dict]:
        """
        Get current session data for Firebase (without ending it).
        Useful for periodic status updates.
        """
        if self.current_session is None:
            return None
        
        session = self.current_session
        return {
            'type': session.session_type.value,
            'start': session.start_time,
            'duration_minutes': round(session.duration_minutes, 2),
            'date': session.date_str,
            'hour': session.hour
        }
    
    def shutdown(self, current_count: int = 0) -> Optional[Session]:
        """
        Gracefully shutdown - end current session.
        
        Returns:
            The ended session for Firebase push
        """
        ended_session = None
        
        if self.current_session is not None:
            ended_session = self._end_current_session(current_count)
        
        self._status = "OFFLINE"
        logger.info("SessionManager shutdown complete")
        
        return ended_session
