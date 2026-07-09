"""SSML generation: adds pauses, emphasis, prosody for natural Hinglish speech."""

from xml.sax.saxutils import escape


def wrap_ssml(text: str, rate: str = 'slow', pitch: str = 'medium') -> str:
    """Wrap text in SSML tags for natural speech synthesis."""
    escaped = escape(text)
    return f'<speak><prosody rate="{rate}" pitch="{pitch}">{escaped}</prosody></speak>'
