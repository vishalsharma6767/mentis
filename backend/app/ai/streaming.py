"""Streaming Engine — real-time WebSocket pipeline for the AI Teacher.

Manages WebSocket connections, message routing, streaming LLM responses,
and graceful disconnection. Designed for:

  - LLM token streaming (text appears as the teacher speaks)
  - Speech streaming (TTS audio chunks)
  - AR command streaming (board actions in real time)
  - Bidirectional student interaction (interrupt, ask doubt, answer)

Architecture::

    Client WS  →  StreamingEngine.handle()
                    ↓
              MessageRouter.dispatch()
                    ↓
              TeacherOrchestrator.execute()
                    ↓
              ResponseComposer.merge()
                    ↓
              StreamingEngine.send()  →  Client WS
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from enum import Enum
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.ai.context import ContextEngine, UnifiedStudentContext
from app.ai.gateway import AIGateway, LLMProvider
from app.ai.orchestrator import TeacherOrchestrator
from app.ai.teacher.schemas import (
    TeacherResponse,
    WSIncoming,
    WSOutgoing,
)
from app.core.config import settings
from app.core.constants import TeachingLanguage
from app.core.events import Event, EventBus, EventType
from app.core.exceptions import MentisError
from app.core.logger import get_logger

log = get_logger(__name__)


class ConnectionState(str, Enum):
    CONNECTING = 'connecting'
    CONNECTED = 'connected'
    STREAMING = 'streaming'
    INTERRUPTED = 'interrupted'
    CLOSING = 'closing'
    CLOSED = 'closed'


class MessageType(str, Enum):
    """WebSocket message types understood by the frontend."""
    TEACHER_RESPONSE = 'teacher_response'
    TOKEN_STREAM = 'token_stream'
    SPEECH_CHUNK = 'speech_chunk'
    AR_COMMAND = 'ar_command'
    BOARD_ACTION = 'board_action'
    ERROR = 'error'
    PING = 'ping'
    PONG = 'pong'
    SESSION_STATE = 'session_state'


class StreamEvent(str, Enum):
    """Events that the streaming engine fires on the Event Bus."""
    CLIENT_CONNECTED = 'client_connected'
    CLIENT_DISCONNECTED = 'client_disconnected'
    MESSAGE_RECEIVED = 'message_received'
    STREAM_STARTED = 'stream_started'
    STREAM_CHUNK = 'stream_chunk'
    STREAM_ENDED = 'stream_ended'
    STREAM_INTERRUPTED = 'stream_interrupted'


# ── Connection Manager ────────────────────────────────────────────────


class ConnectionManager:
    """Manages active WebSocket connections with metadata.

    Thread-safe for single-event-loop use. Each connection has a unique
    ID, the user/session it belongs to, and its current state.
    """

    def __init__(self) -> None:
        self._connections: dict[str, ConnectionInfo] = {}

    async def register(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: str,
    ) -> str:
        """Register a new connection and return its connection ID."""
        conn_id = uuid.uuid4().hex[:16]
        self._connections[conn_id] = ConnectionInfo(
            id=conn_id,
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
            state=ConnectionState.CONNECTED,
            connected_at=time.monotonic(),
        )
        log.info('ws_connected', conn_id=conn_id, user_id=user_id, session_id=session_id)
        return conn_id

    async def unregister(self, conn_id: str) -> None:
        """Remove a connection."""
        self._connections.pop(conn_id, None)
        log.info('ws_disconnected', conn_id=conn_id)

    def get(self, conn_id: str) -> Optional[ConnectionInfo]:
        return self._connections.get(conn_id)

    def get_by_user(self, user_id: str) -> list[ConnectionInfo]:
        return [c for c in self._connections.values() if c.user_id == user_id]

    def get_by_session(self, session_id: str) -> list[ConnectionInfo]:
        return [c for c in self._connections.values() if c.session_id == session_id]

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected clients."""
        for conn in list(self._connections.values()):
            try:
                await conn.websocket.send_json(message)
            except Exception:
                await self.unregister(conn.id)

    def active_count(self) -> int:
        return len(self._connections)

    def set_state(self, conn_id: str, state: ConnectionState) -> None:
        conn = self._connections.get(conn_id)
        if conn:
            conn.state = state


