"""Graph Engine — understands plotted graphs and charts.

Analyses graph regions to extract:
  - X and Y axis labels and scale
  - Data points and curves
  - Trend direction and pattern
  - Minimum/maximum values
  - Linear vs non-linear relationships

Supports line graphs, bar charts, scatter plots, and
coordinate-plane-based geometry drawings.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import numpy as np

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.vision_intelligence.schema import BoundingBox, Graph, Point2D
from app.core.logger import get_logger

log = get_logger(__name__)


class GraphEngine:
    """Analyse graph regions and extract structured data.

    Usage::

        ge = GraphEngine()
        graphs = await ge.analyze(image, graph_regions)
        # graphs[0].x_label, graphs[0].points, graphs[0].trend_description
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def analyze(
        self,
        image: np.ndarray,
        graph_regions: list[BoundingBox],
        provider: Optional[LLMProvider] = None,
    ) -> list[Graph]:
        """Analyse graph regions and extract structured information.

        Args:
            image: Full page image.
            graph_regions: Bounding boxes of graph-like regions.
            provider: Optional LLM provider override.

        Returns:
            List of Graph objects with axes, points, and trend info.
        """
        if image is None or image.size == 0:
            return []

        log.info('graph_engine_start', regions=len(graph_regions))
        h, w = image.shape[:2]

        graphs: list[Graph] = []
        for region in graph_regions:
            x = int(region.x * w)
            y = int(region.y * h)
            rw = int(region.width * w)
            rh = int(region.height * h)

            if rw < 30 or rh < 30:
                continue

            crop = image[y:y + rh, x:x + rw]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            detected = self._detect_axes_and_scale(gray)
            if detected['has_axes']:
                graph = Graph(
                    bbox=region,
                    confidence=detected['confidence'],
                    x_label=detected.get('x_label', ''),
                    y_label=detected.get('y_label', ''),
                    x_min=detected.get('x_min'),
                    x_max=detected.get('x_max'),
                    y_min=detected.get('y_min'),
                    y_max=detected.get('y_max'),
                    points=detected.get('points', []),
                    trend_description=detected.get('trend', ''),
                    is_linear=detected.get('is_linear'),
                )

                # AI refinement for complex graphs
                if graph.confidence < 0.6:
                    refined = await self._refine_with_vision(crop, provider)
                    if refined:
                        graph.x_label = refined.x_label or graph.x_label
                        graph.y_label = refined.y_label or graph.y_label
                        graph.trend_description = refined.trend_description or graph.trend_description
                        graph.is_linear = refined.is_linear
                        if refined.confidence > graph.confidence:
                            graph.confidence = refined.confidence

                graphs.append(graph)

            else:
                # Fallback: use AI vision for graphs without clear axes
                refined = await self._refine_with_vision(crop, provider)
                if refined:
                    refined.bbox = region
                    graphs.append(refined)

        log.info('graph_engine_complete', graphs=len(graphs))
        return graphs

    # ── Axes detection ──────────────────────────────────────────────────

    @staticmethod
    def _detect_axes_and_scale(gray: np.ndarray) -> dict[str, Any]:
        """Detect coordinate axes and estimate scale."""
        h, w = gray.shape[:2]
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180,
            threshold=int(min(h, w) * 0.1),
            minLineLength=int(min(h, w) * 0.2),
            maxLineGap=10,
        )

        result: dict[str, Any] = {
            'has_axes': False,
            'confidence': 0.0,
            'x_label': '',
            'y_label': '',
            'points': [],
            'trend': '',
        }

        if lines is None:
            return result

        # Separate horizontal and vertical lines
        horizontal = []
        vertical = []
        for l in lines:
            x1, y1, x2, y2 = l[0]
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            if dx > dy and dy < dx * 0.1:
                horizontal.append((x1, y1, x2, y2))
            elif dy > dx and dx < dy * 0.1:
                vertical.append((x1, y1, x2, y2))

        if len(horizontal) >= 1 and len(vertical) >= 1:
            result['has_axes'] = True
            result['confidence'] = min(0.5 + len(lines) * 0.02, 0.9)

            # Estimate scale from tick marks
            h_median = int(np.median([abs(l[0] - l[2]) for l in horizontal])) if horizontal else w
            v_median = int(np.median([abs(l[1] - l[3]) for l in vertical])) if vertical else h

            result['x_min'] = 0
            result['x_max'] = round(h_median / 10) if h_median > 0 else 10
            result['y_min'] = 0
            result['y_max'] = round(v_median / 10) if v_median > 0 else 10

        # Detect data points (small blobs near axes)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 3 < area < 50:  # typical data point size
                M = cv2.moments(cnt)
                if M['m00'] > 0:
                    cx = M['m10'] / M['m00']
                    cy = M['m01'] / M['m00']
                    points.append(Point2D(x=round(cx / w, 4), y=round(cy / h, 4)))

        if points and result['has_axes']:
            result['points'] = points[:50]

            # Simple trend detection
            if len(points) >= 2:
                x_vals = [p.x for p in points]
                y_vals = [p.y for p in points]
                if max(x_vals) - min(x_vals) > 0:
                    slope = (y_vals[-1] - y_vals[0]) / (x_vals[-1] - x_vals[0])
                    if abs(slope) < 0.1:
                        result['trend'] = 'Nearly constant / flat'
                        result['is_linear'] = True
                    elif slope > 0:
                        result['trend'] = f'Increasing (slope={slope:.2f})'
                        result['is_linear'] = True
                    else:
                        result['trend'] = f'Decreasing (slope={slope:.2f})'
                        result['is_linear'] = True

        return result

    # ── AI refinement ──────────────────────────────────────────────────

    async def _refine_with_vision(
        self,
        crop: np.ndarray,
        provider: Optional[LLMProvider],
    ) -> Optional[Graph]:
        """Use AI vision for detailed graph analysis."""
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
                                    'Analyse this graph or chart. Extract: '
                                    'X-axis label, Y-axis label, title, '
                                    'minimum and maximum values, '
                                    'whether the trend is increasing/decreasing/constant, '
                                    'and if it appears linear or non-linear. '
                                    'Return JSON: {"x_label": "...", "y_label": "...", '
                                    '"title": "...", '
                                    '"x_min": number, "x_max": number, '
                                    '"y_min": number, "y_max": number, '
                                    '"trend_description": "...", '
                                    '"is_linear": true/false, '
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
                max_tokens=1024,
                temperature=0.1,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            return Graph(
                bbox=BoundingBox(x=0, y=0, width=0, height=0),
                confidence=float(parsed.get('confidence', 0.5)),
                x_label=str(parsed.get('x_label', '')),
                y_label=str(parsed.get('y_label', '')),
                title=str(parsed.get('title', '')),
                x_min=parsed.get('x_min'),
                x_max=parsed.get('x_max'),
                y_min=parsed.get('y_min'),
                y_max=parsed.get('y_max'),
                trend_description=str(parsed.get('trend_description', '')),
                is_linear=parsed.get('is_linear'),
            )

        except Exception as exc:
            log.debug('graph_vision_refine_failed', error=str(exc)[:80])
            return None

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — GraphEngine disabled')
