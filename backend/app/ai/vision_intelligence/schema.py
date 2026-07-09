"""Vision Intelligence domain models — pure Pydantic v2 schemas.

Every module in the vision pipeline produces structured data that
conforms to these models. The final output is always an EducationalScene.

No raw OCR text ever reaches the teacher — only structured educational
understanding.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.constants import Difficulty, Subject


# ── Enums ────────────────────────────────────────────────────────────────


class BlockType(str, Enum):
    HEADING = 'heading'
    QUESTION_TEXT = 'question_text'
    STUDENT_ANSWER = 'student_answer'
    TEACHER_NOTE = 'teacher_note'
    INSTRUCTION = 'instruction'
    EXAMPLE = 'example'
    FORMULA = 'formula'
    DIAGRAM_LABEL = 'diagram_label'
    MARGIN_NOTE = 'margin_note'
    UNKNOWN = 'unknown'


class FormulaType(str, Enum):
    MATHEMATICS = 'mathematics'
    PHYSICS = 'physics'
    CHEMISTRY = 'chemistry'
    STATISTICS = 'statistics'
    PROGRAMMING = 'programming'
    GENERAL = 'general'


class DiagramType(str, Enum):
    TRIANGLE = 'triangle'
    CIRCLE = 'circle'
    COORDINATE_AXES = 'coordinate_axes'
    FREE_BODY_DIAGRAM = 'free_body_diagram'
    ELECTRIC_CIRCUIT = 'electric_circuit'
    BIOLOGY = 'biology'
    FLOWCHART = 'flowchart'
    CHEMISTRY_STRUCTURE = 'chemistry_structure'
    BAR_CHART = 'bar_chart'
    PIE_CHART = 'pie_chart'
    LINE_GRAPH = 'line_graph'
    GENERAL = 'general'


class MistakeType(str, Enum):
    CALCULATION = 'calculation'
    CONCEPTUAL = 'conceptual'
    CARELESS = 'careless'
    INCOMPLETE = 'incomplete'
    SIGN_ERROR = 'sign_error'
    FORMULA_ERROR = 'formula_error'
    UNIT_ERROR = 'unit_error'
    UNKNOWN = 'unknown'


class PageType(str, Enum):
    NOTEBOOK = 'notebook'
    BOOK = 'book'
    WORKSHEET = 'worksheet'
    WHITEBOARD = 'whiteboard'
    LOOSE_PAPER = 'loose_paper'
    SCREEN = 'screen'
    UNKNOWN = 'unknown'


class Language(str, Enum):
    ENGLISH = 'english'
    HINDI = 'hindi'
    HINGLISH = 'hinglish'
    MIXED = 'mixed'


# ── Geometry ─────────────────────────────────────────────────────────────


class BoundingBox(BaseModel):
    """Normalised bounding box (0.0-1.0) within the page."""
    x: float = Field(..., ge=0.0, le=1.0, description='Left edge, normalised')
    y: float = Field(..., ge=0.0, le=1.0, description='Top edge, normalised')
    width: float = Field(..., ge=0.0, le=1.0, description='Width, normalised')
    height: float = Field(..., ge=0.0, le=1.0, description='Height, normalised')

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)


class Point2D(BaseModel):
    x: float
    y: float


# ── Image-level ──────────────────────────────────────────────────────────


class ImageQuality(BaseModel):
    """Quality assessment of the raw camera image."""
    brightness: float = Field(default=0.5, ge=0.0, le=1.0)
    contrast: float = Field(default=0.5, ge=0.0, le=1.0)
    sharpness: float = Field(default=0.5, ge=0.0, le=1.0)
    blur_score: float = Field(default=1.0, ge=0.0, le=1.0, description='1.0 = sharp, 0.0 = fully blurred')
    noise_level: float = Field(default=0.0, ge=0.0, le=1.0, description='0.0 = clean')
    shadow_present: bool = False
    skew_angle_degrees: float = 0.0
    overall_score: float = Field(default=0.5, ge=0.0, le=1.0)
    is_acceptable: bool = True
    rejection_reason: str = ''


class PageRegion(BaseModel):
    """Detected page within the image."""
    page_type: PageType = PageType.UNKNOWN
    bbox: BoundingBox = Field(default_factory=lambda: BoundingBox(x=0, y=0, width=1, height=1))
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    corners: list[Point2D] = Field(default_factory=list, description='Four corner points after perspective correction')
    page_number: Optional[int] = None


# ── Content blocks ───────────────────────────────────────────────────────


class TextBlock(BaseModel):
    """A block of text with positional and semantic information."""
    text: str
    bbox: BoundingBox
    block_type: BlockType = BlockType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: Language = Language.MIXED
    is_handwritten: bool = False
    font_size_estimate: Optional[float] = None
    line_number: Optional[int] = None


class Formula(BaseModel):
    """A detected mathematical or scientific formula."""
    latex: str = ''
    plain_text: str = ''
    bbox: BoundingBox
    formula_type: FormulaType = FormulaType.GENERAL
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    symbols: list[str] = Field(default_factory=list, description='Detected symbols/variables')
    is_handwritten: bool = False


class Diagram(BaseModel):
    """A detected diagram or illustration."""
    diagram_type: DiagramType = DiagramType.GENERAL
    bbox: BoundingBox
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    labels: list[str] = Field(default_factory=list)
    shapes_detected: list[str] = Field(default_factory=list, description='e.g. circle, line, arrow, rectangle')
    description: str = ''


class Graph(BaseModel):
    """A detected graph/chart with axis and trend understanding."""
    bbox: BoundingBox
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    x_label: str = ''
    y_label: str = ''
    title: str = ''
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    points: list[Point2D] = Field(default_factory=list)
    curves: list[list[Point2D]] = Field(default_factory=list)
    trend_description: str = ''
    is_linear: Optional[bool] = None


class DetectedTable(BaseModel):
    """A detected table structure."""
    bbox: BoundingBox
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rows: int = 0
    columns: int = 0
    headers: list[str] = Field(default_factory=list)
    cells: list[list[str]] = Field(default_factory=list)


class DetectedMistake(BaseModel):
    """A detected mistake or correction in the student's work."""
    text: str = ''
    bbox: BoundingBox
    mistake_type: MistakeType = MistakeType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    correction: str = ''
    is_teacher_correction: bool = False


