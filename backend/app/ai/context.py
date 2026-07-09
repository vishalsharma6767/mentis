"""Context Engine — unified student context assembly.

The Context Engine sits above the Teacher Orchestrator. Before any AI
agent runs, it assembles everything known about the student:

  - Profile & preferences (language, level, device)
  - Current session state (active lesson, step, elapsed time)
  - Knowledge graph (weak/strong concepts, mastery levels)
  - Mistake history (recent errors, patterns)
  - Revision queue (overdue topics)
  - Session history (last N sessions, performance trend)
  - Device capabilities (AR supported, input modality)
  - Current vision context (camera input, detected problem)

This rich context is passed to every downstream agent so the teaching
experience is consistent and deeply personalised.

The Context Engine also subscribes to relevant Event Bus events to
keep its cached context fresh without re-querying the database.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ai.gateway import AIGateway
from app.core.constants import (
    ConfidenceLevel,
    Difficulty,
    Subject,
    TeachingLanguage,
)
from app.core.events import Event, EventBus, EventType
from app.core.logger import get_logger
log = get_logger(__name__)


# ── Student Profile ────────────────────────────────────────────────────


@dataclass
class StudentProfile:
    """Core student profile loaded from the database."""
    user_id: str
    display_name: str = ''
    email: str = ''
    level: Difficulty = Difficulty.INTERMEDIATE
    preferred_language: TeachingLanguage = TeachingLanguage.HINGLISH
    teacher_tone: str = 'warm_and_patient'
    device_capabilities: dict[str, bool] = field(default_factory=lambda: {
        'ar_supported': False,
        'camera_supported': True,
        'voice_input_supported': True,
        'board_interaction': True,
    })
    created_at: Optional[str] = None


@dataclass
class KnowledgeState:
    """Snapshot of the student's knowledge graph."""
    weak_concepts: list[str] = field(default_factory=list)
    strong_concepts: list[str] = field(default_factory=list)
    recently_covered: list[str] = field(default_factory=list)
    mastery_by_topic: dict[str, float] = field(default_factory=dict)
    total_concepts_mastered: int = 0
    total_concepts_attempted: int = 0


@dataclass
class MistakeProfile:
    """Pattern of mistakes the student has made."""
    recent_mistakes: list[dict[str, Any]] = field(default_factory=list)
    common_error_patterns: list[str] = field(default_factory=list)
    total_mistakes: int = 0
    total_corrections: int = 0


@dataclass
class RevisionStatus:
    """What the student needs to revise."""
    overdue_topics: list[str] = field(default_factory=list)
    due_soon_topics: list[str] = field(default_factory=list)
    next_revision_due: Optional[str] = None
    total_pending_revisions: int = 0


@dataclass
class SessionHistorySummary:
    """Aggregated history of past sessions."""
    total_sessions: int = 0
    total_learning_minutes: int = 0
    average_session_duration_minutes: float = 0.0
    topics_covered: list[str] = field(default_factory=list)
    last_session_date: Optional[str] = None
    streak_days: int = 0
    performance_trend: str = 'stable'  # 'improving', 'stable', 'declining'


@dataclass
class VisionContext:
    """Current visual context from the camera/image input."""
    raw_text: str = ''
    subject: Subject = Subject.GENERAL
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    topics: list[str] = field(default_factory=list)
    detected_elements: list[str] = field(default_factory=list)
    problem_type: str = 'general'
    diagram_type: Optional[str] = None
    formulas: list[str] = field(default_factory=list)
    handwritten: bool = False
    image_base64: Optional[str] = None


@dataclass
class SessionContext:
    """Current session state."""
    session_id: str = ''
    active_lesson_topic: str = ''
    current_step: int = 0
    total_steps: int = 0
    session_started_at: float = 0.0
    elapsed_seconds: float = 0.0
    messages_exchanged: int = 0
    consecutive_correct: int = 0
    consecutive_wrong: int = 0


