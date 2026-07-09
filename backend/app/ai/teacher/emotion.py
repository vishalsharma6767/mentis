"""Emotion & Tone Analysis Agent.

Detects student affect (confusion, frustration, boredom, engagement,
confidence) from text inputs — their answers, questions, and messages.
Uses lightweight heuristics first, then AIGateway for nuanced cases.
"""

from __future__ import annotations

import re
from typing import Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.core.logger import get_logger

log = get_logger(__name__)


class EmotionState:
    CONFUSED = 'confused'
    FRUSTRATED = 'frustrated'
    BORED = 'bored'
    ENGAGED = 'engaged'
    CONFIDENT = 'confident'
    ANXIOUS = 'anxious'
    CURIOUS = 'curious'
    NEUTRAL = 'neutral'


_CONFUSION_MARKERS = [
    'samajh nahi', 'nhi aaya', 'kya matlab', 'explain again',
    'confuse', 'confusing', 'difficult', 'hard', 'kya hai ye',
    "don't understand", 'not clear', '???', 'what?', 'huh',
]

_FRUSTRATION_MARKERS = [
    'frustrating', 'still wrong', 'nhi ho raha', 'too hard',
    'ye kya hai', 'useless', 'waste', 'not helping',
    'frustrate', 'annoying', 'stop',
]

_BOREDOM_MARKERS = [
    'boring', 'too easy', 'simple hai', 'basic', 'already know',
    'ye to pata hai', 'bore', 'same thing', 'next',
]

_ENGAGEMENT_MARKERS = [
    'interesting', 'wow', 'acha', 'maza aa raha', 'cool',
    'understood', 'samajh aaya', 'got it', 'yes', 'correct',
    'exactly', 'right', 'awesome', 'nice',
]

_CONFIDENCE_MARKERS = {
    'high': ['sure', 'certain', 'definitely', 'pakka', 'bilkul', 'yes sir', 'easy'],
    'low': ['maybe', 'not sure', 'shayad', 'pata nahi', 'guess', 'try', 'think so', 'uncertain'],
}

_ANXIETY_MARKERS = [
    'nervous', 'worried', 'anxious', 'exam', 'test', 'fail',
    'tension', 'pressure', 'scared', 'afraid',
]

_CURIOSITY_MARKERS = [
    'why', 'how', 'what if', 'kyu', 'kaise', 'possible',
    'curious', 'wonder', 'interesting thought',
]

EMOTION_LABELS = '|'.join([
    EmotionState.CONFUSED, EmotionState.FRUSTRATED, EmotionState.BORED,
    EmotionState.ENGAGED, EmotionState.CONFIDENT, EmotionState.ANXIOUS,
    EmotionState.CURIOUS, EmotionState.NEUTRAL,
])


def _heuristic_emotion(text: str) -> tuple[str, float]:
    """Detect emotion using keyword matching.

    Returns (emotion_label, confidence) where confidence is 0.0-1.0.
    """
    lower = text.lower()

    def score(markers: list[str]) -> float:
        matches = sum(1 for m in markers if m in lower)
        if matches == 0:
            return 0.0
        return min(matches / max(len(lower.split()), 1) * 10, 1.0)

    candidates = [
        (EmotionState.FRUSTRATED, _FRUSTRATION_MARKERS),
        (EmotionState.CONFUSED, _CONFUSION_MARKERS),
        (EmotionState.ANXIOUS, _ANXIETY_MARKERS),
        (EmotionState.CURIOUS, _CURIOSITY_MARKERS),
        (EmotionState.CONFIDENT, _ENGAGEMENT_MARKERS),
        (EmotionState.BORED, _BOREDOM_MARKERS),
    ]

    best_emotion = EmotionState.NEUTRAL
    best_score = 0.0
    for emotion, markers in candidates:
        s = score(markers)
        if s > best_score:
            best_score = s
            best_emotion = emotion

    high_conf = sum(1 for m in _CONFIDENCE_MARKERS['high'] if m in lower)
    low_conf = sum(1 for m in _CONFIDENCE_MARKERS['low'] if m in lower)
    if high_conf > low_conf and best_score < 0.3:
        return EmotionState.CONFIDENT, max(0.5, best_score)
    if low_conf > high_conf and best_score < 0.3:
        return EmotionState.ANXIOUS, max(0.4, best_score)

    return best_emotion, best_score if best_score > 0.2 else (EmotionState.NEUTRAL, 0.0)


async def detect_emotion(
    text: str,
    use_llm: bool = False,
    provider: Optional[LLMProvider] = None,
) -> tuple[str, float]:
    """Detect student emotion from text.

    Uses fast keyword heuristics first. Falls back to AIGateway for
    deeper analysis when heuristics are uncertain.

    Args:
        text: The student's message.
        use_llm: If True, uses LLM for deep analysis when heuristics
                 are uncertain (confidence < 0.4).
        provider: Optional LLM provider override.

    Returns:
        (emotion_label, confidence_score).
    """
    if not text or not text.strip():
        return EmotionState.NEUTRAL, 0.0

    emotion, confidence = _heuristic_emotion(text)

    if use_llm and confidence < 0.4:
        try:
            gateway = await AIGateway.get_instance()
            result = await gateway.execute(
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            f'You detect student emotion from text. '
                            f'Respond with JSON: {{"emotion": "{EMOTION_LABELS}", '
                            f'"confidence": 0.0-1.0}}'
                        ),
                    },
                    {'role': 'user', 'content': f'Student says: "{text[:500]}"\n\nWhat emotion?'},
                ],
                provider=provider,
                expect_json=True,
                max_tokens=128,
                temperature=0.3,
            )
            import json
            parsed = json.loads(result.text)
            emotion = str(parsed.get('emotion', emotion))
            confidence = float(parsed.get('confidence', confidence))
        except Exception:
            log.debug('emotion_llm_fallback_skipped', heuristics_emotion=emotion)

    return emotion, confidence


def urgency_level(emotion: str) -> int:
    """Determine intervention urgency (0=low, 3=high)."""
    return {
        EmotionState.FRUSTRATED: 3,
        EmotionState.CONFUSED: 2,
        EmotionState.ANXIOUS: 2,
        EmotionState.BORED: 1,
        EmotionState.NEUTRAL: 0,
        EmotionState.ENGAGED: 0,
        EmotionState.CONFIDENT: 0,
        EmotionState.CURIOUS: 0,
    }.get(emotion, 0)
