"""Adaptive Coaching Agent.

Monitors student responses and engagement during a lesson. Adjusts the
teaching strategy in real time: speed up, slow down, add practice
problems, or switch teaching approaches based on student signals.
"""

from __future__ import annotations

from typing import Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.utils.json_utils import extract_json
from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.schemas import CoachingDecision, CoachingSignal, StudentContext
from app.core.logger import get_logger

log = get_logger(__name__)

SIGNAL_HISTORY_LIMIT = 50
RECENT_WINDOW = 5
ACCELERATE_THRESHOLD = 0.8
HESITATION_THRESHOLD = 0.6
STRUGGLE_THRESHOLD = 0.3


class CoachAgent:
    """Monitors student progress and adapts the teaching strategy.

    Uses fast-path heuristics for common student states and falls back
    to LLM analysis for complex or mixed signals.

    Usage::

        coach = CoachAgent(personality)
        coach.add_signal(CoachingSignal(type='correct_answer', confidence=0.9))
        decision = await coach.decide(student=student_ctx)
        # decision.adaptation is 'accelerate', 'slow_down', 'continue', etc.
    """

    def __init__(
        self,
        personality: Optional[TeacherPersonality] = None,
        gateway: Optional[AIGateway] = None,
    ) -> None:
        self.personality = personality or TeacherPersonality()
        self._gateway = gateway
        self._history: list[CoachingSignal] = []

    def add_signal(self, signal: CoachingSignal) -> None:
        """Record a student signal for coaching analysis.

        Args:
            signal: The student signal (answer, hesitation, help request, etc.).
        """
        self._history.append(signal)
        if len(self._history) > SIGNAL_HISTORY_LIMIT:
            self._history = self._history[-SIGNAL_HISTORY_LIMIT:]

    async def decide(
        self,
        student: StudentContext,
        current_step_index: int = 0,
        total_steps: int = 1,
        provider: Optional[LLMProvider] = None,
    ) -> CoachingDecision:
        """Decide if and how to adapt the teaching based on recent signals.

        Uses fast heuristics first; falls back to LLM analysis for
        mixed or borderline cases.

        Args:
            student: Current student profile and knowledge state.
            current_step_index: Which step the student is on.
            total_steps: Total steps in the lesson plan.
            provider: Optional LLM provider override.

        Returns:
            CoachingDecision with adaptation recommendation.
        """
        if not self._history:
            return CoachingDecision(adaptation='continue', confidence=1.0)

        recent = self._history[-RECENT_WINDOW:]
        correct_rate = sum(1 for s in recent if s.type == 'correct_answer') / max(len(recent), 1)
        hesitation_rate = sum(1 for s in recent if s.type == 'hesitation') / max(len(recent), 1)
        wrong_rate = sum(1 for s in recent if s.type == 'wrong_answer') / max(len(recent), 1)
        help_rate = sum(1 for s in recent if s.type in ('help_request', 'confusion')) / max(len(recent), 1)

        # Accelerate: student is consistently correct
        if correct_rate >= ACCELERATE_THRESHOLD and hesitation_rate < 0.2 and wrong_rate < 0.1:
            if current_step_index < total_steps - 1:
                return CoachingDecision(
                    adaptation='accelerate',
                    confidence=min(correct_rate + 0.1, 1.0),
                    reason='Student is answering correctly consistently',
                    suggested_action='Reduce step detail, combine next two steps',
                )
            return CoachingDecision(
                adaptation='provide_challenge',
                confidence=correct_rate,
                reason='Student is mastering this topic',
                suggested_action='Add an advanced extension problem',
            )

        # Slow down: student is struggling
        if hesitation_rate >= HESITATION_THRESHOLD or wrong_rate >= HESITATION_THRESHOLD or help_rate >= 0.5:
            return CoachingDecision(
                adaptation='slow_down',
                confidence=min(hesitation_rate + wrong_rate + 0.2, 1.0),
                reason='Student showing signs of struggle or confusion',
                suggested_action='Break down the current step into smaller sub-steps with simpler language',
            )

        # Repeat step: very high struggle
        if wrong_rate >= STRUGGLE_THRESHOLD and help_rate >= STRUGGLE_THRESHOLD:
            return CoachingDecision(
                adaptation='repeat_step',
                confidence=min(wrong_rate + help_rate, 1.0),
                reason='Student needs to revisit this concept',
                suggested_action='Re-teach the current step with a different approach and more examples',
            )

        # Mixed signals: use LLM for nuanced analysis
        return await self._llm_decide(student, current_step_index, total_steps, provider)

    async def _llm_decide(
        self,
        student: StudentContext,
        current_step_index: int,
        total_steps: int,
        provider: Optional[LLMProvider],
    ) -> CoachingDecision:
        """Use LLM for nuanced coaching decisions on mixed signals."""
        messages = [
            {
                'role': 'system',
                'content': (
                    'You are an adaptive teaching coach. Analyze student signals and decide how to adjust. '
                    'Respond in JSON with:\n'
                    '  - adaptation: "continue" | "accelerate" | "slow_down" | "provide_challenge" | '
                    '"switch_approach" | "repeat_step"\n'
                    '  - confidence: 0.0-1.0\n'
                    '  - reason: short explanation\n'
                    '  - suggested_action: what the teacher should do'
                ),
            },
            {'role': 'user', 'content': self._build_coaching_prompt(student, current_step_index, total_steps)},
        ]

        try:
            gateway = await self._resolve_gateway()
            response = await gateway.execute(
                messages=messages,
                provider=provider,
                expect_json=True,
                max_tokens=512,
                temperature=0.4,
                use_cache=True,
            )

            result = extract_json(response.text)
            if result is None:
                raise ValueError('No valid JSON in coach response')
            return CoachingDecision(
                adaptation=str(result.get('adaptation', 'continue')),
                confidence=float(result.get('confidence', 0.7)),
                reason=str(result.get('reason', '')),
                suggested_action=str(result.get('suggested_action', '')),
            )

        except Exception as exc:
            log.warning('coach_llm_failed', error=str(exc)[:120])
            return CoachingDecision(adaptation='continue', confidence=0.5)

    def _build_coaching_prompt(
        self,
        student: StudentContext,
        current_step_index: int,
        total_steps: int,
    ) -> str:
        """Build the coaching analysis prompt from student signals and context."""
        signals_text = '\n'.join(
            f'{i}: type={s.type}, detail={s.detail or "—"}, confidence={s.confidence}'
            for i, s in enumerate(self._history[-10:])
        )

        return (
            f'Student signals (last 10):\n\n{signals_text}\n\n'
            f'Progress: step {current_step_index + 1} of {total_steps}\n'
            f'Student level: {student.level.value if hasattr(student.level, "value") else student.level}\n'
            f'Confidence: {student.current_confidence.value if hasattr(student.current_confidence, "value") else student.current_confidence}\n'
            f'Weak topics: {", ".join(student.weak_topics[:5])}\n'
            f'Strong topics: {", ".join(student.strong_topics[:3])}\n\n'
            'What adaptation do you recommend?'
        )

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
