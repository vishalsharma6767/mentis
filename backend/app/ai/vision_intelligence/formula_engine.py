"""Formula Engine — detects and parses mathematical/scientific formulas.

Specialised module that recognises:
  - Mathematics: equations, integrals, derivatives, matrices, fractions
  - Physics: force equations, kinematics, circuit formulas
  - Chemistry: chemical equations, molecular formulas, reactions
  - Statistics: probability, distributions, statistical notation
  - Programming syntax: code snippets, pseudo-code

Converts detected formulas into structured LaTeX and plain-text
representations with per-formula confidence scoring.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import numpy as np

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.vision_intelligence.schema import BoundingBox, Formula, FormulaType
from app.core.logger import get_logger

log = get_logger(__name__)

# Regex patterns for quick heuristic detection
MATH_PATTERN = re.compile(
    r'[=+\-*/^∫∑∏√∞πθαβγΔδ]|\\frac|\\int|\\sum|\\sqrt|x\^|y\^|z\^',
)
CHEM_PATTERN = re.compile(
    r'(?:[A-Z][a-z]?\d*)+→(?:[A-Z][a-z]?\d*)+|'
    r'\bH2O\b|\bCO2\b|\bNaCl\b|\bCH4\b|\bC6H12O6\b',
)
PHYSICS_PATTERN = re.compile(
    r'\b[FmaEPWJ]=(?:ma|mg|mv|½|1/2)|'
    r'\bF=\b|\bE=mc|\bv=u|\bs=ut|\bP=IV|\bV=IR\b',
)


class FormulaEngine:
    """Detects and parses formulas within page regions.

    Usage::

        fe = FormulaEngine()
        formulas = await fe.detect(image, text_blocks)
        # formulas is a list of Formula with LaTeX, plain_text, and
        # formula_type
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def detect(
        self,
        image: np.ndarray,
        text_blocks: list[Any],
        provider: Optional[LLMProvider] = None,
    ) -> list[Formula]:
        """Detect and parse formulas from the page.

        Args:
            image: Full page image.
            text_blocks: Text blocks from layout analyzer/OCR.
            provider: Optional LLM provider override.

        Returns:
            List of Formula objects with LaTeX and plain text.
        """
        if image is None or image.size == 0:
            return []

        log.info('formula_engine_start')
        h, w = image.shape[:2]

        formulas: list[Formula] = []

        # 1. Quick heuristic detection from text blocks
        for block in text_blocks:
            if not block.text:
                continue
            detected = self._heuristic_detect(block.text, block.bbox)
            formulas.extend(detected)

        # 2. AI vision detection for regions not covered by text
        formula_regions = self._detect_formula_regions(image)
        for region_bbox in formula_regions:
            x = int(region_bbox.x * w)
            y = int(region_bbox.y * h)
            rw = int(region_bbox.width * w)
            rh = int(region_bbox.height * h)

            if rw < 20 or rh < 20:
                continue

            crop = image[y:y + rh, x:x + rw]
            parsed = await self._parse_formula_region(crop, provider)
            if parsed:
                parsed.bbox = region_bbox
                formulas.append(parsed)

        # Deduplicate by bounding box overlap
        formulas = self._deduplicate(formulas)

        log.info('formula_engine_complete', formulas=len(formulas))
        return formulas

    # ── Heuristic detection ──────────────────────────────────────────────

    @staticmethod
    def _heuristic_detect(text: str, bbox: BoundingBox) -> list[Formula]:
        """Detect formulas via regex patterns in OCR text."""
        results: list[Formula] = []

        if MATH_PATTERN.search(text):
            ftype = FormulaType.MATHEMATICS
            if PHYSICS_PATTERN.search(text):
                ftype = FormulaType.PHYSICS
            if CHEM_PATTERN.search(text):
                ftype = FormulaType.CHEMISTRY

            results.append(Formula(
                plain_text=text.strip()[:300],
                bbox=bbox,
                formula_type=ftype,
                confidence=0.6,
            ))

        return results

    # ── Visual formula region detection ─────────────────────────────────

    @staticmethod
    def _detect_formula_regions(image: np.ndarray) -> list[BoundingBox]:
        """Find regions with dense mathematical symbols using morphology."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

        h, w = image.shape[:2]

        # Formula regions tend to have dense, small connected components
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 10))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions: list[BoundingBox] = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            bbox = BoundingBox(
                x=round(x / w, 4),
                y=round(y / h, 4),
                width=round(cw / w, 4),
                height=round(ch / h, 4),
            )

            # Filter: formula regions are typically medium size
            if bbox.area < 0.01 or bbox.area > 0.3:
                continue
            if bbox.width / max(bbox.height, 0.001) > 8:  # too wide
                continue

            regions.append(bbox)

        return regions

    # ── AI parsing ───────────────────────────────────────────────────────

    async def _parse_formula_region(
        self,
        crop: np.ndarray,
        provider: Optional[LLMProvider],
    ) -> Optional[Formula]:
        """Use AI vision to parse a formula from a cropped region."""
        try:
            import base64
            success, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                return None
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
                                    'This image shows a mathematical or scientific formula. '
                                    'Extract it as LaTeX and plain text. '
                                    'Classify the type: mathematics, physics, chemistry, '
                                    'statistics, or programming. '
                                    'Return JSON: {"latex": "...", "plain_text": "...", '
                                    '"formula_type": "mathematics|physics|chemistry|statistics|programming", '
                                    '"symbols": ["variable1", "variable2"], '
                                    '"confidence": 0.0-1.0}'
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
            ftype_str = str(parsed.get('formula_type', 'general'))
            ftype = self._resolve_formula_type(ftype_str)

            return Formula(
                latex=str(parsed.get('latex', ''))[:500],
                plain_text=str(parsed.get('plain_text', ''))[:500],
                bbox=BoundingBox(x=0, y=0, width=0, height=0),
                formula_type=ftype,
                confidence=float(parsed.get('confidence', 0.5)),
                symbols=[str(s) for s in (parsed.get('symbols', []) or [])],
                is_handwritten=True,
            )

        except Exception as exc:
            log.debug('formula_parse_failed', error=str(exc)[:80])
            return None

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_formula_type(val: str) -> FormulaType:
        try:
            return FormulaType(val.lower())
        except ValueError:
            return FormulaType.GENERAL

    @staticmethod
    def _deduplicate(formulas: list[Formula]) -> list[Formula]:
        """Remove overlapping formulas, keeping the one with highest confidence."""
        if not formulas:
            return []
        formulas = sorted(formulas, key=lambda f: f.confidence, reverse=True)
        kept: list[Formula] = []
        for f in formulas:
            if not any(f.bbox == k.bbox or _iou(f.bbox, k.bbox) > 0.5 for k in kept):
                kept.append(f)
        return kept

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """Intersection over union between two bounding boxes."""
    x_left = max(a.x, b.x)
    y_top = max(a.y, b.y)
    x_right = min(a.x + a.width, b.x + b.width)
    y_bottom = min(a.y + a.height, b.y + b.height)

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    union = a.area + b.area - intersection
    return intersection / union if union > 0 else 0.0


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — FormulaEngine disabled')
