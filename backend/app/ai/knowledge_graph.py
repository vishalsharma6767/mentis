"""Knowledge Graph Engine — per-student concept mastery tracking.

The knowledge graph stores:
  - Every concept the student has encountered
  - Mastery level (0.0 – 1.0) for each concept
  - Prerequisite relationships between concepts
  - Strong vs weak concept classification
  - Revision priority scoring

The graph grows after every lesson. It is the single source of truth
for what the student knows and what they need to learn next.

Every mutation fires an event on the Event Bus so the Context Engine
and other modules can react without coupling.
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.constants import ConfidenceLevel, KnowledgeEdgeType, Subject
from app.core.events import EventBus, EventType
from app.core.logger import get_logger

log = get_logger(__name__)

MASTERY_THRESHOLD_HIGH = 0.8
MASTERY_THRESHOLD_MEDIUM = 0.5
MASTERY_THRESHOLD_LOW = 0.3
RECENCY_DECAY_HOURS = 72  # topics not practiced in 72h lose priority


@dataclass
class ConceptNode:
    """A single concept in the student's knowledge graph."""
    topic_id: str
    name: str
    subject: Subject = Subject.GENERAL
    mastery: float = 0.0  # 0.0 – 1.0
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    times_practiced: int = 0
    mistakes_count: int = 0
    last_practiced_at: Optional[float] = None  # Unix timestamp
    prerequisites: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    """A directed relationship between two concepts."""
    source: str
    target: str
    edge_type: KnowledgeEdgeType = KnowledgeEdgeType.PREREQUISITE
    weight: float = 1.0


