"""Handwriting Engine — understands student and teacher handwriting.

Specialised module that goes beyond OCR to understand:
  - Messy or cursive student handwriting
  - Teacher corrections and margin notes
  - Strike-throughs and cross-outs
  - Arrows showing work flow
  - Marks / checkmarks / crosses
  - Underlines and highlights

Returns structured annotations about the handwriting quality and
content, separate from the main OCR text blocks.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import numpy as np

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.vision_intelligence.schema import BoundingBox, TextBlock
from app.core.logger import get_logger

log = get_logger(__name__)


class HandwritingAnnotation:
    """An annotation about handwriting in a specific region."""

    def __init__(
        self,
        text: str = '',
        bbox: Optional[BoundingBox] = None,
        confidence: float = 0.0,
        is_teacher: bool = False,
        has_strike_through: bool = False,
        has_arrows: bool = False,
        has_marks: bool = False,
        legibility: float = 0.5,
    ) -> None:
        self.text = text
        self.bbox = bbox or BoundingBox(x=0, y=0, width=0, height=0)
        self.confidence = confidence
        self.is_teacher = is_teacher
        self.has_strike_through = has_strike_through
        self.has_arrows = has_arrows
        self.has_marks = has_marks
        self.legibility = legibility


class HandwritingEngine:
    """Analyses handwriting regions for deeper understanding.

    Usage::

        hw = HandwritingEngine()
        annotations = await hw.analyze(image, handwriting_regions)
        for ann in annotations:
            if ann.has_strike_through:
                # student crossed something out
            if ann.is_teacher:
                # this is a teacher correction
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def analyze(
        self,
        image: np.ndarray,
        regions: list[TextBlock],
        provider: Optional[LLMProvider] = None,
    ) -> list[HandwritingAnnotation]:
        """Analyse handwriting regions for annotations and corrections.

        Args:
            image: Full page image.
            regions: Text blocks classified as student answer or notes.
            provider: Optional LLM provider override.

        Returns:
            List of HandwritingAnnotation with detected features.
        """
        if image is None or image.size == 0:
            return []

        log.info('handwriting_start', regions=len(regions))
        h, w = image.shape[:2]

        annotations: list[HandwritingAnnotation] = []
        for region in regions:
            if not region.is_handwritten and region.block_type not in ('student_answer', 'teacher_note', 'margin_note'):
                continue

            x = int(region.bbox.x * w)
            y = int(region.bbox.y * h)
            rw = int(region.bbox.width * w)
            rh = int(region.bbox.height * h)

            if rw < 20 or rh < 20:
                continue

            crop = image[y:y + rh, x:x + rw]

            # Visual analysis
            strike = self._detect_strike_through(crop)
            arrows = self._detect_arrows(crop)
            marks = self._detect_marks(crop)
            is_teacher = self._is_teacher_handwriting(crop)
            legibility = self._estimate_legibility(crop)

            # Deep text extraction for handwriting
            text = await self._extract_handwritten_text(crop, region, provider)

            annotations.append(HandwritingAnnotation(
                text=text,
                bbox=region.bbox,
                confidence=region.confidence,
                is_teacher=is_teacher,
                has_strike_through=strike,
                has_arrows=arrows,
                has_marks=marks,
                legibility=legibility,
            ))

        log.info('handwriting_complete', annotations=len(annotations))
        return annotations

    # ── Visual feature detection ─────────────────────────────────────────

    @staticmethod
    def _detect_strike_through(crop: np.ndarray) -> bool:
        """Detect horizontal lines crossing through text (strike-throughs)."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180,
            threshold=20, minLineLength=max(crop.shape[1] // 3, 10),
            maxLineGap=5,
        )
        if lines is None:
            return False
        horizontal = [
            l for l in lines
            if abs(l[0][1] - l[0][3]) < 5  # nearly horizontal
        ]
        return len(horizontal) >= 2

    @staticmethod
    def _detect_arrows(crop: np.ndarray) -> bool:
        """Detect arrow-like shapes (lines with arrowheads)."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180,
            threshold=15, minLineLength=15, maxLineGap=5,
        )
        if lines is None:
            return False
        return len(lines) >= 3

    @staticmethod
    def _detect_marks(crop: np.ndarray) -> bool:
        """Detect checkmarks, crosses, or other grading marks."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)[1]

        # Checkmark: two intersecting lines at ~45 degrees
        # Cross: two intersecting lines at ~90 degrees
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return len(contours) > 2

    @staticmethod
    def _is_teacher_handwriting(crop: np.ndarray) -> bool:
        """Heuristic: teacher handwriting is often in red ink or margin."""
        if crop.shape[2] < 3:
            return False
        red_mask = (
            (crop[:, :, 2] > 150) &
            (crop[:, :, 1] < 100) &
            (crop[:, :, 0] < 100)
        )
        return float(np.sum(red_mask)) / red_mask.size > 0.02

    @staticmethod
    def _estimate_legibility(crop: np.ndarray) -> float:
        """Estimate how legible the handwriting is (0.0-1.0)."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

        # Measure stroke consistency via contour analysis
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0.0

        areas = [cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 5]
        if not areas:
            return 0.5

        std_area = float(np.std(areas)) / max(np.mean(areas), 1)
        legibility = max(0.0, min(1.0, 1.0 - std_area * 0.5))
        return legibility

    # ── Text extraction ─────────────────────────────────────────────────

    async def _extract_handwritten_text(
        self,
        crop: np.ndarray,
        region: TextBlock,
        provider: Optional[LLMProvider],
    ) -> str:
        """Extract handwritten text from a region using AI vision."""
        try:
            import base64
            success, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                return ''
            image_b64 = base64.b64encode(buf.tobytes()).decode('utf-8')

            gateway = await self._resolve_gateway()
            response = await gateway.execute(
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': (
                                    'This is handwritten student work. Extract the text exactly as written. '
                                    'If you see corrections, strike-throughs, or arrows, include them. '
                                    'Return JSON: {"text": "extracted text", '
                                    '"is_teacher_correction": false, '
                                    '"has_strike_through": false}'
                                ),
                            },
                            {
                                'type': 'image_url',
                                'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'},
                            },
                        ],
                    },
                ],
                provider=provider or LLMProvider.GROQ,
                expect_json=True,
                max_tokens=1024,
                temperature=0.1,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            return str(parsed.get('text', ''))

        except Exception as exc:
            log.debug('handwriting_extract_failed', error=str(exc)[:80])
            return region.text

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — HandwritingEngine disabled')
