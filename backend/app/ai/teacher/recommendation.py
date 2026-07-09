"""Recommendation Agent — suggests next topics and learning paths.

Analyses the student's knowledge graph, weak areas, and learning pace
to recommend:
  - What topic to study next
  - Which weak concepts need revision
  - Additional resources (videos, practice sets)
  - Learning path optimisations
"""

from __future__ import annotations

import json
from typing import Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.teacher.schemas import HomeworkItem, StudentContext
from app.core.constants import Difficulty
from app.core.logger import get_logger

log = get_logger(__name__)

MAX_RECOMMENDATIONS = 5


class RecommendationItem:
    """A single learning recommendation."""

    def __init__(
        self,
        topic: str,
        reason: str,
        priority: str = 'medium',
        action_type: str = 'study',
        difficulty: str = 'intermediate',
    ) -> None:
        self.topic = topic
        self.reason = reason
        self.priority = priority
        self.action_type = action_type
        self.difficulty = difficulty

    def to_dict(self) -> dict:
        return {
            'topic': self.topic,
            'reason': self.reason,
            'priority': self.priority,
            'action_type': self.action_type,
            'difficulty': self.difficulty,
        }


class RecommendationAgent:
    """Suggests personalised learning paths and next topics.

    Usage::

        rec = RecommendationAgent()
        items = await rec.recommend(
            topic="Linear Equations",
            student=student_ctx,
        )
        # items[0].topic, items[0].reason
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def recommend(
        self,
        topic: str,
        student: StudentContext,
        max_items: int = MAX_RECOMMENDATIONS,
        provider: Optional[LLMProvider] = None,
    ) -> list[RecommendationItem]:
        """Generate learning recommendations for the student.

        Args:
            topic: The current topic being studied.
            student: Current student context.
            max_items: Maximum number of recommendations.
            provider: Optional LLM provider override.

        Returns:
            List of RecommendationItem objects.
        """
        log.info('recommendation_start', topic=topic)

        if not topic or not topic.strip():
            log.warning('recommendation_empty_topic')
            return self._fallback_recommendations(student)

        messages = [
            {
                'role': 'system',
                'content': (
                    'You are an expert Indian teacher recommending personalised '
                    'learning paths. Analyse the student\'s strengths, weaknesses, '
                    'and current topic to suggest what to study next.\n\n'
                    'Return JSON: {"recommendations": [{"topic": "...", "reason": "...", '
                    '"priority": "high|medium|low", "action_type": "study|revise|practice|challenge", '
                    '"difficulty": "beginner|intermediate|advanced"}]}'
                ),
            },
            {'role': 'user', 'content': self._build_prompt(topic, student, max_items)},
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
                items = self._parse_items(parsed.get('recommendations', [parsed]), max_items)

                log.info('recommendation_success', count=len(items))
                return items

            except Exception as exc:
                log.warning('recommendation_attempt_failed', attempt=attempt, error=str(exc)[:120])
                if attempt < 2:
                    continue

        log.warning('recommendation_fallback')
        return self._fallback_recommendations(student)

    def _build_prompt(self, topic: str, student: StudentContext, max_items: int) -> str:
        return json.dumps({
            'current_topic': topic,
            'student_level': student.level.value if hasattr(student.level, 'value') else str(student.level),
            'strong_topics': student.strong_topics[:5],
            'weak_topics': student.weak_topics[:5],
            'recent_topics': student.recent_topics[-5:],
            'revision_due': student.revision_due[:3],
            'max_recommendations': min(max_items, MAX_RECOMMENDATIONS),
            'instructions': (
                f'Based on {topic} and the student\'s profile, recommend what to study next. '
                'Focus on weak areas first, then suggest logical next topics. '
                'Include revision recommendations for topics that are due.'
            ),
        }, indent=2)

    def _parse_items(self, raw: list, max_items: int) -> list[RecommendationItem]:
        items: list[RecommendationItem] = []
        valid_actions = {'study', 'revise', 'practice', 'challenge'}
        for r in raw[:max_items]:
            if not isinstance(r, dict):
                continue
            try:
                action = str(r.get('action_type', 'study')).lower()
                if action not in valid_actions:
                    action = 'study'
                items.append(RecommendationItem(
                    topic=str(r.get('topic', ''))[:200],
                    reason=str(r.get('reason', ''))[:500],
                    priority=str(r.get('priority', 'medium'))[:10],
                    action_type=action,
                    difficulty=str(r.get('difficulty', 'intermediate'))[:20],
                ))
            except Exception:
                continue
        return items[:max_items]

    def _fallback_recommendations(self, student: StudentContext) -> list[RecommendationItem]:
        items: list[RecommendationItem] = []

        for wt in student.weak_topics[:3]:
            items.append(RecommendationItem(
                topic=wt,
                reason=f'{wt} mein aapko aur practice ki zaroorat hai',
                priority='high',
                action_type='revise',
                difficulty=student.level.value if hasattr(student.level, 'value') else 'intermediate',
            ))

        for rt in student.revision_due[:2]:
            items.append(RecommendationItem(
                topic=rt,
                reason=f'{rt} ki revision due hai — phir se dekhte hain',
                priority='medium',
                action_type='revise',
            ))

        if not items:
            items.append(RecommendationItem(
                topic='Review & Practice',
                reason='Agli baar hum naye topics start karenge. Tab tak practice karte raho.',
                priority='low',
                action_type='practice',
            ))

        return items

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
