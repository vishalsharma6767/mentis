"""Scene Builder — assembles all module outputs into EducationalScene.

This is the final stage of the Vision Intelligence Engine. It takes
outputs from every module and builds a single structured
EducationalScene that the Teacher Orchestrator consumes.

No raw OCR text ever reaches the teacher — only this rich scene.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from app.ai.vision_intelligence.schema import (
    BoundingBox,
    DetectedMistake,
    Diagram,
    EducationalScene,
    Formula,
    Graph,
    ImageQuality,
    PageRegion,
    Question,
    SceneConfidence,
    SceneMetadata,
    TextBlock,
)
from app.ai.vision_intelligence.diagram_engine import DiagramEngine
from app.ai.vision_intelligence.document_detector import DocumentDetector
from app.ai.vision_intelligence.formula_engine import FormulaEngine
from app.ai.vision_intelligence.graph_engine import GraphEngine
from app.ai.vision_intelligence.handwriting_engine import HandwritingEngine
from app.ai.vision_intelligence.image_preprocessor import ImagePreprocessor
from app.ai.vision_intelligence.layout_analyzer import LayoutAnalyzer
from app.ai.vision_intelligence.ocr_engine import OCREngine
from app.ai.vision_intelligence.question_extractor import QuestionExtractor
from app.ai.vision_intelligence.topic_classifier import TopicClassifier
from app.ai.vision_intelligence.vision_validator import VisionValidator
from app.core.constants import Difficulty, Subject
from app.core.logger import get_logger

log = get_logger(__name__)


class SceneBuilder:
    """Assembles all vision module outputs into a single EducationalScene.

    The SceneBuilder coordinates the partial results from every pipeline
    stage and produces the final structured scene.

    Usage::

        builder = SceneBuilder()
        scene = await builder.build(
            image=preprocessed_image,
            preprocessed_result=prep_result,
            page=page_region,
            layout=layout_blocks,
            ocr=ocr_blocks,
            handwriting=hwr_annotations,
            formulas=formulas,
            diagrams=diagrams,
            graphs=graphs,
            questions=questions,
            classification=classification,
        )
        # scene is a complete EducationalScene
    """

    def __init__(self) -> None:
        self.validator = VisionValidator()

    async def build(
        self,
        image: Optional[np.ndarray] = None,
        preprocessed_result: Optional[dict[str, Any]] = None,
        page: Optional[PageRegion] = None,
        layout: Optional[list[TextBlock]] = None,
        ocr: Optional[list[TextBlock]] = None,
        handwriting: Optional[list[Any]] = None,
        formulas: Optional[list[Formula]] = None,
        diagrams: Optional[list[Diagram]] = None,
        graphs: Optional[list[Graph]] = None,
        questions: Optional[list[Question]] = None,
        classification: Optional[dict[str, Any]] = None,
    ) -> EducationalScene:
        """Build a complete EducationalScene from all module outputs.

        Each argument is the output of a corresponding pipeline module.
        If None, the field defaults to empty in the scene.

        Returns:
            A validated EducationalScene.
        """
        log.info('scene_builder_start')

        # 1. Image quality
        quality = ImageQuality()
        if preprocessed_result:
            quality = preprocessed_result.get('quality', quality)

        # 2. Page
        page_region = page or PageRegion()

        # 3. Text blocks
        text_blocks = ocr or layout or []

        # 4. Questions
        question_list = questions or []

        # 5. Formulas
        formula_list = formulas or []

        # 6. Diagrams
        diagram_list = diagrams or []

        # 7. Graphs
        graph_list = graphs or []

        # 8. Classification
        subject = Subject.GENERAL
        topic = ''
        difficulty = Difficulty.INTERMEDIATE
        concepts: list[str] = []
        if classification:
            subject = self._resolve_subject(classification.get('subject', 'general'))
            topic = str(classification.get('topic', ''))
            difficulty = self._resolve_difficulty(classification.get('difficulty', 'intermediate'))
            concepts = [str(c) for c in (classification.get('concepts', []) or [])]

        # 9. Mistakes aggregated from questions
        all_mistakes: list[DetectedMistake] = []
        for q in question_list:
            all_mistakes.extend(q.mistakes)

        # 10. Teacher focus — what should be explained next
        teacher_focus = self._determine_focus(question_list, formula_list, diagram_list, all_mistakes)

        # 11. Already solved steps
        solved_steps: list[str] = []
        for q in question_list:
            if q.is_complete and q.student_answer:
                solved_steps.append(q.question_text[:100])

        # 12. Confidence
        conf = self._compute_confidence(
            quality=quality,
            ocr_blocks=text_blocks,
            formulas=formula_list,
            diagrams=diagram_list,
            graphs=graph_list,
            classification=classification,
            page=page_region,
        )

        # 13. Metadata
        meta = SceneMetadata()
        if preprocessed_result:
            meta.processing_time_ms = preprocessed_result.get('processing_time_ms', 0)

        scene = EducationalScene(
            image_quality=quality,
            page=page_region,
            text_blocks=text_blocks,
            questions=question_list,
            formulas=formula_list,
            diagrams=diagram_list,
            graphs=graph_list,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            concepts=concepts,
            teacher_focus=teacher_focus,
            detected_mistakes=all_mistakes,
            already_solved=len(solved_steps) > 0,
            solved_steps=solved_steps,
            confidence=conf,
            metadata=meta,
        )

        # Validate the scene — reject if confidence too low
        if not self.validator.validate(scene):
            log.warning(
                'scene_validation_failed',
                overall_confidence=conf.overall,
                reasons=self.validator.rejection_reasons,
            )
            scene.metadata.models_used = list(self.validator.rejection_reasons)

        log.info(
            'scene_builder_complete',
            questions=len(question_list),
            formulas=len(formula_list),
            diagrams=len(diagram_list),
            confidence=round(conf.overall, 3),
        )
        return scene

    # ── Teacher focus ────────────────────────────────────────────────────

    @staticmethod
    def _determine_focus(
        questions: list[Question],
        formulas: list[Formula],
        diagrams: list[Diagram],
        mistakes: list[DetectedMistake],
    ) -> str:
        """Determine what the teacher should focus on explaining."""
        if mistakes:
            types = {m.mistake_type.value for m in mistakes if m.mistake_type}
            if types:
                return f'Student has mistakes in: {", ".join(types)}. Explain corrections step by step.'

        unsolved = [q for q in questions if not q.is_complete]
        if unsolved:
            return f'Guide the student through: {unsolved[0].question_text[:100]}'

        if formulas:
            return f'Explain the formula: {formulas[0].latex or formulas[0].plain_text}'

        if diagrams:
            return f'Discuss the {diagrams[0].diagram_type.value} diagram and its components'

        return 'Understand the problem and begin step-by-step explanation'

    # ── Confidence aggregation ───────────────────────────────────────────

    @staticmethod
    def _compute_confidence(
        quality: ImageQuality,
        ocr_blocks: list[TextBlock],
        formulas: list[Formula],
        diagrams: list[Diagram],
        graphs: list[Graph],
        classification: Optional[dict[str, Any]],
        page: PageRegion,
    ) -> SceneConfidence:
        ocr_conf = 0.0
        if ocr_blocks:
            ocr_conf = float(np.mean([b.confidence for b in ocr_blocks if b.confidence > 0])) if any(
                b.confidence > 0 for b in ocr_blocks
            ) else 0.0

        formula_conf = float(np.mean([f.confidence for f in formulas])) if formulas else 0.0
        diagram_conf = float(np.mean([d.confidence for d in diagrams])) if diagrams else 0.0
        graph_conf = float(np.mean([g.confidence for g in graphs])) if graphs else 0.0
        class_conf = float(classification.get('confidence', 0.0)) if classification else 0.0

        overall = (
            quality.overall_score * 0.15 +
            ocr_conf * 0.25 +
            formula_conf * 0.10 +
            diagram_conf * 0.10 +
            graph_conf * 0.05 +
            class_conf * 0.20 +
            page.confidence * 0.15
        )

        return SceneConfidence(
            overall=round(overall, 3),
            ocr=round(ocr_conf, 3),
            handwriting=round(page.confidence, 3),
            formulas=round(formula_conf, 3),
            diagrams=round(diagram_conf, 3),
            graphs=round(graph_conf, 3),
            classification=round(class_conf, 3),
            layout=round(page.confidence, 3),
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_subject(val: str) -> Subject:
        if isinstance(val, Subject):
            return val
        try:
            return Subject(val.lower())
        except ValueError:
            return Subject.GENERAL

    @staticmethod
    def _resolve_difficulty(val: str) -> Difficulty:
        if isinstance(val, Difficulty):
            return val
        try:
            return Difficulty(val.lower())
        except ValueError:
            return Difficulty.INTERMEDIATE
