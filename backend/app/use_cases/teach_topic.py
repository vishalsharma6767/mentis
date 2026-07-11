"""TeachTopicUseCase — single entry point for Teach Me (topic-based lesson)."""

import time
from typing import Optional

from app.ai.context import (
    UnifiedStudentContext,
    StudentProfile,
    VisionContext,
    SessionContext,
)
from app.ai.gateway import LLMProvider
from app.ai.teacher.schemas import TeacherResponse
from app.core.constants import Difficulty, Subject, TeachingLanguage
from app.core.logger import get_logger
from app.use_cases.base import BaseUseCase, PipelineMonitor, ProgressCb
from app.use_cases.solve_doubt import SolveDoubtUseCase

log = get_logger(__name__)


class TeachTopicUseCase(BaseUseCase):
    """Teach a full lesson on a given topic."""

    async def execute(
        self,
        topic: str,
        level: str = 'intermediate',
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
        provider: Optional[LLMProvider] = None,
        progress_cb: ProgressCb = None,
    ) -> tuple[TeacherResponse, dict]:
        monitor = PipelineMonitor(request_id=f'lesson_{int(time.time())}')
        log.info('usecase_teach_topic_start', topic=topic, level=level)

        parsed_level = _parse_level(level)
        context = UnifiedStudentContext(
            profile=StudentProfile(
                user_id='anonymous',
                level=parsed_level,
                preferred_language=language,
            ),
            vision=VisionContext(
                raw_text=f'Teach me {topic}',
                subject=Subject.GENERAL,
                difficulty=parsed_level,
                topics=[topic],
            ),
            session=SessionContext(
                session_id=f'ses_{int(time.time())}',
                session_started_at=time.time(),
            ),
        )

        # Reuse the same teaching pipeline from SolveDoubtUseCase
        solver = SolveDoubtUseCase(self.personality)
        response, _ = await solver._run_teaching_pipeline(
            context=context,
            student_message=f'Teach me {topic}',
            language=language,
            provider=provider,
            progress_cb=progress_cb,
            monitor=monitor,
        )

        log.info('usecase_teach_topic_end', topic=topic,
                 explanation_len=len(response.explanation))
        return response, monitor.report()


def _parse_level(level: str) -> Difficulty:
    try:
        return Difficulty(level)
    except ValueError:
        return Difficulty.INTERMEDIATE