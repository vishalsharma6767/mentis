"""Mentis V1 API — Teach & Doubt endpoints.

Integrates the Teacher Orchestrator, Vision Intelligence, Scene Graph, and Memory into
the two core V1 experiences:
  - Solve My Doubt  (POST /api/v1/teach/doubt)
  - Teach Me        (POST /api/v1/teach/lesson)
  - Stream          (WebSocket /api/v1/teach/stream)
"""

import json
import time
import asyncio
from typing import Any, Optional

from fastapi import APIRouter, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.ai.teacher.schemas import TeacherResponse
from app.ai.teacher.personality import TeacherPersonality
from app.core.events import EventBus, EventType
from app.core.logger import get_logger
from app.use_cases.solve_doubt import SolveDoubtUseCase
from app.use_cases.teach_topic import TeachTopicUseCase

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
    type: str
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
    analogy: str = ''
    lesson_plan: Optional[dict] = None
    concepts: list[str] = []
    ask_doubts: bool = False
    session_complete: bool = False
    scene_graph: Optional[dict] = None
    teaching_decision: Optional[dict] = None


# ── Singleton wiring ─────────────────────────────────────────────────────────

_personality: Optional[TeacherPersonality] = None
_solve_doubt: Optional[SolveDoubtUseCase] = None
_teach_topic: Optional[TeachTopicUseCase] = None
_event_bus: Optional[EventBus] = None


def _get_personality() -> TeacherPersonality:
    global _personality
    if _personality is None:
        _personality = TeacherPersonality()
    return _personality


def _get_solve_doubt() -> SolveDoubtUseCase:
    global _solve_doubt
    if _solve_doubt is None:
        _solve_doubt = SolveDoubtUseCase(personality=_get_personality())
    return _solve_doubt


def _get_teach_topic() -> TeachTopicUseCase:
    global _teach_topic
    if _teach_topic is None:
        _teach_topic = TeachTopicUseCase(personality=_get_personality())
    return _teach_topic


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
        analogy=resp.analogy,
        lesson_plan=resp.lesson_plan.model_dump() if resp.lesson_plan and hasattr(resp.lesson_plan, 'model_dump') else None,
        ask_doubts=resp.ask_doubts,
        session_complete=resp.session_complete,
    )


# ── Solve My Doubt (text) ────────────────────────────────────────────────────

