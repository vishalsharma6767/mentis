"""AR Renderer — generates board action sequences for the frontend canvas.

Produces validated board action objects that the frontend interprets
as pen strokes on the virtual AR board. Supports writing text, drawing
shapes, highlighting, and clearing.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.ar.instructions import ARInstructionBuilder
from app.ai.teacher.schemas import ARAction, ARAnimationType, ARShape, BoardAction
from app.core.logger import get_logger

log = get_logger(__name__)


class ARRenderer:
    """Builds board action JSON for the AR pen canvas.

    Usage::

        renderer = ARRenderer()
        actions = renderer.render_step(step_title, step_explanation)
        # actions is a list of ARAction objects ready for the frontend
    """

    def __init__(self) -> None:
        self._current_y = 0.1
        self._line_count = 0

    def reset(self) -> None:
        """Reset the renderer state for a new board."""
        self._current_y = 0.1
        self._line_count = 0

    def render_step(
        self,
        title: str,
        explanation: str,
        board_actions: Optional[list[Any]] = None,
    ) -> list[ARAction]:
        """Render a full lesson step as AR board actions.

        Args:
            title: The step title (written at the top).
            explanation: The step explanation (written line by line).
            board_actions: Optional pre-defined board actions.

        Returns:
            List of validated ARAction objects.
        """
        self.reset()
        instructions: list[ARAction] = []

        # Title
        if title:
            instructions.append(ARAction(
                shape=ARShape.TEXT,
                x=0.05,
                y=0.05,
                label=title[:100],
                color='#00D4FF',
                animation=ARAnimationType.FADE_IN,
                duration_ms=300,
                priority=0,
            ))
            self._advance_line()

        # Explanation lines
        if explanation:
            for line in explanation.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if self._line_count >= 12:
                    break
                instructions.append(ARAction(
                    shape=ARShape.TEXT,
                    x=0.05,
                    y=self._current_y,
                    label=line[:100],
                    color='#FFFFFF',
                    animation=ARAnimationType.DRAW,
                    duration_ms=min(2000, len(line) * 80),
                    priority=5,
                ))
                self._advance_line()

        # Additional board actions
        if board_actions:
            instructions.extend(
                ARInstructionBuilder.build_from_board_actions(board_actions),
            )

        return instructions

    def render_formula(self, formula: str, x: float = 0.3, y: float = 0.4) -> ARAction:
        """Render a formula prominently on the board."""
        return ARInstructionBuilder.build_formula_display(formula, x, y)

    def render_highlight(
        self,
        text: str,
        x: float = 0.1,
        y: float = 0.3,
        width: float = 0.5,
    ) -> ARAction:
        """Render a highlight over text."""
        return ARInstructionBuilder.build_highlight(text, x, y, width)

    def render_clear(self) -> ARAction:
        """Render a board-clear action."""
        self.reset()
        return ARAction(
            shape=ARShape.TEXT,
            x=0,
            y=0,
            label='CLEAR',
            duration_ms=0,
        )

    def _advance_line(self) -> None:
        self._line_count += 1
        self._current_y = 0.08 + self._line_count * 0.07
