"""REST endpoints for tutoring: recognize, generate-lesson, ask-doubt, create-session-pdf, discussions, study-groups."""

from fastapi import APIRouter

router = APIRouter(prefix='/api/tutor', tags=['tutor'])
