"""Mentis V1 API — Teach & Doubt endpoints.

Integrates the Teacher Orchestrator, Vision Intelligence, and Memory into
the two core V1 experiences:
  - Solve My Doubt  (POST /api/v1/teach/doubt)
  - Teach Me        (POST /api/v1/teach/lesson)
  - Stream          (WebSocket /api/v1/teach/stream)
"""

import json
import time
import asyncio
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.context import (
    UnifiedStudentContext,
    StudentProfile,
    VisionContext,
    SessionContext,
    ContextEngine,
)
from app.ai.orchestrator import TeacherOrchestrator
from app.ai.teacher.schemas import TeacherResponse, VisionOutput
from app.ai.teacher.personality import TeacherPersonality
from app.services.vision import vision_service
from app.core.events import EventBus, EventType
from app.core.constants import Subject, Difficulty, TeachingLanguage
from app.core.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix='/api/v1', tags=['v1'])


# ── Request / Response Models ────────────────────────────────────────────────

class DoubtRequest(BaseModel):
    content: str
    mode: str = 'math'
    level: str = 'intermediate'
    student_id: Optional[str] = None


class LessonRequest(BaseModel):
    topic: str
    level: str = 'intermediate'
    mode: str = 'math'
    student_id: Optional[str] = None


class Chunk(BaseModel):
    """A single streamed teaching chunk for the REST fallback."""
    type: str  # 'speech' | 'board' | 'pointer' | 'question' | 'homework' | 'quiz' | 'done'
    data: dict


class TeachResponse(BaseModel):
    session_id: str
    explanation: str = ''
    board_actions: list = []
    ar_instructions: list = []
    speech_action: Optional[dict] = None
    quiz: Optional[dict] = None
    homework: Optional[list] = None
    memory_update: Optional[dict] = None
    key_points: list[str] = []
    checkpoints: list[str] = []
    examples: list[str] = []
    ask_doubts: bool = False
    session_complete: bool = False


# ── Singleton wiring ─────────────────────────────────────────────────────────

_orchestrator: Optional[TeacherOrchestrator] = None
_event_bus: Optional[EventBus] = None


def _get_orchestrator() -> TeacherOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        personality = TeacherPersonality()
        _orchestrator = TeacherOrchestrator(personality=personality)
    return _orchestrator


def _get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def _response_to_teach(resp: TeacherResponse, session_id: str) -> TeachResponse:
    return TeachResponse(
        session_id=session_id,
        explanation=resp.explanation,
        board_actions=[a.model_dump() if hasattr(a, 'model_dump') else a for a in resp.board_actions],
        ar_instructions=[a.model_dump() if hasattr(a, 'model_dump') else a for a in resp.ar_instructions],
        speech_action=resp.speech.model_dump() if resp.speech and hasattr(resp.speech, 'model_dump') else None,
        quiz=resp.quiz.model_dump() if resp.quiz and hasattr(resp.quiz, 'model_dump') else None,
        memory_update=resp.memory_update.model_dump() if resp.memory_update and hasattr(resp.memory_update, 'model_dump') else None,
        key_points=resp.key_points,
        checkpoints=resp.checkpoints,
        examples=resp.examples,
        ask_doubts=resp.ask_doubts,
        session_complete=resp.session_complete,
    )


def _doubt_from_content(content: str, mode: str = 'math', level: str = 'intermediate') -> UnifiedStudentContext:
    return UnifiedStudentContext(
        profile=StudentProfile(
            user_id='anonymous',
            level=Difficulty(level) if level in ('beginner', 'intermediate', 'advanced') else Difficulty.INTERMEDIATE,
            preferred_language=TeachingLanguage.HINGLISH,
        ),
        vision=VisionContext(
            raw_text=content,
            subject=Subject.MATH if mode == 'math' else Subject.GENERAL,
            difficulty=Difficulty(level) if level in ('beginner', 'intermediate', 'advanced') else Difficulty.INTERMEDIATE,
        ),
        session=SessionContext(
            session_id=f'ses_{int(time.time())}',
            session_started_at=time.time(),
        ),
    )


def _lesson_from_topic(topic: str, level: str = 'intermediate') -> UnifiedStudentContext:
    return UnifiedStudentContext(
        profile=StudentProfile(
            user_id='anonymous',
            level=Difficulty(level) if level in ('beginner', 'intermediate', 'advanced') else Difficulty.INTERMEDIATE,
            preferred_language=TeachingLanguage.HINGLISH,
        ),
        vision=VisionContext(
            raw_text=f'Teach me {topic}',
            subject=Subject.GENERAL,
            difficulty=Difficulty(level) if level in ('beginner', 'intermediate', 'advanced') else Difficulty.INTERMEDIATE,
            topics=[topic],
        ),
        session=SessionContext(
            session_id=f'ses_{int(time.time())}',
            session_started_at=time.time(),
        ),
    )


# ── Solve My Doubt ───────────────────────────────────────────────────────────

