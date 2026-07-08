from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from appwrite.client import Client
from appwrite.services.users import Users
from app.config import settings

router = APIRouter(prefix='/api/auth', tags=['auth'])


class SetPasswordRequest(BaseModel):
    user_id: str
    password: str


def _get_users_service() -> Users:
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return Users(client)


@router.post('/set-password')
async def set_password(req: SetPasswordRequest):
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail='Password must be at least 6 characters.')
    try:
        users = _get_users_service()
        users.update_password(user_id=req.user_id, password=req.password)
        return {'status': 'ok'}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SaveProfileRequest(BaseModel):
    user_id: str
    name: str
    grade: str
    subjects: list[str]
    goal: str


@router.post('/save-profile')
async def save_profile(req: SaveProfileRequest):
    try:
        users = _get_users_service()
        users.update_name(user_id=req.user_id, name=req.name)
        users.update_prefs(
            user_id=req.user_id,
            prefs={
                'grade': req.grade,
                'subjects': ','.join(req.subjects),
                'goal': req.goal,
                'registeredAt': __import__('datetime').datetime.utcnow().isoformat(),
            },
        )
        return {'status': 'ok'}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
