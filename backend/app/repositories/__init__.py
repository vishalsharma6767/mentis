"""Repository layer — async data access for all domain models.

Every repository exposes CRUD operations through the ``BaseRepository``
generic. No SQL or query logic leaks into services or routes.

Repositories:
  - UserRepository
  - SessionRepository
  - LessonRepository
  - TopicRepository
  - ProgressRepository
  - KnowledgeGraphRepository
  - AnalyticsRepository
  - RevisionRepository
  - MistakeRepository
  - UploadRepository
  - VoiceHistoryRepository
  - ARSessionRepository

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ARSession,
    Analytics,
    KnowledgeGraphEdge,
    Lesson,
    Mistake,
    Progress,
    RevisionQueue,
    Session,
    Topic,
    Upload,
    User,
    VoiceHistory,
)
from app.repositories.base import BaseRepository


# ── User ────────────────────────────────────────────────────────────────


class UserRepository(BaseRepository[User]):
    """CRUD for the ``users`` table."""

    model_class = User

    async def get_by_email(self, email: str) -> Optional[User]:
        return await self.get_by(email=email)

    async def get_by_appwrite_id(self, appwrite_id: str) -> Optional[User]:
        return await self.get_by(appwrite_user_id=appwrite_id)

    async def activate(self, user_id: str) -> User:
        return await self.update(user_id, {'is_active': True})

    async def deactivate(self, user_id: str) -> User:
        return await self.update(user_id, {'is_active': False})

    async def update_last_login(self, user_id: str) -> User:
        return await self.update(user_id, {'last_login_at': datetime.now(timezone.utc)})

    async def list_active(self, page: int = 1, page_size: int = 20) -> tuple[Sequence[User], int]:
        return await self.list_by(page=page, page_size=page_size, is_active=True)

    async def count_by_level(self) -> dict[str, int]:
        from sqlalchemy import func
        stmt = select(User.level, func.count()).group_by(User.level)
        result = await self.session.execute(stmt)
        return {row[0].value if hasattr(row[0], 'value') else str(row[0]): row[1] for row in result}


# ── Session ─────────────────────────────────────────────────────────────


class SessionRepository(BaseRepository[Session]):
    """CRUD for the ``sessions`` table."""

    model_class = Session

    async def get_active_session(self, user_id: str) -> Optional[Session]:
        return await self.get_by(user_id=user_id, ended_at=None)

    async def end_session(self, session_id: str) -> Session:
        return await self.update(session_id, {'ended_at': datetime.now(timezone.utc)})

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Session], int]:
        return await self.list_by(
            page=page, page_size=page_size,
            user_id=user_id, order_by='created_at', descending=True,
        )

    async def update_progress(
        self,
        session_id: str,
        topics_covered: list[str],
        problems_solved: int,
    ) -> Session:
        return await self.update(session_id, {
            'topics_covered': topics_covered,
            'problems_solved': problems_solved,
        })


# ── Lesson ──────────────────────────────────────────────────────────────


class LessonRepository(BaseRepository[Lesson]):
    """CRUD for the ``lessons`` table."""

    model_class = Lesson

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Lesson], int]:
        return await self.list_by(
            page=page, page_size=page_size,
            user_id=user_id, order_by='created_at', descending=True,
        )

    async def list_by_topic(self, topic_id: str, page: int = 1, page_size: int = 20) -> tuple[Sequence[Lesson], int]:
        return await self.list_by(page=page, page_size=page_size, topic_id=topic_id)


# ── Topic ───────────────────────────────────────────────────────────────


class TopicRepository(BaseRepository[Topic]):
    """CRUD for the ``topics`` table."""

    model_class = Topic

    async def get_by_name_subject(self, name: str, subject: str) -> Optional[Topic]:
        return await self.get_by(name=name, subject=subject)

    async def list_by_subject(self, subject: str, page: int = 1, page_size: int = 50) -> tuple[Sequence[Topic], int]:
        return await self.list_by(page=page, page_size=page_size, subject=subject)

    async def get_subtopics(self, parent_id: str) -> Sequence[Topic]:
        return await self.find(parent_topic_id=parent_id)


# ── Progress ────────────────────────────────────────────────────────────


class ProgressRepository(BaseRepository[Progress]):
    """CRUD for the ``progress`` (per-user, per-topic) table."""

    model_class = Progress

    async def get_user_topic_progress(self, user_id: str, topic_id: str) -> Optional[Progress]:
        return await self.get_by(user_id=user_id, topic_id=topic_id)

    async def list_weak_topics(self, user_id: str, threshold: float = 0.4) -> Sequence[Progress]:
        stmt = select(Progress).where(
            Progress.user_id == user_id,
            Progress.mastery_score < threshold,
        ).order_by(Progress.mastery_score.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_mastered_topics(self, user_id: str, threshold: float = 0.8) -> Sequence[Progress]:
        stmt = select(Progress).where(
            Progress.user_id == user_id,
            Progress.mastery_score >= threshold,
        ).order_by(Progress.mastery_score.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert_progress(
        self,
        user_id: str,
        topic_id: str,
        mastery_delta: float = 0.0,
        correct: bool = True,
    ) -> Progress:
        existing = await self.get_user_topic_progress(user_id, topic_id)
        if existing:
            existing.sessions_count += 1
            existing.last_practiced_at = datetime.now(timezone.utc)
            if correct:
                existing.mastery_score = min(1.0, existing.mastery_score + mastery_delta * (1.0 - existing.mastery_score))
            else:
                existing.total_mistakes += 1
                existing.mastery_score = max(0.0, existing.mastery_score - mastery_delta * 0.5)
            existing.is_mastered = existing.mastery_score >= 0.8
            await self.session.flush()
            return existing

        return await self.create({
            'user_id': user_id,
            'topic_id': topic_id,
            'mastery_score': 0.1 if correct else 0.0,
            'sessions_count': 1,
            'total_mistakes': 0 if correct else 1,
            'last_practiced_at': datetime.now(timezone.utc),
        })


# ── Knowledge Graph ────────────────────────────────────────────────────


class KnowledgeGraphRepository(BaseRepository[KnowledgeGraphEdge]):
    """CRUD for the ``knowledge_graph_edges`` table."""

    model_class = KnowledgeGraphEdge

    async def list_edges_for_user(self, user_id: str) -> Sequence[KnowledgeGraphEdge]:
        return await self.find(user_id=user_id)

    async def get_edge(
        self,
        user_id: str,
        source_topic_id: str,
        target_topic_id: str,
    ) -> Optional[KnowledgeGraphEdge]:
        return await self.get_by(
            user_id=user_id,
            source_topic_id=source_topic_id,
            target_topic_id=target_topic_id,
        )

    async def upsert_edge(
        self,
        user_id: str,
        source_topic_id: str,
        target_topic_id: str,
        edge_type: str,
        weight: float = 1.0,
    ) -> KnowledgeGraphEdge:
        return await self.upsert(
            {
                'user_id': user_id,
                'source_topic_id': source_topic_id,
                'target_topic_id': target_topic_id,
                'edge_type': edge_type,
                'weight': weight,
            },
            constraint=['user_id', 'source_topic_id', 'target_topic_id', 'edge_type'],
        )

    async def delete_user_graph(self, user_id: str) -> int:
        return await self.delete_by(user_id=user_id)


# ── Analytics ───────────────────────────────────────────────────────────


class AnalyticsRepository(BaseRepository[Analytics]):
    """CRUD for the ``analytics`` table."""

    model_class = Analytics

    async def get_by_date(self, user_id: str, date: str) -> Optional[Analytics]:
        return await self.get_by(user_id=user_id, date=date)

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 30,
    ) -> Sequence[Analytics]:
        stmt = (
            select(Analytics)
            .where(Analytics.user_id == user_id)
            .order_by(Analytics.date.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def record_session(
        self,
        user_id: str,
        date: str,
        duration_minutes: int,
        problems_attempted: int = 1,
        problems_solved: int = 0,
    ) -> Analytics:
        existing = await self.get_by_date(user_id, date)
        if existing:
            existing.total_sessions += 1
            existing.total_duration_minutes += duration_minutes
            existing.problems_attempted += problems_attempted
            existing.problems_solved += problems_solved
            await self.session.flush()
            return existing
        return await self.create({
            'user_id': user_id,
            'date': date,
            'total_sessions': 1,
            'total_duration_minutes': duration_minutes,
            'problems_attempted': problems_attempted,
            'problems_solved': problems_solved,
        })


# ── Revision Queue ─────────────────────────────────────────────────────


class RevisionRepository(BaseRepository[RevisionQueue]):
    """CRUD for the ``revision_queue`` table."""

    model_class = RevisionQueue

    async def list_due(self, user_id: str) -> Sequence[RevisionQueue]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(RevisionQueue)
            .where(RevisionQueue.user_id == user_id, RevisionQueue.due_at <= now, RevisionQueue.completed_at.is_(None))
            .order_by(RevisionQueue.due_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_overdue(self, user_id: str) -> Sequence[RevisionQueue]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(RevisionQueue)
            .where(RevisionQueue.user_id == user_id, RevisionQueue.due_at < now, RevisionQueue.completed_at.is_(None))
            .order_by(RevisionQueue.due_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_completed(self, revision_id: str) -> RevisionQueue:
        return await self.update(revision_id, {'completed_at': datetime.now(timezone.utc)})

    async def queue_revision(self, user_id: str, topic_id: str, due_at: datetime) -> RevisionQueue:
        return await self.create({
            'user_id': user_id,
            'topic_id': topic_id,
            'due_at': due_at,
        })


# ── Mistakes ────────────────────────────────────────────────────────────


class MistakeRepository(BaseRepository[Mistake]):
    """CRUD for the ``mistakes`` table."""

    model_class = Mistake

    async def list_by_user(self, user_id: str, limit: int = 20) -> Sequence[Mistake]:
        stmt = (
            select(Mistake)
            .where(Mistake.user_id == user_id)
            .order_by(Mistake.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_topic(self, user_id: str, topic_id: str, limit: int = 20) -> Sequence[Mistake]:
        stmt = (
            select(Mistake)
            .where(Mistake.user_id == user_id, Mistake.topic_id == topic_id)
            .order_by(Mistake.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_type(self, user_id: str) -> dict[str, int]:
        from sqlalchemy import func
        stmt = select(Mistake.mistake_type, func.count()).where(
            Mistake.user_id == user_id
        ).group_by(Mistake.mistake_type)
        result = await self.session.execute(stmt)
        return {row[0].value if hasattr(row[0], 'value') else str(row[0]): row[1] for row in result}


# ── Uploads ─────────────────────────────────────────────────────────────


class UploadRepository(BaseRepository[Upload]):
    """CRUD for the ``uploads`` table."""

    model_class = Upload

    async def list_by_user(self, user_id: str, page: int = 1, page_size: int = 20) -> tuple[Sequence[Upload], int]:
        return await self.list_by(page=page, page_size=page_size, user_id=user_id, order_by='created_at', descending=True)


# ── Voice History ───────────────────────────────────────────────────────


class VoiceHistoryRepository(BaseRepository[VoiceHistory]):
    """CRUD for the ``voice_history`` table."""

    model_class = VoiceHistory

    async def list_by_user(self, user_id: str, limit: int = 50) -> Sequence[VoiceHistory]:
        stmt = (
            select(VoiceHistory)
            .where(VoiceHistory.user_id == user_id)
            .order_by(VoiceHistory.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


# ── AR Sessions ─────────────────────────────────────────────────────────


class ARSessionRepository(BaseRepository[ARSession]):
    """CRUD for the ``ar_sessions`` table."""

    model_class = ARSession

    async def list_by_user(self, user_id: str, page: int = 1, page_size: int = 20) -> tuple[Sequence[ARSession], int]:
        return await self.list_by(page=page, page_size=page_size, user_id=user_id, order_by='created_at', descending=True)

    async def get_active(self, user_id: str) -> Optional[ARSession]:
        return await self.get_by(user_id=user_id, ended_at=None)