@router.post('/teach/doubt', response_model=TeachResponse)
async def solve_doubt(request: DoubtRequest):
    """Solve My Doubt — teach the solution interactively."""
    usecase = _get_solve_doubt()
    session_id = f'ses_{int(time.time())}'

    try:
        result, report = await usecase.execute(
            text=request.content,
            mode=request.mode,
            level=request.level,
        )

        log.info('doubt_complete', report=report)

        await _get_event_bus().publish_sync(
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


# ── Solve My Doubt (image) ───────────────────────────────────────────────────

@router.post('/teach/doubt/image', response_model=TeachResponse)
async def solve_doubt_with_image(
    file: UploadFile = File(...),
    mode: str = Form('math'),
    level: str = Form('intermediate'),
    student_id: Optional[str] = Form(None),
):
    """Solve My Doubt from an image — runs Vision pipeline then teaches."""
    usecase = _get_solve_doubt()
    session_id = f'ses_{int(time.time())}'

    try:
        image_bytes = await file.read()
        result, report = await usecase.execute(
            image_bytes=image_bytes,
            mode=mode,
            level=level,
        )

        log.info('doubt_image_complete', report=report)

        teach_resp = _response_to_teach(result, session_id)

        await _get_event_bus().publish_sync(
            event_type=EventType.LESSON_STARTED,
            data={
                'type': 'doubt_image',
                'content_len': len(result.explanation),
                'student_id': student_id,
                'session_id': session_id,
            },
            source='api.v1.tutor',
            correlation_id=student_id or session_id,
        )

        return teach_resp

    except HTTPException:
        raise
    except Exception as exc:
        log.error('doubt_image_failed', error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# ── Teach Me (Full Lesson) ────────────────────────────────────────────────────

@router.post('/teach/lesson', response_model=TeachResponse)
async def teach_lesson(request: LessonRequest):
    """Teach Me — create an entire interactive classroom lesson."""
    usecase = _get_teach_topic()
    session_id = f'ses_{int(time.time())}'

    try:
        result, report = await usecase.execute(
            topic=request.topic,
            level=request.level,
        )
        log.info('lesson_complete', topic=request.topic, report=report)
        return _response_to_teach(result, session_id)

    except Exception as exc:
        log.error('lesson_failed', topic=request.topic, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# ── Streaming Teaching (WebSocket) ────────────────────────────────────────────

@router.websocket('/teach/stream')
async def teach_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming teaching."""
    await websocket.accept()
    session_id = f'stream_{int(time.time())}'

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get('type', '')

            if msg_type == 'doubt':
                await _stream_doubt(
                    websocket,
                    msg.get('content', ''),
                    msg.get('mode', 'math'),
                    msg.get('level', 'intermediate'),
                    session_id,
                )

            elif msg_type == 'doubt_image':
                await _send_json(websocket, {'type': 'processing', 'phase': 'analyzing_image'})
                try:
                    image_b64 = msg.get('image_base64', '')
                    image_bytes = _decode_base64_image(image_b64)
                    await _stream_doubt_image(
                        websocket, image_bytes,
                        msg.get('mode', 'math'),
                        msg.get('level', 'intermediate'),
                        session_id,
                    )
                except HTTPException as exc:
                    await _send_json(websocket, {'type': 'error', 'message': exc.detail, 'code': exc.status_code})
                except Exception as exc:
                    await _send_json(websocket, {'type': 'error', 'message': str(exc)[:200]})

            elif msg_type == 'lesson':
                await _stream_lesson(
                    websocket,
                    msg.get('topic', ''),
                    msg.get('level', 'intermediate'),
                    session_id,
                )

            elif msg_type == 'student_response':
                await _send_json(websocket, {'type': 'thinking', 'duration_ms': 600})
                await _stream_doubt(
                    websocket,
                    msg.get('text', ''),
                    msg.get('mode', 'math'),
                    msg.get('level', 'intermediate'),
                    session_id,
                )

            elif msg_type == 'cancel':
                await _send_json(websocket, {'type': 'cancelled'})
                break

    except WebSocketDisconnect:
        log.info('ws_disconnected', session_id=session_id)
    except Exception as exc:
        log.error('ws_error', session_id=session_id, error=str(exc))
        try:
            await _send_json(websocket, {'type': 'error', 'message': str(exc)[:200]})
        except Exception:
            pass


async def _stream_doubt(
    ws: WebSocket,
    content: str,
    mode: str,
    level: str,
    session_id: str,
) -> None:
    """Handle 'doubt' WS message — text only."""
    usecase = _get_solve_doubt()
    async def _cb(phase: str, detail: str) -> None:
        try:
            await _send_json(ws, {'type': 'processing', 'phase': phase, 'detail': detail})
        except Exception:
            pass
    result, report = await usecase.execute(
        text=content, mode=mode, level=level, progress_cb=_cb,
    )
    log.info('ws_doubt_complete', session_id=session_id, report=report)
    await _stream_response(ws, result, session_id)


async def _stream_doubt_image(
    ws: WebSocket,
    image_bytes: bytes,
    mode: str,
    level: str,
    session_id: str,
) -> None:
    """Handle 'doubt_image' WS message."""
    usecase = _get_solve_doubt()
    async def _cb(phase: str, detail: str) -> None:
        try:
            await _send_json(ws, {'type': 'processing', 'phase': phase, 'detail': detail})
        except Exception:
            pass
    result, report = await usecase.execute(
        image_bytes=image_bytes, mode=mode, level=level, progress_cb=_cb,
    )
    vision_dict = getattr(usecase, 'last_vision_dict', None)
    log.info('ws_doubt_image_complete', session_id=session_id, report=report)
    await _stream_response(ws, result, session_id, vision_dict=vision_dict)


async def _stream_lesson(
    ws: WebSocket,
    topic: str,
    level: str,
    session_id: str,
) -> None:
    """Handle 'lesson' WS message."""
    usecase = _get_teach_topic()
    async def _cb(phase: str, detail: str) -> None:
        try:
            await _send_json(ws, {'type': 'processing', 'phase': phase, 'detail': detail})
        except Exception:
            pass
    result, report = await usecase.execute(
        topic=topic, level=level, progress_cb=_cb,
    )
    log.info('ws_lesson_complete', session_id=session_id, report=report)
    await _stream_response(ws, result, session_id)


async def _stream_response(
    ws: WebSocket,
    result: TeacherResponse,
    session_id: str,
    vision_dict: Optional[dict] = None,
) -> None:
    """Stream a TeacherResponse over the WebSocket."""
    await _send_json(ws, {'type': 'thinking', 'duration_ms': 400})

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

    if result.key_points:
        await _send_json(ws, {'type': 'key_points', 'points': result.key_points})

    if result.examples:
        await _send_json(ws, {'type': 'examples', 'examples': result.examples})

    if result.checkpoints:
        await _send_json(ws, {'type': 'checkpoints', 'points': result.checkpoints})

    if result.analogy:
        await _send_json(ws, {'type': 'analogy', 'text': result.analogy})

    if result.lesson_plan:
        lp = result.lesson_plan
        await _send_json(ws, {
            'type': 'lesson_plan',
            'topic': lp.topic,
            'subject': lp.subject.value if hasattr(lp.subject, 'value') else str(lp.subject),
            'difficulty': lp.difficulty.value if hasattr(lp.difficulty, 'value') else str(lp.difficulty),
            'prerequisites': lp.prerequisite_topics,
            'key_concepts': lp.key_concepts,
            'total_steps': len(lp.steps),
            'estimated_duration': lp.estimated_total_duration,
            'homework': [h.model_dump() if hasattr(h, 'model_dump') else {'title': h.title, 'description': h.description} for h in lp.homework],
        })

    if result.quiz:
        q = result.quiz.model_dump() if hasattr(result.quiz, 'model_dump') else result.quiz
        await _send_json(ws, {'type': 'quiz', 'questions': q})

    if result.ask_doubts:
        await _send_json(ws, {'type': 'question', 'text': 'Kya samajh mein aaya? Koi doubt hai?', 'wait': True})

    if result.memory_update:
        m = result.memory_update.model_dump() if hasattr(result.memory_update, 'model_dump') else result.memory_update
        await _send_json(ws, {'type': 'memory', **m})

    if vision_dict:
        topics = vision_dict.get('topics', [])
        if topics:
            await _send_json(ws, {'type': 'concepts', 'topics': topics})
        await _send_json(ws, {'type': 'scene', **vision_dict})

    recommendations = []
    if result.memory_update and result.memory_update.revision_suggestions:
        recommendations = result.memory_update.revision_suggestions[:5]

    if result.session_complete:
        await _send_json(ws, {'type': 'session_complete', 'session_id': session_id, 'recommendations': recommendations})

    await _send_json(ws, {'type': 'done', 'session_id': session_id, 'recommendations': recommendations})


def _decode_base64_image(b64: str) -> bytes:
    import base64
    if ',' in b64:
        b64 = b64.split(',')[1]
    return base64.b64decode(b64)


async def _send_json(ws: WebSocket, data: dict) -> None:
    try:
        await ws.send_json(data)
    except Exception:
        pass