@dataclass
class UnifiedStudentContext:
    """Complete context assembled by the Context Engine.

    This is the single source of truth for every agent in the pipeline.
    No agent should fetch student data independently — they receive this.
    """
    profile: StudentProfile = field(default_factory=StudentProfile)
    knowledge: KnowledgeState = field(default_factory=KnowledgeState)
    mistakes: MistakeProfile = field(default_factory=MistakeProfile)
    revision: RevisionStatus = field(default_factory=RevisionStatus)
    session_history: SessionHistorySummary = field(default_factory=SessionHistorySummary)
    vision: VisionContext = field(default_factory=VisionContext)
    session: SessionContext = field(default_factory=SessionContext)

    # Raw enrichment fields for AI prompts
    weak_topics_formatted: str = ''
    strong_topics_formatted: str = ''
    recent_mistakes_formatted: str = ''
    revision_due_formatted: str = ''
    session_context_formatted: str = ''

    def format_for_agent(self) -> str:
        """Return a compact string for injection into AI system prompts."""
        parts = [
            f'Student: {self.profile.display_name or self.profile.user_id}',
            f'Level: {self.profile.level.value}',
            f'Language: {self.profile.preferred_language.value}',
            f'Tone: {self.profile.teacher_tone}',
            f'Subject: {self.vision.subject.value}',
            f'Problem: {self.vision.raw_text[:200]}',
        ]
        if self.vision.topics:
            parts.append(f'Topics: {", ".join(self.vision.topics)}')
        if self.knowledge.weak_concepts:
            parts.append(f'Weak areas: {", ".join(self.knowledge.weak_concepts[:5])}')
        if self.knowledge.strong_concepts:
            parts.append(f'Strong areas: {", ".join(self.knowledge.strong_concepts[:5])}')
        if self.knowledge.recently_covered:
            parts.append(f'Recently covered: {", ".join(self.knowledge.recently_covered[:3])}')
        if self.revision.overdue_topics:
            parts.append(f'Revision overdue: {", ".join(self.revision.overdue_topics[:3])}')
        if self.recent_mistakes_formatted:
            parts.append(f'Recent mistakes: {self.recent_mistakes_formatted}')
        parts.append(f'AR supported: {self.profile.device_capabilities.get("ar_supported", False)}')
        parts.append(f'Session: step {self.session.current_step + 1}/{self.session.total_steps}, '
                     f'{self.session.messages_exchanged} messages exchanged')

        return '\n'.join(parts)


