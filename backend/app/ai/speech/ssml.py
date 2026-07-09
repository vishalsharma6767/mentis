"""SSML generation — natural Hinglish speech markup.

Converts plain teacher text into SSML with:
  - Automatic pauses between sentences
  - Emphasis on key words (numbers, formulas, important terms)
  - Slow prosody for explanations
  - Natural breathing rhythm

Used by the Speech Agent before sending to the TTS engine.
"""

from __future__ import annotations

import re
from typing import Optional
from xml.sax.saxutils import escape

from app.core.logger import get_logger

log = get_logger(__name__)

PAUSE_SHORT_MS = 300
PAUSE_MEDIUM_MS = 500
PAUSE_LONG_MS = 800

SENTENCE_END = re.compile(r'[.!?]\s+')
COMMA_PAUSE = re.compile(r',\s*')
NUMBERS = re.compile(r'\b\d+(?:\.\d+)?\b')
KEY_TERMS = re.compile(
    r'\b(formula|equation|variable|constant|function|derivative|integral|'
    r'solve|proof|theorem|graph|axis|slope|angle|triangle|circle|'
    r'electron|proton|neutron|force|velocity|acceleration)\b',
    re.IGNORECASE,
)


def wrap_ssml(
    text: str,
    rate: str = 'slow',
    pitch: str = 'medium',
    language: str = 'hi-IN',
) -> str:
    """Wrap Hinglish text in conversational SSML tags.

    Args:
        text: The teacher's explanation in Hinglish.
        rate: Speech rate ('x-slow', 'slow', 'medium', 'fast').
        pitch: Voice pitch ('low', 'medium', 'high').
        language: Language tag.

    Returns:
        SSML string ready for TTS.
    """
    if not text or not text.strip():
        return ''

    escaped = escape(text.strip())

    # Add short pauses after punctuation
    parts = SENTENCE_END.split(escaped)
    ssml_parts: list[str] = []
    for i, part in enumerate(parts):
        if not part.strip():
            continue
        if i < len(parts) - 1:
            part += f'<break time="{PAUSE_MEDIUM_MS}ms"/>'
        ssml_parts.append(part)
    escaped = ''.join(ssml_parts)

    # Add brief pauses after commas
    escaped = COMMA_PAUSE.sub(lambda m: f',<break time="{PAUSE_SHORT_MS}ms"/> ', escaped)

    # Emphasise numbers
    escaped = NUMBERS.sub(r'<emphasis level="moderate">\g<0></emphasis>', escaped)

    # Emphasise key terms
    escaped = KEY_TERMS.sub(r'<emphasis level="strong">\g<0></emphasis>', escaped)

    ssml = (
        f'<speak version="1.1" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{language}">'
        f'<prosody rate="{rate}" pitch="{pitch}">'
        f'{escaped}'
        f'</prosody>'
        f'</speak>'
    )

    return ssml


def estimate_duration(text: str) -> int:
    """Estimate speech duration in milliseconds.

    Rough heuristic: ~150ms per character for Hinglish + pause time.
    """
    if not text:
        return 0
    char_time = len(text) * 150
    pause_count = len(SENTENCE_END.findall(text))
    pause_time = pause_count * PAUSE_MEDIUM_MS
    return char_time + pause_time


def add_emotion_markers(text: str, emotion: str = 'neutral') -> str:
    """Add emotion-appropriate SSML markers.

    Args:
        text: The plain text explanation.
        emotion: One of 'neutral', 'encouraging', 'excited', 'serious', 'gentle'.

    Returns:
        SSML string with emotion-appropriate prosody.
    """
    prosody_map = {
        'encouraging': 'rate="slow" pitch="high" volume="loud"',
        'excited': 'rate="medium" pitch="high" volume="loud"',
        'serious': 'rate="x-slow" pitch="low" volume="medium"',
        'gentle': 'rate="x-slow" pitch="medium" volume="soft"',
        'neutral': 'rate="slow" pitch="medium" volume="medium"',
    }
    prosody = prosody_map.get(emotion, prosody_map['neutral'])
    escaped = escape(text.strip())
    return (
        f'<speak><prosody {prosody}>'
        f'{escaped}'
        f'</prosody></speak>'
    )
