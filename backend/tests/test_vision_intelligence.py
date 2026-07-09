"""Tests for the Vision Intelligence Engine (Phase 3).

Tests every module in isolation and the full pipeline end-to-end.

Run with: pytest tests/test_vision_intelligence.py -v
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.ai.vision_intelligence.adapter import VisionAdapter
from app.ai.vision_intelligence.diagram_engine import DiagramEngine
from app.ai.vision_intelligence.document_detector import DocumentDetector
from app.ai.vision_intelligence.formula_engine import FormulaEngine
from app.ai.vision_intelligence.graph_engine import GraphEngine
from app.ai.vision_intelligence.handwriting_engine import HandwritingEngine
from app.ai.vision_intelligence.image_preprocessor import ImagePreprocessor
from app.ai.vision_intelligence.layout_analyzer import LayoutAnalyzer
from app.ai.vision_intelligence.ocr_engine import OCREngine
from app.ai.vision_intelligence.pipeline import VisionPipeline
from app.ai.vision_intelligence.question_extractor import QuestionExtractor
from app.ai.vision_intelligence.scene_builder import SceneBuilder
from app.ai.vision_intelligence.schema import (
    BoundingBox,
    Diagram,
    DiagramType,
    EducationalScene,
    Formula,
    FormulaType,
    Graph,
    ImageQuality,
    PageRegion,
    Question,
    SceneConfidence,
    TextBlock,
)
from app.ai.vision_intelligence.topic_classifier import TopicClassifier
from app.ai.vision_intelligence.vision_validator import VisionValidator

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_test_image(h: int = 400, w: int = 300, value: int = 200) -> np.ndarray:
    """Create a simple test image."""
    return np.full((h, w, 3), value, dtype=np.uint8)


def _make_test_image_with_text(h: int = 400, w: int = 300) -> np.ndarray:
    """Create a test image with some synthetic features."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    # Add a dark rectangle (simulating text)
    img[50:100, 50:250] = (30, 30, 30)
    img[120:140, 50:200] = (30, 30, 30)
    return img


# ── Schema tests ─────────────────────────────────────────────────────────


class TestSchema:
    def test_bounding_box_validation(self):
        bbox = BoundingBox(x=0.1, y=0.2, width=0.5, height=0.3)
        assert bbox.area == 0.15
        cx, cy = bbox.centre
        assert cx == pytest.approx(0.35)
        assert cy == pytest.approx(0.35)

    def test_scene_confidence_reliable(self):
        conf = SceneConfidence(ocr=0.8, layout=0.7, classification=0.9, overall=0.8)
        assert conf.is_reliable() is True

    def test_scene_confidence_unreliable(self):
        conf = SceneConfidence(ocr=0.2, layout=0.7, classification=0.3, overall=0.3)
        assert conf.is_reliable(threshold=0.5) is False

    def test_educational_scene_to_vision_output(self):
        scene = EducationalScene(
            subject='math',
            difficulty='intermediate',
            concepts=['algebra', 'equations'],
            formulas=[Formula(latex='x+5=10', plain_text='x + 5 = 10', bbox=BoundingBox(x=0, y=0, width=0.1, height=0.1))],
            questions=[Question(question_text='Solve for x', bbox=BoundingBox(x=0, y=0, width=1, height=1))],
        )
        output = scene.to_vision_output()
        assert 'x + 5 = 10' in output['raw_text']
        assert output['subject'] == 'math'
        assert output['problem_type'] == 'equation'

    def test_educational_scene_empty(self):
        scene = EducationalScene()
        output = scene.to_vision_output()
        assert output['raw_text'] == ''
        assert output['subject'] == 'general'


# ── Image Preprocessor tests ─────────────────────────────────────────────


