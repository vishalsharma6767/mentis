"""Homework Agent — generates practice problems and assignments.

Produces homework items tailored to the student's level, weak areas,
and recent mistakes. Each homework item includes:
  - Practice problems with varying difficulty
  - Conceptual questions to reinforce understanding
  - Step-by-step hints (not solutions)
  - Estimated completion time
"""

from __future__ import annotations

import json
from typing import Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.schemas import HomeworkItem, StudentContext
from app.core.constants import Difficulty
from app.core.logger import get_logger

log = get_logger(__name__)

MAX_HOMEWORK_ITEMS = 5
MIN_HOMEWORK_ITEMS = 1


class HomeworkAgent:
    """Generates personalised homework based on student performance.

    Usage::

        hw = HomeworkAgent()
        items = await hw.generate(
            topic="Linear Equations",
            student=student_ctx,
        )
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def generate(
        self,
        topic: str,
        student: StudentContext,
        weak_concepts: Optional[list[str]] = None,
        num_items: int = MAX_HOMEWORK_ITEMS,
        provider: Optional[LLMProvider] = None,
    ) -> list[HomeworkItem]:
        """Generate homework items for the given topic and student.

        Args:
            topic: The main topic covered in the lesson.
            student: Current student context (level, weak areas, etc.).
            weak_concepts: Specific weak concepts to target.
            num_items: Number of homework items to generate.
            provider: Optional LLM provider override.

        Returns:
            List of HomeworkItem objects.
        """
        log.info('homework_generate_start', topic=topic, count=num_items)

        if not topic or not topic.strip():
            log.warning('homework_empty_topic')
            return self._fallback_items(topic, student)

        messages = [
            {
                'role': 'system',
                'content': (
                    'You are an experienced Indian teacher creating practice homework. '
                    'Generate homework items in Hinglish (80% Hindi, 20% English).\n\n'
                    'Each item must help the student practice WITHOUT giving the answer.\n'
                    'Return JSON: {"homework": [{"title": "...", "description": "...", '
                    '"difficulty": "beginner|intermediate|advanced"}]}'
                ),
            },
            {'role': 'user', 'content': self._build_prompt(topic, student, weak_concepts, num_items)},
        ]

        for attempt in range(1, 3):
            try:
                gateway = await self._resolve_gateway()
                response = await gateway.execute(
                    messages=messages,
                    provider=provider,
                    expect_json=True,
                    max_tokens=2048,
                    temperature=0.7,
                    use_cache=True,
                )

                parsed = json.loads(response.text)
                items = self._parse_items(parsed.get('homework', [parsed]), num_items)

                log.info('homework_generate_success', count=len(items))
                return items

            except Exception as exc:
                log.warning('homework_attempt_failed', attempt=attempt, error=str(exc)[:120])
                if attempt < 2:
                    continue

        log.warning('homework_fallback')
        return self._fallback_items(topic, student)

    def _build_prompt(
        self,
        topic: str,
        student: StudentContext,
        weak_concepts: Optional[list[str]],
        num_items: int,
    ) -> str:
        return json.dumps({
            'topic': topic,
            'student_level': student.level.value if hasattr(student.level, 'value') else str(student.level),
            'weak_areas': weak_concepts or student.weak_topics[:5],
            'recent_mistakes': student.recent_mistakes[:3],
            'num_items': min(num_items, MAX_HOMEWORK_ITEMS),
            'instructions': (
                f'Create {num_items} practice problems in Hinglish for topic: {topic}. '
                'Include a mix of easy, medium, and hard problems. '
                'Add helpful hints but never give the full solution. '
                'Focus on the student\'s weak areas.'
            ),
        }, indent=2)

    def _parse_items(self, raw: list, max_items: int) -> list[HomeworkItem]:
        items: list[HomeworkItem] = []
        for h in raw[:max_items]:
            if not isinstance(h, dict):
                continue
            try:
                difficulty_str = str(h.get('difficulty', 'intermediate')).lower()
                items.append(HomeworkItem(
                    title=str(h.get('title', 'Practice'))[:200],
                    description=str(h.get('description', h.get('problem', '')))[:500],
                    difficulty=self._resolve_difficulty(difficulty_str),
                ))
            except Exception:
                continue
        return items[:max_items]

    def _fallback_items(self, topic: str, student: StudentContext) -> list[HomeworkItem]:
        diff = student.level.value if hasattr(student.level, 'value') else 'intermediate'
        return [
            HomeworkItem(
                title=f'{topic} — Basic Practice',
                description=(
                    f'{topic} ke 3 basic problems solve karo. '
                    f'Dhyan se har step likho aur answer check karo.'
                ),
                difficulty=self._resolve_difficulty(diff),
            ),
            HomeworkItem(
                title=f'{topic} — Word Problems',
                description=(
                    f'{topic} se related 2 real-life word problems banao aur solve karo. '
                    f'Real life examples se samajhna easy hota hai.'
                ),
                difficulty=self._resolve_difficulty(diff),
            ),
        ]

    @staticmethod
    def _resolve_difficulty(d: str) -> Difficulty:
        try:
            return Difficulty(d)
        except ValueError:
            if d in ('easy', 'beginner', 'basic'):
                return Difficulty.BEGINNER
            if d in ('hard', 'advanced', 'expert'):
                return Difficulty.ADVANCED
            return Difficulty.INTERMEDIATE

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
