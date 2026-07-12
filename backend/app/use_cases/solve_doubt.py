"""SolveDoubtUseCase — single entry point for Ask Doubt (image or text).

Flow::
    Frontend → SolveDoubtUseCase.execute()
      ├─ 1. Vision Pipeline     (if image provided)
      ├─ 2. Scene Graph          (if scene available)
      ├─ 3. Build Context
      ├─ 4. Emotion Detection
      ├─ 5. Planner Agent
      ├─ 6. Teacher Agent        (with critic revision loop)
      ├─ 7. Coach Decision
      ├─ 8. Response Composer
      └─ 9. → TeacherResponse
"""

from __future__ import annotations

import time
from io import BytesIO
from typing import Any, Optional

import numpy as np
from PIL import Image

from app.ai.context import (
    UnifiedStudentContext,
    StudentProfile,
    VisionContext,
    SessionContext,
)
from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.emotion import detect_emotion
from app.ai.teacher.schemas import (
    ARPlan,
    CoachingDecision,
    PlannerOutput,
    SpeechPlan,
    TeacherOutput,
    TeacherResponse,
    VisionOutput,
)
from app.ai.teacher.state_machine import TeacherState
from app.core.constants import Difficulty, Subject, TeachingLanguage
from app.core.events import EventBus, EventType
from app.core.exceptions import AIProviderError
from app.core.logger import get_logger
from app.use_cases.base import BaseUseCase, PipelineMonitor, ProgressCb

log = get_logger(__name__)


