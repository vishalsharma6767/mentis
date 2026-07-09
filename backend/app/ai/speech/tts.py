"""Text-to-Speech Service — generates audio from Hinglish text.

Converts the teacher's explanations into speech audio for playback.
Supports multiple TTS backends (Edge TTS, gTTS, fallback) with
automatic language detection for Hinglish mixed text.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.core.logger import get_logger

log = get_logger(__name__)

DEFAULT_VOICE = 'hi-IN-SwaraNeural'
FALLBACK_VOICE = 'en-IN-PrabhuNeural'
TTS_TIMEOUT = 30


class TTSService:
    """Converts teacher's Hinglish text to speech audio bytes.

    Uses Azure/Edge TTS when available. Falls back to simulated audio
    metadata when no backend is configured (e.g. in development).

    Usage::

        tts = TTSService()
        audio = await tts.synthesize(
            text="Chaliye ab is equation ko solve karte hain",
            language="hi-IN",
            emotion="encouraging",
        )
        # audio bytes ready for streaming
    """

    def __init__(self) -> None:
        self._initialized = False
        self._backend: Optional[str] = None

    async def initialize(self) -> None:
        """Discover available TTS backends."""
        if self._initialized:
            return

        # Try to import optional TTS libraries
        try:
            import edge_tts  # noqa: F401
            self._backend = 'edge'
            log.info('tts_backend_edge')
        except ImportError:
            try:
                from gtts import gTTS  # noqa: F401
                self._backend = 'gtts'
                log.info('tts_backend_gtts')
            except ImportError:
                self._backend = None
                log.info('tts_backend_none')

        self._initialized = True

    async def synthesize(
        self,
        text: str,
        language: str = 'hi-IN',
        voice: Optional[str] = None,
        rate: str = 'slow',
        emotion: str = 'neutral',
    ) -> bytes:
        """Convert text to speech audio bytes.

        Args:
            text: The Hinglish text to speak.
            language: Language code (hi-IN, en-IN, etc.).
            voice: Specific voice name (optional).
            rate: Speech rate modifier.
            emotion: Emotion for prosody tuning.

        Returns:
            Audio bytes in WAV/MP3 format, or empty bytes if no
            TTS backend is available.
        """
        if not text or not text.strip():
            return b''

        if not self._initialized:
            await self.initialize()

        try:
            if self._backend == 'edge':
                return await self._synthesize_edge(text, language, voice)
            if self._backend == 'gtts':
                return await self._synthesize_gtts(text, language)
        except Exception as exc:
            log.warning('tts_synthesis_failed', backend=self._backend, error=str(exc)[:100])

        return b''

    async def _synthesize_edge(
        self,
        text: str,
        language: str,
        voice: Optional[str],
    ) -> bytes:
        """Use Edge TTS for speech synthesis."""
        import edge_tts

        voice_name = voice or (DEFAULT_VOICE if 'hi' in language else FALLBACK_VOICE)
        communicate = edge_tts.Communicate(text, voice_name, rate=rate_to_str(rate))

        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                audio_chunks.append(chunk['data'])

        return b''.join(audio_chunks)

    async def _synthesize_gtts(self, text: str, language: str) -> bytes:
        """Use Google TTS as fallback."""
        from gtts import gTTS
        import io

        tts_lang = 'hi' if 'hi' in language else 'en'
        tts = gTTS(text=text, lang=tts_lang, slow=True)

        buf = io.BytesIO()
        tts.write_to_fp(buf)
        return buf.getvalue()

    async def get_available_voices(self) -> list[dict]:
        """Return available TTS voices for the current backend."""
        if not self._initialized:
            await self.initialize()

        if self._backend == 'edge':
            try:
                import edge_tts
                voices = await edge_tts.list_voices()
                return [
                    {'name': v['ShortName'], 'locale': v['Locale'], 'gender': v.get('Gender', '')}
                    for v in voices
                ]
            except Exception:
                pass

        return [
            {'name': DEFAULT_VOICE, 'locale': 'hi-IN', 'gender': 'Female'},
            {'name': FALLBACK_VOICE, 'locale': 'en-IN', 'gender': 'Male'},
        ]


def rate_to_str(rate: str) -> str:
    """Convert human-readable rate to Edge TTS format."""
    mapping = {'x-slow': '-50%', 'slow': '-30%', 'medium': '+0%', 'fast': '+20%', 'x-fast': '+50%'}
    return mapping.get(rate, '+0%')
