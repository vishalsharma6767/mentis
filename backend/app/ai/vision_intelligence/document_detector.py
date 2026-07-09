"""Document Detector — identifies the document type and page boundaries.

Detects whether the image shows a:
  - Notebook page
  - Textbook / book page
  - Worksheet / printed assignment
  - Whiteboard / blackboard
  - Loose paper

Returns the page bounding box (normalised) and the document type,
so downstream modules can adjust their strategies accordingly.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from app.ai.vision_intelligence.schema import BoundingBox, PageRegion, PageType, Point2D
from app.core.logger import get_logger

log = get_logger(__name__)

AREA_THRESHOLD = 0.15
ASPECT_RATIO_NOTEBOOK = 1.3  # ~A4
ASPECT_RATIO_BOOK = 1.5
ASPECT_TOLERANCE = 0.3


class DocumentDetector:
    """Identifies the document type and locates page boundaries.

    Usage::

        detector = DocumentDetector()
        page = await detector.detect(enhanced_image)
        # page.page_type, page.bbox, page.confidence
    """

    def __init__(self) -> None:
        self._debug: dict[str, Any] = {}

    async def detect(self, image: np.ndarray) -> PageRegion:
        """Detect document type and page boundaries.

        Args:
            image: Preprocessed RGB/BGR image.

        Returns:
            PageRegion with type, bounding box, confidence, and corners.
        """
        if image is None or image.size == 0:
            return PageRegion(confidence=0.0)

        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            h, w = image.shape[:2]

            # Edge detection
            edges = self._detect_edges(gray)

            # Find the largest contour (assumed to be the page)
            contour = self._find_largest_contour(edges)

            if contour is not None and len(contour) >= 4:
                bbox, corners = self._contour_to_bbox(contour, w, h)
                page_type = self._classify_page_type(bbox, h / w if w > 0 else 1.0)
                confidence = self._estimate_confidence(contour, edges, w, h)

                return PageRegion(
                    page_type=page_type,
                    bbox=bbox,
                    confidence=round(confidence, 3),
                    corners=corners,
                )

            # Fallback: assume full image
            log.info('document_detector_fallback_full_image')
            return PageRegion(
                page_type=PageType.UNKNOWN,
                bbox=BoundingBox(x=0, y=0, width=1, height=1),
                confidence=0.3,
                corners=[
                    Point2D(x=0, y=0),
                    Point2D(x=1, y=0),
                    Point2D(x=1, y=1),
                    Point2D(x=0, y=1),
                ],
            )

        except Exception as exc:
            log.error('document_detector_failed', error=str(exc)[:150])
            return PageRegion(confidence=0.0)

    # ── Edge detection ───────────────────────────────────────────────────

    @staticmethod
    def _detect_edges(gray: np.ndarray) -> np.ndarray:
        """Apply Canny edge detection with automatic thresholding."""
        median = float(np.median(gray))
        lower = int(max(0, (1.0 - 0.33) * median))
        upper = int(min(255, (1.0 + 0.33) * median))
        edges = cv2.Canny(gray, lower, upper)

        # Dilate to close gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        return cv2.dilate(edges, kernel, iterations=2)

    # ── Contour detection ────────────────────────────────────────────────

    @staticmethod
    def _find_largest_contour(edges: np.ndarray) -> Optional[np.ndarray]:
        """Find the largest rectangular contour."""
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Sort by area, take the largest
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        img_area = edges.shape[0] * edges.shape[1]

        if area < img_area * AREA_THRESHOLD:
            return None

        # Approximate to a polygon
        peri = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.02 * peri, True)

        if len(approx) < 4:
            return None

        return approx

    # ── Bounding box ─────────────────────────────────────────────────────

    @staticmethod
    def _contour_to_bbox(
        contour: np.ndarray,
        img_w: int,
        img_h: int,
    ) -> tuple[BoundingBox, list[Point2D]]:
        """Convert a contour to a normalised bounding box + corner points."""
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        box = np.int32(box)

        x_coords = [p[0][0] if len(p.shape) > 1 else p[0] for p in box]
        y_coords = [p[0][1] if len(p.shape) > 1 else p[1] for p in box]

        x_min, x_max = max(0, min(x_coords)), min(img_w, max(x_coords))
        y_min, y_max = max(0, min(y_coords)), min(img_h, max(y_coords))

        corners = [
            Point2D(x=round(p[0][0] / img_w, 4), y=round(p[0][1] / img_h, 4))
            if len(p.shape) > 1
            else Point2D(x=round(p[0] / img_w, 4), y=round(p[1] / img_h, 4))
            for p in box
        ]

        bbox = BoundingBox(
            x=round(x_min / img_w, 4),
            y=round(y_min / img_h, 4),
            width=round((x_max - x_min) / img_w, 4),
            height=round((y_max - y_min) / img_h, 4),
        )

        return bbox, corners

    # ── Classification ───────────────────────────────────────────────────

    @staticmethod
    def _classify_page_type(bbox: BoundingBox, aspect_ratio: float) -> PageType:
        """Classify the page type based on aspect ratio and coverage."""
        coverage = bbox.area

        # Full-page coverage → likely a document
        if coverage > 0.85:
            if abs(aspect_ratio - ASPECT_RATIO_NOTEBOOK) < ASPECT_TOLERANCE:
                return PageType.NOTEBOOK
            if abs(aspect_ratio - ASPECT_RATIO_BOOK) < ASPECT_TOLERANCE:
                return PageType.BOOK
            return PageType.WORKSHEET

        # Partial coverage → could be whiteboard or loose paper
        if coverage > 0.5:
            if aspect_ratio > 1.6:
                return PageType.WHITEBOARD
            return PageType.LOOSE_PAPER

        # Small coverage → unknown
        if aspect_ratio > 1.8:
            return PageType.WHITEBOARD
        return PageType.UNKNOWN

    @staticmethod
    def _estimate_confidence(
        contour: np.ndarray,
        edges: np.ndarray,
        img_w: int,
        img_h: int,
    ) -> float:
        """Estimate how confident we are in the detected page region."""
        contour_area = cv2.contourArea(contour)
        img_area = img_w * img_h
        coverage = contour_area / img_area

        # Edge density within contour
        mask = np.zeros((img_h, img_w), dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        edge_density = float(cv2.countNonZero(cv2.bitwise_and(edges, mask))) / max(
            cv2.countNonZero(mask), 1,
        )

        score = coverage * 0.5 + min(edge_density * 2, 1.0) * 0.5
        return min(max(score, 0.0), 1.0)


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — DocumentDetector disabled')
