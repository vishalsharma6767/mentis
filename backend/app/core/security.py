"""Security utilities: password hashing, JWT token management, Appwrite verification.

Uses bcrypt directly (not passlib, which has compatibility issues with bcrypt>=4.1)
and PyJWT for token operations.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt as pyjwt

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    TokenExpiredError,
)

# ── Password ───────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8'),
    )


# ── Access Tokens ──────────────────────────────────────────────────────


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        subject: The user identifier (typically user ID).
        extra_claims: Additional claims to embed in the token.
        expires_delta: Custom expiration duration.

    Returns:
        The encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))

    payload: dict[str, Any] = {
        'sub': subject,
        'iat': now,
        'exp': expire,
        'type': 'access',
    }
    if extra_claims:
        payload.update(extra_claims)

    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT string.

    Returns:
        The decoded payload dictionary.

    Raises:
        InvalidTokenError: If the token is malformed or has an invalid signature.
        TokenExpiredError: If the token has expired.
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except pyjwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except pyjwt.PyJWTError as exc:
        raise InvalidTokenError(details={'reason': str(exc)})

    if payload.get('type') != 'access':
        raise InvalidTokenError(details={'reason': 'Invalid token type'})

    return payload


# ── Refresh Tokens ─────────────────────────────────────────────────────


def create_refresh_token(subject: str) -> str:
    """Create a long-lived JWT refresh token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    payload: dict[str, Any] = {
        'sub': subject,
        'iat': now,
        'exp': expire,
        'type': 'refresh',
    }
    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token."""
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except pyjwt.ExpiredSignatureError:
        raise TokenExpiredError(message='Refresh token has expired. Please log in again.')
    except pyjwt.PyJWTError as exc:
        raise InvalidTokenError(details={'reason': str(exc)})

    if payload.get('type') != 'refresh':
        raise InvalidTokenError(details={'reason': 'Invalid token type'})

    return payload


# ── Token Pair ─────────────────────────────────────────────────────────


def create_token_pair(subject: str) -> dict[str, str]:
    """Return an access token and a refresh token for the given user."""
    return {
        'access_token': create_access_token(subject),
        'refresh_token': create_refresh_token(subject),
        'token_type': 'bearer',
    }


def refresh_access_token(refresh_token: str) -> dict[str, str]:
    """Validate a refresh token and issue a new access + refresh pair."""
    payload = decode_refresh_token(token=refresh_token)
    subject: str = payload.get('sub', '')
    if not subject:
        raise InvalidTokenError(details={'reason': 'Missing subject claim'})
    return create_token_pair(subject)


# ── Current User Extraction ────────────────────────────────────────────


def get_user_id_from_token(token: str) -> str:
    """Extract the user ID from an access token.

    This is a convenience wrapper for FastAPI dependency injection.
    """
    payload = decode_access_token(token)
    user_id: str = payload.get('sub', '')
    if not user_id:
        raise AuthenticationError(message='Token does not contain a user identifier')
    return user_id
