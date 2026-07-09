"""Compatibility adapter — bridges EducationalScene to existing VisionOutput.

The existing Teacher Orchestrator expects a ``VisionOutput``-compatible
dict with ``raw_text``, ``subject``, ``difficulty``, ``topics``, etc.

This adapter converts an ``EducationalScene`` to that format without
modifying any Phase 1 or Phase 2 code. The adapter is a thin shim
that the input layer uses before passing data to the orchestrator.

This is the ONLY file that touches both Phase 2's VisionOutput schema
and Phase 3's EducationalScene. No existing code is modified.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.vision_intelligence.schema import EducationalScene
from app.core.constants import Difficulty, Subject
from app.core.logger import get_logger

log = get_logger(__name__)


class VisionAdapter:
    """Converts EducationalScene → VisionOutput for orchestrator compatibility.

    Usage::

        adapter = VisionAdapter()
        vision_output = adapter.to_vision_output(scene)
        # vision_output is a dict matching VisionOutput fields
        # orchestrator can consume it without changes
    """

    @staticmethod
    def to_vision_output(scene: EducationalScene) -> dict[str, Any]:
        """Convert a rich EducationalScene to the flat VisionOutput format.

        Args:
            scene: The EducationalScene produced by the Vision Pipeline.

        Returns:
            Dict matching the existing ``VisionOutput`` schema fields:
              - raw_text: Concise text representation of the scene
              - subject: Detected subject
              - difficulty: Estimated difficulty
              - topics: Detected concepts/topics
              - problem_type: Type of problem
              - detected_elements: What elements were found
              - diagram_type: Type of diagram if present
              - formulas: List of formula strings
              - confidence: Overall confidence
        """
        raw_text = VisionAdapter._build_raw_text(scene)

        return {
            'raw_text': raw_text,
            'subject': VisionAdapter._resolve_subject(scene.subject),
            'difficulty': VisionAdapter._resolve_difficulty(scene.difficulty),
            'topics': scene.concepts or ([scene.topic] if scene.topic else []),
            'problem_type': VisionAdapter._detect_problem_type(scene),
            'detected_elements': VisionAdapter._detect_elements(scene),
            'diagram_type': VisionAdapter._detect_diagram_type(scene),
            'formulas': [f.latex or f.plain_text for f in scene.formulas],
            'confidence': scene.confidence.overall,
        }

    @staticmethod
    def to_vision_context(scene: EducationalScene) -> dict[str, Any]:
        """Convert scene to the VisionContext format used by Context Engine.

        Returns a dict that can be merged into ``UnifiedStudentContext.vision``.
        """
        return {
            'raw_text': VisionAdapter._build_raw_text(scene),
            'subject': scene.subject.value if hasattr(scene.subject, 'value') else str(scene.subject),
            'difficulty': scene.difficulty.value if hasattr(scene.difficulty, 'value') else str(scene.difficulty),
            'topics': scene.concepts or ([scene.topic] if scene.topic else []),
            'problem_type': VisionAdapter._detect_problem_type(scene),
            'detected_elements': VisionAdapter._detect_elements(scene),
            'diagram_type': VisionAdapter._detect_diagram_type(scene),
            'formulas': [f.latex or f.plain_text for f in scene.formulas],
            'questions': [
                {
                    'text': q.question_text,
                    'answer': q.student_answer,
                    'mistakes': [
                        {'type': m.mistake_type.value, 'text': m.text}
                        for m in q.mistakes
                    ],
                }
                for q in scene.questions
            ],
            'teacher_focus': scene.teacher_focus,
            'already_solved': scene.already_solved,
            'confidence': scene.confidence.overall,
        }

    @staticmethod
    def needs_recapture(scene: EducationalScene) -> bool:
        """Check if the scene quality requires a new image capture."""
        return (
            not scene.image_quality.is_acceptable or
            not scene.confidence.is_reliable() or
            (not scene.text_blocks and not scene.questions)
        )

    @staticmethod
    def get_recapture_message(scene: EducationalScene) -> str:
        """Generate a user-facing recapture request message."""
        if not scene.image_quality.is_acceptable:
            reason = scene.image_quality.rejection_reason or 'image quality too low'
            if 'blurr' in reason.lower():
                return 'Beta, image thoda blur hai. Kripya dobara click karein — phone ko stable rakhein.'
            if 'dark' in reason.lower():
                return 'Beta, image bahut dark hai. Kripya ache light mein photo len.'
            return f'Beta, {reason}. Kripya dobara photo len.'
        if not scene.confidence.is_reliable():
            return 'Beta, image clear nahi hai. Kripya page ko sahi se dikha kar dobara photo len.'
        return ''

    # ── Private helpers ─────────────────────────────────────────────────

    @staticmethod
    def _build_raw_text(scene: EducationalScene) -> str:
        """Build a concise text representation of the scene."""
        parts: list[str] = []

        for q in scene.questions:
            parts.append(f'Question: {q.question_text}')
            if q.student_answer:
                parts.append(f'Answer: {q.student_answer}')
            if q.mistakes:
                for m in q.mistakes:
                    parts.append(f'Mistake ({m.mistake_type.value}): {m.text}')

        for f in scene.formulas:
            parts.append(f.latex or f.plain_text)

        for d in scene.diagrams:
            parts.append(f'[{d.diagram_type.value}] {d.description}')

        for g in scene.graphs:
            parts.append(f'Graph: {g.trend_description}')

        for tb in scene.text_blocks:
            if tb.text and tb.text not in '\n'.join(parts):
                parts.append(tb.text)

        return '\n'.join(parts) if parts else ''

    @staticmethod
    def _detect_problem_type(scene: EducationalScene) -> str:
        if scene.formulas:
            return 'equation'
        if scene.diagrams:
            return 'diagram'
        if scene.graphs:
            return 'graph'
        for q in scene.questions:
            lower = q.question_text.lower()
            if 'diagram' in lower or 'graph' in lower:
                return 'diagram' if 'diagram' in lower else 'graph'
        return 'general'

    @staticmethod
    def _detect_elements(scene: EducationalScene) -> list[str]:
        elements: list[str] = ['text']
        if scene.formulas:
            elements.append('equation')
        if scene.diagrams:
            elements.append('diagram')
        if scene.graphs:
            elements.append('graph')
        if scene.tables:
            elements.append('table')
        return elements

    @staticmethod
    def _detect_diagram_type(scene: EducationalScene) -> Optional[str]:
        if not scene.diagrams:
            if scene.graphs:
                return 'graph'
            return None
        return scene.diagrams[0].diagram_type.value

    @staticmethod
    def _resolve_subject(subject: Subject) -> Subject:
        return subject if isinstance(subject, Subject) else Subject.GENERAL

    @staticmethod
    def _resolve_difficulty(difficulty: Difficulty) -> Difficulty:
        return difficulty if isinstance(difficulty, Difficulty) else Difficulty.INTERMEDIATE