class ConnectionInfo:
    """Metadata for a single WebSocket connection."""

    def __init__(
        self,
        id: str,
        websocket: WebSocket,
        user_id: str,
        session_id: str,
        state: ConnectionState,
        connected_at: float,
    ) -> None:
        self.id = id
        self.websocket = websocket
        self.user_id = user_id
        self.session_id = session_id
        self.state = state
        self.connected_at = connected_at


# ── Streaming Engine ──────────────────────────────────────────────────


class StreamingEngine:
    """Real-time WebSocket handler for the AI Teacher.

    Manages the full lifecycle of a teaching session over WebSocket:

      1. Accept connection
      2. Assemble context (via ContextEngine)
      3. Orchestrate teaching (via TeacherOrchestrator)
      4. Stream response tokens (if streaming)
      5. Send complete TeacherResponse
      6. Handle interruption / follow-up

    Usage::

        engine = StreamingEngine()
        await engine.handle(websocket, user_id, session_id)
    """

    def __init__(self) -> None:
        self.manager = ConnectionManager()
        self.context_engine = ContextEngine()
        self.bus = EventBus.get_instance()
        self._orchestrators: dict[str, TeacherOrchestrator] = {}
        self._ping_interval = 25  # seconds

    # ── Main handler ──────────────────────────────────────────────────

    async def handle(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: Optional[str] = None,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
    ) -> None:
        """Accept and manage a WebSocket teaching session.

        Args:
            websocket: The FastAPI WebSocket connection.
            user_id: Authenticated user identifier.
            session_id: Optional existing session ID.
            language: Preferred teaching language.
        """
        await websocket.accept()
        session_id = session_id or uuid.uuid4().hex[:16]
        conn_id = await self.manager.register(websocket, user_id, session_id)

        await self._send(conn_id, {
            'type': MessageType.SESSION_STATE.value,
            'data': {'session_id': session_id, 'user_id': user_id, 'status': 'connected'},
        })
        await self.bus.publish_sync(
            EventType.USER_CONNECTED,
            data={'user_id': user_id, 'session_id': session_id, 'conn_id': conn_id},
            source='streaming_engine',
        )

        # Get or create orchestrator for this session
        orch = self._get_orchestrator(session_id, user_id)

        # Start background ping task
        ping_task = asyncio.create_task(self._ping_loop(conn_id))

        try:
            while True:
                raw = await websocket.receive_text()

                if raw == '__ping__':
                    await self._send(conn_id, {'type': MessageType.PONG.value})
                    continue

                message = self._parse_message(raw)
                if message is None:
                    continue

                await self.bus.publish_sync(
                    EventType.STUDENT_ANSWERED,
                    data={'user_id': user_id, 'session_id': session_id, 'message': message.text},
                    source='streaming_engine',
                )

                # Assemble context for this turn
                context = await self.context_engine.assemble(
                    user_id=user_id,
                    session_id=session_id,
                    vision_text=message.text or '',
                    vision_image_base64=message.image_base64,
                )

                # Execute the teaching pipeline
                response = await orch.execute(
                    context=context,
                    student_message=message.text or '',
                    image_base64=message.image_base64,
                    language=language,
                )

                # Validate and send response
                from app.ai.teacher.responder import ResponseComposer
                ResponseComposer.validate_response(response)

                await self._send_teacher_response(conn_id, response)

        except WebSocketDisconnect:
            log.info('ws_disconnect', conn_id=conn_id, user_id=user_id)
        except Exception as exc:
            log.error('ws_error', conn_id=conn_id, error=str(exc), exc_info=True)
            await self._send(conn_id, {
                'type': MessageType.ERROR.value,
                'data': {'message': 'An unexpected error occurred', 'code': 'INTERNAL_ERROR'},
            })
        finally:
            ping_task.cancel()
            await self.manager.unregister(conn_id)
            await self.bus.publish_sync(
                EventType.USER_DISCONNECTED,
                data={'user_id': user_id, 'session_id': session_id},
                source='streaming_engine',
            )

    # ── Streaming LLM response ────────────────────────────────────────

    async def handle_streaming(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: Optional[str] = None,
        language: TeachingLanguage = TeachingLanguage.HINGLISH,
    ) -> None:
        """Handle a session with token-level streaming.

        Instead of waiting for the full TeacherResponse, this method
        streams LLM tokens as they arrive, then sends the final response.
        """
        await websocket.accept()
        session_id = session_id or uuid.uuid4().hex[:16]
        conn_id = await self.manager.register(websocket, user_id, session_id)
        orch = self._get_orchestrator(session_id, user_id)

        await self._send(conn_id, {
            'type': MessageType.SESSION_STATE.value,
            'data': {'session_id': session_id, 'status': 'streaming_ready'},
        })

        try:
            while True:
                raw = await websocket.receive_text()
                if raw == '__ping__':
                    continue

                message = self._parse_message(raw)
                if message is None:
                    continue

                context = await self.context_engine.assemble(
                    user_id=user_id,
                    session_id=session_id,
                    vision_text=message.text or '',
                    vision_image_base64=message.image_base64,
                )

                await self._send(conn_id, {
                    'type': MessageType.STREAM_STARTED.value,
                    'data': {},
                })

                # Stream teacher explanation tokens
                collected_tokens: list[str] = []
                gateway = await AIGateway.get_instance()

                # Build a simple teaching prompt for streaming
                prompt = self._build_stream_prompt(context, message.text or '', language)

                async for token in gateway.stream(
                    messages=[
                        {'role': 'system', 'content': 'You are an experienced Indian classroom teacher. '
                                                      'Teach step by step in Hinglish. Never dump answers.'},
                        {'role': 'user', 'content': prompt},
                    ],
                    provider=LLMProvider.GROQ,
                ):
                    collected_tokens.append(token)
                    await self._send(conn_id, {
                        'type': MessageType.TOKEN_STREAM.value,
                        'data': {'token': token},
                    })

                full_text = ''.join(collected_tokens)

                # Build final TeacherResponse
                response = TeacherResponse(explanation=full_text)
                await self._send_teacher_response(conn_id, response)

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            log.error('streaming_error', error=str(exc))
            await self._send(conn_id, {
                'type': MessageType.ERROR.value,
                'data': {'message': str(exc)[:200], 'code': 'STREAMING_ERROR'},
            })
        finally:
            await self.manager.unregister(conn_id)

    # ── Send helpers ──────────────────────────────────────────────────

    async def _send(self, conn_id: str, data: dict[str, Any]) -> None:
        """Send a JSON message to a connection.

        Catches and logs send failures without raising.
        """
        conn = self.manager.get(conn_id)
        if conn is None:
            return
        try:
            await conn.websocket.send_json(data)
        except Exception as exc:
            log.warning('ws_send_failed', conn_id=conn_id, error=str(exc))

    async def _send_teacher_response(
        self,
        conn_id: str,
        response: TeacherResponse,
    ) -> None:
        """Send a structured TeacherResponse to the client."""
        outgoing = WSOutgoing(
            type=MessageType.TEACHER_RESPONSE.value,
            data=response,
        )
        await self._send(conn_id, outgoing.model_dump(mode='json'))

    # ── Internal ──────────────────────────────────────────────────────

    def _get_orchestrator(self, session_id: str, user_id: str) -> TeacherOrchestrator:
        """Get or create an orchestrator for a session."""
        if session_id not in self._orchestrators:
            self._orchestrators[session_id] = TeacherOrchestrator()
        return self._orchestrators[session_id]

    def _parse_message(self, raw: str) -> Optional[WSIncoming]:
        """Parse and validate an incoming WebSocket message."""
        try:
            data = json.loads(raw)
            if isinstance(data, str):
                return WSIncoming(text=data)
            return WSIncoming(**data)
        except (json.JSONDecodeError, TypeError):
            return WSIncoming(text=raw)

    def _build_stream_prompt(
        self,
        context: UnifiedStudentContext,
        student_message: str,
        language: TeachingLanguage,
    ) -> str:
        parts = [f'Student context:\n{context.format_for_agent()}']
        parts.append(f'\nStudent says: {student_message}')
        parts.append(f'\nTeach in {language.value}. Be warm, patient, and clear.')
        parts.append('Use Hinglish (mix Hindi + English).')
        parts.append('Never dump answers. Guide step by step.')
        return '\n'.join(parts)

    # ── Ping loop ─────────────────────────────────────────────────────

    async def _ping_loop(self, conn_id: str) -> None:
        """Periodic ping to detect stale connections."""
        try:
            while True:
                await asyncio.sleep(self._ping_interval)
                conn = self.manager.get(conn_id)
                if conn is None:
                    break
                try:
                    await conn.websocket.send_json({'type': MessageType.PING.value})
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
