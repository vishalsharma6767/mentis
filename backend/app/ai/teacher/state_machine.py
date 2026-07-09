"""Teacher State Machine — explicit lifecycle management.

Every session flows through a well-defined set of states. Transitions
are explicit, validated, and published as events so the Event Bus can
notify any interested module (analytics, logging, frontend push, etc.).

States follow the natural teaching cycle:
  IDLE → OBSERVING → UNDERSTANDING → PLANNING → TEACHING →
  → WAITING → CHECKING → CORRECTING/ PRAISING → ... → SESSION_COMPLETE

Usage::

    sm = TeacherStateMachine()
    await sm.transition(TeacherState.PLANNING)  # raises if invalid
    print(sm.current)  # TeacherState.PLANNING
    sm.on_transition(my_handler)  # callback on every transition
"""

import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, Optional

from app.core.events import Event, EventBus, EventType
from app.core.exceptions import AgentExecutionError
from app.core.logger import get_logger

log = get_logger(__name__)


class TeacherState(str, Enum):
    """All possible states of a teaching session.

    The state machine enforces valid transitions between these states.
    """

    IDLE = 'idle'
    OBSERVING = 'observing'
    UNDERSTANDING = 'understanding'
    PLANNING = 'planning'
    TEACHING = 'teaching'
    WAITING_FOR_STUDENT = 'waiting_for_student'
    LISTENING = 'listening'
    CHECKING = 'checking'
    CORRECTING = 'correcting'
    PRAISING = 'praising'
    GENERATING_HOMEWORK = 'generating_homework'
    SUMMARIZING = 'summarizing'
    SESSION_COMPLETE = 'session_complete'
    ERROR = 'error'


# ── Valid transition map ───────────────────────────────────────────────
# Key: current state → set of allowed next states

_TRANSITIONS: dict[TeacherState, set[TeacherState]] = {
    TeacherState.IDLE: {
        TeacherState.OBSERVING,
        TeacherState.ERROR,
    },
    TeacherState.OBSERVING: {
        TeacherState.UNDERSTANDING,
        TeacherState.IDLE,
        TeacherState.ERROR,
    },
    TeacherState.UNDERSTANDING: {
        TeacherState.PLANNING,
        TeacherState.OBSERVING,
        TeacherState.ERROR,
    },
    TeacherState.PLANNING: {
        TeacherState.TEACHING,
        TeacherState.OBSERVING,
        TeacherState.ERROR,
    },
    TeacherState.TEACHING: {
        TeacherState.WAITING_FOR_STUDENT,
        TeacherState.CHECKING,
        TeacherState.SUMMARIZING,
        TeacherState.ERROR,
    },
    TeacherState.WAITING_FOR_STUDENT: {
        TeacherState.LISTENING,
        TeacherState.CHECKING,
        TeacherState.TEACHING,
        TeacherState.ERROR,
    },
    TeacherState.LISTENING: {
        TeacherState.CHECKING,
        TeacherState.WAITING_FOR_STUDENT,
        TeacherState.ERROR,
    },
    TeacherState.CHECKING: {
        TeacherState.CORRECTING,
        TeacherState.PRAISING,
        TeacherState.TEACHING,
        TeacherState.WAITING_FOR_STUDENT,
        TeacherState.GENERATING_HOMEWORK,
        TeacherState.SUMMARIZING,
        TeacherState.ERROR,
    },
    TeacherState.CORRECTING: {
        TeacherState.TEACHING,
        TeacherState.WAITING_FOR_STUDENT,
        TeacherState.CHECKING,
        TeacherState.ERROR,
    },
    TeacherState.PRAISING: {
        TeacherState.TEACHING,
        TeacherState.CHECKING,
        TeacherState.GENERATING_HOMEWORK,
        TeacherState.SUMMARIZING,
        TeacherState.ERROR,
    },
    TeacherState.GENERATING_HOMEWORK: {
        TeacherState.SUMMARIZING,
        TeacherState.TEACHING,
        TeacherState.ERROR,
    },
    TeacherState.SUMMARIZING: {
        TeacherState.SESSION_COMPLETE,
        TeacherState.TEACHING,
        TeacherState.ERROR,
    },
    TeacherState.SESSION_COMPLETE: {
        TeacherState.IDLE,
        TeacherState.OBSERVING,
        TeacherState.ERROR,
    },
    TeacherState.ERROR: {
        TeacherState.IDLE,
        TeacherState.OBSERVING,
        TeacherState.ERROR,
    },
}

# Map each state to the event types it should publish on enter / exit
_STATE_ENTER_EVENTS: dict[TeacherState, EventType] = {
    TeacherState.IDLE: EventType.SESSION_ENDED,
    TeacherState.OBSERVING: EventType.VISION_PROCESSING_STARTED,
    TeacherState.UNDERSTANDING: EventType.TOPIC_CLASSIFIED,
    TeacherState.PLANNING: EventType.LESSON_PLANNED,
    TeacherState.TEACHING: EventType.TEACHING_STARTED,
    TeacherState.WAITING_FOR_STUDENT: EventType.STEP_COMPLETED,
    TeacherState.LISTENING: EventType.STUDENT_ANSWERED,
    TeacherState.CHECKING: EventType.CRITIC_REVIEW_STARTED,
    TeacherState.CORRECTING: EventType.CRITIC_REQUESTED_REVISION,
    TeacherState.PRAISING: EventType.CONTENT_APPROVED,
    TeacherState.GENERATING_HOMEWORK: EventType.HOMEWORK_GENERATED,
    TeacherState.SUMMARIZING: EventType.SESSION_ANALYTICS_FLUSHED,
    TeacherState.SESSION_COMPLETE: EventType.SESSION_ENDED,
    TeacherState.ERROR: EventType.SYSTEM_ERROR,
}