@router.post('/teach/doubt', response_model=TeachResponse)
async def solve_doubt(request: DoubtRequest):
    """Solve My Doubt — teach the solution interactively."""
    orchestrator = _get_orchestrator()
    event_bus = _get_event_bus()
    session_id = f'ses_{int(time.time())}'

    try:
        context = _doubt_from_content(request.content, request.mode, request.level)
        result: TeacherResponse = await orchestrator.execute(
            context=context,
            student_message=request.content,
        )

        await event_bus.publish_sync(
            event_type=EventType.LESSON_STARTED,
            data={
                'type': 'doubt',
                'content': request.content[:200],
                'student_id': request.student_id,
                'session_id': session_id,
            },
            source='api.v1.tutor',
            correlation_id=request.student_id or session_id,
        )

        return _response_to_teach(result, session_id)

    except Exception as exc:
        log.error('doubt_failed', error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/teach/doubt/image', response_model=TeachResponse)
async def solve_doubt_with_image(
    file: UploadFile = File(...),
    mode: str = Form('math'),
    level: str = Form('intermediate'),
    student_id: Optional[str] = Form(None),
):
    """Solve My Doubt from an image — runs Vision pipeline then teaches."""
    orchestrator = _get_orchestrator()
    session_id = f'ses_{int(time.time())}'

    try:
        image_bytes = await file.read()
        # Vision pipeline
        vision_result = tutor_service.extract_problem(image_bytes, mode)
        if not vision_result or not vision_result.get('content'):
            raise HTTPException(status_code=422, detail='Could not extract problem from image')

        context = _doubt_from_content(vision_result['content'], mode, level)
        result: TeacherResponse = await orchestrator.execute(
            context=context,
            student_message=vision_result['content'],
        )

        return _response_to_teach(result, session_id)

    except HTTPException:
        raise
    except Exception as exc:
        log.error('doubt_image_failed', error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# ── Teach Me (Full Lesson) ────────────────────────────────────────────────────

@router.post('/teach/lesson', response_model=TeachResponse)
async def teach_lesson(request: LessonRequest):
    """Teach Me — create an entire interactive classroom lesson."""
    orchestrator = _get_orchestrator()
    session_id = f'ses_{int(time.time())}'

    try:
        context = _lesson_from_topic(request.topic, request.level)
        result: TeacherResponse = await orchestrator.execute(
            context=context,
            student_message=f'Teach me {request.topic}',
        )

        return _response_to_teach(result, session_id)

    except Exception as exc:
        log.error('lesson_failed', topic=request.topic, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# ── Streaming Teaching (WebSocket) ────────────────────────────────────────────

@router.websocket('/teach/stream')
async def teach_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming teaching.

    Client → Server:
      { type: 'doubt', content: '...', mode: 'math', level: 'intermediate' }
      { type: 'lesson', topic: '...', level: 'intermediate' }
      { type: 'student_response', text: '...' }
      { type: 'cancel' }

    Server → Client (streamed):
      { type: 'speech', text: '...', emotion: {...} }
      { type: 'board', text: '...', action: 'write' }
      { type: 'pointer', action: 'point', x: ..., y: ... }
      { type: 'thinking', duration_ms: 800 }
      { type: 'question', text: '...' }
      { type: 'homework', problems: [...] }
      { type: 'quiz', questions: [...] }
      { type: 'done', session_id: '...' }
      { type: 'error', message: '...' }
    """
    await websocket.accept()
    orchestrator = _get_orchestrator()
    session_id = f'stream_{int(time.time())}'

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get('type', '')

            if msg_type == 'doubt':
                context = _doubt_from_content(
                    msg.get('content', ''),
                    msg.get('mode', 'math'),
                    msg.get('level', 'intermediate'),
                )
                await _run_and_stream(orchestrator, websocket, context, session_id)

            elif msg_type == 'lesson':
                context = _lesson_from_topic(
                    msg.get('topic', ''),
                    msg.get('level', 'intermediate'),
                )
                await _run_and_stream(orchestrator, websocket, context, session_id)

            elif msg_type == 'student_response':
                await _send_json(websocket, {'type': 'thinking', 'duration_ms': 800})
                context = _doubt_from_content(msg.get('text', ''))
                await _run_and_stream(orchestrator, websocket, context, session_id)

            elif msg_type == 'cancel':
                await _send_json(websocket, {'type': 'cancelled'})
                break

    except WebSocketDisconnect:
        log.info('ws_disconnected', session_id=session_id)
    except Exception as exc:
        log.error('ws_error', session_id=session_id, error=str(exc))
        try:
            await _send_json(websocket, {'type': 'error', 'message': str(exc)})
        except Exception:
            pass


async def _run_and_stream(
    orchestrator: TeacherOrchestrator,
    ws: WebSocket,
    context: UnifiedStudentContext,
    session_id: str,
) -> None:
    """Run orchestrator and stream each output element."""
    await _send_json(ws, {'type': 'thinking', 'duration_ms': 600})
    await asyncio.sleep(0.3)

    result: TeacherResponse = await orchestrator.execute(
        context=context,
        student_message=context.vision.raw_text,
    )

    if result.explanation:
        await _send_json(ws, {
            'type': 'speech',
            'text': result.explanation,
            'emotion': {'emotion': 'calmness', 'intensity': 0.5, 'speech_style': 'warm'},
        })

    for action in result.board_actions:
        d = action.model_dump() if hasattr(action, 'model_dump') else action
        await _send_json(ws, {'type': 'board', **d})
        await asyncio.sleep(0.05)

    for instr in result.ar_instructions:
        d = instr.model_dump() if hasattr(instr, 'model_dump') else instr
        await _send_json(ws, {'type': 'pointer', **d})

    if result.quiz:
        q = result.quiz.model_dump() if hasattr(result.quiz, 'model_dump') else result.quiz
        await _send_json(ws, {'type': 'quiz', 'questions': q})

    if result.memory_update:
        m = result.memory_update.model_dump() if hasattr(result.memory_update, 'model_dump') else result.memory_update
        await _send_json(ws, {'type': 'memory', **m})

    await _send_json(ws, {'type': 'done', 'session_id': session_id})


async def _send_json(ws: WebSocket, data: dict) -> None:
    try:
        await ws.send_json(data)
    except Exception:
        pass
