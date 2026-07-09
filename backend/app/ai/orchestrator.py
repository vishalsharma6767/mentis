"""Teacher Orchestrator — central pipeline coordinator.

The Orchestrator replaces TeacherBrain. It does NOT teach directly —
it *coordinates* the teaching pipeline:

  1. Receives UnifiedStudentContext from the Context Engine
  2. Transitions the State Machine through the teaching lifecycle
  3. Calls each agent in order (Vision → Planner → Teacher → Critic →
     Dialogue → Speech → AR → Memory → Analytics → Composer)
  4. Publishes events at every stage for observability and extensibility
  5. Handles errors gracefully with fallback paths

Every agent call is isolated. If one agent fails, the orchestrator
decides whether to retry, skip, or abort — it never crashes.
"""

import time
from typing import Any, Optional

from app.ai.context import UnifiedStudentContext
from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.coach import CoachAgent
from app.ai.teacher.critic import CriticAgent
from app.ai.teacher.dialogue import DialogueManager
from app.ai.teacher.emotion import detect_emotion
from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.planner import PlannerAgent
from app.ai.teacher.responder import ResponseComposer
from app.ai.teacher.teacher import TeacherAgent
from app.ai.teacher.schemas import (
    ARPlan,
    CoachingDecision,
    CriticOutput,
    PlannerOutput,
    SpeechPlan,
    TeacherOutput,
    TeacherResponse,
    VisionOutput,
)
from app.ai.teacher.state_machine import TeacherState, TeacherStateMachine
from app.core.constants import ConfidenceLevel, TeachingLanguage
from app.core.events import EventBus, EventType
from app.core.exceptions import AgentExecutionError
from app.core.logger import get_logger

log = get_logger(__name__)