class TestImagePreprocessor:
    @pytest.fixture
    def preprocessor(self):
        return ImagePreprocessor()

    @pytest.mark.asyncio
    async def test_process_good_image(self, preprocessor):
        img = _make_test_image(400, 300, 180)
        result = await preprocessor.process(img)
        assert result['quality'].is_acceptable is True
        assert result['image'] is not None
        assert result['processing_time_ms'] >= 0

    @pytest.mark.asyncio
    async def test_reject_empty_image(self, preprocessor):
        result = await preprocessor.process(np.array([]))
        assert result['quality'].is_acceptable is False
        assert 'Empty' in result['quality'].rejection_reason

    @pytest.mark.asyncio
    async def test_reject_blank_image(self, preprocessor):
        img = np.full((100, 100, 3), 255, dtype=np.uint8)
        result = await preprocessor.process(img)
        assert result['quality'].is_acceptable is False


# ── Document Detector tests ──────────────────────────────────────────────


class TestDocumentDetector:
    @pytest.fixture
    def detector(self):
        return DocumentDetector()

    @pytest.mark.asyncio
    async def test_detect_no_document(self, detector):
        img = _make_test_image(100, 100, 128)
        result = await detector.detect(img)
        assert result.page_type.value == 'unknown'
        assert result.confidence <= 0.3


# ── Layout Analyzer tests ────────────────────────────────────────────────


class TestLayoutAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return LayoutAnalyzer()

    @pytest.mark.asyncio
    async def test_analyze_empty_image(self, analyzer):
        result = await analyzer.analyze(np.array([]))
        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_simple(self, analyzer):
        img = _make_test_image_with_text()
        blocks = await analyzer.analyze(img)
        assert isinstance(blocks, list)


# ── OCR Engine tests ─────────────────────────────────────────────────────


class TestOCREngine:
    @pytest.fixture
    def engine(self):
        return OCREngine()

    @pytest.mark.asyncio
    async def test_empty_image(self, engine):
        result = await engine.extract(np.array([]), [])
        assert result == []

    def test_detect_language_hinglish(self):
        lang = OCREngine._detect_language('Yeh equation solve karo')
        assert lang.value == 'hinglish'

    def test_detect_language_hindi(self):
        lang = OCREngine._detect_language('समीकरण को हल कीजिए')
        assert lang.value == 'hindi'

    def test_detect_language_english(self):
        lang = OCREngine._detect_language('Solve this equation for x')
        assert lang.value == 'english'


# ── Handwriting Engine tests ──────────────────────────────────────────────


class TestHandwritingEngine:
    @pytest.fixture
    def engine(self):
        return HandwritingEngine()

    @pytest.mark.asyncio
    async def test_analyze_empty(self, engine):
        result = await engine.analyze(np.array([]), [])
        assert result == []

    def test_estimate_legibility_blank(self):
        img = np.full((50, 100, 3), 255, dtype=np.uint8)
        leg = HandwritingEngine._estimate_legibility(img)
        assert 0.0 <= leg <= 1.0


# ── Formula Engine tests ─────────────────────────────────────────────────


class TestFormulaEngine:
    @pytest.fixture
    def engine(self):
        return FormulaEngine()

    @pytest.mark.asyncio
    async def test_detect_empty(self, engine):
        result = await engine.detect(np.array([]), [])
        assert result == []

    def test_heuristic_detect_math(self):
        bbox = BoundingBox(x=0, y=0, width=0.5, height=0.1)
        results = FormulaEngine._heuristic_detect('x² + 5 = 10', bbox)
        assert len(results) == 1
        assert results[0].formula_type == FormulaType.MATHEMATICS

    def test_heuristic_detect_physics(self):
        bbox = BoundingBox(x=0, y=0, width=0.5, height=0.1)
        results = FormulaEngine._heuristic_detect('F = ma where m is mass', bbox)
        assert len(results) == 1
        assert results[0].formula_type == FormulaType.PHYSICS

    def test_heuristic_detect_chemistry(self):
        bbox = BoundingBox(x=0, y=0, width=0.5, height=0.1)
        results = FormulaEngine._heuristic_detect('H₂O → H₂ + O₂', bbox)
        assert len(results) == 1
        assert results[0].formula_type == FormulaType.CHEMISTRY

    def test_deduplicate(self):
        bbox = BoundingBox(x=0, y=0, width=0.1, height=0.1)
        formulas = [
            Formula(latex='a', bbox=bbox, formula_type=FormulaType.MATHEMATICS, confidence=0.9),
            Formula(latex='b', bbox=bbox, formula_type=FormulaType.MATHEMATICS, confidence=0.5),
        ]
        deduped = FormulaEngine._deduplicate(formulas)
        assert len(deduped) == 1


