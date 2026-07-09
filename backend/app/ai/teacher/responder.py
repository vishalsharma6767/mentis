"""Response Composer Agent.

Takes outputs from all pipeline agents (Teacher, AR, Speech, Memory,
Coach, Critic) and composes the final ``TeacherResponse`` sent to
the frontend. This is the last step before the WebSocket message.
"""

from typing import Any, Optional

from app.ai.teacher.prompts import composer_agent_prompt
from app.ai.teacher.reasoner import LLMProvider, reason
from app.ai.teacher.schemas import (
    ConfidenceLevel,
    MemoryUpdate,
    QuizItem,
    StudentContext,
    TeacherOutput,
    TeacherResponse,
)
from app.core.constants import TeachingLanguage
from app.core.logger import get_logger

log = get_logger(__name__)


class ResponderAgent:
    """Composes the final response from all agent outputs."""

    def __init__(self) -> None:
        self._prompt = composer_agent_prompt

    async def compose(
        self,
        teacher_output: TeacherOutput,
        ar_plan: Any,
        speech_plan: Any,
        memory_delta: MemoryUpdate | None,
        quiz: QuizItem | None,
        coaching_decision: Any,
        student: StudentContext,
        dialogue_context: str = '',
        provider: str = LLMProvider.GROQ,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
    ) -> TeacherResponse:
        """Compose all agent outputs into the final TeacherResponse.

        If the LLM is available, uses it to produce a polished response.
        Otherwise falls back to direct composition.
        """
        try:
            result = await reason(
                messages=[
                    {'role': 'system', 'content': self._prompt},
                    {'role': 'user', 'content': self._build_compose_prompt(
                        teacher_output, ar_plan, speech_plan, memory_delta,
                        quiz, coaching_decision, student, dialogue_context, language,
                    )},
                ],
                provider=provider,
                expect_json=True,
            )
            return self._parse_composer_result(result, teacher_output, memory_delta, quiz)
        except Exception as exc:
            log.warning('composer_failed, using direct composition', error=str(exc))
            return self._direct_compose(teacher_output, memory_delta, quiz, language)

    def _build_compose_prompt(
        self,
        teacher_output: TeacherOutput,
        ar_plan: Any,
        speech_plan: Any,
        memory_delta: MemoryUpdate | None,
        quiz: QuizItem | None,
        coaching_decision: Any,
        student: StudentContext,
        dialogue_context: str,
        language: TeachingLanguage,
    ) -> str:
        response = teacher_output.response
        coach_info = ''
        if coaching_decision:
            coach_info = f'Coaching: {coaching_decision.adaptation} ({coaching_decision.reason})'

        return f"""Compose the final teacher response from these agent outputs:

Teacher explanation: {response.explanation[:300]}
Key points: {', '.join(response.key_points[:3])}
Checkpoints: {', '.join(response.checkpoints[:2])}
Examples: {', '.join(response.examples[:2])}
Analogy: {response.analogy or 'none'}
Language: {language.value}

{'Quiz: ' + quiz.question if quiz else 'No quiz'}
Coach says: {coach_info}

{dialogue_context}

Student level: {student.level.value}
Confidence: {student.current_confidence.value}

Compose a natural, warm teacher response that flows conversationally
in {language.value}. Keep it under 200 words for the main explanation."""

    def _parse_composer_result(
        self,
        result: dict[str, Any],
        teacher_output: TeacherOutput,
        memory_delta: MemoryUpdate | None,
        quiz: QuizItem | None,
    ) -> TeacherResponse:
        return TeacherResponse(
            explanation=result.get('explanation', teacher_output.response.explanation),
            key_points=result.get('key_points', teacher_output.response.key_points),
            checkpoints=result.get('checkpoints', teacher_output.response.checkpoints),
            examples=result.get('examples', teacher_output.response.examples),
            analogy=result.get('analogy', teacher_output.response.analogy),
            language_hint=result.get('language_hint', teacher_output.response.language_hint),
            memory_update=memory_delta or teacher_output.response.memory_update,
            quiz=quiz,
            board_actions=teacher_output.response.board_actions,
        )

    def _direct_compose(
        self,
        teacher_output: TeacherOutput,
        memory_delta: MemoryUpdate | None,
        quiz: QuizItem | None,
        language: TeachingLanguage,
    ) -> TeacherResponse:
        return TeacherResponse(
            explanation=teacher_output.response.explanation,
            key_points=teacher_output.response.key_points,
            checkpoints=teacher_output.response.checkpoints,
            examples=teacher_output.response.examples,
            analogy=teacher_output.response.analogy,
            language_hint=language.value,
            memory_update=memory_delta or teacher_output.response.memory_update,
            quiz=quiz,
            board_actions=teacher_output.response.board_actions,
        )
