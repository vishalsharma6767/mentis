"""Application configuration via pydantic-settings v2.

All settings are loaded from environment variables (and .env file).
No secrets are hardcoded. Every API key comes from the environment.
"""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = 'development'
    STAGING = 'staging'
    PRODUCTION = 'production'


class LogLevel(str, Enum):
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    # ── App ────────────────────────────────────────────────────────────
    app_name: str = Field('Mentis API', alias='APP_NAME')
    app_version: str = Field('0.4.0', alias='APP_VERSION')
    app_description: str = Field('AI-powered AR Teacher backend', alias='APP_DESCRIPTION')
    environment: Environment = Field(Environment.DEVELOPMENT, alias='ENVIRONMENT')
    debug: bool = Field(False, alias='DEBUG')
    host: str = Field('0.0.0.0', alias='HOST')
    port: int = Field(8000, alias='PORT')
    root_path: Path = Field(Path(__file__).resolve().parent.parent.parent, alias='ROOT_PATH')

    # ── Database ───────────────────────────────────────────────────────
    database_url: str = Field('sqlite+aiosqlite:///./mentis.db', alias='DATABASE_URL')
    database_echo: bool = Field(False, alias='DATABASE_ECHO')
    database_pool_size: int = Field(20, alias='DATABASE_POOL_SIZE')
    database_max_overflow: int = Field(10, alias='DATABASE_MAX_OVERFLOW')
    database_pool_timeout: int = Field(30, alias='DATABASE_POOL_TIMEOUT')
    database_pool_pre_ping: bool = Field(True, alias='DATABASE_POOL_PRE_PING')

    # ── Redis ──────────────────────────────────────────────────────────
    redis_url: str = Field('redis://localhost:6379/0', alias='REDIS_URL')
    redis_connection_timeout: int = Field(5, alias='REDIS_CONNECTION_TIMEOUT')
    redis_max_connections: int = Field(20, alias='REDIS_MAX_CONNECTIONS')

    # ── Celery ─────────────────────────────────────────────────────────
    celery_broker_url: Optional[str] = Field(None, alias='CELERY_BROKER_URL')
    celery_result_backend: Optional[str] = Field(None, alias='CELERY_RESULT_BACKEND')
    celery_task_always_eager: bool = Field(False, alias='CELERY_TASK_ALWAYS_EAGER')
    celery_task_track_started: bool = Field(True, alias='CELERY_TASK_TRACK_STARTED')

    # ── JWT ────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field('change-me-in-production', alias='JWT_SECRET_KEY')
    jwt_algorithm: str = Field('HS256', alias='JWT_ALGORITHM')
    jwt_access_token_expire_minutes: int = Field(30, alias='JWT_ACCESS_TOKEN_EXPIRE_MINUTES')
    jwt_refresh_token_expire_days: int = Field(7, alias='JWT_REFRESH_TOKEN_EXPIRE_DAYS')

    # ── Appwrite ───────────────────────────────────────────────────────
    appwrite_endpoint: str = Field('https://sgp.cloud.appwrite.io/v1', alias='APPWRITE_ENDPOINT')
    appwrite_project_id: str = Field('', alias='APPWRITE_PROJECT_ID')
    appwrite_api_key: str = Field('', alias='APPWRITE_API_KEY')
    appwrite_database_id: str = Field('mentis_main', alias='APPWRITE_DATABASE_ID')

    # ── LLM Providers ──────────────────────────────────────────────────
    groq_api_key: str = Field('', alias='GROQ_API_KEY')
    groq_vision_model: str = Field('meta-llama/llama-4-scout-17b-16e-instruct', alias='GROQ_VISION_MODEL')
    groq_reasoning_model: str = Field('llama-3.1-8b-instant', alias='GROQ_REASONING_MODEL')
    groq_max_tokens: int = Field(8192, alias='GROQ_MAX_TOKENS')
    groq_temperature: float = Field(0.7, alias='GROQ_TEMPERATURE')

    openrouter_api_key: Optional[str] = Field(None, alias='OPENROUTER_API_KEY')
    openrouter_base_url: str = Field('https://openrouter.ai/api/v1', alias='OPENROUTER_BASE_URL')
    openrouter_model: str = Field('openai/gpt-4o-mini', alias='OPENROUTER_MODEL')
    openrouter_max_tokens: int = Field(4096, alias='OPENROUTER_MAX_TOKENS')

    gemini_api_key: Optional[str] = Field(None, alias='GEMINI_API_KEY')
    gemini_model: str = Field('gemini-2.0-flash', alias='GEMINI_MODEL')

    # ── Google Cloud Vision ────────────────────────────────────────────
    google_vision_credentials_json: Optional[str] = Field(None, alias='GOOGLE_VISION_CREDENTIALS_JSON')

    # ── CORS ───────────────────────────────────────────────────────────
    cors_allow_origins: list[str] = Field(['*'], alias='CORS_ALLOW_ORIGINS')
    cors_allow_credentials: bool = Field(True, alias='CORS_ALLOW_CREDENTIALS')
    cors_allow_methods: list[str] = Field(['*'], alias='CORS_ALLOW_METHODS')
    cors_allow_headers: list[str] = Field(['*'], alias='CORS_ALLOW_HEADERS')

    # ── Rate Limiting ──────────────────────────────────────────────────
    rate_limit_enabled: bool = Field(True, alias='RATE_LIMIT_ENABLED')
    rate_limit_requests: int = Field(100, alias='RATE_LIMIT_REQUESTS')
    rate_limit_window_seconds: int = Field(60, alias='RATE_LIMIT_WINDOW_SECONDS')

    # ── Observability ──────────────────────────────────────────────────
    log_level: LogLevel = Field(LogLevel.INFO, alias='LOG_LEVEL')
    sentry_dsn: Optional[str] = Field(None, alias='SENTRY_DSN')
    enable_metrics: bool = Field(True, alias='ENABLE_METRICS')
    enable_tracing: bool = Field(False, alias='ENABLE_TRACING')

    # ── File Uploads ───────────────────────────────────────────────────
    upload_max_size_mb: int = Field(10, alias='UPLOAD_MAX_SIZE_MB')
    upload_allowed_extensions: list[str] = Field(
        ['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf'],
        alias='UPLOAD_ALLOWED_EXTENSIONS',
    )
    upload_dir: str = Field('uploads', alias='UPLOAD_DIR')

    # ── Teaching ───────────────────────────────────────────────────────
    default_teaching_language: str = Field('hinglish', alias='DEFAULT_TEACHING_LANGUAGE')
    teacher_tone: str = Field('warm_and_patient', alias='TEACHER_TONE')
    max_lesson_steps: int = Field(10, alias='MAX_LESSON_STEPS')
    student_timeout_seconds: int = Field(120, alias='STUDENT_TIMEOUT_SECONDS')

    # ── AR ─────────────────────────────────────────────────────────────
    ar_default_color: str = Field('#00D4FF', alias='AR_DEFAULT_COLOR')
    ar_cursor_speed_ms: int = Field(25, alias='AR_CURSOR_SPEED_MS')
    ar_line_height: int = Field(42, alias='AR_LINE_HEIGHT')
    ar_pen_wobble: float = Field(1.2, alias='AR_PEN_WOBBLE')

    # ── Speech ─────────────────────────────────────────────────────────
    speech_default_rate: float = Field(0.76, alias='SPEECH_DEFAULT_RATE')
    speech_default_pitch: float = Field(1.05, alias='SPEECH_DEFAULT_PITCH')
    speech_default_language: str = Field('hi-IN', alias='SPEECH_DEFAULT_LANGUAGE')

    # ── Validators ─────────────────────────────────────────────────────

    @field_validator('jwt_secret_key')
    @classmethod
    def warn_if_default_jwt_secret(cls, v: str) -> str:
        if v == 'change-me-in-production':
            import warnings
            warnings.warn('JWT_SECRET_KEY is using the default value. Set a strong secret in production.', stacklevel=2)
        return v

    @field_validator('upload_allowed_extensions')
    @classmethod
    def normalize_extensions(cls, v: list[str]) -> list[str]:
        return [ext.lower().lstrip('.') for ext in v]

    # ── Computed Properties ────────────────────────────────────────────

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def celery_broker_url_resolved(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_result_backend_resolved(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace('+aiosqlite', '').replace('+asyncpg', '')

    @property
    def upload_max_size_bytes(self) -> int:
        return self.upload_max_size_mb * 1024 * 1024

    @property
    def upload_path(self) -> Path:
        path = self.root_path / self.upload_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
