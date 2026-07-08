from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

from app.services.groq_client import GroqClient
from app.config import settings

router = APIRouter(prefix='/api/tutor', tags=['tutor'])
groq = GroqClient()


@router.websocket('/ws/tutor')
async def tutor_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        mode = data.get('mode', 'math')
        level = data.get('level', 'intermediate')
        content = data.get('content', '')
        system_prompt = (
            'You are Mentis, an AI AR tutor. Keep responses brief and conversational. '
            'Return only plain text, no JSON. Include one short AR pen annotation phrase when helpful. '
            f'Learning mode: {mode}. Student level: {level}. Problem: {content}'
        )
        messages = [{'role': 'system', 'content': system_prompt}]
        await websocket.send_json({'type': 'ready'})
        while True:
            payload = await websocket.receive_json()
            user_text = payload.get('text', '')
            if not user_text:
                continue
            messages.append({'role': 'user', 'content': user_text})
            full = ''
            try:
                stream = groq.client.chat.completions.create(
                    model=groq.reasoning_model,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.7,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ''
                    if delta:
                        full += delta
                        await websocket.send_json({'type': 'chunk', 'text': delta})
            except Exception:
                full = 'Good question. Try the next small step and tell me what you wrote.'
                await websocket.send_json({'type': 'chunk', 'text': full})
            if full:
                messages.append({'role': 'assistant', 'content': full})
            await websocket.send_json({'type': 'done', 'text': full})
    except WebSocketDisconnect:
        pass
