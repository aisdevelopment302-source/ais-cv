"""Production State Machine - RUNNING vs BREAK"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class ProductionState(Enum):
    RUNNING = "RUN"
    BREAK = "BRK"
    UNKNOWN = "UNK"


@dataclass
class StateChange:
    timestamp: datetime
    previous_state: ProductionState
    new_state: ProductionState
    confidence: float
    duration_in_previous_seconds: float


class ProductionStateMachine:
    def __init__(
        self,
        break_threshold_seconds: float = 120.0,
        min_run_duration_seconds: float = 10.0,
        on_state_change: Optional[Callable[[StateChange], None]] = None,
    ):
        self.break_threshold_seconds = break_threshold_seconds
        self.min_run_duration_seconds = min_run_duration_seconds
        self.on_state_change = on_state_change

        # Current state
        self.current_state = ProductionState.UNKNOWN
        self.state_start_time: Optional[float] = None

        # Last detection tracking
        self.last_hot_stock_time: Optional[float] = None
        self.last_confidence: float = 0.0

        # Debouncing
        self.pending_state: Optional[ProductionState] = None
        self.pending_state_start: Optional[float] = None

    def update(
        self, hot_stock_detected: bool, confidence: float
    ) -> Optional[StateChange]:
        """Update state machine with new detection result"""
        current_time = time.time()
        self.last_confidence = confidence

        if hot_stock_detected:
            self.last_hot_stock_time = current_time

        # Determine target state
        if hot_stock_detected:
            target_state = ProductionState.RUNNING
        elif self.last_hot_stock_time is None:
            target_state = ProductionState.UNKNOWN
        elif current_time - self.last_hot_stock_time >= self.break_threshold_seconds:
            target_state = ProductionState.BREAK
        else:
            # Within break threshold - maintain current state or RUNNING
            target_state = (
                ProductionState.RUNNING
                if self.current_state == ProductionState.RUNNING
                else self.current_state
            )

        # Handle state transition
        if target_state != self.current_state:
            return self._transition_to(target_state, current_time, confidence)

        return None

    def _transition_to(
        self, new_state: ProductionState, current_time: float, confidence: float
    ) -> Optional[StateChange]:
        """Handle state transition with debouncing"""

        # Special case: UNKNOWN -> anything is immediate
        if self.current_state == ProductionState.UNKNOWN:
            return self._commit_transition(new_state, current_time, confidence)

        # BREAK -> RUNNING is immediate (production resumed)
        if (
            self.current_state == ProductionState.BREAK
            and new_state == ProductionState.RUNNING
        ):
            return self._commit_transition(new_state, current_time, confidence)

        # RUNNING -> BREAK requires sustained (handled by break_threshold_seconds in update())
        if (
            self.current_state == ProductionState.RUNNING
            and new_state == ProductionState.BREAK
        ):
            return self._commit_transition(new_state, current_time, confidence)

        return None

    def _commit_transition(
        self, new_state: ProductionState, current_time: float, confidence: float
    ) -> StateChange:
        """Commit a state transition"""
        previous_state = self.current_state
        duration = current_time - self.state_start_time if self.state_start_time else 0

        self.current_state = new_state
        self.state_start_time = current_time

        state_change = StateChange(
            timestamp=datetime.now(),
            previous_state=previous_state,
            new_state=new_state,
            confidence=confidence,
            duration_in_previous_seconds=duration,
        )

        logger.info(
            f"State change: {previous_state.value} -> {new_state.value} (confidence: {confidence:.1f}%)"
        )

        if self.on_state_change:
            self.on_state_change(state_change)

        return state_change

    @property
    def time_in_current_state(self) -> float:
        """Seconds in current state"""
        if self.state_start_time is None:
            return 0
        return time.time() - self.state_start_time

    @property
    def time_since_last_stock(self) -> Optional[float]:
        """Seconds since hot stock was last detected"""
        if self.last_hot_stock_time is None:
            return None
        return time.time() - self.last_hot_stock_time