class TransitionCallback:
    """Signature: async def callback(from_state, to_state, context) -> None"""
    pass


TransitionHandler = Callable[[TeacherState, TeacherState, dict[str, Any]], Awaitable[None]]


class TeacherStateMachine:
    """Finite state machine for a teaching session.

    Each session (WebSocket connection) should create its own instance.
    The machine validates every transition and publishes events to the
    global EventBus so other modules can react without coupling.
    """

    def __init__(self, initial_state: TeacherState = TeacherState.IDLE) -> None:
        self._current: TeacherState = initial_state
        self._previous: Optional[TeacherState] = None
        self._started_at: float = time.monotonic()
        self._state_entered_at: float = time.monotonic()
        self._handlers: list[TransitionHandler] = []
        self._bus = EventBus.get_instance()
        self._context: dict[str, Any] = {}
        self._transition_count: int = 0

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def current(self) -> TeacherState:
        return self._current

    @property
    def previous(self) -> Optional[TeacherState]:
        return self._previous

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._started_at

    @property
    def current_state_duration(self) -> float:
        return time.monotonic() - self._state_entered_at

    @property
    def transition_count(self) -> int:
        return self._transition_count

    @property
    def is_active(self) -> bool:
        return self._current not in (TeacherState.IDLE, TeacherState.SESSION_COMPLETE, TeacherState.ERROR)

    # ── Transition ─────────────────────────────────────────────────────

    async def transition(
        self,
        target: TeacherState,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Attempt to transition to *target* state.

        Raises:
            AgentExecutionError: If the transition is not in the valid map.
        """
        allowed = _TRANSITIONS.get(self._current, set())
        if target not in allowed:
            raise AgentExecutionError(
                agent_name='state_machine',
                message=f'Invalid transition: {self._current.value} → {target.value}',
                details={
                    'from': self._current.value,
                    'to': target.value,
                    'allowed': [s.value for s in allowed],
                },
            )

        self._previous = self._current
        self._current = target
        self._state_entered_at = time.monotonic()
        self._transition_count += 1

        if context:
            self._context.update(context)

        log.info(
            'state_transition',
            from_state=self._previous.value,
            to_state=self._current.value,
            count=self._transition_count,
        )

        # Fire event bus event for this state entry
        event_type = _STATE_ENTER_EVENTS.get(self._current)
        if event_type:
            await self._bus.publish_sync(
                event_type=event_type,
                data={
                    'from_state': self._previous.value,
                    'to_state': self._current.value,
                    'context': self._context,
                    'transition_count': self._transition_count,
                },
                source='state_machine',
            )

        # Notify registered transition handlers
        for handler in self._handlers:
            try:
                await handler(self._previous, self._current, self._context)
            except Exception as exc:
                log.error('transition_handler_failed', handler=handler.__name__, error=str(exc))

    async def reset(self, context: Optional[dict[str, Any]] = None) -> None:
        """Reset to IDLE state (always valid)."""
        await self.transition(TeacherState.IDLE, context)
        self._started_at = time.monotonic()
        self._transition_count = 0

    # ── Guards ─────────────────────────────────────────────────────────

    def can_transition_to(self, target: TeacherState) -> bool:
        """Check if a transition to *target* would be valid."""
        return target in _TRANSITIONS.get(self._current, set())

    def assert_state(self, expected: TeacherState) -> None:
        """Raise if current state is not the expected state."""
        if self._current != expected:
            raise AgentExecutionError(
                agent_name='state_machine',
                message=f'Expected state {expected.value}, current is {self._current.value}',
            )

    def assert_one_of(self, *expected: TeacherState) -> None:
        """Raise if current state is not one of the expected states."""
        if self._current not in expected:
            names = ', '.join(s.value for s in expected)
            raise AgentExecutionError(
                agent_name='state_machine',
                message=f'Expected one of [{names}], current is {self._current.value}',
            )

    # ── Lifecycle hooks ────────────────────────────────────────────────

    def on_transition(self, handler: TransitionHandler) -> Callable[[], None]:
        """Register a callback invoked on every transition.

        Returns an unsubscribe callable.
        """
        self._handlers.append(handler)

        def unsubscribe() -> None:
            self._handlers.remove(handler)

        return unsubscribe

    # ── Serialization ──────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Return a serialisable snapshot of the current machine state."""
        return {
            'current_state': self._current.value,
            'previous_state': self._previous.value if self._previous else None,
            'transition_count': self._transition_count,
            'elapsed_seconds': round(self.elapsed_seconds, 2),
            'current_state_duration': round(self.current_state_duration, 2),
            'is_active': self.is_active,
        }
