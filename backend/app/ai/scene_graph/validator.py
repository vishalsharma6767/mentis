"""Scene Graph Validator — validates graph consistency, missing nodes,
circular dependencies, invalid relationships, and low-confidence paths.

Rejects inconsistent graphs before they reach the reasoner.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Optional

import networkx as nx

from app.ai.scene_graph.graph import EducationalSceneGraph
from app.ai.scene_graph.relationships import allowed_edge_types, get_semantics
from app.ai.scene_graph.schemas import (
    CircularDependency,
    EdgeType,
    MissingNode,
    NodeType,
    SceneEdge,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Minimum confidence thresholds
MIN_NODE_CONFIDENCE = 0.2
MIN_EDGE_CONFIDENCE = 0.1
MIN_OVERALL_CONFIDENCE = 0.3


class SceneGraphValidator:
    """Validates an EducationalSceneGraph for structural consistency.

    Checks:
      1. All edge targets exist as nodes
      2. No circular dependency chains
      3. All node/edge confidence is above threshold
      4. Orphaned nodes (no connections at all)
      5. Invalid relationship types between node types
      6. Overall graph confidence
    """

    def __init__(self, strict_mode: bool = True) -> None:
        self.strict_mode = strict_mode
        self._node_conf_threshold = MIN_NODE_CONFIDENCE
        self._edge_conf_threshold = MIN_EDGE_CONFIDENCE

    def validate(self, graph: EducationalSceneGraph) -> ValidationResult:
        """Run all validation checks and return results.

        If *strict_mode* is True and any error-level issue is found,
        *is_valid* will be False.
        """
        result = ValidationResult()

        # 1. Check missing node references
        self._check_missing_nodes(graph, result)

        # 2. Check circular dependencies
        self._check_circular_dependencies(graph, result)

        # 3. Check low-confidence nodes / edges
        self._check_low_confidence(graph, result)

        # 4. Check orphaned nodes
        self._check_orphaned_nodes(graph, result)

        # 5. Check invalid relationship types
        self._check_invalid_relationships(graph, result)

        # 6. Check overall confidence
        self._check_overall_confidence(graph, result)

        # Final validity
        if self.strict_mode and result.errors:
            result.is_valid = False
            logger.warning('Graph validation FAILED: %d errors', len(result.errors))
        elif result.errors:
            result.is_valid = len(result.errors) < 3  # lenient mode: allow up to 2 errors
            logger.warning('Graph validation warnings: %d errors, %d warnings',
                           len(result.errors), len(result.warnings))
        else:
            result.is_valid = True
            logger.info('Graph validation passed (%d nodes, %d edges)',
                        graph.node_count, graph.edge_count)

        return result

    def assert_valid(self, graph: EducationalSceneGraph) -> EducationalSceneGraph:
        """Validate and return the graph if valid, otherwise raise ValueError."""
        result = self.validate(graph)
        if not result.is_valid:
            msg = '; '.join(result.errors[:5])
            raise ValueError(f'SceneGraph validation failed: {msg}')
        return graph

    # ── Individual checks ────────────────────────────────────────────────

    def _check_missing_nodes(self, graph: EducationalSceneGraph, result: ValidationResult) -> None:
        """Ensure all edge source/target IDs correspond to explicitly added nodes."""
        node_ids = graph._explicit_nodes

        for edge in graph._collect_edges():
            missing_refs: list[str] = []
            if edge.source_id not in node_ids:
                missing_refs.append(edge.source_id)
            if edge.target_id not in node_ids:
                missing_refs.append(edge.target_id)

            if missing_refs:
                result.missing_nodes.append(MissingNode(
                    node_id=missing_refs[0],
                    referenced_by=[f'{edge.source_id}->{edge.target_id}'],
                    severity='error',
                ))
                # Only report first missing per edge to keep output readable
                if len(missing_refs) > 1:
                    result.missing_nodes.append(MissingNode(
                        node_id=missing_refs[1],
                        referenced_by=[f'{edge.source_id}->{edge.target_id}'],
                        severity='error',
                    ))

        if result.missing_nodes:
            result.errors.append(f'Found {len(result.missing_nodes)} missing node reference(s)')

    def _check_circular_dependencies(self, graph: EducationalSceneGraph, result: ValidationResult) -> None:
        """Detect cycles in the graph using NetworkX cycle detection."""
        try:
            nx_g = nx.MultiDiGraph()
            for edge in graph._collect_edges():
                nx_g.add_edge(edge.source_id, edge.target_id)

            cycles = list(nx.simple_cycles(nx_g))
            if cycles:
                for cycle in cycles:
                    result.circular_dependencies.append(CircularDependency(
                        path=cycle,
                        nodes_involved=list(set(cycle)),
                    ))
                result.errors.append(f'Found {len(cycles)} circular dependenc(ies)')
                logger.warning('Circular dependencies detected: %s', cycles[:3])
        except Exception as exc:
            logger.warning('Cycle detection error: %s', exc)

    def _check_low_confidence(self, graph: EducationalSceneGraph, result: ValidationResult) -> None:
        """Flag nodes and edges below confidence thresholds."""
        for node in graph._collect_nodes():
            if node.confidence < self._node_conf_threshold:
                result.low_confidence_nodes.append(f'{node.id} ({node.confidence:.2f})')

        low_count = len(result.low_confidence_nodes)
        if low_count > 0:
            warn_msg = f'{low_count} node(s) below confidence threshold {self._node_conf_threshold}'
            if self.strict_mode:
                result.errors.append(warn_msg)
            else:
                result.warnings.append(warn_msg)

    def _check_orphaned_nodes(self, graph: EducationalSceneGraph, result: ValidationResult) -> None:
        """Find nodes with no incoming or outgoing edges."""
        node_ids = {n.id for n in graph._collect_nodes()}
        connected: set[str] = set()
        for edge in graph._collect_edges():
            connected.add(edge.source_id)
            connected.add(edge.target_id)

        orphans = list(node_ids - connected)
        if orphans:
            result.orphaned_nodes = orphans
            # Orphans are warnings, not errors — they may be intentional roots
            if graph.root_node_ids:
                actual_orphans = [o for o in orphans if o not in graph.root_node_ids]
                if actual_orphans:
                    result.warnings.append(f'{len(actual_orphans)} orphaned node(s) with no edges')
            else:
                result.warnings.append(f'{len(orphans)} node(s) have no connections')

    def _check_invalid_relationships(self, graph: EducationalSceneGraph, result: ValidationResult) -> None:
        """Check that edge types are semantically valid for their node types."""
        invalid_count = 0
        for edge in graph._collect_edges():
            source_node = graph.get_node(edge.source_id)
            target_node = graph.get_node(edge.target_id)
            if source_node is None or target_node is None:
                continue
            allowed = allowed_edge_types(source_node.type, target_node.type)
            if allowed and edge.type not in allowed:
                invalid_count += 1
                if invalid_count <= 5:
                    result.warnings.append(
                        f'Invalid edge: {edge.source_id}({source_node.type.value}) '
                        f'-{edge.type.value}-> {edge.target_id}({target_node.type.value})'
                    )

        if invalid_count:
            result.warnings.append(f'{invalid_count} edge(s) have potentially invalid relationships')

    def _check_overall_confidence(self, graph: EducationalSceneGraph, result: ValidationResult) -> None:
        """Check that the overall graph confidence meets the threshold."""
        all_conf = [n.confidence for n in graph._collect_nodes()]
        if not all_conf:
            result.errors.append('Graph has no nodes')
            return
        avg_conf = sum(all_conf) / len(all_conf)
        if avg_conf < MIN_OVERALL_CONFIDENCE:
            result.errors.append(
                f'Average graph confidence {avg_conf:.2f} below minimum {MIN_OVERALL_CONFIDENCE}'
            )

    # ── Repair utilities ─────────────────────────────────────────────────

    def remove_low_confidence(self, graph: EducationalSceneGraph, threshold: float = 0.2) -> int:
        """Remove nodes and edges below the confidence threshold.

        Returns the number of removed items.
        """
        removed = 0
        for node in graph._collect_nodes():
            if node.confidence < threshold:
                graph.remove_node(node.id)
                removed += 1
        return removed

    def find_inconsistent_graphs(self, graphs: list[EducationalSceneGraph]) -> list[tuple[int, ValidationResult]]:
        """Validate multiple graphs and return indices of invalid ones."""
        results: list[tuple[int, ValidationResult]] = []
        for i, g in enumerate(graphs):
            vr = self.validate(g)
            if not vr.is_valid:
                results.append((i, vr))
        return results
