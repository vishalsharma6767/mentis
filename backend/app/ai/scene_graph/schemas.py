"""Domain models for the Educational Scene Graph system.

Every node, edge, analysis, and decision in the scene graph pipeline
is defined here. All downstream modules (reasoner, builder, validator)
import from this single schema file.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.constants import Difficulty, Subject


# ── Enums ────────────────────────────────────────────────────────────────


class NodeType(str, Enum):
    QUESTION = 'question'
    SUB_QUESTION = 'sub_question'
    FORMULA = 'formula'
    DIAGRAM = 'diagram'
    GRAPH = 'graph'
    GEOMETRY = 'geometry'
    TABLE = 'table'
    EQUATION = 'equation'
    VARIABLE = 'variable'
    CONSTANT = 'constant'
    STUDENT_ANSWER = 'student_answer'
    TEACHER_HINT = 'teacher_hint'
    MISTAKE = 'mistake'
    CONCEPT = 'concept'
    PREREQUISITE = 'prerequisite'
    LEARNING_OBJECTIVE = 'learning_objective'
    STEP = 'step'
    KNOWN_VALUE = 'known_value'
    UNKNOWN_VALUE = 'unknown_value'
    RULE = 'rule'
    THEOREM = 'theorem'
    SOLUTION_PATH = 'solution_path'
    STUDENT_STEP = 'student_step'
    TEACHER_NOTE = 'teacher_note'
    EXAMPLE = 'example'
    ANALOGY = 'analogy'


class EdgeType(str, Enum):
    CONTAINS = 'contains'
    DEPENDS_ON = 'depends_on'
    EXPLAINS = 'explains'
    REFERENCES = 'references'
    DERIVED_FROM = 'derived_from'
    SOLVES = 'solves'
    INCORRECT_STEP = 'incorrect_step'
    NEXT_STEP = 'next_step'
    REQUIRES_REVISION = 'requires_revision'
    BELONGS_TO_TOPIC = 'belongs_to_topic'
    RELATED_TO_CONCEPT = 'related_to_concept'
    LEADS_TO = 'leads_to'
    CORRECTS = 'corrects'
    PRECEDES = 'precedes'
    FOLLOWS = 'follows'
    HAS_MISTAKE = 'has_mistake'
    HAS_ANSWER = 'has_answer'
    HAS_DIAGRAM = 'has_diagram'
    HAS_FORMULA = 'has_formula'
    USES_CONCEPT = 'uses_concept'
    BUILDS_ON = 'builds_on'
    SUBSTITUTES = 'substitutes'
    EQUIVALENT_TO = 'equivalent_to'
    HAS_PROPERTY = 'has_property'
    MEASURES = 'measures'
    TEACHER_HINT = 'teacher_hint'
    TEACHER_NOTE = 'teacher_note'


class MistakeCategory(str, Enum):
    CALCULATION = 'calculation'
    CONCEPTUAL = 'conceptual'
    CARELESS = 'careless'
    SIGN_ERROR = 'sign_error'
    FORMULA_ERROR = 'formula_error'
    UNIT_ERROR = 'unit_error'
    INCOMPLETE = 'incomplete'
    DIAGRAM_ERROR = 'diagram_error'
    LABEL_ERROR = 'label_error'
    MISSING_STEP = 'missing_step'
    UNKNOWN = 'unknown'


class StepStatus(str, Enum):
    CORRECT = 'correct'
    INCORRECT = 'incorrect'
    INCOMPLETE = 'incomplete'
    SKIPPED = 'skipped'
    UNKNOWN = 'unknown'


class ReasoningDepth(str, Enum):
    SURFACE = 'surface'
    PROCEDURAL = 'procedural'
    CONCEPTUAL = 'conceptual'
    TRANSFER = 'transfer'


# ── Graph nodes ──────────────────────────────────────────────────────────


class SceneNode(BaseModel):
    """A single node in the educational scene graph."""
    id: str = Field(..., description='Unique node identifier (e.g. q_1, f_2, c_algebra)')
    type: NodeType
    label: str = Field(..., description='Human-readable label')
    content: str = Field(default='', description='Full text/content of this node')
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    data: dict[str, Any] = Field(default_factory=dict, description='Arbitrary structured data')
    metadata: dict[str, Any] = Field(default_factory=dict, description='Generation metadata')

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type.value,
            'label': self.label,
            'content': self.content[:200],
            'confidence': self.confidence,
        }


class SceneEdge(BaseModel):
    """A directed edge connecting two scene graph nodes."""
    source_id: str = Field(..., description='Source node ID')
    target_id: str = Field(..., description='Target node ID')
    type: EdgeType
    label: str = Field(default='', description='Optional edge label')
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'source': self.source_id,
            'target': self.target_id,
            'type': self.type.value,
            'label': self.label or self.type.value.replace('_', ' '),
            'confidence': self.confidence,
        }


class SceneGraphMetadata(BaseModel):
    """Metadata about the graph construction."""
    source_scene_id: str = ''
    vision_confidence: float = 0.0
    node_count: int = 0
    edge_count: int = 0
    builder_version: str = '3.5.0'
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    processing_time_ms: int = 0
    models_used: list[str] = Field(default_factory=list)
    cache_hit: bool = False


class SceneGraph(BaseModel):
    """The complete educational scene graph.

    This is the single source of truth. Every downstream module
    (teacher, planner, memory, coach, AR, speech, homework, quiz)
    consumes this graph.
    """
    nodes: list[SceneNode] = Field(default_factory=list)
    edges: list[SceneEdge] = Field(default_factory=list)
    metadata: SceneGraphMetadata = Field(default_factory=SceneGraphMetadata)
    root_node_ids: list[str] = Field(default_factory=list, description='Top-level question/concept node IDs')

    def get_node(self, node_id: str) -> Optional[SceneNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_edges(self, node_id: str, direction: str = 'outgoing') -> list[SceneEdge]:
        if direction == 'outgoing':
            return [e for e in self.edges if e.source_id == node_id]
        return [e for e in self.edges if e.target_id == node_id]

    def get_children(self, node_id: str) -> list[SceneNode]:
        child_ids = {e.target_id for e in self.edges if e.source_id == node_id}
        return [n for n in self.nodes if n.id in child_ids]

    def get_parents(self, node_id: str) -> list[SceneNode]:
        parent_ids = {e.source_id for e in self.edges if e.target_id == node_id}
        return [n for n in self.nodes if n.id in parent_ids]

    def get_nodes_by_type(self, node_type: NodeType) -> list[SceneNode]:
        return [n for n in self.nodes if n.type == node_type]

    def to_serializable(self) -> dict[str, Any]:
        return {
            'nodes': [n.to_dict() for n in self.nodes],
            'edges': [e.to_dict() for e in self.edges],
            'root_node_ids': self.root_node_ids,
            'metadata': self.metadata.model_dump(),
        }

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)


# ── Validation ───────────────────────────────────────────────────────────


class MissingNode(BaseModel):
    node_id: str
    referenced_by: list[str] = Field(default_factory=list)
    severity: str = 'error'


class CircularDependency(BaseModel):
    path: list[str] = Field(default_factory=list)
    nodes_involved: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    is_valid: bool = True
    missing_nodes: list[MissingNode] = Field(default_factory=list)
    circular_dependencies: list[CircularDependency] = Field(default_factory=list)
    low_confidence_nodes: list[str] = Field(default_factory=list)
    orphaned_nodes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ── Student attempt analysis ─────────────────────────────────────────────


class MistakeAnalysis(BaseModel):
    """Detailed analysis of a single mistake in student work."""
    step_id: str = ''
    description: str = ''
    category: MistakeCategory = MistakeCategory.UNKNOWN
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    correction: str = ''
    concept: str = ''
    severity: int = Field(default=1, ge=1, le=5, description='1=minor, 5=critical')
    is_teacher_correction: bool = False


class StudentStep(BaseModel):
    """A single step in the student's solution."""
    step_number: int = 0
    content: str = ''
    status: StepStatus = StepStatus.UNKNOWN
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    mistakes: list[MistakeAnalysis] = Field(default_factory=list)
    expected_approach: str = ''

    @property
    def has_mistake(self) -> bool:
        return len(self.mistakes) > 0


