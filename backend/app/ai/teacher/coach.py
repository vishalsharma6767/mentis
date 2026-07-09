"""Adaptive Coaching Agent.

Monitors student responses and engagement during a lesson.
Adjusts the teaching strategy in real time: speed up, slow down,
add practice problems, or switch teaching approaches.
"""

from typing import Any, Optional

from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.reasoner import LLMProvider, reason
from app.ai.teacher.schemas import (
    CoachingDecision,
    CoachingSignal,
    StudentContext,
)
from app.core.logger import get_logger

log = get_logger(__name__)


class CoachAgent:
    """Monitors student progress and adapts the teaching strategy."""

    def __init__(self, personality: TeacherPersonality) -> None:
        self.personality = personality
        self._history: list[CoachingSignal] = []

    def add_signal(self, signal: CoachingSignal) -> None:
        """Record a student signal (answer, hesitation, request, etc.)."""
        self._history.append(signal)
        if len(self._history) > 50:
            self._history = self._history[-50:]

    async def decide(
        self,
        student: StudentContext,
        current_step_index: int,
        total_steps: int,
        provider: str = LLMProvider.GROQ,
    ) -> CoachingDecision:
        """Decide if and how to adapt the teaching based on recent signals.

        Returns a CoachingDecision that the brain can use to adjust.
        """
        if not self._history:
            return CoachingDecision(adaptation='continue', confidence=1.0)

        recent = self._history[-5:]
        correct_rate = sum(1 for s in recent if s.type == 'correct_answer') / max(len(recent), 1)
        hesitation_rate = sum(1 for s in recent if s.type == 'hesitation') / max(len(recent), 1)

        # Fast-path heuristic for common cases (no LLM call needed)
        if correct_rate >= 0.8 and hesitation_rate < 0.2:
            if current_step_index < total_steps - 1:
                return CoachingDecision(
                    adaptation='accelerate',
                    confidence=correct_rate,
                    reason='Student consistently correct — moving faster',
                    suggested_action='Reduce step detail, combine next two steps',
                )
            return CoachingDecision(
                adaptation='provide_challenge',
                confidence=correct_rate,
                reason='Student mastering this — offer extension',
                suggested_action='Add an advanced practice problem',
            )

        if hesitation_rate >= 0.6 or correct_rate < 0.3:
            return CoachingDecision(
                adaptation='slow_down',
                confidence=1.0 - hesitation_rate,
                reason='Student struggling — break down further',
                suggested_action='Add intermediate step with simpler explanation',
            )

        # For mixed signals, consult the LLM
        return await self._llm_decide(student, current_step_index, total_steps, provider)

    async def _llm_decide(
        self,
        student: StudentContext,
        current_step_index: int,
        total_steps: int,
        provider: str,
    ) -> CoachingDecision:
        prompt = self._build_coaching_prompt(student, current_step_index, total_steps)
        messages = [
            {
                'role': 'system',
                'content': 'You are an adaptive teaching coach. Analyze student signals and decide how to adjust. '
                           'Respond in JSON with: adaptation (string), confidence (0-1), reason (string), '
                           'suggested_action (string).',
            },
            {'role': 'user', 'content': prompt},
        ]

        try:
            result = await reason(messages=messages, provider=provider, expect_json=True)
            return CoachingDecision(
                adaptation=result.get('adaptation', 'continue'),
                confidence=float(result.get('confidence', 0.7)),
                reason=result.get('reason', ''),
                suggested_action=result.get('suggested_action', ''),
            )
        except Exception as exc:
            log.warning('coach_llm_failed', error=str(exc))
            return CoachingDecision(adaptation='continue', confidence=0.5)

    def _build_coaching_prompt(
        self,
        student: StudentContext,
        current_step_index: int,
        total_steps: int,
    ) -> str:
        signals_text = '\n'.join(
            f'{i}: type={s.type}, detail={s.detail or "—"}, confidence={s.confidence}'
            for i, s in enumerate(self._history[-10:])
        )
        return f"""Student signals (last 10):

{signals_text}

Progress: step {current_step_index + 1} of {total_steps}
Student level: {student.level.value}
Confidence: {student.current_confidence.value}
Weak topics: {', '.join(student.weak_topics)}

What adaptation do you recommend?"""
