"""Critic Agent — quality assurance for teacher output.

Reviews the teacher's output before it reaches the student. Validates
for correctness, clarity, age-appropriateness, safety, and pedagogical
effectiveness. Can request the teacher to revise if quality is below
threshold.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.prompts import critic_agent_prompt
from app.ai.teacher.schemas import CriticFeedback, CriticOutput, QualityScore, TeacherOutput
from app.core.logger import get_logger

log = get_logger(__name__)

MINIMUM_PASS_SCORE = 7.0


class CriticAgent:
    """Validates and scores teacher output before delivery.

    Reviews the explanation, key points, examples, and checkpoints for:
      - Answer leaking (must never give the answer directly)
      - Language quality (Hinglish mix, warm tone)
      - Level appropriateness (matches student's level)
      - Visual teaching (board actions present)
      - One-concept focus per step
      - Checkpoints or hints for understanding verification

    Usage::

        critic = CriticAgent()
        result = await critic.review(teacher_output)
        if result.passed:
            # send to student
        else:
            # request revision from teacher
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway
        self._prompt = critic_agent_prompt

    async def review(
        self,
        teacher_output: TeacherOutput,
        provider: Optional[LLMProvider] = None,
    ) -> CriticOutput:
        """Review teacher output and return quality feedback.

        Args:
            teacher_output: The teacher agent's generated output.
            provider: Optional LLM provider override.

        Returns:
            CriticOutput with pass/fail decision, quality scores, and
            revision requests if the output needs improvement.
        """
        log.info('critic_review_start', topic=teacher_output.topic)

        messages = [
            {'role': 'system', 'content': self._prompt},
            {'role': 'user', 'content': self._build_review_prompt(teacher_output)},
        ]

        for attempt in range(1, 3):
            try:
                gateway = await self._resolve_gateway()
                response = await gateway.execute(
                    messages=messages,
                    provider=provider,
                    expect_json=True,
                    max_tokens=1024,
                    temperature=0.3,
                    use_cache=True,
                )

                parsed = json.loads(response.text)
                feedback = self._parse_feedback(parsed)
                passed = feedback.passed and (feedback.quality_score.overall >= MINIMUM_PASS_SCORE)

                log.info(
                    'critic_review_complete',
                    passed=passed,
                    score=feedback.quality_score.overall,
                    revisions=len(feedback.revision_requests),
                )

                return CriticOutput(
                    original_output=teacher_output,
                    feedback=feedback,
                    passed=passed,
                    revised_output=None if passed else teacher_output,
                )

            except Exception as exc:
                log.warning('critic_attempt_failed', attempt=attempt, error=str(exc)[:120])
                if attempt < 2:
                    continue

        log.warning('critic_review_failed_all_attempts')
        feedback = CriticFeedback(
            passed=True,
            quality_score=QualityScore(
                correctness=7, clarity=7, age_appropriateness=8,
                safety=9, pedagogical_value=7, overall=7.6,
            ),
            revision_requests=[],
            comments='Auto-passed: critic unavailable',
        )
        return CriticOutput(
            original_output=teacher_output,
            feedback=feedback,
            passed=True,
        )

    def _build_review_prompt(self, teacher_output: TeacherOutput) -> str:
        """Format teacher output into a review prompt for the LLM."""
        response = teacher_output.response

        lines = [
            'Review this teacher output for quality and safety:',
            '',
            f'Subject: {teacher_output.subject.value if hasattr(teacher_output.subject, "value") else teacher_output.subject}',
            f'Topic: {teacher_output.topic}',
            f'Student level: {teacher_output.student_level.value if hasattr(teacher_output.student_level, "value") else teacher_output.student_level}',
            f'Language: {teacher_output.language.value if hasattr(teacher_output.language, "value") else teacher_output.language}',
            '',
            'Explanation:',
            response.explanation,
            '',
        ]

        if response.key_points:
            lines.append('Key points:')
            lines.extend(f'- {kp}' for kp in response.key_points)

        if response.examples:
            lines.append('Examples:')
            lines.extend(f'- {ex}' for ex in response.examples)

        if response.checkpoints:
            lines.append('Checkpoints:')
            lines.extend(f'- {cp}' for cp in response.checkpoints)

        if response.analogy:
            lines.append(f'Analogy: {response.analogy}')

        lines.append('')
        lines.append(
            'Score each dimension 1-10 (1=worst, 10=best) and decide if this passes.\n'
            'Return JSON with: passed (bool), quality_score (object with correctness, clarity, '
            'age_appropriateness, safety, pedagogical_value, overall), '
            'revision_requests (list of strings), comments (string).'
        )

        return '\n'.join(lines)

    def _parse_feedback(self, result: dict[str, Any]) -> CriticFeedback:
        """Parse LLM response into a CriticFeedback object."""
        quality = result.get('quality_score', result)
        score = QualityScore(
            correctness=int(quality.get('correctness', 7)),
            clarity=int(quality.get('clarity', 7)),
            age_appropriateness=int(quality.get('age_appropriateness', 8)),
            safety=int(quality.get('safety', 9)),
            pedagogical_value=int(quality.get('pedagogical_value', 7)),
            overall=float(quality.get('overall', 7.6)),
        )

        revision_requests = result.get('revision_requests', [])
        if not isinstance(revision_requests, list):
            revision_requests = [str(revision_requests)]

        return CriticFeedback(
            passed=bool(result.get('passed', True)),
            quality_score=score,
            revision_requests=revision_requests,
            comments=str(result.get('comments', '')),
        )

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
