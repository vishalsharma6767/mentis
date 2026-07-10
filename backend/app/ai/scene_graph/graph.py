"""Core SceneGraph data structure backed by NetworkX.

Provides a clean domain interface over NetworkX while keeping the
internal graph model separate from the schema objects. Supports
incremental updates, topological traversal, and subgraph extraction.
"""

from __future__ import annotations

import logging
import time
from copy import deepcopy
from typing import Any, Optional

import networkx as nx

from app.ai.scene_graph.relationships import get_semantics, is_valid_edge
from app.ai.scene_graph.schemas import (
    EdgeType,
    NodeType,
    SceneEdge,
    SceneGraph,
    SceneGraphMetadata,
    SceneNode,
)

logger = logging.getLogger(__name__)


class EducationalSceneGraph:
    """Mutable, NetworkX-backed educational scene graph.

    Provides graph algorithms (topological sort, subgraph extraction,
    path finding) on top of the schema-defined node/edge types.
    """

    def __init__(self, scene_graph: Optional[SceneGraph] = None) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.metadata: SceneGraphMetadata = SceneGraphMetadata()
        self.root_node_ids: list[str] = []
        self._explicit_nodes: set[str] = set()

        if scene_graph is not None:
            self._from_schema(scene_graph)

    # ── Construction ──────────────────────────────────────────────────────

    def _from_schema(self, sg: SceneGraph) -> None:
        self._graph.clear()
        self._explicit_nodes.clear()
        for node in sg.nodes:
            self.add_node(node)
        for edge in sg.edges:
            self.add_edge(edge)
        self.root_node_ids = list(sg.root_node_ids)
        self.metadata = sg.metadata
        logger.debug('Loaded SceneGraph with %d nodes, %d edges', self.node_count, self.edge_count)

    def to_schema(self) -> SceneGraph:
        nodes = self._collect_nodes()
        edges = self._collect_edges()
        self.metadata.node_count = len(nodes)
        self.metadata.edge_count = len(edges)
        return SceneGraph(
            nodes=nodes,
            edges=edges,
            root_node_ids=list(self.root_node_ids),
            metadata=self.metadata,
        )

    def _collect_nodes(self) -> list[SceneNode]:
        result: list[SceneNode] = []
        for nid, data in self._graph.nodes(data=True):
            result.append(SceneNode(
                id=nid,
                type=data.get('type', NodeType.CONCEPT),
                label=data.get('label', nid),
                content=data.get('content', ''),
                confidence=data.get('confidence', 0.5),
                data=data.get('data', {}),
                metadata=data.get('metadata', {}),
            ))
        return result

    def _collect_edges(self) -> list[SceneEdge]:
        result: list[SceneEdge] = []
        for u, v, key, data in self._graph.edges(data=True, keys=True):
            result.append(SceneEdge(
                source_id=u,
                target_id=v,
                type=data.get('type', EdgeType.RELATED_TO_CONCEPT),
                label=data.get('label', ''),
                confidence=data.get('confidence', 0.5),
                metadata=data.get('metadata', {}),
            ))
        return result

    # ── Node operations ──────────────────────────────────────────────────

    def add_node(self, node: SceneNode) -> None:
        if node.id in self._graph:
            logger.debug('Node %s already exists, updating', node.id)
        self._graph.add_node(
            node.id,
            type=node.type,
            label=node.label,
            content=node.content,
            confidence=node.confidence,
            data=deepcopy(node.data),
            metadata=deepcopy(node.metadata),
        )
        self._explicit_nodes.add(node.id)

    def get_node(self, node_id: str) -> Optional[SceneNode]:
        if node_id not in self._graph:
            return None
        data = self._graph.nodes[node_id]
        return SceneNode(
            id=node_id,
            type=data.get('type', NodeType.CONCEPT),
            label=data.get('label', node_id),
            content=data.get('content', ''),
            confidence=data.get('confidence', 0.5),
            data=deepcopy(data.get('data', {})),
            metadata=deepcopy(data.get('metadata', {})),
        )

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self._graph:
            return False
        self._graph.remove_node(node_id)
        self._explicit_nodes.discard(node_id)
        self.root_node_ids = [r for r in self.root_node_ids if r != node_id]
        return True

    def has_node(self, node_id: str) -> bool:
        return node_id in self._graph

    def update_node(self, node_id: str, **updates: Any) -> bool:
        if node_id not in self._graph:
            return False
        for key, value in updates.items():
            if key in ('type', 'label', 'content', 'confidence'):
                self._graph.nodes[node_id][key] = value
            elif key == 'data':
                self._graph.nodes[node_id]['data'].update(value)
            elif key == 'metadata':
                self._graph.nodes[node_id]['metadata'].update(value)
        return True

    # ── Edge operations ──────────────────────────────────────────────────

    def add_edge(self, edge: SceneEdge) -> bool:
        if not is_valid_edge(self._node_type(edge.source_id), edge.type, self._node_type(edge.target_id)):
            logger.warning('Invalid edge %s -- %s -- %s', edge.source_id, edge.type, edge.target_id)
            return False
        self._graph.add_edge(
            edge.source_id,
            edge.target_id,
            type=edge.type,
            label=edge.label or edge.type.value,
            confidence=edge.confidence,
            metadata=deepcopy(edge.metadata),
        )
        return True

    def remove_edge(self, source_id: str, target_id: str, edge_type: Optional[EdgeType] = None) -> bool:
        edges_to_remove = list(self._graph.edges(source_id, target_id, keys=True))
        removed = False
        for u, v, key, data in edges_to_remove:
            if edge_type is None or data.get('type') == edge_type:
                self._graph.remove_edge(u, v, key=key)
                removed = True
        return removed

    def get_edges(self, node_id: Optional[str] = None, edge_type: Optional[EdgeType] = None) -> list[SceneEdge]:
        result: list[SceneEdge] = []
        for u, v, data in self._graph.edges(data=True):
            if node_id is not None and u != node_id and v != node_id:
                continue
            if edge_type is not None and data.get('type') != edge_type:
                continue
            result.append(SceneEdge(
                source_id=u,
                target_id=v,
                type=data.get('type', EdgeType.RELATED_TO_CONCEPT),
                label=data.get('label', ''),
                confidence=data.get('confidence', 0.5),
                metadata=deepcopy(data.get('metadata', {})),
            ))
        return result

    # ── Query operations ─────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    def nodes_by_type(self, node_type: NodeType) -> list[SceneNode]:
        result: list[SceneNode] = []
        for nid, data in self._graph.nodes(data=True):
            if data.get('type') == node_type:
                result.append(self.get_node(nid))  # type: ignore[arg-type]
        return result

    def children(self, node_id: str) -> list[SceneNode]:
        children_ids = set()
        for _, v, data in self._graph.out_edges(node_id, data=True):
            if data.get('type') in (EdgeType.CONTAINS, EdgeType.HAS_ANSWER, EdgeType.HAS_DIAGRAM,
                                    EdgeType.HAS_FORMULA, EdgeType.NEXT_STEP, EdgeType.FOLLOWS):
                children_ids.add(v)
        return [self.get_node(cid) for cid in children_ids if self.get_node(cid) is not None]  # type: ignore[misc]

    def parents(self, node_id: str) -> list[SceneNode]:
        parent_ids = set()
        for u, _, data in self._graph.in_edges(node_id, data=True):
            if data.get('type') in (EdgeType.CONTAINS, EdgeType.HAS_ANSWER, EdgeType.HAS_DIAGRAM,
                                    EdgeType.HAS_FORMULA, EdgeType.NEXT_STEP, EdgeType.FOLLOWS):
                parent_ids.add(u)
        return [self.get_node(pid) for pid in parent_ids if self.get_node(pid) is not None]  # type: ignore[misc]

    def successors(self, node_id: str) -> list[SceneNode]:
        succ_ids = set()
        for _, v in self._graph.successors(node_id):
            succ_ids.add(v)
        return [self.get_node(sid) for sid in succ_ids if self.get_node(sid) is not None]  # type: ignore[misc]

    def predecessors(self, node_id: str) -> list[SceneNode]:
        pred_ids = set()
        for u in self._graph.predecessors(node_id):
            pred_ids.add(u)
        return [self.get_node(pid) for pid in pred_ids if self.get_node(pid) is not None]  # type: ignore[misc]

    # ── Graph algorithms ─────────────────────────────────────────────────

    def topological_sort(self) -> list[SceneNode]:
        try:
            ordered = list(nx.topological_sort(self._graph))
            return [self.get_node(nid) for nid in ordered if self.get_node(nid) is not None]  # type: ignore[misc]
        except nx.NetworkXUnfeasible:
            logger.warning('Graph has a cycle — cannot topological sort')
            return self._collect_nodes()

    def has_path(self, source_id: str, target_id: str) -> bool:
        return nx.has_path(self._graph, source_id, target_id)

    def shortest_path(self, source_id: str, target_id: str) -> list[SceneNode]:
        try:
            path = nx.shortest_path(self._graph, source_id, target_id)
            return [self.get_node(nid) for nid in path if self.get_node(nid) is not None]  # type: ignore[misc]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def subgraph(self, node_ids: list[str]) -> EducationalSceneGraph:
        sub = nx.induced_subgraph(self._graph, node_ids)
        result = EducationalSceneGraph()
        result._graph = sub  # type: ignore[assignment]
        result.root_node_ids = [r for r in self.root_node_ids if r in node_ids]
        result.metadata = deepcopy(self.metadata)
        return result

    def get_roots(self) -> list[SceneNode]:
        roots = []
        for nid in self.root_node_ids:
            node = self.get_node(nid)
            if node:
                roots.append(node)
        if not roots:
            for nid, data in self._graph.nodes(data=True):
                if self._graph.in_degree(nid) == 0:
                    roots.append(self.get_node(nid))  # type: ignore[arg-type]
        return roots

    def find_mistake_path(self) -> list[SceneEdge]:
        mistake_types = {EdgeType.INCORRECT_STEP, EdgeType.HAS_MISTAKE}
        return self.get_edges(edge_type=next(iter(mistake_types))) if mistake_types else []

    # ── Serialization ────────────────────────────────────────────────────

    def to_serializable(self) -> dict[str, Any]:
        return self.to_schema().to_serializable()

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_serializable(), indent=indent, ensure_ascii=False)

    # ── Cache support ────────────────────────────────────────────────────

    def cache_key(self) -> str:
        import hashlib
        raw = f'{self.node_count}-{self.edge_count}-{sorted(self.root_node_ids)}'
        return hashlib.md5(raw.encode()).hexdigest()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _node_type(self, node_id: str) -> NodeType:
        data = self._graph.nodes.get(node_id)
        if data is None:
            return NodeType.CONCEPT
        return data.get('type', NodeType.CONCEPT)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._graph

    def __len__(self) -> int:
        return self.node_count

    def __repr__(self) -> str:
        return f'<EducationalSceneGraph nodes={self.node_count} edges={self.edge_count}>'
