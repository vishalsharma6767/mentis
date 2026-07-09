"""Text-to-speech: generates audio from Hinglish text for playback."""

from typing import Optional


class TTSService:
    """Converts teacher's Hinglish text to speech audio."""

    async def synthesize(self, text: str, language: str = 'hi-IN') -> bytes:
        """Return audio bytes for the given text."""
        return b''

    async def get_available_voices(self) -> list[dict]:
        return []
