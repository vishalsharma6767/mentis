"""Concept Graph Builder — creates a concept dependency graph from
the EducationalSceneGraph.

Maps detected concepts, topics, and subjects into a directed acyclic
graph of prerequisite relationships. Uses a built-in knowledge map
for common subjects and falls back to the AI gateway for novel topics.

The graph determines what the student must understand before the next
lesson and suggests an optimal teaching order via topological sort.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.scene_graph.schemas import (
    ConceptDependencies,
    ConceptEdge,
    ConceptNode,
    Difficulty,
    NodeType,
    Subject,
)
from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


# ── Built-in knowledge maps ──────────────────────────────────────────────
# Subject → topic → prerequisite chain (deepest → most basic)

KNOWLEDGE_MAPS: dict[str, dict[str, list[str]]] = {
    'mathematics': {
        'trigonometry': ['right_triangle', 'pythagoras', 'sine', 'cosine', 'tangent',
                         'angles', 'degrees_radians', 'unit_circle'],
        'calculus': ['limits', 'derivatives', 'integrals', 'functions', 'algebra'],
        'algebra': ['variables', 'expressions', 'equations', 'linear_equations',
                    'quadratic_equations', 'polynomials', 'factorization'],
        'geometry': ['points', 'lines', 'angles', 'triangles', 'circles',
                     'coordinate_geometry', 'congruence', 'similarity'],
        'statistics': ['data_collection', 'mean_median_mode', 'probability',
                       'distributions', 'standard_deviation'],
        'coordinate_geometry': ['cartesian_plane', 'points', 'lines', 'slope',
                                'distance_formula', 'section_formula'],
        'quadratic_equations': ['algebra', 'factorization', 'discriminant',
                                'quadratic_formula', 'completing_square'],
    },
    'physics': {
        'mechanics': ['kinematics', 'newtons_laws', 'forces', 'energy', 'momentum',
                      'vectors', 'calculus'],
        'kinematics': ['displacement', 'velocity', 'acceleration', 'equations_of_motion',
                       'vectors', 'graphs'],
        'optics': ['reflection', 'refraction', 'lenses', 'mirrors', 'light',
                   'snells_law', 'critical_angle'],
        'electricity': ['charge', 'current', 'voltage', 'resistance', 'ohms_law',
                        'circuits', 'power', 'electromagnetism'],
        'thermodynamics': ['temperature', 'heat', 'laws_of_thermodynamics', 'entropy',
                           'specific_heat', 'calorimetry'],
    },
    'chemistry': {
        'organic_chemistry': ['hydrocarbons', 'functional_groups', 'isomerism',
                              'reactions', 'bonding', 'hybridization'],
        'inorganic_chemistry': ['periodic_table', 'atomic_structure', 'chemical_bonding',
                                'coordination_compounds', 'metallurgy'],
        'physical_chemistry': ['mole_concept', 'thermodynamics', 'chemical_kinetics',
                               'equilibrium', 'electrochemistry', 'solutions'],
        'chemical_bonding': ['octet_rule', 'ionic_bond', 'covalent_bond',
                             'metallic_bond', 'hybridization', 'molecular_orbital'],
        'mole_concept': ['atomic_mass', 'molecular_mass', 'avogadro_number',
                         'stoichiometry', 'concentration'],
    },
    'biology': {
        'cell_biology': ['cell_theory', 'cell_structure', 'cell_division',
                         'mitosis', 'meiosis', 'organelles'],
        'genetics': ['dna', 'genes', 'chromosomes', 'inheritance', 'mendel_laws',
                     'genetic_disorders'],
        'human_physiology': ['digestive_system', 'respiratory_system', 'circulatory_system',
                             'nervous_system', 'excretory_system'],
        'plant_biology': ['photosynthesis', 'plant_anatomy', 'reproduction',
                          'transport_plants', 'growth'],
        'ecology': ['ecosystem', 'food_chain', 'biodiversity', 'conservation',
                    'biogeochemical_cycles'],
    },
    'programming': {
        'python_basics': ['variables', 'data_types', 'control_flow', 'functions',
                          'lists', 'strings', 'loops'],
        'data_structures': ['arrays', 'linked_lists', 'stacks', 'queues', 'trees',
                            'graphs', 'hash_tables'],
        'algorithms': ['sorting', 'searching', 'recursion', 'dynamic_programming',
                       'greedy_algorithms', 'graph_algorithms'],
        'oop': ['classes', 'objects', 'inheritance', 'polymorphism', 'encapsulation',
                'abstraction'],
        'web_development': ['html', 'css', 'javascript', 'http', 'apis', 'databases'],
    },
}


class ConceptGraphBuilder:
    """Builds concept dependency graphs from detected topics."""

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    def build(self, subject: str, topic: str, concepts: list[str],
              scene_graph_node_types: Optional[dict[str, list[str]]] = None) -> ConceptDependencies:
        """Build a concept dependency graph for the given subject/topic.

        Args:
            subject: The detected subject ('mathematics', 'physics', etc.)
            topic: The detected topic ('trigonometry', 'mechanics', etc.)
            concepts: Additional detected concepts from the scene.
            scene_graph_node_types: Optional dict mapping node types to
                a list of their textual labels for enrichment.

        Returns:
            A ConceptDependencies with nodes, edges, missing prereqs,
            and a recommended topological teaching order.
        """
        subject_key = subject.lower() if isinstance(subject, str) else subject.value.lower()
        topic_key = topic.lower().replace(' ', '_') if topic else ''

        # 1. Get knowledge map for this subject
        subject_map = KNOWLEDGE_MAPS.get(subject_key, {})
        topic_prereqs = subject_map.get(topic_key, [])

        # 2. Build nodes
        nodes: dict[str, ConceptNode] = {}
        edges: list[ConceptEdge] = []

        # Add topic itself
        if topic:
            nodes[topic_key] = ConceptNode(
                id=topic_key,
                name=topic,
                subject=subject_key,
                is_current_focus=True,
                confidence=0.8,
            )

        # Add prerequisites
        for prereq in topic_prereqs:
            prereq_id = prereq.lower().replace(' ', '_')
            nodes[prereq_id] = ConceptNode(
                id=prereq_id,
                name=prereq.replace('_', ' ').title(),
                subject=subject_key,
                is_prerequisite=True,
                confidence=0.7,
            )

        # Add detected concepts
        for concept in concepts:
            cid = concept.lower().replace(' ', '_')
            if cid not in nodes:
                nodes[cid] = ConceptNode(
                    id=cid,
                    name=concept,
                    subject=subject_key,
                    confidence=0.6,
                )

        # 3. Build edges from knowledge map
        if topic_key in subject_map:
            prereqs = subject_map[topic_key]
            prev_id = topic_key
            for prereq in reversed(prereqs):
                prereq_id = prereq.lower().replace(' ', '_')
                if prereq_id in nodes and prev_id in nodes:
                    edges.append(ConceptEdge(
                        source_id=prereq_id,
                        target_id=prev_id,
                        relationship='builds_on',
                        weight=0.9,
                        confidence=0.8,
                    ))
                    prev_id = prereq_id

        # 4. Cross-link concepts (builds_on edges between related concepts)
        self._cross_link_concepts(nodes, edges, subject_key)

        # 5. Determine topological teaching order
        recommended_path = self._topological_order(nodes, edges, topic_key)

        # 6. Identify missing prerequisites
        missing_prereqs = self._find_missing_prereqs(nodes, edges, topic_key)

        return ConceptDependencies(
            topic=topic,
            subject=subject_key,
            nodes=list(nodes.values()),
            edges=edges,
            missing_prerequisites=missing_prereqs,
            recommended_path=recommended_path,
        )

    def _cross_link_concepts(self, nodes: dict[str, ConceptNode],
                              edges: list[ConceptEdge],
                              subject: str) -> None:
        """Add edges between related concepts."""
        subject_map = KNOWLEDGE_MAPS.get(subject, {})
        for topic_name, prereqs in subject_map.items():
            mapped_prereqs = [p.lower().replace(' ', '_') for p in prereqs]
            for i in range(len(mapped_prereqs) - 1):
                src = mapped_prereqs[i]
                tgt = mapped_prereqs[i + 1]
                if src in nodes and tgt in nodes:
                    if not any(e.source_id == src and e.target_id == tgt for e in edges):
                        edges.append(ConceptEdge(
                            source_id=src,
                            target_id=tgt,
                            relationship='builds_on',
                            weight=0.7,
                            confidence=0.6,
                        ))

    def _topological_order(self, nodes: dict[str, ConceptNode],
                           edges: list[ConceptEdge],
                           topic_key: str) -> list[str]:
        """Return a teaching order by walking prerequisite chains."""
        if not nodes:
            return []
        # Build adjacency
        in_degree: dict[str, int] = {nid: 0 for nid in nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in nodes}
        for edge in edges:
            if edge.source_id in adjacency:
                adjacency[edge.source_id].append(edge.target_id)
                in_degree[edge.target_id] = in_degree.get(edge.target_id, 0) + 1

        # Kahn's algorithm
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        ordered: list[str] = []
        while queue:
            queue.sort(key=lambda x: (x != topic_key, x))
            nid = queue.pop(0)
            ordered.append(nid)
            for neighbor in adjacency.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        remaining = [n for n in nodes if n not in ordered]
        ordered.extend(remaining)
        return ordered

    def _find_missing_prereqs(self, nodes: dict[str, ConceptNode],
                               edges: list[ConceptEdge],
                               topic_key: str) -> list[str]:
        """Identify prerequisites that are important but have low mastery."""
        missing: list[str] = []
        for node in nodes.values():
            if node.is_prerequisite and node.mastery < 0.3:
                # Check if it's a direct prerequisite of the topic or nearby concept
                for edge in edges:
                    if edge.target_id == topic_key and edge.source_id == node.id:
                        missing.append(node.name)
                        break
        return missing

    def update_mastery(self, deps: ConceptDependencies, concept_id: str,
                       mastery_delta: float = 0.2) -> None:
        """Update mastery for a concept node (for incremental learning)."""
        for node in deps.nodes:
            if node.id == concept_id:
                node.mastery = min(1.0, max(0.0, node.mastery + mastery_delta))
                logger.debug('Updated mastery for %s: %.2f', concept_id, node.mastery)
                return
        logger.warning('Concept %s not found in dependencies', concept_id)

    def enrich_from_scene(self, deps: ConceptDependencies,
                          scene_types: Optional[dict[str, list[str]]]) -> None:
        """Add concepts detected in the scene to the dependency graph."""
        if not scene_types:
            return
        for node_type, labels in scene_types.items():
            for label in labels:
                cid = label.lower().replace(' ', '_')
                if not any(n.id == cid for n in deps.nodes):
                    deps.nodes.append(ConceptNode(
                        id=cid,
                        name=label,
                        subject=deps.subject,
                        confidence=0.5,
                    ))
                    logger.debug('Enriched concept graph with: %s', label)

    def get_subject_map(self, subject: str) -> dict[str, list[str]]:
        """Return the knowledge map for a subject."""
        return KNOWLEDGE_MAPS.get(subject.lower(), {})

    def has_topic(self, subject: str, topic: str) -> bool:
        """Check if a topic is in the knowledge map."""
        subject_map = KNOWLEDGE_MAPS.get(subject.lower(), {})
        return topic.lower().replace(' ', '_') in subject_map
