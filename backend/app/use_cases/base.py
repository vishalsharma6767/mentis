"""Base classes: PipelineMonitor and BaseUseCase."""

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ai.teacher.personality import TeacherPersonality
from app.core.logger import get_logger

log = get_logger(__name__)


# ── PipelineMonitor ────────────────────────────────────────────────────


@dataclass
class StageRecord:
    """Record of a single pipeline stage execution."""
    name: str
    status: str  # 'running' | 'success' | 'failed' | 'skipped'
    duration_ms: float = 0.0
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PipelineMonitor:
    """Wraps each pipeline stage with timing, status, and error capture.

    Usage::

        monitor = PipelineMonitor('req_123')
        scene = await monitor.run('vision', self._run_vision, image=True)
        plan  = await monitor.run('planner', lambda: planner.plan(v, s))
    """

    def __init__(self, request_id: str = '') -> None:
        self.request_id = request_id
        self._stages: list[StageRecord] = []

    async def run(
        self,
        name: str,
        fn: Any,
        **metadata: Any,
    ) -> Any:
        """Execute *fn*, record timing/status, and log result."""
        stage = StageRecord(name=name, status='running', metadata=metadata)
        self._stages.append(stage)
        t0 = time.monotonic()
        try:
            result = await fn() if hasattr(fn, '__call__') else fn
            stage.status = 'success'
            stage.duration_ms = round((time.monotonic() - t0) * 1000)
            log.info('pipeline_stage_ok',
                     request_id=self.request_id,
                     stage=name,
                     duration_ms=stage.duration_ms,
                     **metadata)
            return result
        except Exception as exc:
            stage.status = 'failed'
            stage.duration_ms = round((time.monotonic() - t0) * 1000)
            stage.error = str(exc)[:300]
            log.error('pipeline_stage_failed',
                      request_id=self.request_id,
                      stage=name,
                      duration_ms=stage.duration_ms,
                      error=stage.error,
                      **metadata)
            raise

    def report(self) -> dict[str, Any]:
        """Return structured report of all stages."""
        return {
            'request_id': self.request_id,
            'total_stages': len(self._stages),
            'success_count': sum(1 for s in self._stages if s.status == 'success'),
            'failed_count': sum(1 for s in self._stages if s.status == 'failed'),
            'skipped_count': sum(1 for s in self._stages if s.status == 'skipped'),
            'total_duration_ms': sum(s.duration_ms for s in self._stages),
            'stages': [
                {
                    'name': s.name,
                    'status': s.status,
                    'duration_ms': s.duration_ms,
                    'error': s.error,
                    'metadata': s.metadata,
                }
                for s in self._stages
            ],
        }

    def skip(self, name: str, reason: str = '') -> None:
        """Record a stage as skipped without executing."""
        stage = StageRecord(
            name=name,
            status='skipped',
            metadata={'reason': reason},
        )
        self._stages.append(stage)
        log.info('pipeline_stage_skipped',
                 request_id=self.request_id,
                 stage=name,
                 reason=reason)

    @property
    def last_error(self) -> Optional[str]:
        for s in reversed(self._stages):
            if s.error:
                return s.error
        return None

    @property
    def all_ok(self) -> bool:
        return all(s.status == 'success' for s in self._stages)


# ── BaseUseCase ────────────────────────────────────────────────────────

ProgressCb = Optional[callable]


class BaseUseCase:
    """Shared base for all use cases.

    Provides the teacher pipeline agents (planner, teacher, critic, coach,
    composer, dialogue, state machine) and a progress callback mechanism.
    """

    def __init__(self, personality: Optional[TeacherPersonality] = None) -> None:
        from app.ai.teacher.coach import CoachAgent
        from app.ai.teacher.critic import CriticAgent
        from app.ai.teacher.dialogue import DialogueManager
        from app.ai.teacher.planner import PlannerAgent
        from app.ai.teacher.responder import ResponseComposer
        from app.ai.teacher.teacher import TeacherAgent
        from app.ai.teacher.state_machine import TeacherStateMachine

        self.personality = personality or TeacherPersonality()
        self.planner = PlannerAgent(self.personality)
        self.teacher = TeacherAgent(self.personality)
        self.critic = CriticAgent()
        self.coach = CoachAgent(self.personality)
        self.responder = ResponseComposer()
        self.dialogue = DialogueManager()
        self.state = TeacherStateMachine()

    async def _progress(self, cb: ProgressCb, phase: str, detail: str) -> None:
        if cb:
            try:
                await cb(phase, detail)
            except Exception:
                log.warning('progress_cb_failed', phase=phase)