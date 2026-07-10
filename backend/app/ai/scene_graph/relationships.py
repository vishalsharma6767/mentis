"""Semantic relationship definitions for the Educational Scene Graph.

Each relationship (edge type) has:
  - allowed source / target NodeTypes
  - a human-readable description
  - whether it conveys a positive or negative signal
  - whether it can be inferred automatically or requires the reasoner

This module acts as a validation rules engine for edge assignment.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.scene_graph.schemas import EdgeType, NodeType


# ── Relationship semantic record ─────────────────────────────────────────


class RelationshipSemantics:
    """Describes the semantics and constraints of a single edge type."""

    def __init__(
        self,
        edge_type: EdgeType,
        label: str,
        description: str,
        allowed_sources: Optional[list[NodeType]] = None,
        allowed_targets: Optional[list[NodeType]] = None,
        positive_signal: bool = True,
        inferrable: bool = True,
        bidirectional: bool = False,
        required_confidence: float = 0.0,
    ) -> None:
        self.edge_type = edge_type
        self.label = label
        self.description = description
        self.allowed_sources = allowed_sources or []
        self.allowed_targets = allowed_targets or []
        self.positive_signal = positive_signal
        self.inferrable = inferrable
        self.bidirectional = bidirectional
        self.required_confidence = required_confidence

    def allows_source(self, node_type: NodeType) -> bool:
        if not self.allowed_sources:
            return True
        return node_type in self.allowed_sources

    def allows_target(self, node_type: NodeType) -> bool:
        if not self.allowed_targets:
            return True
        return node_type in self.allowed_targets

    def allows(self, source: NodeType, target: NodeType) -> bool:
        return self.allows_source(source) and self.allows_target(target)

    def to_dict(self) -> dict[str, Any]:
        return {
            'type': self.edge_type.value,
            'label': self.label,
            'description': self.description,
            'bidirectional': self.bidirectional,
            'positive_signal': self.positive_signal,
        }


# ── Registry ─────────────────────────────────────────────────────────────


_SEMANTICS: dict[EdgeType, RelationshipSemantics] = {}


def _reg(
    edge_type: EdgeType,
    label: str,
    description: str,
    sources: Optional[list[NodeType]] = None,
    targets: Optional[list[NodeType]] = None,
    positive: bool = True,
    inferrable: bool = True,
    bidirectional: bool = False,
) -> None:
    _SEMANTICS[edge_type] = RelationshipSemantics(
        edge_type=edge_type,
        label=label,
        description=description,
        allowed_sources=sources or [],
        allowed_targets=targets or [],
        positive_signal=positive,
        inferrable=inferrable,
        bidirectional=bidirectional,
    )


# ── Register all edge types ──────────────────────────────────────────────

# containment hierarchy
_reg(EdgeType.CONTAINS, 'Contains', 'Parent-child containment (e.g. question contains sub-question)')
_reg(EdgeType.HAS_ANSWER, 'Has Answer', 'Question node points to its student answer')
_reg(EdgeType.HAS_MISTAKE, 'Has Mistake', 'Step or answer has a detected mistake',
    positive=False)
_reg(EdgeType.HAS_DIAGRAM, 'Has Diagram', 'Question or concept has an associated diagram')
_reg(EdgeType.HAS_FORMULA, 'Has Formula', 'Question or concept has an associated formula')

# dependency
_reg(EdgeType.DEPENDS_ON, 'Depends On', 'One node depends on another (prerequisite)')
_reg(EdgeType.BUILDS_ON, 'Builds On', 'Concept builds on prerequisite concept')
_reg(EdgeType.REQUIRES_REVISION, 'Requires Revision', 'Student must revise this before proceeding',
    positive=False)
_reg(EdgeType.PRECEDES, 'Precedes', 'Temporal ordering — this comes before that')

# reasoning
_reg(EdgeType.EXPLAINS, 'Explains', 'Node explains / defines another node')
_reg(EdgeType.USES_CONCEPT, 'Uses Concept', 'Step or answer uses a specific concept')
_reg(EdgeType.RELATED_TO_CONCEPT, 'Related to Concept', 'Node is related to a concept')
_reg(EdgeType.BELONGS_TO_TOPIC, 'Belongs to Topic', 'Node belongs to a topic')
_reg(EdgeType.REFERENCES, 'References', 'Cross-reference between nodes')
_reg(EdgeType.LEADS_TO, 'Leads To', 'Understanding this leads to understanding that')

# solution steps
_reg(EdgeType.SOLVES, 'Solves', 'Step or formula solves something')
_reg(EdgeType.NEXT_STEP, 'Next Step', 'The next step in the solution process')
_reg(EdgeType.FOLLOWS, 'Follows', 'Node follows logically from another')
_reg(EdgeType.CORRECTS, 'Corrects', 'Corrective relationship (teacher hint corrects mistake)')
_reg(EdgeType.INCORRECT_STEP, 'Incorrect Step', 'Step contains an error',
    positive=False)

# mathematical
_reg(EdgeType.DERIVED_FROM, 'Derived From', 'Mathematical derivation relationship')
_reg(EdgeType.SUBSTITUTES, 'Substitutes', 'Substitution relationship (variable → value)')
_reg(EdgeType.EQUIVALENT_TO, 'Equivalent To', 'Logical or mathematical equivalence')
_reg(EdgeType.HAS_PROPERTY, 'Has Property', 'Node has a specific property')
_reg(EdgeType.MEASURES, 'Measures', 'Measurement relationship (e.g. angle measures 45°)')

# teaching
_reg(EdgeType.TEACHER_HINT, 'Teacher Hint', 'Hedge or hint for the teacher to give',
    inferrable=False)


# ── Public API ───────────────────────────────────────────────────────────


def get_semantics(edge_type: EdgeType) -> RelationshipSemantics:
    """Return the semantic record for an edge type."""
    sem = _SEMANTICS.get(edge_type)
    if sem is None:
        raise ValueError(f'Unknown edge type: {edge_type}')
    return sem


def is_valid_edge(source_type: NodeType, edge_type: EdgeType, target_type: NodeType) -> bool:
    """Check whether an edge of *edge_type* is valid between *source_type* and *target_type*."""
    sem = get_semantics(edge_type)
    return sem.allows(source_type, target_type)


def allowed_edge_types(source_type: NodeType, target_type: NodeType) -> list[EdgeType]:
    """Return all edge types valid between the given node types."""
    result: list[EdgeType] = []
    for et, sem in _SEMANTICS.items():
        if sem.allows(source_type, target_type):
            result.append(et)
    return result


def positive_edge_types() -> list[EdgeType]:
    """Return edge types that convey a positive signal."""
    return [et for et, sem in _SEMANTICS.items() if sem.positive_signal]


def negative_edge_types() -> list[EdgeType]:
    """Return edge types that convey a negative signal (mistakes, errors)."""
    return [et for et, sem in _SEMANTICS.items() if not sem.positive_signal]


def inferrable_edge_types() -> list[EdgeType]:
    """Return edge types that can be automatically inferred."""
    return [et for et, sem in _SEMANTICS.items() if sem.inferrable]


def all_semantics() -> list[dict[str, Any]]:
    return [sem.to_dict() for sem in _SEMANTICS.values()]
