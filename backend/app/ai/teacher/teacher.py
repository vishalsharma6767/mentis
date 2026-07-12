"""Teacher Agent — core teaching engine.

The Teacher is the heart of Mentis. It takes a lesson plan step plus
student context and generates a Hinglish teaching response that includes:

  - Warm, patient explanation in Hinglish (80% Hindi / 20% English)
  - Key points for the student to remember
  - Checkpoints to verify understanding
  - Worked examples with step-by-step reasoning
  - Analogies using real-life Indian-context examples
  - Board drawing actions for visual teaching
  - Speech instructions for the TTS engine

This agent never gives away the answer — it guides the student step by
step, exactly like an experienced Indian classroom teacher.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.utils.json_utils import extract_json
from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.prompts import teacher_agent_prompt
from app.ai.teacher.schemas import (
    MemoryUpdate,
    PlannerOutput,
    StudentContext,
    TeacherOutput,
    TeacherResponse,
    VisionOutput,
)
from app.core.constants import TeachingLanguage
from app.core.exceptions import AgentExecutionError
from app.core.logger import get_logger

log = get_logger(__name__)


class TeacherAgent:
    """Generates structured teaching responses in Hinglish.

    Takes a lesson plan step (from PlannerAgent) plus student context
    and produces a complete TeacherResponse with explanation, key points,
    checkpoints, examples, board actions, and speech instructions.

    Usage::

        teacher = TeacherAgent(personality)
        output = await teacher.teach(
            step=plan.lesson_plan.steps[0],
            plan=plan,
            vision=vision_output,
            student=student_context,
        )
        # output.response.explanation contains the Hinglish teaching text
    """

    def __init__(
        self,
        personality: Optional[TeacherPersonality] = None,
        gateway: Optional[AIGateway] = None,
    ) -> None:
        self.personality = personality or TeacherPersonality()
        self._gateway = gateway
        self._prompt = teacher_agent_prompt(self.personality)

    async def teach(
        self,
        step_index: int,
        plan: Optional[PlannerOutput],
        vision: VisionOutput,
        student: StudentContext,
        student_message: str = '',
        emotion: str = 'neutral',
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        dialogue_context: str = '',
        revision_hint: str = '',
        provider: Optional[LLMProvider] = None,
    ) -> TeacherOutput:
        """Generate a teaching response for the given lesson step.

        Args:
            step_index: Which step of the lesson plan to teach.
            plan: The full lesson plan (or None for fallback).
            vision: The original vision/problem extraction.
            student: Current student profile and knowledge state.
            student_message: The student's latest message.
            emotion: Detected student emotion.
            language: Target teaching language.
            dialogue_context: Summary of previous conversation turns.
            revision_hint: Specific instructions from the Critic for revision.
            provider: Optional LLM provider override.

        Returns:
            Structured TeacherOutput containing the response and metadata.

        Raises:
            AgentExecutionError: If teaching fails catastrophically.
        """
        log.info(
            'teacher_start',
            step=step_index,
            emotion=emotion,
            topic=vision.topics[0] if vision.topics else 'General',
        )

        step = None
        if plan and plan.lesson_plan and step_index < len(plan.lesson_plan.steps):
            step = plan.lesson_plan.steps[step_index]

        messages = [
            {'role': 'system', 'content': self._prompt},
            {'role': 'user', 'content': self._build_input_prompt(
                step=step,
                step_index=step_index,
                plan=plan,
                vision=vision,
                student=student,
                student_message=student_message,
                emotion=emotion,
                language=language,
                dialogue_context=dialogue_context,
                revision_hint=revision_hint,
            )},
        ]

        for attempt in range(1, 4):
            try:
                gateway = await self._resolve_gateway()
                response = await gateway.execute(
                    messages=messages,
                    provider=provider,
                    expect_json=True,
                    max_tokens=2048,
                    temperature=0.2,
                    use_cache=True,
                )

                parsed = extract_json(response.text)
                if parsed is None:
                    raise ValueError('No valid JSON found in response')

                result = self._parse_result(
                    parsed, step, step_index, vision, student, language,
                )

                log.info(
                    'teacher_success',
                    step=step_index,
                    explanation_len=len(result.response.explanation),
                    key_points=len(result.response.key_points),
                    latency_ms=response.latency_ms,
                )
                return result

            except Exception as exc:
                log.warning('teacher_attempt_failed', attempt=attempt, error=str(exc)[:120])
                if attempt < 3:
                    await asyncio.sleep(1.5 * attempt)
                    continue

        log.error('teacher_all_attempts_failed', step=step_index)
        raise AgentExecutionError(
            agent_name='teacher',
            message='No AI provider could generate a teaching response',
        )

    # ── Prompt building ─────────────────────────────────────────────────

    def _build_input_prompt(
        self,
        step: Any,
        step_index: int,
        plan: Optional[PlannerOutput],
        vision: VisionOutput,
        student: StudentContext,
        student_message: str,
        emotion: str,
        language: TeachingLanguage,
        dialogue_context: str,
        revision_hint: str,
    ) -> str:
        """Assemble the full input context for the teacher LLM call."""
        parts: list[str] = []

        # Vision / problem context
        parts.append(json.dumps({
            'problem': {
                'text': vision.raw_text[:800],
                'subject': vision.subject.value,
                'difficulty': vision.difficulty.value,
                'topics': vision.topics,
                'type': vision.problem_type,
                'formulas': vision.formulas,
            },
        }, indent=2))

        # Lesson plan
        if plan and plan.lesson_plan:
            steps_text = '\n'.join(
                f'  Step {i + 1}: [{s.phase}] {s.title}'
                for i, s in enumerate(plan.lesson_plan.steps)
            )
            parts.append(f'Lesson plan:\nStrategy: {plan.teaching_strategy}')
            parts.append(f'Adaptations: {", ".join(plan.adaptations)}')
            parts.append(f'Steps:\n{steps_text}')
            parts.append(f'Current step to teach: {step_index + 1} of {len(plan.lesson_plan.steps)}')

        # Current step detail
        if step:
            parts.append(json.dumps({
                'current_step': {
                    'phase': step.phase.value if hasattr(step.phase, 'value') else str(step.phase),
                    'title': step.title,
                    'explanation': step.explanation,
                    'hint': step.hint,
                    'duration_seconds': step.duration_seconds,
                },
            }, indent=2))

        # Student context
        parts.append(json.dumps({
            'student': {
                'level': student.level.value,
                'weak_topics': student.weak_topics,
                'strong_topics': student.strong_topics,
                'confidence': student.current_confidence.value if hasattr(student.current_confidence, 'value') else str(student.current_confidence),
            },
            'student_message': student_message,
            'emotion': emotion,
            'language': language.value,
        }, indent=2))

        if dialogue_context:
            parts.append(f'Previous dialogue:\n{dialogue_context[:500]}')

        if revision_hint:
            parts.append(f'Revision needed — fix these:\n{revision_hint}')

        parts.append(
            'Teach this step in Hinglish like an experienced Indian classroom teacher. '
            'Never give the final answer — guide the student step by step.'
        )

        return '\n\n'.join(parts)

    # ── Result parsing ──────────────────────────────────────────────────

    def _parse_result(
        self,
        result: dict[str, Any],
        step: Any,
        step_index: int,
        vision: VisionOutput,
        student: StudentContext,
        language: TeachingLanguage,
    ) -> TeacherOutput:
        """Convert the LLM JSON response into a validated TeacherOutput."""
        response_data = result.get('response', result.get('step', result))

        explanation = str(response_data.get('explanation', ''))[:4000]
        if not explanation:
            explanation = str(response_data.get('speech', {}).get('text', ''))[:4000]
        if not explanation and step:
            explanation = step.explanation

        key_points = [str(kp)[:300] for kp in (response_data.get('key_points', []) or [])]
        checkpoints = [str(cp)[:500] for cp in (response_data.get('checkpoints', []) or [])]
        examples = [str(ex)[:500] for ex in (response_data.get('examples', []) or [])]

        analogy = str(response_data.get('analogy', ''))[:500]
        language_hint = str(response_data.get('language_hint', language.value))

        board_actions = response_data.get('board_actions', [])
        if not isinstance(board_actions, list):
            board_actions = []
        if step and hasattr(step, 'board_actions') and step.board_actions:
            board_actions = list(step.board_actions) + board_actions

        ar_actions = response_data.get('ar_actions', [])
        if not isinstance(ar_actions, list):
            ar_actions = []
        if step and hasattr(step, 'ar_actions') and step.ar_actions:
            ar_actions = list(step.ar_actions) + ar_actions

        speech_data = response_data.get('speech', {}) or {}
        speech = None
        if speech_data and isinstance(speech_data, dict) and speech_data.get('text'):
            from app.ai.teacher.schemas import SpeechAction, SpeechEmotion, SpeechSpeed
            speech = SpeechAction(
                text=str(speech_data['text'])[:2000],
                language=str(speech_data.get('language', 'hi-IN')),
                emotion=SpeechEmotion(speech_data.get('emotion', 'neutral')) if hasattr(SpeechEmotion, speech_data.get('emotion', '').upper()) else SpeechEmotion.NEUTRAL,
                speed=SpeechSpeed(speech_data.get('speed', 'slow')) if hasattr(SpeechSpeed, speech_data.get('speed', '').upper()) else SpeechSpeed.SLOW,
            )

        memory = response_data.get('memory_update', {})
        if isinstance(memory, dict):
            memory_update = MemoryUpdate(
                topics_covered=[str(t)[:200] for t in (memory.get('topics_covered', vision.topics) or [])],
                topics_struggled=[str(t)[:200] for t in (memory.get('topics_struggled', student.weak_topics) or [])],
                topics_mastered=[str(t)[:200] for t in (memory.get('topics_mastered', []) or [])],
                mistakes_detected=list(memory.get('mistakes_detected', []) or []),
                confidence_estimate=memory.get('confidence_estimate'),
                session_summary=str(memory.get('session_summary', ''))[:500] or None,
            )
        else:
            memory_update = MemoryUpdate(topics_covered=vision.topics)

        quiz_data = response_data.get('quiz')
        quiz = None
        if quiz_data and isinstance(quiz_data, dict) and quiz_data.get('question'):
            from app.ai.teacher.schemas import QuizItem
            quiz = QuizItem(
                question=str(quiz_data['question'])[:500],
                options=[str(o)[:200] for o in (quiz_data.get('options', []) or [])],
                correct_answer=str(quiz_data.get('correct_answer', ''))[:200],
                explanation=str(quiz_data.get('explanation', ''))[:500],
                hint=str(quiz_data.get('hint', ''))[:300],
            )

        response = TeacherResponse(
            explanation=explanation,
            key_points=key_points[:8],
            checkpoints=checkpoints[:5],
            examples=examples[:5],
            analogy=analogy,
            language_hint=language_hint,
            speech=speech,
            board_actions=board_actions[:20],
            ar_instructions=ar_actions[:10],
            quiz=quiz,
            memory_update=memory_update,
        )

        topic = ''
        if plan and plan.lesson_plan:
            topic = plan.lesson_plan.topic
        if not topic and vision.topics:
            topic = vision.topics[0]

        return TeacherOutput(
            response=response,
            lesson_plan=plan.lesson_plan if plan else None,
            subject=vision.subject,
            topic=topic,
            student_level=student.level,
            language=language,
        )

    # ── Fallback ────────────────────────────────────────────────────────

    def _fallback_output(
        self,
        step: Any,
        step_index: int,
        vision: VisionOutput,
        student: StudentContext,
        language: TeachingLanguage,
    ) -> TeacherOutput:
        """Generate a contextual fallback using vision.raw_text directly."""
        log.info('teacher_using_fallback', step=step_index)

        raw = vision.raw_text[:500].strip()
        subject_name = vision.subject.value.capitalize()
        topic_list = vision.topics[:3] if vision.topics else []
        topic_str = ', '.join(topic_list) if topic_list else subject_name

        if step and step.explanation:
            base = step.explanation
            extra_lines = [
                f'\n\nAaiye, is concept ko aur detail mein samajhte hain. ',
                f'{topic_str} ke baare mein hum step by step padhenge. ',
                f'Problem yeh hai: {raw[:200]}',
                f'\nDhyan se padhiye aur agar koi doubt ho toh poochh sakte hain. Main aapko har step samjhaunga.',
            ]
            explanation = base + ''.join(extra_lines)
        else:
            lines = [
                f'Aapne jo problem poochhi hai, uske baare mein baat karte hain.',
                f'',
                f'Problem: {raw}',
                f'',
                f'Yeh {subject_name} ka question hai. Ismein {topic_str} se related concepts hain.',
            ]
            if student.level.value in ('beginner', 'elementary'):
                lines.append('Pehle basic concepts ko samajhte hain, phir step by step aage badhenge.')
            else:
                lines.append('Hum is problem ko step by step solve karenge.')
            lines.extend([
                f'',
                f'Step 1: Problem ko dhyan se padhein — samjhein ki kya poochha gaya hai.',
                f'Step 2: Jo information di gayi hai, use identify karein.',
                f'Step 3: Formula ya concept apply karke solution nikaalein.',
                f'Step 4: Answer ko verify karein.',
                f'',
                f'Kya aapne kabhi aisa sawaal pehle solve kiya hai? Agar nahi, toh chinta mat karo — main aapko har step samjhaunga.',
            ])
            explanation = '\n'.join(lines)

        weaknesses = ', '.join(student.weak_topics[:3]) if student.weak_topics else 'general concepts'
        key_points = [
            f'Yeh {topic_str} ka problem hai',
            f'Dhyan se di gayi information ko padhein',
            f'Step by step approach use karein',
            f'Answer ko verify karna mat bhoolen',
        ]
        checkpoints = [
            f'Kya aapko problem samajh aa gayi?',
            f'Kya aap bata sakte hain ki kis concept ki zaroorat hai?',
            f'Koi step hai jo mushkil lag raha hai?',
        ]
        examples = [f'{topic_str} se related practice problem: "{raw[:100]}..." Is tarah ke questions mein pehle formula pehchaan na zaroori hai.']
        analogy = f'{topic_str} ko samajhne ke liye, real life example lete hain. Jaise aap roz {weaknesses.split(",")[0] if weaknesses else "cheezein"} face karte hain, waise hi is problem mein bhi same concept apply hota hai.'

        response = TeacherResponse(
            explanation=explanation,
            key_points=key_points,
            checkpoints=checkpoints,
            examples=examples,
            analogy=analogy,
            language_hint=language.value,
            speech=None,
            board_actions=step.board_actions if step and hasattr(step, 'board_actions') else [],
            memory_update=MemoryUpdate(topics_covered=vision.topics),
            ask_doubts=True,
        )

        topic = vision.topics[0] if vision.topics else 'General'

        return TeacherOutput(
            response=response,
            subject=vision.subject,
            topic=topic,
            student_level=student.level,
            language=language,
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
