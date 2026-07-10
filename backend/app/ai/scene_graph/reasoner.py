"""Educational Reasoner — the intelligence layer of the Scene Graph.

Determines:
  - What the teacher explains first
  - What should be ignored (already known)
  - What concept is missing
  - What prerequisite must be revised
  - What hint should be generated
  - What board drawing should happen
  - What homework should be assigned

Never exposes reasoning directly to the teacher. Returns structured
TeachingDecision objects that the Teacher Orchestrator consumes.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.ai.scene_graph.graph import EducationalSceneGraph
from app.ai.scene_graph.schemas import (
    BoardFocus,
    ConceptDependencies,
    EdgeType,
    MistakeCategory,
    NodeType,
    StepAnalysis,
    StudentAttempt,
    TeacherFocus,
    TeachingDecision,
    TeachingPriority,
)
from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


class EducationalReasoner:
    """The central reasoning engine that converts graph + analysis into
    structured teaching decisions.

    This is the only module the Teacher Orchestrator calls to get
    teaching guidance. No raw scene data leaks past this point.
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    def reason(
        self,
        graph: EducationalSceneGraph,
        student_attempts: Optional[list[StudentAttempt]] = None,
        concept_deps: Optional[ConceptDependencies] = None,
    ) -> TeachingDecision:
        """Run the full reasoning pipeline and return teaching decisions."""
        start = time.perf_counter()

        if student_attempts is None:
            student_attempts = []
        attempt = student_attempts[0] if student_attempts else None

        # 1. Determine teacher focus
        focus = self._determine_focus(graph, attempt, concept_deps)

        # 2. Determine teaching priorities
        priority = self._determine_priorities(graph, attempt, concept_deps)

        # 3. Analyze steps
        steps = self._analyze_steps(graph, attempt)

        # 4. Determine board focus
        board = self._determine_board_focus(graph, focus, steps)

        # 5. Generate hints
        hints = self._generate_hints(graph, attempt, focus)

        # 6. Calculate overall confidence
        confidence = self._calculate_confidence(graph, attempt)

        elapsed = int((time.perf_counter() - start) * 1000)

        decision = TeachingDecision(
            focus=focus,
            priority=priority,
            steps=steps,
            board=board,
            student_attempts=student_attempts,
            concept_dependencies=concept_deps,
            hints=hints,
            confidence=confidence,
            processing_time_ms=elapsed,
        )

        logger.info(
            'Reasoning complete in %dms: focus="%s", %d hints, confidence=%.2f',
            elapsed, focus.current_focus, len(hints), confidence,
        )
        return decision

    # ── Focus determination ──────────────────────────────────────────────

    def _determine_focus(
        self,
        graph: EducationalSceneGraph,
        attempt: Optional[StudentAttempt],
        concept_deps: Optional[ConceptDependencies],
    ) -> TeacherFocus:
        """Determine the single most important thing for the teacher."""
        # Phase 1: Check for critical mistakes
        if attempt and attempt.mistakes:
            critical = [m for m in attempt.mistakes if m.severity >= 4]
            if critical:
                mistake = critical[0]
                return TeacherFocus(
                    current_focus=f'Correct the {mistake.category.value} mistake in step {mistake.step_id}',
                    misconception=mistake.description,
                    learning_objective=f'Understand the correct approach for {mistake.concept or "this problem"}',
                    visual_focus=f'Step {mistake.step_id} in the student\'s work',
                    concept_to_teach=mistake.concept or '',
                    confidence=mistake.confidence,
                )

        # Phase 2: Check for missing prerequisites
        if concept_deps and concept_deps.missing_prerequisites:
            missing = concept_deps.missing_prerequisites[0]
            return TeacherFocus(
                current_focus=f'Revise missing prerequisite: {missing}',
                misconception=f'Student lacks understanding of {missing}',
                learning_objective=f'Build foundational knowledge in {missing}',
                revision_priority=concept_deps.missing_prerequisites[:3],
                concept_to_teach=missing,
                confidence=0.7,
            )

        # Phase 3: Check for incomplete work
        if attempt and not attempt.is_complete:
            incomplete = attempt.incomplete_steps or attempt.skipped_steps
            if incomplete:
                step_ref = incomplete[0]
                return TeacherFocus(
                    current_focus=f'Guide through incomplete step {step_ref}',
                    learning_objective='Complete the solution step by step',
                    visual_focus=f'Step {step_ref}',
                    concept_to_teach=concept_deps.topic if concept_deps else '',
                    confidence=0.6,
                )

        # Phase 4: Teach the topic normally
        topic = concept_deps.topic if concept_deps and concept_deps.topic else ''
        recommended = concept_deps.recommended_path[:3] if concept_deps else []

        return TeacherFocus(
            current_focus=f'Teach {topic}' if topic else 'Explain the problem concept',
            learning_objective=f'Master {topic}' if topic else 'Understand the solution approach',
            visual_focus='Question text and solution steps',
            concept_to_teach=topic,
            revision_priority=recommended,
            confidence=0.5,
        )

    # ── Priority determination ───────────────────────────────────────────

    def _determine_priorities(
        self,
        graph: EducationalSceneGraph,
        attempt: Optional[StudentAttempt],
        concept_deps: Optional[ConceptDependencies],
    ) -> TeachingPriority:
        """Categorize actions into immediate, next, deferred, revision, ignore."""
        immediate: list[str] = []
        next_items: list[str] = []
        deferred: list[str] = []
        revision: list[str] = []
        ignore: list[str] = []

        # Check mistakes
        if attempt:
            critical_mistakes = [m for m in attempt.mistakes if m.severity >= 3]
            for m in critical_mistakes:
                immediate.append(f'Correct {m.category.value}: {m.description[:60]}')
            minor_mistakes = [m for m in attempt.mistakes if m.severity < 3]
            for m in minor_mistakes:
                deferred.append(f'Address minor {m.category.value}: {m.description[:60]}')

        # Check prerequisites
        if concept_deps:
            for mp in concept_deps.missing_prerequisites:
                revision.append(f'Revise prerequisite: {mp}')
            if concept_deps.recommended_path:
                next_items.extend(
                    f'Teach {concept_deps.recommended_path[i]}' 
                    for i in range(min(3, len(concept_deps.recommended_path)))
                )

        # Check completed steps
        if attempt:
            for step_num in attempt.solved_steps:
                ignore.append(f'Step {step_num} — already solved correctly')
        # Check incomplete steps
        if attempt:
            for step_num in attempt.incomplete_steps:
                immediate.append(f'Complete step {step_num}')
            for step_num in attempt.skipped_steps:
                next_items.append(f'Address skipped step {step_num}')

        # Fallback: teach topic or explain solution
        if not immediate:
            if attempt and attempt.is_complete:
                immediate.append('Explain the solution and verify understanding')
            elif concept_deps and concept_deps.topic:
                immediate.append(f'Introduce topic: {concept_deps.topic}')
            else:
                immediate.append('Walk through the problem step by step')

        return TeachingPriority(
            immediate=immediate[:5],
            next=next_items[:5],
            deferred=deferred[:5],
            revision=revision[:3],
            ignore=ignore[:5],
        )

    # ── Step analysis ───────────────────────────────────────────────────

    def _analyze_steps(
        self,
        graph: EducationalSceneGraph,
        attempt: Optional[StudentAttempt],
    ) -> list[StepAnalysis]:
        """Generate teaching guidance for each solution step."""
        if not attempt or not attempt.steps:
            # Generate steps from graph
            return self._derive_steps_from_graph(graph)

        analyses: list[StepAnalysis] = []
        for step in attempt.steps:
            guidance = self._generate_step_guidance(step.content, step.status, step.mistakes)
            hint = self._generate_step_hint(step.content, step.status, step.mistakes)
            board_action = self._generate_board_action(step.content, step.status)

            analyses.append(StepAnalysis(
                step_number=step.step_number,
                description=step.content[:120],
                is_correct=step.status.value == 'correct',
                confidence=step.confidence,
                teacher_guidance=guidance,
                hint=hint,
                board_action=board_action,
                ar_visualization='',
            ))
        return analyses

    def _derive_steps_from_graph(self, graph: EducationalSceneGraph) -> list[StepAnalysis]:
        """Create step analyses from graph structure when no attempt exists."""
        question_nodes = graph.nodes_by_type(NodeType.QUESTION)
        if not question_nodes:
            return [StepAnalysis(
                step_number=1,
                description='Analyze the question and solve step by step',
                is_correct=True,
                confidence=0.5,
                teacher_guidance='Read the question carefully and identify known and unknown values.',
                hint='Start by writing what is given and what needs to be found.',
                board_action='Write the question on the board with labelled variables.',
            )]
        return []

    def _generate_step_guidance(self, content: str, status: Any, mistakes: list) -> str:
        if status.value == 'incorrect':
            return f'Review this step carefully. {mistakes[0].description[:80] if mistakes else "Check for errors."}'
        if status.value == 'incomplete':
            return 'This step is incomplete. Show the full derivation.'
        if status.value == 'skipped':
            return 'This step was skipped. Guide the student through it.'
        return 'This step is correct. Explain the reasoning behind it.'

    def _generate_step_hint(self, content: str, status: Any, mistakes: list) -> str:
        if status.value == 'incorrect':
            return f'Try again. Focus on: {mistakes[0].correction[:80] if mistakes else "the correct approach."}'
        if status.value == 'incomplete' or status.value == 'skipped':
            return 'What operation comes next? Look at what you already know.'
        return ''

    def _generate_board_action(self, content: str, status: Any) -> str:
        if status.value == 'incorrect':
            return f'Erase the incorrect working and rewrite step correctly'
        if status.value == 'skipped':
            return f'Write the missing step on the board'
        return f'Highlight this step on the board with explanation'

    # ── Board focus ──────────────────────────────────────────────────────

    def _determine_board_focus(
        self,
        graph: EducationalSceneGraph,
        focus: TeacherFocus,
        steps: list[StepAnalysis],
    ) -> BoardFocus:
        """Determine what to draw / write on the board."""
        formulas = graph.nodes_by_type(NodeType.FORMULA)
        diagrams = graph.nodes_by_type(NodeType.DIAGRAM)
        question_nodes = graph.nodes_by_type(NodeType.QUESTION)

        primary_formula = formulas[0].content if formulas else focus.concept_to_teach
        diagram_focus = diagrams[0].label if diagrams else ''
        step_highlight = steps[0].description if steps else ''
        labels = self._extract_labels(question_nodes, formulas)

        return BoardFocus(
            primary_formula=primary_formula,
            diagram_focus=diagram_focus,
            step_highlight=step_highlight,
            labels_to_write=labels,
            color_hints=['Red for mistakes', 'Green for correct steps', 'Blue for formulas'],
        )

    def _extract_labels(self, questions: list, formulas: list) -> list[str]:
        labels: list[str] = []
        for q in questions:
            labels.append(f'Question: {q.label[:50]}')
        for f in formulas[:3]:
            labels.append(f'Formula: {f.label[:40]}')
        return labels

    # ── Hint generation ──────────────────────────────────────────────────

    def _generate_hints(
        self,
        graph: EducationalSceneGraph,
        attempt: Optional[StudentAttempt],
        focus: TeacherFocus,
    ) -> list[str]:
        """Generate hints for the teacher to give the student."""
        hints: list[str] = []

        # Hint about mistakes
        if attempt:
            for mistake in attempt.mistakes[:2]:
                if mistake.correction:
                    hints.append(f'Show the student that {mistake.description} should be {mistake.correction}')

        # Hint about incomplete steps
        if attempt:
            for step in attempt.incomplete_steps[:1]:
                hints.append(f'Ask the student what comes next after step {step}')

        # Hint about prerequisites
        if focus.revision_priority:
            hints.append(f'Start with a quick revision of {focus.revision_priority[0]}')

        # Default hints
        if not hints:
            hints.append(f'Ensure the student understands {focus.concept_to_teach or "the basic concept"}')

        return hints

    # ── Confidence ───────────────────────────────────────────────────────

    def _calculate_confidence(self, graph: EducationalSceneGraph, attempt: Optional[StudentAttempt]) -> float:
        confidences: list[float] = [graph.metadata.vision_confidence]
        if attempt:
            confidences.append(attempt.confidence)
        for n in graph._collect_nodes():
            confidences.append(n.confidence)
        return sum(confidences) / len(confidences) if confidences else 0.0

    # ── AI refinement (optional gateway use) ─────────────────────────────

    async def _refine_with_ai(self, prompt: str, system_prompt: str = '') -> str:
        """Optionally use the AI gateway to refine reasoning."""
        if not self._gateway:
            return ''
        try:
            result = await self._gateway.execute(
                prompt=prompt,
                system_prompt=system_prompt or 'You are an expert educational reasoner.',
                temperature=0.3,
            )
            return result.content
        except Exception as exc:
            logger.warning('AI refinement failed: %s', exc)
            return ''
