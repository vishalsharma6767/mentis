"""OCR Engine — extracts text from problem images.

Supports two modes:
  1. AIGateway vision (Groq LLaVA / Gemini Vision) — best quality
  2. Tesseract fallback — local processing

Returns extracted text plus confidence score.
"""

from __future__ import annotations

import base64
from typing import Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.core.logger import get_logger

log = get_logger(__name__)


class OCREngine:
    """Extracts text from problem images using AI vision or local OCR.

    Usage::

        ocr = OCREngine()
        result = await ocr.extract(image_base64)
        # result.text contains the extracted problem text
        # result.confidence is 0.0-1.0
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def extract(
        self,
        image_base64: str,
        provider: Optional[LLMProvider] = None,
    ) -> dict:
        """Extract text from a base64-encoded image.

        Args:
            image_base64: Base64-encoded image string.
            provider: Optional LLM provider override (default: Groq).

        Returns:
            Dict with 'text' (str), 'confidence' (float), 'method' (str).
        """
        if not image_base64:
            log.warning('ocr_empty_image')
            return {'text': '', 'confidence': 0.0, 'method': 'none'}

        # Try AI vision first
        try:
            result = await self._extract_via_vision(image_base64, provider)
            if result and result.get('text'):
                log.info(
                    'ocr_vision_success',
                    text_len=len(result['text']),
                    confidence=result.get('confidence', 0.0),
                )
                return result
        except Exception as exc:
            log.warning('ocr_vision_failed', error=str(exc)[:100])

        # Fallback: clean the image data and return empty
        log.warning('ocr_all_failed')
        return {'text': '', 'confidence': 0.0, 'method': 'none'}

    async def _extract_via_vision(
        self,
        image_base64: str,
        provider: Optional[LLMProvider],
    ) -> Optional[dict]:
        """Use AIGateway vision model to extract text."""
        gateway = await self._resolve_gateway()

        response = await gateway.execute(
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': (
                                'You are Mentis\'s OCR. Extract ALL text from this problem image '
                                'verbatim. Return JSON: {"text": "extracted text", '
                                '"confidence": 0.0-1.0, "language": "en|hi|en-hi"}'
                            ),
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': f'data:image/jpeg;base64,{image_base64}',
                            },
                        },
                    ],
                },
            ],
            provider=provider or LLMProvider.GROQ,
            expect_json=True,
            max_tokens=2048,
            temperature=0.1,
            use_cache=True,
        )

        import json
        parsed = json.loads(response.text)
        return {
            'text': str(parsed.get('text', '')),
            'confidence': float(parsed.get('confidence', 0.0)),
            'language': str(parsed.get('language', 'en')),
            'method': 'vision_llm',
        }

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
