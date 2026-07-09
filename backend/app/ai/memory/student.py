"""Student Profile Agent — manages learner profiles.

Tracks student identity, academic level, language preference,
subject-specific strengths and weaknesses, and session metadata.
This is the persistent identity layer for the Memory system.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.constants import Difficulty, Subject, TeachingLanguage
from app.core.logger import get_logger

log = get_logger(__name__)


class StudentProfile:
    """A student's persistent learning profile.

    Created once per user and updated after every session. Profiles
    are stored and retrieved via the Repository layer, not directly.
    """

    def __init__(
        self,
        user_id: str,
        display_name: str = '',
        level: Difficulty = Difficulty.INTERMEDIATE,
        preferred_language: TeachingLanguage = TeachingLanguage.HINGLISH,
        strengths: Optional[list[str]] = None,
        weaknesses: Optional[list[str]] = None,
        session_count: int = 0,
        total_lessons_completed: int = 0,
        average_confidence: float = 0.5,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> None:
        self.user_id = user_id
        self.display_name = display_name
        self.level = level
        self.preferred_language = preferred_language
        self.strengths = strengths or []
        self.weaknesses = weaknesses or []
        self.session_count = session_count
        self.total_lessons_completed = total_lessons_completed
        self.average_confidence = average_confidence
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

    def update_strength(self, topic: str, delta: float = 0.1) -> None:
        """Increase confidence in a topic (move towards strength)."""
        if topic not in self.strengths:
            self.strengths.append(topic)
        self.weaknesses = [w for w in self.weaknesses if w != topic]

    def add_weakness(self, topic: str) -> None:
        """Mark a topic as a weakness."""
        if topic not in self.weaknesses:
            self.weaknesses.append(topic)
        self.strengths = [s for s in self.strengths if s != topic]

    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'display_name': self.display_name,
            'level': self.level.value if hasattr(self.level, 'value') else str(self.level),
            'preferred_language': self.preferred_language.value if hasattr(self.preferred_language, 'value') else str(self.preferred_language),
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
            'session_count': self.session_count,
            'total_lessons_completed': self.total_lessons_completed,
            'average_confidence': self.average_confidence,
            'created_at': self.created_at.isoformat() if self.created_at else '',
            'updated_at': self.updated_at.isoformat() if self.updated_at else '',
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'StudentProfile':
        return cls(
            user_id=str(data.get('user_id', '')),
            display_name=str(data.get('display_name', '')),
            level=cls._parse_level(data.get('level', 'intermediate')),
            preferred_language=cls._parse_language(data.get('preferred_language', 'hinglish')),
            strengths=list(data.get('strengths', [])),
            weaknesses=list(data.get('weaknesses', [])),
            session_count=int(data.get('session_count', 0)),
            total_lessons_completed=int(data.get('total_lessons_completed', 0)),
            average_confidence=float(data.get('average_confidence', 0.5)),
            created_at=cls._parse_datetime(data.get('created_at')),
            updated_at=cls._parse_datetime(data.get('updated_at')),
        )

    @staticmethod
    def _parse_level(val: str) -> Difficulty:
        try:
            return Difficulty(val.lower())
        except ValueError:
            return Difficulty.INTERMEDIATE

    @staticmethod
    def _parse_language(val: str) -> TeachingLanguage:
        try:
            return TeachingLanguage(val.lower())
        except ValueError:
            return TeachingLanguage.HINGLISH

    @staticmethod
    def _parse_datetime(val: Optional[str]) -> Optional[datetime]:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None
