import json
import base64
from io import BytesIO
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from app.services import vision_service, tutor_service
from app.services import groq_client
from app.database import databases, DATABASE_ID, COLLECTIONS

router = APIRouter(prefix='/api/tutor', tags=['tutor'])

SESSION_COLLECTION = 'sessions'
PROGRESS_COLLECTION = 'progress'


@router.post('/recognize')
async def recognize_problem(file: UploadFile = File(...), mode: str = Form('math')):
    image_bytes = await file.read()
    problem = vision_service.extract_problem(image_bytes, mode)
    return problem


@router.post('/lesson')
async def generate_lesson(
    problem_type: str = Form(...),
    content: str = Form(...),
    level: str = Form('intermediate'),
    mode: str = Form('math'),
):
    problem = {'type': problem_type, 'content': content}
    lesson = tutor_service.generate_lesson(problem, level, mode)
    return lesson


@router.post('/help')
async def step_help(
    problem_type: str = Form(...),
    content: str = Form(...),
    completed: str = Form('[]'),
    current: str = Form('{}'),
):
    problem = {'type': problem_type, 'content': content}
    try:
        completed_list = json.loads(completed)
    except json.JSONDecodeError:
        completed_list = []
    try:
        current_dict = json.loads(current)
    except json.JSONDecodeError:
        current_dict = {}
    help_text = tutor_service.get_step_help(problem, completed_list, current_dict)
    return {'help': help_text}


@router.post('/doubt')
async def answer_doubt(
    content: str = Form(...),
    question: str = Form(...),
    current: str = Form('{}'),
    level: str = Form('intermediate'),
    mode: str = Form('math'),
):
    try:
        current_dict = json.loads(current)
    except json.JSONDecodeError:
        current_dict = {}
    return tutor_service.answer_doubt(content, question, current_dict, level, mode)


@router.post('/session-pdf')
async def session_pdf(
    title: str = Form('Mentis Tutor Session'),
    problem: str = Form(''),
    steps: str = Form('[]'),
    transcript: str = Form('[]'),
    pen_notes: str = Form('[]'),
):
    pdf_bytes = _build_session_pdf(title, problem, steps, transcript, pen_notes)
    safe_title = ''.join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip() or 'mentis-session'
    return {
        'filename': f'{safe_title[:48].replace(" ", "-").lower()}-solution.pdf',
        'mime': 'application/pdf',
        'base64': base64.b64encode(pdf_bytes).decode('ascii'),
    }


@router.post('/transcribe')
async def transcribe_audio(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    mime = file.content_type or 'audio/wav'
    ext = 'wav'
    if 'mp4' in mime or 'm4a' in mime:
        ext = 'm4a'
    elif 'mp3' in mime:
        ext = 'mp3'
    elif 'ogg' in mime:
        ext = 'ogg'
    transcription = groq_client.client.audio.transcriptions.create(
        model='whisper-large-v3-turbo',
        file=(f'audio.{ext}', audio_bytes, mime),
        language='en',
        response_format='text',
    )
    return {'text': transcription}


def _pdf_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _wrap(text: str, limit: int = 88) -> list[str]:
    words = str(text or '').replace('\r', '').split()
    lines: list[str] = []
    current = ''
    for word in words:
        if len(current) + len(word) + 1 > limit:
            if current:
                lines.append(current)
            current = word
        else:
            current = f'{current} {word}'.strip()
    if current:
        lines.append(current)
    return lines or ['']


def _read_json_list(value: str) -> list:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _build_session_pdf(title: str, problem: str, steps_json: str, transcript_json: str, pen_json: str) -> bytes:
    steps = _read_json_list(steps_json)
    transcript = _read_json_list(transcript_json)
    pen_notes = _read_json_list(pen_json)

    lines = [
        'Mentis AI Live AR Tutor',
        f'Session: {title}',
        f'Date: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}',
        '',
        'Scanned Problem',
    ]
    lines.extend(_wrap(problem, 92))
    lines.extend(['', 'Step-by-step Solution'])
    for step in steps:
        if not isinstance(step, dict):
            continue
        lines.extend(_wrap(f"Step {step.get('number', '')}: {step.get('instruction', '')}", 92))
        if step.get('explanation'):
            lines.extend(_wrap(f"Why: {step.get('explanation')}", 92))
        if step.get('answer'):
            lines.extend(_wrap(f"Result: {step.get('answer')}", 92))
        if step.get('ar_annotation'):
            lines.extend(_wrap(f"AR pen: {step.get('ar_annotation')}", 92))
        lines.append('')

    if pen_notes:
        lines.append('AR Pen Notes')
        for note in pen_notes:
            text = note.get('text') if isinstance(note, dict) else str(note)
            lines.extend(_wrap(f'- {text}', 92))
        lines.append('')

    if transcript:
        lines.append('Live Doubt Transcript')
        for msg in transcript:
            if isinstance(msg, dict):
                speaker = msg.get('role', 'message').title()
                text = msg.get('text', '')
                lines.extend(_wrap(f'{speaker}: {text}', 92))

    page_streams: list[str] = []
    y = 760
    content = ['BT', '/F1 11 Tf', '50 760 Td', '14 TL']

    def flush_page():
        nonlocal content, y
        content.append('ET')
        page_streams.append('\n'.join(content))
        y = 760
        content = ['BT', '/F1 11 Tf', '50 760 Td', '14 TL']

    for raw_line in lines:
        for line in _wrap(raw_line, 96):
            if y < 48:
                flush_page()
            escaped = _pdf_escape(line)
            content.append(f'({escaped}) Tj')
            content.append('T*')
            y -= 14
    flush_page()

    objects: list[str] = [
        '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
        '',
        '3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n',
    ]
    page_ids: list[int] = []
    next_obj = 4
    for stream in page_streams:
        content_obj = next_obj
        page_obj = next_obj + 1
        next_obj += 2
        stream_bytes = stream.encode('latin-1', 'replace')
        objects.append(
            f'{content_obj} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n{stream}\nendstream\nendobj\n'
        )
        objects.append(
            f'{page_obj} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
            f'/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>\nendobj\n'
        )
        page_ids.append(page_obj)

    kids = ' '.join(f'{page} 0 R' for page in page_ids)
    objects[1] = f'2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>\nendobj\n'

    pdf = ['%PDF-1.4\n']
    offsets = [0] * (next_obj)
    for obj in objects:
        obj_id = int(obj.split(' ', 1)[0])
        offsets[obj_id] = sum(len(part.encode('latin-1', 'replace')) for part in pdf)
        pdf.append(obj)
    xref_offset = sum(len(part.encode('latin-1', 'replace')) for part in pdf)
    pdf.append(f'xref\n0 {next_obj}\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.append(f'{offset:010d} 00000 n \n')
    pdf.append(f'trailer\n<< /Size {next_obj} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF')
    return ''.join(pdf).encode('latin-1', 'replace')


@router.post('/sessions')
async def save_session(
    userId: str = Form(...),
    problemTitle: str = Form(''),
    problemType: str = Form(''),
    extractedText: str = Form(''),
    status: str = Form('completed'),
    steps: str = Form('[]'),
):
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=SESSION_COLLECTION,
        document_id='unique()',
        data={
            'userId': userId,
            'problemTitle': problemTitle,
            'problemType': problemType,
            'extractedText': extractedText,
            'status': status,
            'steps': steps,
            'createdAt': datetime.now(timezone.utc).isoformat(),
        },
    )
    return {'id': doc['$id']}


@router.get('/sessions')
async def list_sessions(userId: str = Query(...), limit: int = 20):
    from appwrite.query import Query as AppwriteQuery
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=SESSION_COLLECTION,
        queries=[
            AppwriteQuery.equal('userId', userId),
            AppwriteQuery.order_desc('createdAt'),
            AppwriteQuery.limit(limit),
        ],
    )
    return {'sessions': docs.documents}