# ── Diagram Engine tests ─────────────────────────────────────────────────


class TestDiagramEngine:
    @pytest.fixture
    def engine(self):
        return DiagramEngine()

    @pytest.mark.asyncio
    async def test_detect_empty(self, engine):
        result = await engine.detect(np.array([]))
        assert result == []

    def test_classify_coordinate_axes(self):
        dtype = DiagramEngine._classify_diagram_type(
            ['horizontal_line', 'vertical_line', 'arrow_likely'],
            _make_test_image(),
        )
        assert dtype == DiagramType.COORDINATE_AXES

    def test_classify_free_body(self):
        dtype = DiagramEngine._classify_diagram_type(
            ['diagonal_line', 'arrow_likely'],
            _make_test_image(),
        )
        assert dtype == DiagramType.FREE_BODY_DIAGRAM


# ── Graph Engine tests ────────────────────────────────────────────────────


class TestGraphEngine:
    @pytest.fixture
    def engine(self):
        return GraphEngine()

    @pytest.mark.asyncio
    async def test_analyze_empty_image(self, engine):
        result = await engine.analyze(np.array([]), [])
        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_no_regions(self, engine):
        img = _make_test_image()
        result = await engine.analyze(img, [])
        assert result == []


# ── Question Extractor tests ─────────────────────────────────────────────


class TestQuestionExtractor:
    @pytest.fixture
    def extractor(self):
        return QuestionExtractor()

    def test_is_question_numbered(self):
        assert QuestionExtractor._is_question('1. Solve the equation')

    def test_is_question_with_q(self):
        assert QuestionExtractor._is_question('Q. Find the value of x')

    def test_is_question_with_problem(self):
        assert QuestionExtractor._is_question('Problem: A train travels...')

    def test_is_not_question(self):
        assert not QuestionExtractor._is_question('The answer is 42')

    def test_is_answer_with_solution(self):
        assert QuestionExtractor._is_answer('Solution: x = 5')

    def test_is_not_answer(self):
        assert not QuestionExtractor._is_answer('What is the capital of France?')


# ── Topic Classifier tests ────────────────────────────────────────────────


class TestTopicClassifier:
    @pytest.fixture
    def classifier(self):
        return TopicClassifier()

    @pytest.mark.asyncio
    async def test_classify_math(self, classifier):
        result = await classifier.classify('Solve the quadratic equation x² + 5x + 6 = 0')
        assert result['subject'] == 'math'
        assert 'quadratic_equations' in result['topic'] or 'general' in result['topic']

    @pytest.mark.asyncio
    async def test_classify_physics(self, classifier):
        result = await classifier.classify('A force of 10 N acts on a mass of 2 kg')
        assert result['subject'] == 'physics'

    @pytest.mark.asyncio
    async def test_classify_empty(self, classifier):
        result = await classifier.classify('')
        assert result['subject'] == 'general'

    def test_heuristic_subject(self):
        subj = TopicClassifier._heuristic_subject('Solve for x in the equation')
        assert subj == 'math'

    def test_heuristic_difficulty_advanced(self):
        diff = TopicClassifier._heuristic_difficulty('Prove the general form of the differential equation')
        assert diff == 'advanced'

    def test_heuristic_difficulty_beginner(self):
        diff = TopicClassifier._heuristic_difficulty('What is the basic definition of a cell?')
        assert diff == 'beginner'


# ── Scene Builder tests ────────────────────────────────────────────────────


