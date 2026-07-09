from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import re

from app.services.groq_client import GroqClient
from app.config import settings

router = APIRouter(prefix='/api/tutor', tags=['tutor'])
groq = GroqClient()

SYSTEM = """You are Mentis, an AI math and science tutor. You teach by writing on a virtual whiteboard while explaining verbally.

For EACH teaching step, output ONE JSON object per line like this:
{"say": "text to speak aloud"}
{"write": "equation or text to write on board (continues same line)"}
{"writeln": "next line of board content"}
{"clear": true}
{"highlight": "text"}
{"sessionComplete": true}

RULES:
- Explain concepts conversationally like a real teacher
- Write equations and key steps on the board using write/writeln
- Speak while writing — students learn by seeing AND hearing
- Each writeln starts a new line on the board
- Encourage the student: ask "Does that make sense?" or "What do you think?"
- When the problem is fully solved and understood, send {"sessionComplete": true}
- ALWAYS output valid JSON, one object per line
- Never output anything except JSON objects, one per line

Example session:
{"say": "Let's solve 2x + 5 = 15 together"}
{"write": "2x + 5 = 15"}
{"say": "First, isolate the variable term by subtracting 5 from both sides"}
{"writeln": "2x = 15 - 5"}
{"writeln": "2x = 10"}
{"say": "Now divide both sides by 2"}
{"writeln": "x = 5"}
{"say": "So x equals 5. Does that make sense?"}"""


@router.websocket('/ws/tutor')
async def tutor_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        mode = data.get('mode', 'math')
        content = data.get('content', '')
        level = data.get('level', 'intermediate')

        system_prompt = (
            SYSTEM + f'\nLearning mode: {mode}. Student level: {level}. Problem: {content}'
        )
        messages = [{'role': 'system', 'content': system_prompt}]
        abort_flag = False

        async def generate_response(user_text: str, is_first: bool = False):
            nonlocal abort_flag
            if user_text:
                messages.append({'role': 'user', 'content': user_text})
            elif is_first:
                messages.append({'role': 'user', 'content': 'Start teaching me this problem step by step.'})
            else:
                return

            collected = ''
            try:
                stream = groq.client.chat.completions.create(
                    model=groq.reasoning_model,
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.7,
                    stream=True,
                )
                for chunk in stream:
                    if abort_flag:
                        abort_flag = False
                        break
                    delta = chunk.choices[0].delta.content or ''
                    if delta:
                        collected += delta
                        await websocket.send_json({'type': 'chunk', 'text': delta})
            except Exception:
                collected = '{"say": "Let me continue explaining. Tell me what step you are on."}'
                await websocket.send_json({'type': 'chunk', 'text': collected})

            if collected:
                actions = []
                for line in collected.strip().split('\n'):
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        try:
                            actions.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                if not actions:
                    text = collected.strip().strip('"')
                    actions = [{'say': text}]
                messages.append({'role': 'assistant', 'content': json.dumps(actions)})
                await websocket.send_json({'type': 'actions', 'actions': actions})
            await websocket.send_json({'type': 'done'})

        await websocket.send_json({'type': 'ready'})
        await generate_response('', is_first=True)

        while True:
            payload = await websocket.receive_json()
            user_text = payload.get('text', '')
            if not user_text:
                continue
            abort_flag = True
            await generate_response(user_text, is_first=False)

    except WebSocketDisconnect:
        pass
