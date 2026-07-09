"""Progress Tracker Agent — monitors topic mastery over time.

Tracks each student's progress per topic: mastery level, mistake count,
session frequency, revision intervals, and confidence estimates.
Used by the Planner and Coach to adapt lessons.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.core.constants import ConfidenceLevel, Difficulty
from app.core.logger import get_logger

log = get_logger(__name__)

MASTERY_THRESHOLD = 0.8
REVISION_BASE_INTERVAL_DAYS = 1
REVISION_MAX_INTERVAL_DAYS = 30


class TopicProgress:
    """Mastery tracking for a single topic."""

    def __init__(
        self,
        user_id: str,
        topic: str,
        mastery: float = 0.0,
        mistakes: int = 0,
        sessions_count: int = 0,
        last_practiced: Optional[datetime] = None,
        next_revision: Optional[datetime] = None,
        confidence: ConfidenceLevel = ConfidenceLevel.LOW,
    ) -> None:
        self.user_id = user_id
        self.topic = topic
        self.mastery = mastery
        self.mistakes = mistakes
        self.sessions_count = sessions_count
        self.last_practiced = last_practiced
        self.next_revision = next_revision
        self.confidence = confidence

    @property
    def is_mastered(self) -> bool:
        return self.mastery >= MASTERY_THRESHOLD

    @property
    def needs_revision(self) -> bool:
        if self.next_revision is None:
            return True
        return datetime.utcnow() >= self.next_revision

    def record_practice(self, correct: bool, confidence_delta: float = 0.1) -> None:
        """Update progress after a practice session."""
        self.sessions_count += 1
        self.last_practiced = datetime.utcnow()

        if correct:
            self.mastery = min(1.0, self.mastery + confidence_delta)
        else:
            self.mistakes += 1
            self.mastery = max(0.0, self.mastery - confidence_delta * 0.5)

        self._update_confidence()
        self._schedule_revision()

    def _update_confidence(self) -> None:
        if self.mastery >= 0.8:
            self.confidence = ConfidenceLevel.HIGH
        elif self.mastery >= 0.5:
            self.confidence = ConfidenceLevel.MEDIUM
        else:
            self.confidence = ConfidenceLevel.LOW

    def _schedule_revision(self) -> None:
        if self.mastery >= MASTERY_THRESHOLD:
            interval = min(REVISION_MAX_INTERVAL_DAYS, int(REVISION_BASE_INTERVAL_DAYS * (1 / max(self.mastery, 0.1))))
        else:
            interval = REVISION_BASE_INTERVAL_DAYS
        self.next_revision = datetime.utcnow() + timedelta(days=interval)


class ProgressTracker:
    """Manages topic-level progress for a student across all subjects.

    Usage::

        tracker = ProgressTracker()
        tracker.record_practice(user_id, topic, correct=True)
        mastery = tracker.get_mastery(user_id, topic)
        due = tracker.get_revision_due(user_id)
    """

    def __init__(self) -> None:
        self._progress: dict[str, dict[str, TopicProgress]] = {}

    def record_practice(
        self,
        user_id: str,
        topic: str,
        correct: bool,
        confidence_delta: float = 0.1,
    ) -> TopicProgress:
        """Record a practice result and update the topic progress."""
        prog = self._get_or_create(user_id, topic)
        prog.record_practice(correct, confidence_delta)
        return prog

    def get_mastery(self, user_id: str, topic: str) -> float:
        """Return mastery level (0.0-1.0) for a topic."""
        prog = self._get_or_create(user_id, topic)
        return prog.mastery

    def get_revision_due(self, user_id: str) -> list[TopicProgress]:
        """Return all topics that need revision."""
        topics = self._progress.get(user_id, {}).values()
        return [t for t in topics if t.needs_revision]

    def get_weak_topics(self, user_id: str, threshold: float = 0.4) -> list[TopicProgress]:
        """Return topics with low mastery scores."""
        topics = self._progress.get(user_id, {}).values()
        return [t for t in topics if t.mastery < threshold]

    def get_strong_topics(self, user_id: str, threshold: float = 0.8) -> list[TopicProgress]:
        """Return topics with high mastery scores."""
        topics = self._progress.get(user_id, {}).values()
        return [t for t in topics if t.mastery >= threshold]

    def get_all_topics(self, user_id: str) -> dict[str, TopicProgress]:
        """Return all tracked topics for a user."""
        return self._progress.get(user_id, {})

    def _get_or_create(self, user_id: str, topic: str) -> TopicProgress:
        if user_id not in self._progress:
            self._progress[user_id] = {}
        if topic not in self._progress[user_id]:
            self._progress[user_id][topic] = TopicProgress(user_id=user_id, topic=topic)
        return self._progress[user_id][topic]
