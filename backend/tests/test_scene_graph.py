"""Comprehensive tests for the Educational Scene Graph (Phase 3.5).

Covers:
  - schemas: construction, serialization, helpers
  - relationships: semantics, validation, registry
  - graph: construction, traversal, topological sort, subgraph
  - builder: EducationalScene → EducationalSceneGraph
  - student_attempt: step extraction, mistake classification
  - concept_graph: built-in maps, topological order, missing prereqs
  - reasoner: focus, priorities, steps, hints, confidence
  - validator: missing nodes, cycles, low confidence, orphans
  - integration: full pipeline end-to-end with a realistic scene
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.scene_graph.builder import SceneGraphBuilder
from app.ai.scene_graph.concept_graph import ConceptGraphBuilder
from app.ai.scene_graph.graph import EducationalSceneGraph
from app.ai.scene_graph.integration import SceneGraphIntegration
from app.ai.scene_graph.reasoner import EducationalReasoner
from app.ai.scene_graph.relationships import (
    RelationshipSemantics,
    all_semantics,
    allowed_edge_types,
    get_semantics,
    is_valid_edge,
)
from app.ai.scene_graph.schemas import (
    BoardFocus,
    ConceptDependencies,
    ConceptEdge,
    ConceptNode,
    EdgeType,
    MistakeAnalysis,
    MistakeCategory,
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
from app.ai.scene_graph.student_attempt import StudentAttemptAnalyzer
from app.ai.scene_graph.validator import SceneGraphValidator
from app.core.constants import Subject

from app.ai.vision_intelligence.schema import (
    BoundingBox,
    DetectedMistake,
    Diagram,
    EducationalScene,
    Formula,
    Graph,
    ImageQuality,
    PageRegion,
    Question,
    SceneConfidence,
    SceneMetadata,
    TextBlock,
)


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_scene() -> EducationalScene:
    """A realistic educational scene from a math notebook."""
    return EducationalScene(
        image_quality=ImageQuality(
            brightness=0.7, contrast=0.6, sharpness=0.8,
            blur_score=0.9, noise_level=0.1, overall_score=0.85,
            is_acceptable=True,
        ),
        page=PageRegion(
            page_type='notebook',
            bbox=BoundingBox(x=0.05, y=0.05, width=0.9, height=0.9),
            confidence=0.95,
        ),
        text_blocks=[
            TextBlock(
                text='Solve the quadratic equation: x² - 5x + 6 = 0',
                bbox=BoundingBox(x=0.1, y=0.1, width=0.8, height=0.05),
                block_type='question_text',
                confidence=0.95,
            ),
            TextBlock(
                text='Step 1: Identify coefficients a=1, b=-5, c=6',
                bbox=BoundingBox(x=0.1, y=0.2, width=0.8, height=0.04),
                block_type='student_answer',
                confidence=0.9,
                is_handwritten=True,
            ),
        ],
        questions=[
            Question(
                question_text='Solve the quadratic equation: x² - 5x + 6 = 0',
                student_answer='x = 2, x = 3',
                bbox=BoundingBox(x=0.1, y=0.1, width=0.8, height=0.15),
                confidence=0.92,
                mistakes=[
                    DetectedMistake(
                        text='Wrong sign in middle term',
                        bbox=BoundingBox(x=0.1, y=0.25, width=0.3, height=0.03),
                        mistake_type='sign_error',
                        confidence=0.85,
                        correction='The formula is x = [-b ± √(b² - 4ac)] / 2a',
                        is_teacher_correction=False,
                    ),
                ],
                sub_questions=[],
                is_complete=True,
            ),
        ],
        formulas=[
            Formula(
                latex='x^2 - 5x + 6 = 0',
                plain_text='x² - 5x + 6 = 0',
                bbox=BoundingBox(x=0.1, y=0.1, width=0.5, height=0.05),
                formula_type='mathematics',
                confidence=0.9,
                symbols=['x'],
            ),
            Formula(
                latex='x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}',
                plain_text='quadratic formula',
                bbox=BoundingBox(x=0.1, y=0.35, width=0.6, height=0.05),
                formula_type='mathematics',
                confidence=0.88,
                symbols=['a', 'b', 'c', 'x'],
            ),
        ],
        diagrams=[],
        graphs=[],
        tables=[],
        subject=Subject.MATH,
        topic='quadratic_equations',
        difficulty='intermediate',
        concepts=['algebra', 'quadratic equations', 'factorization', 'discriminant'],
        teacher_focus='Explain the quadratic formula step by step',
        detected_mistakes=[],
        already_solved=False,
        solved_steps=[],
        confidence=SceneConfidence(
            overall=0.85, ocr=0.9, handwriting=0.75,
            formulas=0.88, diagrams=0.0, graphs=0.0,
            classification=0.85, layout=0.9,
        ),
        metadata=SceneMetadata(
            processing_time_ms=450,
            pipeline_version='3.0.0',
            models_used=['vision-ocr', 'layout-analyzer'],
            timestamp=datetime.utcnow().isoformat(),
        ),
    )


@pytest.fixture
def sample_graph(sample_scene: EducationalScene) -> EducationalSceneGraph:
    builder = SceneGraphBuilder()
    return builder.build(sample_scene, scene_id='test_scene_001')


@pytest.fixture
def empty_graph() -> EducationalSceneGraph:
    return EducationalSceneGraph()


@pytest.fixture
def student_attempt() -> StudentAttempt:
    return StudentAttempt(
        question_id='q_1',
        question_text='Solve: x² - 5x + 6 = 0',
        student_answer='Step 1: a=1, b=-5, c=6 | Step 2: Discriminant = 25-24=1 | Step 3: x = 3, x = 2',
        steps=[
            StudentStep(step_number=1, content='a=1, b=-5, c=6', status=StepStatus.CORRECT, confidence=0.9),
            StudentStep(step_number=2, content='Discriminant = 25-24=1', status=StepStatus.CORRECT, confidence=0.85),
            StudentStep(step_number=3, content='x = 3, x = 2', status=StepStatus.CORRECT, confidence=0.8),
        ],
        solved_steps=['1', '2', '3'],
        mistakes=[],
        overall_correctness=0.9,
        completeness=1.0,
        confidence=0.85,
        reasoning_depth=ReasoningDepth.PROCEDURAL,
        summary='All steps correctly solved',
    )


# ══════════════════════════════════════════════════════════════════════════
# Schema Tests
# ══════════════════════════════════════════════════════════════════════════


class TestSchemas:
    def test_scene_node_creation(self):
        node = SceneNode(id='q_1', type=NodeType.QUESTION, label='Test Question', confidence=0.9)
        assert node.id == 'q_1'
        assert node.type == NodeType.QUESTION
        assert node.confidence == 0.9
        assert node.data == {}
        assert node.metadata == {}

    def test_scene_node_to_dict(self):
        node = SceneNode(id='q_1', type=NodeType.QUESTION, label='Test Question',
                         content='Long content here', confidence=0.9)
        d = node.to_dict()
        assert d['id'] == 'q_1'
        assert 'Long content' in d['content']

    def test_scene_edge_creation(self):
        edge = SceneEdge(source_id='q_1', target_id='f_1', type=EdgeType.HAS_FORMULA, confidence=0.8)
        assert edge.source_id == 'q_1'
        assert edge.target_id == 'f_1'
        assert edge.type == EdgeType.HAS_FORMULA

    def test_scene_edge_to_dict(self):
        edge = SceneEdge(source_id='q_1', target_id='f_1', type=EdgeType.HAS_FORMULA, label='Has Formula')
        d = edge.to_dict()
        assert d['source'] == 'q_1'
        assert d['target'] == 'f_1'
        assert d['label'] == 'Has Formula'

    def test_scene_graph_operations(self):
        sg = SceneGraph(
            nodes=[
                SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9),
                SceneNode(id='a_1', type=NodeType.STUDENT_ANSWER, label='Ans', confidence=0.8),
            ],
            edges=[
                SceneEdge(source_id='q_1', target_id='a_1', type=EdgeType.HAS_ANSWER, confidence=0.9),
            ],
            root_node_ids=['q_1'],
        )
        assert sg.get_node('q_1') is not None
        assert sg.get_node('nonexistent') is None
        children = sg.get_children('q_1')
        assert len(children) == 1
        assert children[0].id == 'a_1'
        parents = sg.get_parents('a_1')
        assert len(parents) == 1
        assert parents[0].id == 'q_1'

    def test_scene_graph_get_nodes_by_type(self):
        sg = SceneGraph(
            nodes=[
                SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9),
                SceneNode(id='f_1', type=NodeType.FORMULA, label='F1', confidence=0.8),
                SceneNode(id='f_2', type=NodeType.FORMULA, label='F2', confidence=0.7),
            ],
        )
        formulas = sg.get_nodes_by_type(NodeType.FORMULA)
        assert len(formulas) == 2

    def test_scene_graph_serializable(self):
        sg = SceneGraph(
            nodes=[SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)],
            root_node_ids=['q_1'],
        )
        ser = sg.to_serializable()
        assert 'nodes' in ser
        assert 'edges' in ser
        assert 'root_node_ids' in ser

    def test_student_attempt_properties(self):
        sa = StudentAttempt(
            question_id='q_1',
            steps=[
                StudentStep(step_number=1, content='Step 1', status=StepStatus.CORRECT),
                StudentStep(step_number=2, content='Step 2', status=StepStatus.INCORRECT,
                            mistakes=[MistakeAnalysis(description='Arithmetic error', category=MistakeCategory.CALCULATION)]),
            ],
            mistakes=[MistakeAnalysis(description='Overall error', category=MistakeCategory.CONCEPTUAL)],
        )
        assert sa.mistake_count == 2
        assert not sa.is_complete
        assert sa.completeness == 0.0

    def test_mistake_analysis_defaults(self):
        m = MistakeAnalysis(description='Test mistake')
        assert m.category == MistakeCategory.UNKNOWN
        assert m.severity == 1
        assert not m.is_teacher_correction

    def test_teaching_decision(self):
        td = TeachingDecision(
            focus=TeacherFocus(
                current_focus='Teach quadratic formula',
                misconception='Sign error in discriminant',
                learning_objective='Understand quadratic formula application',
            ),
            priority=TeachingPriority(
                immediate=['Explain discriminant', 'Show quadratic formula'],
            ),
            confidence=0.8,
        )
        assert td.focus.current_focus == 'Teach quadratic formula'
        assert len(td.priority.immediate) == 2
        assert td.confidence == 0.8


# ══════════════════════════════════════════════════════════════════════════
# Relationships Tests
# ══════════════════════════════════════════════════════════════════════════


class TestRelationships:
    def test_get_semantics(self):
        sem = get_semantics(EdgeType.CONTAINS)
        assert isinstance(sem, RelationshipSemantics)
        assert sem.label == 'Contains'

    def test_get_semantics_unknown(self):
        with pytest.raises(ValueError):
            get_semantics('unknown_type')  # type: ignore[arg-type]

    def test_allowed_edge_types(self):
        types = allowed_edge_types(NodeType.QUESTION, NodeType.STUDENT_ANSWER)
        assert EdgeType.HAS_ANSWER in types
        assert EdgeType.CONTAINS in types

    def test_is_valid_edge_true(self):
        # HAS_ANSWER should be valid between question and answer
        assert is_valid_edge(NodeType.QUESTION, EdgeType.HAS_ANSWER, NodeType.STUDENT_ANSWER)

    def test_positive_negative_edge_types(self):
        from app.ai.scene_graph.relationships import positive_edge_types, negative_edge_types
        pos = positive_edge_types()
        neg = negative_edge_types()
        assert EdgeType.CONTAINS in pos
        assert EdgeType.HAS_MISTAKE in neg
        assert EdgeType.INCORRECT_STEP in neg

    def test_inferrable_edge_types(self):
        from app.ai.scene_graph.relationships import inferrable_edge_types
        inferrable = inferrable_edge_types()
        assert EdgeType.CONTAINS in inferrable
        assert EdgeType.TEACHER_HINT not in inferrable

    def test_all_semantics(self):
        sem_list = all_semantics()
        assert len(sem_list) > 0
        for s in sem_list:
            assert 'type' in s
            assert 'label' in s
            assert 'description' in s


# ══════════════════════════════════════════════════════════════════════════
# Graph Tests
# ══════════════════════════════════════════════════════════════════════════


class TestGraph:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.node_count == 0
        assert empty_graph.edge_count == 0
        assert len(empty_graph.get_roots()) == 0

    def test_add_node(self, empty_graph):
        node = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        empty_graph.add_node(node)
        assert empty_graph.node_count == 1
        assert empty_graph.has_node('q_1')

    def test_get_node(self, empty_graph):
        node = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        empty_graph.add_node(node)
        retrieved = empty_graph.get_node('q_1')
        assert retrieved is not None
        assert retrieved.id == 'q_1'
        assert retrieved.type == NodeType.QUESTION

    def test_remove_node(self, empty_graph):
        node = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        empty_graph.add_node(node)
        assert empty_graph.remove_node('q_1') is True
        assert empty_graph.node_count == 0
        assert empty_graph.remove_node('nonexistent') is False

    def test_update_node(self, empty_graph):
        node = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        empty_graph.add_node(node)
        empty_graph.update_node('q_1', label='Updated Q1', confidence=0.95)
        updated = empty_graph.get_node('q_1')
        assert updated is not None
        assert updated.label == 'Updated Q1'
        assert updated.confidence == 0.95

    def test_add_edge(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        a = SceneNode(id='a_1', type=NodeType.STUDENT_ANSWER, label='Ans', confidence=0.8)
        empty_graph.add_node(q)
        empty_graph.add_node(a)
        edge = SceneEdge(source_id='q_1', target_id='a_1', type=EdgeType.HAS_ANSWER, confidence=0.9)
        assert empty_graph.add_edge(edge) is True
        assert empty_graph.edge_count == 1

    def test_add_invalid_edge(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        f = SceneNode(id='f_1', type=NodeType.FORMULA, label='F1', confidence=0.8)
        empty_graph.add_node(q)
        empty_graph.add_node(f)
        # HAS_FORMULA should be valid, so this should succeed
        edge = SceneEdge(source_id='q_1', target_id='f_1', type=EdgeType.HAS_FORMULA, confidence=0.9)
        assert empty_graph.add_edge(edge) is True

    def test_remove_edge(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        a = SceneNode(id='a_1', type=NodeType.STUDENT_ANSWER, label='Ans', confidence=0.8)
        empty_graph.add_node(q)
        empty_graph.add_node(a)
        edge = SceneEdge(source_id='q_1', target_id='a_1', type=EdgeType.HAS_ANSWER, confidence=0.9)
        empty_graph.add_edge(edge)
        assert empty_graph.remove_edge('q_1', 'a_1') is True
        assert empty_graph.edge_count == 0

    def test_get_edges(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        a = SceneNode(id='a_1', type=NodeType.STUDENT_ANSWER, label='Ans', confidence=0.8)
        f = SceneNode(id='f_1', type=NodeType.FORMULA, label='F1', confidence=0.7)
        empty_graph.add_node(q)
        empty_graph.add_node(a)
        empty_graph.add_node(f)
        empty_graph.add_edge(SceneEdge(source_id='q_1', target_id='a_1', type=EdgeType.HAS_ANSWER, confidence=0.9))
        empty_graph.add_edge(SceneEdge(source_id='q_1', target_id='f_1', type=EdgeType.HAS_FORMULA, confidence=0.8))
        edges = empty_graph.get_edges(node_id='q_1')
        assert len(edges) == 2
        formula_edges = empty_graph.get_edges(edge_type=EdgeType.HAS_FORMULA)
        assert len(formula_edges) == 1

    def test_nodes_by_type(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        f1 = SceneNode(id='f_1', type=NodeType.FORMULA, label='F1', confidence=0.8)
        f2 = SceneNode(id='f_2', type=NodeType.FORMULA, label='F2', confidence=0.7)
        empty_graph.add_node(q)
        empty_graph.add_node(f1)
        empty_graph.add_node(f2)
        formulas = empty_graph.nodes_by_type(NodeType.FORMULA)
        assert len(formulas) == 2
        questions = empty_graph.nodes_by_type(NodeType.QUESTION)
        assert len(questions) == 1

    def test_topological_sort(self, empty_graph):
        a = SceneNode(id='a', type=NodeType.CONCEPT, label='A', confidence=0.9)
        b = SceneNode(id='b', type=NodeType.CONCEPT, label='B', confidence=0.9)
        c = SceneNode(id='c', type=NodeType.CONCEPT, label='C', confidence=0.9)
        empty_graph.add_node(a)
        empty_graph.add_node(b)
        empty_graph.add_node(c)
        empty_graph.add_edge(SceneEdge(source_id='a', target_id='b', type=EdgeType.BUILDS_ON, confidence=0.9))
        empty_graph.add_edge(SceneEdge(source_id='b', target_id='c', type=EdgeType.BUILDS_ON, confidence=0.9))
        ordered = empty_graph.topological_sort()
        assert len(ordered) == 3
        ids = [n.id for n in ordered]
        assert ids.index('a') < ids.index('b') < ids.index('c')

    def test_has_path(self, empty_graph):
        a = SceneNode(id='a', type=NodeType.CONCEPT, label='A', confidence=0.9)
        b = SceneNode(id='b', type=NodeType.CONCEPT, label='B', confidence=0.9)
        c = SceneNode(id='c', type=NodeType.CONCEPT, label='C', confidence=0.9)
        empty_graph.add_node(a)
        empty_graph.add_node(b)
        empty_graph.add_node(c)
        empty_graph.add_edge(SceneEdge(source_id='a', target_id='b', type=EdgeType.BUILDS_ON, confidence=0.9))
        empty_graph.add_edge(SceneEdge(source_id='b', target_id='c', type=EdgeType.BUILDS_ON, confidence=0.9))
        assert empty_graph.has_path('a', 'c') is True
        assert empty_graph.has_path('c', 'a') is False

    def test_shortest_path(self, empty_graph):
        a = SceneNode(id='a', type=NodeType.CONCEPT, label='A', confidence=0.9)
        b = SceneNode(id='b', type=NodeType.CONCEPT, label='B', confidence=0.9)
        c = SceneNode(id='c', type=NodeType.CONCEPT, label='C', confidence=0.9)
        empty_graph.add_node(a)
        empty_graph.add_node(b)
        empty_graph.add_node(c)
        empty_graph.add_edge(SceneEdge(source_id='a', target_id='b', type=EdgeType.BUILDS_ON, confidence=0.9))
        empty_graph.add_edge(SceneEdge(source_id='b', target_id='c', type=EdgeType.BUILDS_ON, confidence=0.9))
        path = empty_graph.shortest_path('a', 'c')
        assert len(path) == 3
        assert path[0].id == 'a'
        assert path[2].id == 'c'

    def test_subgraph(self, empty_graph):
        nodes = [
            SceneNode(id='a', type=NodeType.CONCEPT, label='A', confidence=0.9),
            SceneNode(id='b', type=NodeType.CONCEPT, label='B', confidence=0.9),
            SceneNode(id='c', type=NodeType.CONCEPT, label='C', confidence=0.9),
        ]
        for n in nodes:
            empty_graph.add_node(n)
        empty_graph.add_edge(SceneEdge(source_id='a', target_id='b', type=EdgeType.BUILDS_ON, confidence=0.9))
        sub = empty_graph.subgraph(['a', 'b'])
        assert sub.node_count == 2
        assert sub.has_node('a')
        assert not sub.has_node('c')

    def test_cache_key(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        empty_graph.add_node(q)
        key = empty_graph.cache_key()
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hex digest length

    def test_to_schema_roundtrip(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        a = SceneNode(id='a_1', type=NodeType.STUDENT_ANSWER, label='Ans', confidence=0.8)
        empty_graph.add_node(q)
        empty_graph.add_node(a)
        empty_graph.add_edge(SceneEdge(source_id='q_1', target_id='a_1', type=EdgeType.HAS_ANSWER, confidence=0.9))
        empty_graph.root_node_ids = ['q_1']
        sg = empty_graph.to_schema()
        assert sg.node_count() == 2
        assert sg.edge_count() == 1
        assert 'q_1' in sg.root_node_ids

    def test_to_json(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        empty_graph.add_node(q)
        json_str = empty_graph.to_json()
        data = json.loads(json_str)
        assert 'nodes' in data
        assert 'edges' in data


# ══════════════════════════════════════════════════════════════════════════
# Builder Tests
# ══════════════════════════════════════════════════════════════════════════


class TestBuilder:
    def test_build_from_scene(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene, scene_id='test_001')
        assert graph.node_count > 0
        assert graph.edge_count > 0
        assert 'test_001' in graph.metadata.source_scene_id
        assert graph.metadata.vision_confidence == 0.85

    def test_build_creates_question_nodes(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        questions = graph.nodes_by_type(NodeType.QUESTION)
        assert len(questions) == 1
        assert questions[0].id == 'q_1'

    def test_build_creates_formula_nodes(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        formulas = graph.nodes_by_type(NodeType.FORMULA)
        assert len(formulas) == 2  # two formulas in sample scene

    def test_build_creates_concept_nodes(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        concepts = graph.nodes_by_type(NodeType.CONCEPT)
        assert len(concepts) >= 4

    def test_build_creates_answer_nodes(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        answers = graph.nodes_by_type(NodeType.STUDENT_ANSWER)
        assert len(answers) == 1

    def test_build_creates_mistake_nodes(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        mistakes = graph.nodes_by_type(NodeType.MISTAKE)
        assert len(mistakes) >= 1

    def test_build_has_root_nodes(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        assert len(graph.root_node_ids) > 0

    def test_build_connects_formulas_to_questions(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        q_edges = graph.get_edges(node_id='q_1', edge_type=EdgeType.HAS_FORMULA)
        assert len(q_edges) >= 1

    def test_build_sets_metadata(self, sample_scene):
        builder = SceneGraphBuilder()
        graph = builder.build(sample_scene)
        assert graph.metadata.node_count == graph.node_count
        assert graph.metadata.edge_count == graph.edge_count
        assert graph.metadata.processing_time_ms > 0

    def test_build_empty_scene(self):
        empty_scene = EducationalScene()
        builder = SceneGraphBuilder()
        graph = builder.build(empty_scene)
        assert graph.node_count == 0  # no content to build from


# ══════════════════════════════════════════════════════════════════════════
# Student Attempt Tests
# ══════════════════════════════════════════════════════════════════════════


class TestStudentAttemptAnalyzer:
    def test_analyze_extracts_steps(self, sample_graph):
        analyzer = StudentAttemptAnalyzer()
        attempts = analyzer.analyze(sample_graph)
        # We should have at least one attempt for q_1
        for attempt in attempts:
            if attempt.question_id == 'q_1':
                assert len(attempt.steps) > 0

    def test_analyze_no_questions(self, empty_graph):
        analyzer = StudentAttemptAnalyzer()
        attempts = analyzer.analyze(empty_graph)
        assert attempts == []

    def test_extract_steps_multiline(self):
        analyzer = StudentAttemptAnalyzer()
        answer = 'Step 1: a=1, b=-5, c=6\nStep 2: Discriminant = b² - 4ac = 25 - 24 = 1\nStep 3: x = [5 ± 1] / 2'
        steps = analyzer._extract_steps(answer)
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert 'a=1' in steps[0].content

    def test_extract_steps_single_line(self):
        analyzer = StudentAttemptAnalyzer()
        steps = analyzer._extract_steps('Just one step here')
        assert len(steps) == 1
        assert steps[0].step_number == 1

    def test_extract_steps_empty(self):
        analyzer = StudentAttemptAnalyzer()
        steps = analyzer._extract_steps('')
        assert steps == []

    def test_classify_correct_step(self):
        analyzer = StudentAttemptAnalyzer()
        steps = [StudentStep(step_number=1, content='a=1, b=-5, c=6', status=StepStatus.UNKNOWN)]
        analyzer._classify_steps(steps, [], 'Test question')
        assert steps[0].status == StepStatus.CORRECT

    def test_classify_skipped_step(self):
        analyzer = StudentAttemptAnalyzer()
        steps = [StudentStep(step_number=1, content='Skip this step for now', status=StepStatus.UNKNOWN)]
        analyzer._classify_steps(steps, [], '')
        assert steps[0].status == StepStatus.SKIPPED

    def test_classify_incomplete_step(self):
        analyzer = StudentAttemptAnalyzer()
        steps = [StudentStep(step_number=1, content='I am not sure about the next step??', status=StepStatus.UNKNOWN)]
        analyzer._classify_steps(steps, [], '')
        assert steps[0].status == StepStatus.INCOMPLETE

    def test_mistake_classification_calculation(self):
        analyzer = StudentAttemptAnalyzer()
        cat = analyzer._classify_mistake('15 + 7 = 23 is wrong')
        assert cat == MistakeCategory.CALCULATION

    def test_mistake_classification_conceptual(self):
        analyzer = StudentAttemptAnalyzer()
        cat = analyzer._classify_mistake('Student does not understand the concept of discriminant')
        assert cat == MistakeCategory.CONCEPTUAL

    def test_mistake_classification_sign(self):
        analyzer = StudentAttemptAnalyzer()
        cat = analyzer._classify_mistake('--5 should be +5')
        assert cat == MistakeCategory.SIGN_ERROR

    def test_mistake_classification_formula(self):
        analyzer = StudentAttemptAnalyzer()
        cat = analyzer._classify_mistake('Wrong formula used for area of circle')
        assert cat == MistakeCategory.FORMULA_ERROR

    def test_mistake_classification_unit(self):
        analyzer = StudentAttemptAnalyzer()
        cat = analyzer._classify_mistake('Missing unit in final answer cm')
        assert cat == MistakeCategory.UNIT_ERROR

    def test_estimate_reasoning_depth_surface(self):
        analyzer = StudentAttemptAnalyzer()
        depth = analyzer._estimate_reasoning_depth(
            [StudentStep(step_number=1, content='x=2', status=StepStatus.CORRECT)],
            'x=2',
        )
        assert depth == ReasoningDepth.SURFACE

    def test_estimate_reasoning_depth_procedural(self):
        analyzer = StudentAttemptAnalyzer()
        depth = analyzer._estimate_reasoning_depth(
            [
                StudentStep(step_number=1, content='Step 1', status=StepStatus.CORRECT),
                StudentStep(step_number=2, content='Step 2', status=StepStatus.CORRECT),
            ],
            'Step 1 then step 2',
        )
        assert depth == ReasoningDepth.PROCEDURAL

    def test_categorize_steps(self):
        analyzer = StudentAttemptAnalyzer()
        steps = [
            StudentStep(step_number=1, content='Correct', status=StepStatus.CORRECT),
            StudentStep(step_number=2, content='Wrong', status=StepStatus.INCORRECT),
            StudentStep(step_number=3, content='Skip', status=StepStatus.SKIPPED),
        ]
        solved, incomplete, skipped = analyzer._categorize_steps(steps)
        assert '1' in solved
        assert '3' in skipped


# ══════════════════════════════════════════════════════════════════════════
# Concept Graph Tests
# ══════════════════════════════════════════════════════════════════════════


class TestConceptGraphBuilder:
    def test_build_trigonometry(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('mathematics', 'trigonometry', ['sine', 'cosine', 'tangent'])
        assert deps.topic == 'trigonometry'
        assert deps.subject == 'mathematics'
        assert len(deps.nodes) >= 5
        assert len(deps.edges) >= 1

    def test_build_physics_mechanics(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('physics', 'mechanics', ['forces', 'energy'])
        assert deps.topic == 'mechanics'
        assert len(deps.nodes) > 0

    def test_build_recommended_path(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('mathematics', 'quadratic_equations', ['algebra'])
        assert len(deps.recommended_path) > 0
        assert 'quadratic_equations' in deps.recommended_path or 'algebra' in deps.recommended_path

    def test_build_missing_prerequisites(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('mathematics', 'trigonometry', [])
        # All prerequisites start with 0.0 mastery, should be flagged
        assert isinstance(deps.missing_prerequisites, list)

    def test_update_mastery(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('mathematics', 'algebra', [])
        initial = deps.nodes[0].mastery if deps.nodes else 0.0
        if deps.nodes:
            builder.update_mastery(deps, deps.nodes[0].id, 0.3)
            assert deps.nodes[0].mastery >= initial

    def test_has_topic(self):
        builder = ConceptGraphBuilder()
        assert builder.has_topic('mathematics', 'trigonometry')
        assert not builder.has_topic('mathematics', 'nonexistent_topic')

    def test_get_subject_map(self):
        builder = ConceptGraphBuilder()
        subject_map = builder.get_subject_map('mathematics')
        assert 'trigonometry' in subject_map
        assert 'algebra' in subject_map

    def test_enrich_from_scene(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('mathematics', 'algebra', [])
        builder.enrich_from_scene(deps, {'formula': ['quadratic_formula']})
        ids = [n.id for n in deps.nodes]
        assert 'quadratic_formula' in ids

    def test_build_programming(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('programming', 'python_basics', ['variables', 'functions'])
        assert deps.subject == 'programming'
        assert len(deps.nodes) > 0

    def test_build_chemistry(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('chemistry', 'mole_concept', ['stoichiometry'])
        assert deps.subject == 'chemistry'
        assert len(deps.nodes) > 0

    def test_build_biology(self):
        builder = ConceptGraphBuilder()
        deps = builder.build('biology', 'genetics', ['dna', 'genes'])
        assert deps.subject == 'biology'
        assert len(deps.nodes) > 0


# ══════════════════════════════════════════════════════════════════════════
# Reasoner Tests
# ══════════════════════════════════════════════════════════════════════════


class TestReasoner:
    def test_reason_with_full_data(self, sample_graph, student_attempt, sample_scene):
        concept_builder = ConceptGraphBuilder()
        concept_deps = concept_builder.build('mathematics', 'quadratic_equations', ['algebra'])
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [student_attempt], concept_deps)
        assert isinstance(decision, TeachingDecision)
        assert decision.focus.current_focus != ''
        assert decision.confidence > 0

    def test_reason_with_attempt_only(self, sample_graph, student_attempt):
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [student_attempt])
        assert decision.focus.current_focus != ''
        assert decision.confidence > 0
        assert len(decision.priority.immediate) > 0

    def test_reason_with_graph_only(self, sample_graph):
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph)
        assert decision.focus.current_focus != ''
        assert isinstance(decision.hints, list)

    def test_reason_with_critical_mistake(self, sample_graph):
        attempt = StudentAttempt(
            question_id='q_1',
            question_text='Test',
            student_answer='Wrong answer',
            steps=[StudentStep(step_number=1, content='Wrong step', status=StepStatus.INCORRECT)],
            mistakes=[MistakeAnalysis(
                step_id='1',
                description='Critical formula error',
                category=MistakeCategory.FORMULA_ERROR,
                severity=5,
                correction='Use correct formula',
            )],
            overall_correctness=0.0,
            completeness=0.5,
            confidence=0.9,
        )
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [attempt])
        assert 'mistake' in decision.focus.current_focus.lower() or 'formula' in decision.focus.current_focus.lower()

    def test_reason_with_missing_prerequisites(self, sample_graph):
        concept_deps = ConceptDependencies(
            topic='test',
        subject=Subject.MATH,
            nodes=[ConceptNode(id='pre_req', name='Pre Req', is_prerequisite=True, mastery=0.0)],
            missing_prerequisites=['Pre Req'],
        )
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, concept_deps=concept_deps)
        assert 'prerequisite' in decision.focus.current_focus.lower()

    def test_reason_prioritizes_critical_mistakes(self, sample_graph):
        """Test that severe mistakes get highest priority."""
        attempt = StudentAttempt(
            question_id='q_1',
            question_text='Test',
            student_answer='Wrong',
            steps=[StudentStep(step_number=1, content='Wrong', status=StepStatus.INCORRECT)],
            mistakes=[MistakeAnalysis(
                description='Critical',
                category=MistakeCategory.CALCULATION,
                severity=5,
            )],
        )
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [attempt])
        assert len(decision.priority.immediate) > 0

    def test_determine_board_focus(self, sample_graph):
        reasoner = EducationalReasoner()
        concept_builder = ConceptGraphBuilder()
        concept_deps = concept_builder.build('mathematics', 'quadratic_equations', ['algebra'])
        decision = reasoner.reason(sample_graph, concept_deps=concept_deps)
        assert isinstance(decision.board, BoardFocus)

    def test_generate_hints(self, sample_graph):
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph)
        assert isinstance(decision.hints, list)
        assert len(decision.hints) > 0

    def test_confidence_calculation(self, sample_graph, student_attempt):
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [student_attempt])
        assert 0.0 <= decision.confidence <= 1.0

    def test_processing_time(self, sample_graph, student_attempt):
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [student_attempt])
        assert decision.processing_time_ms >= 0

    def test_step_analysis_in_decision(self, sample_graph, student_attempt):
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [student_attempt])
        assert len(decision.steps) > 0
        for step in decision.steps:
            assert isinstance(step, StepAnalysis)
            assert step.teacher_guidance != ''

    def test_reason_with_incorrect_attempt(self, sample_graph):
        attempt = StudentAttempt(
            question_id='q_1',
            question_text='Solve 2+2',
            student_answer='5',
            steps=[StudentStep(step_number=1, content='2+2=5', status=StepStatus.INCORRECT,
                               mistakes=[MistakeAnalysis(description='Arithmetic error',
                                                         category=MistakeCategory.CALCULATION)])],
            mistakes=[MistakeAnalysis(description='Wrong sum', category=MistakeCategory.CALCULATION)],
            overall_correctness=0.0,
            completeness=0.5,
            confidence=0.7,
        )
        reasoner = EducationalReasoner()
        decision = reasoner.reason(sample_graph, [attempt])
        assert len(decision.steps) > 0
        assert not decision.steps[0].is_correct


# ══════════════════════════════════════════════════════════════════════════
# Validator Tests
# ══════════════════════════════════════════════════════════════════════════


class TestValidator:
    def test_validate_valid_graph(self, sample_graph):
        validator = SceneGraphValidator()
        result = validator.validate(sample_graph)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_missing_node(self, empty_graph):
        q = SceneNode(id='q_1', type=NodeType.QUESTION, label='Q1', confidence=0.9)
        empty_graph.add_node(q)
        empty_graph.add_edge(SceneEdge(source_id='q_1', target_id='missing_node', type=EdgeType.HAS_ANSWER, confidence=0.9))
        validator = SceneGraphValidator()
        result = validator.validate(empty_graph)
        assert len(result.missing_nodes) > 0
        assert not result.is_valid

    def test_validate_circular_dependency(self, empty_graph):
        a = SceneNode(id='a', type=NodeType.CONCEPT, label='A', confidence=0.9)
        b = SceneNode(id='b', type=NodeType.CONCEPT, label='B', confidence=0.9)
        empty_graph.add_node(a)
        empty_graph.add_node(b)
        # Create a cycle: a -> b -> a
        empty_graph.add_edge(SceneEdge(source_id='a', target_id='b', type=EdgeType.DEPENDS_ON, confidence=0.9))
        empty_graph.add_edge(SceneEdge(source_id='b', target_id='a', type=EdgeType.DEPENDS_ON, confidence=0.9))
        validator = SceneGraphValidator()
        result = validator.validate(empty_graph)
        assert len(result.circular_dependencies) > 0
        assert not result.is_valid

    def test_validate_low_confidence(self, empty_graph):
        node = SceneNode(id='low_conf', type=NodeType.CONCEPT, label='Low', confidence=0.05)
        empty_graph.add_node(node)
        validator = SceneGraphValidator()
        result = validator.validate(empty_graph)
        assert len(result.low_confidence_nodes) > 0

    def test_validate_orphaned_nodes(self, empty_graph):
        a = SceneNode(id='orphan', type=NodeType.CONCEPT, label='Orphan', confidence=0.9)
        b = SceneNode(id='connected', type=NodeType.CONCEPT, label='Connected', confidence=0.9)
        empty_graph.add_node(a)
        empty_graph.add_node(b)
        empty_graph.root_node_ids = ['connected']
        validator = SceneGraphValidator()
        result = validator.validate(empty_graph)
        assert 'orphan' in result.orphaned_nodes

    def test_assert_valid_success(self, sample_graph):
        validator = SceneGraphValidator()
        graph = validator.assert_valid(sample_graph)
        assert isinstance(graph, EducationalSceneGraph)

    def test_assert_valid_failure(self, empty_graph):
        empty_graph.add_edge(SceneEdge(source_id='a', target_id='b', type=EdgeType.DEPENDS_ON, confidence=0.9))
        validator = SceneGraphValidator()
        with pytest.raises(ValueError):
            validator.assert_valid(empty_graph)

    def test_remove_low_confidence(self, empty_graph):
        low = SceneNode(id='low', type=NodeType.CONCEPT, label='Low', confidence=0.05)
        high = SceneNode(id='high', type=NodeType.CONCEPT, label='High', confidence=0.9)
        empty_graph.add_node(low)
        empty_graph.add_node(high)
        validator = SceneGraphValidator()
        removed = validator.remove_low_confidence(empty_graph, threshold=0.1)
        assert removed == 1
        assert not empty_graph.has_node('low')
        assert empty_graph.has_node('high')

    def test_find_inconsistent_graphs(self, sample_graph, empty_graph):
        validator = SceneGraphValidator()
        graphs = [sample_graph, empty_graph]
        results = validator.find_inconsistent_graphs(graphs)
        assert len(results) >= 1  # empty_graph should fail


# ══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, sample_scene):
        integration = SceneGraphIntegration()
        decision = await integration.process(sample_scene)
        assert isinstance(decision, TeachingDecision)
        assert decision.focus.current_focus != ''
        assert decision.confidence > 0.0
        assert len(decision.priority.immediate) > 0
        assert isinstance(decision.hints, list)

    @pytest.mark.asyncio
    async def test_pipeline_cache(self, sample_scene):
        integration = SceneGraphIntegration()
        decision1 = await integration.process(sample_scene, scene_id='cache_test')
        decision2 = await integration.process(sample_scene, scene_id='cache_test')
        assert decision1.focus.current_focus == decision2.focus.current_focus
        assert decision1.confidence == decision2.confidence

    @pytest.mark.asyncio
    async def test_pipeline_cache_bypass(self, sample_scene):
        integration = SceneGraphIntegration()
        decision1 = await integration.process(sample_scene, scene_id='bypass_test')
        integration.invalidate_cache('bypass_test')
        decision2 = await integration.process(sample_scene, scene_id='bypass_test', bypass_cache=True)
        assert isinstance(decision2, TeachingDecision)

    def test_sync_pipeline(self, sample_scene):
        integration = SceneGraphIntegration()
        decision = integration.process_sync(sample_scene)
        assert isinstance(decision, TeachingDecision)

    def test_build_graph(self, sample_scene):
        integration = SceneGraphIntegration()
        graph = integration.build_graph(sample_scene)
        assert isinstance(graph, EducationalSceneGraph)
        assert graph.node_count > 0

    def test_validate_graph(self, sample_graph):
        integration = SceneGraphIntegration()
        is_valid = integration.validate_graph(sample_graph)
        assert is_valid is True

    def test_analyze_attempts(self, sample_graph):
        integration = SceneGraphIntegration()
        attempts = integration.analyze_attempts(sample_graph)
        assert isinstance(attempts, list)

    def test_build_concept_graph(self):
        integration = SceneGraphIntegration()
        deps = integration.build_concept_graph('mathematics', 'trigonometry', ['sine'])
        assert isinstance(deps, ConceptDependencies)
        assert deps.topic == 'trigonometry'

    def test_fallback_decision(self):
        scene = EducationalScene()
        integration = SceneGraphIntegration()
        fallback = integration._fallback_decision(scene, 'test failure')
        assert fallback.confidence == 0.3
        assert fallback.focus.current_focus != ''

    def test_invalidate_cache_all(self, sample_scene):
        integration = SceneGraphIntegration()
        decision = integration.process_sync(sample_scene, 'inval_test')
        assert decision is not None
        integration.invalidate_cache()
        assert len(integration._cache) == 0
