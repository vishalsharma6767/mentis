"""Vision Intelligence Pipeline — orchestrates all vision modules.

The pipeline runs every stage of the Vision Intelligence Engine in
an optimised order, parallelising independent modules. It produces
a single EducationalScene that the Teacher Orchestrator consumes.

Pipeline stages order:
  1. Image Preprocessor (all images go through this)
  2. Document Detector (parallel after preprocessor)
  3. Layout Analyzer (parallel with detector)
  4. OCR Engine (after layout)
  5. Handwriting Engine (parallel with OCR)
  6. Formula Engine (after OCR)
  7. Diagram Engine (after layout)
  8. Graph Engine (after diagram)
  9. Question Extractor (after OCR + handwriting)
  10. Topic Classifier (after question extractor)
  11. Scene Builder (final assembly)
  12. Vision Validator (built into Scene Builder)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import numpy as np

from app.ai.gateway import LLMProvider
from app.ai.vision_intelligence.diagram_engine import DiagramEngine
from app.ai.vision_intelligence.document_detector import DocumentDetector
from app.ai.vision_intelligence.formula_engine import FormulaEngine
from app.ai.vision_intelligence.graph_engine import GraphEngine
from app.ai.vision_intelligence.handwriting_engine import HandwritingEngine
from app.ai.vision_intelligence.image_preprocessor import ImagePreprocessor
from app.ai.vision_intelligence.layout_analyzer import LayoutAnalyzer
from app.ai.vision_intelligence.ocr_engine import OCREngine
from app.ai.vision_intelligence.question_extractor import QuestionExtractor
from app.ai.vision_intelligence.scene_builder import SceneBuilder
from app.ai.vision_intelligence.schema import (
    Diagram,
    EducationalScene,
    Formula,
    Graph,
    TextBlock,
)
from app.ai.vision_intelligence.topic_classifier import TopicClassifier
from app.core.logger import get_logger

log = get_logger(__name__)


class VisionPipeline:
    """End-to-end vision intelligence pipeline.

    Takes a raw camera image and returns a complete EducationalScene.
    This is the ONLY entry point the rest of the system should use.

    Usage::

        pipeline = VisionPipeline()
        scene = await pipeline.run(image_array)
        if scene.confidence.is_reliable():
            teacher.receive(scene)
        else:
            await request_recapture(scene)

    The pipeline never returns raw OCR text — only EducationalScene.
    """

    def __init__(self) -> None:
        self._preprocessor = ImagePreprocessor()
        self._document_detector = DocumentDetector()
        self._layout_analyzer = LayoutAnalyzer()
        self._ocr_engine = OCREngine()
        self._handwriting_engine = HandwritingEngine()
        self._formula_engine = FormulaEngine()
        self._diagram_engine = DiagramEngine()
        self._graph_engine = GraphEngine()
        self._question_extractor = QuestionExtractor()
        self._topic_classifier = TopicClassifier()
        self._scene_builder = SceneBuilder()
        self._provider: Optional[LLMProvider] = None

    # ── Public API ───────────────────────────────────────────────────────

    async def run(
        self,
        image: np.ndarray,
        provider: Optional[LLMProvider] = None,
    ) -> EducationalScene:
        """Run the full vision pipeline on a raw camera image.

        Args:
            image: Raw camera frame as numpy array (H, W, C).
            provider: Optional LLM provider override.

        Returns:
            Complete EducationalScene with all detected information.
            The teacher never receives raw text.
        """
        t0 = time.monotonic()
        log.info('vision_pipeline_start', shape=image.shape)

        self._provider = provider

        # ── Stage 1-3: Parallel preprocessor + detector ─────────────────
        preprocessed, page = await asyncio.gather(
            self._preprocessor.process(image),
            self._document_detector.detect(image),
        )

        enhanced = preprocessed.get('image', image)
        quality = preprocessed.get('quality')

        if not quality or not quality.is_acceptable:
            log.warning('vision_pipeline_image_rejected', reason=quality.rejection_reason if quality else 'unknown')
            return await self._build_fallback_scene(image, preprocessed, page)

        # ── Stage 4: Layout analysis ─────────────────────────────────────
        layout_blocks = await self._layout_analyzer.analyze(enhanced)

        # ── Stage 5-6: Parallel OCR + diagram detection ─────────────────
        ocr_blocks, diagrams = await asyncio.gather(
            self._ocr_engine.extract(enhanced, layout_blocks, provider=provider),
            self._diagram_engine.detect(enhanced, provider=provider),
        )

        # ── Stage 7: Handwriting analysis ────────────────────────────────
        handwriting_regions = [b for b in ocr_blocks if b.is_handwritten or b.block_type in ('student_answer', 'margin_note')]
        handwriting_annotations = await self._handwriting_engine.analyze(
            enhanced, handwriting_regions, provider=provider,
        )

        # ── Stage 8: Formula + Graph detection (parallel) ───────────────
        formulas, graphs = await asyncio.gather(
            self._formula_engine.detect(enhanced, ocr_blocks, provider=provider),
            self._detect_graphs(enhanced, diagrams),
        )

        # ── Stage 9: Question extraction ─────────────────────────────────
        questions = await self._question_extractor.extract(
            ocr_blocks, enhanced, provider=provider,
        )

        # Merge handwriting text into question answers
        for ann in handwriting_annotations:
            if ann.text and questions:
                for q in questions:
                    if self._bbox_overlaps(ann.bbox, q.bbox):
                        if ann.is_teacher:
                            q.teacher_notes = ann.text
                        else:
                            if not q.student_answer:
                                q.student_answer = ann.text

        # ── Stage 10: Classification ─────────────────────────────────────
        full_text = '\n'.join(
            b.text for b in ocr_blocks if b.text
        )
        formula_dicts = [{'latex': f.latex, 'plain_text': f.plain_text} for f in formulas]
        diagram_dicts = [{'diagram_type': d.diagram_type.value, 'description': d.description} for d in diagrams]

        classification = await self._topic_classifier.classify(
            full_text=full_text,
            formulas=formula_dicts,
            diagrams=diagram_dicts,
            provider=provider,
        )

        # ── Stage 11: Scene assembly ────────────────────────────────────
        scene = await self._scene_builder.build(
            image=enhanced,
            preprocessed_result=preprocessed,
            page=page,
            layout=layout_blocks,
            ocr=ocr_blocks,
            handwriting=handwriting_annotations,
            formulas=formulas,
            diagrams=diagrams,
            graphs=graphs,
            questions=questions,
            classification=classification,
        )

        elapsed = time.monotonic() - t0
        scene.metadata.processing_time_ms = int(elapsed * 1000)

        log.info(
            'vision_pipeline_complete',
            elapsed_ms=int(elapsed * 1000),
            questions=len(scene.questions),
            formulas=len(scene.formulas),
            diagrams=len(scene.diagrams),
            confidence=round(scene.confidence.overall, 3),
        )
        return scene

    # ── Graph detection ──────────────────────────────────────────────────

    async def _detect_graphs(
        self,
        image: np.ndarray,
        diagrams: list[Diagram],
    ) -> list[Graph]:
        """Run graph analysis on coordinate-axes diagrams."""
        graph_regions = [
            d.bbox for d in diagrams
            if d.diagram_type.value in ('coordinate_axes', 'line_graph', 'bar_chart')
        ]
        if not graph_regions:
            return []
        return await self._graph_engine.analyze(image, graph_regions, provider=self._provider)

    # ── Fallback ─────────────────────────────────────────────────────────

    async def _build_fallback_scene(
        self,
        image: np.ndarray,
        preprocessed: dict[str, Any],
        page: Any,
    ) -> EducationalScene:
        """Build a minimal scene when the image is rejected."""
        quality = preprocessed.get('quality')
        return EducationalScene(
            image_quality=quality,
            page=page,
            metadata=SceneMetadata(processing_time_ms=preprocessed.get('processing_time_ms', 0)),
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _bbox_overlaps(a: Any, b: Any) -> bool:
        """Check if two bounding boxes overlap."""
        if not a or not b:
            return False
        try:
            return (
                a.x < b.x + b.width and
                a.x + a.width > b.x and
                a.y < b.y + b.height and
                a.y + a.height > b.y
            )
        except (AttributeError, TypeError):
            return False


# Import for the fallback
from app.ai.vision_intelligence.schema import SceneMetadata  # noqa: E402
