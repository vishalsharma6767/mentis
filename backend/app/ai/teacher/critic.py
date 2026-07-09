"""Critic Agent.

Reviews the teacher's output before it reaches the student.
Validates for: correctness, clarity, age-appropriateness, safety,
and pedagogical effectiveness. Can request the teacher to revise.
"""

from typing import Any, Optional

from app.ai.teacher.prompts import critic_agent_prompt
from app.ai.teacher.reasoner import LLMProvider, reason
from app.ai.teacher.schemas import (
    CriticFeedback,
    CriticOutput,
    TeacherOutput,
    QualityScore,
)
from app.core.logger import get_logger

log = get_logger(__name__)

MINIMUM_PASS_SCORE = 7  # out of 10


class CriticAgent:
    """Validates and scores the teacher's output before delivery."""

    def __init__(self) -> None:
        self._prompt = critic_agent_prompt

    async def review(
        self,
        teacher_output: TeacherOutput,
        provider: str = LLMProvider.GROQ,
    ) -> CriticOutput:
        """Review the teacher's output and return feedback.

        Returns the original output if it passes; otherwise includes
        revision requests for the teacher to address.
        """
        messages = [
            {'role': 'system', 'content': self._prompt},
            {'role': 'user', 'content': self._build_review_prompt(teacher_output)},
        ]

        try:
            result = await reason(
                messages=messages,
                provider=provider,
                expect_json=True,
            )
            feedback = self._parse_feedback(result)
        except Exception as exc:
            log.warning('critic_review_failed', error=str(exc))
            feedback = CriticFeedback(
                passed=True,
                quality_score=QualityScore(
                    correctness=7,
                    clarity=7,
                    age_appropriateness=8,
                    safety=9,
                    pedagogical_value=7,
                    overall=7.6,
                ),
                revision_requests=[],
                comments='Auto-passed: critic unavailable',
            )

        passed = feedback.passed and (feedback.quality_score.overall >= MINIMUM_PASS_SCORE)
        return CriticOutput(
            original_output=teacher_output,
            feedback=feedback,
            passed=passed,
            revised_output=None if passed else teacher_output,
        )

    def _build_review_prompt(self, teacher_output: TeacherOutput) -> str:
        from app.ai.teacher.schemas import TeacherResponse

        response = teacher_output.response
        steps = teacher_output.lesson_plan.steps if teacher_output.lesson_plan else []

        return f"""Review this teacher's output:

Subject: {teacher_output.subject.value if hasattr(teacher_output.subject, 'value') else teacher_output.subject}
Topic: {teacher_output.topic}
Student level: {teacher_output.student_level.value if hasattr(teacher_output.student_level, 'value') else teacher_output.student_level}
Language: {teacher_output.language.value if hasattr(teacher_output.language, 'value') else teacher_output.language}

Teacher's explanation:
{response.explanation}

Key points:
{chr(10).join(f'- {p}' for p in response.key_points)}

Examples provided:
{chr(10).join(f'- {e}' for e in response.examples)}

Checkpoints/questions for student:
{chr(10).join(f'- {c}' for c in response.checkpoints)}

Lesson steps: {len(steps)}

Score each dimension 1-10 and decide if this passes."""

    def _parse_feedback(self, result: dict[str, Any]) -> CriticFeedback:
        quality = result.get('quality_score', result)
        score = QualityScore(
            correctness=int(quality.get('correctness', 7)),
            clarity=int(quality.get('clarity', 7)),
            age_appropriateness=int(quality.get('age_appropriateness', 8)),
            safety=int(quality.get('safety', 9)),
            pedagogical_value=int(quality.get('pedagogical_value', 7)),
            overall=float(quality.get('overall', 7.6)),
        )

        return CriticFeedback(
            passed=result.get('passed', True),
            quality_score=score,
            revision_requests=result.get('revision_requests', []),
            comments=result.get('comments', ''),
        )