class SolveDoubtUseCase(BaseUseCase):
    """Solve a student's doubt from text or image + optional image."""

    async def execute(
        self,
        text: str = '',
        image_bytes: Optional[bytes] = None,
        mode: str = 'math',
        level: str = 'intermediate',
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        provider: Optional[LLMProvider] = None,
        progress_cb: ProgressCb = None,
    ) -> tuple[TeacherResponse, dict[str, Any]]:
        """Run the full doubt-solving pipeline.

        Returns:
            (TeacherResponse, pipeline_report)

        After execution, ``self.last_vision_dict`` and
        ``self.last_decision_dict`` contain vision/scene results.
        """
        self.last_vision_dict: Optional[dict] = None
        self.last_decision_dict: Optional[dict] = None

        monitor = PipelineMonitor(request_id=f'doubt_{int(time.time())}')
        log.info('usecase_solve_doubt_start',
                 has_image=image_bytes is not None,
                 text_len=len(text),
                 mode=mode)

        # ── 1. Vision Pipeline ──────────────────────────────────────────
        await self._progress(progress_cb, 'analyzing_image', 'Analyzing your image')
        scene = None

        if image_bytes:
            scene, self.last_vision_dict = await self._run_vision(image_bytes, monitor)
        else:
            monitor.skip('vision', 'no image provided')

        # ── 2. Scene Graph ──────────────────────────────────────────────
        await self._progress(progress_cb, 'building_scene', 'Building scene graph')
        if scene is not None:
            self.last_decision_dict = await self._run_scene_graph(scene, monitor)

        # ── 3. Build Unified Context ──
        parsed_level = _parse_level(level)
        raw_text, subject, topics, problem_type, formulas = self._extract_problem(
            scene, text, mode,
        )

        context = UnifiedStudentContext(
            profile=StudentProfile(
                user_id='anonymous',
                level=parsed_level,
                preferred_language=language,
            ),
            vision=VisionContext(
                raw_text=raw_text,
                subject=subject,
                difficulty=parsed_level,
                topics=topics,
                problem_type=problem_type,
                formulas=formulas,
            ),
            session=SessionContext(
                session_id=f'ses_{int(time.time())}',
                session_started_at=time.time(),
            ),
        )

        # ── 4+ Pipeline (orchestrator stages) ──────────────────────────
        response = await self._run_teaching_pipeline(
            context=context,
            student_message=raw_text,
            language=language,
            provider=provider,
            progress_cb=progress_cb,
            monitor=monitor,
        )

        elapsed = time.monotonic()
        log.info('usecase_solve_doubt_end',
                 explanation_len=len(response.explanation),
                 total_stages=len(monitor.report()['stages']))

        return response, monitor.report()

    # ── Private stages ─────────────────────────────────────────────────

    async def _run_vision(
        self,
        image_bytes: bytes,
        monitor: PipelineMonitor,
    ) -> tuple[Any, Optional[dict]]:
        """Run the Vision Intelligence pipeline.

        Returns:
            (scene, vision_dict)
        """
        try:
            from app.ai.vision_intelligence.pipeline import VisionPipeline
            from app.ai.vision_intelligence.adapter import VisionAdapter

            img = Image.open(BytesIO(image_bytes)).convert('RGB')
            img_array = np.array(img)
            pipeline = VisionPipeline()
            scene = await pipeline.run(img_array)

            adapter = VisionAdapter()
            vision_dict = adapter.to_vision_context(scene) if scene and not adapter.needs_recapture(scene) else None
            return scene, vision_dict
        except Exception as exc:
            log.warning('vision_pipeline_failed', error=str(exc)[:200])
            monitor.skip('scene_graph', 'vision pipeline failed')
            return None, None

    async def _run_scene_graph(
        self,
        scene: Any,
        monitor: PipelineMonitor,
    ) -> Optional[dict]:
        """Run the Scene Graph pipeline."""
        from app.ai.vision_intelligence.adapter import VisionAdapter
        from app.ai.scene_graph.integration import SceneGraphIntegration

        adapter = VisionAdapter()
        if adapter.needs_recapture(scene):
            monitor.skip('scene_graph', 'needs recapture')
            return None

        try:
            scene_graph = SceneGraphIntegration()
            teaching_decision = await scene_graph.process(scene)
            return (
                teaching_decision.model_dump()
                if hasattr(teaching_decision, 'model_dump')
                else {}
            )
        except Exception as exc:
            log.warning('scene_graph_failed', error=str(exc)[:200])
            monitor.skip('scene_graph_complete', str(exc))
            return None

    def _extract_problem(
        self,
        scene: Any,
        text: str,
        mode: str,
    ) -> tuple[str, Subject, list[str], str, list[str]]:
        """Extract problem info from scene or fall back to raw text."""
        if scene is not None:
            try:
                from app.ai.vision_intelligence.adapter import VisionAdapter
                adapter = VisionAdapter()
                vo = adapter.to_vision_output(scene)
                return (
                    vo.get('raw_text', text),
                    Subject.MATH if mode == 'math' else Subject.GENERAL,
                    vo.get('topics', []),
                    vo.get('problem_type', 'general'),
                    vo.get('formulas', []),
                )
            except Exception as exc:
                log.debug('vision_adapter_fallback_used', error=str(exc)[:100])

        subject = Subject.MATH if mode == 'math' else Subject.GENERAL
        return text, subject, [], 'general', []

    async def _run_teaching_pipeline(
        self,
        context: UnifiedStudentContext,
        student_message: str,
        language: TeachingLanguage,
        provider: Optional[LLMProvider],
        progress_cb: ProgressCb,
        monitor: PipelineMonitor,
    ) -> TeacherResponse:
        """Run the teacher pipeline: planner → teacher → critic → coach → composer."""
        # None = let gateway auto-select best provider (Gemini → Groq)

        # Gateway check
        await self._log_providers(monitor)

        # Emotion
        emotion, emotion_conf = await detect_emotion(student_message, use_llm=False)

        # Build VisionOutput
        vision = VisionOutput(
            raw_text=student_message or context.vision.raw_text,
            subject=context.vision.subject,
            difficulty=context.vision.difficulty,
            topics=context.vision.topics,
            problem_type=context.vision.problem_type,
            diagram_type=context.vision.diagram_type,
            formulas=context.vision.formulas,
        )

        # Planner
        await self._progress(progress_cb, 'planning_lesson', 'Planning lesson')
        try:
            plan = await self._run_planner(vision, context, provider, monitor)
        except Exception as exc:
            log.error('pipeline_failed_planner', error=str(exc)[:300])
            raise AIProviderError(
                provider='all',
                message='The AI teacher could not create a lesson plan',
            ) from exc

        # Teacher
        await self._progress(progress_cb, 'teaching', 'Teaching the concept')
        try:
            teacher_output = await self._run_teacher(
                plan, vision, context, student_message, language,
                emotion, provider, monitor,
            )
        except Exception as exc:
            log.error('pipeline_failed_teacher', error=str(exc)[:300])
            raise AIProviderError(
                provider='all',
                message='The AI teacher could not generate a teaching response',
            ) from exc

        # Critic + revision
        try:
            teacher_output = await self._run_critic_loop(
                teacher_output, plan, vision, context, student_message,
                language, emotion, provider, monitor,
            )
        except Exception as exc:
            log.error('pipeline_failed_critic', error=str(exc)[:300])

        # Coach
        await self._progress(progress_cb, 'adapting', 'Adapting to you')
        coaching = await self._run_coach(context, provider, monitor)

        # Dialogue
        self.dialogue.record_turn(
            student_message=student_message,
            teacher_response=teacher_output.response.explanation,
            emotion=emotion,
            emotion_confidence=emotion_conf,
        )

        # Composer
        await self._progress(progress_cb, 'composing', 'Composing response')
        try:
            response = await self._run_composer(
                teacher_output, language, coaching, monitor,
            )
        except Exception as exc:
            log.error('pipeline_failed_composer', error=str(exc)[:300])
            return self._error_response(
                teacher_output.response.explanation or 'Please try asking your doubt again.',
                monitor,
            )

        return response

    # ── Agent runners ──────────────────────────────────────────────────

    async def _log_providers(self, monitor: PipelineMonitor) -> None:
        try:
            gw = await AIGateway.get_instance()
            available = [p.value for p in gw.available_providers]
            log.info('usecase_providers', providers=available, count=len(available))
        except Exception as exc:
            log.warning('usecase_providers_failed', error=str(exc))

    async def _run_planner(
        self,
        vision: VisionOutput,
        context: UnifiedStudentContext,
        provider: Optional[LLMProvider],
        monitor: PipelineMonitor,
    ) -> PlannerOutput:
        student_ctx = self._build_student_context(context)
        result = await monitor.run(
            'planner',
            lambda: self.planner.plan(vision, student_ctx, provider),
            steps='?',
        )
        if result:
            log.info('planner_done', steps=len(result.lesson_plan.steps))
            if self.dialogue._total_steps == 0:
                self.dialogue.start_lesson(
                    len(result.lesson_plan.steps),
                    result.lesson_plan.topic,
                )
        return result

    async def _run_teacher(
        self,
        plan: Optional[PlannerOutput],
        vision: VisionOutput,
        context: UnifiedStudentContext,
        student_message: str,
        language: TeachingLanguage,
        emotion: str,
        provider: Optional[LLMProvider],
        monitor: PipelineMonitor,
        revision_hint: str = '',
    ) -> TeacherOutput:
        student_ctx = self._build_student_context(context)
        step_index = self.dialogue.current_step
        dialogue_ctx = self.dialogue.to_system_context()
        result = await monitor.run(
            'teacher',
            lambda: self.teacher.teach(
                step_index=step_index,
                plan=plan,
                vision=vision,
                student=student_ctx,
                student_message=student_message,
                emotion=emotion,
                language=language,
                dialogue_context=dialogue_ctx,
                revision_hint=revision_hint,
                provider=provider,
            ),
            step=step_index,
        )
        return result

    async def _run_critic_loop(
        self,
        teacher_output: TeacherOutput,
        plan: Optional[PlannerOutput],
        vision: VisionOutput,
        context: UnifiedStudentContext,
        student_message: str,
        language: TeachingLanguage,
        emotion: str,
        provider: Optional[LLMProvider],
        monitor: PipelineMonitor,
    ) -> TeacherOutput:
        try:
            critic_result = await monitor.run(
                'critic',
                lambda: self.critic.review(teacher_output, provider),
            )
        except Exception:
            monitor.skip('critic', 'critic failed, proceeding without review')
            return teacher_output

        if critic_result and not critic_result.passed:
            log.info('revision_needed',
                     issues=len(critic_result.feedback.revision_requests))
            try:
                revised = await self._run_teacher(
                    plan, vision, context, student_message, language,
                    emotion, provider, monitor,
                    revision_hint=critic_result.feedback.comments[:300],
                )
                return revised
            except Exception as exc:
                log.warning('revision_teacher_failed', error=str(exc)[:200])
        return teacher_output

    async def _run_coach(
        self,
        context: UnifiedStudentContext,
        provider: Optional[LLMProvider],
        monitor: PipelineMonitor,
    ) -> CoachingDecision:
        try:
            student_ctx = self._build_student_context(context)
            result = await monitor.run(
                'coach',
                lambda: self.coach.decide(
                    student=student_ctx,
                    current_step_index=self.dialogue.current_step,
                    total_steps=max(self.dialogue._total_steps, 1),
                    provider=provider,
                ),
            )
            return result
        except Exception as exc:
            log.warning('coach_failed', error=str(exc)[:100])
            monitor.skip('coach', str(exc)[:100])
            return CoachingDecision(adaptation='continue', confidence=0.5)

    async def _run_composer(
        self,
        teacher_output: TeacherOutput,
        language: TeachingLanguage,
        coaching: CoachingDecision,
        monitor: PipelineMonitor,
    ) -> TeacherResponse:
        try:
            result = await monitor.run(
                'composer',
                lambda: self.responder.merge(
                    teacher_output=teacher_output,
                    speech_plan=SpeechPlan(),
                    ar_plan=ARPlan(),
                    memory_delta=teacher_output.response.memory_update,
                    quiz=teacher_output.response.quiz,
                    coaching=coaching,
                    language=language,
                    use_llm_polish=False,
                ),
            )
            return result
        except Exception as exc:
            log.error('composer_failed', error=str(exc)[:200])
            return TeacherResponse(
                explanation=teacher_output.response.explanation or '',
                board_actions=list(teacher_output.response.board_actions),
            )

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_student_context(context: UnifiedStudentContext) -> Any:
        from app.ai.teacher.schemas import StudentContext
        from app.core.constants import ConfidenceLevel

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

    @staticmethod
    def _error_response(message: str, monitor: PipelineMonitor) -> TeacherResponse:
        log.error('pipeline_failed_returning_error', message=message)
        hinglish_msg = message or 'Kripya apna doubt dobara poochh lijiye. Main aapki madad karunga.'
        return TeacherResponse(
            explanation=hinglish_msg,
            key_points=['Kripya apna doubt dobara poochh lijiye'],
            checkpoints=['Kya aapko samajh aa raha hai?'],
            speech=None,
            board_actions=[],
            ar_instructions=[],
        )


def _fallback_explanation(vision: VisionOutput) -> str:
    raw = (vision.raw_text or '')[:300].strip()
    topic_str = ', '.join(vision.topics[:2]) if vision.topics else 'this topic'
    return f'Main {topic_str} ke baare mein samjha raha hoon. {raw}'


def _parse_level(level: str) -> Difficulty:
    try:
        return Difficulty(level)
    except ValueError:
        return Difficulty.INTERMEDIATE