@router.get('/stats')
async def get_stats(userId: str = Query(...)):
    from appwrite.query import Query as AppwriteQuery
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=SESSION_COLLECTION,
        queries=[
            AppwriteQuery.equal('userId', userId),
            AppwriteQuery.limit(5000),
        ],
    )
    sessions = docs.documents
    completed = [s for s in sessions if s.get('status') == 'completed']
    types = {}
    for s in sessions:
        t = s.get('problemType', 'unknown')
        types[t] = types.get(t, 0) + 1
    return {
        'totalSessions': len(sessions),
        'completedSessions': len(completed),
        'topTopics': sorted(types.items(), key=lambda x: -x[1])[:5],
    }


@router.get('/streak')
async def get_streak(userId: str = Query(...)):
    from appwrite.query import Query as AppwriteQuery
    from datetime import datetime, timezone, timedelta
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id=SESSION_COLLECTION,
        queries=[
            AppwriteQuery.equal('userId', userId),
            AppwriteQuery.equal('status', 'completed'),
            AppwriteQuery.order_desc('createdAt'),
            AppwriteQuery.limit(1000),
        ],
    )
    sessions = docs.documents
    if not sessions:
        return {'streak': 0, 'lastActive': None}
    dates = []
    for s in sessions:
        ts = s.get('createdAt')
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            dates.append(dt.date())
        except Exception:
            continue
    unique_dates = sorted(set(dates), reverse=True)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    if not unique_dates:
        return {'streak': 0, 'lastActive': None}
    if unique_dates[0] != today and unique_dates[0] != yesterday:
        return {'streak': 0, 'lastActive': unique_dates[0].isoformat()}
    streak = 1
    for i in range(1, len(unique_dates)):
        if (unique_dates[i - 1] - unique_dates[i]).days == 1:
            streak += 1
        else:
            break
    return {'streak': streak, 'lastActive': unique_dates[0].isoformat()}


@router.get('/discussions')
async def list_discussions(tag: str = Query('')):
    from appwrite.query import Query as AppwriteQuery
    queries = [AppwriteQuery.order_desc('createdAt'), AppwriteQuery.limit(50)]
    if tag:
        queries.append(AppwriteQuery.equal('tag', tag))
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id='discussions',
        queries=queries,
    )
    return {'discussions': docs.documents}


@router.post('/discussions')
async def create_discussion(
    userId: str = Form(...),
    title: str = Form(...),
    body: str = Form(''),
    tag: str = Form(''),
    authorName: str = Form(''),
):
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id='discussions',
        document_id='unique()',
        data={
            'userId': userId,
            'title': title,
            'body': body,
            'tag': tag,
            'replies': 0,
            'likes': 0,
            'authorName': authorName,
            'createdAt': datetime.now(timezone.utc).isoformat(),
        },
    )
    return {'id': doc['$id']}


@router.get('/study-groups')
async def list_study_groups():
    from appwrite.query import Query as AppwriteQuery
    docs = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id='study_groups',
        queries=[AppwriteQuery.order_desc('createdAt')],
    )
    return {'groups': docs.documents}


@router.post('/study-groups')
async def create_study_group(
    name: str = Form(...),
    subject: str = Form(...),
    members: int = Form(0),
    active: int = Form(0),
    nextSession: str = Form(''),
):
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id='study_groups',
        document_id='unique()',
        data={
            'name': name,
            'subject': subject,
            'members': members,
            'active': active,
            'nextSession': nextSession,
            'createdAt': datetime.now(timezone.utc).isoformat(),
        },
    )
    return {'id': doc['$id']}
