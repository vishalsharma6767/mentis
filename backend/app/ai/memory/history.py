"""Session history: past problems, solutions, mistakes for review."""

from pydantic import BaseModel
from datetime import datetime


class SessionHistory(BaseModel):
    user_id: str
    session_id: str
    problem_text: str
    solution: str
    created_at: datetime
    duration_seconds: int = 0
