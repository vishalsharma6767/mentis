"""Student profile: strengths, weaknesses, learning pace, session history."""

from pydantic import BaseModel


class StudentProfile(BaseModel):
    user_id: str
    level: str = 'intermediate'
    strengths: list[str] = []
    weaknesses: list[str] = []
    session_count: int = 0
