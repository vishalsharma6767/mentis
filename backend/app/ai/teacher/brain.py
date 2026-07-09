"""DEPRECATED — use TeacherOrchestrator from app.ai.orchestrator instead.

This file exists only for backward compatibility. The old TeacherBrain
class has been replaced by TeacherOrchestrator.

New code should use::

    from app.ai.orchestrator import TeacherOrchestrator

    orch = TeacherOrchestrator(personality)
    result = await orch.execute(context=unified_context, ...)
"""

import warnings
from typing import Any, Optional

from app.ai.orchestrator import TeacherOrchestrator
from app.ai.teacher.personality import TeacherPersonality
from app.ai.teacher.schemas import (
    ARPlan,
    CoachingDecision,
    CriticOutput,
    MemoryUpdate,
    PlannerOutput,
    QuizItem,
    SpeechPlan,
    StudentContext,
    TeacherOutput,
    TeacherResponse,
    VisionOutput,
)
from app.core.constants import TeachingLanguage
from app.core.logger import get_logger

log = get_logger(__name__)

warnings.warn(
    'TeacherBrain is deprecated. Use TeacherOrchestrator from app.ai.orchestrator instead.',
    DeprecationWarning,
    stacklevel=2,
)


class TeacherBrain:
    """DEPRECATED — use TeacherOrchestrator instead.

    Thin wrapper around TeacherOrchestrator for backward compatibility.
    """

    def __init__(
        self,
        personality: Optional[TeacherPersonality] = None,
    ) -> None:
        self._orchestrator = TeacherOrchestrator(personality)
        self.personality = self._orchestrator.personality
        self.planner = self._orchestrator.planner
        self.critic = self._orchestrator.critic
        self.coach = self._orchestrator.coach
        self.dialogue = self._orchestrator.dialogue

    async def teach(
        self,
        vision_output: VisionOutput,
        student: StudentContext,
        student_message: str = '',
        history: Optional[list[dict[str, Any]]] = None,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        provider: str = 'groq',
    ) -> TeacherResponse:
        """Run the pipeline. Delegates to TeacherOrchestrator."""
        from app.ai.context import UnifiedStudentContext
        from app.ai.teacher.schemas import VisionOutput as VO
        from app.core.constants import ConfidenceLevel

        context = UnifiedStudentContext(
            profile=None,  # type: ignore
            vision=vision_output or VO(raw_text=student_message),
            session=None,  # type: ignore
            knowledge=None,  # type: ignore
            session_history=None,  # type: ignore
            mistakes=None,  # type: ignore
            revision=None,  # type: ignore
        )

        return await self._orchestrator.execute(
            context=context,
            student_message=student_message,
            language=language,
            provider=None,
        )

    async def continue_teaching(
        self,
        student_message: str,
        student: StudentContext,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        provider: str = 'groq',
    ) -> TeacherResponse:
        """Continue an existing lesson."""
        vision = VisionOutput(raw_text=student_message)
        return await self.teach(vision, student, student_message, language=language, provider=provider)

    def add_signal(self, signal_type: str, detail: str = '', confidence: float = 0.5) -> None:
        """Inject a student signal."""
        self.coach.add_signal(signal_type=signal_type, detail=detail, confidence=confidence)
