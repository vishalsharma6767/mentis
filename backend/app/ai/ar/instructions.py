"""AR Instruction Builder — converts board actions into AR instructions.

Takes teacher board actions (write, draw line, circle, etc.) and
produces structured AR instruction objects that the frontend renders
on the virtual board / AR canvas.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.teacher.schemas import ARAction, ARAnchorType, ARAnimationType, ARShape
from app.core.logger import get_logger

log = get_logger(__name__)


class ARInstructionBuilder:
    """Converts board actions and lesson content into AR instruction sets.

    Usage::

        builder = ARInstructionBuilder()
        instructions = builder.build_from_board_actions(board_actions)
        # instructions is a list of ARAction objects
    """

    @staticmethod
    def build_from_board_actions(
        board_actions: list[Any],
        color: str = '#00D4FF',
    ) -> list[ARAction]:
        """Convert board action dicts into validated AR instructions.

        Each board action dict should have at minimum an 'action' key
        with one of: write, writeln, line, arrow, circle, underline, clear.
        """
        instructions: list[ARAction] = []

        for action in board_actions:
            if isinstance(action, dict):
                instruction = ARInstructionBuilder._convert_dict_to_ar(action, color)
                if instruction:
                    instructions.append(instruction)
            elif hasattr(action, 'dict'):
                instruction = ARInstructionBuilder._convert_dict_to_ar(action.dict(), color)
                if instruction:
                    instructions.append(instruction)

        return instructions

    @staticmethod
    def build_for_step(
        step_title: str,
        step_explanation: str,
        board_actions: Optional[list[Any]] = None,
    ) -> list[ARAction]:
        """Build AR instructions for a lesson step.

        Generates a title annotation plus any specific board actions.
        """
        instructions: list[ARAction] = []

        if step_title:
            instructions.append(ARAction(
                shape=ARShape.TEXT,
                x=0.1,
                y=0.1,
                label=step_title[:100],
                animation=ARAnimationType.FADE_IN,
                duration_ms=300,
            ))

        if board_actions:
            instructions.extend(
                ARInstructionBuilder.build_from_board_actions(board_actions),
            )

        return instructions

    @staticmethod
    def build_formula_display(
        formula: str,
        x: float = 0.3,
        y: float = 0.4,
    ) -> ARAction:
        """Create an AR instruction to display a formula prominently."""
        return ARAction(
            shape=ARShape.TEXT,
            x=x,
            y=y,
            label=formula,
            color='#FFD700',
            animation=ARAnimationType.DRAW,
            duration_ms=800,
            priority=1,
        )

    @staticmethod
    def build_highlight(
        text: str,
        x: float,
        y: float,
        width: float = 0.5,
        color: str = '#FFD700',
    ) -> ARAction:
        """Create a highlight annotation."""
        return ARAction(
            shape=ARShape.UNDERLINE,
            x=x,
            y=y,
            width=width,
            height=0.05,
            color=color,
            animation=ARAnimationType.PULSE,
            duration_ms=1000,
        )

    @staticmethod
    def _convert_dict_to_ar(action: dict, default_color: str) -> Optional[ARAction]:
        """Convert a raw board action dict to a validated ARAction."""
        try:
            action_type = str(action.get('action', 'writeln')).lower()
            color = str(action.get('color', default_color))

            if action_type == 'clear':
                return None

            if action_type in ('write', 'writeln', 'text'):
                return ARAction(
                    shape=ARShape.TEXT,
                    x=float(action.get('x', 0.1)),
                    y=float(action.get('y', 0.2)),
                    label=str(action.get('text', ''))[:200],
                    color=color,
                    animation=ARAnimationType.DRAW,
                    duration_ms=max(200, min(3000, len(str(action.get('text', ''))) * 100)),
                    priority=0,
                )

            if action_type in ('line', 'arrow'):
                return ARAction(
                    anchor_type=ARAnchorType.WORLD,
                    shape=ARShape.ARROW if action_type == 'arrow' else ARShape.LINE,
                    x=float(action.get('x1', 0)),
                    y=float(action.get('y1', 0)),
                    z=0.0,
                    x2=float(action.get('x2', 0)),
                    y2=float(action.get('y2', 0)),
                    color=color,
                    animation=ARAnimationType.DRAW,
                    duration_ms=500,
                )

            if action_type == 'circle':
                return ARAction(
                    shape=ARShape.CIRCLE,
                    x=float(action.get('x', 0)),
                    y=float(action.get('y', 0)),
                    radius=float(action.get('radius', 0.05)),
                    color=color,
                    animation=ARAnimationType.PULSE,
                    duration_ms=600,
                )

            if action_type == 'underline':
                return ARAction(
                    shape=ARShape.UNDERLINE,
                    x=float(action.get('x', 0.1)),
                    y=float(action.get('y', 0.3)),
                    width=float(action.get('width', 0.5)),
                    height=0.03,
                    color=color,
                    animation=ARAnimationType.DRAW,
                    duration_ms=300,
                )

            if action_type == 'highlight':
                return ARAction(
                    shape=ARShape.HIGHLIGHT,
                    x=float(action.get('x', 0.1)),
                    y=float(action.get('y', 0.3)),
                    width=float(action.get('width', 0.4)),
                    height=float(action.get('height', 0.06)),
                    color=color,
                    animation=ARAnimationType.GLOW,
                    duration_ms=800,
                )

        except (ValueError, TypeError) as exc:
            log.debug('ar_convert_skipped', error=str(exc)[:100])

        return None