class StudentAttempt(BaseModel):
    """Complete analysis of the student's work on a question."""
    question_id: str = ''
    question_text: str = ''
    student_answer: str = ''
    steps: list[StudentStep] = Field(default_factory=list)
    solved_steps: list[str] = Field(default_factory=list)
    incomplete_steps: list[str] = Field(default_factory=list)
    skipped_steps: list[str] = Field(default_factory=list)
    mistakes: list[MistakeAnalysis] = Field(default_factory=list)
    overall_correctness: float = Field(default=0.0, ge=0.0, le=1.0)
    completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning_depth: ReasoningDepth = ReasoningDepth.SURFACE
    summary: str = ''

    @property
    def is_complete(self) -> bool:
        return self.completeness >= 0.9

    @property
    def mistake_count(self) -> int:
        return len(self.mistakes) + sum(len(s.mistakes) for s in self.steps)


# ── Concept graph ────────────────────────────────────────────────────────


class ConceptNode(BaseModel):
    """A concept in the educational knowledge graph."""
    id: str
    name: str
    subject: str = 'general'
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    is_prerequisite: bool = False
    is_current_focus: bool = False


class ConceptEdge(BaseModel):
    """A relationship between two concepts."""
    source_id: str
    target_id: str
    relationship: str = 'builds_on'
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ConceptDependencies(BaseModel):
    """Complete concept dependency graph for a topic."""
    topic: str = ''
    subject: str = 'general'
    nodes: list[ConceptNode] = Field(default_factory=list)
    edges: list[ConceptEdge] = Field(default_factory=list)
    missing_prerequisites: list[str] = Field(default_factory=list)
    recommended_path: list[str] = Field(default_factory=list, description='Topological teaching order')


