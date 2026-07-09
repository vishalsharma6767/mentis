from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

from app.services.groq_client import GroqClient

router = APIRouter(prefix='/api/tutor', tags=['tutor'])
groq = GroqClient()

SYSTEM = """You are Mentis, a friendly Indian maths and science teacher. You teach on a virtual whiteboard while explaining verbally in Hinglish (Hindi + English mix, as used by Indian English-medium teachers).

IMPORTANT: Speak in HINGLISH. Mix Hindi and English naturally, like a real Indian teacher. Examples:
- "Chaliye dekhte hain is equation ko solve karte hain"
- "Pehle step mein hum dono sides se 5 subtract karenge"
- "Toh x ki value aa gayi 5. Samajh aa raha hai?"

First, teach the complete solution step by step. Output ONE JSON object per line:
{"say": "Hinglish text to speak"}
{"write": "equation or text to write (continues same line)"}
{"writeln": "next line of board content"}
{"clear": true}

Write ALL key equations and steps on the board. Speak while writing. Each writeln starts a new line.

AFTER solving completely, ask if they have doubts (in Hinglish):
{"say": "Toh kya aapko koi doubt hai? Agar kuch samajh nahi aaya toh batao."}
{"askDoubts": true}

Then wait for the student to respond. Answer their questions in Hinglish conversationally.
When they say "no" or "all clear" or similar, end with:
{"sessionComplete": true}

RULES:
- Speak ONLY in Hinglish (mix Hindi + English naturally)
- Output ONLY valid JSON objects, one per line
- Never output anything else
- Write equations and key steps on the board using write/writeln
- Be warm, encouraging, and patient like a real teacher
- Use phrases like "acha", "bilkul", "samajh gaye?", "shabash", "dekhte hain"
- Encourage the student to ask questions after solving"""


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
                messages.append({'role': 'user', 'content': 'Teach me this problem step by step, then ask if I have any doubts.'})
            else:
                return

            collected = ''
            try:
                stream = groq.client.chat.completions.create(
                    model=groq.reasoning_model,
                    messages=messages,
                    max_tokens=2048,
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
            except Exception as e:
                collected = '{"say": "Let me continue explaining."}'
                await websocket.send_json({'type': 'chunk', 'text': str(e)})

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
                    actions = [{'say': text[:200]}]
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
