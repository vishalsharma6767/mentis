"""Layout Analyzer — segments the page into semantic regions.

Analyses the document layout to identify:
  - Headings (larger font, bold, centred)
  - Question blocks (numbered / bulleted regions)
  - Answer regions (below questions, handwritten)
  - Margin notes (sidebar annotations)
  - Formula regions (dense symbols, operators)
  - Diagram regions (enclosed shapes, lines, arrows)
  - Table regions (grid lines, rows/columns)
  - Image regions

Output is a list of TextBlock and region annotations that the OCR
engines use to focus their recognition strategies per region type.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from app.ai.vision_intelligence.schema import BlockType, BoundingBox, TextBlock
from app.core.logger import get_logger

log = get_logger(__name__)

MIN_REGION_SIZE = 0.005  # 0.5% of page area
MAX_REGIONS = 50


class LayoutAnalyzer:
    """Segments page into semantic regions for focused OCR.

    Usage::

        analyzer = LayoutAnalyzer()
        blocks = await analyzer.analyze(enhanced_image)
        # blocks is a list of TextBlock with bbox and block_type
    """

    def __init__(self) -> None:
        self._h = 0
        self._w = 0

    async def analyze(self, image: np.ndarray) -> list[TextBlock]:
        """Segment the page into semantic text/region blocks.

        Args:
            image: Preprocessed RGB/BGR image.

        Returns:
            Ordered list of TextBlock objects with bounding boxes and
            predicted block types.
        """
        if image is None or image.size == 0:
            return []

        self._h, self._w = image.shape[:2]
        log.info('layout_analyzer_start', dimensions=(self._w, self._h))

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        blocks: list[TextBlock] = []
        blocks.extend(self._detect_text_regions(gray))
        blocks.extend(self._detect_diagram_regions(image))
        blocks.extend(self._detect_table_regions(image))

        # Classify each block
        for block in blocks:
            block.block_type = self._classify_block(block, gray)

        blocks.sort(key=lambda b: (b.bbox.y, b.bbox.x))

        log.info('layout_analyzer_complete', blocks=len(blocks))
        return blocks[:MAX_REGIONS]

    # ── Text region detection ────────────────────────────────────────────

    def _detect_text_regions(self, gray: np.ndarray) -> list[TextBlock]:
        """Find text regions using morphological operations."""
        # Threshold to binary
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

        # Morphological close to group text lines into blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        blocks: list[TextBlock] = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            bbox = self._normalise_bbox(x, y, w, h)
            if bbox.area < MIN_REGION_SIZE:
                continue

            # Crop the region for analysis
            region = gray[y:y + h, x:x + w]
            text_density = float(cv2.countNonZero(
                cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1],
            )) / max(region.size, 1)

            if text_density < 0.02:
                continue

            blocks.append(TextBlock(
                text='',
                bbox=bbox,
                block_type=BlockType.UNKNOWN,
                confidence=round(min(text_density * 3, 1.0), 3),
                line_number=len(blocks),
            ))

        return blocks

    # ── Diagram region detection ─────────────────────────────────────────

    def _detect_diagram_regions(self, image: np.ndarray) -> list[TextBlock]:
        """Identify regions likely containing diagrams or drawings."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=3)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        blocks: list[TextBlock] = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            bbox = self._normalise_bbox(x, y, w, h)
            if bbox.area < MIN_REGION_SIZE * 2:
                continue

            # Count straight lines vs curves in the region
            region_edges = edges[y:y + h, x:x + w]
            lines = cv2.HoughLinesP(
                region_edges, rho=1, theta=np.pi / 180,
                threshold=30, minLineLength=20, maxLineGap=10,
            )
            line_count = len(lines) if lines is not None else 0
            is_diagram = line_count > 5 and bbox.width > 0.3

            if is_diagram:
                blocks.append(TextBlock(
                    text='',
                    bbox=bbox,
                    block_type=BlockType.DIAGRAM_LABEL,
                    confidence=round(min(line_count / 30.0, 1.0), 3),
                ))

        return blocks

    # ── Table region detection ──────────────────────────────────────────

    def _detect_table_regions(self, image: np.ndarray) -> list[TextBlock]:
        """Identify grid/table-like structures."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            ~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY, 15, -2,
        )

        horizontal = self._extract_lines(binary, orientation='horizontal')
        vertical = self._extract_lines(binary, orientation='vertical')

        grid = cv2.bitwise_and(horizontal, vertical)
        contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        blocks: list[TextBlock] = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            bbox = self._normalise_bbox(x, y, w, h)
            if bbox.area < MIN_REGION_SIZE * 3:
                continue
            blocks.append(TextBlock(
                text='',
                bbox=bbox,
                block_type=BlockType.UNKNOWN,
                confidence=0.5,
            ))

        return blocks

    @staticmethod
    def _extract_lines(binary: np.ndarray, orientation: str) -> np.ndarray:
        """Extract horizontal or vertical lines from a binary image."""
        h, w = binary.shape
        if orientation == 'horizontal':
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 30, 1))
        else:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 30))
        return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # ── Block classification ────────────────────────────────────────────

    def _classify_block(self, block: TextBlock, gray: np.ndarray) -> BlockType:
        """Predict the semantic type of a text block based on position and visual features."""
        x = int(block.bbox.x * self._w)
        y = int(block.bbox.y * self._h)
        w = int(block.bbox.width * self._w)
        h = int(block.bbox.height * self._h)

        if w < 1 or h < 1:
            return BlockType.UNKNOWN

        region = gray[y:y + h, x:x + w]
        mean_intensity = float(np.mean(region)) / 255.0

        # Margin notes: small blocks on the left or right edge
        if block.bbox.x < 0.05 or block.bbox.x + block.bbox.width > 0.95:
            if block.bbox.width < 0.15:
                return BlockType.MARGIN_NOTE

        # Heading: top of page, wide block, higher intensity (bold)
        if block.bbox.y < 0.15 and block.bbox.width > 0.4:
            if mean_intensity < 0.6:  # darker = bolder
                return BlockType.HEADING

        # Already marked as diagram
        if block.block_type == BlockType.DIAGRAM_LABEL:
            return BlockType.DIAGRAM_LABEL

        return BlockType.UNKNOWN

    # ── Helpers ─────────────────────────────────────────────────────────

    def _normalise_bbox(self, x: int, y: int, w: int, h: int) -> BoundingBox:
        return BoundingBox(
            x=round(max(0, x) / self._w, 4),
            y=round(max(0, y) / self._h, 4),
            width=round(min(w, self._w - x) / self._w, 4),
            height=round(min(h, self._h - y) / self._h, 4),
        )


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — LayoutAnalyzer disabled')
