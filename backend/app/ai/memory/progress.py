"""Progress tracker: topics mastered, mistake tracking, improvement over time."""

from pydantic import BaseModel
from datetime import datetime


class TopicProgress(BaseModel):
    user_id: str
    topic: str
    mastered: bool = False
    mistakes: int = 0
    sessions_count: int = 0
    last_practiced: datetime | None = None