# ── Teacher focus and decisions ──────────────────────────────────────────


class BoardFocus(BaseModel):
    """What the teacher should draw on the board."""
    primary_formula: str = ''
    diagram_focus: str = ''
    step_highlight: str = ''
    labels_to_write: list[str] = Field(default_factory=list)
    color_hints: list[str] = Field(default_factory=list)


class TeacherFocus(BaseModel):
    """What the teacher should focus on explaining next."""
    current_focus: str = Field(..., description='The single most important thing to explain now')
    misconception: str = Field(default='', description='The misconception to address')
    learning_objective: str = Field(default='', description='What the student should learn this turn')
    visual_focus: str = Field(default='', description='What to point at / draw on the board')
    revision_priority: list[str] = Field(default_factory=list)
    concept_to_teach: str = ''
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class TeachingPriority(BaseModel):
    """Ordered teaching priorities for the current session."""
    immediate: list[str] = Field(default_factory=list, description='Teach right now')
    next: list[str] = Field(default_factory=list, description='Teach after immediate')
    deferred: list[str] = Field(default_factory=list, description='Teach later in session')
    revision: list[str] = Field(default_factory=list, description='Must revise before proceeding')
    ignore: list[str] = Field(default_factory=list, description='Already known, skip')


class StepAnalysis(BaseModel):
    """Analysis of a single solution step with teaching guidance."""
    step_number: int
    description: str
    is_correct: bool
    confidence: float
    teacher_guidance: str = ''
    hint: str = ''
    board_action: str = ''
    ar_visualization: str = ''


class TeachingDecision(BaseModel):
    """The complete output of the Educational Reasoner.

    This is what the Teacher Orchestrator receives instead of raw
    scene data. Every downstream module uses this.
    """
    focus: TeacherFocus = Field(default_factory=TeacherFocus)
    priority: TeachingPriority = Field(default_factory=TeachingPriority)
    steps: list[StepAnalysis] = Field(default_factory=list)
    board: BoardFocus = Field(default_factory=BoardFocus)
    student_attempts: list[StudentAttempt] = Field(default_factory=list)
    concept_dependencies: Optional[ConceptDependencies] = None
    hints: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    processing_time_ms: int = 0
