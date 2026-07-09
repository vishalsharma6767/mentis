"""SQLAlchemy 2.0 ORM models for Mentis.

Every table has ``id`` (UUID str), ``created_at``, ``updated_at``.
All relationships use ``lazy='selectin'`` for eager-loading safety.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Enum as SAEnum,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    Difficulty,
    Subject,
    ConfidenceLevel,
    MistakeType,
    KnowledgeEdgeType,
    StudentLevel,
    TeachingLanguage,
    TeacherTone,
)
from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


# ── Mixins ─────────────────────────────────────────────────────────────


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` to any model."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


# ══════════════════════════════════════════════════════════════════════════
# USER
# ══════════════════════════════════════════════════════════════════════════


class User(TimestampMixin, Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    appwrite_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default='')
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Profile
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    student_level: Mapped[StudentLevel] = mapped_column(SAEnum(StudentLevel), default=StudentLevel.SCHOOL, nullable=False)
    preferred_language: Mapped[TeachingLanguage] = mapped_column(SAEnum(TeachingLanguage), default=TeachingLanguage.HINGLISH, nullable=False)
    preferred_tone: Mapped[TeacherTone] = mapped_column(SAEnum(TeacherTone), default=TeacherTone.WARM_AND_PATIENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    sessions: Mapped[list['Session']] = relationship('Session', back_populates='user', lazy='selectin')
    progress_records: Mapped[list['Progress']] = relationship('Progress', back_populates='user', lazy='selectin')
    mistakes: Mapped[list['Mistake']] = relationship('Mistake', back_populates='user', lazy='selectin')
    knowledge_graph: Mapped[list['KnowledgeGraphEdge']] = relationship('KnowledgeGraphEdge', back_populates='user', lazy='selectin')
    revision_queue: Mapped[list['RevisionQueue']] = relationship('RevisionQueue', back_populates='user', lazy='selectin')

    def __repr__(self) -> str:
        return f'<User {self.email}>'


# ══════════════════════════════════════════════════════════════════════════
# SESSION
# ══════════════════════════════════════════════════════════════════════════


class Session(TimestampMixin, Base):
    __tablename__ = 'sessions'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    subject: Mapped[Subject] = mapped_column(SAEnum(Subject), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(SAEnum(Difficulty), default=Difficulty.INTERMEDIATE, nullable=False)
    problem_text: Mapped[str] = mapped_column(Text, nullable=False, default='')
    problem_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default='active', nullable=False)  # active | paused | completed | abandoned
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    steps_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_after: Mapped[Optional[ConfidenceLevel]] = mapped_column(SAEnum(ConfidenceLevel), nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lesson_plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)

    user: Mapped['User'] = relationship('User', back_populates='sessions')
    lessons: Mapped[list['Lesson']] = relationship('Lesson', back_populates='session', lazy='selectin', cascade='all, delete-orphan')
    ar_sessions: Mapped[list['ARSession']] = relationship('ARSession', back_populates='session', lazy='selectin', cascade='all, delete-orphan')
    voice_history: Mapped[list['VoiceHistory']] = relationship('VoiceHistory', back_populates='session', lazy='selectin', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_sessions_user_status', 'user_id', 'status'),
    )

    def __repr__(self) -> str:
        return f'<Session {self.id[:8]} {self.subject.value}>'


# ══════════════════════════════════════════════════════════════════════════
# LESSON
# ══════════════════════════════════════════════════════════════════════════


class Lesson(TimestampMixin, Base):
    __tablename__ = 'lessons'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey('sessions.id'), nullable=False, index=True)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)  # concept | example | checkpoint | etc
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default='')
    board_actions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    ar_actions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    speech_ssml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quiz_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quiz_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    student_answered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    student_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    hint_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    session: Mapped['Session'] = relationship('Session', back_populates='lessons')

    __table_args__ = (
        UniqueConstraint('session_id', 'step_number', name='uq_lesson_step'),
    )

    def __repr__(self) -> str:
        return f'<Lesson {self.id[:8]} step={self.step_number} phase={self.phase}>'


# ══════════════════════════════════════════════════════════════════════════
# TOPIC
# ══════════════════════════════════════════════════════════════════════════


class Topic(TimestampMixin, Base):
    __tablename__ = 'topics'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Subject] = mapped_column(SAEnum(Subject), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_topic_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey('topics.id'), nullable=True)
    difficulty: Mapped[Difficulty] = mapped_column(SAEnum(Difficulty), default=Difficulty.INTERMEDIATE, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    parent: Mapped[Optional['Topic']] = relationship('Topic', remote_side='Topic.id', backref='subtopics')

    __table_args__ = (
        UniqueConstraint('name', 'subject', name='uq_topic_name_subject'),
    )

    def __repr__(self) -> str:
        return f'<Topic {self.name} ({self.subject.value})>'


# ══════════════════════════════════════════════════════════════════════════
# PROGRESS (per-user, per-topic)
# ══════════════════════════════════════════════════════════════════════════


class Progress(TimestampMixin, Base):
    __tablename__ = 'progress'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    topic_id: Mapped[str] = mapped_column(String(64), ForeignKey('topics.id'), nullable=False)
    confidence: Mapped[ConfidenceLevel] = mapped_column(SAEnum(ConfidenceLevel), default=ConfidenceLevel.MEDIUM, nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_mistakes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_practiced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_mastered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0.0 – 1.0

    user: Mapped['User'] = relationship('User', back_populates='progress_records')
    topic: Mapped['Topic'] = relationship('Topic')

    __table_args__ = (
        UniqueConstraint('user_id', 'topic_id', name='uq_progress_user_topic'),
        Index('idx_progress_mastery', 'user_id', 'is_mastered'),
    )

    def __repr__(self) -> str:
        return f'<Progress user={self.user_id[:8]} topic={self.topic_id[:8]} score={self.mastery_score:.2f}>'


# ══════════════════════════════════════════════════════════════════════════
# MISTAKE
# ══════════════════════════════════════════════════════════════════════════


class Mistake(TimestampMixin, Base):
    __tablename__ = 'mistakes'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey('sessions.id'), nullable=True)
    topic_id: Mapped[str] = mapped_column(String(64), ForeignKey('topics.id'), nullable=True)
    mistake_type: Mapped[MistakeType] = mapped_column(SAEnum(MistakeType), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    correct_approach: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lesson_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    was_repeated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped['User'] = relationship('User', back_populates='mistakes')

    __table_args__ = (
        Index('idx_mistakes_user_type', 'user_id', 'mistake_type'),
    )

    def __repr__(self) -> str:
        return f'<Mistake {self.id[:8]} type={self.mistake_type.value}>'


# ══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE GRAPH EDGE
# ══════════════════════════════════════════════════════════════════════════


class KnowledgeGraphEdge(TimestampMixin, Base):
    __tablename__ = 'knowledge_graph_edges'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    source_topic_id: Mapped[str] = mapped_column(String(64), ForeignKey('topics.id'), nullable=False)
    target_topic_id: Mapped[str] = mapped_column(String(64), ForeignKey('topics.id'), nullable=False)
    edge_type: Mapped[KnowledgeEdgeType] = mapped_column(SAEnum(KnowledgeEdgeType), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)  # strength of connection

    user: Mapped['User'] = relationship('User', back_populates='knowledge_graph')
    source_topic: Mapped['Topic'] = relationship('Topic', foreign_keys=[source_topic_id])
    target_topic: Mapped['Topic'] = relationship('Topic', foreign_keys=[target_topic_id])

    __table_args__ = (
        UniqueConstraint('user_id', 'source_topic_id', 'target_topic_id', 'edge_type', name='uq_knowledge_edge'),
    )

    def __repr__(self) -> str:
        return f'<KGEdge {self.source_topic_id[:8]} -> {self.target_topic_id[:8]} [{self.edge_type.value}]>'


# ══════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════


class Analytics(TimestampMixin, Base):
    __tablename__ = 'analytics'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    total_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problems_attempted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problems_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mistakes_made: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hints_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subjects_practiced: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    extra_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_analytics_user_date'),
        Index('idx_analytics_date', 'date'),
    )

    def __repr__(self) -> str:
        return f'<Analytics user={self.user_id[:8]} date={self.date}>'


# ══════════════════════════════════════════════════════════════════════════
# REVISION QUEUE
# ══════════════════════════════════════════════════════════════════════════


class RevisionQueue(TimestampMixin, Base):
    __tablename__ = 'revision_queue'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    topic_id: Mapped[str] = mapped_column(String(64), ForeignKey('topics.id'), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # spaced repetition interval
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5, nullable=False)
    times_reviewed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 – 1.0

    user: Mapped['User'] = relationship('User', back_populates='revision_queue')
    topic: Mapped['Topic'] = relationship('Topic')

    __table_args__ = (
        Index('idx_revision_due', 'user_id', 'due_at'),
    )

    def __repr__(self) -> str:
        return f'<RevisionQueue {self.topic_id[:8]} due={self.due_at.date()}>'


# ══════════════════════════════════════════════════════════════════════════
# UPLOAD
# ══════════════════════════════════════════════════════════════════════════


class Upload(TimestampMixin, Base):
    __tablename__ = 'uploads'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f'<Upload {self.original_filename} ({self.size_bytes} bytes)>'


# ══════════════════════════════════════════════════════════════════════════
# VOICE HISTORY
# ══════════════════════════════════════════════════════════════════════════


class VoiceHistory(TimestampMixin, Base):
    __tablename__ = 'voice_history'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey('sessions.id'), nullable=False, index=True)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)  # 'teacher' | 'student'
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ssml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emotion: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    session: Mapped['Session'] = relationship('Session', back_populates='voice_history')

    def __repr__(self) -> str:
        return f'<VoiceHistory {self.speaker}: {self.text[:40]}...>'


# ══════════════════════════════════════════════════════════════════════════
# AR SESSION
# ══════════════════════════════════════════════════════════════════════════


class ARSession(TimestampMixin, Base):
    __tablename__ = 'ar_sessions'

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey('sessions.id'), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)  # write | writeln | line | arrow | circle | clear | highlight
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    animation: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    anchor_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    world_coordinates: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    session: Mapped['Session'] = relationship('Session', back_populates='ar_sessions')

    __table_args__ = (
        Index('idx_ar_session_order', 'session_id', 'order_index'),
    )

    def __repr__(self) -> str:
        return f'<ARSession {self.action_type} #{self.order_index}>'