class TeacherOrchestrator:
    """Coordinates the multi-agent teaching pipeline.

    Usage::

        orch = TeacherOrchestrator(personality)
        response = await orch.execute(
            context=unified_context,
            student_message="Mujhe samajh nahi aaya",
        )
        # response is a TeacherResponse ready for the frontend

    Each call to ``execute()`` processes one student turn. The orchestrator
    maintains session state (state machine, dialogue, coach) so subsequent
    calls continue where the last one left off.
    """

    def __init__(
        self,
        personality: Optional[TeacherPersonality] = None,
    ) -> None:
        self.personality = personality or TeacherPersonality()
        self.state = TeacherStateMachine()
        self.dialogue = DialogueManager()
        self.coach = CoachAgent(self.personality)
        self.planner = PlannerAgent(self.personality)
        self.teacher = TeacherAgent(self.personality)
        self.critic = CriticAgent()
        self.responder = ResponseComposer()
        self._gateway: Optional[AIGateway] = None
        self.bus = EventBus.get_instance()

        # Register the state machine as an event source
        self.state.on_transition(self._on_state_transition)

    # ── Public API ─────────────────────────────────────────────────────

    async def execute(
        self,
        context: UnifiedStudentContext,
        student_message: str = '',
        image_base64: Optional[str] = None,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        provider: Optional[LLMProvider] = None,
    ) -> TeacherResponse:
        """Process a single student turn through the full pipeline.

        Args:
            context: Assembled student context from the Context Engine.
            student_message: The student's latest text input.
            image_base64: Optional base64-encoded camera frame.
            language: Output language preference.
            provider: Optional LLM provider override.

        Returns:
            Structured TeacherResponse for the frontend.
        """
        start = time.monotonic()
        log.info('orchestrator_execute_start',
                 user=context.profile.user_id,
                 subject=context.vision.subject.value,
                 topic=', '.join(context.vision.topics[:2]))

        # ── 1. Emotion Detection ───────────────────────────────────────
        emotion, emotion_conf = await detect_emotion(student_message, use_llm=False)
        log.debug('orchestrator_emotion', emotion=emotion, confidence=emotion_conf)

        # ── 2. State: OBSERVING → UNDERSTANDING ────────────────────────
        await self._safe_transition(TeacherState.OBSERVING, context)
        await self._publish(EventType.PROBLEM_DETECTED, context, student_message=student_message)

        # Build VisionOutput from context
        vision = VisionOutput(
            raw_text=student_message or context.vision.raw_text,
            subject=context.vision.subject,
            difficulty=context.vision.difficulty,
            topics=context.vision.topics,
            problem_type=context.vision.problem_type,
            diagram_type=context.vision.diagram_type,
            formulas=context.vision.formulas,
        )

        # ── 3. State: UNDERSTANDING → PLANNING ─────────────────────────
        await self._safe_transition(TeacherState.UNDERSTANDING, context)

        plan = await self._execute_planner(vision, context, provider)
        if plan is None:
            log.warning('orchestrator_plan_fallback')

        # Initialise dialogue on first run
        if plan and self.dialogue._total_steps == 0:
            self.dialogue.start_lesson(len(plan.lesson_plan.steps), plan.lesson_plan.topic)

        # ── 4. State: PLANNING → TEACHING ──────────────────────────────
        await self._safe_transition(TeacherState.PLANNING, context)
        await self._publish(EventType.LESSON_PLANNED, context, plan=plan)

        teacher_output = await self._execute_teacher(
            plan, vision, context, student_message, language, emotion, provider,
        )
        if teacher_output is None:
            return self._fallback_response(context, language)

        # ── 5. State: TEACHING → CHECKING ──────────────────────────────
        await self._safe_transition(TeacherState.TEACHING, context)
        await self._publish(EventType.TEACHING_STARTED, context, output=teacher_output)

        # ── 6. Critic Review ───────────────────────────────────────────
        await self._safe_transition(TeacherState.CHECKING, context)
        critic_result = await self._execute_critic(teacher_output, provider)

        if critic_result and not critic_result.passed:
            log.info('orchestrator_revision_requested',
                     issues=len(critic_result.feedback.revision_requests))
            await self._publish(EventType.CRITIC_REQUESTED_REVISION, context,
                                feedback=critic_result.feedback)

            # Retry teacher with revision hint
            revised_output = await self._execute_teacher(
                plan, vision, context, student_message, language, emotion, provider,
                revision_hint=critic_result.feedback.comments[:300],
            )
            if revised_output:
                teacher_output = revised_output

        # ── 7. Coach decision ──────────────────────────────────────────
        coaching = await self._execute_coach(context, provider)
        await self._publish(EventType.COACH_DECISION_MADE, context, coaching=coaching)

        # ── 8. Dialogue record ─────────────────────────────────────────
        self.dialogue.record_turn(
            student_message=student_message,
            teacher_response=teacher_output.response.explanation,
            emotion=emotion,
            emotion_confidence=emotion_conf,
        )

        # ── 9. Compose final response ──────────────────────────────────
        result = await self._execute_composer(
            teacher_output, context, language, provider,
            coaching=coaching,
        )

        # ── 10. State: SUMMARIZING → SESSION_COMPLETE ──────────────────
        if context.session.session_id:
            await self._safe_transition(TeacherState.SUMMARIZING, context)
            await self._publish(EventType.SESSION_ANALYTICS_FLUSHED, context, result=result)

        elapsed = time.monotonic() - start
        log.info('orchestrator_execute_end', elapsed_ms=round(elapsed * 1000))

        return result

    async def add_signal(self, signal_type: str, detail: str = '', confidence: float = 0.5) -> None:
        """Inject a student signal into the coach for real-time adaptation."""
        from app.ai.teacher.schemas import CoachingSignal
        self.coach.add_signal(CoachingSignal(type=signal_type, detail=detail, confidence=confidence))

    async def reset_session(self) -> None:
        """Reset the orchestrator for a new session."""
        await self.state.reset()
        self.dialogue = DialogueManager()
        self.coach = CoachAgent(self.personality)

    # ── Pipeline stages ────────────────────────────────────────────────

    async def _execute_planner(
        self,
        vision: VisionOutput,
        context: UnifiedStudentContext,
        provider: Optional[LLMProvider],
    ) -> Optional[PlannerOutput]:
        try:
            student_ctx = self._build_student_context(context)
            return await self.planner.plan(vision, student_ctx, provider or LLMProvider.GROQ)
        except Exception as exc:
            log.error('planner_failed', error=str(exc))
            return None

    async def _execute_teacher(
        self,
        plan: Optional[PlannerOutput],
        vision: VisionOutput,
        context: UnifiedStudentContext,
        student_message: str,
        language: TeachingLanguage,
        emotion: str,
        provider: Optional[LLMProvider],
        revision_hint: str = '',
    ) -> Optional[TeacherOutput]:
        try:
            student_ctx = self._build_student_context(context)
            step_index = self.dialogue.current_step
            dialogue_ctx = self.dialogue.to_system_context()
            return await self.teacher.teach(
                step_index=step_index,
                plan=plan,
                vision=vision,
                student=student_ctx,
                student_message=student_message,
                emotion=emotion,
                language=language,
                dialogue_context=dialogue_ctx,
                revision_hint=revision_hint,
                provider=provider or LLMProvider.GROQ,
            )
        except Exception as exc:
            log.error('teacher_agent_failed', error=str(exc))
            return None

    async def _execute_critic(
        self,
        teacher_output: TeacherOutput,
        provider: Optional[LLMProvider],
    ) -> Optional[CriticOutput]:
        try:
            return await self.critic.review(teacher_output, provider or LLMProvider.GROQ)
        except Exception as exc:
            log.error('critic_agent_failed', error=str(exc))
            return None

    async def _execute_coach(
        self,
        context: UnifiedStudentContext,
        provider: Optional[LLMProvider],
    ) -> CoachingDecision:
        try:
            student_ctx = self._build_student_context(context)
            return await self.coach.decide(
                student=student_ctx,
                current_step_index=self.dialogue.current_step,
                total_steps=max(self.dialogue._total_steps, 1),
                provider=provider or LLMProvider.GROQ,
            )
        except Exception as exc:
            log.error('coach_agent_failed', error=str(exc))
            return CoachingDecision(adaptation='continue', confidence=0.5)

    async def _execute_composer(
        self,
        teacher_output: TeacherOutput,
        context: UnifiedStudentContext,
        language: TeachingLanguage,
        provider: Optional[LLMProvider],
        coaching: Optional[CoachingDecision] = None,
    ) -> TeacherResponse:
        try:
            return await self.responder.merge(
                teacher_output=teacher_output,
                speech_plan=SpeechPlan(),
                ar_plan=ARPlan(),
                memory_delta=teacher_output.response.memory_update,
                quiz=None,
                coaching=coaching,
                language=language,
                use_llm_polish=False,
            )
        except Exception as exc:
            log.error('composer_failed', error=str(exc))
            return TeacherResponse(
                explanation='',
                board_actions=teacher_output.response.board_actions,
            )

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_student_context(context: UnifiedStudentContext) -> 'StudentContext':
        """Convert UnifiedStudentContext → StudentContext (agent input schema)."""
        from app.ai.teacher.schemas import StudentContext

        return StudentContext(
            user_id=context.profile.user_id,
            display_name=context.profile.display_name,
            level=context.profile.level,
            preferred_language=context.profile.preferred_language.value,
            recent_topics=context.knowledge.recently_covered,
            weak_topics=context.knowledge.weak_concepts,
            strong_topics=context.knowledge.strong_concepts,
            current_streak=0,
            session_count=context.session_history.total_sessions,
            current_confidence=ConfidenceLevel.MEDIUM,
            recent_mistakes=[m.get('topic', '') for m in context.mistakes.recent_mistakes],
            revision_due=context.revision.overdue_topics + context.revision.due_soon_topics,
        )

    def _fallback_response(self, context: UnifiedStudentContext, language: TeachingLanguage) -> TeacherResponse:
        """Return a safe fallback when the pipeline fails."""
        return TeacherResponse(
            speech=None,
            board_actions=[],
            ar_instructions=[],
        )

    async def _safe_transition(self, target: TeacherState, context: UnifiedStudentContext) -> None:
        """Transition state if valid; skip silently if not."""
        try:
            await self.state.transition(target)
        except AgentExecutionError:
            pass

    async def _publish(self, event_type: EventType, context: UnifiedStudentContext, **extra: Any) -> None:
        """Publish an event with standardised metadata."""
        await self.bus.publish_sync(
            event_type=event_type,
            data={
                'user_id': context.profile.user_id,
                'session_id': context.session.session_id,
                'subject': context.vision.subject.value,
                'topics': context.vision.topics,
                'state': self.state.current.value,
                **extra,
            },
            source='orchestrator',
            correlation_id=context.session.session_id or context.profile.user_id,
        )

    async def _on_state_transition(
        self,
        from_state: TeacherState,
        to_state: TeacherState,
        ctx: dict[str, Any],
    ) -> None:
        log.debug('state_transition_callback', from_state=from_state.value, to_state=to_state.value)
