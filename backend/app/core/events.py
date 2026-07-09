"""Internal event bus for decoupled inter-module communication.

Every agent, service, and engine communicates through events rather than
direct calls. This eliminates coupling between pipeline stages and makes
the system extensible: new modules simply subscribe to the events they
need without modifying existing code.

Usage::

    # Subscribe
    bus = EventBus.get_instance()
    bus.subscribe(EventType.LESSON_STARTED, my_handler)

    # Publish
    await bus.publish(Event(EventType.LESSON_STARTED, data={...}))

Event flow follows a fire-and-forget pattern. Handlers run concurrently
via asyncio.gather. A failed handler never blocks other handlers.
"""

import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.core.logger import get_logger

log = get_logger(__name__)

# Type alias for an async event handler
EventHandler = Callable[['Event'], Awaitable[None]]


class EventType(str, Enum):
    """All event types in the system.

    Naming convention: <Actor>_<Action>_<Target>
    """

    # ── Vision Pipeline ────────────────────────────────────────────────
    PROBLEM_DETECTED = 'problem_detected'
    VISION_PROCESSING_STARTED = 'vision_processing_started'
    VISION_PROCESSING_COMPLETED = 'vision_processing_completed'
    OCR_COMPLETED = 'ocr_completed'
    FORMULA_DETECTED = 'formula_detected'
    DIAGRAM_DETECTED = 'diagram_detected'
    TOPIC_CLASSIFIED = 'topic_classified'
    DIFFICULTY_ESTIMATED = 'difficulty_estimated'

    # ── Lesson Lifecycle ───────────────────────────────────────────────
    LESSON_STARTED = 'lesson_started'
    LESSON_PLANNED = 'lesson_planned'
    LESSON_PAUSED = 'lesson_paused'
    LESSON_RESUMED = 'lesson_resumed'
    LESSON_COMPLETED = 'lesson_completed'
    LESSON_FAILED = 'lesson_failed'

    # ── Teaching Pipeline ──────────────────────────────────────────────
    TEACHING_STARTED = 'teaching_started'
    TEACHING_COMPLETED = 'teaching_completed'
    STEP_STARTED = 'step_started'
    STEP_COMPLETED = 'step_completed'
    EXPLANATION_GENERATED = 'explanation_generated'
    ANALOGY_PROVIDED = 'analogy_provided'
    EXAMPLE_SHOWN = 'example_shown'

    # ── Student Interaction ────────────────────────────────────────────
    STUDENT_ANSWERED = 'student_answered'
    STUDENT_ASKED_DOUBT = 'student_asked_doubt'
    STUDENT_REQUESTED_HINT = 'student_requested_hint'
    STUDENT_HESITATED = 'student_hesitated'
    STUDENT_CORRECT = 'student_correct'
    STUDENT_INCORRECT = 'student_incorrect'
    STUDENT_DISENGAGED = 'student_disengaged'
    STUDENT_TIMED_OUT = 'student_timed_out'

    # ── Critic & Quality ───────────────────────────────────────────────
    CRITIC_REVIEW_STARTED = 'critic_review_started'
    CRITIC_REVIEW_COMPLETED = 'critic_review_completed'
    CRITIC_REQUESTED_REVISION = 'critic_requested_revision'
    CONTENT_APPROVED = 'content_approved'
    CONTENT_REJECTED = 'content_rejected'

    # ── Coach & Adaptation ─────────────────────────────────────────────
    COACH_DECISION_MADE = 'coach_decision_made'
    ADAPTATION_TRIGGERED = 'adaptation_triggered'
    DIFFICULTY_ADJUSTED = 'difficulty_adjusted'
    PACE_CHANGED = 'pace_changed'

    # ── AR Engine ──────────────────────────────────────────────────────
    AR_RENDER_STARTED = 'ar_render_started'
    AR_RENDER_COMPLETED = 'ar_render_completed'
    AR_ANCHOR_CREATED = 'ar_anchor_created'
    AR_ANIMATION_PLAYED = 'ar_animation_played'
    AR_GESTURE_DETECTED = 'ar_gesture_detected'
    AR_LAYER_CHANGED = 'ar_layer_changed'

    # ── Speech / TTS ───────────────────────────────────────────────────
    SPEECH_GENERATION_STARTED = 'speech_generation_started'
    SPEECH_GENERATION_COMPLETED = 'speech_generation_completed'
    SPEECH_PLAYBACK_STARTED = 'speech_playback_started'
    SPEECH_PLAYBACK_FINISHED = 'speech_playback_finished'

    # ── Memory & Knowledge Graph ───────────────────────────────────────
    MEMORY_UPDATED = 'memory_updated'
    KNOWLEDGE_GRAPH_UPDATED = 'knowledge_graph_updated'
    TOPIC_MASTERED = 'topic_mastered'
    TOPIC_STRUGGLED = 'topic_struggled'
    REVISION_QUEUED = 'revision_queued'
    REVISION_COMPLETED = 'revision_completed'

    # ── Analytics ──────────────────────────────────────────────────────
    ANALYTICS_UPDATED = 'analytics_updated'
    PERFORMANCE_METRIC_RECORDED = 'performance_metric_recorded'
    SESSION_ANALYTICS_FLUSHED = 'session_analytics_flushed'

    # ── Homework & Quiz ────────────────────────────────────────────────
    HOMEWORK_GENERATED = 'homework_generated'
    QUIZ_GENERATED = 'quiz_generated'
    QUIZ_ATTEMPTED = 'quiz_attempted'
    QUIZ_SCORED = 'quiz_scored'

    # ── Session Management ─────────────────────────────────────────────
    SESSION_STARTED = 'session_started'
    SESSION_ENDED = 'session_ended'
    SESSION_INTERRUPTED = 'session_interrupted'
    USER_CONNECTED = 'user_connected'
    USER_DISCONNECTED = 'user_disconnected'

    # ── System ─────────────────────────────────────────────────────────
    SYSTEM_ERROR = 'system_error'
    PROVIDER_FAILOVER = 'provider_failover'
    CACHE_INVALIDATED = 'cache_invalidated'
    CONFIGURATION_CHANGED = 'configuration_changed'