@dataclass
class GraphSnapshot:
    """Immutable snapshot of the knowledge graph at a point in time."""
    nodes: dict[str, ConceptNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    weak_concepts: list[str] = field(default_factory=list)
    strong_concepts: list[str] = field(default_factory=list)
    revision_priority: list[tuple[str, float]] = field(default_factory=list)
    overall_mastery: float = 0.0


class KnowledgeGraphEngine:
    """Per-student knowledge graph.

    Usage::

        kg = KnowledgeGraphEngine(user_id)
        kg.update_mastery('algebra', 0.6)
        kg.record_mistake('fractions')
        snapshot = kg.snapshot()
        print(snapshot.weak_concepts)
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._nodes: dict[str, ConceptNode] = {}
        self._edges: list[GraphEdge] = []
        self._bus = EventBus.get_instance()

    # ── Mutations ──────────────────────────────────────────────────────

    def add_concept(
        self,
        topic_id: str,
        name: str,
        subject: Subject = Subject.GENERAL,
        prerequisites: Optional[list[str]] = None,
    ) -> ConceptNode:
        """Add a concept to the graph if it doesn't exist."""
        if topic_id not in self._nodes:
            self._nodes[topic_id] = ConceptNode(
                topic_id=topic_id,
                name=name,
                subject=subject,
                prerequisites=prerequisites or [],
            )
            log.debug('concept_added', user=self.user_id, concept=name)
        return self._nodes[topic_id]

    def update_mastery(
        self,
        topic_id: str,
        delta: float,
        correct: bool = True,
    ) -> float:
        """Update mastery for a concept and return the new score.

        Mastery uses an exponential moving average that approaches 1.0
        with repeated correct practice and decays with mistakes.

        Args:
            topic_id: The concept to update.
            delta: Weight of this practice session (0.0 – 0.3).
            correct: Whether the student answered correctly.

        Returns:
            New mastery score (0.0 – 1.0).
        """
        node = self._nodes.get(topic_id)
        if node is None:
            return 0.0

        node.times_practiced += 1
        node.last_practiced_at = time.time()

        if correct:
            node.mastery = min(1.0, node.mastery + delta * (1.0 - node.mastery))
        else:
            node.mistakes_count += 1
            node.mastery = max(0.0, node.mastery - delta * 0.5)

        node.confidence = self._mastery_to_confidence(node.mastery)

        log.debug('mastery_updated', user=self.user_id, concept=node.name,
                  mastery=round(node.mastery, 3), correct=correct)

        self._bus.publish_sync(
            EventType.KNOWLEDGE_GRAPH_UPDATED,
            data={
                'user_id': self.user_id,
                'topic_id': topic_id,
                'concept': node.name,
                'mastery': node.mastery,
                'confidence': node.confidence.value,
            },
            source='knowledge_graph',
        )

        return node.mastery

    def record_mistake(self, topic_id: str, mistake_type: str = 'general') -> None:
        """Record a mistake on a concept."""
        node = self._nodes.get(topic_id)
        if node:
            node.mistakes_count += 1
            node.mastery = max(0.0, node.mastery - 0.05)
            node.confidence = self._mastery_to_confidence(node.mastery)

    def add_prerequisite(self, source: str, target: str, weight: float = 1.0) -> None:
        """Add a prerequisite edge: source → target (source must be learned first)."""
        edge = GraphEdge(source=source, target=target, edge_type=KnowledgeEdgeType.PREREQUISITE, weight=weight)
        self._edges.append(edge)

        if source in self._nodes:
            if target not in self._nodes[source].dependents:
                self._nodes[source].dependents.append(target)
        if target in self._nodes:
            if source not in self._nodes[target].prerequisites:
                self._nodes[target].prerequisites.append(source)

    def add_relationship(
        self,
        source: str,
        target: str,
        edge_type: KnowledgeEdgeType = KnowledgeEdgeType.RELATED,
        weight: float = 1.0,
    ) -> None:
        """Add a generic relationship edge."""
        self._edges.append(GraphEdge(source=source, target=target, edge_type=edge_type, weight=weight))

    # ── Queries ────────────────────────────────────────────────────────

    def get_mastery(self, topic_id: str) -> float:
        """Return mastery score for a concept (0.0 if unknown)."""
        node = self._nodes.get(topic_id)
        return node.mastery if node else 0.0

    def get_confidence(self, topic_id: str) -> ConfidenceLevel:
        node = self._nodes.get(topic_id)
        return node.confidence if node else ConfidenceLevel.VERY_LOW

    def is_mastered(self, topic_id: str) -> bool:
        return self.get_mastery(topic_id) >= MASTERY_THRESHOLD_HIGH

    def is_weak(self, topic_id: str) -> bool:
        return self.get_mastery(topic_id) < MASTERY_THRESHOLD_LOW

    def get_pending_prerequisites(self, topic_id: str) -> list[str]:
        """Return prerequisites that the student has NOT mastered yet."""
        node = self._nodes.get(topic_id)
        if not node:
            return []
        return [p for p in node.prerequisites if not self.is_mastered(p)]

    def snapshot(self) -> GraphSnapshot:
        """Take an immutable snapshot of the current graph state."""
        now = time.time()
        weak: list[str] = []
        strong: list[str] = []
        revision: list[tuple[str, float]] = []

        for tid, node in self._nodes.items():
            if node.mastery >= MASTERY_THRESHOLD_HIGH:
                strong.append(tid)
            elif node.mastery < MASTERY_THRESHOLD_LOW:
                weak.append(tid)

            # Revision priority = (1 - mastery) * recency_factor
            if node.last_practiced_at:
                hours_since = (now - node.last_practiced_at) / 3600
                recency = min(1.0, hours_since / RECENCY_DECAY_HOURS)
            else:
                recency = 1.0  # never practiced → high priority

            priority = (1.0 - node.mastery) * (0.5 + 0.5 * recency) * (1.0 + 0.2 * node.mistakes_count)
            revision.append((tid, round(priority, 3)))

        revision.sort(key=lambda x: x[1], reverse=True)

        total_mastery = sum(n.mastery for n in self._nodes.values()) / max(len(self._nodes), 1)

        return GraphSnapshot(
            nodes=dict(self._nodes),
            edges=list(self._edges),
            weak_concepts=weak,
            strong_concepts=strong,
            revision_priority=revision[:20],
            overall_mastery=round(total_mastery, 3),
        )

    def get_learning_path(self, target_concept: str) -> list[str]:
        """Return an ordered list of concepts to learn before *target_concept*.

        Uses BFS on the prerequisite graph to find the shortest learning path.
        """
        visited: set[str] = set()
        path: list[str] = []

        def dfs(tid: str) -> None:
            if tid in visited:
                return
            visited.add(tid)
            node = self._nodes.get(tid)
            if node:
                for prereq in node.prerequisites:
                    dfs(prereq)
                path.append(tid)

        dfs(target_concept)
        return path

    def load_from_db(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        """Load graph state from database records.

        Args:
            nodes: List of dicts with keys: topic_id, name, subject, mastery,
                   times_practiced, mistakes_count, last_practiced_at.
            edges: List of dicts with keys: source, target, edge_type, weight.
        """
        for n in nodes:
            node = ConceptNode(
                topic_id=n.get('topic_id', n.get('id', '')),
                name=n.get('name', ''),
                subject=Subject(n['subject']) if 'subject' in n else Subject.GENERAL,
                mastery=float(n.get('mastery', 0.0)),
                confidence=self._mastery_to_confidence(float(n.get('mastery', 0.0))),
                times_practiced=int(n.get('times_practiced', 0)),
                mistakes_count=int(n.get('mistakes_count', 0)),
                last_practiced_at=n.get('last_practiced_at'),
            )
            self._nodes[node.topic_id] = node

        for e in edges:
            edge = GraphEdge(
                source=e['source'],
                target=e['target'],
                edge_type=KnowledgeEdgeType(e['edge_type']) if 'edge_type' in e else KnowledgeEdgeType.RELATED,
                weight=float(e.get('weight', 1.0)),
            )
            self._edges.append(edge)

    # ── Serialisation ──────────────────────────────────────────────────

    def to_db_format(self) -> dict[str, Any]:
        """Return the graph state ready for database persistence."""
        return {
            'nodes': [
                {
                    'topic_id': n.topic_id,
                    'name': n.name,
                    'subject': n.subject.value,
                    'mastery': n.mastery,
                    'times_practiced': n.times_practiced,
                    'mistakes_count': n.mistakes_count,
                    'last_practiced_at': n.last_practiced_at,
                }
                for n in self._nodes.values()
            ],
            'edges': [
                {
                    'source': e.source,
                    'target': e.target,
                    'edge_type': e.edge_type.value,
                    'weight': e.weight,
                }
                for e in self._edges
            ],
        }

    def to_repository_format(self) -> dict[str, Any]:
        """Return the graph state formatted for bulk database update.

        Returns a dict with separate :attr:`edges` suitable for passing
        to KnowledgeGraphEdge repository methods.
        """
        base = self.to_db_format()
        base['edges'] = [
            {
                'user_id': self.user_id,
                'source_topic_id': e.source,
                'target_topic_id': e.target,
                'edge_type': e.edge_type,
                'weight': e.weight,
            }
            for e in self._edges
        ]
        return base

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _mastery_to_confidence(mastery: float) -> ConfidenceLevel:
        if mastery >= 0.9:
            return ConfidenceLevel.VERY_HIGH
        elif mastery >= 0.7:
            return ConfidenceLevel.HIGH
        elif mastery >= 0.4:
            return ConfidenceLevel.MEDIUM
        elif mastery >= 0.2:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.VERY_LOW
