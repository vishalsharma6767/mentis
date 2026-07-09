"""Teacher Brain — Central Orchestrator.

Runs the full multi-agent pipeline end-to-end:
Vision → Planner → Teacher → Critic → AR → Speech → Memory → Composer

Manages retry, fallback, and graceful degradation at every stage.
"""

import time
from typing import Any, Optional

from app.ai.teacher.coach import CoachAgent
from app.ai.teacher.critic import CriticAgent
from app.ai.teacher.dialogue import DialogueManager
from app.ai.teacher.emotion import detect_emotion, urgency_level
from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.planner import PlannerAgent
from app.ai.teacher.prompts import teacher_agent_prompt as make_teacher_prompt
from app.ai.teacher.reasoner import LLMProvider, reason
from app.ai.teacher.responder import ResponderAgent
from app.ai.teacher.schemas import (
    ARPlan,
    CoachingDecision,
    CriticOutput,
    LessonPlan,
    MemoryUpdate,
    PlannerOutput,
    QuizItem,
    SpeechPlan,
    StudentContext,
    TeacherOutput,
    TeacherResponse,
    VisionOutput,
)
from app.core.constants import TeachingLanguage
from app.core.exceptions import AgentExecutionError
from app.core.logger import get_logger

log = get_logger(__name__)


