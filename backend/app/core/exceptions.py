"""Application-wide custom exceptions and error-handling utilities.

Every service, agent, and repository raises typed exceptions from this module.
The global exception handler in middleware.py catches these and returns
structured JSON error responses.
"""

from typing import Any, Optional


class MentisError(Exception):
    """Base exception for all Mentis errors."""

    def __init__(
        self,
        message: str = 'An unexpected error occurred',
        code: str = 'INTERNAL_ERROR',
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            'error': {
                'code': self.code,
                'message': self.message,
                'details': self.details,
            }
        }


# ── Configuration Errors ───────────────────────────────────────────────


class ConfigurationError(MentisError):
    """Raised when a required setting is missing or invalid."""

    def __init__(self, message: str = 'Invalid configuration', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='CONFIGURATION_ERROR', status_code=500, details=details)


# ── Authentication & Authorization ─────────────────────────────────────


class AuthenticationError(MentisError):
    """Raised when authentication fails."""

    def __init__(self, message: str = 'Authentication failed', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='AUTHENTICATION_ERROR', status_code=401, details=details)


class AuthorizationError(MentisError):
    """Raised when the user lacks permission for the requested action."""

    def __init__(self, message: str = 'Not authorized', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='AUTHORIZATION_ERROR', status_code=403, details=details)


class TokenExpiredError(MentisError):
    """Raised when a JWT or refresh token has expired."""

    def __init__(self, message: str = 'Token has expired', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='TOKEN_EXPIRED', status_code=401, details=details)


class InvalidTokenError(MentisError):
    """Raised when a token is malformed or invalid."""

    def __init__(self, message: str = 'Invalid token', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='INVALID_TOKEN', status_code=401, details=details)


# ── Resource Errors ────────────────────────────────────────────────────


class NotFoundError(MentisError):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str = 'Resource', identifier: Optional[str] = None) -> None:
        message = f'{resource} not found'
        if identifier:
            message += f': {identifier}'
        super().__init__(message=message, code='NOT_FOUND', status_code=404)


class ConflictError(MentisError):
    """Raised when a resource already exists (duplicate)."""

    def __init__(self, message: str = 'Resource already exists', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='CONFLICT', status_code=409, details=details)


# ── Validation Errors ──────────────────────────────────────────────────


class ValidationError(MentisError):
    """Raised when input validation fails."""

    def __init__(self, message: str = 'Validation failed', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='VALIDATION_ERROR', status_code=422, details=details)


# ── Database Errors ────────────────────────────────────────────────────


class DatabaseError(MentisError):
    """Raised when a database operation fails."""

    def __init__(self, message: str = 'Database operation failed', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='DATABASE_ERROR', status_code=500, details=details)


class DatabaseConnectionError(DatabaseError):
    """Raised when the database cannot be reached."""

    def __init__(self, message: str = 'Cannot connect to database') -> None:
        super().__init__(message=message, code='DATABASE_CONNECTION_ERROR')


# ── AI / Agent Errors ──────────────────────────────────────────────────


class AIProviderError(MentisError):
    """Raised when an external AI provider (Groq, OpenRouter, Gemini) fails."""

    def __init__(self, provider: str = 'unknown', message: str = 'AI provider error', details: Optional[dict[str, Any]] = None) -> None:
        full_message = f'[{provider}] {message}'
        super().__init__(message=full_message, code='AI_PROVIDER_ERROR', status_code=502, details=details)


class AgentExecutionError(MentisError):
    """Raised when an agent in the multi-agent pipeline fails."""

    def __init__(self, agent_name: str = 'unknown', message: str = 'Agent execution failed', details: Optional[dict[str, Any]] = None) -> None:
        full_message = f'Agent [{agent_name}]: {message}'
        super().__init__(message=full_message, code='AGENT_EXECUTION_ERROR', status_code=500, details=details)


class VisionProcessingError(MentisError):
    """Raised when image/vision processing fails."""

    def __init__(self, message: str = 'Vision processing failed', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='VISION_PROCESSING_ERROR', status_code=422, details=details)


class SpeechSynthesisError(MentisError):
    """Raised when TTS/SSML generation fails."""

    def __init__(self, message: str = 'Speech synthesis failed', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='SPEECH_SYNTHESIS_ERROR', status_code=502, details=details)


# ── Rate Limiting Errors ───────────────────────────────────────────────


class RateLimitExceededError(MentisError):
    """Raised when the client has exceeded the rate limit."""

    def __init__(self, retry_after_seconds: int = 60) -> None:
        super().__init__(
            message=f'Rate limit exceeded. Retry after {retry_after_seconds} seconds.',
            code='RATE_LIMIT_EXCEEDED',
            status_code=429,
            details={'retry_after_seconds': retry_after_seconds},
        )


# ── File Upload Errors ─────────────────────────────────────────────────


class FileTooLargeError(MentisError):
    """Raised when the uploaded file exceeds the maximum size."""

    def __init__(self, max_size_mb: int = 10) -> None:
        super().__init__(
            message=f'File exceeds maximum size of {max_size_mb} MB.',
            code='FILE_TOO_LARGE',
            status_code=413,
        )


class UnsupportedFileTypeError(MentisError):
    """Raised when the uploaded file type is not allowed."""

    def __init__(self, allowed_extensions: list[str] | None = None) -> None:
        ext_list = ', '.join(allowed_extensions or [])
        super().__init__(
            message=f'Unsupported file type. Allowed: {ext_list}',
            code='UNSUPPORTED_FILE_TYPE',
            status_code=415,
        )


# ── AR Errors ──────────────────────────────────────────────────────────


class ARInstructionError(MentisError):
    """Raised when AR instruction generation or rendering fails."""

    def __init__(self, message: str = 'AR instruction error', details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message=message, code='AR_INSTRUCTION_ERROR', status_code=500, details=details)
