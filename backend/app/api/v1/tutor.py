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
from io import BytesIO

import numpy as np
from PIL import Image

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
from app.ai.vision_intelligence.pipeline import VisionPipeline
from app.ai.vision_intelligence.adapter import VisionAdapter
from app.ai.scene_graph.integration import SceneGraphIntegration
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
    ask_doubts: bool = False
    session_complete: bool = False
    concepts: list[str] = []
    scene_graph: Optional[dict] = None
    teaching_decision: Optional[dict] = None


# ── Singleton wiring ─────────────────────────────────────────────────────────

_orchestrator: Optional[TeacherOrchestrator] = None
_event_bus: Optional[EventBus] = None
_vision_pipeline: Optional[VisionPipeline] = None
_scene_graph: Optional[SceneGraphIntegration] = None


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


def _get_vision_pipeline() -> VisionPipeline:
    global _vision_pipeline
    if _vision_pipeline is None:
        _vision_pipeline = VisionPipeline()
    return _vision_pipeline


def _get_scene_graph() -> SceneGraphIntegration:
    global _scene_graph
    if _scene_graph is None:
        _scene_graph = SceneGraphIntegration()
    return _scene_graph


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


def _parse_level(level: str) -> Difficulty:
    try:
        return Difficulty(level)
    except ValueError:
        return Difficulty.INTERMEDIATE


def _doubt_from_content(content: str, mode: str = 'math', level: str = 'intermediate') -> UnifiedStudentContext:
    return UnifiedStudentContext(
        profile=StudentProfile(
            user_id='anonymous',
            level=_parse_level(level),
            preferred_language=TeachingLanguage.HINGLISH,
        ),
        vision=VisionContext(
            raw_text=content,
            subject=Subject.MATH if mode == 'math' else Subject.GENERAL,
            difficulty=_parse_level(level),
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
            level=_parse_level(level),
            preferred_language=TeachingLanguage.HINGLISH,
        ),
        vision=VisionContext(
            raw_text=f'Teach me {topic}',
            subject=Subject.GENERAL,
            difficulty=_parse_level(level),
            topics=[topic],
        ),
        session=SessionContext(
            session_id=f'ses_{int(time.time())}',
            session_started_at=time.time(),
        ),
    )


async def _process_image_with_vision(
    image_bytes: bytes,
    mode: str,
    level: str,
) -> tuple[UnifiedStudentContext, Optional[dict], Optional[dict]]:
    """Run Vision Pipeline + Scene Graph on image, return context + scene + decision."""
    img = Image.open(BytesIO(image_bytes)).convert('RGB')
    img_array = np.array(img)

    pipeline = _get_vision_pipeline()
    scene = await pipeline.run(img_array)

    adapter = VisionAdapter()
    if adapter.needs_recapture(scene):
        msg = adapter.get_recapture_message(scene)
        raise HTTPException(status_code=422, detail=msg)

    vision_output = adapter.to_vision_output(scene)
    vision_dict = adapter.to_vision_context(scene)

    scene_graph = _get_scene_graph()
    try:
        teaching_decision = await scene_graph.process(scene)
        decision_dict = teaching_decision.model_dump() if hasattr(teaching_decision, 'model_dump') else {}
    except Exception:
        decision_dict = None

    context = UnifiedStudentContext(
        profile=StudentProfile(
            user_id='anonymous',
            level=_parse_level(level),
            preferred_language=TeachingLanguage.HINGLISH,
        ),
        vision=VisionContext(
            raw_text=vision_output.get('raw_text', ''),
            subject=Subject.MATH if mode == 'math' else Subject.GENERAL,
            difficulty=_parse_level(level),
            topics=vision_output.get('topics', []),
            problem_type=vision_output.get('problem_type', 'general'),
            formulas=vision_output.get('formulas', []),
        ),
        session=SessionContext(
            session_id=f'ses_{int(time.time())}',
            session_started_at=time.time(),
        ),
    )

    return context, vision_dict, decision_dict