# ── Questions ────────────────────────────────────────────────────────────


class Question(BaseModel):
    """A complete question with the student's attempt."""
    question_text: str = ''
    student_answer: str = ''
    teacher_notes: str = ''
    bbox: BoundingBox
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    mistakes: list[DetectedMistake] = Field(default_factory=list)
    sub_questions: list[Question] = Field(default_factory=list)
    is_complete: bool = False
    step_number: Optional[int] = None


# ── Scene ────────────────────────────────────────────────────────────────


class SceneConfidence(BaseModel):
    """Aggregate confidence scores for the full scene."""
    overall: float = Field(default=0.0, ge=0.0, le=1.0)
    ocr: float = Field(default=0.0, ge=0.0, le=1.0)
    handwriting: float = Field(default=0.0, ge=0.0, le=1.0)
    formulas: float = Field(default=0.0, ge=0.0, le=1.0)
    diagrams: float = Field(default=0.0, ge=0.0, le=1.0)
    graphs: float = Field(default=0.0, ge=0.0, le=1.0)
    classification: float = Field(default=0.0, ge=0.0, le=1.0)
    layout: float = Field(default=0.0, ge=0.0, le=1.0)

    def is_reliable(self, threshold: float = 0.6) -> bool:
        """Return True if all key components meet the threshold."""
        return all([
            self.ocr >= threshold if self.ocr > 0 else True,
            self.classification >= threshold,
            self.layout >= threshold,
        ])


