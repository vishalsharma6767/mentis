"""Diagram Engine — detects and classifies educational diagrams.

Recognises:
  - Triangles (geometry)
  - Circles and arcs (geometry)
  - Coordinate axes (graph grids)
  - Free body diagrams (physics)
  - Electric circuits (physics)
  - Biology diagrams (cells, anatomy, ecosystems)
  - Flowcharts (logic, algorithms)
  - Chemistry structures (molecules, bonds)

Returns structured information about the diagram type, location,
labels, and detected shapes within the diagram boundary.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import numpy as np

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.vision_intelligence.schema import BoundingBox, Diagram, DiagramType
from app.core.logger import get_logger

log = get_logger(__name__)

MIN_DIAGRAM_AREA = 0.02
MAX_DIAGRAM_AREA = 0.8


class DiagramEngine:
    """Detects and classifies educational diagrams on the page.

    Usage::

        de = DiagramEngine()
        diagrams = await de.detect(image)
        # diagrams[0].diagram_type, diagrams[0].shapes_detected
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def detect(
        self,
        image: np.ndarray,
        provider: Optional[LLMProvider] = None,
    ) -> list[Diagram]:
        """Detect and classify all diagrams in the image.

        Args:
            image: Full page image.
            provider: Optional LLM provider override.

        Returns:
            List of detected Diagrams with type and shape information.
        """
        if image is None or image.size == 0:
            return []

        log.info('diagram_engine_start')
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        # Find candidate diagram regions
        candidates = self._find_diagram_candidates(edges)
        log.debug('diagram_candidates', count=len(candidates))

        diagrams: list[Diagram] = []
        for bbox in candidates:
            x = int(bbox.x * w)
            y = int(bbox.y * h)
            rw = int(bbox.width * w)
            rh = int(bbox.height * h)

            crop = image[y:y + rh, x:x + rw]
            crop_edges = edges[y:y + rh, x:x + rw]

            shapes = self._detect_shapes(crop_edges)
            dtype = self._classify_diagram_type(shapes, crop)

            diagram = Diagram(
                diagram_type=dtype,
                bbox=bbox,
                confidence=self._estimate_confidence(shapes, dtype),
                shapes_detected=shapes,
                description=self._generate_description(dtype, shapes),
            )

            # AI vision refinement for complex diagrams
            if diagram.confidence < 0.5:
                refined = await self._refine_with_vision(crop, provider)
                if refined:
                    diagram.diagram_type = refined.diagram_type
                    diagram.confidence = refined.confidence
                    diagram.description = refined.description

            diagrams.append(diagram)

        log.info('diagram_engine_complete', diagrams=len(diagrams))
        return diagrams

    # ── Region detection ────────────────────────────────────────────────

    @staticmethod
    def _find_diagram_candidates(edges: np.ndarray) -> list[BoundingBox]:
        """Find regions with high edge density (potential diagrams)."""
        h, w = edges.shape[:2]

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 10))
        dilated = cv2.dilate(edges, kernel, iterations=3)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: list[BoundingBox] = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            bbox = BoundingBox(
                x=round(x / w, 4),
                y=round(y / h, 4),
                width=round(cw / w, 4),
                height=round(ch / h, 4),
            )

            if bbox.area < MIN_DIAGRAM_AREA or bbox.area > MAX_DIAGRAM_AREA:
                continue

            # Edge density check
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            edge_density = float(cv2.countNonZero(cv2.bitwise_and(edges, edges, mask=mask))) / max(
                cv2.countNonZero(mask), 1,
            )

            if edge_density > 0.05:
                candidates.append(bbox)

        return candidates

    # ── Shape detection ─────────────────────────────────────────────────

    @staticmethod
    def _detect_shapes(edges: np.ndarray) -> list[str]:
        """Detect basic geometric shapes in an edge image."""
        shapes: list[str] = []
        h, w = edges.shape[:2]

        # Detect circles using Hough Circle Transform
        circles = cv2.HoughCircles(
            edges, cv2.HOUGH_GRADIENT, dp=1.2, minDist=20,
            param1=50, param2=30, minRadius=5, maxRadius=min(h, w) // 2,
        )
        if circles is not None:
            shapes.append('circle')

        # Detect lines
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180,
            threshold=30, minLineLength=20, maxLineGap=10,
        )
        if lines is not None:
            # Count horizontal vs vertical vs diagonal
            angles = []
            for l in lines:
                dx = l[0][2] - l[0][0]
                dy = l[0][3] - l[0][1]
                if abs(dx) > 0:
                    angles.append(abs(dy / dx))

            if angles:
                mean_angle = float(np.mean(angles))
                if mean_angle < 0.3:
                    shapes.append('horizontal_line')
                elif mean_angle > 2.0:
                    shapes.append('vertical_line')
                else:
                    shapes.append('diagonal_line')

            if len(lines) > 5:
                shapes.append('multiple_lines')

            if len(lines) > 20:
                shapes.append('dense_lines')

        # Detect arrows (lines converging at one end)
        if lines is not None and len(lines) >= 2:
            endpoints: list[tuple] = []
            for l in lines:
                endpoints.append((l[0][0], l[0][1]))
                endpoints.append((l[0][2], l[0][3]))
            if endpoints:
                clusters = len({(e[0] // 5, e[1] // 5) for e in endpoints})
                if clusters < len(endpoints) * 0.6:
                    shapes.append('arrow_likely')

        if not shapes:
            shapes.append('unknown')

        return list(set(shapes))

    # ── Classification ─────────────────────────────────────────────────

    @staticmethod
    def _classify_diagram_type(shapes: list[str], crop: np.ndarray) -> DiagramType:
        """Classify the diagram type based on detected shapes and content."""
        has_circle = 'circle' in shapes
        has_lines = 'multiple_lines' in shapes or 'dense_lines' in shapes
        has_horizontal = 'horizontal_line' in shapes
        has_vertical = 'vertical_line' in shapes
        has_diagonal = 'diagonal_line' in shapes
        has_arrow = 'arrow_likely' in shapes

        # Coordinate axes: horizontal + vertical + arrows
        if has_horizontal and has_vertical and has_arrow:
            return DiagramType.COORDINATE_AXES

        # Free body diagram: arrows + diagonal lines
        if has_arrow and has_diagonal and not has_circle:
            return DiagramType.FREE_BODY_DIAGRAM

        # Electric circuit: lines + some circles
        if has_lines and has_circle:
            return DiagramType.ELECTRIC_CIRCUIT

        # Triangle: three lines/diagonals
        if has_diagonal and has_lines:
            return DiagramType.TRIANGLE

        # Circle
        if has_circle and not has_lines:
            return DiagramType.CIRCLE

        # Flowchart: arrows + vertical/horizontal lines
        if has_arrow and (has_vertical or has_horizontal):
            return DiagramType.FLOWCHART

        # Default
        return DiagramType.GENERAL

    # ── Confidence ─────────────────────────────────────────────────────

    @staticmethod
    def _estimate_confidence(shapes: list[str], dtype: DiagramType) -> float:
        """Estimate confidence based on shape richness and type match."""
        score = 0.3
        if len(shapes) >= 2:
            score += 0.2
        if len(shapes) >= 4:
            score += 0.2
        if dtype != DiagramType.GENERAL:
            score += 0.2
        return min(score, 1.0)

    # ─── AI refinement ─────────────────────────────────────────────────

    async def _refine_with_vision(
        self,
        crop: np.ndarray,
        provider: Optional[LLMProvider],
    ) -> Optional[Diagram]:
        """Use AI vision to refine diagram classification."""
        try:
            import base64
            success, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
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
                                    'Classify this educational diagram. '
                                    'Types: triangle, circle, coordinate_axes, free_body_diagram, '
                                    'electric_circuit, biology, flowchart, chemistry_structure, '
                                    'bar_chart, pie_chart, line_graph, general. '
                                    'Return JSON: {"diagram_type": "...", '
                                    '"description": "...", '
                                    '"labels": ["label1", "label2"], '
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
                provider=provider,
                expect_json=True,
                max_tokens=512,
                temperature=0.3,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            dtype_str = str(parsed.get('diagram_type', 'general'))
            dtype = self._resolve_diagram_type(dtype_str)

            return Diagram(
                diagram_type=dtype,
                bbox=BoundingBox(x=0, y=0, width=0, height=0),
                confidence=float(parsed.get('confidence', 0.5)),
                labels=[str(l) for l in (parsed.get('labels', []) or [])],
                description=str(parsed.get('description', '')),
            )

        except Exception as exc:
            log.debug('diagram_vision_refine_failed', error=str(exc)[:80])
            return None

    @staticmethod
    def _generate_description(dtype: DiagramType, shapes: list[str]) -> str:
        desc_map = {
            DiagramType.TRIANGLE: 'Triangle with vertices and sides',
            DiagramType.CIRCLE: 'Circle with radius and centre',
            DiagramType.COORDINATE_AXES: 'X-Y coordinate axes with grid',
            DiagramType.FREE_BODY_DIAGRAM: 'Free body diagram with force vectors',
            DiagramType.ELECTRIC_CIRCUIT: 'Electric circuit with components',
            DiagramType.BIOLOGY: 'Biology diagram',
            DiagramType.FLOWCHART: 'Flowchart with decision boxes and arrows',
            DiagramType.CHEMISTRY_STRUCTURE: 'Chemical molecular structure',
            DiagramType.LINE_GRAPH: 'Line graph with data points',
            DiagramType.BAR_CHART: 'Bar chart with bars',
        }
        return desc_map.get(dtype, f'Diagram with {", ".join(shapes[:3])}')

    @staticmethod
    def _resolve_diagram_type(val: str) -> DiagramType:
        try:
            return DiagramType(val.lower())
        except ValueError:
            return DiagramType.GENERAL

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — DiagramEngine disabled')
