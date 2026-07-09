"""Lesson Planner Agent.

Creates a structured, step-by-step lesson plan for any problem,
adapted to the student's level, learning style, and history.
"""

from typing import Any, Optional

from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.prompts import planner_agent_prompt
from app.ai.teacher.reasoner import LLMProvider, reason
from app.ai.teacher.schemas import (
    LessonPlan,
    LessonStep,
    PlannerOutput,
    StudentContext,
    VisionOutput,
)
from app.core.constants import Difficulty, Subject
from app.core.exceptions import AgentExecutionError
from app.core.logger import get_logger

log = get_logger(__name__)


class PlannerAgent:
    """Generates a complete lesson plan for a given problem and student.

    The planner never teaches — it only designs the teaching sequence.
    """

    def __init__(self, personality: TeacherPersonality) -> None:
        self.personality = personality
        self._prompt = planner_agent_prompt(personality)

    async def plan(
        self,
        vision_output: VisionOutput,
        student: StudentContext,
        provider: str = LLMProvider.GROQ,
    ) -> PlannerOutput:
        """Create a lesson plan based on the vision output and student context.

        Args:
            vision_output: Extracted problem info from the Vision Agent.
            student: Current student profile and history.

        Returns:
            A structured PlannerOutput with lesson plan and strategy.

        Raises:
            AgentExecutionError: If planning fails after retries.
        """
        messages = [
            {'role': 'system', 'content': self._prompt},
            {'role': 'user', 'content': self._build_input_prompt(vision_output, student)},
        ]

        try:
            result = await reason(
                messages=messages,
                provider=provider,
                expect_json=True,
            )
            return self._parse_result(result, vision_output)
        except Exception as exc:
            log.error('planner_failed', error=str(exc))
            return self._fallback_plan(vision_output, student)

    def _build_input_prompt(self, vision: VisionOutput, student: StudentContext) -> str:
        """Format the vision output and student context into a prompt."""
        weak = ', '.join(student.weak_topics) or 'none identified'
        strong = ', '.join(student.strong_topics) or 'none identified'
        recent = ', '.join(student.recent_topics[-5:]) or 'none'

        return f"""Plan a lesson for this problem:

Problem text: {vision.raw_text}
Subject: {vision.subject.value}
Difficulty: {vision.difficulty.value}
Topics detected: {', '.join(vision.topics)}
Problem type: {vision.problem_type}
Formulas: {', '.join(vision.formulas)}

Student profile:
- Level: {student.level.value}
- Weak topics: {weak}
- Strong topics: {strong}
- Recent topics: {recent}
- Session count: {student.session_count}
- Current confidence: {student.current_confidence.value}
- Revision due: {', '.join(student.revision_due)}"""

    def _parse_result(self, result: dict[str, Any], vision: VisionOutput) -> PlannerOutput:
        """Convert the LLM JSON response into a validated PlannerOutput."""
        lesson_data = result.get('lesson_plan', result)
        steps_data = lesson_data.get('steps', [])

        steps = []
        for i, s in enumerate(steps_data):
            try:
                step = LessonStep(
                    phase=s.get('phase', 'step_by_step'),
                    title=s.get('title', f'Step {i + 1}'),
                    explanation=s.get('explanation', ''),
                    board_actions=s.get('board_actions', []),
                    ar_actions=s.get('ar_actions', []),
                    hint=s.get('hint', ''),
                    duration_seconds=s.get('duration_seconds', 30),
                )
                steps.append(step)
            except Exception as exc:
                log.warning('planner_step_parse_failed', index=i, error=str(exc))
                continue

        if not steps:
            log.warning('planner_no_steps_generated, using fallback')
            return self._fallback_plan(vision, StudentContext(user_id=''))

        lesson_plan = LessonPlan(
            subject=lesson_data.get('subject', vision.subject),
            topic=lesson_data.get('topic', vision.topics[0] if vision.topics else 'General'),
            difficulty=lesson_data.get('difficulty', vision.difficulty),
            prerequisite_topics=lesson_data.get('prerequisite_topics', []),
            steps=steps,
            estimated_total_duration=lesson_data.get('estimated_total_duration', sum(s.duration_seconds for s in steps)),
            key_concepts=lesson_data.get('key_concepts', vision.topics),
            homework=lesson_data.get('homework', []),
        )

        return PlannerOutput(
            lesson_plan=lesson_plan,
            teaching_strategy=result.get('teaching_strategy', 'step_by_step'),
            adaptations=result.get('adaptations', []),
        )

    def _fallback_plan(self, vision: VisionOutput, student: StudentContext) -> PlannerOutput:
        """Generate a safe default plan when the LLM call fails."""
        step = LessonStep(
            phase='step_by_step',
            title='Problem ko samajhte hain',
            explanation=f'Chaliye is {vision.subject.value} problem ko step by step solve karte hain. '
                        f'Pehle problem ko dhyan se padhte hain.',
            duration_seconds=45,
        )
        plan = LessonPlan(
            subject=vision.subject,
            topic=vision.topics[0] if vision.topics else 'General',
            difficulty=student.level,
            steps=[step],
            estimated_total_duration=45,
            key_concepts=vision.topics,
        )
        return PlannerOutput(
            lesson_plan=plan,
            teaching_strategy='step_by_step',
            adaptations=['simplify_language', 'more_examples'],
        )
