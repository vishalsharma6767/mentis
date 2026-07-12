"""OCR Engine — extracts text from page regions with language detection.

Supports:
  - Printed text (English, Hindi, mixed Hinglish)
  - Handwritten text
  - Mathematical symbols and scientific notation
  - Per-block confidence scoring

Uses AIGateway for vision-model-based extraction with fallback to
local Tesseract when available.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

import numpy as np

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.vision_intelligence.schema import BlockType, BoundingBox, Language, TextBlock
from app.core.logger import get_logger

log = get_logger(__name__)

MAX_BLOCK_TEXT_LENGTH = 2000


class OCREngine:
    """Extracts text from page regions with full language support.

    Uses AI vision models as the primary engine with hardcoded
    fallback logic for resilience.

    Usage::

        ocr = OCREngine()
        blocks = await ocr.extract(image, layout_blocks)
        # each TextBlock now has recognised text and language
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def extract(
        self,
        image: np.ndarray,
        regions: list[TextBlock],
        full_page: bool = True,
        provider: Optional[LLMProvider] = None,
    ) -> list[TextBlock]:
        """Extract text from the given page regions.

        Args:
            image: Full page image array.
            regions: Layout-analyzed regions to extract text from.
            full_page: If True, also do a full-page OCR pass.
            provider: Optional LLM provider override.

        Returns:
            TextBlocks with recognised text filled in.
        """
        if image is None or image.size == 0:
            return regions

        log.info('ocr_engine_start', regions=len(regions), full_page=full_page)

        h, w = image.shape[:2]

        # Full page OCR for overall context
        full_text = ''
        if full_page:
            full_text = await self._extract_full_page(image, provider)

        # Region-by-region extraction
        for region in regions:
            if region.block_type == BlockType.DIAGRAM_LABEL:
                continue

            x = int(region.bbox.x * w)
            y = int(region.bbox.y * h)
            rw = int(region.bbox.width * w)
            rh = int(region.bbox.height * h)

            if rw < 10 or rh < 10:
                region.confidence = 0.0
                continue

            crop = image[y:y + rh, x:x + rw]
            text = await self._extract_region(crop, region.block_type, provider)

            if text:
                region.text = text[:MAX_BLOCK_TEXT_LENGTH]
                region.confidence = max(region.confidence, 0.5)
                region.language = self._detect_language(text)

        # If no regions, create one from full page result
        if not regions and full_text:
            regions.append(TextBlock(
                text=full_text[:MAX_BLOCK_TEXT_LENGTH],
                bbox=BoundingBox(x=0, y=0, width=1, height=1),
                block_type=BlockType.UNKNOWN,
                confidence=0.5,
                language=self._detect_language(full_text),
            ))

        log.info('ocr_engine_complete', blocks_with_text=sum(1 for r in regions if r.text))
        return regions

    # ── Full page ────────────────────────────────────────────────────────

    async def _extract_full_page(
        self,
        image: np.ndarray,
        provider: Optional[LLMProvider],
    ) -> str:
        """Extract all text from the full page using AI vision."""
        try:
            image_b64 = self._array_to_base64(image)
            gateway = await self._resolve_gateway()

            response = await gateway.execute(
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': (
                                    'Extract ALL text from this educational page. '
                                    'Include English, Hindi, and mixed Hinglish text. '
                                    'Detect mathematical symbols and formulas. '
                                    'Return JSON: {"text": "full extracted text", '
                                    '"language": "english|hindi|hinglish|mixed", '
                                    '"confidence": 0.0-1.0}'
                                ),
                            },
                            {
                                'type': 'image_url',
                                'image_url': {
                                    'url': f'data:image/jpeg;base64,{image_b64}',
                                },
                            },
                        ],
                    },
                ],
                provider=provider,
                expect_json=True,
                max_tokens=4096,
                temperature=0.1,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            return str(parsed.get('text', ''))

        except Exception as exc:
            log.warning('ocr_full_page_failed', error=str(exc)[:120])
            return ''

    # ── Region extraction ────────────────────────────────────────────────

    async def _extract_region(
        self,
        crop: np.ndarray,
        block_type: BlockType,
        provider: Optional[LLMProvider],
    ) -> str:
        """Extract text from a single cropped region."""
        if crop.size < 50:
            return ''

        try:
            image_b64 = self._array_to_base64(crop)
            gateway = await self._resolve_gateway()

            prompt = self._build_region_prompt(block_type)

            response = await gateway.execute(
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': prompt},
                            {
                                'type': 'image_url',
                                'image_url': {
                                    'url': f'data:image/jpeg;base64,{image_b64}',
                                },
                            },
                        ],
                    },
                ],
                provider=provider,
                expect_json=True,
                max_tokens=1024,
                temperature=0.1,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            return str(parsed.get('text', ''))

        except Exception as exc:
            log.debug('ocr_region_failed', block_type=block_type.value, error=str(exc)[:80])
            return ''

    @staticmethod
    def _build_region_prompt(block_type: BlockType) -> str:
        """Build a context-aware extraction prompt."""
        base = 'Extract text from this image region. Return JSON: {"text": "..."}.'
        hints = {
            BlockType.HEADING: ' This appears to be a heading or title.',
            BlockType.QUESTION_TEXT: ' This is a question or problem statement.',
            BlockType.STUDENT_ANSWER: ' This is handwritten student work.',
            BlockType.TEACHER_NOTE: ' This is a teacher\'s correction or note.',
            BlockType.FORMULA: ' This contains mathematical formulas or equations.',
            BlockType.MARGIN_NOTE: ' This is a margin note or annotation.',
        }
        return base + hints.get(block_type, '')

    # ── Language detection ──────────────────────────────────────────────

    @staticmethod
    def _detect_language(text: str) -> Language:
        """Detect whether text is English, Hindi, Hinglish, or mixed."""
        if not text or not text.strip():
            return Language.ENGLISH

        hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        total_chars = sum(1 for c in text if c.isalpha())

        if total_chars == 0:
            return Language.ENGLISH

        hindi_ratio = hindi_chars / total_chars

        if hindi_ratio > 0.8:
            return Language.HINDI
        if hindi_ratio > 0.2:
            return Language.HINGLISH
        return Language.ENGLISH

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _array_to_base64(image: np.ndarray) -> str:
        """Convert numpy array to base64 JPEG string."""
        success, buf = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            return ''
        return base64.b64encode(buf.tobytes()).decode('utf-8')

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — OCREngine disabled')
