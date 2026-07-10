"""Educational Scene Graph — Mentis Phase 3.5.

Converts the Vision Intelligence Engine's EducationalScene into a rich
semantic graph that becomes the single source of truth for:
  - Teacher Orchestrator
  - Planner Agent
  - Coach Agent
  - Memory Agent
  - Homework Agent
  - Quiz Agent
  - Recommendation Engine
  - AR Planner
  - Response Composer

Pipeline:
  EducationalScene → SceneGraphBuilder → EducationalSceneGraph
    → StudentAttemptAnalyzer → StudentAttempt
    → ConceptGraphBuilder → ConceptDependencies
    → EducationalReasoner → TeachingDecision
    → TeacherOrchestrator

No module consumes raw OCR. The graph is the source of truth.
"""

from app.ai.scene_graph.schemas import (
    BoardFocus,
    CircularDependency,
    ConceptDependencies,
    ConceptEdge,
    ConceptNode,
    EdgeType,
    MistakeAnalysis,
    MistakeCategory,
    MissingNode,
    NodeType,
    ReasoningDepth,
    SceneEdge,
    SceneGraph,
    SceneGraphMetadata,
    SceneNode,
    StepAnalysis,
    StepStatus,
    StudentAttempt,
    StudentStep,
    TeacherFocus,
    TeachingDecision,
    TeachingPriority,
    ValidationResult,
)

from app.ai.scene_graph.graph import EducationalSceneGraph
from app.ai.scene_graph.builder import SceneGraphBuilder
from app.ai.scene_graph.student_attempt import StudentAttemptAnalyzer
from app.ai.scene_graph.concept_graph import ConceptGraphBuilder
from app.ai.scene_graph.reasoner import EducationalReasoner
from app.ai.scene_graph.validator import SceneGraphValidator
from app.ai.scene_graph.integration import SceneGraphIntegration
from app.ai.scene_graph.relationships import (
    RelationshipSemantics,
    all_semantics,
    allowed_edge_types,
    get_semantics,
    inferrable_edge_types,
    is_valid_edge,
    negative_edge_types,
    positive_edge_types,
)

__all__ = [
    # Schemas
    'BoardFocus', 'CircularDependency', 'ConceptDependencies', 'ConceptEdge',
    'ConceptNode', 'EdgeType', 'MistakeAnalysis', 'MistakeCategory',
    'MissingNode', 'NodeType', 'ReasoningDepth', 'SceneEdge', 'SceneGraph',
    'SceneGraphMetadata', 'SceneNode', 'StepAnalysis', 'StepStatus',
    'StudentAttempt', 'StudentStep', 'TeacherFocus', 'TeachingDecision',
    'TeachingPriority', 'ValidationResult',
    # Core
    'EducationalSceneGraph', 'SceneGraphBuilder', 'StudentAttemptAnalyzer',
    'ConceptGraphBuilder', 'EducationalReasoner', 'SceneGraphValidator',
    'SceneGraphIntegration',
    # Relationships
    'RelationshipSemantics', 'all_semantics', 'allowed_edge_types',
    'get_semantics', 'inferrable_edge_types', 'is_valid_edge',
    'negative_edge_types', 'positive_edge_types',
]