class TestSceneBuilder:
    @pytest.fixture
    def builder(self):
        return SceneBuilder()

    @pytest.mark.asyncio
    async def test_build_empty(self, builder):
        scene = await builder.build()
        assert isinstance(scene, EducationalScene)
        assert scene.confidence.overall == 0.0

    @pytest.mark.asyncio
    async def test_build_with_questions(self, builder):
        questions = [
            Question(question_text='Solve x+5=10', bbox=BoundingBox(x=0, y=0, width=1, height=1), confidence=0.8),
        ]
        scene = await builder.build(questions=questions, classification={'subject': 'math', 'difficulty': 'beginner', 'topic': 'linear_equations', 'confidence': 0.7})
        assert len(scene.questions) == 1
        assert scene.subject.value == 'math'
        assert 'linear_equations' in scene.topic
        assert 'Solve' in scene.teacher_focus


# ── Vision Validator tests ──────────────────────────────────────────────


class TestVisionValidator:
    @pytest.fixture
    def validator(self):
        return VisionValidator()

    def test_accept_good_scene(self, validator):
        scene = EducationalScene(
            image_quality=ImageQuality(overall_score=0.8, is_acceptable=True),
            confidence=SceneConfidence(overall=0.7, ocr=0.6, classification=0.8, layout=0.7, handwriting=0.5, formulas=0.0, diagrams=0.0, graphs=0.0),
            text_blocks=[TextBlock(text='hello', bbox=BoundingBox(x=0, y=0, width=0.1, height=0.1))],
        )
        assert validator.validate(scene) is True

    def test_reject_low_quality(self, validator):
        scene = EducationalScene(
            image_quality=ImageQuality(overall_score=0.1, is_acceptable=False, rejection_reason='Image is too dark'),
        )
        assert validator.validate(scene) is False
        assert validator.rejection_reasons

    def test_reject_empty_scene(self, validator):
        scene = EducationalScene()
        assert validator.validate(scene) is False


# ── Adapter tests ────────────────────────────────────────────────────────


class TestVisionAdapter:
    def test_to_vision_output(self):
        scene = EducationalScene(
            subject='math',
            difficulty='intermediate',
            concepts=['algebra'],
            formulas=[Formula(latex='E=mc²', bbox=BoundingBox(x=0, y=0, width=0.1, height=0.05))],
            questions=[Question(question_text='Find mass', student_answer='m=5', bbox=BoundingBox(x=0, y=0, width=1, height=1))],
        )
        output = VisionAdapter.to_vision_output(scene)
        assert output['subject'] == 'math'
        assert 'E=mc²' in output['raw_text']
        assert output['problem_type'] == 'equation'

    def test_needs_recapture(self):
        scene = EducationalScene(
            image_quality=ImageQuality(overall_score=0.1, is_acceptable=False),
        )
        assert VisionAdapter.needs_recapture(scene) is True

    def test_to_vision_context(self):
        scene = EducationalScene(
            subject='physics',
            questions=[Question(question_text='Find F', bbox=BoundingBox(x=0, y=0, width=1, height=1))],
            teacher_focus='Explain F=ma',
        )
        ctx = VisionAdapter.to_vision_context(scene)
        assert ctx['subject'] == 'physics'
        assert ctx['teacher_focus'] == 'Explain F=ma'


# ── Pipeline integration tests ──────────────────────────────────────────


class TestVisionPipeline:
    @pytest.fixture
    def pipeline(self):
        return VisionPipeline()

    @pytest.mark.asyncio
    async def test_run_empty_image(self, pipeline):
        scene = await pipeline.run(np.array([]))
        assert isinstance(scene, EducationalScene)
        assert scene.metadata.processing_time_ms >= 0

    @pytest.mark.asyncio
    async def test_run_simple_image(self, pipeline):
        img = _make_test_image(200, 200, 180)
        scene = await pipeline.run(img)
        assert isinstance(scene, EducationalScene)

    @pytest.mark.asyncio
    async def test_pipeline_returns_scene_not_ocr(self, pipeline):
        img = _make_test_image(200, 200, 180)
        scene = await pipeline.run(img)
        # The teacher never receives raw OCR — only EducationalScene
        assert not hasattr(scene, 'raw_text')
        assert isinstance(scene, EducationalScene)
        assert scene.confidence is not None