class ContextEngine:
    """Assembles and caches student context for the teaching pipeline.

    The engine:
      1. Loads the student profile from the database (or cache).
      2. Loads the knowledge graph, mistake history, and revision queue.
      3. Attaches the current vision context.
      4. Subscribes to Event Bus events to invalidate stale cache entries.
      5. Produces a UnifiedStudentContext consumed by every AI agent.

    Usage::

        engine = ContextEngine()
        ctx = await engine.assemble(
            user_id='usr_abc',
            vision_text='Solve x^2 + 5x + 6 = 0',
        )
        # ctx is a rich UnifiedStudentContext
        orchestrator.teach(ctx)
    """

    def __init__(self) -> None:
        self._bus = EventBus.get_instance()
        self._cache: dict[str, UnifiedStudentContext] = {}
        self._cache_ttl: float = 120.0  # seconds
        self._cache_timestamps: dict[str, float] = {}
        self._gateway: Optional[AIGateway] = None

        # Subscribe to events that should invalidate cache
        self._bus.subscribe(EventType.MEMORY_UPDATED, self._on_memory_updated)
        self._bus.subscribe(EventType.KNOWLEDGE_GRAPH_UPDATED, self._on_knowledge_updated)
        self._bus.subscribe(EventType.STUDENT_ANSWERED, self._on_student_answered)
        self._bus.subscribe(EventType.SESSION_ENDED, self._on_session_ended)
        self._bus.subscribe(EventType.PROBLEM_DETECTED, self._on_problem_detected)

    # ── Public API ─────────────────────────────────────────────────────

    async def assemble(
        self,
        user_id: str,
        session_id: str = '',
        vision_text: str = '',
        vision_image_base64: Optional[str] = None,
        force_refresh: bool = False,
    ) -> UnifiedStudentContext:
        """Assemble the full student context.

        Uses a cached context if available and not expired, unless
        ``force_refresh`` is True.
        """
        cache_key = f'{user_id}:{session_id}'

        if not force_refresh and cache_key in self._cache:
            cached = self._cache[cache_key]
            age = time.monotonic() - self._cache_timestamps.get(cache_key, 0)
            if age < self._cache_ttl:
                cached.vision.raw_text = vision_text
                cached.vision.image_base64 = vision_image_base64
                return cached

        ctx = UnifiedStudentContext()

        # 1. Load student profile
        ctx.profile = await self._load_profile(user_id)

        # 2. Load knowledge state
        ctx.knowledge = await self._load_knowledge(user_id)

        # 3. Load mistakes
        ctx.mistakes = await self._load_mistakes(user_id)

        # 4. Load revision status
        ctx.revision = await self._load_revision(user_id)

        # 5. Load session history
        ctx.session_history = await self._load_session_history(user_id)

        # 6. Attach vision context
        await self._attach_vision_context(ctx, vision_text, vision_image_base64)

        # 7. Attach session state
        ctx.session.session_id = session_id
        ctx.session.session_started_at = time.time()

        # 8. Pre-compute formatted strings for prompt injection
        ctx.weak_topics_formatted = ', '.join(ctx.knowledge.weak_concepts[:5]) if ctx.knowledge.weak_concepts else 'none identified'
        ctx.strong_topics_formatted = ', '.join(ctx.knowledge.strong_concepts[:5]) if ctx.knowledge.strong_concepts else 'none identified'
        ctx.recent_mistakes_formatted = self._format_mistakes(ctx.mistakes.recent_mistakes[:3])
        ctx.revision_due_formatted = ', '.join(ctx.revision.overdue_topics[:3] + ctx.revision.due_soon_topics[:2]) if ctx.revision.overdue_topics or ctx.revision.due_soon_topics else 'none'

        # Cache it
        self._cache[cache_key] = ctx
        self._cache_timestamps[cache_key] = time.monotonic()

        # Publish context assembled event
        await self._bus.publish_sync(
            EventType.SESSION_STARTED,
            data={
                'user_id': user_id,
                'session_id': session_id,
                'topics': ctx.vision.topics,
                'subject': ctx.vision.subject.value,
                'weak_topics': ctx.knowledge.weak_concepts,
            },
            source='context_engine',
        )

        return ctx

    def invalidate(self, user_id: str, session_id: str = '') -> None:
        """Force cache invalidation for a user."""
        key = f'{user_id}:{session_id}'
        self._cache.pop(key, None)
        self._cache_timestamps.pop(key, None)

    def get_cached(self, user_id: str, session_id: str = '') -> Optional[UnifiedStudentContext]:
        key = f'{user_id}:{session_id}'
        return self._cache.get(key)

    # ── Data loaders (pluggable: DB → cache → fallback) ───────────────

    async def _load_profile(self, user_id: str) -> StudentProfile:
        # TODO: Load from database via UserRepository
        # For now, return a sensible default based on user_id
        return StudentProfile(
            user_id=user_id,
            display_name=user_id,
            level=Difficulty.INTERMEDIATE,
            preferred_language=TeachingLanguage.HINGLISH,
        )

    async def _load_knowledge(self, user_id: str) -> KnowledgeState:
        # TODO: Load from KnowledgeGraphRepository
        return KnowledgeState()

    async def _load_mistakes(self, user_id: str) -> MistakeProfile:
        # TODO: Load from MistakeRepository
        return MistakeProfile()

    async def _load_revision(self, user_id: str) -> RevisionStatus:
        # TODO: Load from RevisionRepository
        return RevisionStatus()

    async def _load_session_history(self, user_id: str) -> SessionHistorySummary:
        # TODO: Load from AnalyticsRepository
        return SessionHistorySummary()

    async def _attach_vision_context(
        self,
        ctx: UnifiedStudentContext,
        text: str,
        image_base64: Optional[str],
    ) -> None:
        """Parse the vision input and attach it to the context.

        For text-only, we do quick topic extraction inline.
        For images, the Vision Pipeline would be called.
        """
        ctx.vision.raw_text = text
        ctx.vision.image_base64 = image_base64

        if not text:
            return

        lower = text.lower()

        # Quick subject detection
        subject_keywords = {
            Subject.MATH: ['solve', 'equation', 'calculate', 'derivative', 'integral', 'matrix',
                           'x^', 'y =', 'prove that', 'find the', 'sum of', 'root', 'factor'],
            Subject.PHYSICS: ['force', 'velocity', 'acceleration', 'energy', 'wave', 'circuit',
                              'newton', 'gravity', 'electric', 'magnetic', 'lens', 'mirror'],
            Subject.CHEMISTRY: ['reaction', 'element', 'compound', 'molecule', 'acid', 'base',
                                'oxidation', 'mole', 'concentration', 'bond'],
            Subject.BIOLOGY: ['cell', 'dna', 'organism', 'photosynthesis', 'mitosis', 'enzyme',
                              'protein', 'gene', 'tissue', 'organ'],
            Subject.CODING: ['function', 'class', 'algorithm', 'loop', 'array', 'variable',
                             'sort', 'search', 'compile', 'debug'],
        }
        for subj, kws in subject_keywords.items():
            if any(kw in lower for kw in kws):
                ctx.vision.subject = subj
                break

        # Topic extraction via LLM for non-trivial input
        if len(text) > 20:
            await self._enrich_vision_topics(ctx, text)

    async def _enrich_vision_topics(self, ctx: UnifiedStudentContext, text: str) -> None:
        """Use a lightweight LLM call to extract topics and difficulty."""
        try:
            if self._gateway is None:
                self._gateway = await AIGateway.get_instance()
            response = await self._gateway.execute(
                messages=[
                    {
                        'role': 'system',
                        'content': 'Extract the educational topic, subject, and difficulty from the student\'s input. '
                                   'Respond in JSON: {"topics": [str], "subject": "math|physics|chemistry|biology|coding|general", '
                                   '"difficulty": "beginner|intermediate|advanced", "problem_type": "str"}',
                    },
                    {'role': 'user', 'content': f'Student problem: {text[:500]}'},
                ],
                expect_json=True,
                max_tokens=256,
                temperature=0.3,
            )
            result = json.loads(response.text)
            topics = result.get('topics', [])
            if topics:
                ctx.vision.topics = topics if isinstance(topics, list) else [str(topics)]
            if result.get('subject'):
                try:
                    ctx.vision.subject = Subject(result['subject'])
                except ValueError:
                    pass
            if result.get('difficulty'):
                try:
                    ctx.vision.difficulty = Difficulty(result['difficulty'])
                except ValueError:
                    pass
            if result.get('problem_type'):
                ctx.vision.problem_type = result['problem_type']
        except Exception as exc:
            log.debug('vision_enrichment_failed', error=str(exc))

    # ── Event handlers (cache invalidation) ────────────────────────────

    async def _on_memory_updated(self, event: Event) -> None:
        user_id = event.data.get('user_id', '')
        if user_id:
            self.invalidate(user_id)

    async def _on_knowledge_updated(self, event: Event) -> None:
        user_id = event.data.get('user_id', '')
        if user_id:
            self.invalidate(user_id)

    async def _on_student_answered(self, event: Event) -> None:
        user_id = event.data.get('user_id', '')
        session_id = event.data.get('session_id', '')
        key = f'{user_id}:{session_id}'
        cached = self._cache.get(key)
        if cached:
            cached.session.messages_exchanged += 1
            correct = event.data.get('correct', False)
            if correct:
                cached.session.consecutive_correct += 1
                cached.session.consecutive_wrong = 0
            else:
                cached.session.consecutive_wrong += 1
                cached.session.consecutive_correct = 0

    async def _on_session_ended(self, event: Event) -> None:
        user_id = event.data.get('user_id', '')
        session_id = event.data.get('session_id', '')
        if user_id:
            self.invalidate(user_id, session_id)

    async def _on_problem_detected(self, event: Event) -> None:
        user_id = event.data.get('user_id', '')
        session_id = event.data.get('session_id', '')
        key = f'{user_id}:{session_id}'
        cached = self._cache.get(key)
        if cached:
            cached.vision.raw_text = event.data.get('raw_text', cached.vision.raw_text)
            cached.vision.topics = event.data.get('topics', cached.vision.topics)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _format_mistakes(mistakes: list[dict[str, Any]]) -> str:
        if not mistakes:
            return 'none'
        return '; '.join(
            f'{m.get("topic", "unknown")}: {m.get("description", "")[:60]}'
            for m in mistakes
        )