# ── Solve My Doubt (text) ────────────────────────────────────────────────────

@router.post('/teach/doubt', response_model=TeachResponse)
async def solve_doubt(request: DoubtRequest):
    """Solve My Doubt — teach the solution interactively."""
    orchestrator = _get_orchestrator()
    session_id = f'ses_{int(time.time())}'

    try:
        context = _doubt_from_content(request.content, request.mode, request.level)
        result: TeacherResponse = await orchestrator.execute(
            context=context,
            student_message=request.content,
        )

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
    orchestrator = _get_orchestrator()
    session_id = f'ses_{int(time.time())}'

    try:
        image_bytes = await file.read()
        context, vision_dict, decision_dict = await _process_image_with_vision(
            image_bytes, mode, level,
        )

        result: TeacherResponse = await orchestrator.execute(
            context=context,
            student_message=context.vision.raw_text,
        )

        teach_resp = _response_to_teach(result, session_id)
        if vision_dict:
            teach_resp.concepts = vision_dict.get('topics', [])
        if decision_dict:
            teach_resp.teaching_decision = decision_dict

        await _get_event_bus().publish_sync(
            event_type=EventType.LESSON_STARTED,
            data={
                'type': 'doubt_image',
                'content_len': len(context.vision.raw_text),
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
      { type: 'doubt_image', image_base64: '...', mode: 'math', level: 'intermediate' }
      { type: 'lesson', topic: '...', level: 'intermediate' }
      { type: 'student_response', text: '...' }
      { type: 'cancel' }

    Server → Client (streamed):
      { type: 'processing', phase: 'analyzing_image' }
      { type: 'processing', phase: 'building_scene' }
      { type: 'processing', phase: 'planning_lesson' }
      { type: 'speech', text: '...', emotion: {...} }
      { type: 'board', text: '...', action: 'write', color: ... }
      { type: 'pointer', action: 'point', x: ..., y: ... }
      { type: 'thinking', duration_ms: 800 }
      { type: 'question', text: '...' }
      { type: 'homework', problems: [...] }
      { type: 'quiz', questions: {...} }
      { type: 'concepts', topics: [...] }
      { type: 'memory', topics_covered: [...], ... }
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

            elif msg_type == 'doubt_image':
                image_b64 = msg.get('image_base64', '')
                mode = msg.get('mode', 'math')
                level = msg.get('level', 'intermediate')
                await _send_json(websocket, {'type': 'processing', 'phase': 'analyzing_image'})
                try:
                    image_bytes = _decode_base64_image(image_b64)
                    context, vision_dict, _ = await _process_image_with_vision(
                        image_bytes, mode, level,
                    )
                    await _send_json(websocket, {'type': 'processing', 'phase': 'planning_lesson'})
                    await _run_and_stream(orchestrator, websocket, context, session_id, vision_dict=vision_dict)
                except HTTPException as exc:
                    await _send_json(websocket, {'type': 'error', 'message': exc.detail, 'code': exc.status_code})
                except Exception as exc:
                    await _send_json(websocket, {'type': 'error', 'message': str(exc)[:200]})

            elif msg_type == 'lesson':
                context = _lesson_from_topic(
                    msg.get('topic', ''),
                    msg.get('level', 'intermediate'),
                )
                await _run_and_stream(orchestrator, websocket, context, session_id)

            elif msg_type == 'student_response':
                await _send_json(websocket, {'type': 'thinking', 'duration_ms': 600})
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
            await _send_json(websocket, {'type': 'error', 'message': str(exc)[:200]})
        except Exception:
            pass


async def _run_and_stream(
    orchestrator: TeacherOrchestrator,
    ws: WebSocket,
    context: UnifiedStudentContext,
    session_id: str,
    vision_dict: Optional[dict] = None,
) -> None:
    """Run orchestrator and stream each output element."""
    await _send_json(ws, {'type': 'thinking', 'duration_ms': 400})
    await asyncio.sleep(0.2)

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
