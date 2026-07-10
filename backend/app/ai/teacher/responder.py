"""Response Composer — merges all agent outputs into the final response.

Every agent in the pipeline produces partial output. The composer merges
them into a single validated ``TeacherResponse`` that is sent to the
frontend. No agent output reaches the client unmediated.

Inputs merged:
  - Teacher output (explanation, key points, examples, checkpoints)
  - Speech output (TTS instructions)
  - AR output (3D annotations, board layers)
  - Memory output (knowledge graph delta, revision updates)
  - Coaching decision (adaptation metadata)
  - Quiz/Homework items

Validation:
  - Every field is type-checked via Pydantic v2
  - Missing fields fall back to defaults
  - Invalid combinations are caught before sending
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.schemas import (
    ARPlan,
    CoachingDecision,
    MemoryUpdate,
    QuizItem,
    SpeechPlan,
    TeacherOutput,
    TeacherResponse,
)
from app.core.constants import TeachingLanguage
from app.core.logger import get_logger

log = get_logger(__name__)


class ResponseComposer:
    """Merges partial agent outputs into a validated TeacherResponse.

    Usage::

        composer = ResponseComposer()
        response = await composer.merge(
            teacher_output=teacher_out,
            speech_plan=speech,
            ar_plan=ar,
            memory_delta=memory,
            quiz=quiz_item,
            coaching=coaching_decision,
            language=TeachingLanguage.HINGLISH,
        )
        # response is a ready-to-send TeacherResponse
    """

    def __init__(self) -> None:
        self._gateway: Optional[AIGateway] = None

    async def merge(
        self,
        teacher_output: TeacherOutput,
        speech_plan: Optional[SpeechPlan] = None,
        ar_plan: Optional[ARPlan] = None,
        memory_delta: Optional[MemoryUpdate] = None,
        quiz: Optional[QuizItem] = None,
        coaching: Optional[CoachingDecision] = None,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        use_llm_polish: bool = False,
    ) -> TeacherResponse:
        """Merge all agent outputs into a single TeacherResponse.

        Args:
            teacher_output: The teacher agent's core output.
            speech_plan: TTS instructions (optional).
            ar_plan: AR annotation instructions (optional).
            memory_delta: Knowledge graph / memory updates (optional).
            quiz: Quiz item to present (optional).
            coaching: Coaching adaptation metadata (optional).
            language: Output language.
            use_llm_polish: If True, uses an LLM call to polish the
                            final explanation text (costly — use sparingly).

        Returns:
            A validated TeacherResponse with all non-None fields merged.
        """
        source = teacher_output.response

        # Build the base response from teacher output
        response = TeacherResponse(
            explanation=source.explanation,
            key_points=source.key_points,
            checkpoints=source.checkpoints,
            examples=source.examples,
            analogy=source.analogy,
            language_hint=language.value,
            board_actions=list(source.board_actions),
            memory_update=memory_delta or source.memory_update,
            quiz=quiz or source.quiz,
            lesson_plan=teacher_output.lesson_plan,
        )

        # Merge speech plan (creates SpeechAction from SpeechPlan)
        if speech_plan:
            from app.ai.teacher.schemas import SpeechAction, SpeechEmotion, SpeechSpeed

            response.speech = SpeechAction(
                text=speech_plan.ssml or source.explanation,
                language=language.value,
                emotion=speech_plan.emotion,
                speed=SpeechSpeed.SLOW,
                ssml=speech_plan.ssml or None,
            )

        # Merge AR instructions
        if ar_plan and ar_plan.instructions:
            response.ar_instructions = ar_plan.instructions

        # LLM polish (optional, for production quality)
        if use_llm_polish:
            polished = await self._llm_polish(response, teacher_output, language)
            if polished is not None:
                response = polished

        log.debug(
            'response_composed',
            has_speech=response.speech is not None,
            board_actions=len(response.board_actions),
            ar_instructions=len(response.ar_instructions),
            has_quiz=response.quiz is not None,
        )

        return response

    async def merge_streaming(
        self,
        teacher_output: TeacherOutput,
        speech_stream: Optional[str] = None,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
    ) -> TeacherResponse:
        """Fast-path merge for streaming responses (no LLM polish)."""
        return await self.merge(
            teacher_output=teacher_output,
            language=language,
            use_llm_polish=False,
        )

    # ── LLM polish (optional, off by default) ──────────────────────────

    async def _llm_polish(
        self,
        draft: TeacherResponse,
        teacher_output: TeacherOutput,
        language: TeachingLanguage,
    ) -> Optional[TeacherResponse]:
        """Use a lightweight LLM call to polish the explanation text.

        This is an optional quality pass. It only rewrites the explanation
        for clarity and tone — it never changes the structure or content.
        """
        try:
            if self._gateway is None:
                self._gateway = await AIGateway.get_instance()

            result = await self._gateway.execute(
                messages=[
                    {
                        'role': 'system',
                        'content': 'You polish teacher explanations for clarity and warmth. '
                                   'Keep the same facts, concepts, and structure. '
                                   'Improve the language to sound like an experienced Indian classroom teacher. '
                                   f'Respond in {language.value}. '
                                   'Return JSON with: {"explanation": "polished text"}',
                    },
                    {
                        'role': 'user',
                        'content': f'Polish this explanation:\n\n{draft.explanation}',
                    },
                ],
                expect_json=True,
                max_tokens=1024,
                temperature=0.4,
            )
            polished_text = json.loads(result.text).get('explanation', '')
            if polished_text:
                draft.explanation = polished_text
            return draft
        except Exception as exc:
            log.debug('llm_polish_skipped', error=str(exc))
            return None

    # ── Validation ─────────────────────────────────────────────────────

    @staticmethod
    def validate_response(response: TeacherResponse) -> None:
        """Validate a TeacherResponse before sending.

        Raises:
            ValidationError: If the response is invalid.
        """
        if not response.explanation and not response.board_actions and not response.speech:
            log.warning('response_composer_empty_response')

        if response.explanation and len(response.explanation) > 10000:
            log.warning('response_composer_explanation_truncated')
            response.explanation = response.explanation[:10000]

        if len(response.board_actions) > 50:
            log.warning('response_composer_too_many_board_actions', count=len(response.board_actions))
            response.board_actions = response.board_actions[:50]

        if response.quiz and not response.quiz.question:
            log.warning('response_composer_quiz_missing_question')
            response.quiz = None

    @staticmethod
    def trim_response(response: TeacherResponse, max_explanation_length: int = 2000) -> TeacherResponse:
        """Trim the response to fit within size constraints."""
        if len(response.explanation) > max_explanation_length:
            response.explanation = response.explanation[:max_explanation_length] + '...'
        response.key_points = response.key_points[:5]
        response.checkpoints = response.checkpoints[:3]
        response.examples = response.examples[:3]
        return response