class TeacherBrain:
    """Full multi-agent pipeline orchestrator.

    Usage::

        brain = TeacherBrain(personality)
        result = await brain.teach(
            vision_output=vision,
            student=student_ctx,
            student_message="Mujhe samajh nahi aaya",
        )
        # result is a TeacherResponse ready for the frontend
    """

    def __init__(
        self,
        personality: Optional[TeacherPersonality] = None,
    ) -> None:
        self.personality = personality or TeacherPersonality()
        self.planner = PlannerAgent(self.personality)
        self.critic = CriticAgent()
        self.coach = CoachAgent(self.personality)
        self.dialogue = DialogueManager()
        self.responder = ResponderAgent()
        self._teacher_prompt = make_teacher_prompt(self.personality)

    # ── Public API ──────────────────────────────────────────────────────

    async def teach(
        self,
        vision_output: VisionOutput,
        student: StudentContext,
        student_message: str = '',
        history: Optional[list[dict[str, Any]]] = None,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        provider: str = LLMProvider.GROQ,
    ) -> TeacherResponse:
        """Run the full teaching pipeline for a single student turn.

        Args:
            vision_output: Problem / context from the Vision Agent.
            student: Current student profile.
            student_message: The student's latest text input.
            history: Previous conversation messages (OpenAI format).
            language: Output language preference.
            provider: LLM backend.

        Returns:
            Composed TeacherResponse ready for the frontend.
        """
        start = time.monotonic()
        log.info('brain_pipeline_start', subject=vision_output.subject.value if vision_output.subject else 'general')

        # 1. Detect emotion
        emotion, emotion_conf = await detect_emotion(student_message, use_llm=False)
        log.debug('emotion_detected', emotion=emotion, confidence=emotion_conf)

        # 2. Plan the lesson (runs once per problem, cached via vision hash)
        plan = await self._get_or_create_plan(vision_output, student, provider)

        # 3. Initialise dialogue for new lessons
        if self.dialogue._total_steps == 0:
            self.dialogue.start_lesson(len(plan.lesson_plan.steps), plan.lesson_plan.topic)

        # 4. Run the Teacher Agent (core explanation generation)
        teacher_output = await self._run_teacher(
            plan, vision_output, student, student_message, language, emotion, provider,
        )

        # 5. Run Critic for quality check
        critic_result = await self._run_critic(teacher_output, provider)

        # 6. If critic failed, request revision from teacher
        if not critic_result.passed:
            log.info('critic_requested_revision', issues=len(critic_result.feedback.revision_requests))
            teacher_output = await self._run_teacher(
                plan, vision_output, student, student_message, language, emotion, provider,
                revision_hint=critic_result.feedback.comments[:200],
            )

        # 7. Coach: decide adaptation based on student signals
        coaching = await self._run_coach(student, provider)

        # 8. Record this turn in dialogue
        self.dialogue.record_turn(
            student_message=student_message,
            teacher_response=teacher_output.response.explanation,
            emotion=emotion,
            emotion_confidence=emotion_conf,
        )

        # 9. Composer: build final response
        result = await self.responder.compose(
            teacher_output=teacher_output,
            ar_plan=ARPlan(),
            speech_plan=SpeechPlan(),
            memory_delta=teacher_output.response.memory_update,
            quiz=None,
            coaching_decision=coaching,
            student=student,
            dialogue_context=self.dialogue.to_system_context(),
            provider=provider,
            language=language,
        )

        elapsed = time.monotonic() - start
        log.info('brain_pipeline_end', elapsed_ms=round(elapsed * 1000))
        return result

    async def continue_teaching(
        self,
        student_message: str,
        student: StudentContext,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        provider: str = LLMProvider.GROQ,
    ) -> TeacherResponse:
        """Continue an existing lesson with a new student message."""
        vision = VisionOutput(raw_text=student_message)
        return await self.teach(vision, student, student_message, language=language, provider=provider)

    def add_signal(self, signal_type: str, detail: str = '', confidence: float = 0.5) -> None:
        """Inject a student signal (used by the frontend WebSocket handler)."""
        from app.ai.teacher.schemas import CoachingSignal
        self.coach.add_signal(CoachingSignal(type=signal_type, detail=detail, confidence=confidence))

    # ── Internal pipeline steps ─────────────────────────────────────────

    async def _get_or_create_plan(
        self,
        vision: VisionOutput,
        student: StudentContext,
        provider: str,
    ) -> PlannerOutput:
        return await self.planner.plan(vision, student, provider)

    async def _run_teacher(
        self,
        plan: PlannerOutput,
        vision: VisionOutput,
        student: StudentContext,
        student_message: str,
        language: TeachingLanguage,
        emotion: str,
        provider: str,
        revision_hint: str = '',
    ) -> TeacherOutput:
        messages = [{'role': 'system', 'content': self._teacher_prompt}]

        if plan.lesson_plan:
            steps_text = '\n'.join(
                f'  Step {i + 1}: [{s.phase}] {s.title} — {s.explanation[:120]}...'
                for i, s in enumerate(plan.lesson_plan.steps)
            )
            messages.append({
                'role': 'user',
                'content': f"""Lesson plan:
Topic: {plan.lesson_plan.topic}
Difficulty: {plan.lesson_plan.difficulty.value if hasattr(plan.lesson_plan.difficulty, 'value') else plan.lesson_plan.difficulty}
Strategy: {plan.teaching_strategy}
Adaptations: {', '.join(plan.adaptations)}

Steps:
{steps_text}

Problem: {vision.raw_text}
Student emotion: {emotion}
{revision_hint}
Previous context:
{self.dialogue.to_system_context()}

Language: {language.value}
Student message: {student_message}

Now teach this step-by-step in {language.value}."""
            })

        try:
            result = await reason(messages=messages, provider=provider, expect_json=True)
            return self._parse_teacher_result(result, plan, vision)
        except Exception as exc:
            raise AgentExecutionError(agent='teacher', message=str(exc))

    def _parse_teacher_result(
        self,
        result: dict[str, Any],
        plan: PlannerOutput,
        vision: VisionOutput,
    ) -> TeacherOutput:
        from app.ai.teacher.schemas import TeacherResponse as TR

        response = TR(
            explanation=result.get('explanation', ''),
            key_points=result.get('key_points', []),
            checkpoints=result.get('checkpoints', []),
            examples=result.get('examples', []),
            analogy=result.get('analogy', ''),
            language_hint=result.get('language_hint', 'hinglish'),
            board_actions=result.get('board_actions', []),
            memory_update=MemoryUpdate(
                topics_covered=result.get('topics_covered', vision.topics),
                topics_struggled=result.get('topics_struggled', []),
                confidence_estimate=result.get('confidence_estimate'),
            ),
        )

        return TeacherOutput(
            response=response,
            lesson_plan=plan.lesson_plan,
            subject=vision.subject,
            topic=plan.lesson_plan.topic,
            student_level=plan.lesson_plan.difficulty,
            language=TeachingLanguage.HINGLISH,
        )

    async def _run_critic(
        self,
        teacher_output: TeacherOutput,
        provider: str,
    ) -> CriticOutput:
        return await self.critic.review(teacher_output, provider)

    async def _run_coach(
        self,
        student: StudentContext,
        provider: str,
    ) -> CoachingDecision:
        return await self.coach.decide(
            student=student,
            current_step_index=self.dialogue.current_step,
            total_steps=self.dialogue._total_steps,
            provider=provider,
        )