class SceneMetadata(BaseModel):
    """Metadata about the vision pipeline execution."""
    processing_time_ms: int = 0
    pipeline_version: str = '3.0.0'
    models_used: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    image_dimensions: Optional[tuple[int, int]] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class EducationalScene(BaseModel):
    """The final structured output of the Vision Intelligence Engine.

    This is the ONLY thing the Teacher Agent receives. No raw OCR text
    is ever passed to the teacher — only this rich, structured scene.
    """
    # Image & page
    image_quality: ImageQuality = Field(default_factory=ImageQuality)
    page: PageRegion = Field(default_factory=PageRegion)

    # Content
    text_blocks: list[TextBlock] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    formulas: list[Formula] = Field(default_factory=list)
    diagrams: list[Diagram] = Field(default_factory=list)
    graphs: list[Graph] = Field(default_factory=list)
    tables: list[DetectedTable] = Field(default_factory=list)

    # Classification
    subject: Subject = Subject.GENERAL
    topic: str = ''
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    concepts: list[str] = Field(default_factory=list)

    # Teacher guidance
    teacher_focus: str = Field(
        default='',
        description='What the teacher should focus on explaining next',
    )
    detected_mistakes: list[DetectedMistake] = Field(default_factory=list)
    already_solved: bool = False
    solved_steps: list[str] = Field(default_factory=list)

    # Confidence & metadata
    confidence: SceneConfidence = Field(default_factory=SceneConfidence)
    metadata: SceneMetadata = Field(default_factory=SceneMetadata)

    def has_questions(self) -> bool:
        return len(self.questions) > 0

    def has_formulas(self) -> bool:
        return len(self.formulas) > 0

    def has_diagrams(self) -> bool:
        return len(self.diagrams) > 0

    def to_vision_output(self) -> dict[str, Any]:
        """Convert to the format expected by existing Orchestrator.

        Returns a dict matching the existing VisionOutput schema so
        the downstream pipeline can consume it unchanged.
        """
        raw_text_parts: list[str] = []
        for q in self.questions:
            raw_text_parts.append(f'Question: {q.question_text}')
            if q.student_answer:
                raw_text_parts.append(f'Answer: {q.student_answer}')
        for tb in self.text_blocks:
            if tb.text:
                raw_text_parts.append(tb.text)
        for f in self.formulas:
            if f.latex or f.plain_text:
                raw_text_parts.append(f.latex or f.plain_text)

        return {
            'raw_text': '\n'.join(raw_text_parts) if raw_text_parts else '',
            'subject': self.subject,
            'difficulty': self.difficulty,
            'topics': self.concepts or ([self.topic] if self.topic else []),
            'problem_type': self._detect_problem_type(),
            'detected_elements': self._detect_elements(),
            'diagram_type': self._detect_diagram_type(),
            'formulas': [f.latex or f.plain_text for f in self.formulas],
            'confidence': self.confidence.overall,
        }

    def _detect_problem_type(self) -> str:
        if self.formulas:
            return 'equation'
        if self.diagrams:
            return 'diagram'
        if self.graphs:
            return 'graph'
        for q in self.questions:
            if 'diagram' in q.question_text.lower() or 'graph' in q.question_text.lower():
                return 'diagram' if 'diagram' in q.question_text.lower() else 'graph'
        return 'general'

    def _detect_elements(self) -> list[str]:
        elements: list[str] = ['text']
        if self.formulas:
            elements.append('equation')
        if self.diagrams:
            elements.append('diagram')
        if self.graphs:
            elements.append('graph')
        if self.tables:
            elements.append('table')
        return elements

    def _detect_diagram_type(self) -> Optional[str]:
        if not self.diagrams:
            if self.graphs:
                return self.graphs[0].trend_description[:50] or 'graph'
            return None
        return self.diagrams[0].diagram_type.value
