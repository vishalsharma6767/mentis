import json
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
async def recognize_problem(file: UploadFile = File(...)):
    image_bytes = await file.read()
    problem = vision_service.extract_problem(image_bytes)
    return problem


@router.post('/lesson')
async def generate_lesson(
    problem_type: str = Form(...),
    content: str = Form(...),
    level: str = Form('intermediate'),
):
    problem = {'type': problem_type, 'content': content}
    lesson = tutor_service.generate_lesson(problem, level)
    return lesson


@router.post('/help')
async def step_help(
    problem_type: str = Form(...),
    content: str = Form(...),
    completed: str = Form('[]'),
    current: str = Form('{}'),
):
    problem = {'type': problem_type, 'content': content}
    completed_list = json.loads(completed)
    current_dict = json.loads(current)
    help_text = tutor_service.get_step_help(problem, completed_list, current_dict)
    return {'help': help_text}


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
