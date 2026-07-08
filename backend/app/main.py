from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import tutor

app = FastAPI(
    title='Mentis API',
    version='0.2.0',
    description='Backend for Mentis AI Live AR Tutor',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(tutor.router)


@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'version': '0.2.0',
    }
