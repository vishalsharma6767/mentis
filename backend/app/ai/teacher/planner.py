"""Planner Agent — lesson plan designer.

The Planner never teaches. Its sole responsibility is to analyse a
problem and student context, then produce a structured, step-by-step
lesson plan that the Teacher Agent executes.

Every lesson plan includes:
  - Greeting, observation, concept explanation
  - Prerequisite review if needed
  - Step-by-step teaching flow with board/AR actions
  - Checkpoints, hints, and correction paths
  - Homework and quiz recommendations
  - Estimated duration per step
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.prompts import planner_agent_prompt
from app.ai.teacher.schemas import (
    HomeworkItem,
    LessonPlan,
    LessonStep,
    PlannerOutput,
    StudentContext,
    VisionOutput,
)
from app.core.constants import Difficulty, LessonPhase, Subject
from app.core.exceptions import AgentExecutionError
from app.core.logger import get_logger

log = get_logger(__name__)

MIN_STEPS = 3
MAX_STEPS = 12
FALLBACK_STEP_DURATION = 45


class PlannerAgent:
    """Generates structured lesson plans.

    The planner analyses the problem and student context, then produces
    a step-by-step teaching plan. It never teaches — it only designs.

    Usage::

        planner = PlannerAgent(personality)
        plan = await planner.plan(vision_output, student_context)
        # plan.lesson_plan.steps contains the teaching sequence
    """

    def __init__(
        self,
        personality: Optional[TeacherPersonality] = None,
        gateway: Optional[AIGateway] = None,
    ) -> None:
        self.personality = personality or TeacherPersonality()
        self._gateway = gateway
        self._prompt = planner_agent_prompt(self.personality)

    async def plan(
        self,
        vision_output: VisionOutput,
        student: StudentContext,
        provider: Optional[LLMProvider] = None,
    ) -> PlannerOutput:
        """Create a lesson plan from vision output and student context.

        Args:
            vision_output: Extracted problem info from vision pipeline.
            student: Current student profile and knowledge state.
            provider: Optional LLM provider override.

        Returns:
            Structured PlannerOutput with lesson plan and strategy.

        Raises:
            AgentExecutionError: If planning fails catastrophically.
        """
        log.info(
            'planner_start',
            subject=vision_output.subject.value,
            topic=', '.join(vision_output.topics[:2]),
            student_level=student.level.value,
        )

        messages = [
            {'role': 'system', 'content': self._prompt},
            {'role': 'user', 'content': self._build_input_prompt(vision_output, student)},
        ]

        for attempt in range(1, 4):
            try:
                gateway = await self._resolve_gateway()
                response = await gateway.execute(
                    messages=messages,
                    provider=provider,
                    expect_json=True,
                    max_tokens=4096,
                    temperature=0.7,
                    use_cache=True,
                )

                parsed = self._try_parse_json(response.text)
                if parsed is None:
                    raise ValueError('No valid JSON found in response')

                result = self._parse_result(parsed, vision_output)

                log.info(
                    'planner_success',
                    steps=len(result.lesson_plan.steps),
                    strategy=result.teaching_strategy,
                    duration=result.lesson_plan.estimated_total_duration,
                    latency_ms=response.latency_ms,
                )
                return result

            except Exception as exc:
                log.warning('planner_attempt_failed', attempt=attempt, error=str(exc)[:120])
                if attempt < 3:
                    continue

        log.error('planner_all_attempts_failed')
        return self._fallback_plan(vision_output, student)

    def _build_input_prompt(self, vision: VisionOutput, student: StudentContext) -> str:
        """Format vision output and student context into the planner prompt."""
        weak = ', '.join(student.weak_topics[:5]) or 'none identified'
        strong = ', '.join(student.strong_topics[:5]) or 'none identified'
        recent = ', '.join(student.recent_topics[-5:]) or 'none'
        revision = ', '.join(student.revision_due[:3]) or 'none'
        mistakes = ', '.join(student.recent_mistakes[:3]) or 'none'

        return json.dumps({
            'problem': {
                'text': vision.raw_text[:1000],
                'subject': vision.subject.value,
                'difficulty': vision.difficulty.value,
                'topics': vision.topics,
                'type': vision.problem_type,
                'formulas': vision.formulas,
                'diagram': vision.diagram_type,
            },
            'student': {
                'level': student.level.value,
                'weak_topics': student.weak_topics,
                'strong_topics': student.strong_topics,
                'recent_topics': student.recent_topics[-5:],
                'revision_due': student.revision_due,
                'recent_mistakes': student.recent_mistakes,
                'session_count': student.session_count,
                'confidence': student.current_confidence.value,
                'streak': student.current_streak,
            },
        }, indent=2)

    def _parse_result(self, result: dict[str, Any], vision: VisionOutput) -> PlannerOutput:
        """Convert the LLM JSON response into a validated PlannerOutput."""
        lesson_data = result.get('lesson_plan', result)
        steps_data = lesson_data.get('steps', [])

        if not isinstance(steps_data, list):
            log.warning('planner_steps_not_a_list', type=type(steps_data).__name__)
            steps_data = []

        steps: list[LessonStep] = []
        for i, s in enumerate(steps_data):
            if not isinstance(s, dict):
                continue
            try:
                phase_str = s.get('phase', 'step_by_step')
                phase = self._resolve_phase(phase_str)

                step = LessonStep(
                    phase=phase,
                    title=s.get('title', f'Step {i + 1}')[:200],
                    explanation=s.get('explanation', '')[:2000],
                    board_actions=s.get('board_actions', []),
                    ar_actions=self._parse_ar_actions(s.get('ar_actions', [])),
                    hint=s.get('hint', '')[:500],
                    duration_seconds=max(10, min(300, int(s.get('duration_seconds', FALLBACK_STEP_DURATION)))),
                )
                steps.append(step)
            except Exception as exc:
                log.warning('planner_step_parse_failed', index=i, error=str(exc)[:100])
                continue

        if len(steps) < MIN_STEPS:
            log.warning('planner_too_few_steps', count=len(steps))
            steps = self._pad_steps(steps, vision)

        if len(steps) > MAX_STEPS:
            log.info('planner_truncating_steps', from_count=len(steps), to_count=MAX_STEPS)
            steps = steps[:MAX_STEPS]

        subject = self._resolve_subject(lesson_data.get('subject', vision.subject))
        difficulty = self._resolve_difficulty(lesson_data.get('difficulty', vision.difficulty))
        topic = lesson_data.get('topic', vision.topics[0] if vision.topics else 'General')

        total_duration = lesson_data.get('estimated_total_duration', 0)
        if total_duration <= 0:
            total_duration = sum(s.duration_seconds for s in steps)

        lesson_plan = LessonPlan(
            subject=subject,
            topic=topic[:200],
            difficulty=difficulty,
            prerequisite_topics=[str(t)[:200] for t in (lesson_data.get('prerequisite_topics', []) or [])],
            steps=steps,
            estimated_total_duration=total_duration,
            key_concepts=[str(c)[:200] for c in (lesson_data.get('key_concepts', vision.topics) or [])],
            homework=self._parse_homework(lesson_data.get('homework', [])),
        )

        return PlannerOutput(
            lesson_plan=lesson_plan,
            teaching_strategy=str(result.get('teaching_strategy', 'step_by_step')),
            adaptations=[str(a) for a in (result.get('adaptations', []) or [])],
        )

    # ── JSON parsing ────────────────────────────────────────────────────

    @staticmethod
    def _try_parse_json(text: str) -> Optional[dict[str, Any]]:
        """Extract the first JSON object from a string."""
        text = text.strip()
        if text.startswith('{') and text.endswith('}'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        pass
        return None

    def _fallback_plan(self, vision: VisionOutput, student: StudentContext) -> PlannerOutput:
        """Generate a contextual fallback plan using vision.raw_text directly."""
        log.info('planner_using_fallback', subject=vision.subject.value)

        raw = vision.raw_text[:400].strip()
        subject_name = vision.subject.value.capitalize()
        topic_list = vision.topics[:3] if vision.topics else []
        topic_str = ', '.join(topic_list) if topic_list else subject_name
        weak_str = ', '.join(student.weak_topics[:3]) if student.weak_topics else 'basic concepts'

        steps = [
            LessonStep(
                phase=LessonPhase.OBSERVE,
                title=f'{topic_str} — problem samjhte hain',
                explanation=f'Aapne {subject_name} ka sawaal poochha hai: "{raw[:200] if len(raw) > 200 else raw}". '
                            f'Pehle hum problem ko dhyan se padhenge aur samjhenge ki kya poochha gaya hai. '
                            f'Ismein {topic_str} se related concepts hain.',
                duration_seconds=45,
                board_actions=[],
            ),
            LessonStep(
                phase=LessonPhase.CONCEPT,
                title=f'Zaroori concepts — {topic_str}',
                explanation=f'Is problem ko solve karne ke liye {topic_str} ki samajh zaroori hai. '
                            f'{weak_str} par dhyan denge kyunki yahan aapko thodi practice ki zaroorat hai. '
                            f'Pehle basic rules ko revise karte hain, phir problem par aate hain.',
                duration_seconds=60,
            ),
            LessonStep(
                phase=LessonPhase.STEP_BY_STEP,
                title=f'Step by step — {topic_str}',
                explanation=f'Ab hum step by step is problem ko solve karenge. '
                            f'Har step ko dhyan se samjhiye. Agar koi step samajh na aaye toh ruk kar poochh sakte hain. '
                            f'Hum dhairy se ek-ek kadam badhenge.',
                duration_seconds=90,
                board_actions=[],
            ),
            LessonStep(
                phase=LessonPhase.CHECKPOINT,
                title='Kya samajh aa raha hai?',
                explanation=f'Kya aapko ab tak ka explanation samajh mein aaya? '
                            f'Maine {topic_str} ke baare mein bataya. '
                            f'Agar koi doubt ho toh abhi poochh lijiye — main phir se samjhaunga.',
                duration_seconds=20,
            ),
            LessonStep(
                phase=LessonPhase.SUMMARY,
                title=f'{topic_str} — aaj humne kya seekha',
                explanation=f'Chaliye ek baar revise karte hain. Aaj humne {topic_str} ke baare mein seekha. '
                            f'Problem tha: {raw[:150 if len(raw) > 150 else len(raw)]}. '
                            f'Humne step by step approach use kiya. Ghar par practice zaroor karein.',
                duration_seconds=30,
            ),
        ]

        plan = LessonPlan(
            subject=vision.subject,
            topic=vision.topics[0] if vision.topics else 'General',
            difficulty=student.level,
            steps=steps,
            estimated_total_duration=sum(s.duration_seconds for s in steps),
            key_concepts=vision.topics,
            prerequisite_topics=student.weak_topics[:3],
        )

        return PlannerOutput(
            lesson_plan=plan,
            teaching_strategy='step_by_step',
            adaptations=['simplify_language', 'more_examples', 'focus_on_weak_areas'],
        )

    # ── Helpers ────────────────────────────────────────────────────────

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway

    @staticmethod
    def _resolve_phase(phase_str: str) -> LessonPhase:
        try:
            return LessonPhase(phase_str)
        except ValueError:
            valid = [e.value for e in LessonPhase]
            if phase_str in ('step', 'solve'):
                return LessonPhase.STEP_BY_STEP
            if phase_str in ('intro', 'greeting', 'welcome'):
                return LessonPhase.OBSERVE
            if phase_str in ('practice', 'try'):
                return LessonPhase.EXAMPLE
            if phase_str in ('assess', 'test', 'question'):
                return LessonPhase.CHECKPOINT
            log.warning('planner_unknown_phase', phase=phase_str, valid=valid)
            return LessonPhase.STEP_BY_STEP

    @staticmethod
    def _resolve_subject(subject: Any) -> Subject:
        if isinstance(subject, Subject):
            return subject
        if isinstance(subject, str):
            try:
                return Subject(subject.lower())
            except ValueError:
                pass
        return Subject.GENERAL

    @staticmethod
    def _resolve_difficulty(difficulty: Any) -> Difficulty:
        if isinstance(difficulty, Difficulty):
            return difficulty
        if isinstance(difficulty, str):
            try:
                return Difficulty(difficulty.lower())
            except ValueError:
                pass
        return Difficulty.INTERMEDIATE

    @staticmethod
    def _parse_ar_actions(actions: Any) -> list:
        if not isinstance(actions, list):
            return []
        return [a for a in actions if isinstance(a, dict)]

    @staticmethod
    def _parse_homework(homework: Any) -> list[HomeworkItem]:
        if not isinstance(homework, list):
            return []
        items: list[HomeworkItem] = []
        for h in homework:
            if not isinstance(h, dict):
                continue
            try:
                items.append(HomeworkItem(
                    title=str(h.get('title', 'Practice'))[:200],
                    description=str(h.get('description', ''))[:500],
                    difficulty=PlannerAgent._resolve_difficulty(h.get('difficulty', 'intermediate')),
                ))
            except Exception:
                continue
        return items

    def _pad_steps(self, steps: list[LessonStep], vision: VisionOutput) -> list[LessonStep]:
        """Pad steps to meet minimum count with sensible defaults."""
        existing_phases = {s.phase for s in steps}
        fallbacks = [
            (LessonPhase.OBSERVE, 'Problem samjhte hain', f'Chaliye is {vision.subject.value} problem ko samajhte hain.'),
            (LessonPhase.CONCEPT, 'Concept samjhao', 'Is concept ko detail mein samajhte hain.'),
            (LessonPhase.STEP_BY_STEP, 'Step by step karte hain', 'Ab hum step by step solve karte hain.'),
            (LessonPhase.CHECKPOINT, 'Check karte hain', 'Kya aapko samajh aa raha hai?'),
            (LessonPhase.SUMMARY, 'Summary', 'Aaj humne kya seekha, ek baar revise karte hain.'),
        ]
        for phase, title, explanation in fallbacks:
            if phase not in existing_phases:
                steps.append(LessonStep(phase=phase, title=title, explanation=explanation, duration_seconds=30))
                if len(steps) >= MIN_STEPS:
                    break
        return steps
