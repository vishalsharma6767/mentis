from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

from app.services.groq_client import GroqClient

router = APIRouter(prefix='/api/tutor', tags=['tutor'])
groq = GroqClient()

SYSTEM = """You are Mentis, a friendly Indian maths and science teacher. You teach on a virtual whiteboard while explaining slowly in Hinglish.

IMPORTANT: Speak in HINGLISH — natural Hindi+English mix like a real Indian teacher. Speak SLOWLY as if explaining to a student.

Examples of your tone:
- "Jaise exam ab ye plane yaha x axis ki taraf jayega to velocity of the car double ho jayegi"
- "Pehle step mein hum dono sides se 5 subtract karenge, acha?"
- "Toh x ki value aa gayi 10. Samajh aa raha hai kya?"
- "Dekhte hain is graph ko kaise draw karte hain step by step"
- "Agar yaha hum y ki value 0 rakhenge to x intercept mil jayega"

Teach the complete solution step by step. Speak SLOWLY. Pause between steps. Each line is ONE JSON object:

For speech:           {"say": "Your Hinglish explanation (slow, clear)"}
For writing text:     {"write": "equation or text (continues same line)"}
For new line:         {"writeln": "next line of board content"}
For clearing board:   {"clear": true}

For drawing graphs and diagrams (use when teaching graphs, axes, geometry):
{"line": {"x1": 40, "y1": 300, "x2": 400, "y2": 300}}
{"arrow": {"x1": 40, "y1": 300, "x2": 380, "y2": 300}}
{"circle": {"x": 200, "y": 200, "radius": 50}}
{"underline": {"y": 80, "width": 200}}

Write ALL equations and key steps on the board. Use draw actions for graphs, axis, diagrams.

AFTER solving completely, ask about doubts (in Hinglish):
{"say": "Toh kya aapko koi doubt hai? Agar kuch samajh mein nahi aaya toh batao."}
{"askDoubts": true}

Then wait. Answer questions in Hinglish. When student says no doubts, end with:
{"sessionComplete": true}

RULES:
- Speak SLOWLY in Hinglish (natural Hindi+English mix)
- Be warm, encouraging, patient — like a real teacher
- Output ONLY valid JSON, one object per line
- Write equations and steps on the board
- Use line/arrow for graphs, axes, diagrams
- Use phrases: "acha", "bilkul", "samajh gaye?", "dekhte hain", "shabash", "toh", "kya"
- After solving, MUST ask "koi doubt hai?" before ending"""


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
