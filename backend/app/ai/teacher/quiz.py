"""Quiz Agent — generates checkpoint quizzes and assessments.

Creates short quizzes to verify understanding after each teaching step.
Quizzes are:
  - At the right difficulty level for the student
  - Focused on ONE concept per question
  - Multiple choice with clear distractors
  - Followed by an explanation of the correct answer
"""

from __future__ import annotations

import json
from typing import Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.schemas import QuizItem, StudentContext
from app.core.logger import get_logger

log = get_logger(__name__)

MAX_QUIZ_QUESTIONS = 3
MIN_QUIZ_QUESTIONS = 1


class QuizAgent:
    """Generates checkpoint quizzes to verify student understanding.

    Usage::

        quiz = QuizAgent()
        items = await quiz.generate(
            topic="Linear Equations",
            concept="Variable isolation",
            student=student_ctx,
        )
        # items[0].question, items[0].options, items[0].correct_answer
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def generate(
        self,
        topic: str,
        concept: str = '',
        student: Optional[StudentContext] = None,
        num_questions: int = 1,
        provider: Optional[LLMProvider] = None,
    ) -> list[QuizItem]:
        """Generate quiz questions for the given topic and concept.

        Args:
            topic: The main topic (e.g. "Linear Equations").
            concept: Specific concept to test (e.g. "Variable isolation").
            student: Optional student context for difficulty tuning.
            num_questions: Number of questions to generate.
            provider: Optional LLM provider override.

        Returns:
            List of QuizItem objects.
        """
        log.info('quiz_generate_start', topic=topic, concept=concept, count=num_questions)

        if not topic or not topic.strip():
            log.warning('quiz_empty_topic')
            return self._fallback_quiz()

        messages = [
            {
                'role': 'system',
                'content': (
                    'You are Mentis\'s Quiz Agent. Create checkpoint quiz questions '
                    'in Hinglish (80% Hindi, 20% English) to verify student understanding.\n\n'
                    'Rules:\n'
                    '- ONE concept per question\n'
                    '- Multiple choice with 4 options\n'
                    '- Include plausible distractors\n'
                    '- Correct answer must be unambiguous\n'
                    '- Explanation must teach WHY it\'s correct\n'
                    '- Never trick or confuse the student\n\n'
                    'Return JSON: {"questions": [{"question": "...", "options": ["A", "B", "C", "D"], '
                    '"correct_answer": "A", "explanation": "...", "hint": "..."}]}'
                ),
            },
            {'role': 'user', 'content': self._build_prompt(topic, concept, student, num_questions)},
        ]

        for attempt in range(1, 3):
            try:
                gateway = await self._resolve_gateway()
                response = await gateway.execute(
                    messages=messages,
                    provider=provider,
                    expect_json=True,
                    max_tokens=2048,
                    temperature=0.6,
                    use_cache=True,
                )

                parsed = json.loads(response.text)
                raw_questions = parsed.get('questions', [parsed])
                items = self._parse_questions(raw_questions, num_questions)

                log.info('quiz_generate_success', count=len(items))
                return items

            except Exception as exc:
                log.warning('quiz_attempt_failed', attempt=attempt, error=str(exc)[:120])
                if attempt < 2:
                    continue

        log.warning('quiz_fallback')
        return self._fallback_quiz()

    def _build_prompt(
        self,
        topic: str,
        concept: str,
        student: Optional[StudentContext],
        num_questions: int,
    ) -> str:
        level = ''
        weak = []
        if student:
            level = student.level.value if hasattr(student.level, 'value') else str(student.level)
            weak = student.weak_topics[:3]

        return json.dumps({
            'topic': topic,
            'concept': concept or topic,
            'student_level': level or 'intermediate',
            'weak_areas': weak,
            'num_questions': min(num_questions, MAX_QUIZ_QUESTIONS),
            'instructions': 'Create checkpoint questions in Hinglish. Make them clear and fair.',
        }, indent=2)

    def _parse_questions(self, raw: list, max_items: int) -> list[QuizItem]:
        items: list[QuizItem] = []
        for q in raw[:max_items]:
            if not isinstance(q, dict):
                continue
            try:
                options = q.get('options', [])
                if isinstance(options, str):
                    options = [options]
                correct = str(q.get('correct_answer', q.get('answer', '')))[:200]
                items.append(QuizItem(
                    question=str(q.get('question', ''))[:500],
                    options=[str(o)[:200] for o in options[:4]],
                    correct_answer=correct,
                    explanation=str(q.get('explanation', ''))[:500],
                    hint=str(q.get('hint', ''))[:300],
                ))
            except Exception:
                continue
        return items[:max_items]

    def _fallback_quiz(self) -> list[QuizItem]:
        return [
            QuizItem(
                question='Kya aapko yeh concept samajh aa gaya? Agar haan, toh aap kaise explain karenge?',
                options=['Haan, samajh aa gaya', 'Thoda samajh aa gaya', 'Nahi samajh aaya', 'Aur examples chahiye'],
                correct_answer='Haan, samajh aa gaya',
                explanation='Agar aap samajh gaye hain toh hum next step par chalein. Agar nahi, toh phir se samjhaate hain.',
                hint='Apne words mein samjhaane ki koshish karo',
            ),
        ]

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
