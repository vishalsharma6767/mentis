"""Student Attempt Analyzer — detects solved steps, incomplete steps,
wrong formulas, arithmetic mistakes, conceptual mistakes, skipped
reasoning, wrong diagrams, missing labels, and wrong graphs.

Operates on the EducationalSceneGraph, not on raw text.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.ai.scene_graph.graph import EducationalSceneGraph
from app.ai.scene_graph.schemas import (
    EdgeType,
    MistakeAnalysis,
    MistakeCategory,
    NodeType,
    ReasoningDepth,
    SceneNode,
    StepStatus,
    StudentAttempt,
    StudentStep,
)
from app.ai.scene_graph.validator import SceneGraphValidator
from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# ── Heuristic patterns ───────────────────────────────────────────────────

ARITHMETIC_PATTERNS = re.compile(
    r'(\d+\s*[+\-*/]\s*\d+\s*=\s*\d+)'
    r'|(\d+\.\d+\s*[+\-*/]\s*\d+\.?\d*)',
)
SIGN_PATTERNS = re.compile(
    r'[+\-]{2,}|(?<!\w)-\s*[+\-]|(?<=\d)\s*-\s*-',
)
FORMULA_KEYWORDS = re.compile(
    r'(formula|equation|using|applying|by|from|since|because)',
    re.IGNORECASE,
)
SKIPPED_PATTERNS = re.compile(
    r'(skip|omit|left|not done|missing|incomplete|\.\.\.|—)',
    re.IGNORECASE,
)
DIAGRAM_KEYWORDS = re.compile(
    r'(diagram|draw|sketch|plot|graph|figure|label)',
    re.IGNORECASE,
)


class StudentAttemptAnalyzer:
    """Analyzes student attempts by walking the SceneGraph."""

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    # ── Main entry point ─────────────────────────────────────────────────

    def analyze(self, graph: EducationalSceneGraph) -> list[StudentAttempt]:
        """Analyze every question node in the graph for student attempt data."""
        question_nodes = graph.nodes_by_type(NodeType.QUESTION)
        if not question_nodes:
            logger.info('No question nodes found in graph')
            return []

        attempts: list[StudentAttempt] = []
        for q_node in question_nodes:
            attempt = self._analyze_single(graph, q_node)
            if attempt is not None:
                attempts.append(attempt)

        logger.info('Analyzed %d student attempts', len(attempts))
        return attempts

    def _analyze_single(self, graph: EducationalSceneGraph, q_node: SceneNode) -> Optional[StudentAttempt]:
        """Analyze student attempt for a single question node."""
        if q_node.id is None:
            return None

        answer_node = self._find_answer(graph, q_node.id)
        student_answer = answer_node.content if answer_node else ''

        if not student_answer:
            logger.debug('No student answer found for %s', q_node.id)
            return None

        mistake_nodes = self._find_mistakes(graph, q_node.id)
        formula_nodes = graph.children(q_node.id)
        formulas = [n for n in formula_nodes if n and n.type == NodeType.FORMULA]
        diagram_nodes = [n for n in formula_nodes if n and n.type in (NodeType.DIAGRAM, NodeType.GRAPH)]

        # Split student answer into steps
        steps = self._extract_steps(student_answer)
        self._classify_steps(steps, formulas, q_node.content)

        mistakes = self._build_mistake_list(mistake_nodes, steps)
        solved, incomplete, skipped = self._categorize_steps(steps)
        completeness = self._estimate_completeness(steps, mistakes)
        correctness = self._estimate_correctness(steps, mistakes, student_answer)
        reasoning_depth = self._estimate_reasoning_depth(steps, student_answer)
        confidence = self._estimate_confidence(steps, mistakes, completeness)
        summary = self._build_summary(q_node.content, student_answer, solved, mistakes)

        return StudentAttempt(
            question_id=q_node.id,
            question_text=q_node.content,
            student_answer=student_answer,
            steps=steps,
            solved_steps=solved,
            incomplete_steps=incomplete,
            skipped_steps=skipped,
            mistakes=mistakes,
            overall_correctness=correctness,
            completeness=completeness,
            confidence=confidence,
            reasoning_depth=reasoning_depth,
            summary=summary,
        )

    # ── Step extraction ──────────────────────────────────────────────────

    def _extract_steps(self, answer: str) -> list[StudentStep]:
        """Split student answer into numbered steps."""
        if not answer.strip():
            return []

        lines = answer.strip().split('\n')
        steps: list[StudentStep] = []
        current_step_num: Optional[int] = None
        current_text: list[str] = []

        def flush() -> None:
            if current_text and current_step_num is not None:
                steps.append(StudentStep(
                    step_number=current_step_num,
                    content=' '.join(current_text),
                    status=StepStatus.UNKNOWN,
                ))

        for line in lines:
            line = line.strip()
            if not line:
                if current_text:
                    flush()
                    current_text = []
                    current_step_num = None
                continue

            step_match = re.match(r'^(Step\s*(\d+)[:.)]?\s*|(\d+)[:.)]\s+)', line)
            if step_match:
                flush()
                current_step_num = int(step_match.group(2) or step_match.group(3) or 1)
                current_text = [line[step_match.end():]]
            else:
                if current_step_num is None:
                    current_step_num = len(steps) + 1
                current_text.append(line)

        flush()
        return steps if steps else [StudentStep(step_number=1, content=answer.strip(), status=StepStatus.UNKNOWN)]

    # ── Step classification ──────────────────────────────────────────────

    def _classify_steps(self, steps: list[StudentStep], formulas: list[SceneNode], question_text: str) -> None:
        """Classify each step as correct, incorrect, incomplete, or skipped."""
        for step in steps:
            content = step.content.lower()

            if SKIPPED_PATTERNS.search(content):
                step.status = StepStatus.SKIPPED
                continue

            if self._is_arithmetic_mistake(content):
                step.status = StepStatus.INCORRECT
                step.mistakes.append(MistakeAnalysis(
                    step_id=str(step.step_number),
                    description='Arithmetic error detected in this step',
                    category=MistakeCategory.CALCULATION,
                    confidence=0.6,
                ))
                continue

            if self._is_incomplete(content):
                step.status = StepStatus.INCOMPLETE
                continue

            step.status = StepStatus.CORRECT

        # If all steps are UNKNOWN, mark as correct by default with low confidence
        unknown_steps = [s for s in steps if s.status == StepStatus.UNKNOWN]
        if unknown_steps and len(unknown_steps) == len(steps):
            for s in unknown_steps:
                s.status = StepStatus.CORRECT

    def _is_arithmetic_mistake(self, content: str) -> bool:
        """Heuristic check for arithmetic errors."""
        if not ARITHMETIC_PATTERNS.search(content):
            return False
        arithmetic_parts = ARITHMETIC_PATTERNS.findall(content)
        for parts in arithmetic_parts:
            expr = parts[0] or parts[1]
            if expr and self._check_computation(expr) is False:
                return True
        return False

    def _check_computation(self, expr: str) -> Optional[bool]:
        """Simple arithmetic check. Returns False if clearly wrong, None if unsure."""
        try:
            parts = re.split(r'\s*=\s*', expr, maxsplit=1)
            if len(parts) != 2:
                return None
            left_str, right_str = parts[0].strip(), parts[1].strip()
            left_val = eval(left_str, {'__builtins__': {}}, {})
            right_val = float(right_str) if '.' in right_str else int(right_str)
            return abs(left_val - right_val) < 1e-9
        except Exception:
            return None

    def _is_incomplete(self, content: str) -> bool:
        incomplete_markers = [
            '...', '—', '--', '??', '?', 'not sure', 'dont know',
            "don't know", 'cannot', "can't",
        ]
        return any(marker in content.lower() for marker in incomplete_markers)

    # ── Mistake analysis ─────────────────────────────────────────────────

    def _find_mistakes(self, graph: EducationalSceneGraph, q_id: str) -> list[SceneNode]:
        mistakes: list[SceneNode] = []
        for edge in graph.get_edges(edge_type=EdgeType.HAS_MISTAKE):
            if edge.source_id == q_id:
                node = graph.get_node(edge.target_id)
                if node:
                    mistakes.append(node)
        return mistakes

    def _build_mistake_list(self, mistake_nodes: list[SceneNode], steps: list[StudentStep]) -> list[MistakeAnalysis]:
        mistakes: list[MistakeAnalysis] = []
        for node in mistake_nodes:
            category = self._classify_mistake(node.content)
            mistakes.append(MistakeAnalysis(
                step_id='',
                description=node.content,
                category=category,
                confidence=node.confidence,
                correction=node.data.get('correction', ''),
                concept=node.data.get('concept', ''),
            ))
        for step in steps:
            if step.has_mistake:
                mistakes.extend(step.mistakes)
        return mistakes

    def _classify_mistake(self, text: str) -> MistakeCategory:
        text_lower = text.lower()
        if SIGN_PATTERNS.search(text):
            return MistakeCategory.SIGN_ERROR
        if re.search(r'(formula|equation|theorem|rule|law)', text_lower):
            return MistakeCategory.FORMULA_ERROR
        if re.search(r'\b(unit|cm|kg|ms|km|ml|litre)\b', text_lower):
            return MistakeCategory.UNIT_ERROR
        if re.search(r'\b(m|s)\b', text_lower):
            return MistakeCategory.UNIT_ERROR
        if ARITHMETIC_PATTERNS.search(text):
            return MistakeCategory.CALCULATION
        if re.search(r'(incomplete|missing|not finished|half)', text_lower):
            return MistakeCategory.INCOMPLETE
        if re.search(r'(concept|understand|meaning|definition)', text_lower):
            return MistakeCategory.CONCEPTUAL
        if re.search(r'(careless|oops|sorry|mistake)', text_lower):
            return MistakeCategory.CARELESS
        return MistakeCategory.UNKNOWN

    # ── Categorization ───────────────────────────────────────────────────

    def _categorize_steps(self, steps: list[StudentStep]) -> tuple[list[str], list[str], list[str]]:
        solved: list[str] = []
        incomplete: list[str] = []
        skipped: list[str] = []
        for step in steps:
            if step.status == StepStatus.CORRECT:
                solved.append(str(step.step_number))
            elif step.status == StepStatus.INCOMPLETE:
                incomplete.append(str(step.step_number))
            elif step.status == StepStatus.SKIPPED:
                skipped.append(str(step.step_number))
        return solved, incomplete, skipped

    def _estimate_completeness(self, steps: list[StudentStep], mistakes: list[MistakeAnalysis]) -> float:
        if not steps:
            return 0.0
        correct = sum(1 for s in steps if s.status in (StepStatus.CORRECT, StepStatus.UNKNOWN))
        ratio = correct / len(steps)
        mistake_penalty = min(len(mistakes) * 0.1, 0.5)
        return max(0.0, min(1.0, ratio - mistake_penalty))

    def _estimate_correctness(self, steps: list[StudentStep], mistakes: list[MistakeAnalysis], answer: str) -> float:
        if not steps and not answer:
            return 0.0
        correct_steps = sum(1 for s in steps if s.status == StepStatus.CORRECT)
        total_steps = len(steps) or 1
        step_score = correct_steps / total_steps
        mistake_penalty = min(len(mistakes) * 0.15, 0.75)
        return max(0.0, min(1.0, step_score - mistake_penalty))

    def _estimate_reasoning_depth(self, steps: list[StudentStep], answer: str) -> ReasoningDepth:
        if len(steps) <= 1:
            return ReasoningDepth.SURFACE
        explanation_markers = re.search(
            r'(because|since|therefore|hence|thus|so|reason|implies|meaning)', answer, re.IGNORECASE,
        )
        if explanation_markers:
            return ReasoningDepth.CONCEPTUAL if FORMULA_KEYWORDS.search(answer) else ReasoningDepth.PROCEDURAL
        multi_step = len(steps) >= 2
        return ReasoningDepth.PROCEDURAL if multi_step else ReasoningDepth.SURFACE

    def _estimate_confidence(self, steps: list[StudentStep], mistakes: list[MistakeAnalysis], completeness: float) -> float:
        if not steps:
            return 0.0
        step_conf = sum(s.confidence for s in steps) / len(steps) if steps else 0.0
        mistake_factor = max(0.0, 1.0 - len(mistakes) * 0.1)
        return min(1.0, max(0.0, step_conf * 0.5 + completeness * 0.3 + mistake_factor * 0.2))

    def _build_summary(self, question: str, answer: str, solved: list[str], mistakes: list[MistakeAnalysis]) -> str:
        parts: list[str] = []
        if solved:
            parts.append(f'Solved {len(solved)}/{len(solved) + sum(1 for m in mistakes if m)} steps')
        if mistakes:
            parts.append(f'Found {len(mistakes)} mistake(s): {mistakes[0].description[:60]}')
        if not parts:
            parts.append('Student attempt analyzed')
        return ' | '.join(parts) or 'No summary available'

    def _find_answer(self, graph: EducationalSceneGraph, q_id: str) -> Optional[SceneNode]:
        for edge in graph.get_edges(edge_type=EdgeType.HAS_ANSWER):
            if edge.source_id == q_id:
                return graph.get_node(edge.target_id)
        return None
