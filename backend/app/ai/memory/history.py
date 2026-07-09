"""Session History Agent — records and retrieves past teaching sessions.

Stores every student-teacher interaction turn, including the problem,
solution steps, mistakes, emotions, and outcomes. Used by the
Memory Agent and Coach Agent for long-term personalisation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.core.logger import get_logger

log = get_logger(__name__)


class SessionRecord:
    """A single teaching session record."""

    def __init__(
        self,
        session_id: str,
        user_id: str,
        topic: str,
        subject: str = 'general',
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        turns: int = 0,
        problems_solved: int = 0,
        mistakes_made: int = 0,
        help_requests: int = 0,
        overall_confidence: float = 0.5,
        topics_covered: Optional[list[str]] = None,
        errors: Optional[list[dict[str, Any]]] = None,
        summary: str = '',
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.topic = topic
        self.subject = subject
        self.started_at = started_at or datetime.utcnow()
        self.ended_at = ended_at
        self.turns = turns
        self.problems_solved = problems_solved
        self.mistakes_made = mistakes_made
        self.help_requests = help_requests
        self.overall_confidence = overall_confidence
        self.topics_covered = topics_covered or []
        self.errors = errors or []
        self.summary = summary


class SessionHistoryManager:
    """Manages the history of teaching sessions for a student.

    Usage::

        history = SessionHistoryManager()
        history.record_session(session_record)
        recent = history.get_recent_sessions(user_id, limit=5)
    """

    def __init__(self) -> None:
        self._sessions: dict[str, list[SessionRecord]] = {}

    def record_session(self, record: SessionRecord) -> None:
        """Store a completed session record."""
        if record.user_id not in self._sessions:
            self._sessions[record.user_id] = []
        self._sessions[record.user_id].append(record)
        log.debug('session_recorded', user=record.user_id, topic=record.topic)

    def get_recent_sessions(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[SessionRecord]:
        """Return the most recent sessions for a user."""
        sessions = self._sessions.get(user_id, [])
        return sorted(sessions, key=lambda s: s.started_at, reverse=True)[:limit]

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """Find a session by its ID."""
        for user_sessions in self._sessions.values():
            for s in user_sessions:
                if s.session_id == session_id:
                    return s
        return None

    def get_topics_covered(self, user_id: str) -> list[str]:
        """Return all unique topics a user has studied."""
        topics: set[str] = set()
        for s in self._sessions.get(user_id, []):
            topics.update(s.topics_covered)
        return sorted(topics)

    def get_total_study_time(self, user_id: str) -> int:
        """Return total study time in seconds across all sessions."""
        total = 0
        for s in self._sessions.get(user_id, []):
            if s.ended_at and s.started_at:
                total += int((s.ended_at - s.started_at).total_seconds())
        return total
