"""Emotion & Tone Analysis Agent.

Detects student affect (confusion, frustration, boredom, engagement,
confidence) from text inputs — their answers, questions, and messages.
Uses lightweight heuristics first, then LLM for nuanced cases.
"""

import re
from typing import Optional

from app.ai.teacher.reasoner import LLMProvider, reason
from app.core.logger import get_logger

log = get_logger(__name__)

# ── Emotion categories ─────────────────────────────────────────────────


class EmotionState:
    CONFUSED = 'confused'
    FRUSTRATED = 'frustrated'
    BORED = 'bored'
    ENGAGED = 'engaged'
    CONFIDENT = 'confident'
    ANXIOUS = 'anxious'
    CURIOUS = 'curious'
    NEUTRAL = 'neutral'


# ── Keyword-based heuristic markers ────────────────────────────────────

_CONFUSION_MARKERS = [
    'samajh nahi', 'nhi aaya', 'kya matlab', 'explain again',
    'confuse', 'confusing', 'difficult', 'hard', 'kya hai ye',
    'don\'t understand', 'not clear', '???', 'what?', 'huh',
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


def _heuristic_emotion(text: str) -> tuple[str, float]:
    """Detect emotion using keyword matching.

    Returns (emotion, confidence).
    """
    lower = text.lower()

    def score(markers: list[str]) -> float:
        matches = sum(1 for m in markers if m in lower)
        if matches == 0:
            return 0.0
        return min(matches / max(len(lower.split()), 1) * 10, 1.0)

    # Prioritise strongest signal
    candidates = [
        (EmotionState.FRUSTRATED, _FRUSTRATION_MARKERS),
        (EmotionState.CONFUSED, _CONFUSION_MARKERS),
        (EmotionState.ANXIOUS, _ANXIETY_MARKERS),
        (EmotionState.CURIOUS, _CURIOSITY_MARKERS),
        (EmotionState.CONFIDENT, _ENGAGEMENT_MARKERS),  # engaged → confident
        (EmotionState.BORED, _BOREDOM_MARKERS),
    ]

    best_emotion = EmotionState.NEUTRAL
    best_score = 0.0
    for emotion, markers in candidates:
        s = score(markers)
        if s > best_score:
            best_score = s
            best_emotion = emotion

    # Check confidence level
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
    provider: str = LLMProvider.GROQ,
) -> tuple[str, float]:
    """Detect student emotion from text.

    Args:
        text: The student's message.
        use_llm: If True, uses LLM for deeper analysis when heuristics are uncertain.
        provider: LLM provider for deep analysis.

    Returns:
        (emotion_label, confidence_score).
    """
    emotion, confidence = _heuristic_emotion(text)

    if use_llm and confidence < 0.4:
        try:
            result = await reason(
                messages=[
                    {
                        'role': 'system',
                        'content': 'You detect student emotion from text. '
                                   'Respond with JSON: {"emotion": "confused|frustrated|bored|engaged|confident|anxious|curious|neutral", "confidence": 0.0-1.0}',
                    },
                    {'role': 'user', 'content': f'Student says: "{text}"\n\nWhat emotion?'},
                ],
                provider=provider,
                expect_json=True,
            )
            emotion = result.get('emotion', emotion)
            confidence = float(result.get('confidence', confidence))
        except Exception:
            pass

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
