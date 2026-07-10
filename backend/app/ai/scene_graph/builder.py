"""Scene Graph Builder — converts EducationalScene into EducationalSceneGraph.

The builder walks the structured output of the Vision Intelligence Engine
(an EducationalScene) and creates a rich semantic graph where every detected
element becomes a typed node connected by meaningful edges.

No raw OCR text leaks into the graph — only structured nodes.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from app.ai.scene_graph.graph import EducationalSceneGraph
from app.ai.scene_graph.schemas import (
    EdgeType,
    NodeType,
    SceneEdge,
    SceneGraphMetadata,
    SceneNode,
)
from app.ai.vision_intelligence.schema import (
    DetectedMistake,
    Diagram,
    EducationalScene,
    Formula,
    Graph,
    Question,
    TextBlock,
)

logger = logging.getLogger(__name__)


class SceneGraphBuilder:
    """Builds an EducationalSceneGraph from an EducationalScene.

    Usage:
        builder = SceneGraphBuilder()
        graph = builder.build(scene)
        teaching_decisions = reasoner.process(graph)
    """

    def __init__(self) -> None:
        self._node_counter: dict[str, int] = {}

    def build(self, scene: EducationalScene, scene_id: str = '') -> EducationalSceneGraph:
        """Convert an EducationalScene into a fully connected SceneGraph."""
        start = time.perf_counter()
        graph = EducationalSceneGraph()
        graph.metadata.source_scene_id = scene_id or id(scene).__str__()
        graph.metadata.vision_confidence = scene.confidence.overall

        self._reset_counters()

        # 1. Create concept / topic nodes
        concept_nodes = self._build_concept_nodes(scene)
        for cn in concept_nodes:
            graph.add_node(cn)

        # 2. Create question nodes and sub-question trees
        question_roots = self._build_question_nodes(scene, graph)
        graph.root_node_ids.extend(question_roots)

        # 3. Create formula nodes
        self._build_formula_nodes(scene, graph)

        # 4. Create diagram nodes
        self._build_diagram_nodes(scene, graph)

        # 5. Create graph nodes
        self._build_graph_nodes(scene, graph)

        # 6. Create table nodes
        self._build_table_nodes(scene, graph)

        # 7. Create text block nodes (non-question text)
        self._build_text_block_nodes(scene, graph)

        # 8. Create mistake nodes
        self._build_mistake_nodes(scene, graph, question_roots)

        # 9. Connect concepts to questions
        self._connect_concepts(scene, graph, concept_nodes)

        # Finalize metadata
        elapsed = int((time.perf_counter() - start) * 1000)
        graph.metadata.processing_time_ms = elapsed
        graph.metadata.node_count = graph.node_count
        graph.metadata.edge_count = graph.edge_count
        graph.metadata.models_used = scene.metadata.models_used
        graph.metadata.cache_hit = scene.metadata.cache_hit

        logger.info(
            'Built SceneGraph in %dms: %d nodes, %d edges, %d roots',
            elapsed, graph.node_count, graph.edge_count, len(graph.root_node_ids),
        )
        return graph

    # ── Internal builders ────────────────────────────────────────────────

    def _reset_counters(self) -> None:
        self._node_counter = {}

    def _next_id(self, prefix: str) -> str:
        self._node_counter[prefix] = self._node_counter.get(prefix, 0) + 1
        return f'{prefix}_{self._node_counter[prefix]}'

    def _build_concept_nodes(self, scene: EducationalScene) -> list[SceneNode]:
        nodes: list[SceneNode] = []
        seen: set[str] = set()

        for concept in scene.concepts:
            key = concept.lower().strip()
            if key and key not in seen:
                seen.add(key)
                nodes.append(SceneNode(
                    id=f'c_{key.replace(" ", "_")}',
                    type=NodeType.CONCEPT,
                    label=concept,
                    content=concept,
                    confidence=scene.confidence.classification,
                ))

        if scene.topic and scene.topic.lower().strip() not in seen:
            key = scene.topic.lower().strip()
            nodes.append(SceneNode(
                id=f'c_{key.replace(" ", "_")}',
                type=NodeType.CONCEPT,
                label=scene.topic,
                content=scene.topic,
                confidence=scene.confidence.classification,
            ))

        return nodes

    def _build_question_nodes(self, scene: EducationalScene, graph: EducationalSceneGraph) -> list[str]:
        roots: list[str] = []
        for i, q in enumerate(scene.questions):
            q_id = f'q_{i + 1}'
            self._add_question_node(graph, q, q_id)
            roots.append(q_id)
        return roots

    def _add_question_node(self, graph: EducationalSceneGraph, q: Question, q_id: str) -> None:
        graph.add_node(SceneNode(
            id=q_id,
            type=NodeType.QUESTION,
            label=q.question_text[:80] or f'Question {q_id}',
            content=q.question_text,
            confidence=q.confidence,
            data={'step_number': q.step_number, 'is_complete': q.is_complete},
        ))

        if q.student_answer:
            ans_id = f'{q_id}_ans'
            graph.add_node(SceneNode(
                id=ans_id,
                type=NodeType.STUDENT_ANSWER,
                label=q.student_answer[:80],
                content=q.student_answer,
                confidence=q.confidence * 0.9,
            ))
            graph.add_edge(SceneEdge(
                source_id=q_id,
                target_id=ans_id,
                type=EdgeType.HAS_ANSWER,
                confidence=q.confidence,
            ))

        for j, sub_q in enumerate(q.sub_questions):
            sub_id = f'{q_id}_sub_{j + 1}'
            self._add_question_node(graph, sub_q, sub_id)
            graph.add_edge(SceneEdge(
                source_id=q_id,
                target_id=sub_id,
                type=EdgeType.CONTAINS,
                confidence=sub_q.confidence,
            ))

        for mistake in q.mistakes:
            self._add_mistake_from_question(graph, mistake, q_id)

    def _build_formula_nodes(self, scene: EducationalScene, graph: EducationalSceneGraph) -> None:
        for i, f in enumerate(scene.formulas):
            f_id = f'f_{i + 1}'
            graph.add_node(SceneNode(
                id=f_id,
                type=NodeType.FORMULA,
                label=f.plain_text[:60] or f.latex[:60],
                content=f.latex or f.plain_text,
                confidence=f.confidence,
                data={
                    'latex': f.latex,
                    'formula_type': f.formula_type.value,
                    'symbols': f.symbols,
                    'is_handwritten': f.is_handwritten,
                },
            ))

            # Link to parent question by proximity
            parent_q = self._find_parent_question(scene, f.bbox.x, f.bbox.y)
            if parent_q:
                graph.add_edge(SceneEdge(
                    source_id=parent_q,
                    target_id=f_id,
                    type=EdgeType.HAS_FORMULA,
                    confidence=f.confidence,
                ))

    def _build_diagram_nodes(self, scene: EducationalScene, graph: EducationalSceneGraph) -> None:
        for i, d in enumerate(scene.diagrams):
            d_id = f'd_{i + 1}'
            graph.add_node(SceneNode(
                id=d_id,
                type=NodeType.DIAGRAM,
                label=d.description[:80] or d.diagram_type.value,
                content=d.description,
                confidence=d.confidence,
                data={
                    'diagram_type': d.diagram_type.value,
                    'labels': d.labels,
                    'shapes': d.shapes_detected,
                },
            ))

            parent_q = self._find_parent_question(scene, d.bbox.x, d.bbox.y)
            if parent_q:
                graph.add_edge(SceneEdge(
                    source_id=parent_q,
                    target_id=d_id,
                    type=EdgeType.HAS_DIAGRAM,
                    confidence=d.confidence,
                ))

    def _build_graph_nodes(self, scene: EducationalScene, graph: EducationalSceneGraph) -> None:
        for i, g in enumerate(scene.graphs):
            g_id = f'g_{i + 1}'
            graph.add_node(SceneNode(
                id=g_id,
                type=NodeType.GRAPH,
                label=g.title or f'Graph {i + 1}',
                content=g.trend_description,
                confidence=g.confidence,
                data={
                    'x_label': g.x_label,
                    'y_label': g.y_label,
                    'is_linear': g.is_linear,
                    'x_range': [g.x_min, g.x_max],
                    'y_range': [g.y_min, g.y_max],
                },
            ))

            parent_q = self._find_parent_question(scene, g.bbox.x, g.bbox.y)
            if parent_q:
                graph.add_edge(SceneEdge(
                    source_id=parent_q,
                    target_id=g_id,
                    type=EdgeType.HAS_DIAGRAM,
                    confidence=g.confidence,
                ))

    def _build_table_nodes(self, scene: EducationalScene, graph: EducationalSceneGraph) -> None:
        for i, t in enumerate(scene.tables):
            t_id = f't_{i + 1}'
            graph.add_node(SceneNode(
                id=t_id,
                type=NodeType.TABLE,
                label=f'Table {i + 1} ({t.rows}x{t.columns})',
                content=str(t.cells)[:500] if t.cells else '',
                confidence=t.confidence,
                data={
                    'rows': t.rows,
                    'columns': t.columns,
                    'headers': t.headers,
                },
            ))

    def _build_text_block_nodes(self, scene: EducationalScene, graph: EducationalSceneGraph) -> None:
        for i, tb in enumerate(scene.text_blocks):
            tb_id = f'tb_{i + 1}'
            text_type = NodeType.EXAMPLE if tb.block_type.value == 'example' else NodeType.CONCEPT
            if tb.block_type.value in ('heading', 'instruction'):
                text_type = NodeType.LEARNING_OBJECTIVE if tb.block_type.value == 'heading' else NodeType.TEACHER_NOTE

            graph.add_node(SceneNode(
                id=tb_id,
                type=text_type,
                label=tb.text[:80],
                content=tb.text,
                confidence=tb.confidence,
                data={
                    'block_type': tb.block_type.value,
                    'language': tb.language.value,
                    'is_handwritten': tb.is_handwritten,
                },
            ))

    def _build_mistake_nodes(self, scene: EducationalScene, graph: EducationalSceneGraph, question_roots: list[str]) -> None:
        for i, m in enumerate(scene.detected_mistakes):
            m_id = f'm_{i + 1}'
            graph.add_node(SceneNode(
                id=m_id,
                type=NodeType.MISTAKE,
                label=m.text[:80] or f'Mistake {i + 1}',
                content=m.text,
                confidence=m.confidence,
                data={
                    'mistake_type': m.mistake_type.value,
                    'correction': m.correction,
                    'is_teacher_correction': m.is_teacher_correction,
                },
            ))

            if question_roots:
                graph.add_edge(SceneEdge(
                    source_id=question_roots[0],
                    target_id=m_id,
                    type=EdgeType.HAS_MISTAKE,
                    confidence=m.confidence,
                ))

    def _add_mistake_from_question(self, graph: EducationalSceneGraph, mistake: DetectedMistake, q_id: str) -> None:
        m_id = self._next_id('m')
        graph.add_node(SceneNode(
            id=m_id,
            type=NodeType.MISTAKE,
            label=mistake.text[:80] or f'Mistake {m_id}',
            content=mistake.text,
            confidence=mistake.confidence,
            data={
                'mistake_type': mistake.mistake_type.value,
                'correction': mistake.correction,
                'is_teacher_correction': mistake.is_teacher_correction,
            },
        ))
        graph.add_edge(SceneEdge(
            source_id=q_id,
            target_id=m_id,
            type=EdgeType.HAS_MISTAKE,
            confidence=mistake.confidence,
        ))

    def _connect_concepts(self, scene: EducationalScene, graph: EducationalSceneGraph, concept_nodes: list[SceneNode]) -> None:
        for i, q in enumerate(scene.questions):
            q_id = f'q_{i + 1}'
            if not graph.has_node(q_id):
                continue
            for cn in concept_nodes:
                graph.add_edge(SceneEdge(
                    source_id=q_id,
                    target_id=cn.id,
                    type=EdgeType.RELATED_TO_CONCEPT,
                    confidence=scene.confidence.classification * 0.8,
                ))

    def _find_parent_question(self, scene: EducationalScene, x: float, y: float) -> Optional[str]:
        """Find the question node closest to a given (x, y) position."""
        best_q: Optional[str] = None
        best_dist = float('inf')
        for i, q in enumerate(scene.questions):
            qx, qy = q.bbox.x, q.bbox.y
            dist = ((qx - x) ** 2 + (qy - y) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_q = f'q_{i + 1}'
        return best_q
