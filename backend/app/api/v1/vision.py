"""Vision API endpoints: image upload, OCR extraction, problem detection."""

from fastapi import APIRouter

router = APIRouter(prefix='/api/vision', tags=['vision'])