@dataclass
class Event:
    """A single event instance flowing through the bus.

    Attributes:
        type: The event type identifier.
        data: Arbitrary payload associated with the event.
        id: Unique event ID for tracing and deduplication.
        timestamp: Unix timestamp (seconds) when the event was created.
        source: Optional name of the component that published this event.
        correlation_id: Optional ID to group related events together.
    """
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    correlation_id: Optional[str] = None


class EventBus:
    """Async pub/sub event bus — singleton.

    Thread-safe for single-event-loop usage. Handlers are awaited
    concurrently via asyncio.gather. A failing handler never propagates
    its exception or blocks other handlers from running.
    """

    _instance: Optional['EventBus'] = None

    def __new__(cls) -> 'EventBus':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: dict[EventType, list[_SubscriptionEntry]] = defaultdict(list)
            cls._instance._wildcard_subscribers: list[EventHandler] = []
            cls._instance._history: list[Event] = []
            cls._instance._max_history = 500
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'EventBus':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
        source_filter: Optional[str] = None,
    ) -> Callable[[], None]:
        """Register a handler for a specific event type.

        Args:
            event_type: The event type to subscribe to.
            handler: An async callable accepting an Event.
            source_filter: If set, only events from this source are delivered.

        Returns:
            A callable that unsubscribes the handler when invoked.
        """
        entry = _SubscriptionEntry(handler=handler, source_filter=source_filter)
        self._subscribers[event_type].append(entry)
        log.debug('subscriber_registered', event_type=event_type.value, handler=handler.__name__)

        def unsubscribe() -> None:
            self._subscribers[event_type].remove(entry)
            log.debug('subscriber_unregistered', event_type=event_type.value, handler=handler.__name__)

        return unsubscribe

    def subscribe_all(self, handler: EventHandler) -> Callable[[], None]:
        """Register a handler that receives ALL events.

        Useful for logging, monitoring, and analytics sinks.
        """
        self._wildcard_subscribers.append(handler)

        def unsubscribe() -> None:
            self._wildcard_subscribers.remove(handler)

        return unsubscribe

    async def publish(self, event: Event) -> None:
        """Publish an event to all registered handlers.

        Handlers are awaited concurrently. Individual handler failures
        are logged but never raised — one broken handler cannot crash
        the system.
        """
        self._add_to_history(event)
        log.debug('event_published', type=event.type.value, event_id=event.id)

        handlers: list[EventHandler] = list(self._wildcard_subscribers)

        specific = self._subscribers.get(event.type, [])
        for entry in specific:
            if entry.source_filter is None or entry.source_filter == event.source:
                handlers.append(entry.handler)

        if not handlers:
            return

        tasks = [handler(event) for handler in handlers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error(
                    'event_handler_failed',
                    handler=handlers[i].__name__,
                    event_type=event.type.value,
                    error=str(result),
                    exc_info=result,
                )

    async def publish_sync(
        self,
        event_type: EventType,
        data: Optional[dict[str, Any]] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Event:
        """Convenience method: create and publish an event in one call."""
        event = Event(
            type=event_type,
            data=data or {},
            source=source,
            correlation_id=correlation_id,
        )
        await self.publish(event)
        return event

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 50,
    ) -> list[Event]:
        """Return recent events, optionally filtered by type."""
        if event_type is None:
            return self._history[-limit:]
        return [e for e in self._history if e.type == event_type][-limit:]

    def clear_history(self) -> None:
        self._history.clear()

    def _add_to_history(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]


@dataclass
class _SubscriptionEntry:
    handler: EventHandler
    source_filter: Optional[str] = None
